#!/usr/bin/env python3
"""Keep commit messages and new comments short.

Limits (CONTRIBUTING.md, "Keep it short"):
  subject       <= 65 chars (a squash adds " (#123)"; GitHub cuts at ~70)
  body          <= 8 lines of text, blank lines and trailers not counted
  new comment   <= 4 consecutive lines (# in .py, <!-- --> in .py/.tpl/.xml)

    python3 tools/check_brevity.py                    # the last commit
    python3 tools/check_brevity.py --range "A..B"     # what pre-push passes
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBJECT_MAX, BODY_MAX, COMMENT_MAX = 65, 8, 4
TRAILER = re.compile(r"^[A-Za-z-]+: .+")
CHECKED = (".py", ".tpl", ".xml")
GENERATED = "plugin.video.tofa/resources/skins/Main/1080i/"


def git(*args: str) -> str:
    return subprocess.run(("git",) + args, cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def message_problems(sha: str, message: str) -> list[str]:
    lines = message.strip().splitlines() or [""]
    subject, body = lines[0], lines[1:]
    while body and (not body[-1].strip() or TRAILER.match(body[-1])):
        body.pop()                       # trailers sit at the end
    text = [l for l in body if l.strip()]
    out = []
    if len(subject) > SUBJECT_MAX:
        out.append(f"{sha[:9]}: subject is {len(subject)} chars (max {SUBJECT_MAX})")
    if len(text) > BODY_MAX:
        out.append(f"{sha[:9]}: body is {len(text)} lines (max {BODY_MAX})")
    return out


def comment_problems(sha: str, diff: str) -> list[str]:
    out, path, line, run, start, in_xml = [], "", 0, 0, 0, False

    def close():
        nonlocal run
        if run > COMMENT_MAX:
            out.append(f"{sha[:9]}: {path}:{start} adds a {run}-line comment "
                       f"(max {COMMENT_MAX})")
        run = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            close()
            path = raw[6:] if raw.startswith("+++ b/") else ""
            continue
        m = re.match(r"@@ -\S+ \+(\d+)", raw)
        if m:
            close()
            line, in_xml = int(m.group(1)), False
            continue
        if not raw.startswith("+") or not path.endswith(CHECKED) \
                or path.startswith(GENERATED):
            continue
        text = raw[1:].strip()
        opens = text.startswith("<!--")      # not a "<!--" inside code
        is_comment = in_xml or opens or (
            path.endswith(".py") and text.startswith("#")
            and not text.startswith(("#!", "# -*-")))
        if opens:
            in_xml = "-->" not in text
        elif in_xml and "-->" in text:
            in_xml = False
        if is_comment:
            start = start if run else line
            run += 1
        else:
            close()
        line += 1
    close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--range", dest="revs", default="-1 HEAD",
                    help="rev-list arguments, as one string")
    revs = ap.parse_args().revs.split()
    problems = []
    for sha in git("rev-list", "--no-merges", *revs).split():
        problems += message_problems(sha, git("log", "-1", "--format=%B", sha))
        problems += comment_problems(sha, git("show", "--format=", "-U0", sha))
    for p in problems:
        print(p)
    print(f"BREVITY: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
