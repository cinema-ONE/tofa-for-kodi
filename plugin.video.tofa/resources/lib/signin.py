# -*- coding: utf-8 -*-
"""Interactive device-code sign-in flow.

Extracted out of addon.py's action_sign_in() so both the plugin:// router and
the window UI (windows/home.py and friends) can drive the same flow directly
on first launch when nobody is signed in yet, instead of only being reachable
by hand through Add-on settings.
"""
from __future__ import annotations

import os
import re
import struct
import time
import zlib

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import auth, cloud, http
from .windows import cardoptions, kodigui, theme

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
_ = ADDON.getLocalizedString

_QR_FILENAME = "signin_qr.png"

# Matches one dark-module square emitted by the server's QR SVG, e.g.
# "M8 0h8v8H8V0" -- moveto (x,y), relative h/v by the module size, then
# absolute H/V back to (x,y) closing the unit square. See _qr_svg_to_png.
_QR_SQUARE_RE = re.compile(r"M(\d+) (\d+)h(\d+)v\d+H\d+V\d+")
_QR_VIEWBOX_RE = re.compile(r'viewBox="0 0 (\d+) (\d+)"')

# QR spec wants a blank "quiet zone" >= 4 modules wide on every side so
# scanners can find the code's edges; the server's SVG has none at all
# (modules start right at pixel 0,0).
_QUIET_ZONE_MODULES = 4


