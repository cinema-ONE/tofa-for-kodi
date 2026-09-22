"""An empty related list on a first visit is asked again before Detail says so.

The server answers /similar empty while it is still working the list out, then
full a moment later (measured 0.15 s to 4.5 s). Detail must not show "Nothing
similar yet" for that first answer, and the waits must not run on the UI thread.

Run:  python3 test_similar_empty_retry.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http  # noqa: E402
from resources.lib.windows import detail  # noqa: E402
from resources.lib.windows.detail import DetailWindow  # noqa: E402

RESULTS = []


def check(name, ok, detail_=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail_) if detail_ and not ok else ""))


FULL = {"owned": [{"id": "a"}, {"id": "b"}], "requestable": [{"tmdb_id": 1}]}
EMPTY = {"owned": [], "requestable": []}


class FakeList:
    def __init__(self):
        self.items = []

    def reset(self):
        self.items = []

    def addItems(self, items):
        self.items += items


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)
        self.asks = 0

    def media_similar(self, media_id):
        self.asks += 1
        answer = self.answers.pop(0) if self.answers else EMPTY
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeThread:
    """Holds the worker so a test can look at the page before it runs."""
    started = []

    def __init__(self, target, name=None, daemon=None):
        self.target = target

    def start(self):
        FakeThread.started.append(self)


class FakeMonitor:
    pauses = []
    on_wait = None

    def waitForAbort(self, t=0):
        FakeMonitor.pauses.append(t)
        if FakeMonitor.on_wait:
            FakeMonitor.on_wait()
        return False


class FakeDetail:
    _render_more_like_this = DetailWindow._render_more_like_this
    _similar_retry = DetailWindow._similar_retry
    _fill_similar = DetailWindow._fill_similar
    SIMILAR_RETRY_S = DetailWindow.SIMILAR_RETRY_S
    MORE_SHELF_IDS = DetailWindow.MORE_SHELF_IDS

    def __init__(self, part_of=False):
        self.props = {}
        self.isOpen = True
        self.similar_list = FakeList()
        self.discover_list = FakeList()
        self.part_of = part_of
        self.wired = []

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, "")

    def _render_collection_strip(self, client, media_id):
        return self.part_of

    def _similar_card(self, client, item):
        return item

    def _wire_more_shelves(self, present):
        self.wired.append(present)


def run(answers, part_of=False):
    FakeThread.started = []
    FakeMonitor.pauses = []
    FakeMonitor.on_wait = None
    w = FakeDetail(part_of)
    client = FakeClient(answers)
    w._render_more_like_this(client, "m1")
    return w, client


def main():
    detail.threading.Thread = FakeThread
    detail.xbmc.Monitor = FakeMonitor

    # --- a full first answer is drawn at once --------------------------------
    w, client = run([FULL])
    check("a full first answer fills the shelves without a worker",
          len(w.similar_list.items) == 2 and not FakeThread.started)
    check("...and the grid is shown", w.getProperty("similar_state") == "")

    # --- an empty first answer is provisional --------------------------------
    w, client = run([EMPTY, FULL])
    check("an empty first answer does not say 'Nothing similar' yet",
          w.getProperty("similar_state") == "", w.getProperty("similar_state"))
    check("...and hands the waiting to a worker, off the UI thread",
          len(FakeThread.started) == 1 and client.asks == 1)
    FakeThread.started[0].target()
    check("the worker's next ask fills the shelves",
          len(w.similar_list.items) == 2 and len(w.discover_list.items) == 1)
    check("...after one short pause", FakeMonitor.pauses == [0.5], str(FakeMonitor.pauses))
    check("...with the shelf titles on and the shelves wired",
          w.getProperty("similar_row_title") == "More Like This"
          and w.wired[-1] == (False, True, True))

    # --- empty every time: then it is the answer -------------------------------
    w, client = run([EMPTY] * 9)
    FakeThread.started[0].target()
    check("an empty list that stays empty is asked five times in all",
          client.asks == 5, str(client.asks))
    check("...over the planned pauses", FakeMonitor.pauses == [0.5, 1, 2, 4],
          str(FakeMonitor.pauses))
    check("...and only then says 'Nothing similar'",
          w.getProperty("similar_state") == "empty")

    w, client = run([EMPTY] * 9, part_of=True)
    FakeThread.started[0].target()
    check("with a 'Part of' strip, the page is not empty after all",
          w.getProperty("similar_state") == "")

    # --- a failed retry is not the answer -------------------------------------
    w, client = run([EMPTY, http.ApiError(0, "connection_error", "down"), FULL])
    FakeThread.started[0].target()
    check("a failed retry keeps asking", client.asks == 3 and len(w.similar_list.items) == 2,
          str(client.asks))

    # --- nothing lands on a page that has moved on ------------------------------
    w, client = run([EMPTY, FULL])
    FakeMonitor.on_wait = lambda: setattr(w, "isOpen", False)
    FakeThread.started[0].target()
    check("a closed page stops asking and is not filled",
          client.asks == 1 and not w.similar_list.items)

    w, client = run([EMPTY, EMPTY, FULL])
    worker = FakeThread.started[0]
    w._render_more_like_this(FakeClient([FULL]), "m1")
    before = list(w.similar_list.items)
    worker.target()
    check("a reload supersedes the older worker",
          client.asks == 1 and w.similar_list.items == before)

    # --- the error card is unchanged -----------------------------------------
    w, client = run([http.ApiError(0, "connection_error", "down")])
    check("a failed first ask still shows the error, and does not retry",
          w.getProperty("similar_state") == "error" and not FakeThread.started)

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
