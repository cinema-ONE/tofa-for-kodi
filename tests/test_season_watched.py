"""Marking a season is ONE request now, with the old loop as the fallback.

The server had no season-scoped endpoint until 0.9.28, so detail.py sent a
PUT per file -- its own comment said "a 39-episode season really is 39
requests". PUT /seasons/{id}/watched replaces that. The fallback matters as
much as the fast path: a season we have no id for, or a server too old to
know the route, must still work.

Run:  python3 test_season_watched.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeClient:
    def __init__(self, season_ok=True):
        self.season_ok = season_ok
        self.season_calls = []
        self.file_calls = []
    def update_season_watched(self, season_id, watched):
        self.season_calls.append((season_id, watched))
        if not self.season_ok:
            raise http.ApiError(404, "not_found", "no such route")
        return {"season_id": season_id, "updated": 39, "watched": watched}
    def update_watched(self, file_id, watched):
        self.file_calls.append((file_id, watched))
        return {}


class FakeDetail:
    _mark_season = DetailWindow._mark_season
    def refresh_watch_progress(self):
        self.refreshed = True


PLAYABLE = [({"episode_number": n}, {"id": f"f{n}"}) for n in range(1, 40)]

win = FakeDetail()
c = FakeClient()
win._mark_season(c, PLAYABLE, True, season_id="S-1")
check("one request, not 39", len(c.season_calls) == 1 and not c.file_calls,
      f"{len(c.season_calls)} season / {len(c.file_calls)} file")
check("...carrying the direction", c.season_calls[0] == ("S-1", True), str(c.season_calls))
check("the grid is refreshed", getattr(win, "refreshed", False))

# No season id -- an older payload. Must still work, the slow way.
win = FakeDetail()
c = FakeClient()
win._mark_season(c, PLAYABLE, False, season_id=None)
check("no season id falls back to per-episode", len(c.file_calls) == 39, str(len(c.file_calls)))
check("...and does not call the season route", not c.season_calls)
check("...carrying the direction", c.file_calls[0] == ("f1", False), str(c.file_calls[:1]))

# Server too old: the route 404s. Must not lose the action.
win = FakeDetail()
c = FakeClient(season_ok=False)
win._mark_season(c, PLAYABLE, True, season_id="S-1")
check("a failing season route falls back", len(c.file_calls) == 39, str(len(c.file_calls)))
check("...after trying it once", len(c.season_calls) == 1, str(len(c.season_calls)))
check("the grid is still refreshed", getattr(win, "refreshed", False))

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
