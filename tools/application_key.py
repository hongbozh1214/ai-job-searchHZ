#!/usr/bin/env python3
"""Select an application draft/archive slug before writing any personal files.

Print JSON with slug and action. A second attempt at a closed application uses
its own dated slug, even if the posting URL is unchanged. Unknown provenance
fails closed rather than assigning another application's archive by title.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

if __package__:
    from .job_key import make_key, make_url_collision_key
else:
    from job_key import make_key, make_url_collision_key


ROOT = Path(__file__).resolve().parent.parent
FINAL = {"hired", "rejected", "no_response", "no response", "offer_declined",
         "offer declined", "withdrawn"}
MARKER = re.compile(r"(?:^|\s)(?:posting_key|china_posting_key):([^\s,]+)")
SAFE = re.compile(r"[^\W_][\w-]*\Z", re.UNICODE)


def ordinary_slug(company, role):
    """The legacy documents/README.md subfolder rule for Europe/Finland."""
    def component(value):
        return "_".join("".join(c for c in word.lower() if c.isalnum() or c == "_")
                        for word in re.split(r"\s+", value.strip()))
    return re.sub(r"_+", "_", f"{component(company)}_{component(role)}").strip("_")


def safe_slug(value):
    if not value or not SAFE.fullmatch(value):
        raise ValueError("posting marker is not a safe single folder name")
    return value


def row_slug(row, default):
    match = MARKER.search(row.get("notes") or "")
    return safe_slug(match.group(1)) if match else default


def choose(root, company, role, url="", market="europe", today=None):
    if not company.strip() or not role.strip():
        raise ValueError("company and role are required")
    today = today or date.today()
    base = safe_slug(make_key(company, role, url) if market == "china" else ordinary_slug(company, role))
    rows = []
    tracker = root / "job_search_tracker.csv"
    if tracker.exists():
        with tracker.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    matching = [r for r in rows if (r.get("company") or "").strip().casefold() == company.strip().casefold()
                and (r.get("role") or "").strip().casefold() == role.strip().casefold()]
    source = url.strip().rstrip("/")
    open_rows = [r for r in matching if (r.get("status") or "").strip().casefold() not in FINAL]
    if source:
        same = [r for r in matching if (r.get("source") or "").strip().rstrip("/") == source]
        open_same = [r for r in same if r in open_rows]
        if len(open_same) > 1:
            raise ValueError("more than one open tracker row has this URL; choose the application explicitly")
        if open_same:
            slug = row_slug(open_same[0], base)
            if any(row_slug(r, base) == slug for r in matching if r is not open_same[0]):
                raise ValueError("open and closed applications share an archive; resolve the legacy collision before drafting")
            return {"slug": slug, "action": "refresh_open"}
        # A URL-less older record could still be this application. Do not
        # mistake its occupied archive for a distinct known posting.
        if any(not (r.get("source") or "").strip() for r in matching):
            raise ValueError("older application has no source URL; identify its posting before drafting")
    elif matching:
        if len(matching) == 1 and len(open_rows) == 1 and not (open_rows[0].get("source") or "").strip():
            return {"slug": row_slug(open_rows[0], base), "action": "refresh_open"}
        raise ValueError("source URL missing and the existing application cannot be identified")

    occupied = {row_slug(r, base) for r in matching}
    archive = root / "documents/applications"
    if not archive.resolve().is_relative_to(root.resolve()):
        raise ValueError("application archive resolves outside this checkout")
    def in_use(slug):
        generated = (("cv", f"main_{slug}.*"), ("cv/chinese", f"main_{slug}.*"),
                     ("cover_letters", f"cover_{slug}.*"), ("cover_letters", f"Cover_{slug}.*"),
                     ("cover_letters/chinese", f"cover_{slug}.*"),
                     ("cover_letters/chinese", f"Cover_{slug}.*"))
        for folder, pattern in generated:
            parent = root / folder
            if not parent.resolve().is_relative_to(root.resolve()):
                raise ValueError("generated document path resolves outside this checkout")
            if any(parent.glob(pattern)):
                return True
        return slug in occupied or (archive / slug).exists() or (archive / slug).is_symlink()

    if source and any((r.get("source") or "").strip().rstrip("/") == source for r in matching):
        stem = safe_slug(f"{base}-attempt-{today:%Y%m%d}")
        slug = stem
        number = 2
        while in_use(slug):
            slug = f"{stem}-{number}"
            number += 1
        return {"slug": slug, "action": "new_attempt"}

    if in_use(base):
        if not source or not matching or any(not (r.get("source") or "").strip() for r in matching):
            raise ValueError("an existing draft/archive has unverified provenance; identify it before drafting")
        slug = safe_slug(make_url_collision_key(company, role, source))
        if in_use(slug):
            raise ValueError("URL-specific draft/archive already exists without a matching open tracker row")
        return {"slug": slug, "action": "new_posting"}
    return {"slug": base, "action": "new_posting"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--url", default="")
    ap.add_argument("--market", choices=("china", "europe", "finland"), default="europe")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        print(json.dumps(choose(args.root, args.company, args.role, args.url,
                                args.market, args.today), ensure_ascii=False))
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Cannot select application path: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
