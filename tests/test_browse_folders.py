"""Browse's folder view: which libraries open in it, and how levels stack.

Server 0.11.0 lists a library by folder: folders first, then videos, in one
paged list. A library of home videos opens in it, as on tofa's web app;
films and shows keep their grid until the Folders pill is pressed.

Run:  python3 test_browse_folders.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


class FakeGrid:
    def __init__(self, n=0):
        self.items, self.pos = [None] * n, 0

    def __len__(self):
        return len(self.items)

    def getSelectedPosition(self):
        return self.pos

    def setSelectedItemByPos(self, pos):
        self.pos = pos

    def reset(self):
        pass


class FakeWindow:
    _browse_folders_offered = MainWindow._browse_folders_offered
    _browse_in_folders = MainWindow._browse_in_folders
    _browse_folder_entries = MainWindow._browse_folder_entries
    _browse_folder_trail = MainWindow._browse_folder_trail
    _browse_open_folder = MainWindow._browse_open_folder
    _browse_folder_up = MainWindow._browse_folder_up
    _browse_folder_root = MainWindow._browse_folder_root
    _FOLDER_TRAIL_CHARS = MainWindow._FOLDER_TRAIL_CHARS
    NAV_LIST_ID, TILES_ID, GRID_ID = 3000, 6020, 6200

    def __init__(self, src, caps=("library.folders",)):
        self.src, self._server_capabilities = src, set(caps)
        self._browse_folders_on, self._browse_folder_path, self._browse_folder_levels = {}, {}, {}
        self._browse_page_data, self._browse_pages_loaded, self._browse_total = {}, set(), 8
        self.grid_list, self.loads, self.restored, self.focus = FakeGrid(8), [], [], self.GRID_ID

    def _browse_active_source(self):
        return self.src

    def getProperty(self, key):
        return "browse" if key == "active_section" else ""

    def getFocusId(self):
        return self.focus

    def setFocusId(self, cid):
        self.focus = cid

    def _get_client(self):
        return object()

    def _browse_load_grid(self):
        self.loads.append(self._browse_folder_path.get(self.src["id"], ""))

    def _browse_show_folder_level(self, client, path, level):
        self.restored.append((path, level["pos"]))

    def _browse_reset_paging(self):
        pass

    def _browse_wire_nav_down(self):
        pass

    def _browse_maybe_load_more(self):
        pass


def main():
    videos = {"kind": "library", "id": "v", "media_type": "other"}
    movies = {"kind": "library", "id": "m", "media_type": "movie"}
    check("a library of videos opens in folders", FakeWindow(videos)._browse_in_folders(), True)
    check("films and shows keep their grid", FakeWindow(movies)._browse_in_folders(), False)
    w = FakeWindow(movies)
    w._browse_folders_on["m"] = True
    check("...until the pill turns folders on", w._browse_in_folders(), True)
    check("never without the server's folder listing",
          FakeWindow(videos, caps=())._browse_in_folders(), False)
    check("never on Watchlist or Collections",
          FakeWindow({"kind": "collections"})._browse_in_folders(), False)

    entries = MainWindow._browse_folder_entries(
        {"folders": [{"name": "Samples", "path": "Samples"}], "items": [{"id": "x"}]})
    check("a page is its folders, marked, then its videos",
          [(e.get("_folder"), e.get("name") or e.get("id")) for e in entries],
          [(True, "Samples"), (None, "x")])

    w = FakeWindow(videos)
    w.grid_list.pos = 5
    w._browse_open_folder({"path": "Samples"})
    w.grid_list.pos = 0
    w._browse_open_folder({"path": "Samples/8K Association"})
    check("opening folders goes down a level each time",
          w.loads, ["Samples", "Samples/8K Association"])
    check("Back goes up one level, from memory: no fetch",
          (w._browse_folder_up(), w.restored[-1], len(w.loads)), (True, ("Samples", 0), 2))
    w._browse_folder_up()
    check("...and lands on the folder we came out of", w.restored[-1], ("", 5))
    check("at the top, Back is Browse's own again", w._browse_folder_up(), False)
    w._browse_folder_path["v"] = "Samples"
    w.focus = w.TILES_ID
    check("Back from the tiles leaves the folder alone", w._browse_folder_up(), False)
    w._browse_folder_path["v"] = "Samples/8K Association"
    check("Select on the library row goes to its folder root",
          (w._browse_folder_root(), w.loads[-1]), (True, ""))
    check("...and does nothing more once there", w._browse_folder_root(), False)

    trail = FakeWindow(videos)._browse_folder_trail
    check("the trail names the folders, not the library",
          trail(["Samples", "8K Association"]), "Samples / 8K Association")
    long = ["A very long folder name number one", "Another long folder name",
            "The folder on screen"]
    check("a long trail drops whole crumbs from the start, never the last",
          trail(long), "\u2026 / Another long folder name / The folder on screen")
    check("...even when the last alone is too long", trail(["x" * 80]), "x" * 80)

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
