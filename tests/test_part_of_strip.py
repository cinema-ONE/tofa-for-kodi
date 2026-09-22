"""7.5.2's "Part of <name>" shelf on Detail's More pane.

The title's own payload carries `tmdb_collection_id`; the members come from
/collections/{id} in the server's order. The strip drops the title on screen,
keeps the not-in-library badge, carries no format badges, sits first in the
pane, and opens a member the library holds by its local id and one it lacks
through the out-of-library Detail.

Run:  python3 test_part_of_strip.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import detail as D
from resources.lib.windows.detail import DetailWindow

RESULTS = []
HERE = "goldfinger-local"
MEMBERS = [
    {"title": "Dr. No", "year": 1962, "in_library": True, "local_media_id": "drno", "type": "movie",
     "tmdb_id": 646, "poster_path": "images/posters/a.jpg",
     "format": {"resolution_label": "4K", "audio": {"label": "Dolby Atmos"}}},
    {"title": "Goldfinger", "year": 1964, "in_library": True, "local_media_id": HERE, "type": "movie",
     "tmdb_id": 658, "poster_path": "images/posters/b.jpg"},
    {"title": "Never Say Never Again", "year": 1983, "in_library": False, "local_media_id": None,
     "type": "movie", "tmdb_id": 36670, "poster_path": "images/posters/c.jpg"},
]


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Client:
    def __init__(self, fail=False):
        self.fail, self.asked = fail, []

    def collection(self, cid):
        self.asked.append(cid)
        if self.fail:
            raise D.http.ApiError(503, "unavailable", "down")
        return {"name": "James Bond Collection", "items": [dict(m) for m in MEMBERS]}

    def resolve_image_url(self, path):
        return "http://srv/" + path


class List:
    def __init__(self):
        self.items, self.selected = [], None

    def reset(self):
        self.items = []

    def addItems(self, items):
        self.items.extend(items)

    def getSelectedItem(self):
        return self.selected


class Control:
    def __init__(self, cid):
        self.cid, self.up, self.down = cid, None, None

    def controlUp(self, other):
        self.up = other.cid

    def controlDown(self, other):
        self.down = other.cid


class Fake:
    _render_collection_strip = DetailWindow._render_collection_strip
    _similar_card = DetailWindow._similar_card
    _wire_more_shelves = DetailWindow._wire_more_shelves
    _similar_clicked = DetailWindow._similar_clicked
    TAB_MORE = DetailWindow.TAB_MORE
    COLLECTION_LIST, SIMILAR_LIST, DISCOVER_LIST = (
        DetailWindow.COLLECTION_LIST, DetailWindow.SIMILAR_LIST, DetailWindow.DISCOVER_LIST)
    MORE_SHELF_IDS = DetailWindow.MORE_SHELF_IDS

    def __init__(self, collection_id=645):
        self.media = {"id": HERE, "tmdb_collection_id": collection_id}
        self.props, self.controls = {}, {}
        self.collection_list, self.similar_list, self.discover_list = List(), List(), List()

    def setProperty(self, k, v):
        self.props[k] = v

    def getControl(self, cid):
        return self.controls.setdefault(cid, Control(cid))

    def _ensure_preferences(self):
        return {"show_format_badges": True}


def run():
    win = Fake()
    shown = win._render_collection_strip(Client(), HERE)
    titles = [mli.getLabel() for mli in win.collection_list.items]
    check("a title in a collection gets the strip", shown is True)
    check("named for the collection", win.props.get("collection_row_title") == "Part of James Bond Collection",
          repr(win.props.get("collection_row_title")))
    check("the title on screen is dropped, the rest keep server order",
          titles == ["Dr. No", "Never Say Never Again"], repr(titles))
    missing = win.collection_list.items[1]
    check("a member the library lacks keeps the not-in-library badge",
          bool(missing.getProperty("watchlist_glyph")), repr(missing.getProperty("watchlist_glyph")))
    owned = win.collection_list.items[0]
    check("no format badges on the strip, though the member carries a format",
          not owned.getProperty("badge_fmt_1"), repr(owned.getProperty("badge_fmt_1")))
    check("...which a normal related card would show",
          bool(win._similar_card(Client(), MEMBERS[0]).getProperty("badge_fmt_1")))

    none = Fake(collection_id=None)
    check("no collection id, no strip, no request",
          none._render_collection_strip(Client(), HERE) is False and not none.collection_list.items)
    failed = Fake()
    check("a failed collection call leaves the pane to the other shelves",
          failed._render_collection_strip(Client(fail=True), HERE) is False
          and failed.props.get("collection_row_title") == "")

    win._wire_more_shelves((True, False, True))
    tab = win.controls[win.TAB_MORE]
    strip, disc = win.controls[win.COLLECTION_LIST], win.controls[win.DISCOVER_LIST]
    check("Down from the tab lands on the strip", tab.down == win.COLLECTION_LIST, repr(tab.down))
    check("the strip goes up to the tab and down to the next shown shelf",
          strip.up == win.TAB_MORE and strip.down == win.DISCOVER_LIST, repr((strip.up, strip.down)))
    check("the last shelf goes up to the strip and stops at the bottom",
          disc.up == win.COLLECTION_LIST and disc.down == win.DISCOVER_LIST, repr((disc.up, disc.down)))

    opened = []
    DetailWindow.open = classmethod(lambda cls, **kw: opened.append(kw))
    win.collection_list.selected = win.collection_list.items[0]
    win._similar_clicked(win.COLLECTION_LIST)
    win.collection_list.selected = win.collection_list.items[1]
    win._similar_clicked(win.COLLECTION_LIST)
    check("an owned member opens by its local id", opened[0] == {"media_id": "drno"}, repr(opened[0]))
    check("a missing member opens the out-of-library Detail with its card",
          opened[1].get("discovery_id") == 36670 and opened[1].get("media_type") == "movie"
          and opened[1].get("discovery_item", {}).get("title") == "Never Say Never Again", repr(opened[1]))

    failed_n = [n for n, ok in RESULTS if not ok]
    print()
    if failed_n:
        print("FAIL: %d of %d" % (len(failed_n), len(RESULTS)))
        return 1
    print("the Part of strip follows 7.5.2 (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
