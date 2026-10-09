"""Every tokens.json writer holds the refresh lock while it reads and writes.

A writer working from a stale copy can put back a retired refresh token, and
the cloud revokes the whole login when a retired token is used again.

Run:  python3 test_token_writes_locked.py
"""
import contextlib
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs

from resources.lib import auth

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


TOK = auth.Tokens(server="http://a", server_id="s", connect_url="https://c",
                  access_token="t", refresh_token="r", token_type="Bearer",
                  expires_in=3600, obtained_at=time.time(), device_id="d",
                  profile_token="p")
STATE = {"locked": False, "unlocked_io": []}


@contextlib.contextmanager
def fake_lock():
    STATE["locked"] = True
    try:
        yield
    finally:
        STATE["locked"] = False


def guarded(name):
    def io(*args):
        if not STATE["locked"]:
            STATE["unlocked_io"].append(name)
        return TOK if name == "load" else None
    return io


auth._refresh_lock = fake_lock
auth.load = guarded("load")
auth.save = guarded("save")

for name, call in [
        ("update_server", lambda: auth.update_server("http://b", None)),
        ("save_profile_selection", lambda: auth.save_profile_selection("x", None, None)),
        ("save_rotated_profile_token", lambda: auth.save_rotated_profile_token("q", None)),
        ("save_cloud_refresh_token", lambda: auth.save_cloud_refresh_token("new")),
        ("clear_profile_selection", lambda: auth.clear_profile_selection()),
]:
    STATE["unlocked_io"].clear()
    call()
    check(f"{name} reads and writes under the lock", STATE["unlocked_io"], [])

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
