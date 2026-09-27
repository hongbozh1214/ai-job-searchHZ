#!/usr/bin/env python3
"""Keep /scrape's growing history and tracker out of the model context.

lookup accepts a JSON array of {company, title, url} and emits only decisions.
add accepts a JSON array of new seen-job objects and refuses ambiguous or
previously recorded postings; no existing entry is replaced.
history answers a zero-result portal health check without printing job data.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from job_key import make_key, make_url_collision_key
from rank_state import load_state, norm, save_state, tracker_pairs


ROOT = Path(__file__).resolve().parent.parent
MARKETS = {"china", "europe", "finland"}


def source(url):
    return (url or "").strip().rstrip("/")


def read_state(path):
    if not path.exists():
        return {"seen": {}}, {}
    return load_state(path)


def entries(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("input must be a JSON array of objects")
    return value


def decision(candidate, seen, tracked):
    company = candidate.get("company")
    title = candidate.get("title")
    url = candidate.get("url", "")
    if not isinstance(company, str) or not company.strip() or not isinstance(title, str) or not title.strip():
        raise ValueError("each posting needs a company and title")
    if not isinstance(url, str):
        raise ValueError("posting url must be a string")
    url = source(url)
    pair = (norm(company), norm(title))
    same_url = [(key, row) for key, row in seen.items()
                if isinstance(row, dict) and url and source(row.get("url")) == url]
    if len(same_url) > 1:
        return {"decision": "ambiguous", "reason": "multiple saved entries share this URL"}
    if same_url:
        key, row = same_url[0]
        return {"decision": "seen_url", "key": key, "market": row.get("market"),
                "markets": row.get("markets", []), "status": row.get("status")}

    saved_pair = [(key, row) for key, row in seen.items() if isinstance(row, dict)
                  and (norm(row.get("company")), norm(row.get("title"))) == pair]
    if any(not url or not source(row.get("url")) for _, row in saved_pair):
        return {"decision": "ambiguous", "reason": "same company and title with missing URL"}
    tracked_urls = tracked.get(pair, set())
    if any(not url or not old or url == old for old in tracked_urls):
        return {"decision": "tracked", "reason": "same posting already in application tracker or missing URL"}

    key = make_key(company, title, url)
    if key in seen:
        old = seen[key]
        if not isinstance(old, dict) or not url or not source(old.get("url")):
            return {"decision": "ambiguous", "reason": "key occupied without distinct known URLs"}
        key = make_url_collision_key(company, title, url)
        if key in seen:
            return {"decision": "ambiguous", "reason": "URL collision key already occupied"}
    return {"decision": "new", "key": key}


def run_lookup(batch, seen, tracked):
    return [{"index": index, **decision(item, seen, tracked)} for index, item in enumerate(batch)]


def run_add(batch, state, tracker):
    doc, seen = read_state(state)
    tracked = tracker_pairs(tracker)
    pending = []
    # Check against all earlier entries in this batch; any conflict aborts the
    # entire write, so a rerun cannot silently overwrite an existing ranking.
    shadow = dict(seen)
    for index, item in enumerate(batch):
        result = decision(item, shadow, tracked)
        if result["decision"] != "new":
            raise ValueError(f"entry {index}: {result['decision']} ({result.get('reason', result.get('key', ''))})")
        key = result["key"]
        if item.get("key", key) != key:
            raise ValueError(f"entry {index}: key must be {key}")
        if item.get("market") not in MARKETS or item.get("status") not in {"new", "skipped", "expired"}:
            raise ValueError(f"entry {index}: invalid market or scraper status")
        if item.get("source") not in {"cli", "websearch"}:
            raise ValueError(f"entry {index}: invalid source")
        shadow[key] = {k: v for k, v in item.items() if k != "key"}
        pending.append(key)
    if pending:
        state.parent.mkdir(parents=True, exist_ok=True)
        save_state(state, {**doc, "seen": shadow} if "seen" in doc else shadow)
    return pending


def portal_history(seen, portal, domain):
    if domain and (not isinstance(domain, str) or "/" in domain or ":" in domain):
        raise ValueError("domain must be a hostname")
    return any(isinstance(row, dict) and (
        row.get("portal") == portal or
        (not row.get("portal") and domain and
         ((host := (urlsplit(row.get("url") or "").hostname or "").lower()) == domain or
          host.endswith("." + domain)))
    ) for row in seen.values())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("lookup", "add", "history"))
    parser.add_argument("--state", type=Path, default=ROOT / "job_scraper/seen_jobs.json")
    parser.add_argument("--tracker", type=Path, default=ROOT / "job_search_tracker.csv")
    parser.add_argument("--input", type=Path, help="JSON array for lookup/add")
    parser.add_argument("--portal", help="portal name for history")
    parser.add_argument("--domain", help="base hostname for legacy history")
    args = parser.parse_args(argv)
    try:
        if args.command in {"lookup", "add"} and not args.input:
            parser.error("lookup/add require --input")
        if args.command == "history" and not args.portal:
            parser.error("history requires --portal")
        if args.command == "add":
            print(json.dumps({"added": run_add(entries(args.input), args.state, args.tracker)}))
        else:
            _, seen = read_state(args.state)
            result = (run_lookup(entries(args.input), seen, tracker_pairs(args.tracker))
                      if args.command == "lookup" else
                      {"portal": args.portal, "previous_results": bool(portal_history(seen, args.portal, args.domain))})
            print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"scrape state: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
