# -*- coding: utf-8 -*-
"""Keep Kodi's stereoscopic mode question off our player.

THE PROBLEM, reported 2026-08-10 on the local Kodi with Hugo's 3D edition:
starting a 3D file pops Kodi's own "Select stereoscopic mode" dialog over our
player, and it CANNOT be dismissed -- cancelling just re-raises it. Picking
anything gets playback going, so it is a nuisance rather than a wall, but it
is a stock Kodi dialog in someone else's skin sitting on top of ours, and it
is unavoidable through our UI.

It is not a bug. `videoplayer.stereoscopicplaybackmode` defaults to 0, "Ask
me", on both the local Kodi and the cinema box (measured), and Kodi is doing
exactly what that says.

THE FIX, owner's design: ASK THE SAME QUESTION OURSELVES. Kodi's prompt is
stopped for the length of playback, and our own panel offers the same choices
in our own language -- so "Ask me" is still honoured, and the answer still
comes from the viewer. What changes is that ours can be cancelled, does not
pause playback, and does not look like a different application.

Cancelling leaves the mode alone, which is what Kodi's own cancel is
documented to do (CGUIDialogSelect::IsConfirmed guards SetStereoModeByUser).

MEASURED, 2026-08-10, and the reason this exists: Kodi's dialog took THIRTEEN
Back presses to clear on the local Kodi, with playback never starting -- it
re-raises rather than dismissing.

There IS a way to turn Kodi's prompt off outright, and it is this same
setting: anything other than "Ask me" (Preferred mode / Monoscopic / Ignore).
It sits at ADVANCED level under Player > Videos and reads as a playback mode
rather than as a dialog switch, which is why it is easy to miss.

This writes a GLOBAL Kodi setting, which normally wants asking first
(feedback_consent_before_touching_outside). It is restored on close, and
`restore_stale()` covers the case where a crash or a force-quit meant close
never ran.

The marker is a FILE, not a window property, and that distinction was paid
for: the first cut parked it on Kodi's home window (the trick splash.py uses)
and 2026-08-10 a `kodictl restart` mid-playback proved what that misses. A
window property dies with KODI, so it covers our add-on crashing and nothing
else -- Kodi itself going down is precisely the case where nobody is left to
restore, and the viewer comes back to a setting we changed and never
returned. Measured after that restart: still on Preferred, no marker left to
notice it. A file in our own profile directory outlives both.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import xbmc
import xbmcaddon
import xbmcvfs

from . import log

SETTING = "videoplayer.stereoscopicplaybackmode"

#: videoplayer.stereoscopicplaybackmode
ASK, PREFERRED, MONO, IGNORE = 0, 1, 2, 100

#: Where the viewer's own value is parked while ours is in force. On disk,
#: so it survives Kodi itself dying and can be put back by the next launch.
_SAVED_FILE = "stereo_playbackmode_saved"


def _saved_path() -> str:
    path = xbmcvfs.translatePath(
        xbmcaddon.Addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(path)
    return os.path.join(path, _SAVED_FILE)


def _read_saved() -> Optional[int]:
    path = _saved_path()
    if not xbmcvfs.exists(path):
        return None
    handle = xbmcvfs.File(path)
    try:
        raw = handle.read()
    finally:
        handle.close()
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError):
        # Unreadable is the same as absent, and clearing it stops a corrupt
        # marker from being retried at every single launch from now on.
        _clear_saved()
        return None


def _write_saved(value: int) -> None:
    handle = xbmcvfs.File(_saved_path(), "w")
    try:
        handle.write(str(value))
    finally:
        handle.close()


def _clear_saved() -> None:
    path = _saved_path()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)


def _rpc(method: str, params: Optional[dict] = None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload))).get("result")
    except (ValueError, TypeError, AttributeError) as exc:
        log.debug(f"stereoscopic: rpc {method} failed: {exc!r}")
        return None


def _get() -> Optional[int]:
    result = _rpc("Settings.GetSettingValue", {"setting": SETTING})
    if not isinstance(result, dict):
        return None
    try:
        return int(result.get("value"))
    except (TypeError, ValueError):
        return None


def _set(value: int) -> bool:
    return _rpc("Settings.SetSettingValue",
                {"setting": SETTING, "value": value}) is True


def should_ask() -> bool:
    """Is the viewer on "Ask me"? Then WE ask, in our own panel."""
    return _get() == ASK


def modes() -> list:
    """[{label, mode}] the GUI can actually output on this hardware.

    Asked at runtime, never hard-coded: the cinema box offers four and the
    AM6B+ five, and only the second has `hardware_based` -- which is HDMI
    frame packing, the one mode a 3D projector actually wants."""
    result = _rpc("GUI.GetStereoscopicModes") or {}
    return list(result.get("stereoscopicmodes") or [])


def preferred_label() -> str:
    """The label of videoscreen.preferedstereoscopicmode, e.g. "Same as
    movie" -- so our row can name it the way Kodi's own dialog does."""
    result = _rpc("Settings.GetSettings", {
        "level": "expert",
        "filter": {"section": "system", "category": "display"}}) or {}
    for setting in result.get("settings") or []:
        if setting.get("id") != "videoscreen.preferedstereoscopicmode":
            continue
        value = setting.get("value")
        for option in setting.get("options") or []:
            if option.get("value") == value:
                return option.get("label") or ""
    return ""


def current_mode() -> Optional[dict]:
    """{label, mode} the GUI is on right now, or None."""
    result = _rpc("GUI.GetProperties", {"properties": ["stereoscopicmode"]}) or {}
    mode = result.get("stereoscopicmode")
    return mode if isinstance(mode, dict) else None


def set_mode(mode: str) -> bool:
    """Apply a GUI stereo mode. Kodi puts it back on stop by itself when
    videoplayer.quitstereomodeonstop is true -- which it is by default, and
    on the AM6B+, but NOT on the cinema box, where someone has turned it
    off. Worth knowing before blaming us for a mode that outlived a film."""
    return _rpc("GUI.SetStereoscopicMode", {"mode": mode}) is not None


def suppress_ask() -> None:
    """Stop KODI asking, because we are about to ask instead.

    A no-op unless the viewer is actually on "Ask me": someone who has
    already chosen Preferred, Mono or Ignore has answered the question, and
    overriding that would be us deciding something they decided."""
    current = _get()
    if current is None or current != ASK:
        return
    if not _set(PREFERRED):
        log.warning("stereoscopic: could not suppress the mode prompt")
        return
    _write_saved(current)
    log.info("stereoscopic: mode prompt suppressed for this playback")


def was_suppressed() -> bool:
    """Did WE swap the setting for this playback? Then the viewer is on
    "Ask me" underneath, and our own panel is owed."""
    return _read_saved() is not None


def restore() -> None:
    """Put the viewer's own value back. Safe to call when nothing was saved."""
    value = _read_saved()
    if value is None:
        return
    _clear_saved()
    if _set(value):
        log.info(f"stereoscopic: mode prompt restored to {value}")


def restore_stale() -> None:
    """Called at launch, for the playback that never got to close cleanly.

    Without it a crash mid-film would leave Kodi permanently not asking --
    a quiet, lasting change to someone else's setting, which is exactly what
    the consent rule is about."""
    if _read_saved() is not None:
        log.info("stereoscopic: restoring a value left behind by an earlier run")
        restore()
