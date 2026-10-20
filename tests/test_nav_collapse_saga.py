"""The top bar stays over Continue the saga under Continue Watching (app 2.1.0).

Run:  python3 test_nav_collapse_saga.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


class Fake:
    _sync_nav_collapse = MainWindow._sync_nav_collapse
    ROW_LIST_IDS = (4110, 4130, 4150)
    DISCOVER_ROW_LIST_IDS = (7000, 7010)
    SEARCH_RESULT_LIST_IDS = ()

    def __init__(self, row1_kind, cw=4110):
        self.props = {"active_section": "home", "row1_kind": row1_kind}
        self._cw_list_id = cw

    def getProperty(self, k):
        return self.props.get(k, "")

    def setProperty(self, k, v):
        self.props[k] = v


def collapsed(w, cid):
    w._sync_nav_collapse(cid)
    return w.props["nav_collapsed"] == "1"


saga = Fake("saga")
check("Continue Watching keeps the bar", not collapsed(saga, 4110))
check("so does the saga row under it", not collapsed(saga, 4130))
check("the next row collapses it", collapsed(saga, 4150))
plain = Fake("")
check("without a saga row, the second row collapses it, as before", collapsed(plain, 4130))
no_cw = Fake("saga", cw=None)
check("a saga row first on Home is the first row only", collapsed(no_cw, 4130))
disc = Fake("saga")
disc.props["active_section"] = "discover"
check("Discover keeps its own rule", collapsed(disc, 7010) and not collapsed(disc, 7000))

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