def _notify(message: str, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(ADDON_NAME, message, icon)


def _qr_svg_to_png(svg: str) -> bytes | None:
    """Rasterize the tofa API's qr_code_svg into a PNG.

    Kodi's texture loader can't reliably decode SVG, so render it ourselves.
    The server's SVG is always the same trivial shape -- a white background
    rect plus one black <path> made of unit-square "M x y h s v s H x V y"
    commands, one per dark QR module -- so this only needs to regex out
    those squares, not parse general SVG path syntax. No extra deps: zlib
    (PNG's DEFLATE-compressed IDAT) is stdlib.
    """
    viewbox = _QR_VIEWBOX_RE.search(svg)
    squares = _QR_SQUARE_RE.findall(svg)
    if not viewbox or not squares:
        return None
    inner_width, inner_height = int(viewbox.group(1)), int(viewbox.group(2))
    module_size = int(squares[0][2])
    margin = _QUIET_ZONE_MODULES * module_size
    width, height = inner_width + margin * 2, inner_height + margin * 2

    row_bytes = width * 3
    canvas = bytearray(b"\xff" * (row_bytes * height))
    for x_str, y_str, s_str in squares:
        x0, y0, s = int(x_str) + margin, int(y_str) + margin, int(s_str)
        black_run = b"\x00" * (min(s, width - x0) * 3)
        for y in range(y0, min(y0 + s, height)):
            row_off = y * row_bytes
            canvas[row_off + x0 * 3 : row_off + x0 * 3 + len(black_run)] = black_run

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = bytearray()
    for y in range(height):
        raw += b"\x00" + canvas[y * row_bytes : (y + 1) * row_bytes]  # per-row filter byte: none

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit depth, color type 2 (RGB)
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _write_qr_png(svg: str | None) -> str | None:
    """Rasterize `qr_code_svg` from POST /device/code (null if server-side
    generation failed) and land it on disk once -- Kodi's texture loader
    (skin <texture> tags and xbmcgui.ControlImage alike) takes a file path,
    not raw markup."""
    if not svg:
        return None
    try:
        png_bytes = _qr_svg_to_png(svg)
        if not png_bytes:
            return None
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        xbmcvfs.mkdirs(profile_dir)
        path = os.path.join(profile_dir, _QR_FILENAME)
        f = xbmcvfs.File(path, "w")
        try:
            f.write(png_bytes)
        finally:
            f.close()
        return path
    except Exception:
        return None


class SignInDialog(kodigui.BaseDialog):
    """Device-code + QR sign-in dialog, styled to match tofa's own Apple TV
    app pairing screen: star-flecked dark backdrop, centered logo, teal
    caption, link pill, boxed code characters, QR in a white card,
    self-refreshing countdown."""

    xmlFile = "script-tofa-signin.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    # Transparent hit-target over the "Generate new code" pill, see
    # script-tofa-signin.xml's expired-state group.
    RETRY_BUTTON_ID = 700

    def __init__(self, *args, **kwargs):
        self._heading = kwargs.pop("heading", "")
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self._canceled = False
        self._retry = False

    def onFirstInit(self):
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("heading", self._heading.upper())
        self.setProperty("instruction_line", _(31025))
        self.setProperty("qr_hint", _(31023).upper())
        self.setProperty("expired_caption", _(31026).upper())
        self.setProperty("expired_headline", _(31027))
        self.setProperty("expired_subtext", _(31028))
        self.setProperty("retry_label", _(31029))
        self.setProperty("expired_footnote", _(31052))
        self.setProperty("state", "waiting")

    def set_countdown(self, remaining_seconds: float) -> None:
        """Ticks the "Code refreshes in M:SS" readout, matching tofa's own
        Apple TV app which self-refreshes the code on a visible timer
        instead of only reacting after the fact."""
        total = max(0, int(remaining_seconds))
        minutes, seconds = divmod(total, 60)
        countdown_text = "{0}:{1:02d}".format(minutes, seconds)
        self.setProperty("countdown_text", countdown_text)
        self.setProperty("countdown_label", _(31053) % countdown_text)

    def apply_code(self, link_url: str, code_chars: list[str], qr_path: str | None) -> None:
        """Push a (possibly freshly re-requested) device code's details into
        the XML and switch back to the waiting state."""
        self.setProperty("link_url", link_url)
        for i, ch in enumerate(code_chars):
            self.setProperty("code_char_{0}".format(i), ch)
        self.setProperty("qr_image", qr_path or "")
        self.setProperty("state", "waiting")

    def show_expired(self) -> None:
        """Switch to the "code timed out" state, mirroring tofa's own app,
        instead of silently closing with a toast."""
        self.setProperty("countdown_text", "")
        self.setProperty("countdown_label", "")
        self.setProperty("state", "expired")
        self.setFocusId(self.RETRY_BUTTON_ID)

    def retry_requested(self) -> bool:
        if self._retry:
            self._retry = False
            return True
        return False

    def iscanceled(self) -> bool:
        return self._canceled

    def onClick(self, controlID):
        if controlID == self.RETRY_BUTTON_ID:
            self._retry = True

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self._canceled = True
            return
        kodigui.BaseDialog.onAction(self, action)


def _request_code(session):
    return cloud.start_device_flow(session, cloud.CLOUD_BASE_URL, None, "Kodi (tofa add-on)", "kodi")


def _apply_code(dialog: SignInDialog, code: dict, old_qr_path: str | None) -> str | None:
    """Push a device code's details into the dialog, cleaning up the
    previous QR PNG (if any) first. Returns the new QR path for the caller
    to track."""
    if old_qr_path:
        try:
            xbmcvfs.delete(old_qr_path)
        except Exception:
            pass
    # Mimics tofa's Android TV app: bare host+path (no scheme) in a pill
    # above 8 individually boxed code characters.
    link_url = code["verification_uri"].split("://", 1)[-1].rstrip("/")
    raw_chars = [ch for ch in code["user_code"] if ch != "-"]
    code_chars = (raw_chars + [""] * 8)[:8]
    qr_path = _write_qr_png(code.get("qr_code_svg"))
    dialog.apply_code(link_url, code_chars, qr_path)
    return qr_path


def _poll_until_resolved(session, dialog: SignInDialog, code: dict, monitor: xbmc.Monitor):
    """Poll /device/token until granted, a hard error, cancellation, or
    expiry. Returns (granted, error_message, expired).

    Ticks the dialog's countdown every second while only actually hitting
    the network at the server-given `interval` (5s+) -- a visible
    per-second countdown needs a finer wake-up than the server's polling
    cadence."""
    interval = code.get("interval", 5)
    deadline = time.monotonic() + code.get("expires_in", 600)
    next_poll_at = time.monotonic()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, None, True
        dialog.set_countdown(remaining)
        if dialog.iscanceled() or monitor.waitForAbort(1.0):
            return None, None, False
        if time.monotonic() < next_poll_at:
            continue
        next_poll_at = time.monotonic() + interval
        try:
            return cloud.poll_token_once(session, cloud.CLOUD_BASE_URL, code["device_code"]), None, False
        except http.ApiError as exc:
            if exc.error in ("authorization_pending", "slow_down"):
                continue
            if exc.error == "expired_token":
                return None, None, True
            return None, exc.message, False


def interactive_sign_in() -> bool:
    """Drive the device-code flow end to end: show the verification URL and
    code, poll for approval, let the user pick a server if their account has
    more than one, and persist tokens on success. Returns whether sign-in
    completed.

    On expiry, matches tofa's own apps rather than just giving up: shows a
    "code timed out" state with a "Generate new code" button, and loops
    back into a fresh device code if pressed.

    Font installation is handled centrally by service.py at Kodi startup,
    not here -- sign-in is seen once per user but every screen needs
    fonts."""
    session = http.new_session()
    heading = _(31010)

    try:
        code = _request_code(session)
    except http.ApiError as exc:
        cardoptions.alert(heading, _(31050) % exc.message, error=True)
        return False

    # On-screen caption is "Pair this TV" (matching tofa's Android TV app),
    # distinct from `heading` which stays "Sign in to tofa" for the plain
    # OK-dialog titles used elsewhere in this function.
    dialog = SignInDialog.create(heading=_(31024))
    monitor = xbmc.Monitor()
    device_id = auth.get_or_create_device_id()

    qr_path = None
    granted = None
    error_message = None
    try:
        while True:
            qr_path = _apply_code(dialog, code, qr_path)
            granted, error_message, expired = _poll_until_resolved(session, dialog, code, monitor)
            if granted or error_message or dialog.iscanceled():
                break

            dialog.show_expired()
            while not dialog.iscanceled() and not dialog.retry_requested():
                if monitor.waitForAbort(0.3):
                    break
            if dialog.iscanceled():
                break
            try:
                code = _request_code(session)
            except http.ApiError as exc:
                error_message = exc.message
                break
    finally:
        dialog.doClose()
        if qr_path:
            try:
                xbmcvfs.delete(qr_path)
            except Exception:
                pass

    if error_message:
        cardoptions.alert(heading, _(31015) % error_message, error=True)
        return False
    if not granted:
        _notify(_(31019))
        return False

    # Account-first: the device flow above (no server_id) only grants a
    # short-lived cloud token. List the account's servers, let the user
    # pick one if there's more than one, then exchange for the durable
    # server-scoped token pair -- no second approval needed.
    cloud_access_token = granted["access_token"]
    try:
        server_list = cloud.list_servers(session, cloud.CLOUD_BASE_URL, cloud_access_token)
    except http.ApiError as exc:
        cardoptions.alert(heading, _(31050) % exc.message, error=True)
        return False

    # connect_url is absent for a server that has never come online; it's
    # the address we'll need for every request afterwards, so a server
    # without one isn't a usable choice yet.
    candidates = [s for s in (server_list.get("items") or []) if s.get("connect_url")]
    if not candidates:
        cardoptions.alert(heading, _(31018), error=True)
        return False

    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        # The SAME page the switch uses, not the narrow panel this used to
        # borrow. Pairing and switching ask one question -- "which of your
        # servers?" -- and asking it twice in two different screens is how
        # Adrian met both in one flow on 2026-08-13: Switch Server on an
        # install with no cloud token falls through to pairing, so the page
        # was replaced mid-sentence by the panel.
        #
        # No current_idx: nothing is current yet, so no card is badged.
        from .windows.serverpicker import ServerPickerDialog
        dialog = ServerPickerDialog.open(servers=candidates, eyebrow=_(31022))
        if not dialog or dialog.canceled or dialog.picked_idx is None:
            _notify(_(31019))
            return False
        chosen = candidates[dialog.picked_idx]

    try:
        session_tokens = cloud.create_server_session(session, cloud.CLOUD_BASE_URL, cloud_access_token, chosen["id"])
    except http.ApiError as exc:
        cardoptions.alert(heading, _(31050) % exc.message, error=True)
        return False

    primary, fallback = _pick_server_address(session, chosen)
    # Capture the friendly name here or never: it comes from the cloud's
    # GET /servers, which needs the non-scoped cloud token, and that token
    # is gone the moment this flow ends. Settings > Account shows it.
    # The cloud refresh token goes with it. Same "capture it here or never"
    # reasoning as the name, for a bigger prize: it is what lets Settings >
    # Account mint another cloud token months later and re-run this picker
    # alone, instead of making a viewer with two servers pair again to move
    # between them.
    auth.complete_sign_in(primary, chosen["id"], cloud.CLOUD_BASE_URL, session_tokens, device_id,
                          server_fallback=fallback, server_name=chosen.get("name"),
                          cloud_refresh_token=granted.get("refresh_token"))
    _notify(_(31014))
    return True


def _pick_server_address(session, chosen: dict) -> tuple[str, str | None]:
    """A signed-in-as-owner/admin caller's `GET /servers` entry can carry a
    `connection.local_ip`/`port` alongside the public `connect_url`. Prefer
    the LAN address when it's actually reachable -- many consumer routers
    don't support NAT hairpinning back to their own public address from the
    same LAN, even though it's reachable from outside.
    Returns (primary, fallback) -- fallback is used by MediaServerClient if
    primary later starts failing."""
    remote_url = chosen["connect_url"].rstrip("/")
    connection = chosen.get("connection") or {}
    local_ip, port = connection.get("local_ip"), connection.get("port")
    if not local_ip or not port:
        return remote_url, None

    local_url = f"http://{local_ip}:{port}"
    try:
        http.request_json(session, "GET", f"{local_url}/api/v1/auth/status", timeout=3.0)
        return local_url, remote_url
    except http.ApiError:
        return remote_url, local_url


def _alert_api_error(heading: str, exc: http.ApiError) -> None:
    """Report a failed cloud call. A transport failure (status 0, what
    http.request_json raises a timeout or a refused connection as) says
    nothing about the server and carries a requests exception string no
    viewer can act on, so it gets the plain unreachable line instead."""
    cardoptions.alert(
        heading,
        _(31051) if exc.status == 0 else _(31050) % exc.message,
        error=True,
    )


def _cloud_access_token(session, tok: auth.Tokens) -> str | None:
    """A fresh 15-minute cloud token from the stored cloud refresh token, or
    None if this install cannot mint one at all.

    None is an ordinary answer, not an error: an install paired before the
    cloud refresh token was persisted has none, and a device left off for
    more than the 90-day refresh window has one the cloud has since revoked
    or expired. Both mean the same thing to the caller -- pair again.

    Anything else -- a timeout, a refused connection, a cloud 5xx -- is
    raised, and deliberately NOT folded into that None. Those are temporary
    and say nothing about whether the pairing is still good; answering them
    with "pair again" would talk a viewer into tearing down a working
    pairing because their router hiccuped."""
    if not tok.cloud_refresh_token:
        return None
    try:
        granted = cloud.refresh_cloud(session, tok.connect_url, tok.cloud_refresh_token)
    except http.ApiError as exc:
        # 401 invalid_refresh_token / refresh_token_expired_or_revoked, and
        # 403 email_not_verified: all three end the same way, with the
        # device flow.
        if exc.status in (401, 403):
            return None
        raise
    # Rotation is conditional on the token's age, so this is usually the
    # same string back. Persisting unconditionally is what keeps the chain
    # intact on the runs where it isn't -- a dropped rotation retires the
    # token we still hold, and reusing a retired one revokes the family.
    rotated = granted.get("refresh_token")
    if rotated:
        auth.save_cloud_refresh_token(rotated)
    return granted.get("access_token")


def interactive_switch_server() -> bool:
    """Move this device to another server on the same account without
    re-pairing. Returns whether the server actually changed.

    Pairing is an account-level act -- the device flow proves who you are,
    and the server-scoped token pair is only an exchange made afterwards.
    So switching servers needs nothing the viewer has to approve again: mint
    a cloud token from the refresh token pairing left behind, re-run the
    same picker pairing shows, and exchange for the new server's pair.

    The caller owns the teardown afterwards. Everything cached -- client,
    preferences, theme, profile -- belongs to the old server."""
    session = http.new_session()
    heading = _(31022)

    try:
        tok = auth.load()
    except (auth.NotSignedIn, auth.TokenLoadError):
        return False

    try:
        cloud_token = _cloud_access_token(session, tok)
    except http.ApiError as exc:
        _alert_api_error(heading, exc)
        return False
    if not cloud_token:
        # No usable cloud session: the only way to reach another server is
        # the full device flow. Say so and let the viewer decide, rather
        # than silently starting a pairing they asked not to do.
        if not cardoptions.confirm_pair_again():
            return False
        auth.sign_out()
        return interactive_sign_in()

    try:
        server_list = cloud.list_servers(session, tok.connect_url, cloud_token)
    except http.ApiError as exc:
        _alert_api_error(heading, exc)
        return False

    # Same rule as pairing: a server that has never come online has no
    # connect_url and so is not somewhere this device could go.
    candidates = [s for s in (server_list.get("items") or []) if s.get("connect_url")]
    if not candidates:
        cardoptions.alert(heading, _(31018), error=True)
        return False

    # None, not 0, when the current server isn't in the list -- it may be
    # offline right now and so filtered out above, and defaulting to zero
    # would hang "Current" on whichever server happens to sort first.
    current_idx = next(
        (i for i, s in enumerate(candidates) if s.get("id") == tok.server_id), None)
    # The current server stays IN the list and is marked, rather than being
    # filtered out. A picker that omits it cannot answer "which one am I on
    # now?", which is the first thing a two-server household wants from this
    # screen, and it makes the list's length change depending on where you
    # already are.
    # A SCREEN, not a dialog. The app gives this its own full page --
    # "SWITCH SERVER / Pick where to watch from." -- because picking where
    # your library comes from is not the same weight of choice as picking an
    # audio track. It borrowed PickerDialog's glass panel until 2026-08-13;
    # windows/serverpicker.py is the page itself.
    from .windows.serverpicker import ServerPickerDialog
    dialog = ServerPickerDialog.open(servers=candidates,
                                     current_idx=current_idx)
    if not dialog or dialog.canceled or dialog.picked_idx is None:
        return False
    chosen = candidates[dialog.picked_idx]
    if chosen.get("id") == tok.server_id:
        return False

    try:
        session_tokens = cloud.create_server_session(
            session, tok.connect_url, cloud_token, chosen["id"])
    except http.ApiError as exc:
        _alert_api_error(heading, exc)
        return False

    primary, fallback = _pick_server_address(session, chosen)
    auth.switch_server(primary, chosen["id"], session_tokens,
                       server_fallback=fallback, server_name=chosen.get("name"))
    _notify(_(31056) % (chosen.get("name") or primary))
    return True
