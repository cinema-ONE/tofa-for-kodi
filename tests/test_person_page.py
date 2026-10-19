"""The person page reads server 0.12.0's PersonPage: by id when known, else by name.

Run:  python3 test_person_page.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api
from resources.lib.windows import person

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


CALLS = []
client = api.MediaServerClient.__new__(api.MediaServerClient)
client._get = lambda path, params=None: CALLS.append((path, params)) or {}

client.person_page("Ryan Gosling", "30614")
check("with an id: the id route", CALLS[-1] == ("/api/v1/discovery/people/30614", None),
      str(CALLS[-1]))
client.person_page("Ryan Gosling", "")
check("without one: by name",
      CALLS[-1] == ("/api/v1/discovery/people/by-name", {"name": "Ryan Gosling"}),
      str(CALLS[-1]))

# Shaped like a live page: owned credits carry local_media_id.
credits = [
    {"title": "Drive", "type": "movie", "in_library": True,
     "local_media_id": "09b0", "tmdb_id": 64690},
    {"title": "Knock Knock", "type": "movie", "in_library": False, "tmdb_id": 263472},
    {"title": "Odd one", "type": "movie", "in_library": True, "tmdb_id": 1},
]
owned, discover = person.split_credits(credits)
check("an owned credit opens by its library id",
      [it.get("id") for it in owned] == ["09b0"], str(owned))
check("...and keeps its credit fields", owned[0]["tmdb_id"] == 64690)
check("owned but without an id stays visible, as not owned",
      [it["title"] for it in discover] == ["Knock Knock", "Odd one"], str(discover))
check("the page's own dicts are not changed", "id" not in credits[0])
check("no credits at all is two empty halves", person.split_credits(None) == ([], []))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
