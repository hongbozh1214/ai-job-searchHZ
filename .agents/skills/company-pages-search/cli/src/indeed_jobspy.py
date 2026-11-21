"""Run JobSpy's original Indeed request and hand one list page to the CLI."""

import hmac
import json
import logging
import os
import sys
from importlib.metadata import Distribution
from pathlib import Path

VERSION = "1.5.0"
ENDPOINT = "https://apis.indeed.com/graphql"
PAGE_SIZE = 100
BODY_LIMIT = 8 * 1024 * 1024


def fields(record, **limits):
    record = record if isinstance(record, dict) else {}
    return {key: record[key] for key, limit in limits.items()
            if isinstance(record.get(key), str) and len(record[key]) <= limit}


def lead_fields(row):
    job = row.get("job") if isinstance(row, dict) else None
    if not isinstance(job, dict):
        return {}
    lead = fields(job, key=80, title=1024, sourceEmployerName=512)
    if type(job.get("dateOnIndeed")) is int:
        lead["dateOnIndeed"] = job["dateOnIndeed"]
    lead["location"] = fields(job.get("location"), countryCode=2, city=256)
    lead["employer"] = fields(job.get("employer"), name=512)
    lead["recruit"] = fields(job.get("recruit"), viewJobUrl=2048)
    return {"job": lead}


def project_page(payload):
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        return None
    if errors:
        return {"errors": [{"extensions": fields(error.get("extensions"), code=80)}
                           if isinstance(error, dict) else {} for error in errors[:PAGE_SIZE]]}
    data = payload.get("data")
    search = data.get("jobSearch") if isinstance(data, dict) else None
    rows = search.get("results") if isinstance(search, dict) else None
    if not isinstance(rows, list):
        return None
    page = {"results": [lead_fields(row) for row in rows[:PAGE_SIZE + 1]]}
    info = search.get("pageInfo")
    if isinstance(info, dict) and "nextCursor" in info:
        page["pageInfo"] = {"nextCursor": None if info["nextCursor"] is None else True}
    return {"data": {"jobSearch": page}}


def read_page(response, result):
    result["status"] = response.status_code
    result["challenge"] = response.headers.get("cf-mitigated") == "challenge"
    if response.status_code == 429:
        result["retry_after"] = response.headers.get("Retry-After", "")[:64]
    if response.status_code != 200 or result["challenge"]:
        return
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("application/json", "application/graphql-response+json"):
        result["error"] = "indeed_non_json_response"
        return
    body = bytearray()
    for chunk in response.iter_content(65536):
        if len(body) + len(chunk) > BODY_LIMIT:
            result["error"] = "indeed_body_too_large"
            return
        body.extend(chunk)
    try:
        result["payload"] = project_page(json.loads(body.decode("utf-8")))
    except (UnicodeError, ValueError, RecursionError):
        result["error"] = "indeed_invalid_json_body"


class FirstPageRead(Exception):
    """Stop inside JobSpy after reading the first response."""


def run_page(keyword, country_code, result):
    vendor = Path(os.environ.get("INDEED_JOBSPY_VENDOR_DIR", ""))
    if not vendor.is_absolute() or not vendor.is_dir():
        result["error"] = "indeed_jobspy_unavailable"
        return
    distribution = next(Distribution.discover(name="python-jobspy", path=[str(vendor)]), None)
    if distribution is None or distribution.version != VERSION:
        result["error"] = "indeed_jobspy_unavailable"
        return
    sys.path.insert(0, str(vendor))
    try:
        from requests import exceptions
        from requests.utils import select_proxy
        from urllib3.exceptions import ReadTimeoutError
        from jobspy.indeed import Indeed
        from jobspy.indeed.constant import country_codes, headers, jobs_per_page
        from jobspy.model import ScraperInput, Site
        from jobspy.util import RequestsRotating
    except (ImportError, OSError):
        result["error"] = "indeed_jobspy_unavailable"
        return
    key = os.environ.get("INDEED_SHARED_API_KEY", "")
    if not key or not hmac.compare_digest(key, headers["indeed-api-key"]):
        result["error"] = "indeed_jobspy_credential_mismatch"
        return
    if jobs_per_page != PAGE_SIZE or Indeed.api_url != ENDPOINT:
        result["error"] = "indeed_jobspy_unavailable"
        return
    country = next((country for country in country_codes if country_codes[country] == country_code), None)
    if country is None:
        result["error"] = "indeed_country_unsupported"
        return
    location = "United Kingdom" if country_code == "GB" else country.value.title()

    post = RequestsRotating.post

    def first_post(session, url, **kwargs):
        if url != ENDPOINT or result["requests"]:
            result["error"] = "indeed_jobspy_request_budget"
            raise FirstPageRead()
        settings = session.merge_environment_settings(url, {}, True, None, None)
        if (select_proxy(url, settings["proxies"]) or settings["verify"] is False
                or session.get_adapter(url).max_retries.total != 0):
            result["error"] = "indeed_jobspy_transport_configuration"
            raise FirstPageRead()
        session.trust_env = False
        result["requests"] = 1
        try:
            with post(session, url, **kwargs, allow_redirects=False,
                      stream=True, timeout=(5, 15)) as response:
                read_page(response, result)
        except exceptions.Timeout:
            result["error"] = "indeed_jobspy_timeout"
        except exceptions.RequestException as exc:
            # Requests wraps streaming read timeouts in ConnectionError.
            result["error"] = ("indeed_jobspy_timeout" if isinstance(exc.__context__, ReadTimeoutError)
                               else "indeed_transport_failure")
        # The project validates and normalizes this page. JobSpy must not follow its cursor.
        raise FirstPageRead()

    RequestsRotating.post = first_post
    try:
        Indeed().scrape(ScraperInput(site_name=[Site.INDEED], country_indeed=country,
                                    location=location, search_term=keyword, results_wanted=PAGE_SIZE))
    finally:
        RequestsRotating.post = post
    if "status" not in result and "error" not in result:
        result["error"] = "indeed_jobspy_process_failed"


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    result = {"requests": 0}
    try:
        run_page(sys.argv[1], sys.argv[2], result)
    except Exception:
        result["error"] = "indeed_jobspy_process_failed"
    print(json.dumps(result))
