import { expect, test } from "bun:test"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { parseIndeedPage } from "../src/indeed"

const parseIndeedFinland = (value: unknown) => parseIndeedPage(value, "FI")

const cli = fileURLToPath(new URL("../src/cli.ts", import.meta.url))
const markets = { FI: "Finland", GB: "United Kingdom", DK: "Denmark", DE: "Germany", NL: "Netherlands", BE: "Belgium", CH: "Switzerland", CN: "China" } as const
const finnishJob = {
  key: "synthetic1", title: "Research scientist", sourceEmployerName: "Fixture Labs",
  location: { countryCode: "FI", city: "Espoo" },
  recruit: { viewJobUrl: "https://careers.example.test/jobs/1" },
}
const page = (jobs: unknown[], nextCursor: string | null = null) => ({
  data: { jobSearch: { results: jobs.map(job => ({ job })), pageInfo: { nextCursor } } },
})

const fixtureSession = String.raw`
import json
from pathlib import Path
from types import SimpleNamespace
from requests import exceptions
from urllib3.exceptions import ReadTimeoutError

fixture = Path(__file__).parents[1] / "response.json"

class Response:
    def __init__(self, spec):
        self.status_code = spec.get("status", 200)
        self.headers = {"Content-Type": "application/json", "Retry-After": "60"}
        self.body = spec.get("raw", json.dumps(spec.get("payload")))
        self.body_timeout = spec.get("body_timeout")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def iter_content(self, _):
        if self.body_timeout:
            try:
                raise ReadTimeoutError()
            except ReadTimeoutError as exc:
                raise exceptions.RequestException() from exc
        yield self.body.encode()

class RequestsRotating:
    def merge_environment_settings(self, *_):
        return {"proxies": {}, "verify": True}

    def get_adapter(self, _):
        return SimpleNamespace(max_retries=SimpleNamespace(total=0))

    def post(self, url, *, json, allow_redirects, stream, timeout):
        assert url == "https://apis.indeed.com/graphql"
        assert json == {"query": "stock request"}
        assert allow_redirects is False and stream and timeout == (5, 15)
        assert self.trust_env is False
        with fixture.with_name("one-post").open("x") as file:
            file.write("1")
        spec = __import__("json").loads(fixture.read_text())
        if spec.get("timeout"):
            raise exceptions.Timeout()
        return Response(spec)
`
const fixtureJobSpy = String.raw`
import json
from pathlib import Path
from jobspy.util import RequestsRotating

class Indeed:
    api_url = "https://apis.indeed.com/graphql"

    def scrape(self, args):
        assert args.site_name == ["indeed"]
        requested = json.loads((Path(__file__).parents[2] / "response.json").read_text())
        expected_country = requested["country"]
        assert args.country_indeed.value == ("uk" if expected_country == "United Kingdom" else expected_country.lower())
        assert args.location == expected_country
        assert args.search_term == "protein" and args.results_wanted == 100
        try:
            RequestsRotating().post(self.api_url, json={"query": "stock request"})
            raise AssertionError("JobSpy was not stopped after the first page")
        except Exception as exc:
            if type(exc).__name__ != "FirstPageRead":
                raise
`

function cliReplay(response: object, key = "synthetic-key", country?: keyof typeof markets) {
  const cwd = mkdtempSync(join(tmpdir(), "indeed-jobspy-test-"))
  const codes = Object.keys(markets)
  const enumValues = Object.entries(markets).map(([code, name]) => `    ${code} = "${code === "GB" ? "uk" : name.toLowerCase()}"`).join("\n")
  const fixture = {
    "requests/__init__.py": "",
    "requests/exceptions.py": "class RequestException(Exception): pass\nclass Timeout(RequestException): pass\n",
    "requests/utils.py": "def select_proxy(url, proxies): return proxies.get(url)\n",
    "urllib3/__init__.py": "",
    "urllib3/exceptions.py": "class ReadTimeoutError(Exception): pass\n",
    "jobspy/__init__.py": "",
    "jobspy/indeed/__init__.py": fixtureJobSpy,
    "jobspy/indeed/constant.py": `from jobspy.model import Country\nheaders = {"indeed-api-key": "synthetic-key"}\njobs_per_page = 100\ncountry_codes = {${codes.map(code => `Country.${code}:"${code}"`).join(",")}}\n`,
    "jobspy/model.py": `from enum import Enum\nfrom types import SimpleNamespace as ScraperInput\nclass Country(Enum):\n${enumValues}\nclass Site: INDEED = "indeed"\n`,
    "jobspy/util.py": fixtureSession,
    "python_jobspy-1.5.0.dist-info/METADATA": "Name: python-jobspy\nVersion: 1.5.0\n",
    "response.json": JSON.stringify({ ...response, country: markets[country ?? "FI"] }),
  }
  try {
    for (const [name, content] of Object.entries(fixture)) {
      const path = join(cwd, name)
      mkdirSync(join(path, ".."), { recursive: true })
      writeFileSync(path, content)
    }
    const args = [process.execPath, "run", cli, "search", "--source", "indeed", "--query", "protein", "--format", "json"]
    if (country) args.push("--country", country)
    const result = Bun.spawnSync(args, {
      cwd, env: { PATH: process.env.PATH, INDEED_SHARED_API_KEY: key, INDEED_JOBSPY_VENDOR_DIR: cwd },
    })
    expect(result.exitCode).toBe(0)
    const stdout = result.stdout.toString()
    expect(stdout).not.toContain("synthetic-key")
    expect(stdout).not.toContain("fixture-only body")
    const resultJson = JSON.parse(stdout)
    const attempts = Bun.file(join(cwd, "one-post")).size > 0 ? Number(readFileSync(join(cwd, "one-post"), "utf8")) : 0
    expect(resultJson.meta.coverage[0].requests).toBe(attempts)
    return resultJson
  } finally {
    rmSync(cwd, { recursive: true, force: true })
  }
}

