"""A pooled connection that has been idle too long must be dropped, not used.

The tofa server closes an idle keep-alive connection after 40 seconds
(`keep-alive: timeout=40`). urllib3 discards a pooled connection it can SEE
has been closed, so a clean close is harmless. One that died silently -- a
Wi-Fi path that dropped the flow, a NAT entry that expired -- is not: the
request goes into a dead socket and waits out the full 15s timeout.

Reproduced against a loopback server that keep-alives the first request and
then black-holes the second on the same connection: 15.01s, one TCP
connection, reused. With the guard: 0.003s and a second connection opened.

**Scope, recorded because it was got wrong once.** This guards only the
sessions that outlive a single action -- artcache's, monitor's and
service.py's. Every WINDOW builds a fresh session per action, so no screen
is protected by this and none needed to be. It was written believing it
fixed a Detail page that came up empty after a break on 2026-08-21; that
page had a brand-new session, so this was never the cause. Verified by
reading the call sites and by watching a box idle 110s without the guard
firing.

The loopback repro needs a real `requests`, which `tests/kodi_stubs.py`
deliberately stubs as a `SimpleNamespace` with no pooling -- so no suite in
the harness can exercise real sockets. What is checked here is the part that
can regress: WHEN the pool is dropped, against a fake session, with
`http._now` as the clock seam.

Run:  python3 test_stale_pool_reset.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import http  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s %s%s" % ("ok  " if ok else "FAIL", name,
                       "" if ok else "   <- %s" % detail))


class FakeSession:
    """Stands in for a requests.Session: counts close(), records requests.

    A plain class so it is hashable and weak-referenceable, which is what
    http._LAST_USED needs of a key.
    """

    def __init__(self):
        self.headers = {}
        self.closed = 0
        self.requests = 0
        self.fail_with = None

    def close(self):
        self.closed += 1

    def request(self, *a, **k):
        self.requests += 1
        if self.fail_with is not None:
            raise self.fail_with
        return _Resp()


class _Resp:
    ok = True
    status_code = 200
    content = b""
    headers = {}


class _Clock:
    """Drives http's idea of now, so an idle gap costs no wall-clock."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def main():
    clock = _Clock()
    real_now = http._now
    http._now = clock

    LIMIT = http.IDLE_POOL_LIMIT_SECONDS
    try:
        # --- the reported case -------------------------------------------
        s = FakeSession()
        http.request_response(s, "GET", "http://server/api/v1/media/x")
        check("a first request opens a connection and closes nothing",
              s.closed == 0 and s.requests == 1,
              "closed=%d requests=%d" % (s.closed, s.requests))

        clock.advance(12 * 60)          # the break, as reported
        http.request_response(s, "GET", "http://server/api/v1/media/x")
        check("after a 12-minute break the pool is dropped first",
              s.closed == 1, "closed=%d" % s.closed)
        check("...and the request still goes out, on a fresh connection",
              s.requests == 2, "requests=%d" % s.requests)

        # --- a busy session must not be disturbed -------------------------
        s = FakeSession()
        for _ in range(5):
            clock.advance(LIMIT / 2)
            http.request_response(s, "GET", "http://server/api/v1/media/x")
        check("back-to-back requests inside the window keep their connection",
              s.closed == 0, "closed=%d" % s.closed)

        # --- the boundary --------------------------------------------------
        s = FakeSession()
        http.request_response(s, "GET", "http://server/x")
        clock.advance(LIMIT - 1)
        http.request_response(s, "GET", "http://server/x")
        check("one second inside the limit is not stale", s.closed == 0,
              "closed=%d" % s.closed)
        clock.advance(LIMIT + 1)
        http.request_response(s, "GET", "http://server/x")
        check("one second past it is", s.closed == 1, "closed=%d" % s.closed)

        # The server says `keep-alive: timeout=40`, so the limit has to sit
        # under it or the drop happens after the socket is already dead.
        check("the limit stays under the server's 40s keep-alive window",
              LIMIT < 40, "%.0fs" % LIMIT)

        # --- the clock moves on a FAILED request too -----------------------
        # Otherwise a failure inside the window leaves last-used stale, and
        # the retry right behind it needlessly drops a live pool.
        s = FakeSession()
        http.request_response(s, "GET", "http://server/x")
        clock.advance(1)
        s.fail_with = http.requests.RequestException("boom")
        try:
            http.request_response(s, "GET", "http://server/x")
        except http.ApiError:
            pass
        s.fail_with = None
        clock.advance(1)
        http.request_response(s, "GET", "http://server/x")
        check("a failed request still moves the idle clock", s.closed == 0,
              "closed=%d" % s.closed)

        # --- artwork goes through the other door ---------------------------
        s = FakeSession()
        http.raw_range_request(s, "http://server/image/x.jpg")
        clock.advance(12 * 60)
        http.raw_range_request(s, "http://server/image/x.jpg")
        check("range requests get the same guard (artwork after a still screen)",
              s.closed == 1, "closed=%d" % s.closed)

        # --- sessions are tracked apart ------------------------------------
        a, b = FakeSession(), FakeSession()
        http.request_response(a, "GET", "http://server/x")
        clock.advance(12 * 60)
        http.request_response(b, "GET", "http://server/x")
        check("a fresh session is not punished for another one's idle time",
              b.closed == 0, "closed=%d" % b.closed)
    finally:
        http._now = real_now

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("stale pool: an idle connection is dropped before it can hang "
          "(%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
