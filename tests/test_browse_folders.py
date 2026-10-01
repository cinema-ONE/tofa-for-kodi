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


class FakeWindow:
    _browse_folders_offered = MainWindow._browse_folders_offered
    _browse_in_folders = MainWindow._browse_in_folders
    _browse_folder_entries = MainWindow._browse_folder_entries
    _browse_open_folder = MainWindow._browse_open_folder
    _browse_folder_up = MainWindow._browse_folder_up
    NAV_LIST_ID, SIDEBAR_ID, SIDEBAR_LIBRARY_ID, GRID_ID = 3000, 6000, 6010, 6200

    def __init__(self, src, caps=("library.folders",)):
        self.src, self._server_capabilities = src, set(caps)
        self._browse_folders_on, self._browse_folder_path, self._browse_folder_return = {}, {}, {}
        self.grid_list, self.loads, self.focus = FakeGrid(8), [], self.GRID_ID

    def _browse_active_source(self):
        return self.src

    def getProperty(self, key):
        return "browse" if key == "active_section" else ""

    def getFocusId(self):
        return self.focus

    def setFocusId(self, cid):
        self.focus = cid

    def _browse_load_grid(self):
        self.loads.append(self._browse_folder_path.get(self.src["id"], ""))

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
    check("Back goes up one level", (w._browse_folder_up(), w.loads[-1]), (True, "Samples"))
    w._browse_folder_up()
    check("...and lands on the folder we came out of", (w.loads[-1], w.grid_list.pos), ("", 5))
    check("at the top, Back is Browse's own again", w._browse_folder_up(), False)
    w._browse_folder_path["v"] = "Samples"
    w.focus = w.SIDEBAR_ID
    check("Back from the sidebar leaves the folder alone", w._browse_folder_up(), False)

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
