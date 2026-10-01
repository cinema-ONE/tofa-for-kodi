"""A related list the server is still working out is asked for again.

The server answers /similar with 503 and Retry-After while a list is not ready,
and an empty 200 is final (vault #222). Detail asks again rather than showing
its error card, off the UI thread, and the client does not re-send that 503
through the relay, which would only double the wait for the same answer.

Run:  python3 test_similar_busy.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, auth, http  # noqa: E402
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


BUSY = http.ApiError(503, "service_unavailable", "related titles not ready")
RELAY_DOWN = http.ApiError(503, "server_relay_not_connected", "")
GONE = http.ApiError(0, "connection_error", "down")


def worker():
    FakeThread.started[0].target()


def detail_checks():
    detail.threading.Thread = FakeThread
    detail.xbmc.Monitor = FakeMonitor

    w, client = run([FULL])
    check("a full first answer fills the shelves without a worker",
          len(w.similar_list.items) == 2 and not FakeThread.started)
    check("...and the grid is shown", w.getProperty("similar_state") == "")

    w, client = run([EMPTY])
    check("an empty first answer is final: 'Nothing similar' at once, no worker",
          w.getProperty("similar_state") == "empty" and not FakeThread.started)

    w, client = run([BUSY, FULL])
    check("a busy first answer does not show the error card",
          w.getProperty("similar_state") == "", w.getProperty("similar_state"))
    check("...and hands the waiting to a worker", len(FakeThread.started) == 1)
    worker()
    check("the next ask fills the shelves",
          len(w.similar_list.items) == 2 and len(w.discover_list.items) == 1)
    check("...after one short pause", FakeMonitor.pauses == [0.5], str(FakeMonitor.pauses))
    check("...with the shelf titles on and the shelves wired",
          w.getProperty("similar_row_title") == "More Like This"
          and w.wired[-1] == (False, True, True))

    w, client = run([BUSY] * 9)
    worker()
    check("busy on every ask is asked five times in all", client.asks == 5, str(client.asks))
    check("...over the planned pauses", FakeMonitor.pauses == [0.5, 1, 2, 4],
          str(FakeMonitor.pauses))
    check("...and then shows the error card, not 'Nothing similar'",
          w.getProperty("similar_state") == "error", w.getProperty("similar_state"))

    w, client = run([BUSY] * 9, part_of=True)
    worker()
    check("...unless a 'Part of' strip is on the page", w.getProperty("similar_state") == "")

    w, client = run([BUSY, EMPTY])
    worker()
    check("an empty answer after a busy one ends on 'Nothing similar'",
          w.getProperty("similar_state") == "empty" and client.asks == 2,
          w.getProperty("similar_state"))

    w, client = run([BUSY, GONE, FULL])
    worker()
    check("a failed retry keeps asking", client.asks == 3 and len(w.similar_list.items) == 2,
          str(client.asks))

    w, client = run([BUSY] + [GONE] * 4)
    worker()
    check("a list that could not be asked for at the end shows the error card",
          w.getProperty("similar_state") == "error", w.getProperty("similar_state"))

    w, client = run([BUSY, FULL])
    FakeMonitor.on_wait = lambda: setattr(w, "isOpen", False)
    worker()
    check("a closed page stops asking and is not filled",
          client.asks == 1 and not w.similar_list.items)

    w, client = run([BUSY, BUSY, FULL])
    stale = FakeThread.started[0]
    w._render_more_like_this(FakeClient([FULL]), "m1")
    before = list(w.similar_list.items)
    stale.target()
    check("a reload supersedes the older worker",
          client.asks == 1 and w.similar_list.items == before)

    w, client = run([GONE])
    check("a failed first ask shows the error, and does not retry",
          w.getProperty("similar_state") == "error" and not FakeThread.started)

    w, client = run([RELAY_DOWN])
    check("the relay saying the server is gone is a failure at once",
          w.getProperty("similar_state") == "error" and not FakeThread.started)


class Recorder:
    """Stands in for http.request_response: fails as told, per address."""

    def __init__(self, answers):
        self.answers, self.hosts = answers, []

    def __call__(self, session, method, url, **kwargs):
        host = url.split("/api/")[0]
        self.hosts.append(host)
        answer = self.answers[host]
        if isinstance(answer, Exception):
            raise answer
        return answer


def client_checks():
    auth.direct_only = lambda: False
    # A fallback that works makes the relay the main address AND saves it;
    # neither may leak out of this test.
    auth.update_server = lambda *a, **k: None
    http.body_of = lambda resp: resp
    c = api.MediaServerClient.__new__(api.MediaServerClient)
    c.session, c.base_url, c.fallback_base_url = None, "http://lan", "https://relay"
    c._headers = lambda: {}

    def ask(primary, busy_is_final):
        c.base_url, c.fallback_base_url = "http://lan", "https://relay"
        rec = Recorder({"http://lan": primary, "https://relay": FULL})
        http.request_response = rec
        try:
            c._attempt("GET", "/api/v1/media/m1/similar", {}, False, True,
                       busy_is_final=busy_is_final)
        except http.ApiError:
            pass
        return rec.hosts

    check("the server's own 503 stays off the relay for a caller that asks again",
          ask(BUSY, True) == ["http://lan"], str(ask(BUSY, True)))
    check("...while the relay saying the server is gone still falls back",
          ask(RELAY_DOWN, True) == ["http://lan", "https://relay"])
    check("...and so does an address that does not answer",
          ask(GONE, True) == ["http://lan", "https://relay"])
    check("every other caller keeps the fallback on a 503",
          ask(BUSY, False) == ["http://lan", "https://relay"])
    ask(BUSY, True)
    check("...and a busy related list leaves the main address alone",
          c.base_url == "http://lan", c.base_url)
    check("media_similar is such a caller",
          'busy_is_final=True' in open(api.__file__).read().split("def media_similar")[1][:400])


def main():
    detail_checks()
    client_checks()
    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
