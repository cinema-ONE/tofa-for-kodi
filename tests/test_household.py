"""Household viewing: the grant, the five-minute viewer token, and that a
member's session never falls back to the owner's tokens.

Run:  python3 test_household.py
"""
import json
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmcgui

from resources.lib import api, auth, cloud, household, http, monitor

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


TOK = auth.Tokens(server="http://lan:33333", server_id="srv-1", connect_url="https://cloud",
                  access_token="owner-token", refresh_token="r", token_type="Bearer",
                  expires_in=3600, obtained_at=time.time(), device_id="dev",
                  cloud_refresh_token="cloud-r", profile_id="owner-p")
auth.load = lambda: TOK
SAVED_REFRESH = []
auth.save_cloud_refresh_token = SAVED_REFRESH.append
cloud.refresh_cloud = lambda s, url, r: {"access_token": "owner-cloud", "refresh_token": "cloud-r2"}

CALLS = []
ANSWERS = {}


def fake_request_json(session, method, url, **kw):
    CALLS.append((method, url, kw.get("json_body"), (kw.get("headers") or {}).get("Authorization")))
    answer = ANSWERS[(method, url.replace("https://cloud", ""))]
    if isinstance(answer, Exception):
        raise answer
    return answer() if callable(answer) else answer


http.request_json = fake_request_json


def reset():
    CALLS.clear()
    ANSWERS.clear()
    household.erase_grant()
    household.clear_viewer()


# -- enrol ----------------------------------------------------------------
reset()
ANSWERS[("POST", "/v1/household/devices")] = {
    "device": {"id": "dev-9", "name": "Living room", "server_id": "srv-1",
               "expires_at": "2099-01-01T00:00:00Z"},
    "device_token": "g" * 64}
grant = household.enable(None, TOK, "Living room")
method, url, body, bearer = CALLS[-1]
check("enrol posts the TV's name and server", body, {"name": "Living room", "server_id": "srv-1"})
check("enrol uses the owner's cloud bearer", bearer, "Bearer owner-cloud")
check("the rotated cloud refresh token is saved first", SAVED_REFRESH[-1], "cloud-r2")
check("the grant is stored", household.load_grant("srv-1").device_token, "g" * 64)
check("the grant belongs to its server only", household.load_grant("other"), None)
check("enabled for this server", household.is_enabled(TOK), True)

# -- viewers ---------------------------------------------------------------
ANSWERS[("POST", "/v1/household/device/viewers")] = [
    {"identity_id": "m1", "display_name": "Sam", "managed_profiles": False}, {"display_name": "x"}]
members = household.viewers(None, TOK, grant)
method, url, body, bearer = CALLS[-1]
check("viewers carry the grant in the body", body, {"include_owner": False, "device_token": "g" * 64})
check("viewers send no auth header", bearer, None)
check("an entry without an identity is dropped", [m["identity_id"] for m in members], ["m1"])

# -- become a member, renew ------------------------------------------------
ANSWERS[("POST", "/v1/household/device/viewer-token")] = {
    "access_token": "member-1", "expires_in": 300, "server_id": "srv-1", "identity_id": "m1"}
viewer = household.start_viewer(None, TOK, grant, members[0])
check("the member's token is in memory", household.active_viewer()["access_token"], "member-1")
check("and nowhere on disk", "member-1" in open(household._grant_path()).read(), False)
CALLS.clear()
household.renew(None, TOK)
check("a token with minutes left is not renewed", CALLS, [])
v = household.active_viewer(); v["expires_at"] = time.time() + 30; household.set_viewer(v)
ANSWERS[("POST", "/v1/household/device/viewer-token")] = {"access_token": "member-2", "expires_in": 300}
household.renew(None, TOK)
check("one minute before expiry it renews", household.active_viewer()["access_token"], "member-2")

v = household.active_viewer(); v["expires_at"] = time.time() + 30; household.set_viewer(v)
ANSWERS[("POST", "/v1/household/device/viewer-token")] = http.ApiError(502, "bad_gateway", "")
household.renew(None, TOK)
check("a temporary failure keeps a token that still works",
      household.active_viewer()["access_token"], "member-2")