test("CLI reads one JobSpy page and emits deduplicated provisional Finnish leads", () => {
  const result = cliReplay({ payload: page([
    { ...finnishJob, description: { html: "fixture-only body" } }, finnishJob,
    { ...finnishJob, key: "outside", location: { countryCode: "SE" } },
    { ...finnishJob, key: "unknown", location: null },
  ], "never-follow-this-cursor") })
  expect(result.meta.coverage[0]).toMatchObject({ status: "partial", requests: 1, received_count: 4 })
  expect(result.meta.errors).toEqual([{ company: "Indeed", error: "country_unverified:3" }])
  expect(result.results).toMatchObject([{
    id: "synthetic1", company: "Fixture Labs", date: null, date_source: null, country: "FI",
    reported_external_url: "https://careers.example.test/jobs/1", needs_detail: true,
  }])
})

test("missing or mismatched credential prevents the POST", () => {
  for (const [key, reason] of [["", "indeed_runtime_key_unavailable"], ["other", "indeed_jobspy_credential_mismatch"]]) {
    const result = cliReplay({}, key)
    expect(result.meta.coverage[0]).toMatchObject({ status: "unknown", requests: 0, reason })
  }
})

test("Europe and China requests carry their selected country and discard jobs from other countries", () => {
  for (const country of ["GB", "DK", "DE", "NL", "BE", "CH", "CN"] as const) {
    const domain = country === "GB" ? "uk" : country.toLowerCase()
    const result = cliReplay({ payload: page([
      finnishJob, { ...finnishJob, key: "europe1", location: { countryCode: country, city: "Fixture city" } },
    ]) }, "synthetic-key", country)
    expect(result.meta.coverage[0]).toMatchObject({ status: "partial", country_scope: country, requests: 1, received_count: 2 })
    expect(result.results).toMatchObject([{ id: "europe1", country, url: `https://${domain}.indeed.com/viewjob?jk=europe1` }])
  }
  const invalid = Bun.spawnSync([process.execPath, "run", cli, "search", "--source", "indeed", "--query", "protein", "--country", "EU"], {
    env: { PATH: process.env.PATH },
  })
  expect(invalid.exitCode).toBe(1)
  expect(JSON.parse(invalid.stderr.toString()).code).toBe("BAD_ARG")
})

test("CLI distinguishes a valid empty page from denial, throttle, timeout and malformed data", () => {
  const cases = [
    [{ payload: page([]) }, "valid_empty", "empty_first_page"],
    [{ status: 403 }, "blocked", "indeed_http_403"],
    [{ status: 429 }, "rate_limited", "indeed_http_429"],
    [{ status: 302 }, "unknown", "indeed_http_302"],
    [{ timeout: true }, "unknown", "indeed_jobspy_timeout"],
    [{ body_timeout: true }, "unknown", "indeed_jobspy_timeout"],
    [{ raw: "<html>" }, "parse_failed", "indeed_invalid_json_body"],
  ] as const
  for (const [response, status, reason] of cases) {
    const result = cliReplay(response)
    expect(result.results).toEqual([])
    expect(result.meta.coverage[0]).toMatchObject({ status, reason, requests: 1 })
    if (status !== "valid_empty") expect(result.meta.errors).toEqual([{ company: "Indeed", error: reason }])
    if (status === "rate_limited") expect(result.meta.coverage[0].retry_after).toBe("60")
  }
})

test("response parser preserves the original page budget and coverage boundaries", () => {
  expect(parseIndeedFinland({ data: { jobSearch: { results: [] } } }).coverage).toBe("unknown")
  expect(parseIndeedFinland(null).coverage).toBe("parse_failed")
  expect(parseIndeedFinland({ errors: [{ extensions: { code: "FORBIDDEN" } }] }).coverage).toBe("blocked")
  expect(parseIndeedFinland(page(Array(100).fill(finnishJob))).coverage).toBe("partial")
  expect(parseIndeedFinland(page(Array(101).fill(finnishJob))).reason).toBe("response_page_budget_exceeded")
})
