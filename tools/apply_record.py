#!/usr/bin/env python3
"""Print the shared /apply tracker/archive rules for the China text-pack route.

The source remains .claude/commands/apply.md Step 6b. This read-only command
extracts that section so a text-only application need not load the full CV,
reviewer, LaTeX and ATS workflows into the model context.
"""

import re
import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parent.parent / ".claude/commands/apply.md"
HEADING = "### Step 6b: Record the Application"


def record_section(text):
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.strip() == HEADING]
    if len(starts) != 1:
        raise ValueError("expected exactly one shared application recording section")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines))
                if re.match(r"^#{1,3} ", lines[index])), None)
    if end is None:
        raise ValueError("application recording section has no following heading")
    section = "".join(lines[start:end]).strip()
    if "job_search_tracker.csv" not in section or "job_posting.md" not in section:
        raise ValueError("application recording rules are incomplete")
    return section


def main():
    try:
        print(record_section(SOURCE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"Cannot load application recording rules: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
