"""Home's load never waits on GET /system/info.

That request can take ~2s, and Home loads on the action thread, where every
key onAction handles waits for it. The flags are fetched behind the rows;
Browse and Discover wait for that same fetch instead of asking again.
"""
from __future__ import annotations
import os, sys, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import http  # noqa: E402
from lib.windows import main as main_window  # noqa: E402

MainWindow = main_window.MainWindow
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


class FakeClient:
    """system_info() holds until `release` is set, like a slow server."""

    def __init__(self, version="0.10.0", fail=False):
        self.release = threading.Event()
        self.info_asks = 0
        self.lists_asks = 0
        self.version = version
        self.fail = fail

    def system_info(self):
        self.info_asks += 1
        self.release.wait(10)
        if self.fail:
            raise http.ApiError(500, "internal", "boom")
        return {"version": self.version, "capabilities": ["discovery.page"]}

    def discovery_page(self):
        return {"shelves": [{"key": "trending", "title": "Trending",
                             "items": [{"id": "m1"}]}]}

    def discovery_lists(self):
        self.lists_asks += 1
        return {"lists": [{"list_type": "trending", "items": [{"id": "m2"}]}]}


class FakeItem:
    def __init__(self, source):
        self.dataSource = source


class FakeList:
    def __init__(self):
        self.items = []

    def reset(self):
        self.items = []

    def addItems(self, items):
        self.items += items

    def selectItem(self, idx):
        pass

    def getSelectedItem(self):
        return self.items[0] if self.items else None


class FakeMain:
    ROW_LIST_IDS = MainWindow.ROW_LIST_IDS
    _home_load = MainWindow._home_load
    _home_discovery_shelves = MainWindow._home_discovery_shelves
    _ensure_capabilities = MainWindow._ensure_capabilities
    _start_capabilities = MainWindow._start_capabilities
    _fetch_capabilities = MainWindow._fetch_capabilities
    _has_capability = MainWindow._has_capability

    def __init__(self, client):
        self.client = client
        self.isOpen = True
        self.props = {}
        self.row_lists = {lid: FakeList() for lid in self.ROW_LIST_IDS}
        self._shelf_titles = {}
        self._server_capabilities = set()
        self._capabilities_loaded = False
        self._capabilities_fetch = None
        self._capabilities_lock = threading.Lock()

    def _get_client(self):
        return self.client

    def setProperty(self, key, value):
        self.props[key] = value

    def getFocusId(self):
        return 0

    def _settings_home_screen(self):
        return {"show_hero": True, "rows": [
            {"type": "discovery", "discoveryList": "trending", "enabled": True}]}

    def _home_apply_hero(self, show):
        pass

    def _row_art(self, client, items):
        return []

    def _home_build_row_managed_item(self, client, item, kind):
        return FakeItem(item)

    def _home_update_hero(self, item):
        pass

    def _home_wire_row_nav(self, ids):
        pass


class NoArt:
    @staticmethod
    def prefetch(pairs):
        pass


def main() -> int:
    warned = []
    main_window.artcache = NoArt
    main_window.serverversion.warn_if_old = (
        lambda version, **kw: warned.append(version))

    # --- Home returns while the flags are still being fetched --------------
    client = FakeClient()
    win = FakeMain(client)
    started = time.monotonic()
    win._home_load()
    took = time.monotonic() - started
    check("Home's load returns without waiting for /system/info",
          took < 1.0, "took %.2fs" % took)
    first = win.row_lists[win.ROW_LIST_IDS[0]]
    check("...with its discovery row drawn from the page",
          [i.dataSource["id"] for i in first.items] == ["m1"]
          and win.props.get("row0_title") == "Trending",
          "items=%r props=%r" % (first.items, win.props))
    check("...and the flags fetch running behind it",
          wait_until(lambda: client.info_asks == 1)
          and not win._capabilities_loaded)

    # --- Browse waits for THAT fetch rather than asking again -------------
    answer = []
    browse = threading.Thread(
        target=lambda: answer.append(win._has_capability("discovery.page")))
    browse.start()
    time.sleep(0.1)
    check("a lazy caller waits while the fetch is in flight",
          browse.is_alive() and not answer)
    client.release.set()
    browse.join(5)
    check("...then reads the flags from it", answer == [True], repr(answer))
    check("...which was the only /system/info request",
          client.info_asks == 1, "asks=%d" % client.info_asks)
    check("the version check ran once, on that response",
          warned == ["0.10.0"], repr(warned))

    # --- a window closed mid-fetch raises no alert -------------------------
    warned.clear()
    client = FakeClient(version="0.9.20")
    win = FakeMain(client)
    fetch = win._start_capabilities(client)
    win.isOpen = False
    client.release.set()
    fetch.join(5)
    check("no version alert once the window has closed",
          win._capabilities_loaded and warned == [], repr(warned))

    # --- a failed fetch is asked again next time ---------------------------
    client = FakeClient(fail=True)
    client.release.set()
    win = FakeMain(client)
    win._ensure_capabilities()
    check("a failed fetch leaves the flags unloaded",
          not win._capabilities_loaded and client.info_asks == 1)
    client.fail = False
    win._ensure_capabilities()
    check("...and the next caller asks again",
          win._capabilities_loaded and client.info_asks == 2,
          "asks=%d" % client.info_asks)

    # --- a server without the page still gets its discovery rows ----------
    client = FakeClient()
    win = FakeMain(client)
    win._capabilities_loaded = True
    shelves = win._home_discovery_shelves(client)
    check("known-absent discovery.page falls back to the 7 lists",
          client.lists_asks == 1
          and shelves["trending"]["items"] == [{"id": "m2"}])

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("capabilities: fetched off the action thread (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
