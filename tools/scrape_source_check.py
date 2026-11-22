#!/usr/bin/env python3
"""Check the Europe/Finland portal ledger offline; never contacts a source."""

import argparse
import json
from pathlib import Path


MARKET_COUNTRIES = {"europe": ("GB", "DK", "DE", "NL", "BE", "CH"),
                    "finland": ("FI",)}
SKIP_REASONS = {
    "explicit_exclusion", "disabled", "not_installed", "not_interactive",
    "access_denied", "reader_incompatible",
    "dependency_unavailable", "tool_approval_denied", "budget_unconfirmed",
}
DEFER_REASONS = {"prior_country_stop", "tool_approval_pending", "interrupted"}


def no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def check(phase, countries, ledger):
    expected = ["linkedin", *(f"indeed:{code}" for code in countries)]
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    errors = [f"{key}: missing" for key in expected if key not in ledger]
    if set(ledger) - set(expected):
        errors.append("unexpected source or country entries")
    dispositions = {}
    for key in expected:
        if key not in ledger:
            continue
        row = ledger[key]
        if not isinstance(row, dict):
            errors.append(f"{key}: invalid entry")
            continue
        status = row.get("status")
        detail = row.get("evidence")
        evidence = isinstance(detail, str) and bool(detail.strip())
        reason = row.get("reason")
        skip_allowed = isinstance(reason, str) and (
            reason in SKIP_REASONS or (key.startswith("indeed:") and reason == "missing_indeed_scope")
        )
        if status == "skipped" and skip_allowed and evidence:
            dispositions[key] = status
        elif phase == "plan" and status == "planned":
            dispositions[key] = status
        elif phase == "report" and status in ("ran", "failed") and evidence:
            dispositions[key] = status
        elif (phase == "report" and status == "deferred" and isinstance(reason, str)
              and reason in DEFER_REASONS and evidence):
            dispositions[key] = status
        else:
            errors.append(f"{key}: invalid status or missing documented evidence")

    # A stopped Indeed batch must have an earlier, observed failure; a missing
    # result cannot by itself justify deferring the other countries this way.
    failed_indeed = False
    for key in expected[1:]:
        status = dispositions.get(key)
        if status == "deferred" and ledger[key].get("reason") == "prior_country_stop" and not failed_indeed:
            errors.append(f"{key}: no earlier failed Indeed call for prior_country_stop")
        if failed_indeed and status in ("ran", "failed"):
            errors.append(f"{key}: call recorded after a failed Indeed call")
        if status == "failed":
            failed_indeed = True

    return {
        "ok": not errors,
        "expected": expected,
        "errors": errors,
        "uncovered": [key for key in expected if dispositions.get(key) != "ran"]
        if phase == "report" else [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "report"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--market", required=True, choices=MARKET_COUNTRIES)
    parser.add_argument("--countries", nargs="+", choices=MARKET_COUNTRIES["europe"],
                        help="override only for explicitly narrower Europe runs")
    args = parser.parse_args()
    countries = MARKET_COUNTRIES[args.market]
    if args.countries:
        if args.market != "europe" or len(set(args.countries)) != len(args.countries):
            parser.error("country override requires Europe and unique countries")
        countries = tuple(code for code in countries if code in args.countries)
    try:
        ledger = json.loads(args.input.read_text(encoding="utf-8"),
                            object_pairs_hook=no_duplicate_keys)
        result = check(args.phase, countries, ledger)
    except (OSError, ValueError):
        # Do not echo input, filenames, evidence, or arbitrary supplied keys.
        result = {"ok": False, "errors": ["missing or invalid ledger"]}
    print(json.dumps({"market": args.market, **result}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
