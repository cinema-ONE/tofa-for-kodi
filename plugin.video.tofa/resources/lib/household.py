# -*- coding: utf-8 -*-
"""Household viewing: other tofa accounts watching on this TV as themselves.

The TV stays signed in to its owner. Enabling it stores a device grant next
to the owner's tokens; picking a member trades that grant for a five-minute
viewer token, kept in memory only (a Kodi home-window property, so the
service process sees the same viewer as the windows).
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from typing import Any, Optional

import xbmcgui
import xbmcvfs

from . import atomicwrite, auth, cloud, http, log

CAPABILITY = "household.viewing"
VIEWER_PROPERTY = "tofa.household_viewer"
AWAY_PROPERTY = "tofa.household_away_since"
#: Set when a member's session ends in any process; the windows' Renewer
#: picks it up and asks who's watching.
ENDED_PROPERTY = "tofa.household_ended"
#: Back after this long away (Minimize) and the TV asks who's watching again.
ASK_AFTER_S = 15 * 60
#: Renew a viewer token this long before it expires; retry this often.
RENEW_MARGIN_S = 60
RETRY_S = 10

REVOKED = "household_device_revoked"
UNAVAILABLE = "household_viewer_unavailable"
NOT_IN_HOUSEHOLD = "not_found"


class ViewerEnded(http.ApiError):
    """The member's session cannot go on; `reason` says why.

    An ApiError, so every caller that already treats one as "no data" stops
    there, rather than carrying on with the owner's tokens."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(401, reason, "This member can't watch here right now.")


# ---------------------------------------------------------------- the grant

@dataclasses.dataclass
class Grant:
    device_id: str
    device_token: str
    server_id: str
    name: str = ""
    expires_at: Optional[float] = None


def _grant_path() -> str:
    return os.path.join(auth._profile_dir(), "household.json")


def load_grant(server_id: str | None = None) -> Optional[Grant]:
    """The stored grant, if any (and if given, only one for `server_id`)."""
    path = _grant_path()
    if not xbmcvfs.exists(path):
        return None
    f = xbmcvfs.File(path)
    try:
        data = json.loads(f.read() or "{}")
    except ValueError:
        return None
    finally:
        f.close()
    try:
        grant = Grant(**{k: data[k] for k in data.keys() & {
            f.name for f in dataclasses.fields(Grant)}})
    except TypeError:
        return None
    if server_id and grant.server_id != server_id:
        return None
    if grant.expires_at and grant.expires_at <= time.time():
        return None
    return grant


def save_grant(grant: Grant) -> None:
    path = _grant_path()
    atomicwrite.write_json(path, dataclasses.asdict(grant))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def erase_grant() -> None:
    path = _grant_path()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
    clear_viewer()


def drop_for_sign_out() -> None:
    """Signing out turns household viewing off: revoke, then erase."""
    grant = load_grant()
    if grant is not None:
        try:
            revoke(http.new_session(), auth.load(), grant)
        except (auth.NotSignedIn, auth.TokenLoadError):
            pass
    erase_grant()


def is_enabled(tok: auth.Tokens) -> bool:
    return load_grant(tok.server_id) is not None


# ---------------------------------------------------------------- the cloud

def _url(tok: auth.Tokens, path: str) -> str:
    return f"{tok.connect_url.rstrip('/')}{path}"


def _owner_bearer(session, tok: auth.Tokens) -> str:
    """A fresh cloud token for the owner; the rotated refresh token is saved
    before anything else (cloud.refresh_cloud says why)."""
    if not tok.cloud_refresh_token:
        raise http.ApiError(401, "no_cloud_session", "Sign in again to use this.")
    granted = cloud.refresh_cloud(session, tok.connect_url, tok.cloud_refresh_token)
    if granted.get("refresh_token"):
        auth.save_cloud_refresh_token(granted["refresh_token"])
    return granted["access_token"]


def status(session, tok: auth.Tokens) -> dict:
    """GET /v1/household: `{household, invitations, available}`."""
    bearer = _owner_bearer(session, tok)
    return http.request_json(session, "GET", _url(tok, "/v1/household"),
                             headers={"Authorization": f"Bearer {bearer}"}) or {}


