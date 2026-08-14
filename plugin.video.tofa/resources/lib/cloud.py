"""api.tofa.tv device-flow sign-in + refresh.

Deliberately just the HTTP primitives -- no sleep loop baked in here, so the
sign-in dialog in addon.py can drive polling itself: update the progress
dialog, check for user cancellation, and respect xbmc.Monitor().abortRequested()
between polls (a bare `time.sleep` loop would ignore both).
"""
from __future__ import annotations

from typing import Any, Optional

from . import http

DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Account-first sign-in starts the device flow before any server is known,
# so there's no local server left to ask for this the way the old
# per-server flow did via GET /api/v1/auth/status.
CLOUD_BASE_URL = "https://api.tofa.tv"


def start_device_flow(
    session, connect_url: str, server_id: Optional[str], client_name: str, client_type: str
) -> dict[str, Any]:
    body: dict[str, Any] = {"client_name": client_name, "client_type": client_type}
    if server_id:
        body["server_id"] = server_id
    return http.request_json(
        session,
        "POST",
        f"{connect_url.rstrip('/')}/device/code",
        json_body=body,
    )


def poll_token_once(session, connect_url: str, device_code: str) -> dict[str, Any]:
    """One poll attempt. Raises http.ApiError with `.error` set to
    `authorization_pending` / `slow_down` / `expired_token` / `invalid_grant`
    while the user hasn't approved yet -- the caller decides how to react."""
    return http.request_json(
        session,
        "POST",
        f"{connect_url.rstrip('/')}/device/token",
        form_body={"grant_type": DEVICE_GRANT_TYPE, "device_code": device_code},
    )


def list_servers(session, connect_url: str, cloud_access_token: str) -> dict[str, Any]:
    """GET /servers -- the caller's owned + shared media servers. Requires
    the cloud (non-scoped) bearer token from a device flow started without
    `server_id`; a server-scoped token is rejected with 403."""
    return http.request_json(
        session,
        "GET",
        f"{connect_url.rstrip('/')}/servers",
        headers={"Authorization": f"Bearer {cloud_access_token}"},
    )


def get_account(session, connect_url: str, cloud_access_token: str) -> dict[str, Any]:
    """GET /v1/me -- the tofa ACCOUNT behind this pairing: its email, and the
    account avatar the app shows in Settings' identity card.

    The media server cannot answer this. Its `/api/v1/users/me` record is
    id / username / avatar_path / preferences / is_admin and carries no
    email field at all (checked against the live server, 2026-08-13), which
    is why this client showed a username where the app shows an address.

    NOTE THE PATH. This endpoint is under `/v1`, while `/servers` above is
    at the ROOT of the same host -- measured, not assumed: `/servers` and
    `/v1/me` both answer 401, `/v1/servers` and `/me` both answer 404. Do
    not "tidy" one to match the other."""
    return http.request_json(
        session,
        "GET",
        f"{connect_url.rstrip('/')}/v1/me",
        headers={"Authorization": f"Bearer {cloud_access_token}"},
    )


def create_server_session(session, connect_url: str, cloud_access_token: str, server_id: str) -> dict[str, Any]:
    """POST /servers/{id}/server-session -- exchanges the cloud token for a
    durable server-scoped token pair (30-day access / 90-day refresh), no
    further approval needed."""
    return http.request_json(
        session,
        "POST",
        f"{connect_url.rstrip('/')}/servers/{server_id}/server-session",
        headers={"Authorization": f"Bearer {cloud_access_token}"},
    )


def refresh_cloud(session, connect_url: str, cloud_refresh_token: str) -> dict[str, Any]:
    """POST /auth/token/refresh -- mints a CLOUD access token good for
    15 minutes, the one `list_servers` and `create_server_session` demand and
    which the device flow only ever hands out once.

    The cloud counterpart to `refresh()` below, and deliberately a separate
    endpoint: the cloud session and the per-server session are different
    families and the server-scoped refresh token is rejected here (the
    lookup is scoped to `server_id IS NULL`), so the two can never be
    swapped for one another.

    The refresh token only rotates once it has aged past the server's
    rotation threshold -- younger ones come back unchanged -- so the caller
    must persist whatever `refresh_token` this returns rather than assuming
    a new one."""
    return http.request_json(
        session,
        "POST",
        f"{connect_url.rstrip('/')}/auth/token/refresh",
        json_body={"refresh_token": cloud_refresh_token},
    )


def refresh(session, connect_url: str, server_id: str, refresh_token: str) -> dict[str, Any]:
    return http.request_json(
        session,
        "POST",
        f"{connect_url.rstrip('/')}/servers/{server_id}/device-token/refresh",
        json_body={"refresh_token": refresh_token},
    )
