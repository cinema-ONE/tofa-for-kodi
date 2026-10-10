"""Collections sort by Name or Size, and under Name an A-Z rail cuts the series.

Ours, not the app's: the server returns collections in one order (most
titles first) and takes no sort or letter, so all of it is done here.

Run:  python3 test_collections_sort_rail.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


key, letter = main.collection_name_key, main.collection_letter

# --- the name key and its letter ----------------------------------------
check("a leading The is ignored", key("The Olsen Gang Collection") == "olsen gang collection")
check("...and A and An", key("A Nightmare on Elm Street") == "nightmare on elm street"
      and key("An American Tail") == "american tail")
check("German articles stay (Die Hard is under D)", letter("Die Hard Collection") == "D")
check("a name that is only an article keeps it", key("The") == "the")
check("accents fold to the base letter", letter("Ägypten") == "A" and letter("Éclair") == "E")
check("case is ignored", key("ALIEN") == key("alien"))
check("digits and punctuation file under #",
      letter("00 Schneider Filmreihe") == "#" and letter("48 Hrs. Collection") == "#"
      and letter("(500) Days") == "#")

# --- the two orders -----------------------------------------------------
C = [{"name": "The Matrix Collection", "item_count": 4},
     {"name": "Alien Collection", "item_count": 6},
     {"name": "James Bond Collection", "item_count": 25},
     {"name": "Halloween Collection", "item_count": 11},
     {"name": "Winnetou Collection", "item_count": 11},
     {"name": "48 Hrs. Collection", "item_count": 2}]
names = lambda cs: [c["name"].split()[0] for c in cs]  # noqa: E731

check("Name runs A to Z, digits before letters",
      names(main.sort_collections(C, "name")) == ["48", "Alien", "Halloween", "James", "The", "Winnetou"],
      str(names(main.sort_collections(C, "name"))))
check("Name reversed runs Z to A",
      names(main.sort_collections(C, "name", True))[0] == "Winnetou")
check("Size runs largest first, a tie by name",
      names(main.sort_collections(C, "size")) == ["James", "Halloween", "Winnetou", "Alien", "The", "48"])
check("Size reversed runs smallest first, a tie still A to Z",
      names(main.sort_collections(C, "size", True)) == ["48", "The", "Alien", "Halloween", "Winnetou", "James"])


# --- the page: sort, rail and the cut -----------------------------------
class Ctl:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class FakeList(list):
    sel = 0
    rebuilt = 0

    def reset(self):
        self.clear()
        self.rebuilt += 1

    def addItems(self, items):
        self.extend(items)

    def selectItem(self, _i):
        pass

    def getSelectedItem(self):
        return self[self.sel] if self else None


W = main.MainWindow


class FakeWindow:
    """A stand-in `self` carrying the real methods under test."""

    def __init__(self):
        self.props = {}
        self._sources = [{"kind": "collections", "name": "Collections"}]
        self._active_source_idx = 0
        self._browse_collection = None
        self._browse_letter = ""
        self._browse_letter_counts = {}
        self._server_capabilities = set()
        self._coll_sort_idx = 0
        self._coll_sort_reversed = False
        self._coll_letter_counts = {}
        self._coll_custom_all = [{"name": "Zebra test", "item_count": 2, "_custom": True},
                                 {"name": "Panasonic A/B", "item_count": 8, "_custom": True}]
        self._coll_series_all = list(C)
        self.alpha_list = FakeList()
        self.custom_collection_list = FakeList()
        self.collection_list = FakeList()

    def setProperty(self, k, v):
        self.props[k] = v

    def getProperty(self, k):
        return self.props.get(k, "")

    def getControl(self, _cid):
        return Ctl()

    def _get_client(self):
        return object()

    def _browse_active_source(self):
        return self._sources[self._active_source_idx]

    def _browse_stage_collection_art(self, *a):
        pass

    def _browse_apply_collection_row(self, _client, mli, _row):
        return mli

    def _browse_blanks(self, n):
        return [None] * n

    def _browse_fill_collection_window(self, _client):
        pass

    def _browse_sync_custom_last(self):
        pass


for _name in ("COLLECTION_SORT_OPTIONS", "COLL_SORT_ID", "ALPHA_RAIL_ID", "GRID_ID",
              "_browse_render_collections", "_browse_fill_alpha_rail", "_browse_alpha_wanted",
              "_browse_on_collections_index", "_browse_alpha_speech", "_alpha_value",
              "_browse_mark_alpha_active", "_browse_sync_coll_sort_pill", "_browse_chip_width",
              "_browse_coll_sort_picked", "_browse_reset_letter", "_browse_alpha_clicked"):
    setattr(FakeWindow, _name, W.__dict__.get(_name, getattr(W, _name)))  # keeps staticmethods

page = FakeWindow()
page._browse_render_collections(object())
glyphs = lambda: [i.getProperty("glyph") for i in page.alpha_list]  # noqa: E731

check("Name is the default", page.props["browse_chip_6145_label"] == u"↑  Name")
check("the series and your own each sort by name",
      names(page._collection_items)[:2] == ["48", "Alien"]
      and [c["name"] for c in page._custom_items] == ["Panasonic A/B", "Zebra test"])
check("under Name the rail shows the series' letters, All first and # last",
      page.props.get("browse_alpha") == "1"
      and glyphs() == ["All", "A", "H", "J", "M", "W", "#"], str(glyphs()))
check("a letter is spoken with its count of collections",
      page.alpha_list[2].getLabel() == "H, 1 collection")

page.alpha_list.sel = 4               # M
page._browse_alpha_clicked()
check("a letter cuts the series to it", names(page._collection_items) == ["The"])
check("...and never your own collections", len(page._custom_items) == 2
      and len(page.custom_collection_list) == 1)
check("...and leaves the rail as it was, so focus stays on the letter",
      glyphs() == ["All", "A", "H", "J", "M", "W", "#"] and page.alpha_list.rebuilt == 1)

page._browse_coll_sort_picked(0)
check("choosing Name again reverses it, the letter kept",
      page.props["browse_chip_6145_label"] == u"↓  Name" and page._browse_letter == "M")

page._browse_coll_sort_picked(1)
check("Size runs largest first and drops the letter",
      page.props["browse_chip_6145_label"] == u"↓  Size" and page._browse_letter == ""
      and names(page._collection_items)[0] == "James")
check("...and has no rail", page.props.get("browse_alpha") == "")

page._browse_coll_sort_picked(1)
check("choosing Size again runs smallest first",
      page.props["browse_chip_6145_label"] == u"↑  Size"
      and names(page._collection_items)[0] == "48")

page._browse_collection = {"items": []}
check("inside a collection the rail is not the collections'", not page._browse_on_collections_index())

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
