"""Catches numbers that reach the screen without going through regional.py.

The failure this guards is silent in the worst way: a hardcoded "," or "." or
"%H:%M" looks perfect on the machine it was written on and wrong on every box
in another region. Nothing errors, nothing logs, and a screenshot from the
author's own Kodi confirms it.

WHAT IS AND IS NOT A PROBLEM. The trap in this area is over-application, not
under-application: a year must never be grouped (2,026), nor a resolution
(1,920x1,080), nor an episode number. So this does NOT flag every integer. It
flags the three things that are regional and are easy to hardcode:

  1. `strftime` with a hand-written date or clock format. Kodi has the user's
     answer (`xbmc.getRegion`); a literal "%H:%M" or "%b %d" overrides it.
  2. `%-d` / `%-m` inside such a format: glibc extensions Android's bionic
     libc does not have, so broken on one of our three target boxes and fine
     on the other two. Reported as part of the strftime finding rather than
     by scanning lines -- a line scan cannot tell a format string from a
     COMMENT that names the flag to explain why it is avoided, and flagging
     the documentation teaches people to stop writing it.
  3. A literal "." or "," used as a decimal mark in an f-string that formats a
     float for display (`f"{x:.1f}"`), where the mark is regional.

It cannot be airtight -- deciding whether an integer is a count or a year
needs intent, not syntax. It turns the cheap, mechanical mistakes into a
failed check and leaves the judgement calls to review, which is the same bar
tools/check_xml.py sets.

    python3 tools/check_numbers.py
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)

#: The add-on tree, wherever it is. This tool stays in the vault when the
#: add-on moves to its own public repo, so it has to look next door.
ADDON = checkouts.addon_dir(ROOT)
if not ADDON:
    raise SystemExit("cannot find plugin.video.tofa/ -- check it out beside "
                     "this repo, or set TOFA_ADDON_REPO")

LIB = os.path.join(ADDON, "resources", "lib")

#: regional.py is the one place allowed to do any of this -- it IS the
#: implementation. tracks.py's remaining bare formats are integers below the
#: grouping threshold, argued at each site.
EXEMPT = {"regional.py"}

_GLIBC_FLAG = re.compile(r"%-[dmHIMSj]")
_FLOAT_FMT = re.compile(r"\{[^{}]*:[^{}]*\.\d+f\}")


def _rel(path: str) -> str:
    return os.path.relpath(path, ROOT)


def check(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    problems: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ["does not parse: %s" % exc]

    for node in ast.walk(tree):
        # strftime("...") with a literal format
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "strftime" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            fmt = node.args[0].value
            extra = ("; it also uses %s, a glibc extension Android's bionic "
                     "libc lacks" % _GLIBC_FLAG.search(fmt).group(0)
                     ) if _GLIBC_FLAG.search(fmt) else ""
            problems.append(
                "line %d: strftime(%r) hardcodes a format Kodi's region owns%s; "
                "use regional.date/day_and_month/clock"
                % (node.lineno, fmt, extra))

        # f-string pieces that format a float to fixed decimals
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if not isinstance(value, ast.FormattedValue) or value.format_spec is None:
                    continue
                spec = "".join(
                    part.value for part in value.format_spec.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str))
                if re.fullmatch(r"\.\d+f", spec) and not spec.endswith(".0f"):
                    problems.append(
                        "line %d: f-string formats a float as %r; the decimal "
                        "mark is regional, use regional.decimal()"
                        % (node.lineno, spec))

    return problems


def main() -> int:
    failed = 0
    checked = 0
    for base, dirs, files in os.walk(LIB):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py") or name in EXEMPT:
                continue
            path = os.path.join(base, name)
            checked += 1
            problems = check(path)
            if problems:
                failed += 1
                print(_rel(path))
                for problem in problems:
                    print("    " + problem)
    print("checked %d modules, %d with problems" % (checked, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
