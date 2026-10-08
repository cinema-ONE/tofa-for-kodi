"""Poster-card marks as the app 2.0 draws them.

The rating falls back to TMDB's 0-10 score times ten when a title has no
tofa score; a show carries its episodes left (99+ past 99), a finished title
a tick, each behind its own profile switch.

Run:  python3 test_card_marks.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import cards, theme  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeItem:
    def __init__(self):
        self.props = {}

    def setProperty(self, k, v):
        self.props[k] = v


def marks(item, prefs=None):
    mli = FakeItem()
    cards.apply_watch_marks(mli, item, prefs)
    return mli.props


rt = theme.card_rating_text
check("a tofa score wins", rt({"tofa_audience_rating": 81, "vote_average": 7.2}) == "81")
check("no tofa score: TMDB times ten", rt({"vote_average": 7.2}) == "72")
check("...then IMDb times ten", rt({"imdb_rating": 6.66}) == "67")
check("nothing at all: no badge", rt({}) == "")
check("a zero is no score", rt({"vote_average": 0}) == "")
check("Off still hides it", rt({"vote_average": 7.2}, {"show_card_ratings": False}) == "")

show = {"media_type": "tv", "unwatched_episode_count": 6}
check("a show shows its episodes left", marks(show)["episodes_left"] == "6")
check("...capped at 99+", marks(dict(show, unwatched_episode_count=400))["episodes_left"] == "99+")
check("...and the wide chip for it",
      marks(dict(show, unwatched_episode_count=400))["episodes_left_wide"] == "1")
check("...unless the profile turned it off",
      marks(show, {"show_unwatched_count": False})["episodes_left"] == "")
check("a show with none left is finished",
      marks(dict(show, unwatched_episode_count=0))["finished"] == "1")
check("a watched film is finished", marks({"media_type": "movie", "watched": True})["finished"] == "1")
check("...unless watched marks are off",
      marks({"media_type": "movie", "watched": True}, {"show_watched_checkmark": False})["finished"] == "")
check("an unwatched film has neither",
      marks({"media_type": "movie", "watched": False}) == {
          "episodes_left": "", "episodes_left_wide": "", "finished": ""})
check("a title you do not have carries no marks",
      marks(dict(show, in_library=False))["episodes_left"] == "")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
