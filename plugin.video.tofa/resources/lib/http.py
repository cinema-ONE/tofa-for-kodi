"""Shared HTTP plumbing, built on `requests`.

The User-Agent deliberately doesn't contain "python" -- Cloudflare in front
of api.tofa.tv 403s (error code 1010) on any UA containing it.
"""
from __future__ import annotations

import threading
import time
import weakref
from typing import Any, Optional

import requests

from . import branding, clientinfo, log

#: The product token every request carries. `tofa-for-kodi` is this repo, and
#: the add-on it ships -- NOT `tofa-vault`, which is the internals repo beside
#: it and makes no requests of its own. It was `tofa-kodi/0.1.0` until
#: 2026-08-18: a name the vault gave up when it was renamed, and a version
#: frozen at 0.1.0 for the whole of 0.9.x.
#:
#: The version is read from addon.xml rather than written here, for the same
#: reason the name is (see branding.py): a second copy is only a copy that
#: drifts, and this one had. Nothing on the server reads it -- the analytics
#: bucket on X-Tofa-Client-Version below -- but it is what a Cloudflare or
#: nginx log shows, so it should not lie about which build made the call.
USER_AGENT = f"tofa-for-kodi/{branding.app_version()}"

#: How this client names itself to the server. Read by middleware, NOT
#: declared in the OpenAPI spec -- the only trace there is prose on the
#: diagnostics beacons ("folds in caller identity from X-Tofa-* headers,
#: same parser the playback analytics use"). Found by reading the server
#: binary; see reference_tofa_client_identity_headers.
#:
#: They surface as client_name / client_version / platform / device_model /
#: device_name on NowPlayingSession, PlaySessionAdminItem, LiveSessionDiag
#: and the analytics rollups. Without them we were bucketed as "other".
#:
#: CONFIRMED on the server's Analytics page, 2026-08-11: it buckets on
#: `x-tofa-client`, and "tofa for Kodi" is listed there in its own right
#: beside "tofa App" / "tofa Apple TV" / "tofa Web". Sessions from before
#: these headers went in are what sits in "Other".
#:
#: An earlier note here predicted the opposite -- that the label came from a
#: closed set of platform tokens found in the server binary, so an honest
#: `linux` would read as Other for ever. Wrong: that string table drives
#: something else, most likely the browser/OS detection behind BY DEVICE.
#: A table of strings in a binary tells you what strings EXIST, never what
#: consumes them.
#:
#: What each value should look like is decided in clientinfo.py, which also
#: records which parts Kodi will and will not tell an add-on.
_CLIENT_HEADERS: Optional[dict] = None


def _ascii(value: str, limit: int = 64) -> str:
    """Header-safe: ASCII, single-line, bounded.

    A device name is whatever the owner typed into Kodi, so it can carry
    non-latin-1 characters that make requests raise
    UnicodeEncodeError when it builds the request -- which would take out
    EVERY call, not just the one carrying the odd name. Newlines are dropped
    for the obvious reason.
    """
    cleaned = " ".join(str(value or "").split())
    return cleaned.encode("ascii", "ignore").decode("ascii")[:limit]


def client_headers() -> dict:
    """The X-Tofa-* identity set, resolved once per process.

    Cached because none of it can change while Kodi runs, and because this
    is on the path of every single request. Empty values are dropped rather
    than sent blank: the server reads a missing header as unknown, which is
    honest, while "" is noise in somebody's analytics.
    """
    global _CLIENT_HEADERS
    if _CLIENT_HEADERS is None:
        headers = {
            "X-Tofa-Client": _ascii(branding.app_name()),
            "X-Tofa-Client-Version": _ascii(branding.app_version(), 32),
            "X-Tofa-Platform": _ascii(clientinfo.platform_family(), 32),
            "X-Tofa-Device-Name": _ascii(clientinfo.device_name()),
            "X-Tofa-Device-Model": _ascii(clientinfo.device_model()),
            # Longer than the rest on purpose: it carries the OS build AND
            # the Kodi build, and truncating either loses the fact that makes
            # a support report answerable.
            "X-Tofa-OS-Version": _ascii(clientinfo.os_version(), 96),
        }
        _CLIENT_HEADERS = {k: v for k, v in headers.items() if v}
    return dict(_CLIENT_HEADERS)


#: How long a pooled connection may sit idle before we stop trusting it.
#:
#: The tofa server answers with `keep-alive: timeout=40`, so a pooled socket
#: older than that is already closed on its side. urllib3 discards one it can
#: SEE has been closed; it cannot see one that died silently -- a Wi-Fi path
#: that dropped the flow, a NAT entry that expired -- and reusing that costs
#: the FULL request timeout (15s) before anything else can happen.
#:
#: WHICH SESSIONS THIS ACTUALLY PROTECTS, because it is fewer than it looks:
#: only the three that outlive a single action -- `artcache`'s module-level
#: session, `monitor`'s heartbeat and `service.py`'s. **Every window builds a
#: fresh session per action** (`detail._get_client` and its siblings call
#: new_session() whenever `self.client` is None, which is every open, since
#: no caller hands one in). A fresh session has no pool and cannot go stale.
#:
#: Worth stating plainly because this guard was WRITTEN in the belief that it
#: fixed a reported Detail failure -- a page that came up with no artwork and
#: an empty Play pill after a break on 2026-08-21. It did not, and could not:
#: that page had a brand-new session. Verified twice, by reading the call
#: sites and by watching a box idle 110s without this guard ever firing. What
#: really consumed that 15s is still unknown; the primary address's error was
#: never logged, which is what api._request now fixes.
#:
#: 30s rather than the server's 40 so a connection is dropped before the
#: server's own timer can catch it.
IDLE_POOL_LIMIT_SECONDS = 30.0

