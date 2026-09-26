#!/usr/bin/env python3
"""Read-only OpenClaw workspace preflight; run separately in each checkout."""

import argparse
import importlib.util
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


def private_paths(root):
    """Reject private paths whose symlinks lead into another checkout."""
    checkout = root.resolve(strict=True)
    paths = [
        "documents/profile", "documents/cv", "documents/linkedin",
        "documents/applications", "documents/postings", "job_scraper",
        ".claude/skills/job-scraper/job_scraper", "company_research",
        "job_search_tracker.csv", "company_pages.json", "USER.md", "MEMORY.md",
        "memory", "memory.md", "gmail_sync", "reports",
    ]
    scan_paths = ["documents/profile", "documents/cv", "documents/applications",
                  "documents/postings", "documents/linkedin", "job_scraper", "company_research"]
    for market in ("china", "europe", "finland"):
        paths.extend((f"documents/{market}/profile", f"markets/{market}/jobs"))
        scan_paths.extend((f"documents/{market}/profile", f"markets/{market}/jobs"))
    failed = False
    for name in paths:
        path = root / name
        # Check each existing component: a missing leaf under an outside
        # symlink is still an isolation failure before setup creates it.
        for part in (path, *path.parents):
            if part == root.parent:
                break
            if part.is_symlink() and not part.resolve().is_relative_to(checkout):
                failed |= report("FAIL", "private path isolation", f"{name} resolves outside this checkout")
                break
    for name in scan_paths:
        directory = root / name
        if not directory.is_dir() or not directory.resolve().is_relative_to(checkout):
            continue
        for current, dirs, files in os.walk(directory, followlinks=False):
            for child in (Path(current) / entry for entry in dirs + files):
                if child.is_symlink() and not child.resolve().is_relative_to(checkout):
                    failed |= report("FAIL", "private path isolation", f"a link within {name} resolves outside this checkout")
    if not failed:
        report("OK", "private path isolation", "known profile and state paths stay in this checkout")
    return failed


def optional_dependencies():
    if importlib.util.find_spec("pypdf") or shutil.which("pdftotext"):
        report("OK", "PDF text extraction", "pypdf or pdftotext available")
    else:
        report("WARN", "PDF text extraction", "install pypdf or pdftotext for ATS text checks")
    if not shutil.which("fc-list"):
        report("WARN", "Chinese fonts", "fc-list unavailable; verify a CJK font before China LaTeX compilation")
        return
    try:
        fonts = subprocess.run(["fc-list", ":lang=zh", "family"], capture_output=True,
                               text=True, timeout=10, check=True)
        if fonts.stdout.strip():
            report("OK", "Chinese fonts", "a Chinese font is discoverable")
        else:
            report("WARN", "Chinese fonts", "install a CJK font before China LaTeX compilation")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        report("WARN", "Chinese fonts", "cannot query fontconfig; verify a CJK font manually")


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
    if configured and not path.is_absolute():
        path = root / path
    if not path.resolve().is_relative_to(root.resolve()):
        return report("FAIL", "company registry", "registry resolves outside this checkout; use a per-agent registry")
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
    failed |= private_paths(root)
    optional_dependencies()
    failed |= runtime_skill(args.agent, root)
    failed |= registry(root)
    print("Result: FAIL" if failed else "Result: OK (review WARN items above)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
