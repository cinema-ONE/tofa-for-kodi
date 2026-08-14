"""An account with NO accent set wears the DEFAULT one, not the last one.

The bug this guards, found on tofa's demo server 2026-08-14: that account
sets no `accent_color`, and the whole app -- nav, pills, progress bars, and
the tofa fox itself -- came up in the amber left behind by a completely
different server on a different network, paired hours earlier.

The cause was one return value doing two jobs. `_fetch_server_accent_hex`
answered None both for "could not ask" (signed out, network down) and for
"asked, and this account has no preference". The first has to keep the local
setting, which is the offline fallback and what the splash wears. The second
must not: the local setting is the LAST ACCOUNT'S colour, and a colour that
survives a re-pair to an unrelated account is a leak, not a fallback.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import theme  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class _Server:
    """What whoami() answers, or an exception standing in for a dead link."""
    def __init__(self, me):
        self.me = me

    def __enter__(self):
        from lib import api, auth, http
        self._real = (api.client_for, auth.ensure_fresh, http.new_session)
        me = self.me

        class _Client:
            def whoami(self):
                if isinstance(me, Exception):
                    raise me
                return me

        http.new_session = lambda *a, **k: None
        auth.ensure_fresh = lambda *a, **k: object()
        api.client_for = lambda *a, **k: _Client()
        theme.reset_cache()
        return self

    def __exit__(self, *exc):
        from lib import api, auth, http
        api.client_for, auth.ensure_fresh, http.new_session = self._real
        theme.reset_cache()


def main() -> int:
    DEFAULT = theme.DEFAULT_ACCENT

    with _Server({"preferences": {"accent_color": "F472B6"}}):
        check("an account WITH an accent gets its own",
              theme._fetch_server_accent_hex() == "F472B6")

    with _Server({"preferences": {}}):
        check("an account with NO accent gets the default, not None",
              theme._fetch_server_accent_hex() == DEFAULT,
              str(theme._fetch_server_accent_hex()))

    with _Server({}):
        check("...and so does one with no preferences blob at all",
              theme._fetch_server_accent_hex() == DEFAULT)

    with _Server({"preferences": {"accent_color": ""}}):
        check("...and one whose accent is an empty string",
              theme._fetch_server_accent_hex() == DEFAULT)

    # The other half: a failure must NOT masquerade as "no preference", or
    # every offline start would repaint the app default and the splash would
    # lose the fox it is supposed to remember.
    with _Server(RuntimeError("network down")):
        check("a FAILED fetch still answers None, keeping the local colour",
              theme._fetch_server_accent_hex() is None)

    with _Server(None):
        check("a whoami that answers nothing at all is a failure, not a default",
              theme._fetch_server_accent_hex() is None)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("accent: no preference means DEFAULT, a failure means keep (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
