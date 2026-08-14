"""The server picker's id line: it has to FIT, and both ends have to survive.

Two ways this goes wrong, one of which already did. Too many characters and
Kodi truncates what is already truncated, so the card reads
"...e22-8e364313..." -- an ellipsis this code put in, followed by one Kodi
added. Too few and the shortening eats the part that distinguishes two
servers created a minute apart.

The budget is a MEASURED number (see ID_MAX_CHARS): 31 cells of a 16px
Roboto Mono in a 321-unit line. This guards the arithmetic around it.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows.serverpicker import ID_MAX_CHARS, middle_ellipsis  # noqa: E402

#: Two server ids of the shape a real one takes -- 36-character uuids, which
#: is the length the widths below are actually measured at.
HOME = "7d2a19c4-5e83-4b17-9f60-2c1ab84de905"
TESTBOX = "3b81f5a0-9c47-4d62-8e15-6fa0937bc214"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def main() -> int:
    short = middle_ellipsis(HOME)
    check("a uuid is shortened to the budget", len(short) == ID_MAX_CHARS,
          "got %d: %r" % (len(short), short))
    check("it is cut from the MIDDLE, not the end", short.endswith(HOME[-8:]),
          "got %r" % short)
    check("the head survives too", short.startswith(HOME[:8]),
          "got %r" % short)
    check("exactly one ellipsis", short.count("…") == 1, "got %r" % short)
    check("and no ASCII dots, which is what Kodi's own truncation looks like",
          "..." not in short, "got %r" % short)

    # The whole point: two servers made in the same minute share a prefix,
    # and a tail-truncated id would render them identical.
    check("two ids that differ only in the middle stay distinguishable",
          middle_ellipsis("aaaaaaaa-1111-4000-8000-bbbbbbbbbbbb")
          != middle_ellipsis("aaaaaaaa-2222-4000-8000-bbbbbbbbbbbb"))

    # Anything that already fits is left exactly alone -- a server id is not
    # required to be a uuid, and a short one must not grow an ellipsis.
    for text in ("", "medianas", "a" * ID_MAX_CHARS):
        check("%r is left alone" % text, middle_ellipsis(text) == text)
    check("one over the budget IS shortened",
          len(middle_ellipsis("a" * (ID_MAX_CHARS + 1))) == ID_MAX_CHARS)

    # Both ids at full uuid length, at the width they are actually drawn at.
    for name, sid in (("MEDIA-NAS", HOME), ("tofa-testserver", TESTBOX)):
        check("%s fits" % name, len(middle_ellipsis(sid)) <= ID_MAX_CHARS)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("server picker: the id line fits and keeps both ends (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
