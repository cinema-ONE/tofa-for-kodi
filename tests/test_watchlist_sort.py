"""Watchlist's Sort, genre pills and Filter work on the device.

The server returns the watchlist newest-added first and ignores sort/order,
so before this the pills were drawn and did nothing.

Run:  python3 test_watchlist_sort.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def item(title, added, year, score, runtime, genres):
    return {"title": title, "added_at": added, "year": year, "tofa_audience_rating": score,
            "runtime_minutes": runtime, "genres": genres, "media_id": title}


WL = [item("The 100", "2026-09-20", 2014, 75, 42, ["Drama", "Sci-Fi & Fantasy"]),
      item("Hugo", "2026-08-01", 2011, 72, 126, ["Adventure", "Family"]),
      item("Ägypten", "2026-09-01", 1999, 60, 90, ["Documentary"]),
      item("Gemini Man", "2026-07-01", 2019, 53, 117, ["Action"])]
names = lambda xs: [x["title"] for x in xs]  # noqa: E731
score = lambda i: i.get("tofa_audience_rating") or 0  # noqa: E731

check("Date Added runs newest first", names(main.sort_watchlist(WL, "added_at", True, score))
      == ["The 100", "Ägypten", "Hugo", "Gemini Man"])
check("Title ignores The (\"The 100\" files under its digits) and folds accents",
      names(main.sort_watchlist(WL, "title", False, score)) == ["The 100", "Ägypten", "Gemini Man", "Hugo"])
check("Year, Rating and Runtime sort by their fields",
      names(main.sort_watchlist(WL, "release_date", True, score))[0] == "Gemini Man"
      and names(main.sort_watchlist(WL, "rating", True, score))[0] == "The 100"
      and names(main.sort_watchlist(WL, "runtime", False, score))[0] == "The 100")
check("Shuffle is stable for one seed",
      names(main.sort_watchlist(WL, "random", False, score, 7))
      == names(main.sort_watchlist(WL, "random", False, score, 7)))


class FakeWindow:
    """A stand-in `self` with the real watchlist methods."""

    def __init__(self):
        self._sources = [{"kind": "watchlist", "name": "Watchlist"}]
        self._active_source_idx = 0
        self._browse_collection = None
        self._browse_watchlist_items = list(WL)
        self._server_capabilities = {"media.watched_played"}
        self._browse_sort_idx = 0
        self._browse_sort_reversed = False
        self._browse_shuffle_seed = None
        self._active_genre = W.ALL_GENRES
        self._browse_watched_idx = self._browse_year_idx = self._browse_quality_idx = 0
        self._genres, self._genre_counts, self.synced = [], {}, 0

    def _browse_active_source(self):
        return self._sources[self._active_source_idx]

    def _browse_sync_chips(self):
        self.synced += 1

    def _ensure_preferences(self):
        return {}


W = main.MainWindow
for _name in ("BROWSE_SORT_OPTIONS", "BROWSE_WATCHED_OPTIONS_BASE", "BROWSE_QUALITY_OPTIONS",
              "BROWSE_YEAR_OPTIONS", "WATCHLIST_SORTS", "COLLECTION_ANSWERS", "ALL_GENRES",
              "_browse_on_watchlist", "_browse_watchlist_view", "_browse_watched_options",
              "_browse_quality_options", "_browse_collection_answerable", "_browse_offered_sorts"):
    setattr(FakeWindow, _name, W.__dict__.get(_name, getattr(W, _name)))

w = FakeWindow()
idx = lambda v: [o[1] for o in W.BROWSE_SORT_OPTIONS].index(v)  # noqa: E731
got = w._browse_watchlist_view(list(WL))
check("opens in the server's order (Date Added, newest first)", names(got)[0] == "The 100")
check("the genre pills are the watchlist's own",
      w._genres == [W.ALL_GENRES, "Action", "Adventure", "Documentary", "Drama", "Family", "Sci-Fi & Fantasy"])

w._browse_sort_idx = idx("title")
check("Title sorts it", names(w._browse_watchlist_view(list(WL))) == ["The 100", "Ägypten", "Gemini Man", "Hugo"])
w._browse_sort_reversed = True
check("...and choosing it again reverses", names(w._browse_watchlist_view(list(WL)))[0] == "Hugo")

w._browse_sort_reversed = False
w._active_genre = "Adventure"
check("a genre pill keeps only its titles", names(w._browse_watchlist_view(list(WL))) == ["Hugo"])

w._active_genre = W.ALL_GENRES
w._browse_sort_idx = idx("play_count")
w._browse_watchlist_view(list(WL))
check("a sort it cannot answer falls back to Date Added", w._browse_sort_idx == 0)
offered = [W.BROWSE_SORT_OPTIONS[i][1] for i in w._browse_offered_sorts()]
check("the Sort panel offers only what it can answer",
      "play_count" not in offered and "last_watched" not in offered and "title" in offered)
check("no watched state, so no Unwatched option",
      [v for _l, v in w._browse_watched_options()] == [None])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
