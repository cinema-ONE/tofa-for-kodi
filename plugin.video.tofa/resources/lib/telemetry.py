# -*- coding: utf-8 -*-
"""Playback telemetry for the server's Activity page.

Server 0.9.35's Activity page shows one line for a Kodi session -- "This
client doesn't report live metrics" -- beside the desktop app's network,
buffer, dropped-frame and stall tiles. The route behind those tiles is
`POST /stream/s/{session_id}/telemetry`, and this module builds what we
send to it.

WHAT KODI CAN AND CANNOT MEASURE, so the report is honest rather than full:

  position, play state, codecs, resolution   yes, from the player's own labels
  stalls (count and duration)                yes, from the position not moving
                                             or Player.Caching, both of which
                                             monitor.py already watches
  time to first frame                        yes, handoff stash to onAVStarted
  bitrate                                    VideoPlayer.VideoBitrate is EMPTY
                                             on most files (probed 2026-08-01),
                                             sent only when Kodi has a number
  buffer ahead                               Player.CacheLevel is a PERCENTAGE
                                             and the schema wants milliseconds;
                                             nothing honest to derive without a
                                             bitrate, so null
  dropped frames                             no InfoLabel exists (grepped
                                             upstream guiinfo/), null
  bandwidth estimate                         nothing measures it, null

A null is a fact ("this client cannot see that"); a made-up number is not.
The reports are built here as plain dicts from plain inputs so a test can
drive them without Kodi; the sending, cadence and back-off live in
monitor.TofaPlayer, which owns the session.

Everything sent stays on the user's own media server -- the same server the
playback position already goes to -- and never reaches tofa. Settings >
Privacy & About says so.
"""
from __future__ import annotations

import ipaddress
import time
from typing import Any, Optional
from urllib.parse import urlsplit

import xbmc

from . import auth, branding, clientinfo, http

#: The server's own vocabulary (TelemetryReportType). A wrong string is a
#: 4xx and a lost report, so these are named once.
PLAYBACK_STARTED = "playback_started"
HEARTBEAT = "heartbeat"
STATE_CHANGE = "state_change"
FATAL_ERROR = "fatal_error"
SESSION_END = "session_end"

#: PlayerWireState.
PLAYING = "playing"
PAUSED = "paused"
BUFFERING = "buffering"

TICKS_PER_MS = 10_000


def _label(name: str) -> str:
    try:
        return (xbmc.getInfoLabel(name) or "").strip()
    except Exception:                                       # noqa: BLE001
        return ""


def _number(name: str) -> Optional[int]:
    """A Player.Process number with Kodi's locale grouping stripped:
    `1,920` -> 1920. Empty or unparseable is None, never 0 -- the schema
    treats null as "unknown" and 0 as a measurement."""
    raw = _label(name).replace(",", "").replace(" ", "").replace(" ", "")
    try:
        return int(float(raw)) if raw else None
    except ValueError:
        return None


def client_info() -> dict[str, Any]:
    """ClientInfo. The same identity http.py sends in X-Tofa-* headers, in
    the shape this route wants; `player_engine` is the one field with no
    header, and it is Kodi's build ("Kodi 21.3"), which is what actually
    decodes the stream."""
    build = _label("System.BuildVersion").split(" ")[0]
    return {
        "type": branding.app_name(),
        "version": branding.app_version(),
        "player_engine": f"Kodi {build}" if build else "Kodi",
        "device_model": clientinfo.device_model() or None,
        "os_version": clientinfo.os_version() or None,
        "user_agent": http.USER_AGENT,
    }


def playback_state(position_ms: int) -> dict[str, Any]:
    """PlaybackState, from what Kodi reports about the stream it is playing.

    `position_ticks` is 100-nanosecond ticks like every other field on the
    /stream/s/ routes -- see playback.TICKS_PER_MS and the months the
    progress route spent receiving milliseconds."""
    width, height = _number("Player.Process(videowidth)"), _number("Player.Process(videoheight)")
    bitrate = _number("VideoPlayer.VideoBitrate")
    return {
        "position_ticks": int(max(0, position_ms)) * TICKS_PER_MS,
        "video_codec": _label("VideoPlayer.VideoCodec") or None,
        "audio_codec": _label("VideoPlayer.AudioCodec") or None,
        "resolution": f"{width}x{height}" if width and height else None,
        "bitrate_kbps": bitrate if bitrate else None,
        "bandwidth_estimate_bps": None,
        "buffer_ahead_ms": None,
        "dropped_frames": None,
    }


def connection_mode(base_url: str) -> Optional[str]:
    """ConnectionWireMode: relay / lan / wan, from the address in use.

    The relay is the one the server can only guess at from its end, which
    is why it is worth telling it. lan vs wan is the host's address class;
    a hostname that is not an IP literal is reported as wan rather than
    resolved, since a DNS lookup on the heartbeat path is not worth what it
    would tell us."""
    if not base_url:
        return None
    if auth.is_relay_url(base_url):
        return "relay"
    host = urlsplit(base_url).hostname or ""
    try:
        return "lan" if ipaddress.ip_address(host).is_private else "wan"
    except ValueError:
        return "lan" if host.endswith(".local") else "wan"


def report(kind: str, *, position_ms: int, state: str,
           qoe: dict[str, Any], base_url: str = "",
           error: Optional[dict[str, Any]] = None,
           now: Optional[float] = None) -> dict[str, Any]:
    """One TelemetryReport, ready to send."""
    return {
        "type": kind,
        "timestamp_ms": int((now if now is not None else time.time()) * 1000),
        "client": client_info(),
        "playback": playback_state(position_ms),
        "player_state": state,
        "connection": connection_mode(base_url),
        "qoe": qoe,
        "error": error,
    }


class QoE:
    """The session's quality-of-experience counters, kept by the monitor.

    Rebuffers are counted on the way IN and their duration on the way OUT,
    so a stall that ends the session still counts once and its duration is
    whatever had elapsed when the report went. `quality_switch_count` and
    `recovery_attempts` stay 0: a quality change here renegotiates a NEW
    session rather than switching within one, and nothing retries a stream
    on the viewer's behalf. Zero is the truth for both, not a placeholder.
    """

    def __init__(self) -> None:
        self.rebuffer_count = 0
        self.rebuffer_duration_ms = 0.0
        self.time_to_first_frame_ms: Optional[float] = None
        self._buffering_since: Optional[float] = None

    @property
    def buffering(self) -> bool:
        return self._buffering_since is not None

    def buffering_began(self, now: float) -> bool:
        """Returns True the first time, so the caller can send one
        state_change per stall rather than one per tick."""
        if self._buffering_since is not None:
            return False
        self._buffering_since = now
        self.rebuffer_count += 1
        return True

    def buffering_ended(self, now: float) -> bool:
        if self._buffering_since is None:
            return False
        self.rebuffer_duration_ms += max(0.0, now - self._buffering_since) * 1000.0
        self._buffering_since = None
        return True

    def as_dict(self, now: Optional[float] = None) -> dict[str, Any]:
        duration = self.rebuffer_duration_ms
        if self._buffering_since is not None and now is not None:
            duration += max(0.0, now - self._buffering_since) * 1000.0
        return {
            "rebuffer_count": self.rebuffer_count,
            "rebuffer_duration_ms": round(duration, 1),
            "time_to_first_frame_ms": (round(self.time_to_first_frame_ms, 1)
                                       if self.time_to_first_frame_ms is not None else None),
            "quality_switch_count": 0,
            "recovery_attempts": 0,
        }
