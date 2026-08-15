"""Shared HTTP plumbing, built on `requests`.

The User-Agent deliberately doesn't contain "python" -- Cloudflare in front
of api.tofa.tv 403s (error code 1010) on any UA containing it.
"""
from __future__ import annotations

from typing import Any, Optional

import requests

from . import branding, clientinfo

USER_AGENT = "tofa-kodi/0.1.0"

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
    try:
        resp = session.request(
            method, url, params=params, json=json_body, data=form_body, headers=headers, timeout=timeout
        )
    except requests.exceptions.Timeout as exc:
        raise ApiError(0, "timeout", str(exc)) from None
    except requests.RequestException as exc:
        raise ApiError(0, "connection_error", str(exc)) from None

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
    return session.request(method, url, headers=hdrs, timeout=timeout, stream=True)
