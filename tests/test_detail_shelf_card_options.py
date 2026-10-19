"""Detail's shelf card menu does every row it offers.

More Like This, More to Discover and the collection strip used to offer
Watchlist and Mark as Watched rows that did nothing; Seen it and Not
interested were not offered at all.

Run:  python3 test_detail_shelf_card_options.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, toast
from resources.lib.windows import cardoptions as co
from resources.lib.windows import detail as D
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


toast.show = lambda message, *a, **k: None

OWNED = {"id": "m-arrival", "media_type": "movie", "tmdb_id": None,
         "title": "Arrival", "watched": False}
OWNED_SHOW = {"id": "m-severance", "media_type": "tv", "tmdb_id": None, "title": "Severance"}
REQUESTABLE = {"tmdb_id": 693134, "media_type": "movie", "title": "Dune: Part Two"}
MEMBER_MISSING = {"tmdb_id": 36670, "type": "movie", "in_library": False,
                  "local_media_id": None, "seen": False, "not_interested": False,
                  "title": "Never Say Never Again"}
MEMBER_HELD = {"tmdb_id": 646, "type": "movie", "in_library": True,
               "local_media_id": "m-drno", "seen": False, "not_interested": False,
               "title": "Dr. No"}
NO_IDS = {"title": "Mystery"}


class Client:
    def __init__(self):
        self.calls, self.listed, self.completed, self.fail = [], [], set(), False

    def _call(self, *call):
        if self.fail:
            raise http.ApiError(500, "boom", "")
        self.calls.append(call)

    def resolve_image_url(self, path): return "http://srv/" + path
    def watchlist(self): return [dict(e) for e in self.listed]

    def watchlist_add(self, media_id):
        self._call("add", media_id)
        self.listed.append({"media_id": media_id, "tmdb_id": None})

    def watchlist_remove(self, media_id):
        self._call("remove", media_id)
        self.listed = [e for e in self.listed if e["media_id"] != media_id]

    def watchlist_add_content(self, media_type, tmdb_id, snapshot=None):
        self._call("add_content", media_type, tmdb_id)
        self.listed.append({"media_id": None, "tmdb_id": tmdb_id})

    def watchlist_remove_content(self, media_type, tmdb_id):
        self._call("remove_content", media_type, tmdb_id)
        self.listed = [e for e in self.listed if e["tmdb_id"] != tmdb_id]

    def set_seen(self, media_type, tmdb_id, on): self._call("seen", media_type, tmdb_id, on)

    def set_not_interested(self, media_type, tmdb_id, on):
        self._call("not_interested", media_type, tmdb_id, on)

    def media_detail(self, media_id):
        if media_id == OWNED_SHOW["id"]:
            eps = [{"episode_number": n, "files": [{"id": f"f-e{n}", "available": True}]}
                   for n in (1, 2)]
            return {"seasons": [{"season_number": 1, "episodes": eps}]}
        return {"files": [{"id": media_id + "-4k", "available": True},
                          {"id": media_id + "-hd", "available": True},
                          {"id": media_id + "-gone", "available": False}]}

    def media_progress_batch(self, ids):
        return {"items": [{"media_file_id": i, "completed": True}
                          for i in ids if i in self.completed]}

    def update_watched(self, fid, watched): self._call("watched", fid, watched)


class List:
    def __init__(self, item): self.item = item
    def getSelectedItem(self): return self.item


class Fake:
    _open_card_options = DetailWindow._open_card_options
    _apply_shelf_option = DetailWindow._apply_shelf_option
    _similar_card = DetailWindow._similar_card
    EPISODE_GRID_PANEL = DetailWindow.EPISODE_GRID_PANEL
    MORE_SHELF_IDS = DetailWindow.MORE_SHELF_IDS
    SIMILAR_LIST, DISCOVER_LIST, COLLECTION_LIST = (
        DetailWindow.SIMILAR_LIST, DetailWindow.DISCOVER_LIST, DetailWindow.COLLECTION_LIST)

    def __init__(self, client, payload, shelf=DetailWindow.SIMILAR_LIST):
        self.client, self.shelf, self.opened = client, shelf, []
        held = None if shelf != DetailWindow.COLLECTION_LIST else bool(payload.get("in_library"))
        card = self._similar_card(client, dict(payload), in_library=held)
        self.similar_list = self.discover_list = self.collection_list = List(card)
        self.episode_list = None

    def _get_client(self): return self.client
    def _ensure_preferences(self): return {}
    def _similar_clicked(self, cid): self.opened.append(cid)

    @property
    def card(self): return self.similar_list.item

    def menu(self, pick=None):
        """The keys the panel offered; `pick` is chosen from them."""
        offered = []
        def show(**kw):
            offered.extend(kw["keys"])
            return pick if pick in kw["keys"] else None
        D.cardoptions.show = show
        self._open_card_options(self.shelf)
        return offered


c = Client()
win = Fake(c, OWNED)
check("an owned card wears in-library `watchlisted`", win.card.getProperty("watchlisted") == "1")
check("...yet the menu asks the server, so it offers Add",
      win.menu() == [co.PLAY, co.DETAILS, co.MARK_WATCHED, co.WATCHLIST_ADD], str(win.menu()))
win.menu(co.WATCHLIST_ADD)
check("Add to Watchlist on a held title goes by media id", c.calls[-1] == ("add", "m-arrival"),
      str(c.calls))
check("...and the reopened menu offers Remove", co.WATCHLIST_REMOVE in win.menu())
win.menu(co.WATCHLIST_REMOVE)
check("Remove goes by media id too", c.calls[-1] == ("remove", "m-arrival"), str(c.calls))
check("...and Add is back", co.WATCHLIST_ADD in win.menu())

c.calls.clear()
win.menu(co.MARK_WATCHED)
check("Mark as Watched marks every available file of a film",
      c.calls == [("watched", "m-arrival-4k", True), ("watched", "m-arrival-hd", True)],
      str(c.calls))
check("...and the reopened menu offers Unwatched",
      co.MARK_UNWATCHED in win.menu() and co.MARK_WATCHED not in win.menu())
win.menu(co.MARK_UNWATCHED)
check("Mark as Unwatched clears them", c.calls[-1] == ("watched", "m-arrival-hd", False))
check("...and Watched is offered again", co.MARK_WATCHED in win.menu())

c = Client()
c.completed = {"f-e1"}
Fake(c, OWNED_SHOW).menu(co.MARK_WATCHED)
check("on a show it marks the next-up episode only",
      c.calls == [("watched", "f-e2", True)], str(c.calls))

c = Client()
win = Fake(c, REQUESTABLE, DetailWindow.DISCOVER_LIST)
check("a requestable card: Details and Watchlist", win.menu() == [co.DETAILS, co.WATCHLIST_ADD])
win.menu(co.WATCHLIST_ADD)
check("...added by content", c.calls[-1] == ("add_content", "movie", 693134), str(c.calls))
win.menu(co.WATCHLIST_REMOVE)
check("...and removed by content", c.calls[-1] == ("remove_content", "movie", 693134))

c = Client()
win = Fake(c, MEMBER_MISSING, DetailWindow.COLLECTION_LIST)
check("a missing collection member offers Seen it and Not interested",
      win.menu()[-2:] == [co.SEEN_ADD, co.NOT_INTERESTED_ADD], str(win.menu()))
win.menu(co.SEEN_ADD)
check("Seen it is written", c.calls[-1] == ("seen", "movie", 36670, True), str(c.calls))
check("...and the reopened menu offers its undo", co.SEEN_REMOVE in win.menu())
win.menu(co.NOT_INTERESTED_ADD)
check("Not interested is written",
      c.calls[-1] == ("not_interested", "movie", 36670, True), str(c.calls))

c = Client()
win = Fake(c, MEMBER_HELD, DetailWindow.COLLECTION_LIST)
keys = win.menu()
check("a held member: Mark as Watched and Not interested, no Seen it",
      co.MARK_WATCHED in keys and co.NOT_INTERESTED_ADD in keys and co.SEEN_ADD not in keys,
      str(keys))
win.menu(co.WATCHLIST_ADD)
check("...listed by its local id", c.calls[-1] == ("add", "m-drno"), str(c.calls))
check("...and found by it on reopen", co.WATCHLIST_REMOVE in win.menu())

check("no id of any kind: no Watchlist row to fail",
      Fake(Client(), NO_IDS).menu() == [co.DETAILS])

c = Client()
c.fail = True
win = Fake(c, OWNED)
win.menu(co.MARK_WATCHED)
check("a failed write leaves the card's toggle alone", not win.card.getProperty("watched"))

# No dead rows: every key any of these cards offers does something.
for payload, shelf in ((OWNED, DetailWindow.SIMILAR_LIST),
                       (REQUESTABLE, DetailWindow.DISCOVER_LIST),
                       (MEMBER_MISSING, DetailWindow.COLLECTION_LIST),
                       (MEMBER_HELD, DetailWindow.COLLECTION_LIST)):
    for key in Fake(Client(), payload, shelf).menu():
        c = Client()
        win = Fake(c, payload, shelf)
        win.menu(key)
        check(f"{payload['title']}: {key} does something", bool(c.calls or win.opened))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
