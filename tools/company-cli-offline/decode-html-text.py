"""Acceptance text only: decode HTML references once, preserve punctuation.
No files, network or subprocesses. Input is text already extracted from HTML.
"""
import html
import json
import re
import sys

text = sys.stdin.read(2 * 1024 * 1024 + 1)
if len(text) > 2 * 1024 * 1024:
    raise SystemExit("acceptance text budget exceeded")
sys.stdout.write(json.dumps(re.sub(r"\s+", " ", html.unescape(text)).strip()))
