"""Search finds a custom collection by name and shows its members as a row.

The server's search returns no collections, so a set someone made on purpose
could only be reached by scrolling Browse > Collections.

Run:  python3 test_search_custom_collections.py
"""
import os

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import MainWindow, match_custom_collection

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


SETS = [{"id": "a", "name": "Kodi client test (safe to delete)"},
        {"id": "b", "name": "Panasonic A/B 2026-09-28"},
        {"id": "c", "name": "Test Videos"},
        {"id": "d", "name": "Trailers and Samples"}]


def name(query):
    hit = match_custom_collection(SETS, query)
    return hit["name"] if hit else None


def main():
    check("a word of the name finds it", name("panasonic"), "Panasonic A/B 2026-09-28")
    check("case and extra spaces don't matter", name("  PANASONIC   a/b "), "Panasonic A/B 2026-09-28")
    check("every word must be in the name", name("panasonic samples"), None)
    check("a name that starts with the query wins", name("test"), "Test Videos")
    check("one character is not a search", name("t"), None)
    check("nothing matches, nothing shown", name("zombie"), None)
    check("no collections at all", match_custom_collection([], "test"), None)

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
