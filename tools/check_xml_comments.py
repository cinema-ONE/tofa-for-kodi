#!/usr/bin/env python3
"""Catch `--` inside an XML comment, in the SOURCE, before it costs anything.

WHY THIS EXISTS. `--` is illegal inside an XML comment, and the failure is
slow and expensive rather than loud:

  1. `skin/build.py:render_all()` raises on the illegal comment;
  2. so the rendered `resources/skins/Main/1080i/*.xml` keeps its PREVIOUS
     contents;
  3. Kodi loads that stale file and throws `Non-Existent Control <id>` for
     whatever you just added;
  4. and `tools/check_xml.py` stays GREEN throughout, because it validates
     the rendered output, which is old and perfectly legal.

The result is a hunt through Kodi restarts for a control that is missing
because a comment three files away has two hyphens in it. This checks the
SOURCE instead, where the mistake actually is.

    python3 tools/check_xml_comments.py [paths...]

With no paths it checks every skin source. Exits 2 (not 1) on a finding, so
it can be used directly as a Claude Code PostToolUse hook, where 2 means
"blocking error, tell the model".
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "plugin.video.tofa", "resources", "lib", "skin")

#: Only these produce rendered XML. A `--` in any other file is just a
#: comment, an em dash written the ASCII way, or a decrement.
#:
#: skin/static/ is here because it is a SOURCE too: build.py copies those
#: screens through the same comment check on the way out (_copy_static), so
#: a `--` in one of them stalls the render exactly as it does in a template.
#: Missed when this tool was written, and duly walked into on the first
#: static screen authored afterwards.
DEFAULT_PATHS = (
    os.path.join(SKIN, "templates"),
    os.path.join(SKIN, "static"),
    os.path.join(SKIN, "fragments.py"),
    os.path.join(SKIN, "screens.py"),
    os.path.join(SKIN, "build.py"),
)

_COMMENT = re.compile(r"<!--(.*?)-->", re.S)


def is_skin_source(path: str) -> bool:
    """Does this file end up as rendered XML?"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return False
    if path.startswith(os.path.join(SKIN, "templates") + os.sep):
        return path.endswith(".tpl")
    if path.startswith(os.path.join(SKIN, "static") + os.sep):
        return path.endswith(".xml")
    return path in (os.path.abspath(p) for p in DEFAULT_PATHS if p.endswith(".py"))


def check(path: str) -> list[str]:
    """[(human-readable finding)] for one file."""
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as exc:
        return ["{0}: cannot read ({1})".format(path, exc)]
    findings = []
    for match in _COMMENT.finditer(text):
        body = match.group(1)
        if "--" not in body:
            continue
        line = text.count("\n", 0, match.start()) + 1
        # The offending run, with a little context, so the fix is obvious
        # without opening the file.
        hit = re.search(r".{0,40}--.{0,40}", body, re.S)
        snippet = " ".join((hit.group(0) if hit else body).split())
        findings.append(
            "{0}:{1}: '--' inside an XML comment: ...{2}...".format(
                os.path.relpath(path, ROOT), line, snippet))
    return findings


def _walk(paths) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for base, _dirs, names in os.walk(p):
                out.extend(os.path.join(base, n) for n in names
                           if n.endswith(".tpl") or n.endswith(".xml"))
        elif os.path.isfile(p):
            out.append(p)
    return out


def main(argv: list[str]) -> int:
    if argv:
        # Called with paths (the hook does this): silently ignore anything
        # that is not skin source, so it can be wired to every Edit.
        targets = [p for p in argv if is_skin_source(p)]
        if not targets:
            return 0
    else:
        targets = _walk(DEFAULT_PATHS)

    findings = []
    for path in targets:
        findings.extend(check(path))

    if findings:
        print("ILLEGAL XML COMMENT -- the skin will NOT re-render:",
              file=sys.stderr)
        for f in findings:
            print("  " + f, file=sys.stderr)
        print("\nUse ';' or a comma instead. Until this is fixed, the rendered\n"
              "XML stays STALE and Kodi loads the previous version, which shows\n"
              "up as 'Non-Existent Control <id>' rather than as this mistake.",
              file=sys.stderr)
        return 2
    if not argv:
        print("checked {0} skin source file(s), no illegal XML comments"
              .format(len(targets)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
