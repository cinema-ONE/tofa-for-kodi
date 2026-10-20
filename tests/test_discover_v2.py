"""Discover as the Apple TV app 2.1.0 draws it, from the server's layout-2 page.

Run:  python3 test_discover_v2.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import discover, home_rows

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


check("the app's six tabs, Universes before Genres",
      [label for _k, label in home_rows.DISCOVER_TABS]
      == ["For You", "Trending", "Coming Up", "Best Of", "Universes", "Genres"])
page = {
    "groups": [{"key": "for-you"}, {"key": "trending"}],
    "shelves": [
        {"key": "a", "group": "for-you", "items": [{}]},
        {"key": "b", "group": "trending", "ranked": True, "items": [{}]},
        {"key": "c", "group": "best-of", "form": "tiles", "tiles": [{"key": "x"}]},
        {"key": "d", "group": "trending", "items": []},
        {"key": "e", "group": "something-new", "items": [{}]},
    ],
    "lanes": [{"slug": "horror", "title": "Horror", "artwork": "h.jpg"}, {"title": "no slug"}],
}
grouped = discover.group_shelves(page, home_rows.DISCOVER_TABS)
check("shelves land in their group's tab, in the server's order",
      [s["key"] for s in grouped["for-you"]] == ["a", "e"] and [s["key"] for s in grouped["trending"]] == ["b"])
check("an empty shelf is dropped, a tiles shelf kept", [s["key"] for s in grouped["best-of"]] == ["c"])
check("an unknown group falls into For You, never vanishes", grouped["for-you"][-1]["key"] == "e")
check("ranked and tiles are the server's flags",
      discover.is_ranked(grouped["trending"][0]) and discover.is_tiles(grouped["best-of"][0])
      and not discover.is_ranked(grouped["for-you"][0]))
check("the Genres wall: one tile per lane with a slug",
      discover.lane_tiles(page) == [{"key": "horror", "title": "Horror", "artwork": "h.jpg",
                                     "target": "lane"}])

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
