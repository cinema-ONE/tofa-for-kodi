"""Search shows the server's best-matching collection as a row of its titles.

The server returns custom, franchise and curated collections (vault #242).
A custom set holds library titles; a franchise or curated one lists TMDB
titles, and only those in the library make the row.

Run:  python3 test_search_collections.py
"""
import os

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import (MainWindow, search_collection_members,
                                        search_collection_title)

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


TMDB = [{"tmdb_id": 646, "title": "Dr. No", "type": "movie", "year": 1962,
         "in_library": True, "local_media_id": "m1"},
        {"tmdb_id": 657, "title": "From Russia with Love", "type": "movie",
         "in_library": False, "local_media_id": None},
        {"tmdb_id": 1399, "title": "The Mandalorian", "type": "tv",
         "in_library": True, "local_media_id": "s1"}]


class FakeClient:
    def __init__(self):
        self.asked = []

    def custom_collection(self, cid):
        self.asked.append(("custom", cid))
        return {"items": [{"id": "x1", "title": "Clip", "release_date": "2024-05-01"}]}

    def collection(self, cid):
        self.asked.append(("collection", cid))
        return {"items": TMDB}


class FakeWindow:
    _search_collection = MainWindow._search_collection


def main():
    custom = search_collection_members("custom", [{"id": "x1", "release_date": "2024-05-01"}])
    check("a custom set keeps its members, with the year the caption reads",
          [(m["id"], m["year"]) for m in custom], [("x1", 2024)])
    franchise = search_collection_members("franchise", TMDB)
    check("a franchise keeps only what the library holds, by library id",
          [(m["id"], m["media_type"]) for m in franchise], [("m1", "movie"), ("s1", "tv")])
    check("...and a curated set the same", search_collection_members("curated", TMDB), franchise)

    w, c = FakeWindow(), FakeClient()
    hit = {"id": "ad34", "kind": "custom", "name": "Panasonic A/B"}
    check("a custom collection is read from the custom route",
          (w._search_collection(c, hit)[0]["name"], c.asked), ("Panasonic A/B", [("custom", "ad34")]))
    c = FakeClient()
    w._search_collection(c, {"id": "star-wars", "kind": "curated", "name": "Star Wars Universe"})
    check("franchise and curated ones from the shared route", c.asked, [("collection", "star-wars")])
    check("no collection, no row", w._search_collection(FakeClient(), {}), ({}, []))
    check("the header names the collection once",
          (search_collection_title("James Bond Collection"), search_collection_title("Panasonic A/B")),
          ("James Bond Collection", "Collection: Panasonic A/B"))

    check("the row sits between Top Result and Movies",
          MainWindow.SEARCH_RESULT_LIST_IDS[:3],
          (MainWindow.TOP_RESULT_LIST_ID, MainWindow.SEARCH_COLLECTION_LIST_ID,
           MainWindow.MOVIES_LIST_ID))
    tpl = open(os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa",
                            "resources", "lib", "skin", "templates", "main.xml.tpl")).read()
    block = tpl.split('<control type="list" id="6870">')[1].split("</control>")[0]
    check("its Up goes to Top Result and Down to Movies",
          ("<onup>6805</onup>" in block, "<ondown>6820</ondown>" in block), (True, True))
    top = tpl.split('<control type="list" id="6805">')[1].split("</control>")[0]
    movies = tpl.split('<control type="list" id="6820">')[1].split("</control>")[0]
    check("...and both neighbours point back at it",
          ("<ondown>6870</ondown>" in top, "<onup>6870</onup>" in movies), (True, True))

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
