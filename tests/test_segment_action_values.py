"""A stored segment action means the same thing to the PILL and to the PLAYER.

The bug this guards, found 2026-09-17 while checking what server 0.9.36
actually accepts: it accepts everything. `segment_actions.intro` took `play`,
`PLAY` and `Skip` with a 200 each and read them back verbatim, casing and
all -- there is no server-side normaliser, and `auto_play_next` is the only
one of the three playback values that validates.

That left our two readers disagreeing about the same blob. The player
lower-cased before matching, so a stored `Skip` skipped; the settings screen
compared the raw string, failed to find it, and fell back to drawing the
"Ask" pill. Same value, two answers, and the screen was the one lying about
what would happen.

Both now go through `settings_options.segment_action`, so the checks below
are really one check made twice: whatever the blob holds, the pill's index and
the player's action are derived from the same normalised value.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import settings_options  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def main() -> int:
    seg = settings_options.segment_action

    # The three real values survive untouched.
    for value in ("ask", "skip", "none"):
        check("%r is itself" % value, seg(value) == value, seg(value))

    # Casing is the server's, not ours: 0.9.36 stores what it is sent.
    for value, want in (("Skip", "skip"), ("SKIP", "skip"), ("None", "none"),
                        ("Ask", "ask"), (" skip ", "skip")):
        check("%r -> %r" % (value, want), seg(value) == want, seg(value))

    # Anything else is a behaviour we do not have. `play` is the one that
    # matters: the Apple TV app LABELS the third option "Play", so it is the
    # plausible wrong value for another client to store -- and the safe
    # reading of it is "ask", never "skip".
    for value in ("play", "PLAY", "Play", "ignore", "", "  ", "nonsense"):
        check("%r -> ask" % value, seg(value) == "ask", seg(value))

    # Absent and malformed keys read as the default rather than raising.
    for value in (None, 0, [], {}):
        check("%r -> ask" % (value,), seg(value) == "ask", seg(value))

    # An explicit default is honoured, so a caller that wants to distinguish
    # "unset" from "unrecognised" can.
    check("explicit default", seg("ignore", default="skip") == "skip")

    # The value list and the default stay in step with the option table the
    # settings screen draws, which is what keeps the two surfaces aligned.
    labels = [v for v, _l in settings_options.SEGMENT_ACTIONS]
    check("values match the option table",
          list(settings_options.SEGMENT_ACTION_VALUES) == labels, str(labels))
    check("default is one of them",
          settings_options.SEGMENT_ACTION_DEFAULT
          in settings_options.SEGMENT_ACTION_VALUES)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("segment actions: one normaliser, so the pill and the player agree "
          "(%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
