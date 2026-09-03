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
  buffer ahead                               DERIVED, when all three inputs are
                                             real: Player.CacheLevel (how full
                                             Kodi's read-ahead cache is, %),
                                             the cache's configured size
                                             (filecache.memorysize, MB) and the
                                             file's bitrate from the server's
                                             own record. bytes ahead / bytes
                                             per second. Null when any input
                                             is missing -- an HLS session, for
                                             one, buffers inside ffmpeg where
                                             CacheLevel reads 0
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
import json
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


_cache_bytes: Optional[int] = None
_cache_bytes_read = False


def cache_memory_bytes() -> Optional[int]:
    """Kodi's read-ahead cache size, from its own `filecache.memorysize`
    setting (megabytes). Read once per process over the in-process JSON-RPC
    bridge; a setting that cannot be read is None, and stays None."""
    global _cache_bytes, _cache_bytes_read
    if not _cache_bytes_read:
        _cache_bytes_read = True
        try:
            raw = xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Settings.GetSettingValue",
                "params": {"setting": "filecache.memorysize"}}))
            value = (json.loads(raw).get("result") or {}).get("value")
            _cache_bytes = int(value) * 1024 * 1024 if value else None
        except Exception:                                   # noqa: BLE001
            _cache_bytes = None
    return _cache_bytes


def buffer_ahead_ms(level_pct: Optional[int], cache_bytes: Optional[int],
                    bitrate_bps: Optional[int]) -> Optional[int]:
    """How much playback Kodi holds ahead of the demuxer, in milliseconds.

    Player.CacheLevel is the fill of the read-ahead cache as a percentage.
    Multiplied by the cache's size that is bytes; divided by the file's
    bitrate that is time. All three inputs are measurements the box or the
    server actually made -- none is guessed -- which is what makes this
    honest where a bandwidth figure would not be. Any input missing or zero
    is a None, not a 0: a level of 0 means "no cache in use" (HLS buffers
    inside ffmpeg), and 0 ms would read as an empty buffer."""
    if not level_pct or not cache_bytes or not bitrate_bps:
        return None
    return int(round(level_pct / 100.0 * cache_bytes * 8 / bitrate_bps * 1000))


def playback_state(position_ms: int, *, bitrate_bps: Optional[int] = None) -> dict[str, Any]:
    """PlaybackState, from what Kodi reports about the stream it is playing.

    `position_ticks` is 100-nanosecond ticks like every other field on the
    /stream/s/ routes -- see playback.TICKS_PER_MS and the months the
    progress route spent receiving milliseconds. `bitrate_bps` is the
    FILE's bitrate from the server's record, supplied by the monitor; it is
    what turns the cache percentage into a buffer-ahead time."""
    width, height = _number("Player.Process(videowidth)"), _number("Player.Process(videoheight)")
    bitrate = _number("VideoPlayer.VideoBitrate")
    return {
        "position_ticks": int(max(0, position_ms)) * TICKS_PER_MS,
        "video_codec": _label("VideoPlayer.VideoCodec") or None,
        "audio_codec": _label("VideoPlayer.AudioCodec") or None,
        "resolution": f"{width}x{height}" if width and height else None,
        "bitrate_kbps": bitrate if bitrate else None,
        "bandwidth_estimate_bps": None,
        "buffer_ahead_ms": buffer_ahead_ms(
            _number("Player.CacheLevel"), cache_memory_bytes(), bitrate_bps),
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
           bitrate_bps: Optional[int] = None,
           now: Optional[float] = None) -> dict[str, Any]:
    """One TelemetryReport, ready to send."""
    return {
        "type": kind,
        "timestamp_ms": int((now if now is not None else time.time()) * 1000),
        "client": client_info(),
        "playback": playback_state(position_ms, bitrate_bps=bitrate_bps),
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
