"""Server 0.9.30 slides a locked profile's unlock by ROTATING its token. A
rotation invalidates the token it replaced, so every client still holding the
old one starts failing while the unlock is perfectly alive.

The incident (LibreELEC NUC, 2026-08-28, add-on 0.9.18): the heartbeat banked
rotations at 16:58:52 and 19:58:55, both logged as "profile token rotated by
the server, unlock slid". Between them, at 18:06:29 -- an hour and a half
INSIDE the token's validity -- the episode-changeover writes failed:

    player: could not finish outgoing episode: ApiError('HTTP 401 ...
      Invalid or expired profile token')
    player: could not write outgoing progress: ApiError('HTTP 401 ...')

Nothing had expired. PlayerWindow builds its client once in `_get_client` and
keeps it for the life of the window, so a binge outlives its own token: the
heartbeat's client (rebuilt per beat off tokens.json) had moved on, and the
player's had not.

The fix is one retry against whatever is on disk. What is tested here:

  1. a profile-token 401 is retried ONCE with the token another component
     banked, and the caller never sees the failure,
  2. the retry is not a loop -- when disk holds the same token, the 401
     stands,
  3. an ACCOUNT 401 is not swallowed by it, and
  4. a rotation seen in a heartbeat's response headers is still absorbed
     into the client that made it (the other half, from 0.9.19).

Run:  python3 test_rotated_profile_token_adoption.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, http

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Tokens:
    server = "http://server"
    server_fallback = None
    access_token = "bearer"
    device_id = "dev"
    profile_id = "p1"
    profile_token = "OLD"
    profile_token_expires_at = 4e9


def client(profile_token="OLD"):
    tok = Tokens()
    tok.profile_token = profile_token
    return api.client_for(None, tok)


class Server:
    """Refuses everything but `good`, and records the tokens it was shown."""

    def __init__(self, good="NEW", error="Invalid or expired profile token",
                 status=401):
        self.good = good
        self.error = error
        self.status = status
        self.seen = []

    def __call__(self, session, method, url, **kwargs):
        shown = (kwargs.get("headers") or {}).get("X-Profile-Token")
        self.seen.append(shown)
        if shown != self.good:
            raise http.ApiError(self.status, "unauthorized", self.error)
        return Response()


class Response:
    headers = {}
    content = b"{}"

    def json(self):
        return {"ok": True}


def run(monkey_server, on_disk, fn):
    """Point http + auth at stubs for one call."""
    real_req, real_load = http.request_response, api.auth.load
    http.request_response = monkey_server
    api.auth.load = lambda: on_disk
    try:
        return fn()
    finally:
        http.request_response, api.auth.load = real_req, real_load


# --------------------------------------------------------------------------
# 1. The rotated token is adopted and the call retried
# --------------------------------------------------------------------------
disk = Tokens()
disk.profile_token = "NEW"
srv = Server(good="NEW")
c = client("OLD")
out = run(srv, disk, lambda: c._get("/api/v1/users/me"))

check("the caller never sees the 401", out == {"ok": True}, str(out))
check("it was tried with the old token, then the new one",
      srv.seen == ["OLD", "NEW"], str(srv.seen))
check("the client keeps the adopted token for later calls",
      c.profile_token == "NEW", c.profile_token)
check("and its expiry came across too",
      c.profile_token_expires_at == disk.profile_token_expires_at)

# --------------------------------------------------------------------------
# 2. No retry when disk has nothing newer -- a dead token is still dead
# --------------------------------------------------------------------------
same = Tokens()
same.profile_token = "OLD"
srv = Server(good="NEW")
c = client("OLD")
try:
    run(srv, same, lambda: c._get("/api/v1/users/me"))
    check("an unrotated token still raises", False, "no raise")
except http.ApiError as exc:
    check("an unrotated token still raises", exc.status == 401)
check("...and it was tried exactly once", srv.seen == ["OLD"], str(srv.seen))

none_stored = Tokens()
none_stored.profile_token = None
srv = Server(good="NEW")
c = client("OLD")
try:
    run(srv, none_stored, lambda: c._get("/api/v1/users/me"))
    check("no token on disk raises rather than retrying", False, "no raise")
except http.ApiError:
    check("no token on disk raises rather than retrying", srv.seen == ["OLD"],
          str(srv.seen))

# --------------------------------------------------------------------------
# 3. An ACCOUNT 401 is a different problem and must not be swallowed
# --------------------------------------------------------------------------
srv = Server(good="NEW", error="Could not validate credentials")
c = client("OLD")
try:
    run(srv, disk, lambda: c._get("/api/v1/users/me"))
    check("an account 401 is not retried as a profile one", False, "no raise")
except http.ApiError:
    check("an account 401 is not retried as a profile one",
          srv.seen == ["OLD"], str(srv.seen))

check("a 403 about a profile token is not a 401",
      not api._is_profile_token_401(
          http.ApiError(403, "forbidden", "Invalid or expired profile token")))
check("the classifier reads the server's real wording",
      api._is_profile_token_401(
          http.ApiError(401, "unauthorized",
                        "Unauthorized: Invalid or expired profile token")))

# --------------------------------------------------------------------------
# 4. The heartbeat still banks a rotation from its response headers
# --------------------------------------------------------------------------
banked = {}
real_save = api.auth.save_rotated_profile_token
api.auth.save_rotated_profile_token = lambda t, e: banked.update(token=t, expires=e)
try:
    c = client("OLD")
    rotated = Response()
    rotated.headers = {"X-Profile-Token": "SLID",
                       "X-Profile-Token-Expires-At": "2026-08-29T00:00:00Z"}
    c._absorb_rotated_profile_token(rotated)
    check("a rotation in the headers is taken into the client",
          c.profile_token == "SLID", c.profile_token)
    check("...and persisted for every other component",
          banked.get("token") == "SLID", str(banked))
    check("...with its RFC 3339 expiry parsed to epoch seconds",
          isinstance(banked.get("expires"), float) and banked["expires"] > 1e9,
          str(banked.get("expires")))

    # No headers is the common case and must cost nothing.
    c = client("OLD")
    c._absorb_rotated_profile_token(Response())
    check("no headers leaves the token alone", c.profile_token == "OLD")
finally:
    api.auth.save_rotated_profile_token = real_save

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
