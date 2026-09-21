"""Token refresh survives tofa's cloud being down (server 0.10.0).

The cloud stays the primary refresh; when it fails, the server's local
session (POST /api/v1/auth/session/token) takes over. Measured 2026-09-21:
the server accepts the add-on's refresh token and rotates it, and the cloud
accepts the rotated one back. If both fail but the token still works, keep it.

Run:  python3 test_local_session_refresh.py
"""
import contextlib, dataclasses, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa", "resources"))
import kodi_stubs  # noqa: F401,E402
from lib import auth, cloud, http  # noqa: E402

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + str(detail)) if detail and not ok else ''}")

DAY = 86400
def tokens(left, lifetime=30 * DAY, fallback=None):
    return auth.Tokens(server="http://nas:33333", server_id="sid", connect_url="https://cloud",
                       access_token="A0", refresh_token="R0", token_type="Bearer",
                       expires_in=lifetime, obtained_at=time.time() - (lifetime - left),
                       device_id="dev", server_fallback=fallback)

state = {}
auth._refresh_lock = contextlib.nullcontext
auth.load = lambda: state["tok"]
auth.save = lambda t: state.__setitem__("saved", t)
DIRECT = {"on": False}
auth.direct_only = lambda: DIRECT["on"]
CLOUD_OK = {"access_token": "A1", "refresh_token": "R1", "token_type": "Bearer", "expires_in": 30 * DAY}
LOCAL_OK = {"access_token": "L1", "refresh_token": "LR1", "expires_in": 3600, "offline": False, "offline_valid_until": None}

def run(tok, cloud_result, server_results=()):
    """ensure_fresh with the cloud and server answers scripted."""
    state.clear(); state["tok"] = tok; auth._retry_after = 0.0
    calls = {"cloud": 0, "server": []}
    def fake_cloud(*a):
        calls["cloud"] += 1
        if isinstance(cloud_result, Exception): raise cloud_result
        return cloud_result
    answers = list(server_results)
    def fake_server(session, method, url, **kw):
        calls["server"].append(url)
        r = answers.pop(0)
        if isinstance(r, Exception): raise r
        return r
    cloud.refresh, http.request_json = fake_cloud, fake_server
    try:
        return auth.ensure_fresh(None), calls, None
    except http.ApiError as exc:
        return None, calls, exc

DOWN = http.ApiError(0, "connection_error", "no route")
BUSY = http.ApiError(503, "unavailable", "busy")
DEAD = http.ApiError(401, "unauthorized", "revoked")

tok, calls, _ = run(tokens(20 * DAY), CLOUD_OK)
check("a fresh token is not refreshed", calls["cloud"] == 0 and "saved" not in state)

tok, calls, _ = run(tokens(3600), CLOUD_OK)
check("due: the cloud refreshes, the server is not asked",
      state["saved"].refresh_token == "R1" and calls["server"] == [])

tok, calls, _ = run(tokens(3600), DOWN, [LOCAL_OK])
check("cloud unreachable: the server's local session refreshes",
      state["saved"].access_token == "L1" and state["saved"].refresh_token == "LR1", state.get("saved"))
check("...on the server's own address", calls["server"] == ["http://nas:33333/api/v1/auth/session/token"])
check("...and the token type is kept (the server doesn't send one)", state["saved"].token_type == "Bearer")

tok, calls, _ = run(tokens(3600), DEAD, [LOCAL_OK])
check("cloud refuses a token the server issued offline: the server refreshes it",
      state["saved"].refresh_token == "LR1")

tok, calls, exc = run(tokens(3600), DOWN, [DOWN])
check("both unreachable, token still valid: keep it, save nothing",
      exc is None and tok.access_token == "A0" and "saved" not in state)
state_calls = calls["cloud"]
auth.load = lambda: state["tok"]
again, calls2, _ = (auth.ensure_fresh(None), None, None)
check("...and don't retry on the very next call (no timeout per screen)",
      again.access_token == "A0" and state_calls == 1)
auth._retry_after = 0.0

tok, calls, exc = run(tokens(3600), DOWN, [DEAD])
check("cloud down, server says the token is dead: that's the error raised",
      exc is not None and exc.status == 401)

tok, calls, exc = run(tokens(3600), DEAD, [DOWN])
check("cloud says dead, server unreachable: the cloud's refusal is raised",
      exc is not None and exc.status == 401)

tok, calls, exc = run(tokens(-60), DOWN, [DOWN])
check("expired and both unreachable: raise, there's nothing to keep", exc is not None and exc.status == 0)

tok, calls, _ = run(tokens(50 * 60, lifetime=3600), CLOUD_OK)
check("a 1-hour server token with 50 min left is not due", calls["cloud"] == 0)
tok, calls, _ = run(tokens(20 * 60, lifetime=3600), CLOUD_OK)
check("...with 20 min left it is", calls["cloud"] == 1)

state_direct = tokens(3600, fallback="https://cloud/servers/sid")
auth.is_relay_url = lambda u: "cloud/servers" in (u or "")
tok, calls, _ = run(state_direct, DOWN, [DOWN, LOCAL_OK])
check("the fallback address is tried when the server's is unreachable",
      calls["server"] == ["http://nas:33333/api/v1/auth/session/token",
                          "https://cloud/servers/sid/api/v1/auth/session/token"])
DIRECT["on"] = True
tok, calls, exc = run(state_direct, DOWN, [DOWN])
check("...but never the relay when 'direct connections only' is on",
      len(calls["server"]) == 1 and exc is None)

print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
raise SystemExit(0 if all(RESULTS) else 1)
