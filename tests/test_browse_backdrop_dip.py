"""The landing's backdrop changes with a dip, as the app does: the old wall
fades out ("dip" shows nothing, not even the tile's art), then the new one is
written and fades in. A newer change cancels a pending one.

Run:  python3 test_browse_backdrop_dip.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.skin import tokens as T  # noqa: E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Timer:
    """Held, not run: the test fires it, as the 100 ms would."""
    pending: list = []

    def __init__(self, delay, fn):
        self.delay, self.fn, self.daemon = delay, fn, False

    def start(self):
        Timer.pending.append(self)


main.threading.Timer = Timer


class FakeWindow:
    def __init__(self):
        self.props = {}
        self.writes = []
        self._browse_wall_target = None
        self._browse_wall_gen = 0

    def setProperty(self, k, v):
        self.props[k] = v

    def getProperty(self, k):
        return self.props.get(k, "")


FakeWindow._browse_show_wall = main.MainWindow._browse_show_wall
w = FakeWindow()
log = lambda tag: (lambda: w.writes.append(tag))  # noqa: E731


def fire():
    for t in Timer.pending:
        t.fn()
    Timer.pending.clear()


w._browse_show_wall("tilt", ("a",), log("movies"))
check("the first wall shows at once", w.props["browse_wall"] == "tilt" and w.writes == ["movies"])

w._browse_show_wall("tilt", ("a",), log("movies again"))
check("the same wall again does nothing", w.writes == ["movies"] and not Timer.pending)

w._browse_show_wall("row", ("b",), log("watchlist"))
check("a new wall first dips to nothing", w.props["browse_wall"] == "dip" and w.writes == ["movies"])
check("...for the fade-out's time", Timer.pending and Timer.pending[0].delay == T.BROWSE_WALL_OUT_MS / 1000)
fire()
check("...then writes the new one and shows it", w.props["browse_wall"] == "row" and w.writes[-1] == "watchlist")

w._browse_show_wall("tilt", ("c",), log("tv"))
w._browse_show_wall("feature", "Gladiator", log("collections"))
fire()
check("a quick second move cancels the first", w.props["browse_wall"] == "feature"
      and w.writes[-1] == "collections" and "tv" not in w.writes, str(w.writes))

w._browse_show_wall("", None, None)
check("no wall clears at once, nothing pending", w.props["browse_wall"] == "" and not Timer.pending)
w._browse_show_wall("tilt", ("a",), log("movies"))
check("from nothing a wall shows at once (it only fades in)", w.props["browse_wall"] == "tilt"
      and not Timer.pending)

check("left rows are slower than right rows, as the app's",
      T.BROWSE_WALL_PERIOD_LEFT_MS > T.BROWSE_WALL_PERIOD_RIGHT_MS)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
