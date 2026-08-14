"""Checks that "Direct connections only" actually refuses the relay.

The bug this guards is a setting that looks honoured and is not. The first
cut gated only the FALLBACK, which is the relay in the ordinary case --
pairing probes the LAN address and stores `(local, remote)` when it answers.
But when the LAN address does NOT answer at pairing time the order flips
(signin._pick_server_address), the relay becomes the PRIMARY, and a
fallback-only gate guards nothing at all: every call already goes through the
address it was meant to refuse.

So the cases that matter are the ones where the relay is first.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import api, auth  # noqa: E402

RELAY = "https://7d2a19c4-5e83-4b17-9f60-2c1ab84de905.connect.tofa.tv:33333"
LAN = "http://192.168.1.50:33333"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class _Flag:
    """auth.direct_only(), swapped for a value this test controls."""
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._real = auth.direct_only
        auth.direct_only = lambda: self.value
        return self

    def __exit__(self, *exc):
        auth.direct_only = self._real


def main() -> int:
    # --- the detector itself ------------------------------------------
    check("a connect.tofa.tv host is the relay", auth.is_relay_url(RELAY) is True)
    check("a LAN address is not", auth.is_relay_url(LAN) is False)
    check("an empty address is not", auth.is_relay_url("") is False)
    check("None is not", auth.is_relay_url(None) is False)
    check("case is ignored",
          auth.is_relay_url(RELAY.upper().replace("HTTPS", "https")) is True)

    # --- address selection, the part that was missing ------------------
    with _Flag(False):
        check("off: addresses are left exactly as paired",
              api.direct_only_addresses(RELAY, LAN) == (RELAY, LAN))

    with _Flag(True):
        # THE case this test exists for: relay first, LAN second.
        check("on: a relay PRIMARY is replaced by the direct fallback",
              api.direct_only_addresses(RELAY, LAN) == (LAN, None))
        # The ordinary case: LAN first, relay as fallback.
        check("on: a relay fallback is dropped, not merely refused",
              api.direct_only_addresses(LAN, RELAY) == (LAN, None))
        # Two direct addresses are both fine and both kept.
        check("on: two direct addresses are untouched",
              api.direct_only_addresses(LAN, "http://10.0.0.5:33333")
              == (LAN, "http://10.0.0.5:33333"))
        # Nothing direct exists. Both come back; _request does the refusing.
        check("on: relay-only is left for _request to refuse",
              api.direct_only_addresses(RELAY, None) == (RELAY, None))
        check("on: no fallback at all is fine",
              api.direct_only_addresses(LAN, None) == (LAN, None))

    # --- and _request refuses it rather than quietly using it ----------
    with _Flag(True):
        client = api.MediaServerClient(None, RELAY, "token", "device")
        try:
            client._request("GET", "/api/v1/users/me")
        except Exception as exc:                             # noqa: BLE001
            code = getattr(exc, "error", "")
            check("on: a relay-only client refuses the call",
                  code == "direct_only", "raised %r" % (code or exc))
        else:
            check("on: a relay-only client refuses the call", False,
                  "the call was attempted")

    with _Flag(False):
        # The same client must NOT refuse when the setting is off -- it
        # should get as far as trying (and fail on the stub session).
        client = api.MediaServerClient(None, RELAY, "token", "device")
        try:
            client._request("GET", "/api/v1/users/me")
        except Exception as exc:                             # noqa: BLE001
            check("off: the relay is used, not refused",
                  getattr(exc, "error", "") != "direct_only",
                  "refused with direct_only while the setting was off")
        else:
            check("off: the relay is used, not refused", True)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("direct connections only: the relay is refused as primary too (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
