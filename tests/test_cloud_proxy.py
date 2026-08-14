"""The THIRD way to reach a server: tofa's cloud proxying it.

Found 2026-08-14 against tofa's own demo server, where the two addresses
pairing knew about were both dead ends -- the `<uuid>.connect.tofa.tv` relay
host answered 503 `server_relay_not_connected`, and the LAN address in the
cloud's server entry belonged to somebody else's network. Every screen came
up empty with nothing on it to say why, and Switch Profile did nothing at
all, because listing profiles failed and a picker with no profiles has
nothing to show.

tofa's web app reaches that server perfectly well, by a route this client did
not know: `<connect_url>/servers/<uuid>/relay`, with the ordinary API path
appended. Its own stored descriptor calls it `"type":"proxy"`, so it is a
supported way in rather than a workaround.

Three things have to be true for it to work, and each was broken:

  1. `is_relay_url` must recognise it -- otherwise "Direct connections only"
     waves through the one route where EVERY byte goes via tofa's cloud,
     because the hostname is api.tofa.tv rather than the relay's.
  2. A 503 must be retried against the other address. The old rule listed
     requests' own exception names, so an ANSWER of 503 was never retried
     and the second address sat unused.
  3. Pairing must probe rather than assume: it stored the relay host as
     primary without ever asking whether it answered.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import api, auth, http, signin  # noqa: E402

SID = "7d2a19c4-5e83-4b17-9f60-2c1ab84de905"
CLOUD = "https://api.tofa.tv"
PROXY = "%s/servers/%s/relay" % (CLOUD, SID)
RELAY = "https://%s.connect.tofa.tv:33333" % SID
LAN = "http://192.168.1.50:33333"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def _entry():
    """A cloud `GET /servers` entry, as pairing receives one."""
    return {"id": SID, "name": "Tofa Demo", "connect_url": RELAY,
            "connection": {"local_ip": "192.168.1.50", "port": 33333}}


class _Reach:
    """signin's reachability probe, answering from a fixed set."""
    def __init__(self, working):
        self.working = set(working)
        self.asked = []

    def __enter__(self):
        self._real = signin._reachable

        def fake(session, base, timeout=3.0):
            self.asked.append(base)
            return base in self.working
        signin._reachable = fake
        return self

    def __exit__(self, *exc):
        signin._reachable = self._real


def main() -> int:
    # --- 1. the proxy is a relay, whatever its hostname says ------------
    check("the proxy URL reads as a relay", auth.is_relay_url(PROXY))
    check("...and so does one with a path after it",
          auth.is_relay_url(PROXY + "/api/v1/media"))
    check("the relay HOST still reads as a relay", auth.is_relay_url(RELAY))
    check("a LAN address does not", not auth.is_relay_url(LAN))
    check("the cloud's own root does not -- only its /relay path does",
          not auth.is_relay_url(CLOUD))
    check("nor does another path on it",
          not auth.is_relay_url(CLOUD + "/servers/%s/connection-info" % SID))
    check("proxy_url builds what the web app uses",
          auth.proxy_url(CLOUD, SID) == PROXY, auth.proxy_url(CLOUD, SID))

    # "Direct connections only" has to drop it exactly as it drops the relay
    # host -- this is the case that would otherwise route a viewer who asked
    # for direct-only through tofa's cloud without telling them.
    real = auth.direct_only
    auth.direct_only = lambda: True
    try:
        check("direct-only drops the proxy from the fallback slot",
              api.direct_only_addresses(LAN, PROXY) == (LAN, None))
        check("direct-only prefers the LAN address over a proxy primary",
              api.direct_only_addresses(PROXY, LAN) == (LAN, None))
        check("direct-only leaves nothing direct alone to fall into",
              api.direct_only_addresses(PROXY, RELAY) == (PROXY, None))
    finally:
        auth.direct_only = real

    # --- 2. a 503 is an ANSWER, and has to be retried elsewhere ---------
    check("503 server_relay_not_connected is retried",
          api._worth_retrying(http.ApiError(503, "server_relay_not_connected", "")))
    check("a bare 502/504 gateway failure is retried",
          api._worth_retrying(http.ApiError(504, "gateway_timeout", "")))
    check("a transport failure still is",
          api._worth_retrying(http.ApiError(0, "connection_error", "boom")))
    check("a 404 is NOT -- the server answered and would again",
          not api._worth_retrying(http.ApiError(404, "not_found", "")))
    check("a 401 is NOT",
          not api._worth_retrying(http.ApiError(401, "unauthorized", "")))
    check("a 500 is NOT -- that is a bug, not a wrong address",
          not api._worth_retrying(http.ApiError(500, "internal", "")))

    # --- 3. pairing probes instead of assuming --------------------------
    with _Reach([LAN, RELAY, PROXY]):
        check("all three up: the LAN address wins",
              signin._pick_server_address(None, _entry())[0] == LAN)

    with _Reach([RELAY, PROXY]):
        primary, fallback = signin._pick_server_address(None, _entry())
        check("no LAN: the relay host wins", primary == RELAY)
        check("...with the proxy behind it", fallback == PROXY)

    with _Reach([PROXY]) as probe:
        primary, fallback = signin._pick_server_address(None, _entry())
        check("ONLY the proxy answers: it is stored as primary",
              primary == PROXY, primary)
        check("...and every candidate was actually asked",
              probe.asked == [LAN, RELAY, PROXY], str(probe.asked))

    with _Reach([]):
        primary, fallback = signin._pick_server_address(None, _entry())
        check("nothing answers: the relay is still stored, not invented",
              primary == RELAY, primary)
        check("...and a second address is kept to try later",
              fallback is not None)

    # The demo server's own shape: a LAN address that belongs to someone
    # else's network, and a relay host that is 503.
    with _Reach([PROXY]):
        primary, _ = signin._pick_server_address(None, _entry())
        check("the demo server's real case resolves to the proxy",
              primary == PROXY)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("cloud proxy: the third address is found, retried and gated (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
