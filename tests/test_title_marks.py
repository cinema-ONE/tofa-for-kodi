"""Seen it and Not interested (server 0.12.0) in the card options panel.

Run:  python3 test_title_marks.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, http, toast
from resources.lib.windows import cardoptions as co, titlemarks

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


BASE = dict(in_library=False, fully_watched=False, has_progress=False,
            on_watchlist=False, in_continue_watching=False)
check("no marks offered: the panel is as before",
      co.option_keys(**BASE) == [co.DETAILS, co.WATCHLIST_ADD])
check("the app's order: Seen it above Watchlist, Not interested below",
      co.option_keys(**BASE, seen=False, not_interested=False)
      == [co.DETAILS, co.SEEN_ADD, co.WATCHLIST_ADD, co.NOT_INTERESTED_ADD])
check("the app's words", [co._CATALOG[k][0] for k in (co.SEEN_ADD, co.SEEN_REMOVE,
      co.NOT_INTERESTED_ADD, co.NOT_INTERESTED_REMOVE)]
      == ["Seen it", "Seen", "Not interested", "Hidden from suggestions"])
check("a set mark offers its undo",
      co.option_keys(**BASE, seen=True, not_interested=True)
      == [co.DETAILS, co.SEEN_REMOVE, co.WATCHLIST_ADD, co.NOT_INTERESTED_REMOVE])
check("every new key has a label and glyph",
      all(k in co._CATALOG for k in titlemarks.KEYS))

# Discover items carry the flags; a held one has Mark as Watched instead.
NOT_HELD = {"type": "movie", "tmdb_id": 263472, "in_library": False,
            "seen": False, "not_interested": True}
HELD = dict(NOT_HELD, in_library=True, local_media_id="09b0")
check("not held: both rows", titlemarks.offered(NOT_HELD) == (False, True))
check("held: Not interested only", titlemarks.offered(HELD) == (None, True))
check("a library card carries no flags: no rows",
      titlemarks.offered({"id": "x", "type": "movie", "tmdb_id": 1}) == (None, None))
check("no TMDB id: no rows",
      titlemarks.offered({"type": "movie", "seen": False}) == (None, None))
check("ids handed in count (Detail's own)",
      titlemarks.offered({"seen": True}, "tv", 1399) == (True, None))

CALLS, TOASTS = [], []
toast.show = lambda message, *a, **k: TOASTS.append(message)
client = api.MediaServerClient.__new__(api.MediaServerClient)
client._put = lambda path, *a, **k: CALLS.append(("PUT", path))
client._delete = lambda path, *a, **k: CALLS.append(("DELETE", path))

item = dict(NOT_HELD)
check("a mark is handled", titlemarks.apply(client, co.SEEN_ADD, item) is True)
check("...as a PUT on the seen route",
      CALLS[-1] == ("PUT", "/api/v1/users/me/seen/movie/263472"), str(CALLS))
check("...recorded on the card's data, so the menu offers the undo", item["seen"] is True)
titlemarks.apply(client, co.NOT_INTERESTED_REMOVE, item)
check("undo is a DELETE on not-interested",
      CALLS[-1] == ("DELETE", "/api/v1/users/me/not-interested/movie/263472"), str(CALLS))
check("success is silent, as on the app", TOASTS == [], str(TOASTS))
check("and reports it was saved", titlemarks.apply(client, co.NOT_INTERESTED_ADD, item) is True)
check("other keys are left to the caller", titlemarks.apply(client, co.PLAY, item) is None)

def refuse(path, *a, **k):
    raise http.ApiError(500, "boom", "")
client._put = refuse
item = dict(NOT_HELD)
check("a failure reports False", titlemarks.apply(client, co.SEEN_ADD, item) is False)
check("a failure changes nothing", item["seen"] is False)
check("...and says so", TOASTS[-1] == "Couldn't update Seen it, try again later", TOASTS[-1])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
