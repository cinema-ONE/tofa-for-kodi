"""A film opened from Continue Watching resumes that card's edition.

Since server 0.12.0 each edition keeps its own place, so the first file's
position is not the one the viewer left.

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

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