def enable(session, tok: auth.Tokens, name: str) -> Grant:
    """Enrol this TV. The token comes back once, so it is saved at once."""
    bearer = _owner_bearer(session, tok)
    body = http.request_json(
        session, "POST", _url(tok, "/v1/household/devices"),
        headers={"Authorization": f"Bearer {bearer}"},
        json_body={"name": (name or "Kodi").strip()[:80], "server_id": tok.server_id})
    device = body.get("device") or {}
    grant = Grant(device_id=device.get("id") or "", device_token=body["device_token"],
                  server_id=device.get("server_id") or tok.server_id,
                  name=device.get("name") or name,
                  expires_at=_epoch(device.get("expires_at")))
    save_grant(grant)
    return grant


def disable(session, tok: auth.Tokens) -> None:
    """Remove this TV from the household; the local grant goes either way."""
    grant = load_grant()
    try:
        if grant is None:
            return
        try:
            bearer = _owner_bearer(session, tok)
            http.request_json(session, "DELETE",
                              _url(tok, f"/v1/household/devices/{grant.device_id}"),
                              headers={"Authorization": f"Bearer {bearer}"})
        except http.ApiError as exc:
            log.warning(f"household: delete failed ({exc}); revoking by token")
            revoke(session, tok, grant)
    finally:
        erase_grant()


def revoke(session, tok: auth.Tokens, grant: Grant) -> None:
    """Best effort: the grant revokes itself, no owner session needed."""
    try:
        http.request_json(session, "POST", _url(tok, "/v1/household/device/revoke"),
                          json_body={"device_token": grant.device_token})
    except http.ApiError as exc:
        log.warning(f"household: revoke failed: {exc}")


def _grant_call(session, tok: auth.Tokens, grant: Grant, path: str, body: dict) -> Any:
    """A call that carries the grant in its body; a dead grant is erased."""
    try:
        return http.request_json(session, "POST", _url(tok, path),
                                 json_body=dict(body, device_token=grant.device_token))
    except http.ApiError as exc:
        if exc.error == REVOKED:
            log.warning(f"household: grant is dead ({exc}); back to the owner")
            erase_grant()
            raise ViewerEnded(REVOKED) from None
        raise


def viewers(session, tok: auth.Tokens, grant: Grant) -> list[dict]:
    """The members who may watch here; the owner's own tile is not among them."""
    items = _grant_call(session, tok, grant, "/v1/household/device/viewers",
                        {"include_owner": False})
    return [v for v in items or [] if v.get("identity_id")]


def viewer_token(session, tok: auth.Tokens, grant: Grant, identity_id: str) -> dict:
    """A fresh five-minute token for one member."""
    try:
        return _grant_call(session, tok, grant, "/v1/household/device/viewer-token",
                           {"identity_id": identity_id})
    except http.ApiError as exc:
        if exc.status == 403 and exc.error == UNAVAILABLE:
            clear_viewer()
            raise ViewerEnded(UNAVAILABLE) from None
        raise


