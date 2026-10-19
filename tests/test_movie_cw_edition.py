"""A film offers the edition the viewer is part way through.

Since server 0.12.0 each edition keeps its own place: Continue Watching's
edition when part way, else the part-way edition watched last.

Run:  python3 test_movie_cw_edition.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import detail

RESULTS = []
def check(name, ok, detail_=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail_) if detail_ and not ok else ''}")


# Hugo, as the server lists it: the 3D edition first, then the 4K.
F3D = {"id": "42e4", "edition": "3D", "available": True}
F4K = {"id": "d96e", "edition": None, "available": True}
GONE = {"id": "dead", "edition": "Final Cut", "available": False}
pick = detail._movie_file

check("no card: the first available file", pick([F3D, F4K])["id"] == "42e4")
check("Continue Watching's edition wins", pick([F3D, F4K], "d96e")["id"] == "d96e")
check("an unavailable edition is not offered", pick([GONE, F4K], "dead")["id"] == "d96e")
check("an unknown id falls back to the first available", pick([F3D, F4K], "nope")["id"] == "42e4")
check("nothing available: the first file", pick([GONE])["id"] == "dead")
check("no files: nothing", pick([], "d96e") is None)

# With progress records, as the batch answers them.
def rec(pos, at, done=False):
    return {"position_ms": pos, "updated_at": at, "completed": done}
LATER = {"42e4": rec(1_200_000, "2026-10-19T17:20:08Z"), "d96e": rec(2_681_000, "2026-10-19T17:28:12Z")}
check("no card: the edition watched last", pick([F3D, F4K], None, LATER)["id"] == "d96e")
check("a part-way card edition beats a later one", pick([F3D, F4K], "42e4", LATER)["id"] == "42e4")
DONE3D = {"42e4": rec(0, "2026-10-20T10:00:00Z", True), "d96e": rec(2_681_000, "2026-10-19T17:28:12Z")}
check("a finished card edition yields to a part-way one", pick([F3D, F4K], "42e4", DONE3D)["id"] == "d96e")
SHORT = {"d96e": rec(30_000, "2026-10-20T10:00:00Z")}
check("under a minute is not part way", pick([F3D, F4K], None, SHORT)["id"] == "42e4")
check("an unavailable edition's record is ignored",
      pick([GONE, F4K], None, {"dead": rec(900_000, "2026-10-21T00:00:00Z")})["id"] == "d96e")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
