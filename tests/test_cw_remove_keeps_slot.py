"""Remove from Continue Watching keeps the slot; the next title slides in.

Both destructive entries in the card menu change what the Continue Watching
row holds, and they used to disagree about what that costs the viewer:

  * Mark as Watched refreshed the ROW, kept the cursor's index, and let the
    promoted episode arrive under it.
  * Remove from Continue Watching called _home_load(), which rebuilds every
    shelf on Home and drops the viewer back on the first card of the first
    row -- a long way from the card they had just dismissed. Reported from
    the box 2026-09-01: "the row is refreshed, but the first title is
    focused".

They now take the same route. The index is what is kept, not the item: the
card at this position is deliberately a DIFFERENT one afterwards, which is
the whole point of the row closing up.

Run:  python3 test_cw_remove_keeps_slot.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs

from resources.lib.windows import main as mainwin              # noqa: E402
from resources.lib.windows.main import MainWindow              # noqa: E402
from resources.lib.windows import cardoptions                  # noqa: E402

# The row's art is staged for real inside _home_refresh_cw_row; nothing here
# has a server to stage from.
mainwin.artcache.prefetch = lambda pairs: None

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Item:
    def __init__(self, data): self.dataSource = data
    def getProperty(self, _k): return ""
    def setProperty(self, _k, _v): pass
    def getLabel(self): return (self.dataSource or {}).get("title", "")


class FakeList(list):
    """A ManagedControlList's selection surface, and Kodi's own rule that
    addItems() on a FOCUSED container resets the selection to 0 -- which is
    exactly what the explicit selectItem() afterwards is there to undo."""
    def __init__(self, items):
        super().__init__(items)
        self.pos = 0
    def getSelectedPos(self): return self.pos
    def getSelectedItem(self): return self[self.pos] if self else None
    def selectItem(self, index): self.pos = index
    def reset(self):
        del self[:]
        self.pos = 0
    def addItems(self, items):
        self.extend(items)
        self.pos = 0


class Client:
    def __init__(self): self.dismissed = []
    def dismiss_media(self, media_id): self.dismissed.append(media_id)


class Home:
    """Just enough of MainWindow to run the two REAL methods under test."""

    CW_ID = 5001

    _apply_card_option = MainWindow._apply_card_option
    _home_refresh_cw_row = MainWindow._home_refresh_cw_row

    def __init__(self, titles, selected):
        self.server_rows = [{"media_id": t, "title": t} for t in titles]
        self._cw_list_id = self.CW_ID
        self.row_lists = {self.CW_ID: FakeList(
            [Item(d) for d in self.server_rows])}
        self.row_lists[self.CW_ID].pos = selected
        self.full_reloads = 0
        self.heroes = []
        self.focus = self.CW_ID

    # -- what the server answers next time it is asked -------------------
    def _home_fetch_builtin_row(self, _client, _row_id):
        return list(self.server_rows)

    # -- the surface the two methods touch -------------------------------
    def _home_load(self): self.full_reloads += 1
    def _row_art(self, _client, _items): return []
    def _home_build_row_managed_item(self, _client, item, _kind): return Item(item)
    def _home_update_hero(self, data): self.heroes.append(data)
    def getFocusId(self): return self.focus
    def open_detail(self, **kw): pass

    # -- the dismissal itself, as the server would answer it --------------
    def dismiss(self, client, media_id):
        """Run the real menu handler for Remove from Continue Watching."""
        self.server_rows = [r for r in self.server_rows
                            if r["media_id"] != media_id]
        item = self.row_lists[self.CW_ID].getSelectedItem()
        self._apply_card_option(cardoptions.REMOVE_FROM_CW, client,
                                item.dataSource, item, "cw")

    @property
    def titles(self):
        return [(i.dataSource or {}).get("title")
                for i in self.row_lists[self.CW_ID]]

    @property
    def focused_title(self):
        sel = self.row_lists[self.CW_ID].getSelectedItem()
        return (sel.dataSource or {}).get("title") if sel else None


ROW = ["Andor", "Severance", "The Bear", "Shogun", "Fallout"]

# --- the reported bug ---------------------------------------------------
h, c = Home(ROW, selected=2), Client()
h.dismiss(c, "The Bear")
check("the dismissal reaches the server", c.dismissed == ["The Bear"])
check("the card is gone from the row", "The Bear" not in h.titles)
check("Home is NOT rebuilt wholesale", h.full_reloads == 0,
      "_home_load() drops the viewer on the first card of the first row")
check("the cursor holds slot 2", h.row_lists[h.CW_ID].getSelectedPos() == 2)
check("...and the next title has slid into it",
      h.focused_title == "Shogun",
      f"focused {h.focused_title!r}")
check("the hero follows the card now under the cursor",
      h.heroes and h.heroes[-1].get("title") == "Shogun")

# --- the first card, which is what the old route always landed on -------
h, c = Home(ROW, selected=0), Client()
h.dismiss(c, "Andor")
check("dismissing the FIRST card promotes the second into slot 0",
      h.focused_title == "Severance" and h.row_lists[h.CW_ID].getSelectedPos() == 0)

# --- the last card: nothing slides in, so the row has to give ground ----
h, c = Home(ROW, selected=4), Client()
h.dismiss(c, "Fallout")
check("dismissing the LAST card steps back to the new last one",
      h.focused_title == "Shogun",
      f"focused {h.focused_title!r}; an unclamped index runs off the end")
check("...and still does not rebuild Home", h.full_reloads == 0)

# --- the row emptying is the one case that DOES need the full load ------
h, c = Home(["Andor"], selected=0), Client()
h.dismiss(c, "Andor")
check("dismissing the only card falls back to the full reload",
      h.full_reloads == 1,
      "an empty row has to hide its header and re-point the nav chain")

# --- a card that is NOT on Continue Watching is untouched by this -------
h, c = Home(ROW, selected=1), Client()
item = h.row_lists[h.CW_ID].getSelectedItem()
h._apply_card_option(cardoptions.REMOVE_FROM_CW, c, item.dataSource, item, "home")
check("an ordinary Home row still takes the full reload",
      h.full_reloads == 1,
      "only the Continue Watching row has a single-row refresh")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
