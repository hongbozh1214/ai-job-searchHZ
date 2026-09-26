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
        def query(*command):
            result = subprocess.run(
                ["openclaw", "skills", *command, "--agent", agent, "--json"],
                cwd=root, capture_output=True, text=True, timeout=25, check=True,
            )
            return json.loads(result.stdout)

        def runtime_path(value):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("runtime path missing")
            path = Path(value).expanduser()
            if not path.is_absolute():
                raise ValueError("runtime path must be absolute")
            return path.resolve(strict=True)

        def available(skill):
            # eligible does not include the per-agent allowlist in OpenClaw.
            return (
                skill.get("eligible") is True
                and skill.get("enabled") is not False
                and not any(skill.get(flag) is True for flag in (
                    "disabled", "blockedByAllowlist", "blockedByAgentFilter",
                ))
            )

        checkout = root.resolve(strict=True)
        data = query("list")
        if not isinstance(data, dict) or not data.get("workspaceDir"):
            return report("FAIL", "OpenClaw discovery", "runtime did not report workspaceDir; cannot verify isolation")
        if runtime_path(data["workspaceDir"]) != checkout:
            return report("FAIL", "OpenClaw discovery", f"agent {agent} workspace does not match this checkout; check --agent ID and its workspace setting")
        entries = data.get("skills", [])
        if not isinstance(entries, list):
            raise ValueError("skills list returned an unexpected JSON shape")
        matches = [item for item in entries if isinstance(item, dict) and item.get("name") == "job-search"]
        if len(matches) != 1:
            return report("FAIL", "OpenClaw discovery", f"agent {agent} must list exactly one job-search skill; check its workspace")
        skill = matches[0]
        if not available(skill):
            return report("FAIL", "OpenClaw discovery", f"job-search is unavailable to agent {agent}")

        # `skills list --json` omits filePath. The detail query verifies that
        # the selected skill is this checkout's entry point, not a same-named
        # global skill or a symlink into the other candidate's checkout.
        detail = query("info", "job-search")
        if not isinstance(detail, dict) or detail.get("name") != "job-search":
            raise ValueError("unexpected skill detail")
        if not available(detail):
            return report("FAIL", "OpenClaw discovery", f"job-search is unavailable to agent {agent}")
        expected = (checkout / "skills/job-search/SKILL.md").resolve(strict=True)
        if not expected.is_relative_to(checkout) or not expected.is_file():
            return report("FAIL", "OpenClaw discovery", "local job-search entry point must be a file inside this checkout")
        if runtime_path(detail.get("filePath")) != expected:
            return report("FAIL", "OpenClaw discovery", "job-search resolves outside this checkout's entry point; check skill overrides")
        return report("OK", "OpenClaw discovery", f"agent {agent} workspace and job-search path match this checkout")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
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
