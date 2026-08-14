# -*- coding: utf-8 -*-
"""Multi-user household profiles -- GET /api/v1/profiles lists the
signed-in account's profiles; POST /api/v1/profiles/{id}/verify-pin
unlocks a locked one. Bare HTTP calls only, parallel to cloud.py -- the
interactive "Who's watching?"/PIN screen lives in windows/profile_select.py,
same split as cloud.py (API) vs signin.py (interactive flow).

Every account-scoped endpoint 403s `{"code": "profile_locked"}` once a
profile requires unlocking -- this module isn't optional, an account in
that state is broken without it wired in.
"""
from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Optional

from . import http


@dataclasses.dataclass
class Profile:
    id: str
    name: str
    avatar_color: str
    avatar_image_url: Optional[str]
    avatar_ref: Optional[str]
    is_primary: bool
    is_locked: bool
    is_kids: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Profile":
        return cls(
            id=data["id"],
            name=data.get("name") or "",
            avatar_color=data.get("avatar_color") or "#2DD4BF",
            avatar_image_url=data.get("avatar_image_url"),
            avatar_ref=data.get("avatar_ref"),
            is_primary=bool(data.get("is_primary")),
            is_locked=bool(data.get("is_locked")),
            is_kids=bool(data.get("is_kids")),
        )


def _headers(access_token: str, device_id: str) -> dict[str, str]:
    return {"X-Tofa-Device-Id": device_id, "Authorization": f"Bearer {access_token}"}


def list_profiles(session, server: str, access_token: str, device_id: str,
                  fallback: str | None = None) -> list[Profile]:
    """The account's profiles, with the SAME fallback MediaServerClient has.

    This used to take `tok.server` and nothing else, so it was the one call
    on the way into the app with no second address to try. That is not
    academic: on 2026-08-13 a second server published a port nothing bound
    locally, every `tok.server` call failed, and while the rest of the client
    limped along on its fallback this path failed outright -- so the profile
    gate could not be drawn and Settings showed a profile row with no name.

    A transport failure is the ONLY thing retried. A 401/403/404 is the
    server answering, and asking a different address the same question would
    just get the same answer more slowly."""
    def _fetch(base: str):
        return http.request_json(
            session, "GET", f"{base.rstrip('/')}/api/v1/profiles",
            headers=_headers(access_token, device_id))

    try:
        items = _fetch(server)
    except http.ApiError as exc:
        # Same gate as api._request: "Direct connections only" means the
        # relay is not an option even as a last resort.
        from . import auth
        if (exc.error not in ("connection_error", "timeout") or not fallback
                or (auth.direct_only() and auth.is_relay_url(fallback))):
            raise
        items = _fetch(fallback)
    return [Profile.from_json(item) for item in items or []]


def _parse_iso8601(value: str) -> float:
    """The server emits nanosecond-precision fractional seconds (e.g.
    "...737197432Z") -- datetime.fromisoformat only accepts up to 6 digits
    (microseconds) on the Python versions this add-on ships on, so
    truncate defensively rather than lean on a newer parser's leniency."""
    body = value[:-1] if value.endswith("Z") else value
    if "." in body:
        head, frac = body.split(".", 1)
        body = f"{head}.{frac[:6]}"
    return datetime.datetime.fromisoformat(body + "+00:00").timestamp()


def verify_pin(session, server: str, access_token: str, device_id: str, profile_id: str, pin: str) -> tuple[str, float]:
    """Returns (profile_token, expires_at epoch seconds). Raises
    http.ApiError (401 unauthorized) on a wrong PIN -- no lockout/
    rate-limit kicks in after a few wrong attempts."""
    granted = http.request_json(
        session,
        "POST",
        f"{server.rstrip('/')}/api/v1/profiles/{profile_id}/verify-pin",
        headers=_headers(access_token, device_id),
        json_body={"pin": pin},
    )
    return granted["profile_token"], _parse_iso8601(granted["expires_at"])
