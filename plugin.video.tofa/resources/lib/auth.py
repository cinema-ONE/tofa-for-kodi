"""Token persistence, device-flow sign-in, and refresh.

Reusing a retired refresh token revokes the entire session family and
forces re-pairing -- see _refresh_lock for the race this guards against.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import time
import re
import urllib.parse
import uuid
from typing import Any

try:                                                        # POSIX
    import fcntl
    msvcrt = None
except ImportError:                                         # Windows
    fcntl = None
    try:
        import msvcrt
    except ImportError:                                     # neither: run unlocked
        msvcrt = None

import xbmcaddon
import xbmcvfs

from . import atomicwrite
from . import cloud
from . import log


# How long to wait for the other process to finish its refresh before giving
# up and going ahead unlocked. Only reachable on the msvcrt path; flock waits.
# A refresh is one HTTP round trip, so 10s is already a pathological case --
# and this is time the user spends staring at a screen that hasn't drawn.
_LOCK_WAIT_SECONDS = 10
_LOCK_POLL_SECONDS = 0.1


class NotSignedIn(Exception):
    pass


class TokenLoadError(Exception):
    pass


def _addon() -> xbmcaddon.Addon:
    return xbmcaddon.Addon()


def _profile_dir() -> str:
    path = xbmcvfs.translatePath(_addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(path)
    return path


def token_file_path() -> str:
    return os.path.join(_profile_dir(), "tokens.json")


def _lock_file_path() -> str:
    return os.path.join(_profile_dir(), "tokens.lock")


def _image_token_file_path() -> str:
    return os.path.join(_profile_dir(), "image_token.json")


@dataclasses.dataclass
class Tokens:
    server: str
    server_id: str
    connect_url: str
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    obtained_at: float
    device_id: str
    # LAN/WAN fallback address, tried by MediaServerClient on connection
    # error. Defaulted so older tokens.json files still load.
    server_fallback: str | None = None
    # profile_id alone means "unlocked profile" (sent as X-Profile-Id,
    # doesn't expire). profile_token is for a locked profile (~4h TTL,
    # X-Profile-Token) and needs PIN re-verification once
    # profile_token_expires_at passes. Defaulted so older tokens.json files
    # still load.
    profile_id: str | None = None
    profile_token: str | None = None
    profile_token_expires_at: float | None = None
    # The server's friendly name ("MEDIA-NAS"), for Settings > Account to show
    # instead of a bare IP. Only the tofa cloud's GET /servers knows it, and
    # that needs the non-scoped cloud token which exists solely during
    # pairing -- so it is captured there or not at all. Defaulted, so an
    # install paired before this field existed keeps working and simply
    # falls back to the host until it next pairs.
    server_name: str | None = None
    # The CLOUD (non-scoped) refresh token from the device flow, kept so
    # Settings > Account can mint a cloud access token later and re-run the
    # server picker without a second pairing. `access_token`/`refresh_token`
    # above are server-SCOPED and get 403 from the cloud's GET /servers, so
    # this is the only thing that makes switching possible after pairing
    # ends. Defaulted: an install paired before this field existed has none,
    # and falls back to sign-out-and-pair-again.
    cloud_refresh_token: str | None = None

    @property
    def expires_at(self) -> float:
        return self.obtained_at + self.expires_in

    def seconds_until_expiry(self) -> float:
        return self.expires_at - time.time()

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Tokens":
        required = {
            f.name
            for f in dataclasses.fields(cls)
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        }
        missing = required - data.keys()
        if missing:
            raise TokenLoadError(f"Token file is missing fields {missing} -- sign in again.")
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: data[k] for k in data.keys() & valid})


def load() -> Tokens:
    path = token_file_path()
    if not xbmcvfs.exists(path):
        raise NotSignedIn(f"No tokens at {path} -- sign in first.")
    f = xbmcvfs.File(path)
    try:
        raw = f.read()
    finally:
        f.close()
    return Tokens.from_json(json.loads(raw))


def save(tok: Tokens) -> None:
    path = token_file_path()
    # Atomic replace, and it must work on Windows too: the old
    # xbmcvfs.rename() silently failed there whenever tokens.json already
    # existed, so nothing this function wrote was ever kept.
    atomicwrite.write_json(path, tok.to_json())
    # Best-effort 0600. On Windows os.chmod only toggles read-only, not
    # real ACLs -- never let this failure break sign-in.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _lock_exclusive(fd: int) -> None:
    """Block until this process holds the lock, or give up quietly.

    fcntl is POSIX-only -- importing it on Windows raises ModuleNotFoundError
    and took the whole add-on down on the first action there (0.9.5).
    msvcrt.locking is the Windows equivalent, but it locks a byte range from
    the current file position rather than the whole file. Poll with LK_NBLCK
    rather than LK_LOCK: LK_LOCK blocks for an implementation-defined spell
    (~10s) before raising, which makes the wait here neither predictable nor
    interruptible."""
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    if msvcrt is None:
        return
    os.lseek(fd, 0, os.SEEK_SET)
    deadline = time.time() + _LOCK_WAIT_SECONDS
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.time() >= deadline:
                # Better to refresh unlocked than to refuse to sign in: the
                # race this guards is rare, being locked out is not.
                log.warning(f"auth: token lock unavailable after "
                            f"{_LOCK_WAIT_SECONDS}s -- refreshing without it")
                return
            time.sleep(_LOCK_POLL_SECONDS)
            os.lseek(fd, 0, os.SEEK_SET)


def _unlock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    if msvcrt is None:
        return
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        # We may never have taken it (see above); unlocking is best-effort.
        pass


@contextlib.contextmanager
def _refresh_lock():
    """Advisory file lock so a foreground call and service.py's background
    refresher can never both refresh at once and race each other into
    revoking the session."""
    lock_path = _lock_file_path()
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        _lock_exclusive(fd)
        yield
    finally:
        _unlock(fd)
        os.close(fd)


def is_signed_in() -> bool:
    try:
        load()
        return True
    except NotSignedIn:
        return False


def sign_out() -> None:
    path = token_file_path()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
    _delete_image_token()


def _delete_image_token() -> None:
    """Drop the cached image token. It is minted by, and only valid against,
    ONE server for ONE account (JWT `sub`), so it has to go whenever either
    changes -- otherwise the next screen's art briefly loads with a token the
    new server has never heard of, and the posters come back blank until it
    expires."""
    image_path = _image_token_file_path()
    if xbmcvfs.exists(image_path):
        xbmcvfs.delete(image_path)


def load_cached_image_token() -> tuple[str, float] | None:
    """(token, expires_at) from disk, or None if there's no cached one.
    Doesn't check expiry itself -- the caller (api.py) decides the margin."""
    path = _image_token_file_path()
    if not xbmcvfs.exists(path):
        return None
    f = xbmcvfs.File(path)
    try:
        raw = f.read()
    finally:
        f.close()
    try:
        data = json.loads(raw)
        return data["token"], data["expires_at"]
    except (ValueError, KeyError, TypeError):
        return None


