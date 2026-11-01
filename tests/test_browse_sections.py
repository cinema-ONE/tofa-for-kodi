"""Browse's tiles come from server 0.12.0's sections (Movies, TV Shows, Other).

Run:  python3 test_browse_sections.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import main

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


W = main.MainWindow
# The live shape: Movies spans two libraries, TV Shows has one.
MOVIES = {"key": "type:movie", "kind": "type", "media_type": "movie", "name": "Movies",
          "total": 11624, "library_id": None,
          "libraries": [{"id": "en", "name": "Movies"}, {"id": "de", "name": "Movies (DE)"}]}
TV = {"key": "type:tv", "kind": "type", "media_type": "tv", "name": "TV Shows",
      "total": 874, "libraries": [{"id": "tv1", "name": "TV Shows"}]}
OWN_TAB = {"key": "library:kids", "kind": "library", "media_type": "movie", "name": "Kids",
           "total": 12, "library_id": "kids", "libraries": [{"id": "kids", "name": "Kids"}]}

movies, tv, kids = (W._browse_section_source(s) for s in (MOVIES, TV, OWN_TAB))
check("a section spanning libraries has no single id", movies["id"] is None, str(movies))
check("...and is filtered by its type", movies["media_type"] == "movie")
check("a one-library section browses as that library", tv["id"] == "tv1", str(tv))
check("a library's own tab uses its id", kids["id"] == "kids", str(kids))
check("the count is the section's total", tv["count"] == "874", tv["count"])
check("every section is a library-kind source",
      {s["kind"] for s in (movies, tv, kids)} == {"library"})

check("walls are keyed by section, not by a shared None id",
      len({W._browse_wall_key(s) for s in (movies, tv, kids)}) == 3)


class Caps:
    _server_capabilities = {"library.folders"}

check("no folders for a section spanning libraries",
      not W._browse_folders_offered(Caps(), movies))
check("folders for a one-library section", W._browse_folders_offered(Caps(), tv))

MIXED = {"key": "library:mix", "kind": "library", "library_kind": "mixed", "media_type": "movie",
         "name": "Family", "total": 40, "library_id": "mix",
         "libraries": [{"id": "mix", "name": "Family"}]}
mixed = W._browse_section_source(MIXED)
check("a mixed library is not filtered by a type", mixed["media_type"] is None, str(mixed))
check("...and browses as that library", mixed["id"] == "mix")


class Folders(Caps):
    _browse_folders_on = {}
    def _browse_active_source(self):
        return mixed
    def _browse_folders_offered(self, src):
        return True

check("...and opens on its titles, not its folders", not W._browse_in_folders(Folders(), mixed))
check("a library of other videos still opens on its folders", W._browse_in_folders(
    Folders(), W._browse_section_source({"kind": "library", "media_type": "other", "library_id": "v"})))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
