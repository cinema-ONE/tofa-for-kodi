"""The Collections index fills a WINDOW, not all 529 tiles.

Browse's Collections section stalled for 1.6s warm and 10.6-33.3s cold on
the cinema box, every single time it was opened. The code assumed the index
was small -- its comment said "~15 tiles, so the batch stays small" -- and
on that assumption it staged every tile's art in two blocking prefetches and
then built every card before showing anything.

The real library answers **529 collections**, measured from the box's own
log line:

    browse: 529 collection(s) (1 custom) in 33.27s
    browse: 529 collection(s) (1 custom) in 1.62s     <- warm

So it staged ~1058 images and made 529 cards at ~10 C++ writes each, on the
action thread, for the ~15 tiles a viewer can actually see. That is the same
mistake the poster grid made and fixed in 4847b47, and the fix is the same
one: allocate blanks up front, fill a window around the selection, and stage
only that window's art.

These checks pin the properties that make it a window rather than a sweep,
because the failure mode is silent -- nothing raises if it goes back to
filling everything, it just gets slow again.

Run:  python3 test_collections_windowed_fill.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import artcache  # noqa: E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


TOTAL = 529            # what the real server answers
CUSTOM = 1


class FakeList:
    """Enough ManagedControlList for the window arithmetic."""

    def __init__(self, n):
        self.items = [object() for _ in range(n)]
        self.pos = 0

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def getSelectedPosition(self):
        return self.pos


class FakeClient:
    def __init__(self):
        self.staged = []

    def stage_pairs(self, items, *fields, include_cdn=False):
        self.staged.extend(items)
        return [("http://remote/%s" % id(it), "/p/%s" % id(it)) for it in items]

    def resolve_image_url(self, path):
        return ("http://server/%s" % path) if path else ""


class FakeWindow:
    """A stand-in `self`: only what _browse_fill_collection_window touches."""

    BROWSE_FILL_WINDOW = main.MainWindow.BROWSE_FILL_WINDOW

    def __init__(self, items):
        self.collection_list = FakeList(len(items))
        self._collection_items = items
        self._collection_filled = set()
        self.applied = []

    def _browse_apply_collection_item(self, client, mli, item):
        self.applied.append(item)
        return mli


def items(n, custom=0):
    made = [{"id": i, "name": "made %d" % i, "_custom": True,
             "poster_path": "/p%d" % i, "backdrop_path": "/b%d" % i}
            for i in range(custom)]
    curated = [{"id": 1000 + i, "name": "coll %d" % i,
                "poster_url": "http://x/p%d" % i, "backdrop_url": "http://x/b%d" % i}
               for i in range(n - custom)]
    return made + curated


#: The window is asymmetric -- half a window behind the selection and a
#: full one ahead (lo = here - W//2, hi = here + W + 1), so a mid-list top-up
#: covers W//2 + W + 1 slots. Inherited from _browse_fill_window, which is
#: the point: one window rule for both grids.
SPAN = main.MainWindow.BROWSE_FILL_WINDOW // 2 + main.MainWindow.BROWSE_FILL_WINDOW + 1

FILL = main.MainWindow._browse_fill_collection_window
prefetched = []
artcache.prefetch = lambda pairs, *a, **k: prefetched.append(list(pairs)) or 0

# --- the window is a window ---------------------------------------------
win = FakeWindow(items(TOTAL, CUSTOM))
client = FakeClient()
FILL(win, client)
built = len(win.applied)
check("opening builds a window, not the whole index",
      built <= SPAN < TOTAL,
      f"built {built} of {TOTAL}")
check("...and stages only that window's art",
      len(client.staged) == built,
      f"staged {len(client.staged)} for {built} tiles")

# --- and it covers what is on screen ------------------------------------
check("the window starts at the selection",
      win.applied[0] is win._collection_items[0]
      and len(win.applied) >= 15,
      "a screenful is ~15 tiles; the window must cover it")

# --- moving tops it up, without redoing work ----------------------------
before = len(win.applied)
win.collection_list.pos = 300
FILL(win, client)
added = len(win.applied) - before
check("moving fills where it landed",
      0 < added <= SPAN,
      f"added {added}, window span is {SPAN}")
check("...and never refills a slot",
      len(win.applied) == len(set(id(i) for i in win.applied)),
      "a filled slot was built twice")

seen = win._collection_filled
check("filled slots are recorded around the new position",
      300 in seen and 299 in seen and 0 in seen)
check("...and far-away slots are still untouched",
      528 not in seen and 150 not in seen)

# --- a second call at rest is free --------------------------------------
before = len(win.applied)
FILL(win, client)
check("a repeat call at the same position does nothing",
      len(win.applied) == before)

# --- the two art families stage separately ------------------------------
prefetched.clear()
win2 = FakeWindow(items(TOTAL, CUSTOM))
c2 = FakeClient()
FILL(win2, c2)
check("custom and curated art stage as separate batches",
      len(prefetched) == 2,
      f"{len(prefetched)} prefetch call(s); custom uses *_path, curated *_url")

# --- an empty index does not raise --------------------------------------
empty = FakeWindow([])
try:
    FILL(empty, FakeClient())
    check("an empty index is a no-op", empty.applied == [])
except Exception as exc:                                    # noqa: BLE001
    check("an empty index is a no-op", False, repr(exc))

# --- the loader must not build cards eagerly ----------------------------
import re  # noqa: E402
SRC = open(os.path.join(ROOT, "plugin.video.tofa", "resources", "lib",
                        "windows", "main.py")).read()
loader = re.search(r"\n    def _browse_load_collections_grid\(.*?\n(.*?)(?=\n    def )",
                   SRC, re.S).group(1)
check("the loader allocates blanks instead of building every tile",
      "_browse_blanks" in loader and "_browse_fill_collection_window" in loader)
check("...and no longer builds a card per collection up front",
      "_browse_build_collection_item(client, it)" not in loader,
      "the eager list comprehension is back")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
