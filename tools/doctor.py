#!/usr/bin/env python3
"""Read-only OpenClaw workspace preflight; run separately in each checkout."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def report(level, subject, detail):
    print(f"{level:4} {subject}: {detail}")
    return level == "FAIL"


def executable(name):
    path = shutil.which(name)
    if path:
        return report("OK", name, path)
    return report("FAIL", name, f"missing from PATH; install {name} in this agent's container")


def local_skills(root):
    failed = False
    for skill in [root / "skills/job-search/SKILL.md", *sorted((root / ".agents/skills").glob("*/SKILL.md"))]:
        if not skill.is_file():
            failed |= report("FAIL", "local skill", f"missing {skill.relative_to(root)}")
        else:
            report("OK", "local skill", str(skill.relative_to(root)))
    if not (root / ".agents/skills").is_dir():
        failed |= report("FAIL", "portal skills", "missing .agents/skills")
    return failed


def runtime_skill(agent, root):
    if not agent:
        report("WARN", "OpenClaw discovery", "pass --agent ID to check the configured agent workspace")
        return False
    if not shutil.which("openclaw"):
        return report("FAIL", "OpenClaw discovery", "openclaw not on PATH")
    try:
        result = subprocess.run(
            ["openclaw", "skills", "list", "--agent", agent, "--json"],
            cwd=root, capture_output=True, text=True, timeout=25, check=True,
        )
        data = json.loads(result.stdout)
        entries = data if isinstance(data, list) else data.get("skills", [])
        if not isinstance(entries, list):
            raise ValueError("skills list returned an unexpected JSON shape")
        matches = [item for item in entries if isinstance(item, dict) and item.get("name") == "job-search"]
        if not matches:
            return report("FAIL", "OpenClaw discovery", f"agent {agent} does not list job-search; check its workspace")
        skill = matches[0]
        if skill.get("eligible") is False or skill.get("enabled") is False:
            return report("FAIL", "OpenClaw discovery", f"job-search is unavailable to agent {agent}")
        return report("OK", "OpenClaw discovery", f"agent {agent} lists job-search")
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Don't print command output: OpenClaw may include personal workspace paths.
        return report("FAIL", "OpenClaw discovery", f"unable to query agent {agent} ({type(exc).__name__})")


def registry(root):
    configured = os.environ.get("COMPANY_PAGES_REGISTRY")
    path = Path(configured).expanduser() if configured else root / "company_pages.json"
    if not path.is_file():
        report("WARN", "company registry", "absent; create a personal company_pages.json to use company-pages-search")
        return False
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("expected a JSON array")
        if not entries:
            report("WARN", "company registry", "empty; company-pages-search has no employers to query")
            return False
        for entry in entries:
            if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key].strip() for key in ("name", "careers_url", "ats")):
                raise ValueError("each entry needs name, careers_url and ats strings")
            if entry["ats"] not in ("greenhouse", "lever", "smartrecruiters", "oracle", "generic"):
                raise ValueError("unsupported ats value")
            if "example.com" in entry["careers_url"] or entry["name"].startswith("Example "):
                raise ValueError("example employer still present")
        report("OK", "company registry", f"{len(entries)} employer(s) in personal registry")
        return False
    except (OSError, UnicodeError, ValueError) as exc:
        return report("FAIL", "company registry", f"invalid personal registry ({exc}); no employer details printed")


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", help="OpenClaw agent ID for runtime skill discovery")
    args = parser.parse_args(argv)
    print("Read-only workspace check (run once per checkout/agent)")
    failed = False
    failed |= executable("python3")
    failed |= executable("bun")
    failed |= executable("lualatex")
    failed |= executable("xelatex")
    failed |= local_skills(root)
    failed |= runtime_skill(args.agent, root)
    failed |= registry(root)
    print("Result: FAIL" if failed else "Result: OK (review WARN items above)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
