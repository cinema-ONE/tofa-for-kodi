"""A profile's Missing episodes choice (server 0.12.0) on show pages.

Run:  python3 test_missing_episodes.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import episodes

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


AUTO_SHOW = {"show_missing_episodes": True, "missing_episodes_auto": True}
AUTO_HIDE = {"show_missing_episodes": False, "missing_episodes_auto": True}

check("Automatic follows the server: show", episodes.show_missing({}, AUTO_SHOW))
check("Automatic follows the server: hide", not episodes.show_missing({}, AUTO_HIDE))
check("Always show beats the server",
      episodes.show_missing({"layout.missingEpisodes": "show"}, AUTO_HIDE))
check("Never show beats the server",
      not episodes.show_missing({"layout.missingEpisodes": "hide"}, AUTO_SHOW))
check("an unknown value is Automatic",
      episodes.show_missing({"layout.missingEpisodes": "sometimes"}, AUTO_SHOW))
check("no settings at all lists them", episodes.show_missing(None, None))

TODAY = "2026-10-19"
held = {"id": "e1", "files": [{"id": "f1", "available": True}]}
lost = {"id": "e2", "files": [{"id": "f2", "available": False}]}
never = {"id": "e3", "files": [], "air_date": "2020-01-01"}
coming = {"id": "e4", "files": [], "air_date": "2026-11-02"}
SEASONS = [
    {"season_number": 1, "episodes": [held, lost, never]},
    {"season_number": 2, "episodes": [never]},
    {"season_number": 3, "episodes": [coming]},
    {"season_number": 4, "episodes": [], "air_date": "2027-01-01"},
]

check("showing them changes nothing",
      episodes.listed_seasons(SEASONS, True, TODAY) == SEASONS)
listed = episodes.listed_seasons(SEASONS, False, TODAY)
check("a season with nothing held or to come goes",
      [s["season_number"] for s in listed] == [1, 3, 4], str(listed))
check("an episode with files stays, available or not",
      [e["id"] for e in listed[0]["episodes"]] == ["e1", "e2"])
check("an episode still to air stays", [e["id"] for e in listed[1]["episodes"]] == ["e4"])
check("the season keeps its full count", listed[0]["episode_total"] == 3)
check("filtering twice keeps that count",
      episodes.listed_seasons(listed, False, TODAY)[0]["episode_total"] == 3)
check("the server's seasons are not changed", len(SEASONS[0]["episodes"]) == 3)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