def _epoch(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    from .api import _rfc3339_epoch
    return _rfc3339_epoch(value)


# ---------------------------------------------------------------- the viewer

def _home() -> xbmcgui.Window:
    return xbmcgui.Window(10000)


def active_viewer() -> Optional[dict]:
    """The member watching now, or None when it is the owner."""
    raw = _home().getProperty(VIEWER_PROPERTY)
    if not raw:
        return None
    try:
        viewer = json.loads(raw)
    except ValueError:
        return None
    return viewer if viewer.get("identity_id") and viewer.get("access_token") else None


def set_viewer(viewer: dict) -> None:
    _home().setProperty(VIEWER_PROPERTY, json.dumps(viewer))


def clear_viewer() -> None:
    _home().clearProperty(VIEWER_PROPERTY)


def start_viewer(session, tok: auth.Tokens, grant: Grant, member: dict) -> dict:
    """Become `member`: their token, their name, no profile chosen yet."""
    granted = viewer_token(session, tok, grant, member["identity_id"])
    viewer = {
        "identity_id": member["identity_id"],
        "name": member.get("display_name") or "",
        "managed": bool(member.get("managed_profiles")),
        "access_token": granted["access_token"],
        "expires_at": time.time() + int(granted.get("expires_in") or 300),
        "server_id": granted.get("server_id") or grant.server_id,
        "profile_id": None, "profile_token": None, "profile_token_expires_at": None,
    }
    set_viewer(viewer)
    return viewer


def set_viewer_profile(profile_id: str, profile_token: str | None,
                       expires_at: float | None) -> None:
    viewer = active_viewer()
    if viewer is not None:
        viewer.update(profile_id=profile_id, profile_token=profile_token,
                      profile_token_expires_at=expires_at)
        set_viewer(viewer)


_renew_lock = threading.Lock()


def renew(session, tok: auth.Tokens, force: bool = False) -> Optional[dict]:
    """The active viewer with a token good for at least RENEW_MARGIN_S.

    Raises ViewerEnded when the member can no longer watch here; a transient
    failure keeps the old token while it lasts."""
    with _renew_lock:
        viewer = active_viewer()
        if viewer is None:
            return None
        if not force and viewer["expires_at"] - time.time() > RENEW_MARGIN_S:
            return viewer
        grant = load_grant(tok.server_id)
        if grant is None:
            _ended(REVOKED)
        try:
            granted = viewer_token(session, tok, grant, viewer["identity_id"])
        except ViewerEnded as exc:
            _ended(exc.reason)
        except http.ApiError as exc:
            if viewer["expires_at"] > time.time():
                log.warning(f"household: renewal failed ({exc}); token still good")
                return viewer
            _ended("expired")
        current = active_viewer()
        if current is None or current["identity_id"] != viewer["identity_id"]:
            return current
        current.update(access_token=granted["access_token"],
                       expires_at=time.time() + int(granted.get("expires_in") or 300))
        set_viewer(current)
        return current


CHOSEN_PROPERTY = "tofa.household_chosen"


def note_chosen() -> None:
    """Someone was picked for this run of tofa."""
    _home().setProperty(CHOSEN_PROPERTY, "1")


def chosen_this_run() -> bool:
    return bool(_home().getProperty(CHOSEN_PROPERTY))


def forget_chosen() -> None:
    """Ask who's watching again next time: tofa closed, or long away."""
    _home().clearProperty(CHOSEN_PROPERTY)


def _ended(reason: str):
    """End the member's session wherever it was noticed, and say so."""
    clear_viewer()
    _home().setProperty(ENDED_PROPERTY, reason)
    raise ViewerEnded(reason)


def take_ended() -> str:
    """The reason a member's session ended since last asked, once."""
    reason = _home().getProperty(ENDED_PROPERTY)
    _home().clearProperty(ENDED_PROPERTY)
    return reason


def note_away() -> None:
    """The TV went to the background (Minimize)."""
    _home().setProperty(AWAY_PROPERTY, str(time.time()))


def back_after_long_away() -> bool:
    """True once, on returning after ASK_AFTER_S or more in the background."""
    raw = _home().getProperty(AWAY_PROPERTY)
    _home().clearProperty(AWAY_PROPERTY)
    try:
        return bool(raw) and time.time() - float(raw) >= ASK_AFTER_S
    except ValueError:
        return False


class Renewer(threading.Thread):
    """Keeps the active viewer's token fresh while the windows are open.

    `on_ended(reason)` runs when the member's session cannot go on."""

    def __init__(self, on_ended):
        super().__init__(name="tofa-household-renewer", daemon=True)
        self._on_ended = on_ended
        self._halt = threading.Event()

    def stop(self):
        self._halt.set()

    def run(self):
        import xbmc
        monitor = xbmc.Monitor()
        session = http.new_session()
        while not self._halt.is_set() and not monitor.abortRequested():
            viewer = active_viewer()
            wait = 5.0
            if viewer is not None:
                left = viewer["expires_at"] - time.time()
                if left <= RENEW_MARGIN_S:
                    try:
                        renew(session, auth.load(), force=True)
                    except ViewerEnded:
                        pass                    # take_ended() below reports it
                    except Exception as exc:                 # noqa: BLE001
                        log.warning(f"household: renewer: {exc!r}")
                    viewer = active_viewer()
                    left = (viewer["expires_at"] - time.time()) if viewer else 0
                    wait = RETRY_S if viewer and left <= RENEW_MARGIN_S else 1.0
                else:
                    wait = min(5.0, left - RENEW_MARGIN_S)
            reason = take_ended()
            if reason:
                self._on_ended(reason)
            if monitor.waitForAbort(max(wait, 0.5)) or self._halt.is_set():
                break
