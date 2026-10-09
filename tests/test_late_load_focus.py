"""Late loads must not move focus or the top bar's Down off-screen.

A Browse view's grid loads on a worker: Back before it finished left focus
on the hidden grid. Home's reload, finishing after a move to Browse,
re-aimed the top bar's Down at a hidden Home row.

Run:  python3 test_late_load_focus.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


class FakeWindow:
    _browse_load_source_content = MainWindow._browse_load_source_content
    _browse_close_view = MainWindow._browse_close_view
    TILES_ID = MainWindow.TILES_ID

    def __init__(self, view_open):
        self.props = {"browse_view": "1" if view_open else ""}
        self._browse_focus_after_load = True
        self.focused = []
        self.tiles_list, self._active_source_idx = [], 0

    def getProperty(self, key):
        return self.props.get(key, "")

    def setProperty(self, key, value):
        self.props[key] = value

    def setFocusId(self, control_id):
        self.focused.append(control_id)

    def _browse_start_facets(self):
        return None

    def _browse_load_grid(self):
        pass

    def _browse_finish_facets(self, pending):
        pass

    def _browse_focus_view(self):
        self.setFocusId(6200)

    def _browse_sync_backdrop(self):
        pass


w = FakeWindow(view_open=True)
w._browse_load_source_content()
check("an open view takes focus once loaded", w.focused, [6200])

w = FakeWindow(view_open=False)
w._browse_load_source_content()
check("a view closed while loading leaves focus alone", w.focused, [])

w = FakeWindow(view_open=True)
w._browse_close_view()
check("closing a view drops its pending focus", w._browse_focus_after_load, False)
w._browse_load_source_content()
check("so a late load focuses nothing in it", w.focused, [6020])



class FakeControl:
    def __init__(self, cid):
        self.cid, self.down, self.up = cid, None, None

    def controlDown(self, other):
        self.down = other.cid

    def controlUp(self, other):
        self.up = other.cid


class FakeHome:
    _home_wire_row_nav = MainWindow._home_wire_row_nav
    NAV_LIST_ID = MainWindow.NAV_LIST_ID

    def __init__(self, section):
        self.section, self.controls, self._section_down_targets = section, {}, {}

    def getProperty(self, key):
        return self.section if key == "active_section" else ""

    def getControl(self, cid):
        return self.controls.setdefault(cid, FakeControl(cid))


h = FakeHome("home")
h._home_wire_row_nav([4110, 4130])
check("on Home, the top bar's Down goes to its first row", h.controls[3000].down, 4110)

h = FakeHome("browse")
h._home_wire_row_nav([4110, 4130])
check("on Browse, a late Home load leaves the top bar alone", h.controls[3000].down, None)
check("but still chains Home's rows", (h.controls[4110].down, h.controls[4130].up), (4130, 4110))
check("and remembers Home's entry for later", h._section_down_targets.get("home"), 4110)

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
