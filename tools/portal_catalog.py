#!/usr/bin/env python3
"""List portal names and enabled flags without printing their long SKILL.md bodies."""

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def catalog(root):
    result = []
    for path in sorted((root / ".agents/skills").glob("*/SKILL.md")):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("portal skill resolves outside this checkout")
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
        name = re.search(r"^name:\s*(\S+)\s*$", content, re.MULTILINE)
        toggle = re.search(r"^enabled:\s*(true|false)(?:\s*(?:#.*)?)?$", content, re.MULTILINE | re.IGNORECASE)
        if not name:
            raise ValueError(f"{path.parent.name}: missing name")
        if re.search(r"^enabled:", content, re.MULTILINE) and not toggle:
            raise ValueError(f"{path.parent.name}: invalid enabled value")
        result.append({"name": name.group(1), "path": path.relative_to(root).as_posix(),
                       "enabled": toggle is None or toggle.group(1).lower() == "true"})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(catalog(args.root), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(f"portal catalog: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
