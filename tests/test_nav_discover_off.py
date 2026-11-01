"""The bar with the owner's Discover switched off: the tab goes, the rest follow.

Run:  python3 test_nav_discover_off.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import navbar

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Item:
    def __init__(self, idx):
        self.props = {"nav_idx": str(idx)}
    def setProperty(self, key, value):
        self.props[key] = value


class NavList:
    def __init__(self):
        self.items = [Item(i) for i in range(len(navbar.NAV_TABS))]
        self.selected = 3
    def getSelectedPosition(self):
        return self.selected
    def selectItem(self, index):
        self.selected = index
    def removeItem(self, index):
        del self.items[index]
    def getListItem(self, index):
        return self.items[index]


class Window:
    def __init__(self):
        self.nav = NavList()
    def getControl(self, _id):
        return self.nav


win = Window()
navbar.drop_discover(win, 3000)
check("four items left", len(win.nav.items) == 4)
check("the tabs read Home, Browse, Search, Settings",
      [t[0] for t in win._nav_tabs] == ["Home", "Browse", "Search", "Settings"])
check("Search and the gear draw at their moved spots",
      [i.props["nav_idx"] for i in win.nav.items] == ["0", "1", "3p2", "4p3"])
check("the selection stays on the tab it was on", win.nav.selected == 2)
check("a click resolves through the shorter list",
      navbar.resolve_nav_click(win, 3000, "home_window") == "search_window")
navbar.drop_discover(win, 3000)
check("dropping twice changes nothing", len(win.nav.items) == 4)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