v = household.active_viewer(); v["expires_at"] = time.time() - 1; household.set_viewer(v)
try:
    household.renew(None, TOK)
    ended = None
except household.ViewerEnded as exc:
    ended = exc.reason
check("an expired token that cannot be renewed ends the session", ended, "expired")
check("and the member is gone", household.active_viewer(), None)

# -- refusals ---------------------------------------------------------------
ANSWERS[("POST", "/v1/household/device/viewer-token")] = {"access_token": "m", "expires_in": 300}
household.start_viewer(None, TOK, grant, members[0])
ANSWERS[("POST", "/v1/household/device/viewer-token")] = http.ApiError(
    403, "household_viewer_unavailable", "")
try:
    household.viewer_token(None, TOK, grant, "m1")
    reason = None
except household.ViewerEnded as exc:
    reason = exc.reason
check("a member who left ends their session", reason, household.UNAVAILABLE)
check("but the TV keeps its grant", household.load_grant("srv-1") is not None, True)

ANSWERS[("POST", "/v1/household/device/viewer-token")] = http.ApiError(
    401, "household_device_revoked", "")
try:
    household.viewer_token(None, TOK, grant, "m1")
    reason = None
except household.ViewerEnded as exc:
    reason = exc.reason
check("a revoked grant ends it too", reason, household.REVOKED)
check("and the grant is erased", household.load_grant(), None)

ANSWERS[("POST", "/v1/household/device/viewer-token")] = http.ApiError(500, "unknown_error", "")
household.save_grant(grant)
try:
    household.viewer_token(None, TOK, grant, "m1")
    kind = "ok"
except household.ViewerEnded:
    kind = "ended"
except http.ApiError:
    kind = "temporary"
check("anything else is temporary and keeps the grant", (kind, household.load_grant() is not None),
      ("temporary", True))

# -- the server client --------------------------------------------------------
reset()
household.save_grant(grant)
household.set_viewer({"identity_id": "m1", "name": "Sam", "managed": False,
                      "access_token": "member-1", "expires_at": time.time() + 300,
                      "server_id": "srv-1", "profile_id": "sam-p", "profile_token": None,
                      "profile_token_expires_at": None})
client = api.client_for(None, TOK)
check("client_for speaks for the member", (client.access_token, client.profile_id,
                                           client.household_identity), ("member-1", "sam-p", "m1"))
household.set_viewer(dict(household.active_viewer(), expires_at=time.time() - 1))
ANSWERS[("POST", "/v1/household/device/viewer-token")] = http.ApiError(
    403, "household_viewer_unavailable", "")
try:
    api.client_for(None, TOK)
    got = "owner client"
except household.ViewerEnded:
    got = "refused"
check("a member who cannot renew never gets the owner's client", got, "refused")


class Resp:
    def __init__(self, body):
        self.content = json.dumps(body).encode()
        self._body = body
        self.headers = {}

    def json(self):
        return self._body


household.set_viewer({"identity_id": "m1", "name": "Sam", "managed": False,
                      "access_token": "member-1", "expires_at": time.time() + 300,
                      "server_id": "srv-1", "profile_id": "sam-p", "profile_token": None,
                      "profile_token_expires_at": None})
SENT = []
OUTCOMES = []


def fake_request_response(session, method, url, **kw):
    SENT.append(kw["headers"]["Authorization"])
    outcome = OUTCOMES.pop(0)
    if isinstance(outcome, Exception):
        raise outcome
    return Resp(outcome)


http.request_response = fake_request_response
api.time.sleep = lambda s: None
ANSWERS[("POST", "/v1/household/device/viewer-token")] = {"access_token": "member-3", "expires_in": 300}
client = api.client_for(None, TOK)
OUTCOMES[:] = [http.ApiError(401, "unknown_error", ""), {"ok": 1}]
check("a 401 renews the member's token and retries once", client._get("/x"), {"ok": 1})
check("with the new token", SENT[-1], "Bearer member-3")
OUTCOMES[:] = [http.ApiError(503, "household_authorization_unavailable", ""), {"ok": 2}]
check("the server not reaching the cloud is waited out", client._get("/y"), {"ok": 2})
OUTCOMES[:] = [http.ApiError(500, http.NO_ENVELOPE, ""), {"ok": 3}]
check("the bodyless 500 on a new token is temporary", client._get("/z"), {"ok": 3})