def save_image_token(token: str, expires_at: float) -> None:
    """Persisted across addon.py invocations -- each plugin action is a
    fresh process, so an in-memory-only cache never survives to the next
    listing. The server keeps this token byte-stable for an hour so art
    URLs are cacheable; without disk persistence, every listing mints a new
    token and URL for the same image, and Kodi's URL-keyed texture cache
    never hits."""
    path = _image_token_file_path()
    atomicwrite.write_json(path, {"token": token, "expires_at": expires_at})
    # Lower sensitivity than tokens.json (image-scoped, cache-GET only per
    # the endpoint's own description) but free to protect the same way.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_or_create_device_id() -> str:
    """Stable X-Tofa-Device-Id (UUID4), persisted in the add-on's own
    settings so it survives sign-out/sign-in."""
    addon = _addon()
    device_id = addon.getSettingString("device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
        addon.setSettingString("device_id", device_id)
    return device_id


#: The relay's hostname shape. Pairing stores two addresses -- the LAN one
#: probed from `signin._pick_server_address`, and the cloud's `connect_url`
#: -- and only the second is the relay. Every relay URL seen is
#: `<server-uuid>.connect.tofa.tv`; a LAN address is an IP.
_RELAY_HOST_SUFFIX = ".connect.tofa.tv"

#: The cloud's own PROXY of the same server: `<connect_url>/servers/<uuid>/
#: relay`, with the ordinary API path appended. It is a third way in,
#: alongside a LAN address and the `<uuid>.connect.tofa.tv` relay host, and
#: the one tofa's web app uses when the relay host answers 503
#: `server_relay_not_connected` -- which is what the demo server does.
#:
#: It matters here rather than only in signin because EVERY byte of it goes
#: through tofa's cloud. "Direct connections only" has to refuse it for the
#: same reason it refuses the relay host, and a check written against the
#: hostname alone would have waved it through: the host is api.tofa.tv.
_PROXY_PATH_RE = re.compile(r"^/servers/[^/]+/relay(/|$)")


def proxy_url(connect_url: str, server_id: str) -> str:
    """Where the cloud will proxy this server, as a base URL."""
    return "{0}/servers/{1}/relay".format(connect_url.rstrip("/"), server_id)


def is_relay_url(url: str | None) -> bool:
    """Does this address go through tofa's relay rather than straight to the
    server? Host-shaped rather than flagged, because a pairing made before
    this existed stored no flag to read -- and PATH-shaped as well, since
    the cloud proxy wears the cloud's own hostname."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:                                        # noqa: BLE001
        return False
    if (parsed.hostname or "").lower().endswith(_RELAY_HOST_SUFFIX):
        return True
    return bool(_PROXY_PATH_RE.match(parsed.path or ""))


def direct_only() -> bool:
    """Settings > Account > CONNECTION: never fall back to tofa's relay.

    DEVICE-local, not an account preference, because it describes how THIS
    box reaches the server -- the same account on a phone away from home
    needs the relay this box may be refusing.

    Reads false on any failure. A box that cannot answer the question should
    keep the connection it can get rather than lose the server over a
    setting it failed to read."""
    try:
        return bool(_addon().getSettingBool("direct_only"))
    except Exception:                                        # noqa: BLE001
        return False


def set_direct_only(value: bool) -> None:
    try:
        _addon().setSettingBool("direct_only", bool(value))
    except Exception:                                        # noqa: BLE001
        log.warning("auth: could not persist direct_only")


def complete_sign_in(
    server: str,
    server_id: str,
    connect_url: str,
    granted: dict[str, Any],
    device_id: str,
    server_fallback: str | None = None,
    server_name: str | None = None,
    cloud_refresh_token: str | None = None,
) -> Tokens:
    tok = Tokens(
        server=server.rstrip("/"),
        server_id=server_id,
        connect_url=connect_url,
        access_token=granted["access_token"],
        refresh_token=granted["refresh_token"],
        token_type=granted["token_type"],
        expires_in=granted["expires_in"],
        obtained_at=time.time(),
        device_id=device_id,
        server_fallback=server_fallback.rstrip("/") if server_fallback else None,
        server_name=server_name or None,
        cloud_refresh_token=cloud_refresh_token or None,
    )
    save(tok)
    return tok


def switch_server(
    server: str,
    server_id: str,
    granted: dict[str, Any],
    server_fallback: str | None = None,
    server_name: str | None = None,
) -> Tokens:
    """Re-point this install at a different server on the SAME account,
    keeping the pairing (see signin.interactive_switch_server).

    Builds the record from scratch rather than replacing fields on the old
    one, because the fields that must NOT survive are the easy ones to
    forget: profiles are per-server, so the stored profile_id/profile_token
    belong to a household the new server has never heard of and would be
    sent as X-Profile-Id on its very first request. A dataclasses.replace()
    that names only the server fields carries them over silently -- listing
    every field here makes leaving one behind impossible.

    Held under the same lock as ensure_fresh: service.py's background
    refresher may be mid-refresh against the OLD server, and letting it
    write afterwards would resurrect the old pair over the new one."""
    with _refresh_lock():
        old = load()
        tok = Tokens(
            server=server.rstrip("/"),
            server_id=server_id,
            connect_url=old.connect_url,
            access_token=granted["access_token"],
            refresh_token=granted["refresh_token"],
            token_type=granted["token_type"],
            expires_in=granted["expires_in"],
            obtained_at=time.time(),
            device_id=old.device_id,
            server_fallback=server_fallback.rstrip("/") if server_fallback else None,
            server_name=server_name or None,
            cloud_refresh_token=old.cloud_refresh_token,
        )
        save(tok)
    _delete_image_token()
    return tok


def save_cloud_refresh_token(cloud_refresh_token: str) -> None:
    """Persist the cloud refresh token the cloud handed back on its last
    rotation. Cheap to call every time -- the server only rotates the token
    once it has aged past its threshold and otherwise echoes the same one
    back, and writing an unchanged value costs one file rename."""
    with _refresh_lock():
        tok = load()
        if tok.cloud_refresh_token == cloud_refresh_token:
            return
        save(dataclasses.replace(tok, cloud_refresh_token=cloud_refresh_token))


def update_server(server: str, server_fallback: str | None) -> None:
    """Persist a runtime-discovered working address (see api.py's
    MediaServerClient fallback swap) so the *next* process launch -- every
    plugin action / window open is a fresh process -- tries the reachable
    one first instead of paying a failed-connection round trip every
    time."""
    try:
        tok = load()
    except NotSignedIn:
        return
    if tok.server == server and tok.server_fallback == server_fallback:
        return
    save(dataclasses.replace(tok, server=server, server_fallback=server_fallback))


def save_profile_selection(profile_id: str, profile_token: str | None, profile_token_expires_at: float | None) -> None:
    """Persists the "Who's watching?" choice so the next process launch
    doesn't have to ask again (see windows/profile_select.py's
    ensure_profile_selected, which checks this before any network call)."""
    tok = load()
    save(dataclasses.replace(
        tok,
        profile_id=profile_id,
        profile_token=profile_token,
        profile_token_expires_at=profile_token_expires_at,
    ))


def save_rotated_profile_token(profile_token: str,
                               profile_token_expires_at: float | None) -> None:
    """Store a profile token the SERVER rotated while viewing continued.

    Separate from save_profile_selection because nothing was re-selected:
    the profile, and the PIN entry behind it, are the same ones. Only the
    token changed, and only because the heartbeat happened to carry one that
    was nearing expiry (see MediaServerClient.report_progress).

    Ignored when no profile token is held. The server only rotates a token a
    request carried, so a rotation arriving for a profile we have since left
    is stale by definition, and writing it would re-lock nothing and unlock
    nothing -- it would just put a stranger's token in our file.
    """
    tok = load()
    if not tok.profile_token:
        return
    save(dataclasses.replace(
        tok,
        profile_token=profile_token,
        profile_token_expires_at=profile_token_expires_at,
    ))


def ensure_fresh(session, margin_seconds: float = 6 * 3600) -> Tokens:
    """Load tokens, transparently refreshing (and persisting the rotated
    pair) if the access token is within `margin_seconds` of expiry. The new
    pair is written to disk before this returns -- the old pair is only
    overwritten once the new one is confirmed, so a failed refresh never
    leaves the account signed out."""
    with _refresh_lock():
        tok = load()
        if tok.seconds_until_expiry() > margin_seconds:
            return tok
        granted = cloud.refresh(session, tok.connect_url, tok.server_id, tok.refresh_token)
        new_tok = dataclasses.replace(
            tok,
            access_token=granted["access_token"],
            refresh_token=granted["refresh_token"],
            token_type=granted["token_type"],
            expires_in=granted["expires_in"],
            obtained_at=time.time(),
        )
        save(new_tok)
        return new_tok
