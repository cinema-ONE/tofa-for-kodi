# -*- coding: utf-8 -*-
"""The server slides a locked profile's unlock while viewing continues.

The other half of test_expired_profile_token: that suite proves an expired
token is never read as "nothing has been watched", and this one proves the
token stops expiring mid-film in the first place.

Server 0.9.30. When a heartbeat to /stream/s/{id}/progress carries an
`X-Profile-Token` nearing expiry, the 204 answers with a replacement in
`X-Profile-Token` and its RFC 3339 expiry in `X-Profile-Token-Expires-At`.
The sliding is bounded rather than endless -- a session long enough still
meets the PIN pad again -- and the headers are absent otherwise.

What blocked us until now was on OUR side: `http.request_json` returned
`resp.json()`, so the headers were gone before any caller could look. Hence
`request_response`/`body_of` and `want_response=True`, which this also
covers -- a heartbeat still has to behave like a heartbeat.

Run:  python3 test_sliding_profile_token.py
"""
import datetime

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, auth, http

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}"
          f"{('  -- ' + detail) if detail and not ok else ''}")


class Response:
    """Enough of requests.Response for the code under test."""

    def __init__(self, status=204, headers=None, content=b""):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.ok = status < 400

    def json(self):
        import json
        return json.loads(self.content)


class Session:
    def __init__(self, response):
        self.response = response
        self.sent = []

    def request(self, method, url, **kwargs):
        self.sent.append((method, url, kwargs))
        return self.response


def client(session, **over):
    kwargs = dict(base_url="http://server", access_token="bearer",
                  device_id="dev", profile_id="p1",
                  profile_token="old-token")
    kwargs.update(over)
    return api.MediaServerClient(session, **kwargs)


def banked():
    """Patch auth so the test never touches a real tokens.json."""
    calls = []
    real = auth.save_rotated_profile_token
    auth.save_rotated_profile_token = lambda t, e: calls.append((t, e))
    return calls, (lambda: setattr(auth, "save_rotated_profile_token", real))


# --- the timestamp parser, which has to cope with more than one spelling
epoch = api._rfc3339_epoch
z = epoch("2026-08-15T12:34:56Z")
offset = epoch("2026-08-15T14:34:56+02:00")
check("an RFC 3339 Z timestamp parses", z is not None)
check("...and an offset one means the same instant", z == offset,
      f"{z} != {offset}")
check("a missing expiry is None, not an exception", epoch(None) is None)
check("an unparseable expiry is None, not a guess",
      epoch("next tuesday") is None and epoch("") is None)

# --- the rotation itself
calls, restore = banked()
try:
    resp = Response(headers={"X-Profile-Token": "new-token",
                             "X-Profile-Token-Expires-At":
                                 "2026-08-15T12:34:56Z"})
    session = Session(resp)
    c = client(session)
    body = c.report_progress("sess", "st", 60_000, is_paused=False)

    check("a heartbeat still answers its body, not the response",
          body is None, repr(body))
    check("the rotated token is adopted in memory",
          c.profile_token == "new-token", c.profile_token)
    check("...and banked to disk once", len(calls) == 1, str(calls))
    check("...with the expiry parsed, not the raw string",
          calls and isinstance(calls[0][1], float), str(calls))

    # The request half was already right, but it is the thing that triggers
    # rotation at all -- if it stopped being sent, this would silently never
    # rotate again and nothing else would fail.
    _method, _url, kwargs = session.sent[0]
    check("the heartbeat carried the CURRENT profile token",
          kwargs.get("headers", {}).get("X-Profile-Token") == "old-token",
          str(kwargs.get("headers")))
    check("...and the position in TICKS, unchanged by any of this",
          kwargs.get("json", {}).get("position_ticks") == 600_000_000,
          str(kwargs.get("json")))
finally:
    restore()

# --- the common case: no rotation, nothing touched
calls, restore = banked()
try:
    c = client(Session(Response()))
    c.report_progress("sess", "st", 1000, is_paused=False)
    check("a heartbeat with no rotation banks nothing", not calls, str(calls))
    check("...and leaves the held token alone", c.profile_token == "old-token")
finally:
    restore()

# --- a rotation that cannot be stored must not break the heartbeat
calls, restore = banked()
try:
    def explode(_t, _e):
        raise OSError("disk full")
    auth.save_rotated_profile_token = explode
    c = client(Session(Response(headers={"X-Profile-Token": "new-token"})))
    try:
        c.report_progress("sess", "st", 1000, is_paused=False)
        ok = True
    except Exception:                                        # noqa: BLE001
        ok = False
    check("a heartbeat survives a failed bank", ok)
finally:
    restore()

# --- an expiry we cannot read is stored as unknown rather than as a guess
calls, restore = banked()
try:
    c = client(Session(Response(headers={"X-Profile-Token": "new-token",
                                         "X-Profile-Token-Expires-At": "??"})))
    c.report_progress("sess", "st", 1000, is_paused=False)
    check("an unreadable expiry banks None, and the token still lands",
          calls == [("new-token", None)], str(calls))
finally:
    restore()

# --- body_of, the seam that made the headers reachable
check("body_of answers None for an empty 204",
      http.body_of(Response()) is None)
check("body_of decodes a real body",
      http.body_of(Response(status=200, content=b'{"a": 1}')) == {"a": 1})

# --- auth refuses a rotation when no profile is unlocked
saved = []
real_load, real_save = auth.load, auth.save
try:
    class Tok:
        profile_token = None
    auth.load = lambda: Tok()
    auth.save = lambda t: saved.append(t)
    auth.save_rotated_profile_token("x", 1.0)
    check("a rotation for a profile we do not hold is ignored", not saved,
          str(saved))
finally:
    auth.load, auth.save = real_load, real_save

print()
failed = [n for n, ok in RESULTS if not ok]
if failed:
    print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
    raise SystemExit(1)
print("sliding profile token: the unlock follows the viewing (%d checks)"
      % len(RESULTS))
