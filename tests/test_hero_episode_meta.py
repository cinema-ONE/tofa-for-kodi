"""The hero meta line leads with the EPISODE title, and composes idempotently.

The episode's own title had no home on the detail screen: the hero shows the
SERIES title, the eyebrow repeats it uppercased, and the Play pill carries
only "Resume S5 E5" -- the number was on screen, the name was not. It now
leads the meta line, before the year.

The trap this pins: _apply_episode_meta_line runs AGAIN every time the
next-up episode moves (that is what makes the hero follow the next episode).
Prepending to the live property would stack a second title on each refresh,
so it composes from the parts instead. A test, because the failure only
shows up on the second call and looks like a data problem, not a code one.

The year and runtime in that line now follow the EPISODE as well; that is
pinned separately in test_detail_episode_meta.py.

Run:  python3 test_hero_episode_meta.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import detail as D  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Fake:
    """Only what _apply_episode_meta_line touches.

    The line is now recomposed from the show's own fields rather than from
    the stored base string, because the episode's year and runtime replace
    the show's when it has them (test_detail_episode_meta.py covers that).
    These cases are about COMPOSITION, so they leave the episode's own
    values unset and the show's stand in -- which is the same line as
    before."""
    def __init__(self, base, title, media=None):
        self._hero_meta_base = base
        self._next_up_title = title
        self._next_up_year = ""
        self._next_up_runtime = 0
        self.media = media or {}
        self.props = {"hero_meta_line": base}
    def setProperty(self, k, v): self.props[k] = v
    def getProperty(self, k): return self.props.get(k, "")


APPLY = D.DetailWindow._apply_episode_meta_line
BASE = "2020 • TV-MA • 47 min • Drama"
SHOW = {"release_date": "2020-11-06", "content_rating": "TV-MA",
        "runtime_minutes": 47, "genres": ["Drama"]}

w = Fake(BASE, "The Scytale", SHOW)
APPLY(w)
check("episode title leads the line",
      w.props["hero_meta_line"] == "The Scytale • " + BASE,
      w.props["hero_meta_line"])

once = w.props["hero_meta_line"]
APPLY(w); APPLY(w)
check("composing again is idempotent", w.props["hero_meta_line"] == once,
      "a refresh stacked another copy: " + w.props["hero_meta_line"])

w2 = Fake(BASE, "", SHOW)
APPLY(w2)
check("a film is untouched", w2.props["hero_meta_line"] == BASE)

w3 = Fake("", "The Scytale")
APPLY(w3)
check("an episode with no show meta still shows its title",
      w3.props["hero_meta_line"] == "The Scytale", w3.props["hero_meta_line"])

w4 = Fake("", "")
APPLY(w4)
check("nothing to say writes nothing odd", w4.props["hero_meta_line"] == "")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
