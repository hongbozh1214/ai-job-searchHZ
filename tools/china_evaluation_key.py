#!/usr/bin/env python3
"""Choose a China evaluation path without replacing another saved JD's report."""

import argparse
import hashlib
import re
import sys
from pathlib import Path

if __package__:
    from .job_key import make_key, make_url_collision_key
else:
    from job_key import make_key, make_url_collision_key


ROOT = Path(__file__).resolve().parent.parent


def choose(root, source, company, title, url=""):
    inbox = root / "markets/china/jobs/inbox"
    if not inbox.resolve(strict=True).is_relative_to(root.resolve()):
        raise ValueError("China inbox resolves outside this checkout")
    local = source if source.is_absolute() else root / source
    local = local.resolve(strict=True)
    if not local.is_file() or not local.is_relative_to(inbox.resolve(strict=True)):
        raise ValueError("JD must be a file in the China inbox")
    relative = local.relative_to(root.resolve()).as_posix()
    base = make_key(company, title, url)
    reports = root / "markets/china/jobs/evaluated"
    if not reports.resolve().is_relative_to(root.resolve()):
        raise ValueError("China evaluation directory resolves outside this checkout")

    def report_identity(key):
        target = reports / f"{key}.md"
        if not target.exists():
            return None
        if target.is_symlink() or not target.is_file():
            raise ValueError("evaluation path is not a regular local file")
        content = target.read_text(encoding="utf-8")
        source_field = re.search(r"^\*\*Source:\*\*\s*(.+?)\s*$", content, re.MULTILINE)
        url_field = re.search(r"^\*\*Source URL:\*\*\s*(.+?)\s*$", content, re.MULTILINE)
        if not source_field:
            raise ValueError("existing evaluation has no source identity; inspect before writing")
        return source_field.group(1), url_field.group(1) if url_field else ""

    prior = report_identity(base)
    if prior is None:
        return base
    old_source, old_url = prior
    if old_source == relative:
        if url and old_url and old_url not in (url, "not provided"):
            raise ValueError("same inbox file now has a different URL; preserve the earlier evaluation")
        return base
    # Existing URL-less reports remain distinct by their local inbox files.
    # A URL-based suffix matches the key used by /scrape and /apply.
    candidate = (make_url_collision_key(company, title, url) if url else
                 f"{base}-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:8]}")
    identity = report_identity(candidate)
    if identity and (identity[0] != relative or (url and identity[1] not in (url, "", "not provided"))):
        raise ValueError("evaluation key is already occupied by another JD")
    return candidate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True, help="saved full JD under markets/china/jobs/inbox/")
    ap.add_argument("--company", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--url", default="")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        print(choose(args.root, args.source, args.company, args.title, args.url))
    except (OSError, ValueError) as exc:
        print(f"Cannot select evaluation path: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
