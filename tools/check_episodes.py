"""Checks the episode number/label formatting, including multi-episode files.

Server 0.9.27 added `episode_number_end`. The failure it fixes is a silent
one -- a double episode showing only its first number, so the second looks
missing -- and the natural way to reintroduce it is to trust the field
without checking that it actually describes a range.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)

#: The add-on tree, wherever it is. This tool stays in the vault when the
#: add-on moves to its own public repo, so it has to look next door.
ADDON = checkouts.addon_dir(ROOT)
if not ADDON:
    raise SystemExit("cannot find plugin.video.tofa/ -- check it out beside "
                     "this repo, or set TOFA_ADDON_REPO")

sys.path.insert(0, os.path.join(ADDON, "resources"))

from lib import episodes as ep  # noqa: E402


def main() -> int:
    fails = []
    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r wanted %r" % (name, got, want))

    # --- ordinary single episodes --------------------------------------
    check("plain number", ep.number_text(19), "19")
    check("plain label", ep.number_label(4, 19), "S4 E19")
    check("NULL end is the normal case", ep.number_label(4, 19, None), "S4 E19")
    check("episode 0 is a real episode", ep.number_label(1, 0), "S1 E0")
    check("season 0 is a real season (specials)", ep.number_label(0, 3), "S0 E3")

    # --- multi-episode files -------------------------------------------
    check("range text", ep.number_text(19, 20), "19-E20")
    check("range label", ep.number_label(4, 19, 20), "S4 E19-E20")
    check("wide range", ep.number_label(1, 1, 4), "S1 E1-E4")
    # The E is inside the range so a caller that already wrote E does not
    # produce "E19-20", which could read as a part or a duration.
    check("range carries its own E", "E" + ep.number_text(19, 20), "E19-E20")

    # --- ends that do not describe a range must be ignored --------------
    check("end == start is one episode", ep.number_label(4, 19, 19), "S4 E19")
    check("end < start is one episode", ep.number_label(4, 19, 18), "S4 E19")
    check("junk end is one episode", ep.number_label(4, 19, "x"), "S4 E19")

    # --- missing data ---------------------------------------------------
    check("no episode -> empty", ep.number_label(4, None), "")
    check("no season -> empty", ep.number_label(None, 19), "")
    check("junk episode -> empty", ep.number_text("x"), "")
    # Strings are what a JSON blob may actually carry.
    check("numeric strings work", ep.number_label("4", "19", "20"), "S4 E19-E20")

    # --- the titleless fallback ----------------------------------------
    check("title wins", ep.title_or_number({"title": "An Episode Title",
                                            "episode_number": 1}),
          "An Episode Title")
    check("titleless single", ep.title_or_number({"episode_number": 19}),
          "Episode 19")
    # The point of the whole change: a titleless double episode must not
    # advertise only its first number.
    check("titleless double", ep.title_or_number({"episode_number": 19,
                                                  "episode_number_end": 20}),
          "Episode 19-E20")
    check("no numbers at all", ep.title_or_number({}), "")

    for f in fails:
        print("FAIL " + f)
    print("%d checks, %d failed" % (21, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
