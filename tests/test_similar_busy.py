"""A 503 from the server on a related list means "not ready yet", not "failed".

The server can answer /similar with 503 and Retry-After while it is still
working a list out. Detail asks again rather than showing its error card, and
the client does not re-send that 503 through the relay, which would only
double the wait for the same answer.

Run:  python3 test_similar_busy.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, auth, http  # noqa: E402
from resources.lib.windows import detail  # noqa: E402

import test_similar_empty_retry as base  # noqa: E402

RESULTS = []


def check(name, ok, detail_=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail_) if detail_ and not ok else ""))


BUSY = http.ApiError(503, "service_unavailable", "related titles not ready")
RELAY_DOWN = http.ApiError(503, "server_relay_not_connected", "")
GONE = http.ApiError(0, "connection_error", "down")
FULL, EMPTY = base.FULL, base.EMPTY


def worker():
    base.FakeThread.started[0].target()


def detail_checks():
    detail.threading.Thread = base.FakeThread
    detail.xbmc.Monitor = base.FakeMonitor

    w, client = base.run([BUSY, FULL])
    check("a busy first answer does not show the error card",
          w.getProperty("similar_state") == "", w.getProperty("similar_state"))
    check("...and hands the waiting to a worker", len(base.FakeThread.started) == 1)
    worker()
    check("the next ask fills the shelves", len(w.similar_list.items) == 2)

    w, client = base.run([BUSY] * 9)
    worker()
    check("busy on every ask is asked five times in all", client.asks == 5, str(client.asks))
    check("...and then shows the error card, not 'Nothing similar'",
          w.getProperty("similar_state") == "error", w.getProperty("similar_state"))

    w, client = base.run([BUSY] * 9, part_of=True)
    worker()
    check("...unless a 'Part of' strip is on the page", w.getProperty("similar_state") == "")

    # Still asked again: until the server floor passes the fix, an empty
    # answer cannot be told from a list the server is still working out.
    w, client = base.run([BUSY, EMPTY])
    worker()
    check("an empty answer after a busy one ends on 'Nothing similar'",
          w.getProperty("similar_state") == "empty", w.getProperty("similar_state"))

    w, client = base.run([EMPTY] + [GONE] * 4)
    worker()
    check("a list that could not be asked for at the end shows the error card",
          w.getProperty("similar_state") == "error", w.getProperty("similar_state"))

    w, client = base.run([RELAY_DOWN])
    check("the relay saying the server is gone is a failure at once",
          w.getProperty("similar_state") == "error" and not base.FakeThread.started)


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
