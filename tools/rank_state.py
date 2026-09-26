#!/usr/bin/env python3
"""State helper for /rank: select candidates and write results back.

/rank reads the whole of seen_jobs.json into the model's context to filter it
by eye (Step 1), then re-emits the whole file to record scores (Step 4). That
cost is paid on every run regardless of how many jobs are actually scored, and
it grows for the life of the workspace, since seen_jobs.json is append-only by
design and most stored entries are `skipped`.

This moves the state-file traffic into code. Three subcommands:

  candidates   select the eligible entries for this run and project only the
               fields a scoring agent needs
  sweep        rule 6's expiry pass over entries this run did not re-score -
               a stored-date comparison, no fetch, no agent
  apply        write scoring results back to seen_jobs.json and print the
               ranked/vetoed/expired rows Step 5's report is built from

Selection and projection follow Step 1's existing rules exactly (status
filter, tracker exclusion, focus filter, `--limit`/`--all`); the write-back
follows Step 4's existing rules exactly (the `location` -> `location_verdict`
legacy migration, the deadline null-is-not-a-correction rule, verbatim
strengths/gaps persistence, idempotent skip of already-ranked entries); the
sweep follows rule 6 exactly (defensive date parsing, an absent deadline left
alone, `--all` making a retired entry revivable).

Nothing here fetches a posting or judges a fit. Scoring stays with the model;
this only removes the state file from the conversation.

Usage:
  python3 tools/rank_state.py candidates --market MARKET [--all] [--focus TEXT] [--limit N]
  python3 tools/rank_state.py sweep --market MARKET [--write] [--exclude KEY,KEY]
  python3 tools/rank_state.py apply --market MARKET --results results.json [--dry-run]

All subcommands print JSON on stdout. Exit 0 on success, 1 on a usage or
state error, or on `apply` when any result could not be written.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from job_key import make_key

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "job_scraper" / "seen_jobs.json"
TRACKER = ROOT / "job_search_tracker.csv"

# 04-job-evaluation.md
WEIGHTS = {"technical": 0.30, "experience": 0.25, "behavioral": 0.15, "career": 0.30}
BANDS = ((75, "Strong Fit"), (60, "Good Fit"), (45, "Moderate Fit"), (30, "Weak Fit"), (0, "Poor Fit"))

DEFAULT_LIMIT = 10
URGENT_DAYS = 7
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARKETS = ("china", "europe", "finland")
INBOX = ROOT / "markets" / "china" / "jobs" / "inbox"
REQUIRED_GATES = {
    "china": ("compensation", "work_schedule", "employment_type", "social_insurance", "role_type", "qualifications"),
    "europe": ("authorization", "contract", "compensation", "mobility"),
    "finland": ("authorization", "contract", "compensation", "qualifications"),
}
VERDICTS = {"PASS", "FLAG", "FAIL"}


def load_state(path: Path) -> tuple[dict, dict]:
    """Return (document, seen-map). The map is mutated in place by callers."""
    if not path.is_file():
        sys.exit(f"{path} not found - run /scrape first")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")
    seen = doc.get("seen") if isinstance(doc, dict) and "seen" in doc else doc
    if not isinstance(seen, dict):
        sys.exit(f"{path}: expected an object of job entries")
    return doc, seen


def save_state(path: Path, doc: dict) -> None:
    """Atomic replace: a half-written seen_jobs.json loses the scrape history."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".seen_jobs.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def parse_iso(value) -> date | None:
    """Rule 6's defensive-parse rule: anything that is not YYYY-MM-DD is treated
    exactly like an absent value - never compared, never guessed at."""
    if not isinstance(value, str) or not ISO.match(value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def norm(text) -> str:
    """Ignore case and separators without discarding non-Latin identity."""
    text = unicodedata.normalize("NFC", str(text or "").casefold())
    # Combining marks can distinguish names even after NFC (e.g. Indic vowels).
    return "".join(
        char for char in text
        if char.isalnum() or unicodedata.category(char).startswith("M")
    )


def tracker_pairs(path: Path) -> set[tuple[str, str]]:
    """company+role pairs already in the tracker - out of scope for ranking."""
    if not path.is_file():
        return set()
    import csv

    pairs = set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            company, role = norm(row.get("company")), norm(row.get("role"))
            if company:
                pairs.add((company, role))
    return pairs


def entry_location_verdict(entry: dict) -> str | None:
    """location_verdict, falling back to a legacy verdict stored under `location`
    (Step 4: "an entry ranked before this rename may carry a legacy PASS/FAIL/
    FLAG string in `location`")."""
    verdict = entry.get("location_verdict")
    if verdict:
        return verdict
    legacy = entry.get("location")
    return legacy if legacy in ("PASS", "FAIL", "FLAG") else None


def cmd_candidates(args) -> int:
    _, seen = load_state(args.state)
    excluded = tracker_pairs(args.tracker)

    selected, skipped_tracker, skipped_market, unknown_market = [], 0, 0, 0
    for key, entry in seen.items():
        status = entry.get("status")
        if args.all:
            if status == "skipped":
                continue
        elif status != "new":
            continue
        if args.market:
            entry_market = entry.get("market")
            if not entry_market:
                unknown_market += 1
                continue
            if entry_market != args.market:
                skipped_market += 1
                continue
        if (norm(entry.get("company")), norm(entry.get("title"))) in excluded:
            skipped_tracker += 1
            continue
        if args.focus:
            haystack = " ".join(
                [str(entry.get("title") or ""), str(entry.get("company") or "")]
                + [str(b) for b in entry.get("strengths") or []]
                + [str(b) for b in entry.get("gaps") or []]
            ).lower()
            if args.focus.lower() not in haystack:
                continue
        selected.append(
            {
                "key": key,
                "title": entry.get("title"),
                "company": entry.get("company"),
                "url": entry.get("url"),
                "portal": entry.get("portal"),
                "deadline": entry.get("deadline"),
                "posted_date": entry.get("posted_date"),
                **({"job_file": entry["job_file"]} if entry.get("job_file") else {}),
            }
        )

    eligible = len(selected)
    if args.limit > 0:
        selected = selected[: args.limit]
    print(
        json.dumps(
            {
                "market": args.market,
                "eligible": eligible,
                "selected": selected,
                "deferred": max(0, eligible - len(selected)),
                "excluded_by_tracker": skipped_tracker,
                "excluded_by_market": skipped_market,
                "unknown_market": unknown_market,
                "total_entries": len(seen),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_sweep(args) -> int:
    doc, seen = load_state(args.state)
    today = args.today
    exclude = {k for k in (args.exclude or "").split(",") if k}

    expired, closing, unparseable, checked = [], [], [], 0
    skipped_market, unknown_market = 0, 0
    for key, entry in seen.items():
        if entry.get("status") != "ranked" or key in exclude:
            continue
        if args.market:
            entry_market = entry.get("market")
            if not entry_market:
                unknown_market += 1
                continue
            if entry_market != args.market:
                skipped_market += 1
                continue
        checked += 1
        raw = entry.get("deadline")
        if raw in (None, ""):
            continue
        parsed = parse_iso(raw)
        if parsed is None:
            unparseable.append({"key": key, "portal": entry.get("portal"), "deadline": raw})
            continue
        row = {
            "key": key,
            "title": entry.get("title"),
            "company": entry.get("company"),
            "url": entry.get("url"),
            "deadline": raw,
        }
        if parsed < today:
            expired.append(row)
        elif (parsed - today).days <= URGENT_DAYS:
            closing.append(row)

    if args.write and expired:
        for row in expired:
            seen[row["key"]]["status"] = "expired"
        save_state(args.state, doc)

    print(
        json.dumps(
            {
                "market": args.market,
                "swept": checked,
                "newly_expired": expired,
                "closing_soon": sorted(closing, key=lambda r: r["deadline"]),
                "unparseable_deadlines": unparseable,
                "excluded_by_market": skipped_market,
                "unknown_market": unknown_market,
                "written": bool(args.write and expired),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def overall_score(scores: dict) -> int:
    if not isinstance(scores, dict):
        raise ValueError("scores must be an object")
    total = 0.0
    for dim, weight in WEIGHTS.items():
        value = scores.get(dim)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"missing or non-numeric score '{dim}'")
        if not 0 <= value <= 100:
            raise ValueError(f"score '{dim}' must be finite and between 0 and 100")
        total += float(value) * weight
    return int(total + 0.5)


def band(score: int) -> str:
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "Poor Fit"


def checked_gates(value, market: str) -> dict:
    """Require an explicit decision for every market rule, including unknowns."""
    if not isinstance(value, dict):
        raise ValueError("market_gates must be an object of gate decisions")
    missing = set(REQUIRED_GATES[market]) - set(value)
    if missing:
        raise ValueError("market_gates missing: " + ", ".join(sorted(missing)))
    for name, decision in value.items():
        if not isinstance(name, str) or not isinstance(decision, dict):
            raise ValueError("market_gates entries must be named objects")
        if not isinstance(decision.get("verdict"), str) or decision["verdict"] not in VERDICTS:
            raise ValueError(f"market_gates.{name} requires PASS, FLAG or FAIL")
        if decision["verdict"] != "PASS" and (not isinstance(decision.get("reason"), str)
                                                   or not decision["reason"].strip()):
            raise ValueError(f"market_gates.{name} needs a reason for FLAG or FAIL")
    return value


def local_job(path: Path) -> tuple[str, str, str, str]:
    """Parse an intentionally saved full JD; never accept a search snippet."""
    content = path.read_text(encoding="utf-8-sig")
    header = re.search(r"^#\s+(.+?)\s+@\s+(.+?)\s*$", content, re.M)
    if not header:
        raise ValueError("expected first-level heading '# <Role> @ <Company>'")
    title, company = (part.strip() for part in header.groups())
    if not title or not company:
        raise ValueError("role and company are required")
    sections = re.split(r"^##\s+", content, flags=re.M)
    parts = {section.split("\n", 1)[0].strip().lower(): section.partition("\n")[2].strip()
             for section in sections[1:]}
    pasted = parts.get("paste full jd below", "")
    responsibilities = parts.get("responsibilities", "")
    requirements = parts.get("requirements", "")
    valid = (len(pasted) >= 160 or
             (len(responsibilities) >= 40 and len(requirements) >= 40))
    if not valid:
        raise ValueError("full JD missing: paste >=160 characters under '## Paste Full JD Below', "
                         "or provide substantial Responsibilities and Requirements sections")
    url_match = re.search(r"^\*\*Source URL:\*\*\s*(https?://\S+)", content, re.M)
    return title, company, url_match.group(1) if url_match else "", content


def cmd_import_local(args) -> int:
    """Promote complete China inbox files to canonical scraper state offline."""
    inbox = args.inbox.resolve()
    paths = args.file or sorted(inbox.glob("*.md"))
    if not paths:
        print(json.dumps({"imported": [], "unchanged": [], "errors": [], "written": False}))
        return 0
    if args.state.is_file():
        doc, seen = load_state(args.state)
    else:
        doc = {"seen": {}}
        seen = doc["seen"]
    imported, unchanged, errors = [], [], []
    for path in paths:
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(inbox) or path.suffix.lower() != ".md" or not resolved.is_file():
                raise ValueError("file must be a Markdown file inside the China inbox")
            title, company, url, content = local_job(resolved)
            key = make_key(company, title, url)
            # Preserve legacy keys and the portal source when a scrape already
            # recorded the same posting. Never modify another market's record.
            matches = [k for k, e in seen.items() if isinstance(e, dict) and e.get("market") == "china"
                       and ((url and e.get("url") == url) or
                            (norm(e.get("company")), norm(e.get("title"))) == (norm(company), norm(title)))]
            if len(matches) > 1:
                raise ValueError("ambiguous duplicate records: " + ", ".join(matches))
            key = matches[0] if matches else key
            if key in seen and seen[key].get("market") != "china":
                raise ValueError(f"key {key} belongs to another market; cannot overwrite")
            relative = resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            existing = seen.get(key, {})
            if existing.get("job_file_hash") == digest and existing.get("job_file") == str(relative):
                unchanged.append({"key": key, "job_file": str(relative)})
                continue
            # Fresh local evidence reopens a previously ranked entry for triage;
            # the stored deadline is still enforced when applying the new score.
            seen[key] = {
                **existing, "title": title, "company": company,
                "url": url or existing.get("url") or "", "first_seen": existing.get("first_seen") or args.today.isoformat(),
                "market": "china", "portal": existing.get("portal") or "manual",
                "source": existing.get("source") or "local",
                "status": "new", "fetch_status": "ready",
                "job_file": str(relative), "job_file_hash": digest,
            }
            imported.append({"key": key, "job_file": str(relative)})
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    if imported:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        save_state(args.state, doc)
    print(json.dumps({"market": args.market, "imported": imported,
                      "unchanged": unchanged, "errors": errors,
                      "written": bool(imported)}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


def cmd_apply(args) -> int:
    doc, seen = load_state(args.state)
    today = args.today
    try:
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"cannot read results file {args.results}: {exc}")
    if isinstance(results, dict):
        results = results.get("results", [])
    if not isinstance(results, list):
        sys.exit("results file must be a JSON array of scoring objects")

    rows, expired, errors = [], [], []
    for result in results:
        if not isinstance(result, dict):
            errors.append({"key": None, "error": "result must be an object"})
            continue
        key = result.get("key")
        entry = seen.get(key) if isinstance(key, str) else None
        if entry is None:
            errors.append({"key": key, "error": "no such key in seen_jobs.json"})
            continue
        if args.market:
            entry_market = entry.get("market")
            if not entry_market:
                errors.append({
                    "key": key,
                    "error": f"entry has no market; cannot apply a {args.market} ranking",
                })
                continue
            if entry_market != args.market:
                errors.append({
                    "key": key,
                    "error": f"entry belongs to market '{entry_market}', not '{args.market}'",
                })
                continue

        # A fresh deadline overrides the stored one; an absent deadline does
        # not erase a known date. Never let even a high score revive a closed job.
        fresh_deadline = result.get("deadline")
        if fresh_deadline and parse_iso(fresh_deadline) is None:
            errors.append({"key": key, "error": "fresh deadline must be YYYY-MM-DD"})
            continue
        deadline = fresh_deadline if fresh_deadline else entry.get("deadline")
        if result.get("status") == "expired" or (parse_iso(deadline) or today) < today:
            entry["status"] = "expired"
            if fresh_deadline:
                entry["deadline"] = fresh_deadline
            expired.append(
                {"key": key, "title": entry.get("title"), "company": entry.get("company"),
                 "url": entry.get("url"), "deadline": entry.get("deadline")}
            )
            continue

        try:
            score = overall_score(result.get("scores") or {})
            gates = checked_gates(result.get("market_gates"), args.market)
        except ValueError as exc:
            errors.append({"key": key, "error": str(exc)})
            continue

        legacy = entry_location_verdict(entry)
        if entry.get("location") in ("PASS", "FAIL", "FLAG"):
            entry.pop("location", None)  # legacy verdict, never a place
        entry["status"] = "ranked"
        entry["rank_score"] = score
        entry["rank_verdict"] = band(score)
        entry["rank_date"] = today.isoformat()
        entry["location_verdict"] = result.get("location_verdict") or legacy or "PASS"
        entry["language_gate"] = result.get("language_gate") or "PASS"
        entry["market_gates"] = gates
        if entry["language_gate"] == "PASS":
            entry.pop("language_note", None)
        else:
            entry["language_note"] = result.get("language_note")
        # Absence is not a correction: a fetch that degraded to a listing page
        # returns no deadline, and blanking a stored one would erase a real
        # date and make the entry immortal to rule 6's sweep.
        if result.get("deadline"):
            entry["deadline"] = result["deadline"]
        for field in ("strengths", "gaps"):
            value = result.get(field)
            if isinstance(value, list):
                entry[field] = [str(b) for b in value][:3]

        parsed = parse_iso(entry.get("deadline"))
        rows.append(
            {
                "key": key,
                "title": entry.get("title"),
                "company": entry.get("company"),
                "location": entry.get("location"),
                "url": entry.get("url"),
                "score": score,
                "verdict": entry["rank_verdict"],
                "location_verdict": entry["location_verdict"],
                "language_gate": entry["language_gate"],
                "language_note": entry.get("language_note"),
                "market_gates": gates,
                "deadline": entry.get("deadline"),
                "posted_date": entry.get("posted_date"),
                "urgent": bool(parsed and today <= parsed <= today + timedelta(days=URGENT_DAYS)),
                "strengths": entry.get("strengths", []),
                "gaps": entry.get("gaps", []),
            }
        )

    if not args.dry_run:
        save_state(args.state, doc)

    rows.sort(key=lambda r: (r["score"], r["urgent"]), reverse=True)
    veto = lambda r: (r["location_verdict"] == "FAIL" or r["language_gate"] == "FAIL"
                      or any(g["verdict"] == "FAIL" for g in r["market_gates"].values()))
    vetoed = [r for r in rows if veto(r)]
    ranked = [r for r in rows if not veto(r)]
    print(
        json.dumps(
            {
                "market": args.market,
                "ranked": ranked,
                "vetoed": vetoed,
                "expired": expired,
                "errors": errors,
                "written": not args.dry_run,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is.

    A piped stdout on Windows defaults to the ANSI code page (cp1252 on most
    Western installs), so printing a company, title or file name outside it
    raised UnicodeEncodeError before the workflow saw any output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")


def main() -> int:
    _force_utf8_output()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", type=Path, default=STATE)
    common.add_argument("--today", type=date.fromisoformat, default=date.today())
    common.add_argument(
        "--market",
        choices=MARKETS,
        required=True,
        help="restrict state reads and writes to one configured market",
    )

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    cand = sub.add_parser("candidates", parents=[common], help="select the entries to score")
    cand.add_argument("--tracker", type=Path, default=TRACKER)
    cand.add_argument("--all", action="store_true", help="include every non-skipped status")
    cand.add_argument("--focus", help="substring filter over title, company and stored fit notes")
    cand.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="0 for no cap")
    cand.set_defaults(func=cmd_candidates)

    sweep = sub.add_parser("sweep", parents=[common], help="rule 6's expiry pass, no fetch")
    sweep.add_argument("--write", action="store_true", help="persist the expiries")
    sweep.add_argument("--exclude", help="comma-separated keys re-scored this run")
    sweep.set_defaults(func=cmd_sweep)

    app = sub.add_parser("apply", parents=[common], help="write scoring results back and print the ranking")
    app.add_argument("--results", required=True, help="JSON array from the scoring agents")
    app.add_argument("--dry-run", action="store_true")
    app.set_defaults(func=cmd_apply)

    local = sub.add_parser("import-local", parents=[common], help="ingest full China inbox JDs offline")
    local.add_argument("--inbox", type=Path, default=INBOX)
    local.add_argument("--file", type=Path, action="append", help="one inbox Markdown file; repeat for multiple files")
    local.set_defaults(func=cmd_import_local)

    args = ap.parse_args()
    if args.command == "import-local" and args.market != "china":
        ap.error("import-local requires --market china")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
