""""NN MIN LEFT" means what is left, so an untouched title must not carry one.

Continue Watching is not only the things you are part-way through. The server
promotes the NEXT episode onto the row as soon as you finish one, so an
untouched S1 E2 sits there at position 0 -- and the old rule labelled it
"44 MIN LEFT", which is not what is left, it is the whole episode.

The card already knew, which is what makes this a visible inconsistency
rather than a debatable one: `fill_step` returns 0 at position 0, so those
cards drew NO progress bar while still claiming time remaining. Seen on
Home's first screenful 2026-08-23 -- The Walking Dead: Dead City S1 E2 and
Lioness S1 E2, both bar-less, both captioned.

So these checks pin the two halves TOGETHER: for every input, a caption
appears if and only if a bar does. That is the property that was broken, and
testing them apart would let them drift again.

Run:  python3 test_min_left_when_started.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import progress  # noqa: E402

HOUR = 3600000
EPISODE = 2640000          # 44 minutes, the Lioness case

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


label = progress.minutes_left_label

# -- the reported case ---------------------------------------------------

check("an untouched promoted episode says nothing",
      label(0, EPISODE) == "", repr(label(0, EPISODE)))
check("...and neither does one with no position at all",
      label(None, EPISODE) == "", repr(label(None, EPISODE)))

# -- what must keep working ----------------------------------------------

check("ten minutes into a 44-minute episode",
      label(600000, EPISODE) == "34 MIN LEFT", repr(label(600000, EPISODE)))
check("a part-watched film rounds UP, never down",
      label(HOUR, HOUR + 1) == "1 MIN LEFT", repr(label(HOUR, HOUR + 1)))
check("a finished title says nothing",
      label(EPISODE, EPISODE) == "", repr(label(EPISODE, EPISODE)))
check("...and so does one watched past its own duration",
      label(EPISODE + HOUR, EPISODE) == "")
check("junk is not a caption", label("soon", EPISODE) == "")
check("no duration is not a caption", label(600000, 0) == "")

# -- NO BAR MUST MEAN NO CAPTION -----------------------------------------
#
# The invariant, in the direction that was actually broken: a card drawing
# no progress bar is a card claiming no progress, and it must not then put a
# number on how much of that progress is left.
#
# The converse is NOT an invariant, and asserting it is what this block got
# wrong first: a FINISHED title has a full bar and deliberately no caption,
# because "0 MIN LEFT" is not worth saying. So finished is listed here as
# the one case where a bar stands alone, on purpose.

CASES = [
    (0, EPISODE, "not started"),
    (None, EPISODE, "no position"),
    (1, EPISODE, "one millisecond in"),
    (600000, EPISODE, "part-way"),
    (EPISODE - 1, EPISODE, "nearly done"),
    (600000, 0, "no duration"),
    (600000, None, "duration missing"),
]
for position, duration, why in CASES:
    caption = label(position, duration)
    bar = progress.fill_step(position, duration)
    check("no bar means no caption: %s" % why, bool(bar) or not caption,
          "caption=%r bar=%r" % (caption, bar))

check("a finished title is the one bar without a caption, and that is right",
      progress.fill_step(EPISODE, EPISODE) == 100 and label(EPISODE, EPISODE) == "")

failed = [n for n, ok in RESULTS if not ok]
print("\nMIN LEFT only once started (%d checks)" % len(RESULTS))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
