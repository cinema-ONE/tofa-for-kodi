# -*- coding: utf-8 -*-
"""Honour the viewer's tofa subtitle SIZE on this Kodi.

THE PROBLEM. tofa syncs ten subtitle appearance preferences per profile --
size, vertical offset, text/outline/background colour, bold, outline, and
three that describe tofa's own renderer. Someone who sets their subtitles
larger on the web or Apple TV app gets none of it here: Kodi composites
subtitles itself, from Kodi's own settings.

WHY ONLY THE SIZE. The other nine do not map, and mapping them badly is
worse than not mapping them. Measured against Kodi 22's 29 `subtitles.*`
settings on the cinema box, 2026-09-20:

- `textColor`, `outlineColor` have NO target. The only colour setting
  anywhere in Kodi's settings tree is `lookandfeel.skincolors`.
- `verticalOffsetPercent` looks like `subtitles.marginvertical` and is not.
  tofa's default is 5 and means "the normal resting inset"; Kodi's value
  here was 0.6 on a range of 0..50. Mapping 5 -> 5.0 would move subtitles up
  the screen for someone who never touched the setting -- changing the
  picture in the name of honouring a preference nobody expressed.
- `backgroundColor` could only become `subtitles.backgroundtype`, which
  keeps "is there a background" and throws the colour away.
- `plainText`, `libass`, `libassRenderType` describe tofa's own subtitle
  renderer, and are moot here regardless: we fetch WebVTT and Kodi draws it.
- `bold` -> `subtitles.style` maps cleanly but is not a setting anyone moves.

`sizePercent` is the one people actually change, and it maps honestly: both
sides mean "how big", and 100 means "leave it alone" -- so the common case
writes NOTHING.

WHY THIS IS CAREFUL. `subtitles.fontsize` is a GLOBAL Kodi setting, shared
with every other add-on and outliving our process. That is exactly why this
was not done for a long time, and the objection is a fair one. It is met the
same way stereoscopic.py meets it, for the same reason and with the same
mechanism: the viewer's own value is parked in a FILE in our profile
directory, put back when the player closes, and put back by the next launch
if Kodi itself died before we could. A window property would not do -- it
dies with Kodi, which is precisely the case where nobody is left to restore.

Documented in README.txt, because a global setting we touch is something an
owner should be able to find out about without reading the source.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import xbmc
import xbmcaddon
import xbmcvfs

from . import log

SETTING = "subtitles.fontsize"

#: Kodi's own bounds for it, read off the setting rather than assumed.
MIN_SIZE, MAX_SIZE = 12, 74

#: The percentage that means "the viewer has not asked for anything".
NEUTRAL_PERCENT = 100

#: Where the viewer's own value is parked while ours is in force. On disk,
#: so it survives Kodi itself dying; see the module docstring.
_SAVED_FILE = "subtitle_fontsize_saved"


def _saved_path() -> str:
    path = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("profile"))
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
        # marker being retried at every launch from now on.
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
        log.debug(f"subtitlesize: rpc {method} failed: {exc!r}")
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


def wanted_percent(prefs: Optional[dict]) -> Optional[int]:
    """`subtitles.sizePercent` as an int, or None if it says nothing.

    The blob stores dotted keys as STRINGS, so '100' rather than 100 -- see
    project_preferences_blob_types. Anything unparseable, non-positive or
    absurd is treated as absent: a preference we cannot read is not a
    licence to resize somebody's subtitles.
    """
    if not isinstance(prefs, dict):
        return None
    raw = prefs.get("subtitles.sizePercent")
    if raw is None:
        raw = ((prefs.get("subtitles") or {}).get("sizePercent")
               if isinstance(prefs.get("subtitles"), dict) else None)
    try:
        percent = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not 10 <= percent <= 400:
        return None
    return percent


def scaled(base: int, percent: int) -> int:
    """`base` scaled by `percent`, inside Kodi's own bounds."""
    return max(MIN_SIZE, min(MAX_SIZE, int(round(base * percent / 100.0))))


def apply(prefs: Optional[dict]) -> None:
    """Put the viewer's tofa subtitle size on this Kodi, if they set one.

    A no-op at 100, at an unreadable value, and when nothing changes once
    Kodi's bounds are applied -- all three leave the setting untouched and
    leave no marker, so there is nothing to restore and nothing to go stale.
    """
    percent = wanted_percent(prefs)
    if percent is None or percent == NEUTRAL_PERCENT:
        # Neutral means neutral: if we had applied something earlier in this
        # Kodi run, this is also where it goes back.
        restore()
        return
    base = _read_saved()
    if base is None:
        base = _get()
        if base is None:
            log.debug("subtitlesize: cannot read %s, leaving it alone" % SETTING)
            return
    target = scaled(base, percent)
    if target == base:
        restore()
        return
    if _read_saved() is None:
        _write_saved(base)
    if not _set(target):
        log.warning("subtitlesize: could not set %s" % SETTING)
        _clear_saved()
        return
    log.debug("subtitlesize: %s %d -> %d (%d%%)" % (SETTING, base, target, percent))


def restore() -> None:
    """Put the viewer's own size back. A no-op if we never changed it."""
    saved = _read_saved()
    if saved is None:
        return
    if not _set(saved):
        log.warning("subtitlesize: could not restore %s" % SETTING)
        return
    _clear_saved()
    log.debug("subtitlesize: %s restored to %d" % (SETTING, saved))


def restore_stale() -> None:
    """Called at launch: put it back if a previous run never got to.

    A crash or a force-quit means restore() never ran, and the viewer comes
    back to a size we set and never returned. The marker is a file precisely
    so that it outlives Kodi.
    """
    if _read_saved() is not None:
        log.debug("subtitlesize: a previous run left %s changed" % SETTING)
        restore()
