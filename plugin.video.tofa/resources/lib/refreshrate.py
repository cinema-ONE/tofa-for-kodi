# -*- coding: utf-8 -*-
"""Let Kodi match the display's refresh rate to the video.

WHY THIS EXISTS. Kodi performs its own refresh-rate switching when it takes
the screen for fullscreen video. This add-on plays with
`Player.play(..., windowed=True)` -- required, because it is what stops Kodi
activating its own FullScreenVideo over our player window (see
windows/player.py's header) -- and Kodi does not switch for windowed
playback. So "Adjust display refresh rate" was simply ignored, however the
viewer had it set. Reported from the box.

HOW IT IS DONE, and why not the obvious way. The obvious way is to write
`videoscreen.screenmode` over JSON-RPC. Measured on the box 2026-08-05 with
the projector ON, that route is a dead end:

  - Kodi applies the mode, then puts up its own "Would you like to keep this
    change?" yes/no dialog, focused on **No**. Nobody presses anything, it
    times out, the mode REVERTS and SetSettingValue returns False. Answering
    Yes programmatically does work -- verified -- but it means flashing a
    stock dialog over our player at every playback start.
  - It also writes the mode PERSISTENTLY. A crash mid-playback would leave
    the viewer's GUI on 24Hz for good.

Kodi's own switching does none of that: it drives the graphics context
directly, leaves `videoscreen.screenmode` alone at "DESKTOP", asks nothing,
and reverts by itself when playback stops. So the job here is not to perform
the switch -- it is to get KODI to perform it.

The lever, measured: Kodi re-evaluates the mode whenever its FullScreenVideo
window is ACTIVATED, not only when a stream starts. Proof, on the box: with
"adjust refresh rate" off, a 25fps file started at 60Hz; turning the setting
on mid-stream changed nothing; leaving and re-entering fullscreen video
switched the display to 25Hz. And the switched mode SURVIVES leaving
fullscreen video again, as long as playback continues.

So player.py bounces through FullScreenVideo for a moment and takes the
window straight back. Kodi does the deciding -- whitelist, allowed doubling,
the "on start" / "on start and stop" preference, the settle delay, and the
revert at the end are all its own, which is exactly what the viewer
configured.

WHAT THIS MODULE DOES, then, is only decide whether a bounce is WORTH it. A
bounce costs a brief flicker, so it must not happen when Kodi would conclude
there is nothing to switch to. The prediction reads the same settings Kodi's
own switching reads:

  videoplayer.adjustrefreshrate     0 off, 1 always, 2 on start/stop, 3 on start
  videoscreen.whitelist             the modes the viewer allows
  videoscreen.whitelistdoublerefreshrate   may 24p use 48Hz, 25p use 50Hz...

A viewer who has switched it off, or whitelisted only 60Hz, gets no bounce at
all -- which is the point of reading the settings instead of having our own.

FOR REFERENCE, plex-for-kodi has the same requirement and answers it
structurally: it plays video fullscreen and overlays its player UI as a
WindowXMLDialog (`SeekDialog(kodigui.BaseDialog)`), so Kodi owns the screen
and every display concern with it -- it closes Kodi's `videoosd` dialog
rather than replacing Kodi's window. Its only `windowed=True` play is
background theme music. Our player is a full WindowXML instead, so the bounce
is what buys the same behaviour without that re-architecture.

MODE STRINGS look like `0384002160059.94006pstd`: width(5) + height(5) +
refresh(%09.5f) + flags. That is the shape the whitelist is stored in.

THE RESOLUTION STAYS PUT. Only the refresh rate is predicted; candidates are
filtered to the current width/height. Kodi's whitelist is also the mechanism
for resolution switching, but changing resolution mid-session on a 4K box
means re-laying out the whole GUI, and this add-on's window would be
re-created underneath the player. The viewer's whitelist still decides WHICH
refresh rates are allowed, so their configuration is honoured; it is the
resolution axis that is deliberately left alone.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import xbmc

from . import log

#: videoplayer.adjustrefreshrate
OFF, ALWAYS, ON_START_STOP, ON_START = 0, 1, 2, 3

#: How close two rates must be to count as the same mode. 23.976 vs 24.000 is
#: a real difference and must NOT collapse; 59.94006 vs 59.94 is rounding.
_RATE_EPSILON = 0.01

#: Comparing a whitelist rate against System.ScreenMode, which is rounded to
#: two decimals: 23.97602 arrives as "23.98". Wide enough to absorb that
#: (0.004), tight enough to keep 23.98 and 24.00 apart (0.02).
_LIVE_EPSILON = 0.015


def _rpc(method: str, params: dict | None = None) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    try:
        raw = xbmc.executeJSONRPC(json.dumps(payload))
        return json.loads(raw).get("result")
    except (ValueError, TypeError) as exc:
        log.debug(f"refreshrate: rpc {method} failed: {exc!r}")
        return None


def setting(name: str) -> Any:
    result = _rpc("Settings.GetSettingValue", {"setting": name})
    return result.get("value") if isinstance(result, dict) else None


_SCREENMODE_RE = re.compile(r"(\d+)\s*x\s*(\d+)\s*@\s*([\d.]+)")


def _screen_mode() -> Optional[tuple[int, int, float]]:
    """System.ScreenMode, e.g. "3840x2160 @ 60.00 - Full Screen"."""
    match = _SCREENMODE_RE.search(xbmc.getInfoLabel("System.ScreenMode") or "")
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), float(match.group(3)))


def current_mode() -> Optional[str]:
    """The mode the display is on NOW, as a whitelist-shaped string.

    Read from System.ScreenMode rather than from `videoscreen.screenmode`,
    because Kodi's native switching does not write the setting -- it stays on
    the symbolic "DESKTOP" throughout. The setting is therefore not the live
    state and never was; the infolabel is. Confirmed on the box, where a
    display sitting at 25Hz still reported the setting as "DESKTOP".
    """
    live = _screen_mode()
    if live:
        return "{0:05d}{1:05d}{2:09.5f}pstd".format(*live)
    stored = setting("videoscreen.screenmode")
    return stored if stored and stored != "DESKTOP" and parse_mode(stored) else None


def live_rate() -> float:
    """The refresh rate the display is running at, or 0.0."""
    live = _screen_mode()
    return live[2] if live else 0.0


def parse_mode(mode: str) -> Optional[tuple[int, int, float, str]]:
    """`0384002160059.94006pstd` -> (3840, 2160, 59.94006, 'pstd')."""
    if not mode or len(mode) < 19 or not mode[:10].isdigit():
        return None
    try:
        return (int(mode[0:5]), int(mode[5:10]), float(mode[10:19]), mode[19:])
    except ValueError:
        return None


def is_rate(mode: str, rate: float) -> bool:
    """Is a live `rate` reading the same mode as the whitelist string `mode`?

    Compares rates, not strings: System.ScreenMode rounds to two decimals, so
    the exact whitelist spelling never comes back verbatim.
    """
    parsed = parse_mode(mode)
    return bool(parsed and rate and abs(parsed[2] - rate) < _LIVE_EPSILON)


def choose(whitelist: list, fps: float, current: str,
           allow_double: bool = False) -> Optional[str]:
    """The whitelisted mode that best suits `fps`, or None to stay put.

    Preference order, which is Kodi's own:
      1. the same rate as the video (23.976 content on a 23.976 display),
      2. an integer multiple if the viewer allows it (24p on 48Hz shows every
         frame twice, still judder-free),
      3. nothing -- staying on a mode the viewer whitelisted beats switching
         to one they did not.

    Only modes at the CURRENT resolution are considered; see the module
    docstring for why the resolution axis is left alone.

    "Already there" returns None too, and is compared by RATE: `current` is
    built from System.ScreenMode's two decimals, so a display already running
    23.976 spells itself `...023.98000pstd` and would not match the
    whitelist's `...023.97602pstd` as a string.
    """
    here = parse_mode(current)
    if not here or not fps or fps <= 0:
        return None
    width, height = here[0], here[1]

    candidates = []
    for mode in whitelist or []:
        parsed = parse_mode(mode)
        if not parsed or parsed[0] != width or parsed[1] != height:
            continue
        candidates.append((mode, parsed[2]))

    for mode, rate in candidates:                      # exact
        if abs(rate - fps) < _RATE_EPSILON:
            return None if is_rate(mode, here[2]) else mode
    if allow_double:
        for multiple in (2, 3, 4):                     # 24 -> 48/72/96
            for mode, rate in candidates:
                if abs(rate - fps * multiple) < _RATE_EPSILON:
                    return None if is_rate(mode, here[2]) else mode
    return None


def delay_s() -> float:
    """videoscreen.delayrefreshchange, in tenths of a second.

    Kodi applies this itself around its own switch. We wait it out a second
    time on our side so the seek that follows a resume lands after the
    display has settled, not during -- a display that has just changed mode
    is blank or resyncing.
    """
    raw = setting("videoscreen.delayrefreshchange")
    try:
        return max(0.0, float(raw) / 10.0)
    except (TypeError, ValueError):
        return 0.0


def would_switch(fps: Optional[float]) -> Optional[str]:
    """The mode Kodi would move the display to for `fps`, or None.

    None means "do not bounce": either the viewer switched refresh-rate
    matching off, or nothing whitelisted suits this stream, or the display is
    already on the right mode. Every one of those is a case where a bounce
    through FullScreenVideo would cost a flicker and change nothing.
    """
    if setting("videoplayer.adjustrefreshrate") in (None, OFF):
        return None
    current = current_mode()
    if not current:
        log.debug("refreshrate: cannot read the current display mode")
        return None
    target = choose(setting("videoscreen.whitelist") or [], fps or 0.0, current,
                    bool(setting("videoscreen.whitelistdoublerefreshrate")))
    if not target:
        log.info(f"refreshrate: {fps}fps on {current}, nothing to switch to")
        return None
    log.info(f"refreshrate: {current} -> {target} for {fps}fps")
    return target
