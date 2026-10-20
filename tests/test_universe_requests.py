"""Request N missing on a universe, as tofa's web app picks and words it.

Run:  python3 test_universe_requests.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import universe as U

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


def item(n, **kw):
    return dict(dict(type="movie", tmdb_id=n, title=f"T{n}", year=2000 + n, in_library=False,
                     local_media_id=None), **kw)


u = U.build({"id": "x", "kind": "curated", "name": "X", "items": [
    item(1, chapter="One", in_library=True, local_media_id="m1"),
    item(2, chapter="One"),
    item(3, chapter="One", request_status="requested"),
    item(4, chapter="Two", upcoming=True),
    item(5, chapter="Two", type="tv", season_number=1),
    item(5, chapter="Two", type="tv", season_number=2),
    item(6, chapter="Two", type="tv"),
]})
rows = U.missing_rows(u)
check("held, requested and upcoming titles are left out",
      [r["title"] for r in rows] == ["T2", "T5", "T6"], str([r["title"] for r in rows]))
check("a series listed by season is one row with those seasons",
      rows[1]["kind"] == "series" and rows[1]["seasons"] == [1, 2], str(rows[1]))
check("a series listed whole asks for all of it", rows[2]["seasons"] is None)
check("a chapter offers only its own", [r["title"] for r in U.missing_rows(u, chapter=0)] == ["T2"])
check("no Radarr: no films", [r["kind"] for r in U.missing_rows(u, films=False)] == ["series", "series"])
check("no Sonarr: no series", [r["title"] for r in U.missing_rows(u, shows=False)] == ["T2"])
check("asked for on this page: gone at once",
      [r["title"] for r in U.missing_rows(u, requested=frozenset({u["members"][1]["key"]}))]
      == ["T5", "T6"])

detail = {"seasons": [{"season_number": 0}, {"season_number": 1, "episode_count": 8},
                      {"season_number": 2, "episode_count": 8}, {"season_number": 3}],
          "library_seasons": [{"season_number": 1, "episodes_available": 8}],
          "request_seasons": [{"season_number": 3, "status": "requested"},
                              {"season_number": 2, "status": "denied"}]}
check("requestable: not complete here, not on request (a denial does not count)",
      U.requestable_seasons(detail) == [0, 2], str(U.requestable_seasons(detail)))
check("a whole series asks for all but specials", U.default_seasons(rows[2], [0, 2, 4]) == [2, 4])
check("a listed series asks for its own seasons only", U.default_seasons(rows[1], [1, 2, 3]) == [1, 2])
check("season labels read as the app's", (U.seasons_label([2]), U.seasons_label([1, 2, 3]),
      U.seasons_label([1, 3, 5])) == ("Season 2", "Seasons 1–3", "Seasons 1, 3 and 5"))
check("all requested: nothing to say", U.request_outcome([("film", True)]) is None)
check("some failed: one sentence",
      U.request_outcome([("film", True), ("series", False)]) == "Requested 1 of 2; try the other 1 again")
check("all failed: one sentence", U.request_outcome([("film", False)]) == "Couldn't request it, try again")

from resources.lib import http, toast                  # noqa: E402
from resources.lib.windows import universepage as P   # noqa: E402


class Client:
    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def discovery_detail(self, media_type, tmdb_id):
        if tmdb_id == 6:
            raise http.ApiError(500, "x", "x")
        return {"seasons": [{"season_number": 1}, {"season_number": 2}], "tvdb_id": 77}

    def create_request(self, media_type, title, tmdb_id, seasons=None, tvdb_id=None):
        self.sent.append((media_type, title, seasons, tvdb_id))
        if title in self.fail:
            raise http.ApiError(500, "x", "x")


class Page:
    _request_listing = P.UniverseWindow._request_listing
    _send_requests = P.UniverseWindow._send_requests
    REQUEST_ID, ORDER_ID = P.UniverseWindow.REQUEST_ID, P.UniverseWindow.ORDER_ID
    GRID_REQUEST_IDS = P.UniverseWindow.GRID_REQUEST_IDS
    GRID_PANEL_IDS = P.UniverseWindow.GRID_PANEL_IDS

    def __init__(self, client):
        self.client, self._requested, self._requesting, self.reinit = client, set(), True, 0
        self.focus, self.props = P.UniverseWindow.REQUEST_ID, {}

    def _refresh(self):
        self.reinit += 1
        self.props["u_request_label"] = ""        # nothing left to ask for

    def getFocusId(self):
        return self.focus

    def setFocusId(self, control_id):
        self.focus = control_id

    def getProperty(self, key):
        return self.props.get(key, "")


said = []
toast.show = lambda message, *a, **k: said.append(message)
page = Page(Client(fail={"T5"}))
listing, plan = page._request_listing(rows)
check("the list: a film, and a series with its seasons; a series whose seasons failed to load is left out",
      [(k, t, d) for k, t, d in listing] == [(rows[0]["key"], "T2", "Film · 2002"),
                                             (rows[1]["key"], "T5", "Series · 2005 · Seasons 1–2")],
      str(listing))
page._send_requests([plan[k] for k, _t, _d in listing])
check("one request each, the series with its seasons and TVDB id",
      page.client.sent == [("movie", "T2", None, None), ("tv", "T5", [1, 2], 77)],
      str(page.client.sent))
check("a failure is one sentence; the page refreshes and forgets nothing it asked for",
      said[-1] == "Requested 1 of 2; try the other 1 again" and page.reinit == 1
      and rows[0]["members"][0]["key"] in page._requested and not page._requesting, str(said))
check("the Request pill, once empty, hands focus to the pill before it",
      page.focus == P.UniverseWindow.ORDER_ID, str(page.focus))

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
