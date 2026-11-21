#!/usr/bin/env python3
"""List portal names and enabled flags without printing their long SKILL.md bodies."""

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def discovery_root(requested, project_root=ROOT):
    """Accept an explicit discovery boundary, never search ancestor directories.

    Project data stays rooted at project_root. Only the documented ai-job-search
    child layout may use its immediate workspace parent for skill discovery.
    """
    project = project_root.resolve(strict=True)
    root = (requested if requested is not None else project).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("discovery root is not a directory")
    if root != project and not (project.name == "ai-job-search" and root == project.parent):
        raise ValueError("discovery root must be this project or its direct ai-job-search workspace parent")
    return root


def inside(path, root):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("portal skill resolves outside this checkout (discovery root)")
    return resolved


def catalog(root):
    """Read skills under an already selected boundary; path is relative to root."""
    root = root.resolve(strict=True)
    skills = root / ".agents/skills"
    # Validate the directory before globbing: missing/broken/outside directories
    # must not silently look like a successful catalog with no installed portals.
    try:
        inside(skills, root)
    except FileNotFoundError as exc:
        raise ValueError(f"missing .agents/skills directory under discovery root: {root}") from exc
    if not skills.is_dir():
        raise ValueError(".agents/skills is not a directory")
    result = []
    for folder in sorted(skills.iterdir()):
        inside(folder, root)
        if not folder.is_dir():
            continue
        path = folder / "SKILL.md"
        if not path.exists() and not path.is_symlink():
            continue
        inside(path, root)
        # Stop at the closing frontmatter delimiter; long CLI usage/examples
        # never enter the command's output or the model's context.
        with path.open(encoding="utf-8") as fh:
            if fh.readline().strip() != "---":
                raise ValueError(f"{path.name}: missing skill frontmatter")
            header = []
            for line in fh:
                if line.strip() == "---":
                    break
                header.append(line)
            else:
                raise ValueError(f"{path.name}: unclosed skill frontmatter")
        content = "".join(header)
        # Horizontal whitespace only: a missing value must not consume the next
        # line. Ambiguous/malformed toggles fail closed instead of enabling one.
        name = re.search(r"^name:[ \t]*(\S+)[ \t]*$", content, re.MULTILINE)
        toggle = re.search(r"^enabled:[ \t]*(true|false)[ \t]*(?:#.*)?$", content, re.MULTILINE | re.IGNORECASE)
        fields = re.findall(r"^[ \t]*(name|enabled)[ \t]*:", content, re.MULTILINE)
        if fields.count("name") > 1 or fields.count("enabled") > 1:
            raise ValueError(f"{folder.name}: duplicate name or enabled field")
        if not name:
            raise ValueError(f"{path.parent.name}: missing name")
        if "enabled" in fields and not toggle:
            raise ValueError(f"{path.parent.name}: invalid enabled value")
        result.append({"name": name.group(1), "path": path.relative_to(root).as_posix(),
                       "enabled": toggle is None or toggle.group(1).lower() == "true"})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help=(
        "skill discovery root, relative to cwd (default: this project); the only "
        "alternative is its direct workspace parent when the project is named "
        "ai-job-search. Output paths are relative to this root. This never changes "
        "the project data root or any portal CLI's registry configuration."
    ))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(catalog(discovery_root(args.root)), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"portal catalog: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