#: Last use per session, weak so a short-lived session (signin, artcache)
#: is not kept alive by this bookkeeping. Guarded because a session can be
#: shared between the UI thread and a background fetch, and the check has to
#: be read-and-update in one step or two threads both decide to drop.
_LAST_USED: "weakref.WeakKeyDictionary[requests.Session, float]" = weakref.WeakKeyDictionary()
_LAST_USED_LOCK = threading.Lock()

#: Indirected so a test can drive an idle gap without waiting one out.
#: Monotonic rather than wall-clock: this measures a duration, and the boxes
#: do adjust their clock (a CoreELEC box with no RTC gets its time from NTP
#: seconds after boot, which would otherwise read as a huge idle gap or a
#: negative one).
_now = time.monotonic


def _drop_stale_pool(session: requests.Session) -> None:
    """Drop the connection pool if this session has been idle too long.

    `Session.close()` clears the adapters' pool managers; the session stays
    usable and the next request opens a fresh connection. On a LAN that is a
    ~1ms handshake against the 15s a dead socket costs.

    A request in flight on another thread holds its connection OUTSIDE the
    pool, so clearing cannot pull it out from under that thread -- the
    connection is simply not returned to a live pool afterwards.
    """
    now = _now()
    with _LAST_USED_LOCK:
        last = _LAST_USED.get(session)
        stale = last is not None and now - last > IDLE_POOL_LIMIT_SECONDS
        if stale:
            # Record now so a second thread arriving behind this one does not
            # close the pool again on the same idle gap.
            _LAST_USED[session] = now
    if stale:
        log.debug("http: dropping pooled connections after {0:.0f}s idle".format(now - last))
        session.close()


def _mark_used(session: requests.Session) -> None:
    with _LAST_USED_LOCK:
        _LAST_USED[session] = _now()


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str):
        self.status = status
        self.error = error
        self.message = message
        super().__init__(f"HTTP {status} {error}: {message}")


def _parse_error_body(resp: requests.Response) -> tuple[str, str]:
    try:
        data = resp.json()
    except ValueError:
        return "unknown_error", resp.text[:500]
    # ErrorResponse uses error/message; OAuthErrorResponse uses error/error_description.
    error = data.get("error", "unknown_error")
    message = data.get("message") or data.get("error_description") or ""
    return error, message


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    # On the SESSION rather than per call, so it reaches every request this
    # add-on makes -- including the ones added later by someone who has
    # never read this file.
    session.headers.update(client_headers())
    return session


def request_response(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> requests.Response:
    """The checked Response, for the callers that need its HEADERS.

    Split out of request_json rather than copied, so there is exactly one
    place that turns a transport failure or a non-2xx into an ApiError. The
    reason it exists: the session heartbeat's 204 carries the ROTATED profile
    token in its response headers, and a function that returns `resp.json()`
    throws that away before any caller can see it -- which is what blocked
    the sliding-unlock work (issue #7) until 0.9.30 shipped the rotation.
    """
    if params:
        params = {k: v for k, v in params.items() if v is not None}
    _drop_stale_pool(session)
    try:
        resp = session.request(
            method, url, params=params, json=json_body, data=form_body, headers=headers, timeout=timeout
        )
    except requests.exceptions.Timeout as exc:
        raise ApiError(0, "timeout", str(exc)) from None
    except requests.RequestException as exc:
        raise ApiError(0, "connection_error", str(exc)) from None
    finally:
        # Marked on the way OUT, not in: the next idle gap starts when this
        # request finishes, and a slow one would otherwise be counted as idle
        # time it did not spend idle. In `finally` so a failed request still
        # moves the clock -- the pool has just been proven live or replaced.
        _mark_used(session)

    if not resp.ok:
        error, message = _parse_error_body(resp)
        raise ApiError(resp.status_code, error, message)
    return resp


def body_of(resp: requests.Response) -> Any:
    """The decoded body, or None for the empty ones (204, mostly)."""
    if resp is None or not resp.content:
        return None
    return resp.json()


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> Any:
    return body_of(request_response(
        session, method, url, params=params, json_body=json_body,
        form_body=form_body, headers=headers, timeout=timeout))


def raw_range_request(
    session: requests.Session,
    url: str,
    *,
    method: str = "GET",
    range_header: Optional[str] = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> requests.Response:
    """Returns the raw Response so the caller can stream, HEAD-check status,
    or read `.headers` (a case-insensitive dict -- the server sends header
    names lowercase, and `requests` normalises lookups regardless)."""
    hdrs = dict(headers or {})
    if range_header:
        hdrs["Range"] = range_header
    # Same staleness guard as request_response. This path carries the artwork
    # fetches, which are exactly the ones that run after a screen has sat
    # still, and a hung range request stalls a whole grid of posters.
    _drop_stale_pool(session)
    try:
        return session.request(method, url, headers=hdrs, timeout=timeout, stream=True)
    finally:
        _mark_used(session)
