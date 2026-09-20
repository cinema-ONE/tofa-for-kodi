"""A season with nothing in it says so in words, not as a zero count.

7.1 asks for a status BELOW the season's name and rules out the
alternatives by name -- not a faded pill, an icon, or a zero count, because
none of those distinguishes "nothing here" from "a season you have
finished". We set only an episode count, which is exactly the case it names.

The distinction the two sentences draw is the point: a season with no files
is one you never had, while a season whose files are all unavailable is one
the server has lost track of -- a renamed folder, an unmounted disk. A
viewer can act on the second and not on the first.

Run:  python3 test_season_availability.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import episodes as E

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def season(*eps):
    return {"season_number": 1, "episodes": list(eps)}

def ep(*files):
    return {"episode_number": 1, "files": list(files)}

HAVE = {"id": "a", "available": True}
GONE = {"id": "b", "available": False}

# 1. The ordinary case says nothing at all: an absence needs no announcing.
check("one playable file is silent",
      E.season_availability(season(ep(HAVE))) == E.SEASON_IN_LIBRARY)
check("...and so is a season only PARTLY available",
      E.season_availability(season(ep(HAVE), ep(GONE))) == E.SEASON_IN_LIBRARY)

# 2. Episodes known, no files anywhere: never had it.
check("episodes with no files at all",
      E.season_availability(season(ep(), ep())) == E.SEASON_NOT_IN_LIBRARY)
check("...including a single episode",
      E.season_availability(season(ep())) == E.SEASON_NOT_IN_LIBRARY)
check("...and when `files` is absent rather than empty",
      E.season_availability({"episodes": [{"episode_number": 1}]})
      == E.SEASON_NOT_IN_LIBRARY)

# 3. Files recorded, none of them available: the server has lost them. This
#    is the one a viewer can DO something about, so it must not read the
#    same as the case above.
check("every file unavailable is MISSING, not absent",
      E.season_availability(season(ep(GONE), ep(GONE))) == E.SEASON_MISSING)
check("...and the two states are different",
      E.SEASON_MISSING != E.SEASON_NOT_IN_LIBRARY)

# 4. A shell makes NO claim. Saying "not in library" about episodes nobody
#    has fetched would be a guess, and it would flicker when they arrive.
check("no episodes loaded is a shell",
      E.season_availability({"season_number": 2}) == E.SEASON_UNLOADED)
check("...as is an empty episode list",
      E.season_availability({"season_number": 2, "episodes": []}) == E.SEASON_UNLOADED)
check("...and a shell is not 'not in library'",
      E.SEASON_UNLOADED != E.SEASON_NOT_IN_LIBRARY)

# 5. Only the two real states carry a sentence; the other two are silent.
from resources.lib.windows import detail as D
check("in-library has no sentence", E.SEASON_IN_LIBRARY not in D._SEASON_AVAILABILITY)
check("a shell has no sentence", E.SEASON_UNLOADED not in D._SEASON_AVAILABILITY)
check("not-in-library has one", E.SEASON_NOT_IN_LIBRARY in D._SEASON_AVAILABILITY)
check("missing has one", E.SEASON_MISSING in D._SEASON_AVAILABILITY)
check("...and they are different strings",
      D._SEASON_AVAILABILITY[E.SEASON_NOT_IN_LIBRARY]
      != D._SEASON_AVAILABILITY[E.SEASON_MISSING])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
