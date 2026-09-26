#!/usr/bin/env python3
"""Preview or clear local candidate state in one checkout; never follow symlinks."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOCUMENT_DIRS = (
    "documents/cv", "documents/linkedin", "documents/diplomas",
    "documents/references", "documents/projects", "documents/postings",
    "documents/applications", "documents/interview",
)
PRIVATE_DIRS = (
    "gmail_sync", "reports",
    "upskill", "job_scraper", ".claude/skills/job-scraper/job_scraper",
    ".claude/skills/upskill/upskill", "company_research", "memory", ".openclaw",
)
PRIVATE_FILES = (
    "job_search_tracker.csv", "company_pages.json", "USER.md", "MEMORY.md",
    "memory.md", "SOUL.md", "IDENTITY.md", "TOOLS.md", "HEARTBEAT.md",
    "BOOT.md", "BOOTSTRAP.md", "DREAMS.md", "salary_data.json",
)
GENERATED = (
    "cv/main_*.*", "cv/chinese/main_*.*", "cv/*.txt",
    "cover_letters/cover_*.*", "cover_letters/Cover_*.*",
    "cover_letters/chinese/cover_*.*", "cover_letters/chinese/Cover_*.*",
)


def git_paths(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return {Path(os.fsdecode(item)) for item in result.stdout.split(b"\0") if item}


def inventory(root, scope="full"):
    """Only gitignored, untracked files from explicit private areas qualify."""
    tracked = git_paths(root, "ls-files", "-z")
    candidates = set()

    def collect(path):
        for ancestor in path.parents:
            if ancestor == root:
                break
            if ancestor.is_symlink():
                raise RuntimeError("a parent directory is a symlink; inspect it manually")
        if path.is_symlink() or path.is_file():
            candidates.add(path.relative_to(root))
        elif path.is_dir():
            def fail_walk(error):
                raise error
            for current, dirs, files in os.walk(path, followlinks=False, onerror=fail_walk):
                for name in files:
                    candidates.add((Path(current) / name).relative_to(root))
                for name in list(dirs):
                    child = Path(current) / name
                    if child.is_symlink():
                        dirs.remove(name)
                        candidates.add(child.relative_to(root))

    if scope in ("profile", "all", "full"):
        collect(root / "documents/profile")
    if scope in ("documents", "all", "full"):
        for name in DOCUMENT_DIRS:
            collect(root / name)
    if scope == "full":
        for name in PRIVATE_DIRS:
            collect(root / name)
        for market in ("china", "europe", "finland"):
            collect(root / "documents" / market / "profile")
            collect(root / "markets" / market / "jobs")
        for name in PRIVATE_FILES:
            collect(root / name)
        for pattern in GENERATED:
            parent = root / pattern.split("*")[0].rsplit("/", 1)[0]
            if parent.is_symlink():
                raise RuntimeError("a generated output directory is a symlink")
            for path in root.glob(pattern):
                collect(path)

    examples = {Path(name) for name in (
        "cv/main_example.tex", "cv/chinese/main_example.tex",
        "cover_letters/cover_example.tex", "cover_letters/chinese/cover_example.tex",
    )}
    candidates = {p for p in candidates if p.name != ".gitkeep" and p not in examples}
    ignored = set()
    # check-ignore exits 1 if none of the candidates are ignored; inspect
    # the exit code explicitly instead of letting an empty reset look broken.
    if candidates:
        proc = subprocess.run(["git", "check-ignore", "--no-index", "-z", "--stdin"],
                              cwd=root, input=b"\0".join(os.fsencode(str(p)) for p in sorted(candidates)) + b"\0",
                              capture_output=True, check=False)
        if proc.returncode not in (0, 1):
            raise RuntimeError("cannot check ignore rules")
        ignored = {Path(os.fsdecode(item)) for item in proc.stdout.split(b"\0") if item}
    deletable = sorted(p for p in candidates if p in ignored and p not in tracked)
    preserved = sorted(p for p in candidates if p not in deletable)
    return deletable, preserved


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", choices=("profile", "documents", "all", "full"), default="full")
    ap.add_argument("--execute", action="store_true", help="delete files listed in preview")
    ap.add_argument("--confirm", help="requires literal RESET when executing")
    ap.add_argument("--expected-digest", help="digest from the preview; prevents deleting newly created files")
    args = ap.parse_args(argv)
    if args.execute and args.confirm != "RESET":
        ap.error("--execute requires --confirm RESET after reviewing the preview")
    if args.execute and not args.expected_digest:
        ap.error("--execute requires --expected-digest from the preview")
    root = root.resolve(strict=True)
    try:
        targets, preserved = inventory(root, args.scope)
        digest = hashlib.sha256(json.dumps({"scope": args.scope, "files": [str(p) for p in targets],
                                    "preserved": [str(p) for p in preserved]}, ensure_ascii=False).encode("utf-8")).hexdigest()
        print(json.dumps({"mode": "execute" if args.execute else "preview", "scope": args.scope,
                          "digest": digest,
                          "files": [str(p) for p in targets],
                          "preserved": [str(p) for p in preserved]}, indent=2, ensure_ascii=False))
        if args.execute and args.expected_digest != digest:
            print("Reset preview changed; review the new file list and confirm again", file=sys.stderr)
            return 1
        if args.execute and preserved:
            print("Refusing partial reset: tracked or non-ignored files in private paths", file=sys.stderr)
            return 1
        if args.execute:
            for name in targets:
                path = root / name
                for ancestor in path.parents:
                    if ancestor == root:
                        break
                    if ancestor.is_symlink():
                        raise RuntimeError("a parent directory changed to a symlink; stop reset")
                if path.is_symlink() or path.is_file():
                    path.unlink()
            print(f"Deleted {len(targets)} local files/symlinks; directories and tracked templates preserved")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Reset failed ({type(exc).__name__}); inspect workspace locally", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
