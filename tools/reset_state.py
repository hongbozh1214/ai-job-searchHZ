#!/usr/bin/env python3
"""Preview or clear local candidate state in one checkout; never follow symlinks."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DIRS = (
    "documents/profile", "documents/cv", "documents/linkedin", "documents/diplomas",
    "documents/references", "documents/projects", "documents/postings",
    "documents/applications", "documents/interview", "gmail_sync", "reports",
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


def inventory(root):
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
            for current, dirs, files in os.walk(path, followlinks=False):
                for name in files:
                    candidates.add((Path(current) / name).relative_to(root))
                for name in list(dirs):
                    child = Path(current) / name
                    if child.is_symlink():
                        dirs.remove(name)
                        candidates.add(child.relative_to(root))

    for name in PRIVATE_DIRS:
        collect(root / name)
    for market in ("china", "europe", "finland"):
        collect(root / "documents" / market / "profile")
        for stage in ("inbox", "evaluated", "archived"):
            collect(root / "markets" / market / "jobs" / stage)
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
    deletable = sorted(p for p in candidates if p in ignored and p not in tracked and p.name != ".gitkeep")
    preserved = sorted(p for p in candidates if p not in deletable)
    return deletable, preserved


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="delete files listed in preview")
    ap.add_argument("--confirm", help="requires literal RESET when executing")
    args = ap.parse_args(argv)
    if args.execute and args.confirm != "RESET":
        ap.error("--execute requires --confirm RESET after reviewing the preview")
    root = root.resolve(strict=True)
    try:
        targets, preserved = inventory(root)
        print(json.dumps({"mode": "execute" if args.execute else "preview",
                          "files": [str(p) for p in targets],
                          "preserved": [str(p) for p in preserved]}, indent=2, ensure_ascii=False))
        if args.execute and preserved:
            print("Refusing partial reset: tracked or non-ignored files in private paths", file=sys.stderr)
            return 1
        if args.execute:
            for name in targets:
                path = root / name
                if path.is_symlink() or path.is_file():
                    path.unlink()
            print(f"Deleted {len(targets)} local files/symlinks; directories and tracked templates preserved")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Reset failed ({type(exc).__name__}); inspect workspace locally", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
