"""Home rows read the way every tofa app reads them, and are named the way
the server names them.

Two discrepancies Adrian saw side by side on 2026-09-03 (web app, macOS app,
this add-on, all on the same profile):

  1. The apps showed TWELVE rows where we showed ten. The profile stores ten;
     the apps run the list through a normaliser that appends every default
     row the profile lacks (its `$n`: the eight builtins, then the two
     trending discovery rows), and save that list back on the first edit.
  2. The editor here called a row "New Noteworthy Tv" that the picker, Home
     and every app call "New Series Worth Starting", and "Trending TV Shows"
     where the apps say "Trending Shows". The server's shelf title wins
     everywhere in the apps; here it won only in the picker.

Plus the 0.9.35 `leaving_soon` builtin, which we dropped in silence.

Run:  python3 test_home_rows_parity.py
"""
from __future__ import annotations
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "plugin.video.tofa" / "resources" / "lib"))
import home_rows                                            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


LOC = {31000: "Continue Watching", 31081: "Trending TV Shows",
       31123: "Leaving soon", 31112: "Recently Released Movies"}
_ = LOC.__getitem__

# --- the normaliser --------------------------------------------------------
CLAUDE_CODE = {  # the real profile, 2026-09-03: ten rows, no recently_released_*
    "show_hero": True,
    "rows": [
        {"enabled": True, "id": "continue_watching", "type": "builtin"},
        {"enabled": True, "id": "recent_movies", "type": "builtin"},
        {"enabled": True, "id": "recent_tv", "type": "builtin"},
        {"enabled": True, "id": "top_rated_tv", "type": "builtin"},
        {"enabled": True, "id": "top_rated_movies", "type": "builtin"},
        {"enabled": True, "id": "suggested", "type": "builtin"},
        {"discoveryList": "trending-movies", "enabled": True,
         "id": "discover-trending-movies", "type": "discovery"},
        {"discoveryList": "trending-tv", "enabled": True,
         "id": "discover-trending-tv", "type": "discovery"},
        {"discoveryList": "trending-anime", "enabled": True,
         "id": "discover-trending-anime", "type": "discovery"},
        {"discoveryList": "new-noteworthy-tv", "enabled": True,
         "id": "discover-new-noteworthy-tv", "type": "discovery"},
    ],
}
norm = home_rows.normalize_home_screen(CLAUDE_CODE)
ids = [r["id"] for r in norm["rows"]]
check("the profile's ten rows keep their order",
      ids[:10] == [r["id"] for r in CLAUDE_CODE["rows"]], str(ids))
check("...and the two defaults it lacks are appended, at the END, in the apps' order",
      ids[10:] == ["recently_released_movies", "recently_released_tv"], str(ids[10:]))
check("appended rows are enabled builtins",
      all(r == {"id": i, "type": "builtin", "enabled": True}
          for r, i in zip(norm["rows"][10:], ids[10:])))
check("the input is not mutated", len(CLAUDE_CODE["rows"]) == 10)

empty = home_rows.normalize_home_screen(None)
check("no preference at all -> the ten defaults, hero on",
      [r["id"] for r in empty["rows"]] == list(home_rows.HOME_ROW_DEFAULT_BUILTINS)
      + list(home_rows.HOME_ROW_DEFAULT_DISCOVERY) and empty["show_hero"] is True,
      str(empty))
check("an empty rows list is the same as none",
      home_rows.normalize_home_screen({"rows": []})["rows"] == empty["rows"])
check("a default discovery row is appended with its discoveryList",
      empty["rows"][-1] == {"id": "discover-trending-tv", "type": "discovery",
                            "enabled": True, "discoveryList": "trending-tv"},
      str(empty["rows"][-1]))
check("show_hero False survives",
      home_rows.normalize_home_screen({"show_hero": False, "rows": []})["show_hero"] is False)

odd = home_rows.normalize_home_screen({"rows": [
    {"id": "suggested", "enabled": False},                # no type -> builtin
    {"id": "genre:Horror", "genre": "Horror"},            # no type -> builtin, as the web reads it
    {"no": "id"},                                         # dropped
    {"id": "discover-popular-tv", "type": "discovery", "discoveryList": "popular-tv"},
]})
check("a row without a type is read as builtin, as the web reads it",
      odd["rows"][0] == {"id": "suggested", "type": "builtin", "enabled": False})
check("a row without an id is dropped",
      all("no" not in r for r in odd["rows"]) and len(odd["rows"]) == 3 + 9)
check("a switched-off row stays switched off",
      odd["rows"][0]["enabled"] is False)
check("...and a present default is not appended again",
      [r["id"] for r in odd["rows"]].count("suggested") == 1
      and [r["id"] for r in odd["rows"]].count("discover-popular-tv") == 1)

# --- naming ----------------------------------------------------------------
SHELVES = {"trending-tv": "Trending Shows",
           "new-noteworthy-tv": "New Series Worth Starting"}
row = {"type": "discovery", "id": "discover-new-noteworthy-tv",
       "discoveryList": "new-noteworthy-tv"}
check("the server's shelf title names a discovery row",
      home_rows.row_title(row, _, SHELVES) == "New Series Worth Starting")
trending = {"type": "discovery", "id": "discover-trending-tv", "discoveryList": "trending-tv"}
check("...even where we have a local label ('Trending Shows', not 'Trending TV Shows')",
      home_rows.row_title(trending, _, SHELVES) == "Trending Shows")
check("the local label is the fallback when the page sent nothing",
      home_rows.row_title(trending, _, {}) == "Trending TV Shows"
      and home_rows.row_title(trending, _) == "Trending TV Shows")
check("the fallback's fallback writes TV, not Tv",
      home_rows.row_title(row, _, None) == "New Noteworthy TV",
      home_rows.row_title(row, _, None))
check("deslug keeps every other word capitalised once",
      home_rows.deslug("top-1980s-movies") == "Top 1980s Movies"
      and home_rows.deslug("trending_tv") == "Trending TV")
check("a genre row is named by its genre",
      home_rows.row_title({"type": "genre", "id": "genre:Horror", "genre": "Horror"}, _) == "Horror")

# --- leaving_soon ------------------------------------------------------------
check("leaving_soon is a builtin we can name",
      home_rows.BUILTIN_ROW_LABELS.get("leaving_soon") == 31123)
check("...offered by the editor (the caller gates it on the lifecycle capability)",
      "leaving_soon" in home_rows.ADDABLE_BUILTIN_IDS)
check("...and NOT a default, so it can be removed",
      home_rows.row_removable({"type": "builtin", "id": "leaving_soon"}) is True
      and "leaving_soon" not in home_rows.HOME_ROW_PROTECTED_IDS)
check("the ten protected rows are unchanged",
      len(home_rows.HOME_ROW_PROTECTED_IDS) == 10)

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
sys.exit(1 if failed else 0)