# -- the monitor never reports for someone else --------------------------------
mon = monitor.TofaPlayer.__new__(monitor.TofaPlayer)
mon._http_session = None
mon._session = {"viewer": "someone-else"}
auth.ensure_fresh = lambda session: TOK
check("progress started by another viewer is not reported", mon._client(), None)
mon._session = {"viewer": "m1"}
check("progress for the same member is", mon._client().household_identity, "m1")
household.clear_viewer()
mon._session = {"viewer": ""}
check("and the owner's for the owner", mon._client().household_identity, None)

# -- disable and sign out ---------------------------------------------------------
reset()
household.save_grant(grant)
ANSWERS[("DELETE", "/v1/household/devices/dev-9")] = http.ApiError(500, "boom", "")
ANSWERS[("POST", "/v1/household/device/revoke")] = None
household.disable(None, TOK)
check("a failed delete falls back to revoking by token",
      [c[1].replace("https://cloud", "") for c in CALLS],
      ["/v1/household/devices/dev-9", "/v1/household/device/revoke"])
check("and the grant is erased either way", household.load_grant(), None)
household.save_grant(grant)
household.drop_for_sign_out()
check("signing out erases the grant", household.load_grant(), None)

# -- asked again after a long time away -------------------------------------------
xbmcgui.Window(10000).setProperty(household.AWAY_PROPERTY, str(time.time() - 16 * 60))
check("back after 16 minutes asks again", household.back_after_long_away(), True)
check("only once", household.back_after_long_away(), False)
xbmcgui.Window(10000).setProperty(household.AWAY_PROPERTY, str(time.time() - 60))
check("back after a minute does not", household.back_after_long_away(), False)

# -- Who's watching hands the TV over --------------------------------------------
from resources.lib import profiles as profiles_api  # noqa: E402
from resources.lib.windows import profile_select  # noqa: E402

http.request_json = fake_request_json
reset()
household.save_grant(grant)
OWNER = profiles_api.Profile("owner-p", "Adrian", "", None, None, True, True, False)
SAM = profiles_api.Profile("sam-p", "Sam", "", None, None, True, False, False)
profiles_api.list_profiles = lambda s, server, token, dev, fallback=None: (
    [SAM] if token.startswith("member") else [OWNER])
profile_select._resolve_avatar_photos = lambda *a: {}
profile_select._resolve_preset_urls = lambda *a: {}
profile_select._stop_playback = lambda: None
CLEARED = []
auth.clear_profile_selection = lambda: CLEARED.append(True)
SHOWN = []


class Picked:
    canceled = False

    def __init__(self, chosen):
        self.chosen = chosen


def pick(name):
    def open_(**kw):
        SHOWN.append([p.name for p in kw["profiles"]])
        return Picked(next(p for p in kw["profiles"] if p.name == name))
    profile_select.ProfileDialog.open = open_


ANSWERS[("POST", "/v1/household/device/viewers")] = [
    {"identity_id": "m1", "display_name": "Sam", "managed_profiles": False}]
ANSWERS[("POST", "/v1/household/device/viewer-token")] = {
    "access_token": "member-5", "expires_in": 300, "server_id": "srv-1"}
household.forget_chosen()
pick("Sam")
profile_select.ensure_profile_selected(None, TOK)
check("a shared TV asks who's watching at start, members after the owner",
      SHOWN[-1], ["Adrian", "Sam"])
check("picking a member makes them the viewer, on their primary profile",
      (household.active_viewer()["identity_id"], household.active_viewer()["profile_id"]),
      ("m1", "sam-p"))
check("and forgets the owner's unlock", CLEARED, [True])
SHOWN.clear()
profile_select.ensure_profile_selected(None, TOK)
check("then it does not ask again this run", SHOWN, [])
pick("Adrian")
profile_select.switch_profile()
check("picking the owner ends the member's session", household.active_viewer(), None)

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
