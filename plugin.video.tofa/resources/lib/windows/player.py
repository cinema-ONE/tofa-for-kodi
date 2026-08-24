# -*- coding: utf-8 -*-
"""Persistent, tofa-branded playback window -- used instead of Kodi's native
fullscreen video player when playback starts from tofa's own window UI.
Kodi's native FullscreenVideo's Back/Esc handling only backgrounds the
player, never stops it, so tofa needs its own window to control that.

A DIALOG OVER KODI'S OWN FULLSCREEN VIDEO, since 2026-08-05. It used to be
a WindowXML that REPLACED Kodi's video window, playing with windowed=True
and carrying its own <control type="videowindow">. That worked, and cost
three faults on the CoreELEC box, all measured:

  - SUBTITLES WERE INVISIBLE. On AMLogic the subtitle overlay belongs to
    Kodi's fullscreen-video layer, and a full-screen WindowXML sits on top
    of it. Proven by holding FullScreenVideo in front of the same live
    stream: subtitles appeared, and vanished again when our window came
    back. On the desktop the video and its overlay are composited into the
    videowindow control INSIDE the window, so the same code looked correct
    there and the bug was invisible to local testing.
  - THE DISPLAY MODE HAD TO BE COAXED. Kodi does not refresh-rate switch for
    windowed playback, so refreshrate.py grew a "bounce" that activated
    FullScreenVideo for a moment to make Kodi re-evaluate. That bounce
    re-negotiated HDMI, which panicked the AMLogic Dolby Vision driver hard
    enough to reboot the box.
  - KODI'S SPINNER APPEARED MID-START, because the bounce parked Kodi's own
    UI on screen for several seconds.

Playing fullscreen hands all of it back to Kodi -- subtitle compositing,
refresh-rate matching, whitelist, settle delay and revert -- and this class
becomes an overlay, the same shape plex-for-kodi uses (SeekDialog over
fullscreen video, closing Kodi's `videoosd` rather than replacing its
window). What we keep is the Back/Esc behaviour that motivated a custom
window in the first place: Kodi's native handling only BACKGROUNDS the
player, never stops it.

Deliberately does not touch addon.py's action_play/setResolvedUrl path or
listing.py -- the plain directory-provider surface must keep working with
zero dependency on resources/lib/windows/. This window only ever opens
directly, in-process, from the window UI's own Play buttons.

Reuses playback.py's negotiation pipeline exactly like addon.py's
action_play, and still calls monitor.stash_pending_session(...) so
monitor.py's TofaPlayer (running in the separate service.py process) keeps
doing progress reporting/session teardown unchanged -- Kodi dispatches
every xbmc.Player callback to every process that registered a Player
subclass, not just the one whose play() call started it. That's what lets
this window's own _PlayerUIPlayer (visual state only) and TofaPlayer
coexist.

------------------------------------------------------------------------
The OSD (TV-DESIGN 8, geometry from internal-docs/atv-reference/)

Chrome is a MODE, not a focus state: while it is hidden, focus parks on the
1x1 control 9001 so onAction() sees raw keys with no focus engine in the
way (10.4's "chrome hidden: left/right seek, anything else reveals"), and
while it is up the focus engine owns the d-pad -- except on the scrubber,
which takes left/right for itself.

The back ladder (10.1) is the reason this class has explicit state at all:
with the transport chrome up, Back NEVER leaves the player. Each press
reduces exactly one thing (pending scrub -> chrome -> playback), and the
carve-out that let a paused player exit early was founder-reverted on tvOS,
so it is deliberately absent here too.

A single 0.2s ticker thread owns everything time-based: the 4.0s chrome
auto-hide, the pause card's further 5.0s, the seek toast's lifetime, and
the scrubber's fill/head position. One thread rather than four timers
because they all read the same clock and all write the same window, and
because a torn-down window must stop all of them at once.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import weakref
import urllib.parse
from typing import Optional

import xbmc
import xbmcgui
import xbmcvfs

from . import kodigui, playerstats, playoptions, profile_select, theme
from .. import (api, artcache, auth, episodes, http, langcodes, log, monitor,
                playback, playbackprefs, playbacksync, prefs, regional,
                stereoscopic, textmetrics, tracks)
from ..api import MediaServerClient
from ..profile import DEFAULT_AUDIO_CODECS, CapabilityProfile

# Window(10000) property guarding against a second PlayerWindow opening --
# open() blocks, so a second call can only come from a stray double-press
# racing the first before it grabs focus.
#
# It has a second reader outside this module: seekbarpatch.py teaches the
# active skin to hide its own seek bar while this is set (there is no API
# for that -- see that module). So the property's LIFETIME is now load-
# bearing. It must be set before playback can raise the skin's seek bar and
# cleared once, on the way out; leaving it set would suppress the seek bar
# for Kodi's own playback too. Renaming it means bumping
# SEEKBAR_PATCH_VERSION, since already-patched skins name it literally.
_REENTRANCY_PROPERTY = "plugin.video.tofa.player_open"

# 10.6's shared constants. These are contracts, not preferences: the same
# numbers are stated for every tofa client, so they may only move together.
SEEK_STEP_MS = 10_000
CHROME_AUTO_HIDE_S = 4.0
PAUSE_CARD_DELAY_S = 5.0
PLAY_PAUSE_DEBOUNCE_S = 0.3
SEEK_TOAST_S = 0.9

# 10.4's scrubber step: clamp(duration/60, 10s, 60s).
SCRUB_STEP_MIN_MS = 10_000
SCRUB_STEP_MAX_MS = 60_000

_TICK_S = 0.2
#: How long after a track choice its outcome is confirmed. Comfortably
#: past Kodi's 1s player-state caches, which is the point of it.
_AUDIO_CONFIRM_S = 2.0

# 8.3's Next Up rail. The countdown is a stated hard contract; the lead is
# "~30s before content end", which the spec allows stretching to 6 minutes
# only when an outro MARKER says where the credits start.
#
# This used to say the server exposed no such marker, and take the 30s
# unconditionally. It does expose one: outro segments arrive on the QuickView
# response that 8.5's skip pill has been reading all along, which is why they
# were not found looking for a /markers endpoint. NEXT_UP_LEAD_S is now the
# FALLBACK and the marker is preferred; see _next_up_reveal_ms.
NEXT_UP_LEAD_S = 30.0
NEXT_UP_LEAD_MARKER_MAX_S = 360.0
NEXT_UP_COUNTDOWN_S = 20.0
# 8.3 asks for focus to land on Play Next "~150-200ms after reveal", i.e.
# after the slide-in, so the button does not appear pre-pressed mid-flight.
NEXT_UP_AUTOFOCUS_S = 0.2
# How long focus stays parked on a button whose own click handler hid it,
# before the tick moves it to the bare surface. See _defer_focus_restore.
#
# NOT one 200ms tick, which is what this was and which lost the race:
# Kodi delivers ONE press twice -- onClick on the Python thread, then
# onAction on the app thread -- and the gap between them was measured at
# ~285ms on the development box (press 22:26:07.760, second dispatch
# 22:26:08.045). A restore that landed inside that gap put the bare
# surface under the second dispatch, which is exactly the pause this
# deferral exists to prevent. 0.6s clears it with room, and the cost is
# the d-pad being inert for that long on a control that is not on screen.
DEFERRED_FOCUS_S = 0.6
# How long after a panel opens the tick keeps re-asserting focus onto it.
# Covers the render pass that makes the panel's group visible, plus a
# reveal_chrome() that lands in the same window. 1.0s is three ticks on a
# box slow enough to need any of them, and it costs nothing when the first
# setFocusId already worked -- the re-assert is skipped once focus is home.
PANEL_FOCUS_GRACE_S = 1.0
#: Sender and message a `JSONRPC.NotifyAll` must carry to reach 8.11, and the
#: one mode word that is not a playerstats state. Kodi prefixes the message
#: with "Other." on the way through -- measured, not assumed.
STATS_NOTIFY_SENDER = "plugin.video.tofa"
STATS_NOTIFY_METHOD = "Other.stats"
STATS_CYCLE = "cycle"
# One frame per 500ms of the countdown; see tools/gen_nextup_assets.py.
NEXT_UP_RING_STEPS = 40

# preferences.playback.auto_play_next (server 0.9.27). The API's own words:
# "A missing key means `auto` ... every client must apply that default."
AUTO_PLAY_NEXT_AUTO = "auto"    # rail + countdown, advances on its own
AUTO_PLAY_NEXT_ASK = "ask"      # rail, no countdown, waits to be pressed
AUTO_PLAY_NEXT_NONE = "none"    # no rail at all
AUTO_PLAY_NEXT_MODES = (AUTO_PLAY_NEXT_AUTO, AUTO_PLAY_NEXT_ASK, AUTO_PLAY_NEXT_NONE)

# 8.1's transport pair. A movie gets -10s/+10s; an EPISODE gets
# previous/next episode, which is what the reference app does -- the seek
# is not lost, 10.4 keeps it on left/right over the bare surface.
_GLYPH_SEEK_BACK = "\uE148"      # rotate-ccw
_GLYPH_SEEK_FWD = "\uE149"       # rotate-cw
_GLYPH_PREV_EPISODE = "\uE15F"   # skip-back
_GLYPH_NEXT_EPISODE = "\uE160"   # skip-forward
# 8.4's disabled treatment, reused for a transport button with nowhere to go.
#: Separator between the episode number and its title on the chrome and the
#: pause card -- the same bullet Detail's info line joins with ("2026 • Sci-Fi
#: • Action"), so one screen does not punctuate differently from the next.
#:
#: A DELIBERATE DIVERGENCE from the reference, which writes a hyphen: the
#: capture at atv-reference/player-chrome-episode.png reads "S1 E2 - Earth
#: Skills" (verified at 2x). Internal consistency was preferred over matching
#: the app here -- see DIVERGENCES.md.
_META_SEP = u" • "


_TRANSPORT_DISABLED = "0x59FFFFFF"

# 8.5's skip pill. The confidence floor is the spec's; the three timings
# are the SERVER's (an operator setting on the QuickView admin page), and
# these are only the fallback for a server too old to send them.
SKIP_MIN_CONFIDENCE = 0.65
SKIP_PROMPT_MIN_DURATION_S = 3
SKIP_MIN_REMAINING_S = 1
SKIP_PROMPT_AUTO_HIDE_S = 8

#: EXPERIMENT, 2026-08-05: hand Kodi the next episode's URL WITHOUT stopping
#: the current one first.
#:
#: WHY. The box runs videoplayer.adjustrefreshrate = 2 ("on start and stop"),
#: so Kodi reverts the display to 60Hz on every stop. An auto-advance between
#: two 25fps episodes therefore costs 25 -> 60 -> 25, and that round trip --
#: not our bounce -- is the flicker and the A/V dropouts reported from the
#: room. Kodi's play() replaces a playing item, so never stopping means never
#: triggering the revert, and refreshrate.would_switch() then finds the
#: display already correct and does not bounce at all.
#:
#: WHAT TO WATCH IF IT MISBEHAVES. The stop is load-bearing for something
#: else: monitor.py's TofaPlayer lives in the service.py process and learns
#: that an episode finished ONLY from Kodi's onPlayBackStopped. If replacing
#: the item does not dispatch that callback, the outgoing episode's final
#: position is never written and its server session is never ended -- it
#: would leak one per episode across a binge. Kodi is believed to stop the
#: previous item internally and dispatch normally, but that is the
#: assumption this experiment is testing, so check the previous episode's
#: watched state and the server's open sessions after a couple of advances.
#:
#: Set False to restore the explicit stop.
NO_STOP_BETWEEN_EPISODES = True
# QuickView reports 100-nanosecond ticks, NOT the milliseconds the progress
# endpoint's position_ticks uses. Two units in one API.
SKIP_TICKS_PER_MS = 10_000

# 8.2's thumbnail preview. The server serves QuickView thumbnails as 10x10
# SPRITE SHEETS, and Kodi cannot crop an image -- so a cell is shown by
# putting the whole sheet, offset, inside a container that clips (verified:
# a grouplist does). The 320-wide track is preferred because its cells are
# exactly the 320x180 bubble 8.2 asks for, and because the 640 track's
# sheets are 6400x3600, past what a TV box's GPU will hold as one texture.
PREVIEW_TILE_WIDTH = 320
# Kodi fetches <texture> URLs itself and cannot send the X-Profile-Token
# header the endpoint requires, so sheets are downloaded by us and handed
# over as file paths.
TILE_CACHE_DIR = "special://temp/tofa-tiles/"

# 8.11's stats readouts refresh once a second, not every tick: they are a
# diagnostic reading, and five updates a second would make the buffer and
# fps figures unreadable flicker.
STATS_REFRESH_S = 1.0

# How long to leave Kodi's video window up waiting for the display to report
# the new refresh rate. A working switch lands in about a second; this is a
# ceiling for the case where the display never gets there, chosen so a failed
# switch is a pause rather than a hang.

# What this client tells the server it can direct-play, as a set, so audio
# ranking can prefer a track that will not have to be transcoded. Derived
# from the constant that is actually SENT, so the two cannot disagree.
_PLAYABLE_AUDIO_CODECS = frozenset(
    c.strip().lower() for c in DEFAULT_AUDIO_CODECS.split(",") if c.strip())

# Scrubber geometry, mirrored from script-tofa-player.xml. Python needs it
# to place the scrub head and centre the floating preview timecode, which
# are the only two controls whose x is not fixed.
_TRACK_X = 20
_TRACK_W = 1880
_TRACK_Y = 937
#: Width of a skip-segment tick. Measured off the real Apple TV app at
#: 1920 wide: 3px, against the 2px it gives a chapter tick. See
#: _render_scrub_markers for why this is a fixed width and not the
#: segment's own duration.
_SEGMENT_TICK_W = 3
# 8.6 states this as a HARD rule: a stall shorter than this never flashes
# UI, so the chip is armed on a deadline rather than shown the moment Kodi
# reports caching.
REBUFFER_DELAY_S = 0.3
# One frame per 5% of Player.CacheLevel; see tools/gen_player_assets.py.
REBUFFER_RING_STEPS = 20
# How long the position may stand still, while not paused, before we treat it
# as a stall and show 8.6's chip -- Kodi's own Player.Caching does not cover a
# source that has stopped answering. Comfortably longer than the ticker's
# 0.2s period so ordinary jitter cannot trip it, and REBUFFER_DELAY_S is
# still applied on top, so the chip appears ~1.3s in.
STALL_CHIP_AFTER_S = 1.0
# How far into a chapter you have to be before "previous chapter" means
# "restart this one" rather than "go back one". plex-for-kodi's own value.
_CHAPTER_BACK_GRACE_MS = 2000
_PREVIEW_W = 240
# 8.2's bubble: "320pt wide 16:9 ... 64pt above the bar".
_PREVIEW_TILE_W = 320
_PREVIEW_TILE_H = 180
# 8.2: "64pt above the bar". The track sits at 937, so the bubble's BOTTOM
# is 873 and its top 180 above that.
_PREVIEW_TILE_Y = 693
# Where the timecode goes when a thumbnail is showing: below the bubble,
# clear of both it and the track. Without a thumbnail it keeps its own
# place, which is where the reference app puts the bare fallback.
_PREVIEW_TIME_Y_WITH_TILE = 878
_PREVIEW_TIME_Y = 840
# The shadow texture carries this much bleed around the bubble.
_PREVIEW_SHADOW_PAD = 40
# Gap between the timecode and the chapter name on the scrub readout.
_SCRUB_READOUT_GAP = 10

# Stats pill geometry. The capsule hugs its text, so Python sizes it: the
# font is monospace, which turns "how wide is this string" into a
# multiplication instead of textmetrics.py's per-character table. 9.6px is
# Roboto Mono's own 0.6em advance at size 16, read out of the TTF.
_STATS_CHAR_W = 9.6
# Side padding has to CLEAR the capsule's own corner, not just separate the
# text from its edge: at 38px tall the cap radius is 19, so anything less
# than that puts the first character inside the curve and reads as touching
# the border.
_STATS_PAD_X = 30
_STATS_MIN_W = 200
_STATS_MAX_W = 1500
_STATS_CENTRE_X = 960


def _actions(*names: str) -> frozenset:
    """The xbmcgui.ACTION_* ids that actually exist in this Kodi.

    xbmcgui exposes a hand-curated subset of Kodi's ActionIDs.h, and which
    names are in it has changed across versions -- this add-on runs on both
    Kodi 21.2 (the apartment Android box) and a Kodi 22 nightly (the
    CoreELEC box). A missing name here would be an AttributeError at import
    time, i.e. no player at all, in exchange for one key binding."""
    ids = set()
    for name in names:
        value = getattr(xbmcgui, name, None)
        if value is None:
            log.warning(f"player: xbmcgui has no {name}, that key stays unbound")
        else:
            ids.add(value)
    return frozenset(ids)


def _format_time(total_ms: int) -> str:
    total_s = max(0, total_ms) // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _stream_label(name: str, index: int) -> str:
    """A track row's label from whatever Kodi calls the stream.

    Kodi hands back the container's raw language tag -- "eng", "ger" -- and
    a list reading "eng / eng / ger" is worse than the reference app's
    "English / English / German" for no reason, so the tag is expanded when
    xbmc can name it. Names that aren't language tags (a titled commentary
    track, say) pass through untouched, and an unnamed stream falls back to
    its position."""
    if not name:
        return f"Track {index + 1}"
    try:
        return xbmc.convertLanguage(name, xbmc.ENGLISH_NAME) or name
    except (RuntimeError, AttributeError, TypeError):
        return name


def _format_remaining(total_ms: int) -> str:
    """"2 h 4 min left" for the pause card -- the reference app's own
    phrasing, which is a duration in words rather than the transport bar's
    bare timecode."""
    minutes = max(0, total_ms) // 60_000
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes} min left"
    return f"{minutes} min left"


class _PlayerUIPlayer(xbmc.Player):
    """UI-only xbmc.Player subclass, one per open PlayerWindow -- drives
    only this window's own visual state (play/pause glyph, the
    opening/buffering overlay, progress refresh on seek/start). Deliberately
    separate from monitor.py's TofaPlayer, which keeps owning progress-
    reporting/session teardown in service.py, unchanged."""

    def __init__(self, window: "PlayerWindow") -> None:
        super().__init__()
        self.window = window

    def onAVStarted(self) -> None:
        # THE ORDER HERE IS LOAD-BEARING. match_refresh_rate() must come
        # first and must finish before anything else runs, because it makes
        # the display change mode and it BLOCKS until that has happened.
        #
        # A display reset tears the renderer down mid-flight, and the two
        # calls below are exactly what it would damage: apply_track_selection
        # switches audio/subtitle streams, and on_playback_started issues the
        # resume seek with a plain seekTime() that nothing verifies landed.
        # Reordering them ahead of the switch, or making the switch
        # asynchronous, reintroduces both.
        #
        # This is not theoretical. plex-for-kodi carries several hundred
        # lines against these two failures -- a seek silently dropped by a
        # "display reset around AVStarted (HDMI/DV mode switch, refresh-rate
        # or HDR change)" so playback runs from the opened position, and
        # setAudioStream() during an active mode switch resetting the
        # position or stalling the AMLogic codec, which is what this box
        # uses. They cannot order it: Kodi performs their switch
        # asynchronously around AVStarted, so their seek races it. We CAN
        # order it, because we ask for the switch ourselves and wait it out.
        # That is the whole reason the bounce is synchronous.
        self.window.setProperty("player_state", PlayerWindow.STATE_PLAYING)
        self.window.match_refresh_rate()
        self.window.apply_track_selection()
        # The metadata fetch and the stream coming up race each other; this
        # covers the order where the fetch won, so the info tag is published
        # once the player will actually accept it.
        self.window.republish_now_playing()
        self.window.on_playback_started()

    def onPlayBackPaused(self) -> None:
        self.window.setProperty("player_state", PlayerWindow.STATE_PAUSED)
        self.window.on_paused()

    def onPlayBackResumed(self) -> None:
        self.window.setProperty("player_state", PlayerWindow.STATE_PLAYING)
        self.window._release_next_up()
        self.window.hide_pause_card()

    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        self.window.refresh_progress()
        # NOT republishing the info tag here, though the "remote shows
        # direct" report reads like a seek problem. Measured 2026-08-05:
        # what the remote reads is Player.GetItem's LABEL, updateInfoTag()
        # does not write that field at all, and the label was wrong from the
        # first frame rather than lost later. The fix is li.setLabel() in
        # playback.apply_now_playing(); a republish here changed nothing.

    def onPlayBackStopped(self) -> None:
        # Catches teardown paths that don't originate from this window's own
        # Back/Stop handling -- e.g. monitor.py's TofaPlayer._check_stall()
        # stopping playback from the separate service.py process. Idempotent
        # (ControlledWindow.closeNow -> doClose just sets flags; the native
        # dismiss is wrapped in try/except) so it's safe even if this window
        # already closed itself via onAction.
        #
        # Except when the window stopped playback ITSELF in order to start it
        # again: a quality change has to renegotiate, and the stop that
        # precedes it is not the session ending. Without this the window tore
        # itself down mid-switch and the new stream carried on playing behind
        # whatever screen was underneath.
        if self.window.is_restarting():
            return
        self.window.closeNow()

    def onPlayBackEnded(self) -> None:
        # A stream that DIES arrives here, not at onPlayBackError: the source
        # stops delivering, the demuxer reports `eof`, and Kodi calls that an
        # ended file. So this callback has to ask whether the end was real.
        #
        # 8.7 is the answer when it wasn't. Measured on the box 2026-08-08:
        # the server froze 11:28 into a 46:21 episode and the viewer got a
        # silent close back to Detail, with #31101 -- written for exactly
        # this -- never once reaching the screen.
        #
        # is_restarting() first, because a Next Up advance and a quality
        # change both end the outgoing stream deliberately and mid-title,
        # which is precisely what ended_prematurely() is built to notice.
        if not self.window.is_restarting() and self.window.ended_prematurely():
            self.window.fail(kodigui.ADDON.getLocalizedString(31101))
            return
        self.window.closeNow()

    def onPlayBackError(self) -> None:
        # 8.7's card rather than a silent close: this is the callback for a
        # stream that would not open at all, which is exactly the case the
        # viewer most needs told about.
        self.window.fail(kodigui.ADDON.getLocalizedString(31100))


def _paired(source: str, output: str) -> str:
    """"1" when a row genuinely has the same fact on both sides.

    The arrow is a claim that one side BECAME the other, so it is drawn only
    where that is true. A row whose output is an em dash has not been
    transformed into nothing; we just cannot read what the display got, and
    "23.976 fps -> —" states the opposite of what is meant. One-sided rows
    (DELIVERY has no output, SYSTEM no source) are the same case."""
    missing = playerstats.MISSING
    return "1" if source and output and source != missing and output != missing else ""


def _seek_amount_label(step_ms: int) -> str:
    """"10s" / "30s" / "1m" / "10m" for the quick-seek toast.

    Minutes once past 60s, because "180s" is arithmetic and "3m" is a
    duration. Exact minutes only -- every rung of Kodi's own seeksteps
    divides evenly, and a "2m30s" would not fit the toast's 140px circle.
    """
    seconds = max(1, int(round(step_ms / 1000.0)))
    if seconds < 60:
        return "%ds" % seconds
    minutes = seconds / 60.0
    return "%dm" % round(minutes) if abs(minutes - round(minutes)) < 0.01 else "%.1fm" % minutes


class _StatsNotifyMonitor(xbmc.Monitor):
    """Receives the `stats` notification and hands it to the player window.

    THE ONLY REMOTE ROUTE INTO 8.11, and it is a notification rather than a
    method because Kodi's JSON-RPC method list is compiled in -- an add-on
    cannot register `tofa.SetStats` at any price. `JSONRPC.NotifyAll` is the
    one channel that carries arbitrary add-on messages.

    Measured against a live Kodi (2026-08-11) rather than assumed, because
    three details here are not what the API docs suggest:

    - **Kodi prefixes the message with `Other.`**, so `message: "stats"`
      arrives as method `Other.stats`.
    - **`data` is always a JSON STRING**, never a dict -- including `'null'`
      when it was omitted and `'"pill"'` when a bare string was sent. It
      always needs json.loads, and that parse has to be defensive: the
      payload is whatever the sender typed.
    - **`sender` is preserved verbatim and is a LABEL, not a credential.**
      Any caller Kodi accepts can claim to be us. Access is Kodi's web
      server's business, not ours: `services.webserverauthentication` gates
      the port and DEFAULTS TO TRUE (checked in Kodi's own
      system/settings/settings.xml, not inferred from a live value -- this
      dev box reads false because it was switched off by hand), and
      `services.webserverssl` encrypts it (default false, cert at
      `special://userdata/server.pem`). Acceptable here, where the worst case
      is an overlay toggling; do NOT reuse this channel for anything that
      needs to be trusted.

    Every add-on hears every notification, so both sender and method are
    matched before anything is read.

    Holds the window WEAKLY. A Monitor lives until Kodi drops it, and a
    strong reference here would keep a closed player window (and its lists,
    and its artwork) alive behind it.
    """

    def __init__(self, window):
        super().__init__()
        self._window_ref = weakref.ref(window)

    def onNotification(self, sender, method, data):
        if sender != STATS_NOTIFY_SENDER or method != STATS_NOTIFY_METHOD:
            return
        window = self._window_ref()
        if window is None:
            return
        mode = _stats_mode_from_notification(data)
        if mode is None:
            return
        log.debug(f"player: stats notification -> {mode!r}")
        window.request_stats_mode(mode)


def _stats_mode_from_notification(data) -> Optional[str]:
    """The requested mode out of a notification's `data`, or None.

    Accepts the documented shape `{"mode": "panel"}` and, because it costs
    one line and someone will inevitably try it, a bare `"panel"`. Anything
    else is ignored rather than guessed at -- a malformed payload must not
    change what is on screen.
    """
    if not data:
        return None
    try:
        payload = json.loads(data) if isinstance(data, (str, bytes)) else data
    except (ValueError, TypeError):
        log.warning(f"player: stats notification with unparseable data {data!r}")
        return None
    if isinstance(payload, str):
        mode = payload
    elif isinstance(payload, dict):
        mode = payload.get("mode")
    else:
        return None
    if not isinstance(mode, str):
        return None
    mode = mode.strip().lower()
    # "off" is spelled "" internally (playerstats.OFF), because it is also
    # the window property's empty state. Translate at the boundary so the
    # documented vocabulary can say "off" like a human.
    if mode == "off":
        return playerstats.OFF
    if mode == STATS_CYCLE or mode in playerstats.CYCLE:
        return mode
    log.warning(f"player: stats notification with unknown mode {mode!r}")
    return None


class PlayerWindow(kodigui.ControlledDialog):
    # No dismissOnClose: that is ControlledWindow's native-window teardown.
    # A dialog's doClose() already removes it, and there is no window
    # underneath of ours to pop by mistake.

    xmlFile = "script-tofa-player.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    STATE_OPENING = "opening"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"

    SURFACE_ID = 9001
    CHROME_GROUP_ID = 9100
    FILL_ID = 9104
    BUFFERED_ID = 9105
    HEAD_ID = 9106
    HEAD_DRAG_ID = 9107
    PREVIEW_ID = 9111
    SCRUBBER_ID = 9110
    BACK10_ID = 9120
    PLAYPAUSE_ID = 9121
    FWD10_ID = 9122
    SUBTITLES_ID = 9130
    AUDIO_ID = 9131
    QUALITY_ID = 9132
    STATS_ID = 9133
    # 9600+ rather than continuing the 92xx/94xx pattern of the groups above:
    # this window already spends 9200 on the quick-seek toast and 9400 on the
    # opening overlay, and a duplicate id in one window makes getControl()
    # return whichever Kodi happened to register first.
    PREVIEW_BUBBLE_IDS = (9112, 9116, 9115)
    # 8.2's scrubber markers: a fixed pool, placed by
    # _render_scrub_markers(). Kodi cannot loop in a skin.
    CHAPTER_TICK_IDS = tuple(range(9820, 9860))
    SEGMENT_TICK_IDS = tuple(range(9860, 9866))
    PREVIEW_SHADOW_ID = 9118
    PREVIEW_CHAPTER_ID = 9119
    PREVIEW_TILE_IDS = (9114, 9117)
    SKIP_PILL_ID = 9750
    SKIP_BUTTON_ID = 9751
    # 4 capsule images, 2 glyph labels, 2 text labels -- all sized and
    # placed by _size_skip_pill(), so the XML's numbers are placeholders.
    SKIP_CAPSULE_IDS = (9752, 9753, 9754, 9755)
    SKIP_GLYPH_IDS = (9756, 9757)
    SKIP_TEXT_IDS = (9758, 9759)
    ERROR_GROUP_ID = 9950
    ERROR_CLOSE_ID = 9951
    PANEL_GROUP_ID = 9900
    PANEL_SHADOW_ID = 9901
    # 8.4's panel is sliced horizontally; PANEL_BG_IDS is kept as the set of
    # every piece, for anything that just wants to find them all.
    PANEL_FILL_TOP_ID = 9902
    PANEL_FILL_MID_ID = 9907
    PANEL_FILL_BOTTOM_ID = 9908
    PANEL_RIM_TOP_ID = 9903
    PANEL_RIM_LEFT_ID = 9909
    PANEL_RIM_RIGHT_ID = 9910
    PANEL_RIM_BOTTOM_ID = 9911
    PANEL_BG_IDS = (9902, 9907, 9908, 9903, 9909, 9910, 9911)
    #: The cap art's own height; the seam sits clear of the 22px arc.
    _PANEL_CAP_H = 24
    PANEL_GLYPH_ID = 9904
    PANEL_TITLE_ID = 9905
    PANEL_LIST_ID = 9906
    DRAWER_GROUP_ID = 9800
    DRAWER_SEASONS_ID = 9801
    DRAWER_EPISODES_ID = 9802
    NEXT_UP_GROUP_ID = 9700
    NEXT_UP_PLAY_ID = 9701
    NEXT_UP_DISMISS_ID = 9702
    NEXT_UP_RING_ID = 9703
    STATS_ROWS_ID = 9620
    STATS_PILL_BG_ID = 9601
    STATS_PILL_OUTLINE_ID = 9602
    STATS_PILL_LABEL_ID = 9603

    EPISODES_ID = 9134
    ADJUST_ID = 9135
    STEREO_ID = 9142
    # Adjust sits between Quality and Stats deliberately. Everything to its
    # left CHANGES what plays; Stats only describes it, and the reference
    # app keeps that one last (rightmost).
    #
    # 3D goes directly after Subtitles and Audio (owner's call, 2026-08-15)
    # because it is the same KIND of choice as those two -- which version of
    # this stream to watch -- rather than a correction applied to whatever
    # is already playing, which is what every remaining Adjust row is. It
    # appears only on a stereoscopic file, so no other capsule changes.
    UTILITY_IDS = (SUBTITLES_ID, AUDIO_ID, STEREO_ID, EPISODES_ID,
                   QUALITY_ID, ADJUST_ID, STATS_ID)

    # The capsule's own background, and the six visuals behind each button
    # (focus fill, focus rim, on fill, then the idle/focused/on glyphs).
    # Every one of them is placed by _layout_utility_capsule(); the XML's
    # coordinates are placeholders.
    UTILITY_BG_IDS = (9145, 9146)
    UTILITY_VISUAL_BASE = {
        SUBTITLES_ID: 9150, AUDIO_ID: 9160, EPISODES_ID: 9170,
        QUALITY_ID: 9180, STATS_ID: 9190,
        # 9136..9141, not the 9200 the pattern above would suggest: 9200 is
        # already the quick-seek toast, and Kodi resolves a duplicate id by
        # silently returning the FIRST control with it.
        ADJUST_ID: 9136,
        # 9210..9215. By the time 3D was added the 91xx band had no run of
        # six left -- 9142..9144 and 9147..9149 are what remains, split by
        # the capsule backgrounds. Same rule as ADJUST above: the block has
        # to be free, not adjacent.
        STEREO_ID: 9210,
    }

    @classmethod
    def open(cls, **kwargs):
        if xbmcgui.Window(10000).getProperty(_REENTRANCY_PROPERTY):
            log.warning("player: already open, ignoring duplicate open() call")
            return None
        return super().open(**kwargs)

    def __init__(self, *args, **kwargs):
        # Popped before super() so they don't reach xbmcgui.WindowXML --
        # same convention as DetailWindow's media_id/discovery_id.
        self.file_id = kwargs.pop("file_id", None)
        self.media_id = kwargs.pop("media_id", None)
        self.season = kwargs.pop("season", None)
        self.episode = kwargs.pop("episode", None)
        self.resume_ms = kwargs.pop("resume_ms", None)
        self.title = kwargs.pop("title", None)
        # Backdrop for 8.6's opening card, handed over by the caller that
        # already resolved it (Detail's hero art). Optional: _load_metadata
        # resolves its own a moment later, but "a moment" is the whole life
        # of the opening card on a fast open.
        self._backdrop = kwargs.pop("backdrop", None)
        self._logo = kwargs.pop("logo", None)
        # 7.7's pre-play picks, or a default Selection when playback was
        # started from somewhere that has no Options panel (an episode row,
        # the plugin listing). Both halves of it are optional, so the default
        # is genuinely "whatever the server and Kodi would have chosen".
        self.selection = kwargs.pop("selection", None) or playoptions.Selection()
        #: Set when THIS window deliberately stops playback (Back), as
        #: opposed to being backgrounded by Kodi's Home button with the film
        #: still running.
        self._stopping = False
        kodigui.ControlledDialog.__init__(self, *args, **kwargs)
        self.client: Optional[MediaServerClient] = None
        self.ui_player: Optional[_PlayerUIPlayer] = None
        # Server stream indices, in order, from the negotiation that started
        # THIS playback -- what apply_track_selection maps the picks through.
        self._audio_order: list = []
        self._subtitle_order: list = []
        self._audio_tracks: list = []
        self._subtitle_tracks: list = []
        # server subtitle index -> the Kodi slot setSubtitles() turned it into,
        # and which server track is on. See _select_subtitle.
        self._loaded_subtitle_slots: dict = {}
        self._active_subtitle_index = None
        # Where to seek once the first frame is up, or None. See
        # _start_playback() for why this can't just be self.resume_ms.
        self._resume_pending_ms: Optional[int] = None

        # ---- OSD state. Everything here is read by _tick() on its own
        # thread and written from onAction(), so each field is a single
        # assignment of an immutable value; there is no compound state that
        # could be observed half-updated.
        self._chrome_deadline = 0.0     # monotonic; 0 = chrome is down
        self._pause_card_deadline = 0.0  # monotonic; 0 = not armed
        self._stream_url = ""           # what play() was handed, for updateInfoTag
        # The one-shot audio confirmation: when to check, and against what.
        # See _confirm_audio_slot.
        self._audio_confirm_at = 0.0    # monotonic; 0 = nothing armed
        self._audio_confirm_slot: Optional[int] = None
        self._toast_deadline = 0.0
        # Seek ladder: which rung, which way, and when the last press was.
        # -1 means "no gesture in progress".
        self._seek_rung = -1
        self._seek_dir: bool | None = None
        self._seek_last_at = 0.0
        self._seek_ladder_cache: tuple | None = None
        # 8.6's mid-playback chip: when the current stall becomes old enough
        # to be worth showing, or 0 when nothing is stalling.
        self._rebuffer_at = 0.0
        #: Stall tracking for 8.6's chip -- see _position_frozen.
        self._frozen_at_ms = -1
        self._frozen_since = 0.0
        self._last_toggle = 0.0
        self._scrub_ms: Optional[int] = None   # pending scrub target
        self._duration_ms = 0
        #: Last position read while the player was still alive -- see
        #: _position_ms. Survives Kodi's teardown so the callbacks that run
        #: after it can still say how far the viewer got.
        self._last_live_position_ms = 0
        #: How far into the FILE this stream's first frame sits, in ms.
        #: Zero on DirectPlay; non-zero when the server cut an HLS session
        #: at a resume offset, because then Kodi's clock reads from zero at
        #: a position that is already this far in. Everything the viewer is
        #: shown adds it back -- see _position_ms.
        self._time_offset_ms = 0
        self._ticker: Optional[threading.Thread] = None
        self._stop_tick = threading.Event()
        # Suspends the auto-hide while a modal picker is up: the chrome must
        # not evaporate underneath a dialog the user opened from it.
        self._modal = False
        # 8.11's stats. The negotiation response is kept whole because the
        # overlay reports what the SERVER decided, which nothing else in this
        # window still has once playback is running.
        self._nego: dict = {}
        self._stats_mode = playerstats.OFF
        self._stats_next_refresh = 0.0
        # Set while this window is deliberately stopping playback in order to
        # start it again (a quality change), so its own stop callback doesn't
        # read as the session ending. Written from onAction/onClick and read
        # on Kodi's player-callback thread, hence a plain flag holding an
        # immutable value, like the OSD deadlines above.
        self._restarting = False
        # 8.3's Next Up. `_next_up` is (episode, file) for the episode that
        # follows this one, or None when there is nothing to queue -- a
        # movie, the last episode of the last season, or a show whose next
        # episode has no playable file yet.
        # 8.10's drawer. `_drawer_media` is the media_detail response the
        # rows are built from, kept so opening the drawer costs no round
        # trip; `_drawer_season` is which season's chip is selected, which
        # is NOT necessarily the season playing once the viewer browses.
        # 8.5's segments, as (kind, start_ms, end_ms) sorted by start. Empty
        # for anything the server has not run QuickView over, which is most
        # of a library right after the feature is switched on.
        # 8.2's tile track for this file, plus the sheet cache state. The
        # loader thread exists only while a file with tiles is playing.
        self._tiles: dict = {}
        # QuickView chapters, as (start_ms, label) sorted by start. The
        # reference app names the chapter under the scrub thumbnail.
        self._chapters: list = []
        self._tile_dir = ""
        self._tile_want = None          # sheet index the UI is asking for
        self._tile_have: set = set()    # sheet indices already on disk
        self._tile_thread: Optional[threading.Thread] = None
        self._tile_wake = threading.Event()
        self._segments: list = []
        self._skip_policy: dict = {}
        # segment_type -> 'ask' | 'skip' | 'none'; see _load_segment_actions.
        self._segment_actions: dict = {}
        self._segment_actions_loaded = False
        self._skip_active: Optional[tuple] = None   # the segment on screen
        self._skip_hide_at = 0.0
        # Segments the viewer has already dismissed or used, so the pill
        # does not come back for the rest of that same segment.
        self._skip_done: set = set()
        # Set by _hide_skip when focus is stranded on the hidden
        # pill; applied by the tick, never inline. See _hide_skip.
        #: (monotonic deadline, control id) for a focus move deferred out of
        #: a click handler; (0.0, None) when nothing is pending. See
        #: _defer_focus_restore.
        self._restore_focus_at = 0.0
        self._restore_focus_from: Optional[int] = None
        # 8.4's selection panel. `_panel_apply` is what to do with the row
        # that gets picked, which differs per opener.
        self._panel_list = None
        self._panel_apply = None
        # Set only while the panel is showing live controls rather than a
        # list of choices; it is also the flag that tells onAction the
        # arrows belong to the focused row.
        self._panel_steppers = None
        # Kodi's subtitle delay has no getter, so this is our shadow of it.
        # It lives on the WINDOW, not the panel, because it has to survive
        # the panel closing and reopening -- and be reset when playback
        # restarts, which is the one thing that moves Kodi's value without
        # us.
        self._subtitle_offset = playbacksync.SubtitleOffset()
        #: A 3D file is playing and the viewer is on "Ask me", so the
        #: stereo panel is owed. Consumed once by offer_stereo_mode().
        self._stereo_pending = False
        self._stereo_saved = False
        # Which control had focus when the panel opened, so closing it can
        # hand focus BACK rather than parking on the bare surface.
        self._panel_opener = None
        #: Deadline until which the tick re-asserts focus on an open panel.
        #: The panel's group is gated on Window.Property(player_panel), and
        #: Kodi refuses focus to a control inside a group it has not made
        #: visible yet -- which it does on the render pass AFTER the one
        #: that sets the property. See _open_panel.
        self._panel_focus_deadline = 0.0
        self._drawer_media: Optional[dict] = None
        self._drawer_season: Optional[int] = None
        self._drawer_seasons = None
        self._drawer_episodes = None
        self._next_up: Optional[tuple] = None
        #: The panel's two row lists, and the shape they were last built for.
        self._stats_rows = None
        self._stats_shape = None
        #: The rail still's image PATH (not URL). Kept so the URL can be
        #: re-minted at reveal -- see _refresh_nextup_still.
        self._nextup_still_path = ""
        # The episode BEFORE this one, for the transport capsule's previous
        # button. Not part of 8.3's rail, which only ever looks forward.
        self._prev_episode: Optional[tuple] = None
        # Whether the rail is UP is separate from whether it is counting
        # down: `ask` mode shows it with no timer, so the deadline alone can
        # no longer answer "is the rail open".
        self._next_up_open = False
        self._next_up_deadline = 0.0   # monotonic; 0 = no countdown running
        #: Seconds left on a countdown parked by a pause; 0 = not held. The
        #: deadline is cleared while this is set, so the tick's countdown
        #: block simply does not run and the ring and label stay where they
        #: were. See _hold_next_up and _release_next_up.
        self._next_up_hold = 0.0
        #: playback.auto_play_next, resolved once -- see _auto_play_next_mode
        self._auto_play_mode: Optional[str] = None
        self._next_up_focus_at = 0.0
        # Set once the viewer dismisses it, so the rail does not reappear on
        # the next tick for the remaining 30 seconds of the episode.
        self._next_up_dismissed = False

    def _get_client(self) -> Optional[MediaServerClient]:
        # Same pattern as DetailWindow/HomeWindow's _get_client -- a fresh
        # session/token check per screen, not shared state.
        #
        # NEVER a PIN pad over video. This runs again on every Next Up
        # advance, so an expired token used to put the pad up at an episode
        # boundary mid-binge -- and a viewer who dismissed it lost the
        # playback too, since a None client closes this window. What an
        # expired token actually costs here is bookkeeping: the stream has
        # its own token, good for 24h. So play on, let the writes 401, and
        # let the prompt happen on a screen where it belongs. The moment the
        # viewer re-enters the PIN anywhere, monitor.py's next heartbeat
        # picks the new token off disk and reporting resumes mid-episode.
        #
        # profile_select.renew_for_playback, called before anything opens
        # this window, is the other side of that bargain: it asks in advance
        # whenever the token would not survive what is starting.
        #
        # No profile resolved AT ALL is different and still asks -- without
        # one the server acts as the primary profile, and writing someone
        # else's watch history is worse than any prompt.
        try:
            session = http.new_session()
            tok = auth.ensure_fresh(session)
            if not tok.profile_id:
                tok = profile_select.ensure_profile_selected(session, tok)
        except (auth.NotSignedIn, profile_select.ProfileCanceled, http.ApiError):
            return None
        return api.client_for(session, tok)

    def onFirstInit(self):
        xbmcgui.Window(10000).setProperty(_REENTRANCY_PROPERTY, "1")
        self.ui_player = _PlayerUIPlayer(self)
        # Kept on the window so it lives exactly as long as the window does:
        # a Monitor with no reference is collected and stops being called.
        self._stats_monitor = _StatsNotifyMonitor(self)
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("accent_pill_fill", theme.accent_with_alpha("3D"))
        # 8.3's countdown track is the accent at 22% (0x38/255).
        self.setProperty("nextup_ring_track", theme.accent_with_alpha("38"))
        # 8.2's buffered range: the accent at 20%.
        self.setProperty("accent_buffered", theme.accent_with_alpha("33"))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        # AFTER text_primary: _apply_transport_mode reads it back for the
        # enabled tint. Up front at all, so the transport is never drawn
        # glyphless in the window before _load_metadata decides this is an
        # episode -- which is also the state a movie, or a title whose
        # metadata fetch failed, stays in for good.
        self._apply_transport_mode(episode=False)
        # Hide the marker pool before the first paint, or all 46 sit stacked
        # at the head of the track until something places them.
        for cid in self.CHAPTER_TICK_IDS + self.SEGMENT_TICK_IDS:
            self._hide_marker(cid)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        # Only this window has a TEXT_STRONG label (8.8's "N min left"), so
        # only this window publishes the property.
        self.setProperty("text_strong", theme.TEXT_STRONG)
        self.setProperty("player_state", self.STATE_OPENING)
        self.setProperty("player_stats", playerstats.OFF)
        self.setProperty("player_title", self.title or "")
        # Before any fetch: the caller's backdrop is the only art the opening
        # card can have on its first frame. _load_metadata overwrites it with
        # its own resolution once the detail response lands.
        self.setProperty("player_backdrop", self._backdrop or "")
        self.setProperty("player_logo", self._logo or "")
        # The "10" set inside the +/-10s buttons' circular arrows. It has to
        # arrive as a property because Kodi reads a BARE NUMERIC <label> as a
        # localized string id, not as text -- the same trap the PIN keypad
        # routes its digits around (profile_select's digit_N properties).
        self.setProperty("player_skip_seconds", str(SEEK_STEP_MS // 1000))
        # 8.8's eyebrow. Also a property rather than $LOCALIZE[31097] in the
        # XML: a script window's $LOCALIZE resolves against Kodi's and the
        # ACTIVE SKIN's string tables, never the add-on's, so 31097 came out
        # as Kodi's own "Channel options". Every other tofa window passes its
        # copy in from Python for the same reason.
        self.setProperty("player_watching_label",
                         kodigui.ADDON.getLocalizedString(31097))
        self.setFocusId(self.SURFACE_ID)
        self._remember_window_id()
        self._start_playback()

    # ------------------------------------------------------------------
    # playback
    # ------------------------------------------------------------------

    def _start_playback(self):
        # Before Kodi opens anything: a 3D file otherwise pops Kodi's own
        # "Select stereoscopic mode" dialog over this window, and cancelling
        # it just re-raises it. See stereoscopic.py -- restored in onClosed.
        stereoscopic.suppress_ask()
        self._stereo_saved = stereoscopic.was_suppressed()
        client = self._get_client()
        if not client:
            self.closeNow()
            return
        self.client = client

        file_id = self.file_id
        if not file_id:
            try:
                file_id = playback.resolve_file_id(client, self.media_id, self.season, self.episode)
            except LookupError as exc:
                # The exception text names a media UUID, which is a
                # developer's sentence. Log that, show a human one.
                log.warning(f"player: no playable file: {exc!r}")
                self.fail(kodigui.ADDON.getLocalizedString(31102))
                return
        self.file_id = file_id
        # Seed the subtitle shadow from what we stored for THIS file. Not a
        # reset: Kodi remembers the offset per file and re-applies it, so
        # zeroing here is what made the panel claim "0.00 s" over subtitles
        # that were visibly shifted. See playbacksync.SubtitleOffset.
        self._subtitle_offset.load(file_id)

        try:
            resp = playback.negotiate(
                client, file_id,
                CapabilityProfile.for_device(
                    max_bitrate=self.selection.max_bitrate,
                    quality_mode=self.selection.quality_mode),
                resume_ms=self.resume_ms)
        except playback.NegotiateTimeout:
            self.fail(kodigui.ADDON.getLocalizedString(31033))
            return
        except http.ApiError as exc:
            # Anything the server says here used to escape onFirstInit
            # entirely, and the window sat on its spinner for ever with
            # nothing said. Back still got the viewer out, so this read as
            # "it just doesn't play" -- the state the renamed Bob's Burgers
            # files were found in. 404 is the one worth naming: the library
            # row is fine and only the file moved, so a scan really does fix
            # it, and saying so beats another shrug.
            log.warning(f"player: negotiate failed: {exc!r}")
            self.fail(kodigui.ADDON.getLocalizedString(
                31119 if exc.status == 404 else 31120))
            return

        if not playback.is_direct(resp):
            # Deliberately NOT a prompt any more. It used to ask before
            # playing anything other than DirectPlay, defaulting to No, from
            # a time when this client existed for exactly one LAN and any
            # transcode meant something had gone wrong. Now that Options can
            # ASK for a lower tier, the dialog fires hardest precisely when
            # the user just chose the thing it is querying -- and a modal
            # that second-guesses an explicit choice is worse than no
            # signalling at all. The honest place for this is the stats
            # overlay, which does not interrupt and is right for the
            # unasked-for case too.
            log.warning(
                f"player: non-DirectPlay: play_method={resp.get('play_method')} "
                f"decision_mode={resp.get('decision_mode')} reasons={resp.get('transcode_reasons')}"
            )

        # WHO APPLIES THE RESUME DEPENDS ON WHAT WE GOT.
        #
        # DirectPlay: US. The whole file arrives and the server's
        # start_position_ticks is only advice, so the window seeks after the
        # first frame. build_list_item() sets a resume point too, and that is
        # genuinely what makes Kodi auto-seek when it opens a file through
        # its OWN play flow -- but not when a script hands play() a
        # ListItem, which silently starts at zero. Hugo sitting 10:36 in
        # restarted from the Paramount logo every time. Two alternatives were
        # measured and both opened at 0:00: info.setResumePoint(), and
        # li.setProperty("resumetime"/"totaltime"). Both are honoured when
        # Kodi RESOLVES a plugin item, not when a script supplies one. So the
        # seek stays.
        #
        # THAT SEEK IS WHY THE ACTIVE SKIN'S PLAYER CONTROLS FLASH UP.
        # Isolated 2026-08-05: Kodi shows DialogSeekBar (and whatever the
        # skin hangs off it -- Estuary adds Custom_1109_TopBarOverlay) for
        # ~3.5s after a seek. Starting from the beginning via Rewatch raises
        # neither; resuming from Continue Watching raises both. See
        # project_directplay_start_offset.
        #
        # HLS (DirectStream or a real transcode): THE SERVER. It cuts the
        # stream at the offset, so the first frame IS the resume point and a
        # seek here would move us a second time. What the client owes instead
        # is bookkeeping: the media clock now reads from zero at a position
        # that is `start_offset_ms` into the file, and everything the viewer
        # sees has to add that back. See _time_offset_ms.
        #
        # This used to be "DIRECT PLAY ONLY" on the belief that the server
        # ignored resume_ticks under a transcode. It never did -- we were
        # sending milliseconds where it wanted 100ns ticks, so every resume
        # asked for a position 10,000x too early and duly got it. Measured
        # and corrected 2026-08-07; see playback.TICKS_PER_MS and issue #7.
        self._time_offset_ms = playback.start_offset_ms(resp)
        self._resume_pending_ms = (
            self.resume_ms if (self.resume_ms and playback.is_direct(resp)) else None)
        self._publish_time_offset()
        if self._time_offset_ms:
            log.info("player: stream starts %dms into the file (server-cut)"
                     % self._time_offset_ms)

        # Same one-shot Window(10000) handoff addon.py's action_play uses --
        # monitor.py's TofaPlayer (in service.py) adopts it on the next
        # onAVStarted regardless of which process called play().
        monitor.stash_pending_session(file_id, self.media_id, resp["session_id"], resp["session_token"])

        # Kept whole, not just as index lists: the in-player Audio/Subtitles
        # pickers build their rows from these through the same tracks.py
        # helpers the pre-play Options panel uses, so a track reads
        # identically on both surfaces.
        self._nego = resp
        self._audio_tracks = list(resp.get("audio_tracks") or [])
        self._subtitle_tracks = list(resp.get("subtitle_tracks") or [])
        self._audio_order = [t.get("index") for t in self._audio_tracks]
        self._subtitle_order = [t.get("index") for t in self._subtitle_tracks]
        self._loaded_subtitle_slots = {}
        self._active_subtitle_index = None
        # (inventory is logged from onAVStarted, once Kodi has opened the file)
        # Now that the negotiation has said what tracks exist, the capsule
        # can drop the buttons with nothing behind them. Repeated when
        # _load_metadata works out whether this is an episode; done here too
        # so a title whose metadata fetch FAILS still gets a correct capsule.
        self._layout_utility_capsule()

        # Whatever the caller already knew, so a remote shows a real title
        # from the first frame rather than the stream URL's last path
        # segment. The full picture follows from _load_metadata().
        li = playback.build_list_item(resp, title=self.title or "")
        # Kept because updateInfoTag() needs the item's path, and
        # getPlayingFile() raises until the open actually completes -- play()
        # only queues it. That is what made the first version of
        # _publish_now_playing() a silent no-op.
        self._stream_url = resp["stream_url"]
        # A confirmation armed by the OUTGOING item must not fire against
        # this one; the new item arms its own from apply_track_selection.
        self._audio_confirm_at = 0.0
        # Ticker up BEFORE the open, so Kodi's busy spinner is closed while
        # it appears rather than after; see _ensure_ticker.
        self._ensure_ticker()
        # FULLSCREEN, not windowed. windowed=True used to suppress Kodi's
        # automatic ActivateWindow(FullScreenVideo) so our window could stay
        # the active one; now we WANT that activation, because Kodi owning
        # the screen is what composites subtitles and matches the refresh
        # rate. See the module docstring.
        self.ui_player.play(resp["stream_url"], li)
        # After play(), not before: play() only queues the open, so this
        # extra round trip overlaps with the stream coming up instead of
        # adding itself to time-to-first-frame.
        self._load_metadata()
        self._load_segments()

    def _load_metadata(self):
        """Subtitle line, synopsis and logo art for the chrome and the pause
        card. Best-effort and non-fatal: a title that can't be described
        still plays, and 8.8's card falls back to a text title when there is
        no logo (which is also what the reference app does)."""
        if not (self.client and self.media_id):
            return
        try:
            media = self.client.media_detail(self.media_id) or {}
        except http.ApiError as exc:
            log.warning(f"player: could not load media metadata: {exc!r}")
            return
        # Same fallback chain detail.py's _year_from uses: `year` is often
        # absent and the date fields carry it instead.
        year = media.get("year") or ""
        if not year:
            date = media.get("release_date") or media.get("air_date") or ""
            if len(date) >= 4 and date[:4].isdigit():
                year = date[:4]

        order, here = self._index_episodes(media)
        if here is not None:
            # Two lines exactly as the reference app writes them (see
            # internal-docs/atv-reference/player-chrome-episode.png): the
            # SHOW on line 1, "S1 E2 - Earth Skills" on line 2. The show
            # name is deliberately absent from line 2 because line 1 already
            # carries it; when there is no show name to put up there, it
            # goes back into line 2 so the episode is never unattributed.
            season, ep = order[here]
            self.season = season.get("season_number")
            self.episode = ep.get("episode_number")
            number = episodes.number_label(
                self.season, self.episode, ep.get("episode_number_end"))
            ep_title = ep.get("title") or self.title or ""
            show = media.get("title") or ""
            if show:
                self.setProperty("player_title", show)
            subtitle = f"{number}{_META_SEP}{ep_title}" if ep_title else number
            # 8.8's pause card describes THIS episode, not the series. The
            # same divergence Detail's hero now carries -- see
            # detail.py:_apply_episode_synopsis for why, and note our only
            # reference capture of this card is a MOVIE (Hugo), so the app's
            # behaviour for an episode here is unknown rather than departed
            # from. Falls back to the show's text when the episode has none.
            episode_overview = (ep.get("overview") or "").strip()
        else:
            if not self.title:
                self.setProperty("player_title", media.get("title") or "")
            kind = "Show" if media.get("media_type") == "tv" else "Movie"
            subtitle = f"{kind}{_META_SEP}{year}" if year else kind
            episode_overview = ""
        self.setProperty("player_subtitle", subtitle)
        self.setProperty(
            "player_synopsis", episode_overview or media.get("overview") or "")
        self.setProperty(
            "player_logo", self.client.resolve_image_url(media.get("logo_path")) or "")
        # 8.6's initial load is a full-screen black field carrying the
        # backdrop art, with the title logo centred on it and an accent
        # spinner. We had the logo and the spinner but never the art, so the
        # opening card was a logo on a flat scrim.
        # Confirmed against the real Apple TV app (captured 2026-08-05): it
        # shows the backdrop at FULL brightness behind the logo.
        self.setProperty(
            "player_backdrop",
            self.client.resolve_image_url(media.get("backdrop_path")) or "")
        self._drawer_media = media
        self._publish_now_playing(media)
        self._resolve_next_up(media)

    def match_refresh_rate(self):
        """Nothing to do any more: KODI matches the refresh rate itself.

        This method, _bounce_through_fullscreen(), the _bouncing guard, the
        once-per-item latch and most of refreshrate.py all existed for one
        reason -- we played with windowed=True, and Kodi does not switch for
        windowed playback. So the display had to be coaxed by activating
        Kodi's FullScreenVideo for a moment and taking the window straight
        back.

        Now playback IS fullscreen and Kodi owns the display, so it applies
        the viewer's "adjust display refresh rate" setting on its own, at the
        right moment, with its own whitelist, doubling, settle delay and
        revert. Three reported faults go with the bounce:

          - the AMLogic Dolby Vision panic, which the bounce provoked by
            re-negotiating HDMI (and re-negotiating it repeatedly, before the
            latch),
          - the "Kodi spinner" at playback start, which was Kodi's own
            FullScreenVideo UI on screen for ~7s because the bounce put it
            there,
          - a chunk of the between-episode flicker.

        Kept as a no-op rather than deleted at every call site, because
        onAVStarted's ordering comment explains why the display work came
        FIRST and that reasoning still needs somewhere to live: the audio
        switch and the resume seek must not race a display reset. Kodi still
        performs one; we simply no longer ask for it.
        """
        return

    def _stream_fps(self) -> float:
        """The decoded frame rate, or 0.0 if it cannot be established.

        Kodi's own readout is authoritative -- it is the rate the renderer is
        actually running at, and it accounts for the container lying. The
        server's display_frame_rate is the fallback for the moment before the
        renderer has settled."""
        # Polled, not read once: onAVStarted fires as soon as AV begins and
        # the renderer has not necessarily published a frame rate yet. Two
        # seconds is far longer than it takes in practice and still short
        # enough that a stream which never reports one does not stall the
        # start.
        for _ in range(20):
            try:
                raw = xbmc.getInfoLabel("Player.Process(videofps)")
                fps = float(str(raw).strip() or 0)
                if fps > 0:
                    return fps
            except (ValueError, TypeError):
                pass
            xbmc.sleep(100)
        chosen = next((f for f in (self._nego or {}).get("files", []) or []
                       if f.get("available")), None) or {}
        try:
            return float(chosen.get("display_frame_rate") or 0)
        except (ValueError, TypeError):
            return 0.0

    def republish_now_playing(self):
        """Re-apply the info tag once AV has started, if metadata is in."""
        if self._drawer_media:
            self._publish_now_playing(self._drawer_media)

    def _publish_now_playing(self, media: dict):
        """Re-describe the playing item now that we know what it is.

        play() is called before the metadata fetch on purpose -- the extra
        round trip would otherwise land on time-to-first-frame -- so the item
        starts out with just a title and is completed here.

        updateInfoTag() wants an item carrying the CURRENT path, which is why
        this rebuilds rather than mutating the one handed to play(); that is
        the same shape plex-for-kodi uses (windows/seekdialog.py).
        """
        if not self.ui_player:
            return
        path = self._stream_url
        if not path:
            try:
                path = self.ui_player.getPlayingFile()
            except RuntimeError:
                return                  # stopped between the fetch and here
        art = {}
        if self.client:
            art = {
                "poster": self.client.resolve_image_url(media.get("poster_path")) or "",
                "fanart": self.client.resolve_image_url(media.get("backdrop_path")) or "",
                "thumb": self.client.resolve_image_url(
                    media.get("poster_path") or media.get("backdrop_path")) or "",
            }
        li = xbmcgui.ListItem(path=path)
        playback.apply_now_playing(
            li, media,
            title=self.getProperty("player_subtitle").split(_META_SEP)[-1]
                  if self.season is not None else (media.get("title") or ""),
            season=self.season, episode=self.episode, art=art)
        try:
            self.ui_player.updateInfoTag(li)
        except (AttributeError, RuntimeError) as exc:
            # updateInfoTag is Kodi 20+; older builds keep what play() set.
            log.debug(f"player: could not update the now-playing tag: {exc!r}")

    # ------------------------------------------------------------------
    # 8.3 -- Next Up

    def _index_episodes(self, media: dict) -> tuple:
        """(running order, index of the episode that is playing).

        Identified by FILE, not by the season/episode numbers: those two are
        optional kwargs and most callers into open() don't pass them (the
        Home rail and the episode grid both hand over a file_id and the
        show's media_id and nothing else). The file id is the one thing
        every caller has, and it is what actually identifies the episode
        that is playing -- which is why this also WRITES self.season /
        self.episode rather than trusting them.

        Specials (season 0) are skipped for the same reason detail.py's
        _next_up_episode skips them: they are not part of the running order,
        so auto-playing one after a finale would be wrong.

        Returns ([], None) for anything that is not an episode of a show
        this response describes."""
        if (media.get("media_type") or "") != "tv":
            return [], None
        order = []
        for season in sorted(media.get("seasons") or [],
                             key=lambda s: s.get("season_number") or 0):
            if (season.get("season_number") or 0) == 0:
                continue
            for ep in sorted(season.get("episodes") or [],
                             key=lambda e: e.get("episode_number") or 0):
                order.append((season, ep))
        here = next(
            (i for i, (_s, ep) in enumerate(order)
             if any(str(f.get("id")) == str(self.file_id)
                    for f in (ep.get("files") or []))),
            None)
        return order, here

    def _resolve_next_up(self, media: dict):
        """Find the episodes either side of this one and dress the chrome.

        Forward feeds 8.3's rail AND the transport's next button; backward
        only the previous button, because the rail never looks back."""
        order, here = self._index_episodes(media)
        if here is None:
            self._apply_transport_mode(episode=False)
            return
        nxt = self._playable(order[here + 1:])
        prv = self._playable(list(reversed(order[:here])))
        self._next_up = nxt
        self._prev_episode = prv
        if nxt:
            self._stage_next_up(media, nxt[0], nxt[1])
        self._apply_transport_mode(episode=True)

    @staticmethod
    def _playable(candidates: list) -> Optional[tuple]:
        """First (season, episode, file) in `candidates` with a playable
        file. Skips over unavailable episodes rather than stopping at the
        first gap -- a show part-way through an import shouldn't lose its
        Next Up because episode 4 hasn't landed yet."""
        for season, ep in candidates:
            avail = [f for f in (ep.get("files") or []) if f.get("available")]
            if avail:
                return (season, ep, avail[0])
        return None

    # ------------------------------------------------------------------
    # 8.7 -- terminal failure
    # ------------------------------------------------------------------

    #: How far short of the declared duration an "ended" stream has to stop
    #: before we call it cut off rather than finished. Generous on purpose:
    #: the cost of guessing wrong in one direction is a card over a finished
    #: episode, and in the other a viewer told nothing at all. A minute
    #: clears every real end -- credits run far longer than that, and
    #: getTime()'s last reading before EOF lands within a second or two.
    PREMATURE_END_MS = 60_000

    def ended_prematurely(self) -> bool:
        """Did this "end" happen far enough from the end to be a dead stream?

        Kodi gives a truncated source and a finished episode the same
        callback. On the box (2026-08-08) the server froze mid-episode, the
        demuxer hit `eof`, and onPlayBackEnded fired at 11:28 of a 46:21
        episode -- indistinguishable, to the code, from the credits rolling.
        The position is the one thing that tells them apart."""
        duration_ms = self._duration_ms or self._resolve_duration_ms()
        if duration_ms <= 0:
            # Nothing to measure against. Treat as a normal end rather than
            # accusing a stream that may well have finished.
            return False
        return self._position_ms() <= duration_ms - self.PREMATURE_END_MS

    def fail(self, body: str, *, title: str = ""):
        """Show 8.7's card and STAY, instead of closing the window.

        Every one of these paths used to end in closeNow(): the window
        vanished and the viewer was returned to wherever they came from
        with no statement that anything had gone wrong, let alone what.
        8.7 is explicit that this surface does not auto-dismiss -- the
        viewer closes it, having read it."""
        if self.getProperty("player_error"):
            return
        log.warning(f"player: terminal failure: {body}")
        try:
            if self.ui_player and self.ui_player.isPlaying():
                self.ui_player.stop()
        except RuntimeError:
            pass
        # Nothing else may be on screen over the card, and the chrome's
        # auto-hide must not fight the focus it is about to take.
        self.close_panel()
        self.close_drawer()
        self._hide_skip(used=True)
        self.setProperty("player_next_up", "")
        self.setProperty("player_pause_card", "")
        self.setProperty("player_state", "")
        # 8.6's chip in particular: the stall that brings us here is the very
        # thing that raised it, so it is always up at this moment, and it is
        # the ticker that would normally take it down -- which has just
        # stopped running for want of a player. Left alone it spins on top of
        # the card, promising a recovery the card is there to rule out.
        self._clear_rebuffer()
        self.hide_chrome()
        self.setProperty(
            "player_error_title",
            title or kodigui.ADDON.getLocalizedString(31098))
        self.setProperty("player_error_body", body)
        # Set here, NOT as $LOCALIZE in the XML: in a script WindowXML that
        # resolves against Kodi's own and the ACTIVE SKIN's string tables,
        # never the add-on's, so 31099 came out as the host skin's "IconWall".
        self.setProperty("player_error_cta", kodigui.ADDON.getLocalizedString(31099))
        self.setProperty("player_error", "1")
        self._modal = True
        try:
            self.setFocusId(self.ERROR_CLOSE_ID)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # 8.4 -- trailing selection panel
    # ------------------------------------------------------------------

    # MEASURED, not the spec's numbers: both captures in
    # internal-docs/atv-reference/ put this panel at x1576 w287 with its
    # bottom at 872, whichever capsule button was pressed -- so it is fixed,
    # not anchored per button. 8.4 says width 440; the app says 287.
    _PANEL_X = 1481
    _PANEL_W = 382
    _PANEL_BOTTOM = 872
    _PANEL_HEADER_H = 60
    _PANEL_PAD = 12
    _PANEL_ROW_H = 72
    #: The gap is built INTO the row layout, not declared beside it -- see
    #: the long comment on list 9906 in the skin source. What the XML has to
    #: match is the pitch below, in its <itemheight> AND in both layout
    #: heights; a list whose height is not a whole number of pitches simply
    #: drops its last row, because Kodi draws floor(height / step) of them.
    _PANEL_ROW_GAP = 10
    # 8.4 says "max scroll 460pt", but the real app grows a long list nearly
    # to the top of the screen before it scrolls -- measured on Wuthering
    # Heights, whose subtitle panel reaches y=8. The cap is that, not 460.
    _PANEL_ROWS_MAX_H = 740
    _PANEL_TOP_MIN = 8
    _PANEL_SHADOW_PAD = 42

    def _open_panel(self, *, title, glyph, rows, selected, apply,
                    steppers=None):
        """Raise 8.4's panel with `rows` = [(label, picked, _, detail)].

        Non-blocking, unlike the PickerDialog it replaces: the panel is part
        of this window, so the pick arrives later through onClick rather
        than as a return value.

        `steppers` turns the same panel into a set of live controls instead
        of a list of choices: a list of dicts, one per row, each carrying
        `nudge(forward)`. Left/right belong to the focused row rather than to
        the focus engine (see onAction), and select means "done" rather than
        "pick this". Everything else about it (geometry, glass, focus
        hand-back) is shared, which is the point of putting it here rather
        than building a second window."""
        # Captured BEFORE we steal focus: this is the capsule button that
        # opened us, and where focus has to land again on close.
        opener = self.getFocusId()
        # ...except for a panel that raises ITSELF. The stereoscopic question
        # comes up off a 3D file, not off a button, so what it captures is
        # the bare surface. Handing THAT back is the exact dead end
        # close_panel documents: it re-raises the chrome first, and the
        # surface has no navigation targets, so the d-pad goes nowhere.
        #
        # Reported 2026-08-10: "pressing BACK, SELECT or ESC closes the
        # dialog, but then nothing (especially player controls) can be
        # focused." Recording no opener drops close_panel through to
        # play/pause, which is where a viewer wants to be anyway once the
        # film has started.
        self._panel_opener = opener if opener != self.SURFACE_ID else 0
        if self._panel_list is None:
            self._panel_list = kodigui.ManagedControlList(
                self, self.PANEL_LIST_ID, 12)
        items = []
        for label, picked, _unused, detail in rows:
            item = kodigui.ManagedListItem(label)
            item.setProperty("detail", detail or "")
            item.setProperty("picked", "1" if picked else "")
            # Swaps the row's second line from the plain detail text to the
            # monospace value flanked by chevrons -- see the itemlayout.
            item.setProperty("stepper", "1" if steppers is not None else "")
            items.append(item)
        self._panel_list.reset()
        self._panel_list.addItems(items)
        self._panel_apply = apply
        self._panel_steppers = steppers
        self.setProperty("player_panel_title", title)
        self.setProperty("player_panel_glyph", glyph)
        self._size_panel(len(items))
        self.setProperty("player_panel", "1")
        # The chrome must not evaporate under a panel opened from it.
        self._modal = True
        self.setFocusId(self.PANEL_LIST_ID)
        self._panel_list.setSelectedItemByPos(max(0, selected))
        # ...and keep asserting it for a moment, because this one call is
        # not enough on a slower box. The list lives inside a group gated on
        # Window.Property(player_panel), set three lines up: Kodi evaluates
        # that condition on its next render pass, and a SETFOCUS that
        # arrives before it does is dropped on the floor -- the control is
        # not focusable yet. Nothing reports the failure; the panel simply
        # comes up with no row highlighted and the d-pad still driving
        # whatever had focus before.
        #
        # The panel is a focus island (every nav target on the list is
        # NAV_STOP), so while it is up, focus belongs on it and nowhere
        # else. That makes the re-assert self-correcting rather than a fight
        # with any other owner. Bounded anyway: a permanent re-assert would
        # quietly paper over a real focus bug instead of surfacing it.
        self._panel_focus_deadline = time.monotonic() + PANEL_FOCUS_GRACE_S

    def _place(self, control_id: int, x: int, y: int, height: int):
        """Position one panel slice, tolerating a control that is not there.

        Silent by design: the panel is built from seven controls now, and a
        missing one should cost a slice, never a traceback mid-playback."""
        try:
            control = self.getControl(control_id)
        except RuntimeError:
            return
        control.setPosition(x, y)
        control.setHeight(height)

    def _size_panel(self, row_count: int):
        """Grow the panel upward from its fixed bottom edge."""
        # Whole pitches only, both here and at the cap: the gap lives inside
        # the row layout, so a height of n rows plus (n-1) gaps is ten pixels
        # short of n steps and Kodi would draw n-1 rows.
        pitch = self._PANEL_ROW_H + self._PANEL_ROW_GAP
        rows_h = min(self._PANEL_ROWS_MAX_H // pitch, row_count) * pitch
        height = self._PANEL_HEADER_H + rows_h + self._PANEL_PAD
        top = max(self._PANEL_TOP_MIN, self._PANEL_BOTTOM - height)
        # The panel is three horizontal slices, not one stretched image: a
        # fixed-height cap at each end carrying the corners, and a flat
        # middle between them. Only the middle is resized, and it has no
        # curvature, so there is nothing to distort. See the skin source.
        cap = self._PANEL_CAP_H
        mid_h = max(0, height - 2 * cap)
        x, right = self._PANEL_X, self._PANEL_X + self._PANEL_W - 1
        for cid in (self.PANEL_FILL_TOP_ID, self.PANEL_RIM_TOP_ID):
            self._place(cid, x, top, height=cap)
        for cid in (self.PANEL_FILL_BOTTOM_ID, self.PANEL_RIM_BOTTOM_ID):
            self._place(cid, x, top + height - cap, height=cap)
        self._place(self.PANEL_FILL_MID_ID, x, top + cap, height=mid_h)
        self._place(self.PANEL_RIM_LEFT_ID, x, top + cap, height=mid_h)
        self._place(self.PANEL_RIM_RIGHT_ID, right, top + cap, height=mid_h)
        try:
            self.getControl(self.PANEL_SHADOW_ID).setPosition(
                self._PANEL_X - self._PANEL_SHADOW_PAD,
                top - self._PANEL_SHADOW_PAD)
            self.getControl(self.PANEL_SHADOW_ID).setHeight(
                height + 2 * self._PANEL_SHADOW_PAD)
            self.getControl(self.PANEL_GLYPH_ID).setPosition(
                self._PANEL_X + 24, top + 12)
            self.getControl(self.PANEL_TITLE_ID).setPosition(
                self._PANEL_X + 58, top + 12)
            rows = self.getControl(self.PANEL_LIST_ID)
            rows.setPosition(self._PANEL_X + self._PANEL_PAD,
                             top + self._PANEL_HEADER_H)
            rows.setHeight(rows_h)
        except RuntimeError:
            pass
        log.debug(f"player: panel top={top} h={height} rows={row_count}")

    def _hold_panel_focus(self, now: float):
        """Keep focus on an open panel for PANEL_FOCUS_GRACE_S after it opens.

        Off entirely once the deadline passes or the panel closes, so this is
        a hand on the tiller for one second, not a permanent owner of focus.
        See _open_panel for the two ways focus goes astray in that second."""
        if not self._panel_focus_deadline:
            return
        if not self.getProperty("player_panel") or now >= self._panel_focus_deadline:
            self._panel_focus_deadline = 0.0
            return
        try:
            if self.getFocusId() != self.PANEL_LIST_ID:
                self.setFocusId(self.PANEL_LIST_ID)
        except RuntimeError:
            pass

    def close_panel(self):
        """Take the panel down and give focus BACK to whatever opened it.

        Parking on the bare surface instead is what the first cut did, and
        it left the chrome up with NOTHING focused: with the chrome up the
        focus engine owns the d-pad, and the park control has no navigation
        targets, so every key did nothing. Four seconds later the chrome
        auto-hid and Back -- finding no rung left to reduce -- walked out of
        the player entirely."""
        if not self.getProperty("player_panel"):
            return
        self.setProperty("player_panel", "")
        self._panel_apply = None
        self._panel_steppers = None
        self._modal = False
        # Whatever this hands focus to below, the tick must not drag it back
        # onto a list that is on its way off screen.
        self._panel_focus_deadline = 0.0
        opener = self._panel_opener
        self._panel_opener = None
        # Fresh deadline first, so what follows can tell whether the chrome
        # is actually still on screen.
        self.anchor_chrome()
        if self._chrome_deadline and opener and opener != self.SURFACE_ID:
            try:
                self.setFocusId(opener)
                return
            except RuntimeError:
                # The capsule can be relaid out under us (a quality change
                # restarts playback), so the opener may no longer exist.
                pass
        if self._chrome_deadline:
            self.setFocusId(self.PLAYPAUSE_ID)
        else:
            try:
                self.setFocusId(self.SURFACE_ID)
            except RuntimeError:
                pass

    def _panel_clicked(self):
        if self._panel_list is None:
            return
        if self._panel_steppers is not None:
            # Select CLOSES the panel. It used to reset the focused row, and
            # that was wrong -- reported from the box as "it snaps back
            # without applying the value". Nothing here needs applying: every
            # press has already gone to the player, so the only thing select
            # can sensibly mean is "done". A key that silently throws away
            # the adjustment you just made reads as the panel refusing it.
            #
            # Resetting a row is still reachable, by stepping back to zero,
            # which is also the only way Kodi will move the subtitle offset.
            self.close_panel()
            return
        if self._panel_apply is None:
            return
        index = self._panel_list.getSelectedPosition()
        apply = self._panel_apply
        self.close_panel()
        if index is not None and index >= 0:
            apply(index)

    # ------------------------------------------------------------------
    # Adjust -- audio and subtitle sync
    #
    # Not a TV-DESIGN section: the reference app has no equivalent, because
    # tvOS corrects neither. It is here because both corrections can only be
    # judged against the picture, which is the one place Kodi's own OSD
    # would have to be opened over ours to reach them.
    # ------------------------------------------------------------------

    def offer_stereo_mode(self):
        """Ask the stereoscopic question ourselves, in our own panel.

        Only when the viewer is on "Ask me" -- anyone who has chosen a fixed
        mode has already answered, and asking again would ignore them. Only
        for a file Kodi has actually detected as stereoscopic, which is the
        same trigger Kodi's own prompt uses.

        Kodi's version pauses playback, cannot be cancelled (thirteen Back
        presses, measured) and is drawn in whatever skin is installed. This
        one runs over the playing film, takes Back for an answer, and offers
        the SAME choices: the viewer's preferred mode, 2D, and whatever else
        this hardware can actually output."""
        if not self._stereo_pending:
            return
        self._stereo_pending = False
        self._open_stereo_panel(start_on_current=False)

    def open_stereo_panel(self):
        """The 3D button in the utility capsule: the same question, on demand.

        Deliberately the same panel the start of playback raises rather than
        a control of its own (owner's call, 2026-08-15). What it replaces was
        a 3D STEPPER in the Adjust panel, and a stepper applied each mode the
        moment it was stepped onto -- so walking from one end of the list to
        the other made the display renegotiate HDMI once per press. A panel
        is asked once and answered once, which is one handshake.

        Opened here it starts on the mode in force rather than on Preferred:
        mid-film the viewer is correcting an answer, not giving a first one.
        """
        self._open_stereo_panel(start_on_current=True)

    def _stereo_panel_rows(self):
        """The 3D panel's rows, and the mode each row would apply.

        `None` in picks is "leave it to Kodi's preferred mode", which is not
        a mode name and so cannot be carried in the same list as one."""
        rows, picks = [], []
        # The preferred mode's NAME goes on the row's second line, not in a
        # parenthetical: "Preferred mode (Same as movie)" measures 325px and
        # the widest mode name only 262, so carrying it inline would have set
        # the whole panel's width off one row. The two-line grammar is
        # already here for exactly this.
        rows.append(("Preferred mode", False, None,
                     stereoscopic.preferred_label()))
        picks.append(None)          # None = leave it to Kodi's preferred mode
        for entry in stereoscopic.modes():
            mode, label = entry.get("mode"), entry.get("label")
            # "Disabled" is what Kodi calls off, which on a 3D file means
            # showing it as it is coded -- side by side, in halves. It is a
            # real answer but not a useful first offer, so it rides along at
            # the end with the rest rather than near the top.
            if not mode or not label:
                continue
            rows.append((label, False, None, ""))
            picks.append(mode)
        return rows, picks

    def _open_stereo_panel(self, *, start_on_current: bool):
        rows, picks = self._stereo_panel_rows()
        selected = 0
        if start_on_current:
            current = (stereoscopic.current_mode() or {}).get("mode")
            # Not `if current` -- a mode named "" would fall through to 0
            # anyway, and `in` on a list holding None is safe either way.
            if current in picks:
                selected = picks.index(current)

        def apply(index):
            if index is None or not (0 <= index < len(picks)):
                return
            mode = picks[index]
            if mode is None:
                # Preferred: hand it back to Kodi by restoring the setting
                # and letting its own machinery apply the preference.
                stereoscopic.restore()
                return
            stereoscopic.set_mode(mode)

        # glasses, the same mark the capsule's own button carries. It was
        # `layers` until 2026-08-15, which is what Collections means
        # everywhere else in the app -- one mark, two meanings.
        self._open_panel(title="3D", glyph="\uE20D", rows=rows,
                         selected=selected, apply=apply)

    def _adjust_rows(self) -> list:
        """The stepper rows that apply to what is playing.

        Audio sync is unconditional -- there is always audio. Subtitle sync
        appears only when subtitles are actually ON: an offset applied to
        nothing on screen is a control that looks broken."""
        rows = []
        # Subtitles first, then audio -- the order the utility capsule puts
        # its own buttons in, two slots to the left. Owner's call: a panel
        # that reverses the row order of the controls beside it makes the
        # viewer re-read it every time.
        try:
            _index, subtitles_on = self._current_stream(subtitles=True)
        except (RuntimeError, TypeError):
            subtitles_on = False
        if subtitles_on:
            rows.append({
                "label": "Subtitle sync",
                "value": self._subtitle_offset.label,
                "nudge": self._subtitle_offset.nudge,
            })
        rows.append({
            "label": "Audio sync",
            "value": self._audio_sync_label,
            "nudge": self._nudge_audio_sync,
        })
        # 3D used to be a third row here, and is now its own button in the
        # utility capsule -- see open_stereo_panel(). It was a STEPPER, and
        # a stepper applies as it steps: every press was a live mode change,
        # and on real hardware each one costs an HDMI renegotiation. Walking
        # a four-mode list to compare two of them meant four handshakes.
        # Owner's call, 2026-08-15.
        #
        # Every row left in here shifts something in TIME again, which is
        # what `timer` used to say before the 3D row arrived. The mark stays
        # `wrench` regardless: it is what the button has looked like for a
        # while and it is not wrong for a panel of corrections.
        return rows

    def _audio_sync_label(self) -> str:
        offset = playbacksync.audio_offset()
        # Between play() and the first frame Kodi has no player to ask. An
        # em dash rather than "In sync", which would be a claim about a
        # stream nobody has measured -- same rule as 8.11's panel.
        if offset is None:
            return u"—"
        return playbacksync.format_offset(offset, playbacksync.AUDIO_STEP)

    def _nudge_audio_sync(self, forward: bool):
        return playbacksync.nudge_audio(playbacksync.audio_offset(), forward)

    def open_adjust_panel(self):
        steppers = self._adjust_rows()
        self._open_panel(
            title="Adjust",
            # wrench: see icon_glyphs.WRENCH. It was `timer` while every row
            # shifted something in TIME; the 3D row ended that.
            glyph="\uE1B1",
            rows=[(row["label"], False, None, row["value"]())
                  for row in steppers],
            selected=0,
            apply=None,
            steppers=steppers,
        )

    def _refresh_stepper_row(self, index: int):
        """Repaint one row's value after a press.

        One property on one row, not a rebuild: rebuilding the list would
        drop the selection onto row 0, and holding right would then walk the
        wrong control."""
        if self._panel_list is None or self._panel_steppers is None:
            return
        try:
            self._panel_list[index].setProperty(
                "detail", self._panel_steppers[index]["value"]())
        except (IndexError, RuntimeError, TypeError) as exc:
            log.warning(f"player: could not repaint stepper row: {exc!r}")

    def nudge_stepper(self, forward: bool) -> bool:
        """Left/right on a focused stepper row. True if it was ours."""
        if self._panel_steppers is None or self._panel_list is None:
            return False
        index = self._panel_list.getSelectedPosition()
        if index is None or not (0 <= index < len(self._panel_steppers)):
            return False
        self._panel_steppers[index]["nudge"](forward)
        self._refresh_stepper_row(index)
        # The chrome must not evaporate mid-adjustment: getting sync right
        # takes several seconds of watching between presses, and the panel
        # going away under the viewer is exactly the wrong moment for it.
        self.anchor_chrome()
        return True

    # ------------------------------------------------------------------
    # 8.5 -- skip intro/outro
    # ------------------------------------------------------------------

    _SKIP_LABELS = {
        "intro": "Skip Intro",
        "outro": "Skip Credits",
        "recap": "Skip Recap",
        "preview": "Skip Preview",
    }

    # ------------------------------------------------------------------
    # 8.2 -- scrub thumbnail preview

    def _load_tiles(self, bundle: dict):
        """Pick a tile track and start the sheet loader.

        Prefers the track whose thumbnails are already the bubble's size, so
        the sheet Kodi holds is as small as it can be; falls back to the
        narrowest track offered."""
        tracks = bundle.get("tiles") or []
        if not tracks:
            return
        track = next(
            (tr for tr in tracks if tr.get("width") == PREVIEW_TILE_WIDTH),
            min(tracks, key=lambda tr: tr.get("width") or 0))
        per_sheet = (track.get("tile_width") or 1) * (track.get("tile_height") or 1)
        if not (track.get("interval_ms") and per_sheet):
            return
        self._tiles = dict(track, per_sheet=per_sheet)
        self._tile_dir = xbmcvfs.translatePath(TILE_CACHE_DIR)
        try:
            os.makedirs(self._tile_dir, exist_ok=True)
        except OSError as exc:
            log.warning(f"player: no tile cache dir: {exc!r}")
            self._tiles = {}
            return
        self.setProperty("player_preview_tiles", "1")
        # tools/gen_nextup_assets.py builds the grid mask for exactly one
        # shape. Anything else keeps square corners, which is honest -- a
        # mismatched mask would round the middle of the picture.
        self.setProperty(
            "player_preview_masked",
            "1" if (track.get("width") == PREVIEW_TILE_WIDTH
                    and track.get("tile_width") == 10
                    and track.get("tile_height") == 10) else "")
        log.debug(f"player: tile track {track.get('width')}x{track.get('height')} "
                  f"grid {track.get('tile_width')}x{track.get('tile_height')} "
                  f"every {track.get('interval_ms')}ms")
        if self._tile_thread is None:
            self._tile_thread = threading.Thread(
                target=self._tile_loop, name="tofa-player-tiles")
            self._tile_thread.daemon = True
            self._tile_thread.start()

    def _load_chapters(self, bundle: dict):
        """Chapter names for the scrub readout.

        Same 100-nanosecond ticks as the segments, NOT the milliseconds the
        progress endpoint uses. A chapter with no title of its own falls
        back to its number, which is what the reference app shows."""
        chapters = []
        for ch in bundle.get("chapters") or []:
            start = int(ch.get("start_ticks") or 0) // SKIP_TICKS_PER_MS
            label = (ch.get("title") or "").strip()
            if not label:
                label = "Chapter {0:02d}".format((ch.get("chapter_index") or 0) + 1)
            chapters.append((start, label))
        self._chapters = sorted(chapters)
        log.debug(f"player: {len(self._chapters)} chapters")

    def _chapter_at(self, position_ms: int) -> str:
        """The last chapter that has started by `position_ms`."""
        label = ""
        for start, text in self._chapters:
            if start > position_ms:
                break
            label = text
        return label

    def _tile_path(self, index: int) -> str:
        return os.path.join(
            self._tile_dir,
            "{0}_{1}_{2}_{3}.jpg".format(
                self.file_id, self._tiles.get("width"),
                self._tiles.get("version") or 0, index))

    def _tile_loop(self):
        """Fetch whichever sheet the scrubber is currently asking for.

        One thread and one WANTED index rather than a queue: a scrub that
        crosses four sheets in a second should fetch the one it ended on,
        not all four. Whatever it was fetching when the target moved is
        simply finished and kept, since it is already paid for."""
        while not self._stop_tick.is_set():
            self._tile_wake.wait(0.5)
            self._tile_wake.clear()
            index = self._tile_want
            if index is None or index in self._tile_have or not self._tiles:
                continue
            path = self._tile_path(index)
            if os.path.exists(path):
                self._tile_have.add(index)
                continue
            try:
                data = self.client.quickview_tile_bytes(
                    self.file_id, self._tiles["width"], index)
            except (http.ApiError, OSError, KeyError) as exc:
                log.debug(f"player: tile sheet {index} failed: {exc!r}")
                continue
            try:
                with open(path, "wb") as fh:
                    fh.write(data)
            except OSError as exc:
                log.warning(f"player: could not cache tile sheet: {exc!r}")
                continue
            self._tile_have.add(index)

    def _render_scrub_markers(self):
        """Lay 8.2's chapter and skip-segment ticks on the track.

        Called once the duration is known, not per tick: nothing here moves
        while a title plays.

        BOTH ARE TICKS AT A POSITION, not spans. A segment used to be drawn
        as a band covering its own duration, on the reasoning that this made
        it read as a stretch of film rather than a point in it. That was an
        inference, never measured, and it is wrong on both counts:

          - 8.2 draws a skip segment as an amber TICK the full height of
            the bar, and
          - the real app agrees. Captured off the Apple TV's HDMI mid-episode
            (Murder, She Wrote S1E3, internal-docs/atv-reference/
            player-scrubber-segments.png): two amber marks, each 3px wide and
            spanning the full 11px track height, one at the intro and one at
            the outro. That episode's intro runs 29.8s to 75.1s of 46:21,
            which is 1.63% of the track -- about 30px here. The app draws 3.

        Both pools are finite, so a disc rip with more chapters than the
        pool shows the first N of them rather than none."""
        if not self._duration_ms:
            return
        scale = float(_TRACK_W) / self._duration_ms

        def place(control_id, x, width):
            try:
                control = self.getControl(control_id)
            except RuntimeError:
                return
            control.setPosition(_TRACK_X + x, _TRACK_Y)
            control.setWidth(max(2, width))
            control.setVisible(True)

        for i, cid in enumerate(self.SEGMENT_TICK_IDS):
            if i >= len(self._segments):
                self._hide_marker(cid)
                continue
            _kind, start, _end = self._segments[i]
            place(cid, int(start * scale), _SEGMENT_TICK_W)
        chapters = self._chapters[:len(self.CHAPTER_TICK_IDS)]
        if len(self._chapters) > len(chapters):
            log.debug(f"player: {len(self._chapters)} chapters, showing "
                      f"{len(chapters)} ticks")
        for i, cid in enumerate(self.CHAPTER_TICK_IDS):
            if i >= len(chapters):
                self._hide_marker(cid)
                continue
            start = chapters[i][0]
            # A tick at 0 sits under the track's own rounded cap and reads
            # as a nick in the edge rather than a marker.
            if start <= 0:
                self._hide_marker(cid)
                continue
            place(cid, int(start * scale), 2)

    def _hide_marker(self, control_id: int):
        """Hide one marker -- and HIDE it, do not park it off-screen.

        The pool used to be parked at x=-50 instead, because a static
        `<visible>false</visible>` in the XML is a CONDITION that Kodi keeps
        re-evaluating, so `setVisible(True)` could never win against it and
        the whole pool stayed invisible however it was placed. True, but the
        conclusion was wrong: the fix for that is to leave the tag OUT, which
        these controls already do. With no condition to re-evaluate, the
        Python call stands in both directions.

        Parking leaked. Kodi's GUI zoom (Settings > Interface > Skin > Zoom)
        scales the whole skin about the centre, so anything just off the edge
        comes back on screen below 100%: at -10%, skin x=-50 lands at
        960 + (-50 - 960) * 0.9 = 51. Reported as "a white tick left of the
        scrub bar, only visible when zoom is under 100%", and reproduced
        locally at exactly that pixel -- 40 chapter ticks at 35% white plus
        every unused segment tick, stacked on one spot, which is why
        something built from 2px translucent marks read as a solid nick.
        """
        try:
            self.getControl(control_id).setVisible(False)
        except RuntimeError:
            pass

    def _place_scrub_readout(self, centre_x: int, position_ms: int, y: int):
        """Centre "17:43 Chapter 02" as a UNIT under the bubble.

        Two labels rather than one, because the reference app gives the
        timecode and the chapter name different weights -- and two labels
        mean Python has to measure them to centre the pair, since Kodi
        cannot size a control to its own text."""
        chapter = self._chapter_at(position_ms) if self._chapters else ""
        self.setProperty("player_scrub_chapter", chapter)
        time_text = self.getProperty("player_scrub_time")
        time_w = self._readout_width(time_text)
        chapter_w = self._readout_width(chapter) if chapter else 0
        total = time_w + (_SCRUB_READOUT_GAP + chapter_w if chapter else 0)
        left = centre_x - total // 2
        try:
            self.getControl(self.PREVIEW_ID).setPosition(left, y)
            self.getControl(self.PREVIEW_ID).setWidth(time_w + 8)
            self.getControl(self.PREVIEW_CHAPTER_ID).setPosition(
                left + time_w + _SCRUB_READOUT_GAP, y)
        except RuntimeError:
            pass

    @staticmethod
    def _readout_width(text: str) -> int:
        """Rendered width in tofa_font_row_title (semibold 26).

        textmetrics measures inter_tight_REGULAR at 23, so this scales by
        size and by the same 1.05 the skip pill uses for semibold -- the two
        labels only have to be centred, not typeset, so a pixel either way
        does not show."""
        if not text:
            return 0
        return int(round(
            textmetrics.text_width(text) * (26.0 / textmetrics.SIZE) * 1.05))

    def _refresh_preview(self, position_ms: int):
        """Point the bubble at the cell covering `position_ms`.

        The whole sheet goes in an image that is deliberately far bigger
        than its container, offset so the wanted cell lands in the window --
        Kodi has no source rectangle, and a grouplist clips."""
        if not self._tiles or self._scrub_ms is None:
            # Only while a scrub is actually pending: the bubble is hidden
            # otherwise, and fetching sheets for a position nobody is
            # looking at would pull megabytes per title for nothing.
            return
        position_ms = max(0, position_ms)
        interval = self._tiles["interval_ms"]
        per_sheet = self._tiles["per_sheet"]
        cols = self._tiles.get("tile_width") or 1
        total = self._tiles.get("thumbnail_count") or 0
        idx = position_ms // interval
        if total:
            idx = min(idx, total - 1)
        sheet, cell = divmod(idx, per_sheet)
        self._tile_want = sheet
        self._tile_wake.set()
        if sheet not in self._tile_have:
            # Not on disk yet: 8.2's timecode-only fallback carries the
            # scrub until it is.
            self.setProperty("player_preview_ready", "")
            return
        cell_w = self._tiles["width"]
        cell_h = self._tiles["height"]
        row, col = divmod(cell, cols)
        for cid in self.PREVIEW_TILE_IDS:
            try:
                self.getControl(cid).setPosition(-col * cell_w, -row * cell_h)
            except RuntimeError:
                return
        self.setProperty("player_preview_image", self._tile_path(sheet))
        self.setProperty("player_preview_ready", "1")

    def _load_segments(self):
        """8.5's detected segments and 8.2's tile track, in one request.

        Best-effort and non-fatal, like the metadata load: a server that has
        never run QuickView returns an empty list and the pill simply never
        appears -- which is most of a library for a while after the feature
        is switched on."""
        if not (self.client and self.file_id):
            return
        try:
            resp = self.client.quickview(self.file_id) or {}
        except http.ApiError as exc:
            log.debug(f"player: no quickview data: {exc!r}")
            return
        # 8.2's tiles and its chapter names ride along in the same response.
        self._load_tiles(resp)
        self._load_chapters(resp)
        self._skip_policy = resp.get("skip_policy") or {}
        self._load_segment_actions()
        min_duration = self._policy("prompt_min_duration_secs",
                                    SKIP_PROMPT_MIN_DURATION_S) * 1000
        segments = []
        # The BUNDLE keys these `segments`; the segments-only endpoint keys
        # them `items`. Both are read so this cannot break again if the
        # request is ever pointed back at the narrower one.
        for seg in resp.get("segments") or resp.get("items") or []:
            confidence = seg.get("confidence")
            # A null confidence means the provider does not score itself,
            # not that it scored zero -- those are kept.
            if confidence is not None and confidence < SKIP_MIN_CONFIDENCE:
                continue
            start = int(seg.get("start_ticks") or 0) // SKIP_TICKS_PER_MS
            end = int(seg.get("end_ticks") or 0) // SKIP_TICKS_PER_MS
            if end - start < min_duration:
                continue
            segments.append(((seg.get("segment_type") or "").lower(), start, end))
        self._segments = sorted(segments, key=lambda s: s[1])
        if self._segments:
            log.debug(f"player: skip segments {self._segments}")
        # Harmless if the duration is not known yet; on_playback_started
        # calls it again once it is.
        self._render_scrub_markers()

    def _policy(self, key: str, fallback: int) -> int:
        value = self._skip_policy.get(key)
        return fallback if value is None else int(value)

    def _load_segment_actions(self):
        """What the viewer wants done with each segment TYPE.

        `preferences.playback.segment_actions`, the same object Settings >
        Playback & Video writes. Values are `ask` / `skip` / `none` -- NOT
        `play`; the Apple TV app labels the third one "Play", but the stored
        value is `none` and the server drops anything else.

        Absent means `ask`, which is both the server's own default and the
        safer one: prompting is undoable, auto-skipping is not.

        Fetched once per player SESSION, not per title: _start_playback runs
        again for every episode of a binge (play_next_up reuses it), and this
        is a whole extra round trip to say the same thing each time. A
        preference changed mid-binge is therefore not picked up until the
        player is reopened -- which is the behaviour we want anyway, since a
        setting changed elsewhere should not start silently skipping under
        someone mid-episode.

        Only a SUCCESSFUL read latches; a server that was unreachable at the
        first episode gets asked again at the next."""
        if self._segment_actions_loaded or not self.client:
            return
        try:
            prefs = (self.client.whoami() or {}).get("preferences") or {}
        except http.ApiError as exc:
            log.debug(f"player: no segment actions: {exc!r}")
            return
        self._segment_actions_loaded = True
        actions = (prefs.get("playback") or {}).get("segment_actions") or {}
        self._segment_actions = {
            str(k).lower(): str(v).lower()
            for k, v in actions.items() if isinstance(v, str)
        }
        log.debug(f"player: segment actions {self._segment_actions}")

    def _segment_action(self, kind: str) -> str:
        action = self._segment_actions.get(kind, "ask")
        return action if action in ("ask", "skip", "none") else "ask"

    def _tick_rebuffer(self, now: float):
        """8.6's mid-playback chip, held back 300ms.

        Only while playback is actually up: the initial load has its own
        full-screen overlay, and showing both would put a chip on top of
        it."""
        if self.getProperty("player_state") == self.STATE_OPENING:
            return
        # Always evaluate the freeze, even when Kodi is caching, so the
        # tracking stays current and does not fire the moment caching ends.
        frozen = self._position_frozen(now)
        refilling = xbmc.getCondVisibility("Player.Caching")
        if not (refilling or frozen):
            self._clear_rebuffer()
            return
        if not self._rebuffer_at:
            self._rebuffer_at = now + REBUFFER_DELAY_S
        elif now >= self._rebuffer_at:
            self.setProperty("player_rebuffer", "1")
            # The determinate ring needs real progress to be about. Kodi
            # refilling a buffer has that; a source that has stopped
            # answering does not -- Player.CacheLevel just drains and sits
            # there, so the ring hangs at whatever it last read and reads as
            # frozen rather than busy. Reported from the box: "spinner is up,
            # but it's not spinning". The indeterminate spinner is the honest
            # variant for a stall, and it keeps turning.
            self.setProperty("player_rebuffer_ring",
                             self._rebuffer_ring() if refilling else "")

    def _clear_rebuffer(self) -> None:
        """Take 8.6's chip down and disarm its delay."""
        self._rebuffer_at = 0.0
        self.setProperty("player_rebuffer", "")
        self.setProperty("player_rebuffer_ring", "")

    def _position_frozen(self, now: float) -> bool:
        """Has the clock stopped moving while we are supposedly playing?

        `Player.Caching` is Kodi telling us it is refilling a buffer. It is
        NOT true for a source that has simply stopped answering: on the box
        2026-08-08 the server froze mid-episode, the picture stopped, and
        Kodi reported no caching at all -- so 8.6's chip never appeared and
        the viewer sat in front of a black screen with nothing on it.

        A position that will not advance is the signal Kodi does not give us.
        It means the same thing to the viewer as a rebuffer -- "it has
        stopped, it may come back" -- so it gets the same chip, and 8.7's
        card takes over if it never does come back
        (monitor.STALL_TIMEOUT_SECONDS).

        Paused is not frozen: the clock is meant to stand still there."""
        if self.getProperty("player_state") == self.STATE_PAUSED:
            self._frozen_since = 0.0
            return False
        pos = self._position_ms()
        if pos != self._frozen_at_ms:
            self._frozen_at_ms = pos
            self._frozen_since = now
            return False
        if not self._frozen_since:
            self._frozen_since = now
            return False
        return now - self._frozen_since >= STALL_CHIP_AFTER_S

    @staticmethod
    def _rebuffer_ring() -> str:
        """8.6's determinate variant, or "" to fall back to the spinner.

        Player.CacheLevel is how full the engine's buffer is, which is the
        one "rebuffer progress" Kodi reports. A 0 is treated as no reading
        rather than as an empty buffer: it is also what the label gives when
        it has nothing to say, and a ring frozen at zero would claim to know
        something it does not."""
        try:
            level = int(xbmc.getInfoLabel("Player.CacheLevel") or 0)
        except ValueError:
            return ""
        if level <= 0:
            return ""
        step = max(1, min(REBUFFER_RING_STEPS,
                          round(REBUFFER_RING_STEPS * level / 100.0)))
        return f"rebuffer-ring/{step}.png"

    def _tick_skip(self, now: float, position_ms: int):
        """Raise the pill exactly at a segment's start, and drop it again at
        the segment's end or after the operator's auto-hide, whichever comes
        first.

        THE NEXT UP RAIL OUTRANKS THE PILL. Both surfaces describe the same
        moment near the end of an episode -- 8.3 opens the rail around 30s
        from the end of the content when no outro marker exists, and 8.5
        raises the pill at the segment's own start, which for an outro is the
        same seconds. They also
        occupy the same screen: the rail is x1140..1920 full height, the pill
        sits at y952 inside x1700..1900, i.e. underneath it.

        So with both live the pill was drawn behind the rail AND unreachable,
        because the rail owns the d-pad. Reported from the box as "Skip
        Credits cannot be reached while Up Next is displayed".

        The rail wins because it strictly dominates: its Play Next does what
        Skip Credits does at the tail of a file (take_skip's own last branch
        advances the episode) and more. Suppressed rather than repositioned:
        two buttons offering the same thing is worse than one, and the spec
        gives the rail this moment by name."""
        if self._next_up_open:
            if self._skip_active is not None:
                # Marked used, so it does not spring back the moment the
                # rail is dismissed -- by then the viewer has answered the
                # question the pill was asking.
                self._hide_skip(used=True)
            return
        if self._skip_active is not None:
            _kind, start, end = self._skip_active
            expired = self._skip_hide_at and now >= self._skip_hide_at
            # ...but not while the viewer is plainly still deciding. Focus on
            # the pill means they have arrived at it and are about to press
            # it; the chrome being up means they have the remote in hand and
            # the pill is sitting right above the controls they raised.
            # Expiring under either is the "impossible to hit" complaint.
            #
            # The segment's own end still takes it down on the line below, so
            # neither case can leave the pill offering a skip it no longer
            # has anything to skip.
            if expired and (self.getFocusId() == self.SKIP_BUTTON_ID
                            or self.getProperty("player_chrome")):
                expired = False
                self._skip_hide_at = now + self._policy(
                    "prompt_auto_hide_secs", SKIP_PROMPT_AUTO_HIDE_S)
            if expired or not (start <= position_ms < end):
                self._hide_skip(used=expired)
            return
        if not self._segments:
            return
        # RE-ARM anything now ahead of us again. _skip_done exists so a
        # dismissed prompt cannot flicker back two seconds later while the
        # same segment is still running -- it was never meant to mean "this
        # segment is spent for the rest of the file". Seeking back to before
        # the intro and getting no pill at all was that overreach: the
        # viewer's rewind is the clearest possible statement that they want
        # the segment offered again. Keyed on the segment being wholly
        # AHEAD, so it cannot re-arm the one we are sitting inside.
        if self._skip_done:
            self._skip_done = {s for s in self._skip_done if s[1] <= position_ms}
        for segment in self._segments:
            kind, start, end = segment
            if segment in self._skip_done or not (start <= position_ms < end):
                continue
            action = self._segment_action(kind)
            if action == "none":
                # "Do nothing" -- let it play. Marked done so this is decided
                # once per segment rather than re-evaluated every tick.
                self._skip_done.add(segment)
                continue
            if kind == "outro" and self.rail_owns_outro():
                # The rail now OPENS at this marker rather than at a flat 30s
                # (see _next_up_reveal_ms), so the pill would be raised and
                # then suppressed a moment later by the block at the top of
                # this method -- which is exactly the "Skip Credits, then Up
                # Next" flicker reported from the box. The rail's Play Next
                # already does everything Skip Credits does here and more, so
                # the pill is not drawn for an outro at all. Intro, recap and
                # preview are untouched: they are mid-file and the rail has
                # nothing to say about them.
                self._skip_done.add(segment)
                continue
            # Nothing to skip TO: the spec's own guard, and the server's
            # number for it. Applies to BOTH actions -- an automatic seek of
            # under a second is a stutter, not a skip.
            if end - position_ms <= self._policy(
                    "skip_min_remaining_secs", SKIP_MIN_REMAINING_S) * 1000:
                continue
            if action == "skip":
                self._auto_skip(segment)
                return
            self._skip_active = segment
            self._skip_hide_at = now + self._policy(
                "prompt_auto_hide_secs", SKIP_PROMPT_AUTO_HIDE_S)
            label = self._SKIP_LABELS.get(kind, "Skip")
            self.setProperty("player_skip_label", label)
            self._size_skip_pill(label)
            self.setProperty("player_skip", "1")
            # Land focus on it, so SELECT alone takes the skip. Reaching it
            # by pressing DOWN first was the whole interaction, and it is not
            # discoverable: the pill looks like a button and did not behave
            # like one.
            #
            # Only from the bare surface, though. Focus anywhere else means
            # the viewer is already driving something -- the chrome, a panel,
            # the Next Up rail -- and yanking them onto a pill that appeared
            # by itself would be worse than the pill being one press away.
            # From the chrome, UP now reaches it instead.
            if self.getFocusId() == self.SURFACE_ID:
                try:
                    self.setFocusId(self.SKIP_BUTTON_ID)
                except RuntimeError:
                    pass                    # window went away mid-tick
            return

    # 8.5: "pad 28h, icon 18pt + label", pinned to the transport bar's
    # right cluster, which is 1900 on this canvas.
    _SKIP_RIGHT = 1900
    _SKIP_PAD_X = 28
    _SKIP_ICON_W = 24
    _SKIP_ICON_GAP = 10
    _SKIP_Y = 952
    _SKIP_H = 60
    # textmetrics.py measures tofa_font_metadata (inter_tight_regular @23);
    # the pill's label is tofa_font_button (inter_tight_semibold @28). The
    # size ratio alone lands 3.5-6.7px NARROW on the real labels, because
    # semibold is wider than regular; 1.05 corrects that to within ~1.5px,
    # checked against PIL's own getlength for all five labels. Well inside
    # the 28px padding either side.
    _SKIP_SEMIBOLD = 1.05

    def _size_skip_pill(self, label: str):
        """Hug the text: 8.5 says the pill is never full width, and a fixed
        width leaves a visibly bigger gap on one side than the other."""
        text_w = int(round(
            textmetrics.text_width(label) * (28.0 / textmetrics.SIZE)
            * self._SKIP_SEMIBOLD))
        width = (self._SKIP_PAD_X * 2 + self._SKIP_ICON_W
                 + self._SKIP_ICON_GAP + text_w)
        left = self._SKIP_RIGHT - width
        for cid in self.SKIP_CAPSULE_IDS + (self.SKIP_BUTTON_ID,):
            try:
                ctrl = self.getControl(cid)
            except RuntimeError:
                continue
            ctrl.setPosition(left, self._SKIP_Y)
            ctrl.setWidth(width)
        for cid in self.SKIP_GLYPH_IDS:
            try:
                self.getControl(cid).setPosition(
                    left + self._SKIP_PAD_X, self._SKIP_Y)
            except RuntimeError:
                pass
        for cid in self.SKIP_TEXT_IDS:
            try:
                ctrl = self.getControl(cid)
            except RuntimeError:
                continue
            ctrl.setPosition(
                left + self._SKIP_PAD_X + self._SKIP_ICON_W + self._SKIP_ICON_GAP,
                self._SKIP_Y)
            ctrl.setWidth(text_w + 4)
        log.debug(f"player: skip pill x={left} w={width} label={label!r}")

    def _auto_skip(self, segment: tuple):
        """Seek past a segment the viewer asked to have skipped outright.

        Marked done BEFORE the seek, not after: the seek lands inside the
        next tick's window near the segment's own end, and an unmarked
        segment would be re-detected and skipped again in a loop.

        No pill and no toast. 8.9's "no auto-quality toast" reasoning applies
        here too -- the viewer configured this, so announcing it every time is
        noise. The scrub track still shows the segment's band, which is where
        someone wondering what just happened can see it.

        Seeks to the segment's END rather than end+1: `end` is the first
        frame that is no longer part of the segment."""
        kind, _start, end = segment
        self._skip_done.add(segment)
        # Through _seek_to, not a raw seekTime: `end` is a position in the
        # FILE, and on a server-cut HLS session that is not the media clock.
        try:
            self._seek_to(end)
        except Exception as exc:
            log.warning(f"player: auto-skip seek failed: {exc!r}")
            return
        log.debug(f"player: auto-skipped {kind} to {end}ms")

    def _hide_skip(self, *, used: bool):
        """Take the pill down. `used` marks the segment so it cannot come
        back for the rest of its own run -- an auto-hidden or dismissed
        prompt reappearing two seconds later is worse than no prompt."""
        if used and self._skip_active is not None:
            self._skip_done.add(self._skip_active)
        self._skip_active = None
        self._skip_hide_at = 0.0
        self.setProperty("player_skip", "")
        if self.getProperty("player_error") or self.getProperty("player_panel"):
            # Something else owns focus -- the error card's button, or the
            # panel's list -- so leave it alone. Taking focus back to the
            # surface here would pull the viewer out of the panel they just
            # opened, merely because a pill happened to time out behind it.
            #
            # These two guards used to call ControlledWindow.onAction(self,
            # action) instead, with no `action` in scope: two blocks copied
            # from onAction into this method. It raised NameError, the tick
            # loop caught it ("a ticker must never die") and abandoned the
            # rest of that cycle -- including the focus restore below, whose
            # own comment says leaving focus on a hidden control kills the
            # d-pad. Never seen in a log, because it needs the pill to time
            # out while a panel is open, but it was live.
            return
        if self.getFocusId() == self.SKIP_BUTTON_ID:
            # Focus cannot be left on a control inside a hidden group, or the
            # d-pad stops responding entirely -- but it must NOT move while
            # the press that got us here is still being dispatched.
            #
            # take_skip() runs as the pill's click handler. Moving focus to
            # the surface from inside it put control 9001 under the very
            # select that was mid-flight, and a select on the bare surface
            # with the chrome down is toggle_play_pause (10.2). So "Skip
            # Intro" skipped the intro and then PAUSED: measured as
            # state='playing' speed=1 before the press, state='paused'
            # speed=0 and position moved 0:31 -> 1:15 after it. Reported from
            # the box.
            #
            # Deferred to the tick instead, ~200ms later, by which time the
            # press is long finished. Leaving focus on the hidden pill for
            # that one tick is harmless: a second select there re-enters
            # take_skip(), which returns immediately on _skip_active is None.
            self._defer_focus_restore(self.SKIP_BUTTON_ID)

    def take_skip(self):
        """Jump to the end of the segment the pill is offering.

        A closing outro usually runs to the LAST MILLISECOND of the file, so
        "seek to its end" is a seek to the end -- which Kodi clamps to the
        duration and then ignores, leaving the credits playing under a pill
        that has just been pressed. What "Skip Credits" actually promises
        there is that the title is over, so this finishes it: on to the next
        episode if there is one, out of the player if there isn't."""
        if self._skip_active is None:
            return
        _kind, _start, end = self._skip_active
        self._hide_skip(used=True)
        tail_ms = self._policy(
            "skip_min_remaining_secs", SKIP_MIN_REMAINING_S) * 1000
        if self._duration_ms and end >= self._duration_ms - tail_ms:
            if self._next_up is None:
                self._exit()
                return
            # Only `auto` may advance on the viewer's behalf. The API is
            # just as flat about the other two: `ask` may never start
            # anything by itself, and `none` may neither raise the Next Up
            # card nor advance. Pressing Skip Credits is consent to skip credits,
            # not consent to start the next episode. So ask and off fall
            # through to the seek below: the last seconds play out, and the
            # rail decides (ask) or nothing does (off).
            if self._auto_play_next_mode() == AUTO_PLAY_NEXT_AUTO:
                self.play_next_up()
                return
        self._seek_to(end)

    # ------------------------------------------------------------------
    # 8.10 -- episode drawer
    # ------------------------------------------------------------------

    _DRAWER_ROW_TEXT_W = 468     # matches the row layout's label width
    _DRAWER_STILL_W = 140

    def toggle_drawer(self):
        if self.getProperty("player_episodes"):
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):
        """Raise the drawer on the season that is playing.

        Built from the media_detail response _load_metadata already fetched,
        so opening costs no round trip -- the drawer has to be instant, it
        is opened mid-scene."""
        if not self._drawer_media:
            return
        if self._drawer_seasons is None:
            self._drawer_seasons = kodigui.ManagedControlList(
                self, self.DRAWER_SEASONS_ID, 12)
            self._drawer_episodes = kodigui.ManagedControlList(
                self, self.DRAWER_EPISODES_ID, 30)
        self._drawer_season = self.season
        self._render_drawer_seasons()
        self._render_drawer_episodes(self._drawer_season)
        self.setProperty("player_episodes", "1")
        # The drawer owns the screen while it is up, so the chrome's
        # auto-hide must stop fighting it -- same reason 8.3's rail does it.
        self.hide_chrome()
        self.setFocusId(self.DRAWER_EPISODES_ID)
        self._focus_playing_episode()

    def close_drawer(self):
        """Back out of 8.10's drawer, landing on the button that opened it.

        It used to park on the bare surface, which is right for a rung that
        hides the chrome with it -- but the drawer does not: Back leaves the
        controls up, and dropping the viewer onto an unfocused surface under
        visible chrome loses their place in the row they were walking. Same
        reasoning as the selection panel's focus hand-back; owner's request.

        Falls back to the surface when the chrome has since auto-hidden or
        the capsule has been relaid out without an Episodes button (a quality
        change restarts playback and rebuilds it)."""
        if not self.getProperty("player_episodes"):
            return
        self.setProperty("player_episodes", "")
        # Focus has to leave before the group goes, or the focus engine
        # keeps it on a hidden control and the d-pad stops working.
        self.anchor_chrome()
        if self._chrome_deadline:
            try:
                self.setFocusId(self.EPISODES_ID)
                return
            except RuntimeError:
                pass
        try:
            self.setFocusId(self.SURFACE_ID)
        except RuntimeError:
            pass

    def _drawer_season_list(self) -> list:
        """Every season, SPECIALS INCLUDED.

        Deliberately unlike _index_episodes, which drops season 0: that one
        feeds auto-play, where a special following a finale would be wrong.
        The drawer is a browser, and the reference app does list an S0 chip
        when a show has one -- see
        internal-docs/atv-reference/player-episode-drawer-specials.png."""
        return sorted(self._drawer_media.get("seasons") or [],
                      key=lambda x: x.get("season_number") or 0)

    def _render_drawer_seasons(self):
        rows = []
        for season in self._drawer_season_list():
            n = season.get("season_number") or 0
            rows.append(kodigui.ManagedListItem(f"S{n}", data_source=n))
        self._drawer_seasons.reset()
        self._drawer_seasons.addItems(rows)
        self._mark_drawer_season()

    def _mark_drawer_season(self):
        """Move the "selected chip" mark WITHOUT rebuilding the list.

        Rebuilding resets the list's selected index to 0, which parks focus
        back on S1 the instant you pick S2 -- the chip you just chose ends
        up marked while the focus ring sits on a different one."""
        for item in self._drawer_seasons:
            item.setProperty(
                "active", "1" if item.dataSource == self._drawer_season else "")
        self.setProperty("drawer_season", f"S{self._drawer_season or ''}")

    def _render_drawer_episodes(self, season_number):
        season = next(
            (s for s in self._drawer_season_list()
             if (s.get("season_number") or 0) == season_number), None)
        episodes = sorted((season.get("episodes") or []) if season else [],
                          key=lambda e: e.get("episode_number") or 0)
        artcache.prefetch(self.client.stage_pairs(episodes, "still_path"))
        rows = [self._drawer_row(ep) for ep in episodes]
        self._drawer_episodes.reset()
        self._drawer_episodes.addItems(rows)

    def _drawer_row(self, ep: dict):
        """One episode row.

        The metadata line is the reference app's own wording, runtime and
        all: "Episode 2 - 40:37", minutes and SECONDS, not the "40 min" the
        Detail grid uses."""
        number = ep.get("episode_number") or 0
        avail = [f for f in (ep.get("files") or []) if f.get("available")]
        f = avail[0] if avail else None
        title = ep.get("title") or f"Episode {number}"
        item = kodigui.ManagedListItem(title, data_source=(ep, f))
        playing = bool(f and str(f.get("id")) == str(self.file_id))
        item.setProperty("playing", "1" if playing else "")
        meta = f"Episode {number}"
        duration_ms = (f or {}).get("duration_ms") or 0
        if duration_ms:
            total_s = duration_ms // 1000
            meta = f"{meta} · {total_s // 60}:{total_s % 60:02d}"
        if playing:
            # The reference gives the playing episode a THIRD line saying
            # this, which a single-itemheight Kodi list cannot do. Riding on
            # the metadata line keeps the words rather than paying for them
            # out of the title's colour, which the reference leaves alone.
            meta = f"{meta} · Now playing"
        item.setProperty("meta", meta)
        item.setArt({"thumb": self.client.resolve_image_url(ep.get("still_path")) or ""})

        watched = bool((ep.get("user_data") or {}).get("watched")) and not playing
        item.setProperty("watched", "1" if watched else "")
        fraction = 0.0
        if playing and self._duration_ms:
            fraction = self._position_ms() / float(self._duration_ms)
        else:
            position = (ep.get("user_data") or {}).get("position_ms") or 0
            if position and duration_ms:
                fraction = position / float(duration_ms)
        fraction = max(0.0, min(1.0, fraction))
        # A filename, not a width -- see the XML comment on the bar.
        item.setProperty(
            "progress",
            "drawer-progress/{0}.png".format(int(round(fraction * 50)) * 2)
            if fraction > 0.01 else "")
        return item

    def _focus_playing_episode(self):
        """8.10 auto-scrolls to the current episode. Only meaningful while
        the season on screen is the one playing."""
        if self._drawer_episodes is None or self._drawer_season != self.season:
            return
        for i, item in enumerate(self._drawer_episodes):
            if item.getProperty("playing"):
                self._drawer_episodes.setSelectedItemByPos(i)
                return

    def _drawer_clicked(self, control_id):
        if control_id == self.DRAWER_SEASONS_ID:
            item = self._drawer_seasons.getSelectedItem()
            if item is None:
                return
            self._drawer_season = item.dataSource
            self._mark_drawer_season()
            self._render_drawer_episodes(self._drawer_season)
            self._focus_playing_episode()
            return
        item = self._drawer_episodes.getSelectedItem()
        if item is None:
            return
        ep, f = item.dataSource
        if f is None:
            return
        if str(f.get("id")) == str(self.file_id):
            # Already playing it; the drawer just gets out of the way.
            self.close_drawer()
            return
        season = next(
            (s for s in self._drawer_season_list()
             if (s.get("season_number") or 0) == self._drawer_season), {})
        self.close_drawer()
        self._play_episode((season, ep, f))

    # 8.1's utility capsule is content-dependent, not a fixed four. The
    # reference app shows only the buttons with a choice behind them and
    # sizes the capsule to fit: four captures in internal-docs/atv-reference
    # show four, four, four and six. Geometry is the measured one -- 52pt
    # buttons at pitch 70 inside a 72-tall capsule whose RIGHT edge is
    # pinned at 1900, growing leftward.
    _UTIL_RIGHT = 1900
    _UTIL_PITCH = 70
    _UTIL_BTN = 52
    _UTIL_PAD = 20          # capsule edge to first button centre-line
    _UTIL_Y = 990
    _UTIL_BG_Y = 980
    _UTIL_BG_H = 72

    def _visible_utility_buttons(self) -> list:
        """Which buttons apply to what is playing, in the reference order.

        Subtitles and Audio are gated on there being something to choose
        between: a button that opens a picker with one row in it is worse
        than no button, and the reference app does not draw them. Audio
        needs MORE than one track, subtitles only need one, because
        subtitles always have an implicit "Off" to switch back to."""
        buttons = []
        if self._subtitle_tracks:
            buttons.append(self.SUBTITLES_ID)
        if len(self._audio_tracks) > 1:
            buttons.append(self.AUDIO_ID)
        # Only for a file Kodi has actually detected as stereoscopic --
        # the same test the start-of-playback question uses, so the button
        # is present exactly when there is a question worth re-asking.
        if xbmc.getCondVisibility("VideoPlayer.IsStereoscopic"):
            buttons.append(self.STEREO_ID)
        if self.getProperty("player_is_episode"):
            buttons.append(self.EPISODES_ID)
        buttons.append(self.QUALITY_ID)
        # Unconditional, unlike its neighbours: audio sync always has
        # something to correct, because there is always audio. The panel
        # behind it is what varies -- the subtitle row appears only when
        # subtitles are on. See _adjust_rows().
        buttons.append(self.ADJUST_ID)
        buttons.append(self.STATS_ID)
        return buttons

    def _layout_utility_capsule(self):
        """Place the capsule and the buttons that apply, hide the rest.

        Also rewires each button's left/right, because the chain has to
        follow the VISIBLE order -- with Subtitles absent, Audio's left
        neighbour is the transport, not a hidden control the focus engine
        would refuse to leave."""
        buttons = self._visible_utility_buttons()
        width = self._UTIL_PAD * 2 + self._UTIL_BTN + self._UTIL_PITCH * (len(buttons) - 1)
        left = self._UTIL_RIGHT - width
        for bg_id in self.UTILITY_BG_IDS:
            try:
                ctrl = self.getControl(bg_id)
            except RuntimeError:
                continue
            ctrl.setPosition(left, self._UTIL_BG_Y)
            ctrl.setWidth(width)
        for slot, button_id in enumerate(self.UTILITY_IDS):
            shown = button_id in buttons
            x = (left + self._UTIL_PAD + self._UTIL_PITCH * buttons.index(button_id)
                 if shown else 0)
            base = self.UTILITY_VISUAL_BASE[button_id]
            for cid in [base + i for i in range(6)] + [button_id]:
                try:
                    ctrl = self.getControl(cid)
                except RuntimeError:
                    continue
                ctrl.setVisible(shown)
                if shown:
                    ctrl.setPosition(x, self._UTIL_Y)
        # Logged because this geometry exists nowhere else: the XML's
        # coordinates are placeholders, so a capsule in the wrong place
        # cannot be diffed against a source file.
        log.debug(f"player: utility capsule x={left} w={width} buttons={buttons}")
        for i, button_id in enumerate(buttons):
            try:
                ctrl = self.getControl(button_id)
            except RuntimeError:
                continue
            left_id = buttons[i - 1] if i else self.FWD10_ID
            right_id = buttons[i + 1] if i + 1 < len(buttons) else button_id
            try:
                ctrl.controlLeft(self.getControl(left_id))
                ctrl.controlRight(self.getControl(right_id))
            except RuntimeError:
                pass
        # ...and the way IN. The XML sends the transport's right into
        # Subtitles, which is exactly the button most likely to be hidden;
        # without this the capsule is unreachable whenever it is.
        try:
            self.getControl(self.FWD10_ID).controlRight(self.getControl(buttons[0]))
        except (RuntimeError, IndexError):
            pass
        # This can run WHILE the chrome is up -- on_playback_started calls it
        # once the stream can answer what it is. Kodi leaves focus sitting on
        # a control that has just been hidden, and every key from there is
        # dead, which is the same dead end close_panel's docstring describes
        # reached from a different direction. Nothing is hidden on the
        # playback-started pass today; the guard is here so that stays true
        # of whoever calls this next.
        try:
            focused = self.getFocusId()
        except RuntimeError:
            return
        if focused in self.UTILITY_IDS and focused not in buttons:
            log.debug(f"player: capsule hid focused button {focused}, "
                      "moving focus to play/pause")
            self.setFocusId(self.PLAYPAUSE_ID)

    def _apply_transport_mode(self, *, episode: bool):
        """Swap the transport's outer pair between seek and episode.

        The glyphs arrive as Window properties rather than being written
        twice into the XML: each one appears in a focused and an unfocused
        label, so a literal per mode would be four copies of the same
        decision. A button with nowhere to go is dimmed to 8.4's disabled
        alpha instead of vanishing, so the focus chain never changes shape
        under the viewer."""
        self.setProperty("player_is_episode", "1" if episode else "")
        prev_on = (not episode) or self._prev_episode is not None
        next_on = (not episode) or self._next_up is not None
        self.setProperty(
            "transport_prev_glyph",
            _GLYPH_PREV_EPISODE if episode else _GLYPH_SEEK_BACK)
        self.setProperty(
            "transport_next_glyph",
            _GLYPH_NEXT_EPISODE if episode else _GLYPH_SEEK_FWD)
        self.setProperty(
            "transport_prev_color",
            self.getProperty("text_primary") if prev_on else _TRANSPORT_DISABLED)
        self.setProperty(
            "transport_next_color",
            self.getProperty("text_primary") if next_on else _TRANSPORT_DISABLED)
        # The episodes button lives or dies on the same fact, so the capsule
        # is relaid out from here rather than from a second caller that
        # would have to know when this one had run.
        self._layout_utility_capsule()

    def _stage_next_up(self, media: dict, season: dict, ep: dict):
        """Fill the rail's labels and art once, up front -- it has to appear
        instantly 30s from the end, not go fetch a still at that moment.

        The image PATH is kept as well as the resolved URL, because the URL
        does not keep: see _refresh_nextup_still, which re-mints it at
        reveal."""
        number = episodes.number_label(
            season.get("season_number") or 0, ep.get("episode_number") or 0,
            ep.get("episode_number_end"))
        self._nextup_still_path = (
            ep.get("still_path")
            or season.get("poster_path")
            or media.get("backdrop_path")
            or "")
        self.setProperty("nextup_number", number)
        self.setProperty(
            "nextup_title",
            ep.get("title") or "Episode {0}".format(ep.get("episode_number") or "?"))
        self.setProperty("nextup_still", self._resolve_still(self._nextup_still_path))

    def _resolve_still(self, path: str) -> str:
        if not (path and self.client):
            return ""
        try:
            return self.client.resolve_image_url(path) or ""
        except Exception as exc:                            # noqa: BLE001
            log.warning(f"player: could not resolve the Next Up still: {exc!r}")
            return ""

    def _refresh_nextup_still(self):
        """Re-mint the rail's still URL immediately before the rail is shown.

        WHY THE STAGED URL IS NOT ENOUGH. Art URLs carry the image token as
        `?st=<jwt>`, and that token lives exactly **one hour** (measured on
        the wire: iat 1786044982, exp 1786048582). It is minted once and
        shared across the whole session, so its age when an episode starts
        is arbitrary -- anywhere from brand new to 59 minutes old.

        _stage_next_up runs at playback START, because the rail has to
        appear instantly. But the rail appears 30s before the END. On a
        46-minute episode the staged URL is ~46 minutes older than when it
        was minted, so any token that was already a quarter of an hour old
        at playback start is dead by the time anyone sees it. An expired
        `st` is a 401, and Kodi draws nothing at all -- which is exactly
        what was reported from the box: "Up Next panel appears but poster
        has no artwork". Not slow artwork. No artwork, permanently, for
        that rail.

        Re-minting here costs nothing in the ordinary case: image_token()
        is served from memory and then from disk, and only goes to the
        server once an hour -- which is precisely the case this exists for.
        Done BEFORE `player_next_up` is set, so the rail is revealed with a
        URL that works rather than swapping one in a moment later.

        The same staleness applies to `player_logo` and `player_backdrop`,
        which 8.8's pause card reads and which are resolved in
        _load_metadata at playback start -- a film paused ninety minutes in
        has the same dead token. Not fixed here; that surface has its own
        timing and deserves its own change.
        """
        if not self._nextup_still_path:
            return
        fresh = self._resolve_still(self._nextup_still_path)
        if fresh and fresh != self.getProperty("nextup_still"):
            log.debug("player: re-minted the Next Up still for the reveal")
        if fresh:
            self.setProperty("nextup_still", fresh)

    def show_next_up(self):
        """Raise the rail, and count down only if the viewer asked us to.

        `playback.auto_play_next` decides (see _auto_play_next_mode):
        `auto` counts down and advances, `ask` shows the same rail with no
        timer and waits to be pressed. `none` never gets here at all.

        In `ask` the countdown properties are cleared rather than frozen:
        the ring and the seconds label are bound straight to them, so an
        empty value draws nothing and the rail loses its timer without
        needing a second XML layout."""
        if self._next_up is None or self._next_up_open:
            return
        mode = self._auto_play_next_mode()
        now = time.monotonic()
        self._next_up_open = True
        self._next_up_focus_at = now + NEXT_UP_AUTOFOCUS_S
        if mode == AUTO_PLAY_NEXT_AUTO:
            self._next_up_deadline = now + NEXT_UP_COUNTDOWN_S
            self.setProperty("nextup_seconds", str(int(NEXT_UP_COUNTDOWN_S)))
            self.setProperty("nextup_ring",
                             "nextup-ring/{0}.png".format(NEXT_UP_RING_STEPS))
        else:
            self._next_up_deadline = 0.0
            self.setProperty("nextup_seconds", "")
            self.setProperty("nextup_ring", "")
        # Opening onto an already-paused stream: park the countdown at once
        # rather than wait for a pause event that has already been and gone.
        # Rare, because the rail is armed by POSITION and that does not move
        # while paused -- but reachable by pausing in the instant it arms,
        # and it would otherwise spend the full 20s against a still frame.
        if self._paused():
            self._hold_next_up()
        # Before the reveal, not after: the token the URL was staged with
        # may have expired during the episode. See _refresh_nextup_still.
        self._refresh_nextup_still()
        self.setProperty("player_next_up", "1")
        # The rail takes this moment over from 8.5's pill -- see _tick_skip.
        # Done here as well as on the tick so the two are never on screen
        # together for even one frame: _tick_skip runs BEFORE _tick_next_up
        # in _tick, so on the reveal tick it has already had its say.
        self._hide_skip(used=True)
        # The rail takes the d-pad, so the chrome's auto-hide must stop
        # fighting it -- same reason a modal picker suspends it.
        self.hide_chrome()

    def _auto_play_next_mode(self) -> str:
        """`playback.auto_play_next`, defaulting the way the contract says.

        The API documents it plainly: an absent key means `auto`, which is
        what keeps an existing viewer on the behaviour they already have,
        and every client is required to apply that same default.
        Anything unrecognised is treated as the
        default too -- a value we do not know is not a reason to withhold
        the next episode.

        Resolved ONCE per window and cached. _playback_prefs() is an
        uncached whoami() over HTTP, and this is read from the 200ms tick:
        without the cache the rail's reveal check would put five network
        round-trips a second behind every playing episode. A per-profile
        setting cannot change while that profile is watching, so there is
        nothing to re-read."""
        if self._auto_play_mode is None:
            value = str(self._playback_prefs().get("auto_play_next") or "").lower()
            self._auto_play_mode = (
                value if value in AUTO_PLAY_NEXT_MODES else AUTO_PLAY_NEXT_AUTO)
            log.debug(f"player: auto_play_next = {self._auto_play_mode}")
        return self._auto_play_mode

    def dismiss_next_up(self):
        """Take the rail down and leave it down.

        Latched rather than re-armable: the reveal condition stays true for
        the whole 30s that follows, so an unlatched dismiss would put the
        rail straight back up on the next tick."""
        if not self._next_up_open:
            return
        self._next_up_open = False
        self._next_up_deadline = 0.0
        # A rail that closes while paused must not leave a parked countdown
        # behind for the next resume to hand back to a rail that has gone.
        self._next_up_hold = 0.0
        self._next_up_focus_at = 0.0
        self._next_up_dismissed = True
        self.setProperty("player_next_up", "")
        # Focus has to leave the rail before it goes away, or the focus
        # engine keeps it on a hidden control and the d-pad stops working --
        # but NOT from inside the press that got us here. See
        # _defer_focus_restore.
        self._defer_focus_restore(self.getFocusId())

    def play_next_up(self):
        """Swap this window over to the next episode, in place.

        Reuses _start_playback() rather than opening a second PlayerWindow:
        Kodi's window-id pool is hard-capped and a window per episode would
        exhaust it over a binge (see project_player_overlay).

        Runs on whichever thread called it -- the ticker's when the
        countdown expires. That blocks the OSD clock for as long as the
        negotiation takes, which is the same trade _pick_quality already
        makes on the UI thread, and the alternative (a fourth thread) would
        have to be joined by onClosed anyway."""
        self._play_episode(self._next_up)

    def play_prev_episode(self):
        """The transport's previous button on a TV episode."""
        self._play_episode(self._prev_episode)

    def _close_out_session(self, file_id, position_ms: int, *, finished: bool):
        """Write the outgoing episode's state and end its server session.

        `finished` says whether the viewer actually reached the end of it --
        see _play_episode, which decides from the position. It is the whole
        difference between "abandoned at 12 minutes because they pressed
        next" and "watched to the credits and pressed Play Next".

        NECESSARY because we advance without stopping. monitor.py's
        TofaPlayer lives in the service.py process and learns an episode
        finished only from Kodi's onPlayBackStopped -- and replacing the
        playing item does not dispatch it. Measured on the box: the advance
        logged `VideoPlayer::OpenFile` and then `monitor: adopted session
        <new>` with NO teardown of the old one in between. So the position
        was never written and the session never ended: one leaked session
        per episode across a binge, and a viewer's place in the episode they
        just left silently lost.

        Done HERE rather than by signalling monitor, because monitor is in
        another process and the only channel to it is the one-shot pending
        session handoff -- which is for starting, not finishing. We hold the
        session id and token in _nego, so we can close it ourselves.

        Best effort throughout: a failure here must not stop the next
        episode from playing, which is what the viewer actually asked for.
        """
        nego = self._nego or {}
        session_id = nego.get("session_id")
        session_token = nego.get("session_token")
        if not (self.client and file_id):
            return
        if finished:
            # Everything monitor.py's onPlayBackEnded would have done, done
            # here because that callback never fires: the outgoing item is
            # REPLACED rather than stopped, so Kodi reports no end.
            #
            # Without this the episode a viewer just sat through and pressed
            # Play Next on was written back as "in progress, 45:50 of 46:20"
            # -- so it stayed in Continue Watching at 98%, Detail showed it
            # with a nearly-full bar instead of a tick, and the show's
            # next-up never moved along. Reported from the box as "the
            # Details screen is not updated, neither is Continue Watching".
            #
            # update_watched as well as ended=True, for the same reason
            # monitor states: the server is not asked to infer completion
            # from a heartbeat position.
            try:
                self.client.update_watched(file_id, True)
            except Exception as exc:                        # noqa: BLE001
                log.warning(f"player: could not finish outgoing episode: {exc!r}")
        try:
            self.client.update_progress(file_id, position_ms, finished)
        except Exception as exc:                            # noqa: BLE001
            log.warning(f"player: could not write outgoing progress: {exc!r}")
        if not (session_id and session_token):
            return
        for what, call in (("report_stopped", self.client.report_stopped),
                           ("end_session", self.client.end_session)):
            try:
                call(session_id, session_token)
            except http.ApiError as exc:
                # 410 is the END STATE WE WANTED, not a failure: the session
                # is already gone, which is what report_stopped just did to
                # it. monitor.py's _log_api_error draws the same distinction
                # for the same reason -- warning about it once per episode
                # would make a healthy binge look broken.
                log_fn = log.debug if exc.status == 410 else log.warning
                log_fn(f"player: outgoing {what}: {exc}")
            except Exception as exc:                        # noqa: BLE001
                log.warning(f"player: outgoing {what} failed: {exc!r}")

    def _play_episode(self, queued: Optional[tuple]):
        if queued is None:
            return
        # BEFORE anything below reassigns them: this is the last moment the
        # outgoing episode is still identifiable. _duration_ms in particular
        # is zeroed further down for the incoming one.
        outgoing_file_id = self.file_id
        outgoing_position = self._position_ms()
        outgoing_duration = self._duration_ms
        # Did they get to the end of it? The same window the Next Up rail
        # opens in, deliberately: inside it, leaving is finishing (the rail
        # is up, or Skip Credits just ran out the tail), and the episode
        # must be marked watched. Outside it this is the transport's
        # next/previous button pressed mid-episode, which is a jump, not a
        # completion -- marking that watched would be a lie the viewer
        # cannot undo without noticing it first.
        outgoing_finished = bool(
            outgoing_duration
            and outgoing_duration - outgoing_position <= NEXT_UP_LEAD_S * 1000)
        season, ep, f = queued
        self._next_up = None
        self._prev_episode = None
        self._next_up_open = False
        self._next_up_deadline = 0.0
        # A rail that closes while paused must not leave a parked countdown
        # behind for the next resume to hand back to a rail that has gone.
        self._next_up_hold = 0.0
        self._next_up_focus_at = 0.0
        self._next_up_dismissed = False
        self.setProperty("player_next_up", "")
        self.file_id = f.get("id")
        self._segments = []
        self._chapters = []
        self._tiles = {}
        self.setProperty("player_preview_ready", "")
        self._skip_done = set()
        self._hide_skip(used=False)
        self.season = season.get("season_number")
        self.episode = ep.get("episode_number")
        self.title = ep.get("title") or self.title
        self.setProperty("player_title", self.title or "")
        # A fresh episode starts at the beginning, and its duration is not
        # this one's -- leaving either behind would resume the new episode
        # at the old one's position and mis-scale the scrubber.
        self.resume_ms = None
        self._duration_ms = 0
        self._time_offset_ms = 0
        self._nextup_still_path = ""
        self._restarting = True
        if not NO_STOP_BETWEEN_EPISODES:
            try:
                self.ui_player.stop()
            except RuntimeError:
                pass
        else:
            # The outgoing episode keeps playing while the negotiation for the
            # next one is in flight. That is deliberate and it is not visible:
            # STATE_OPENING below puts the full-screen scrim over it on the
            # very next frame, so what the viewer sees is the opening card,
            # not the tail of the credits. A stop here would instead give
            # them a black screen for the same interval AND cost the mode.
            log.debug("player: advancing without stop (keeping display mode)")
            # No stop means no onPlayBackStopped, so nothing else will ever
            # finish the outgoing session. Do it here, before _start_playback
            # overwrites _nego with the next episode's.
            self._close_out_session(outgoing_file_id, outgoing_position,
                                    finished=outgoing_finished)
        self.setProperty("player_state", self.STATE_OPENING)
        # Deferred, not immediate. This runs as the Next Up rail's click
        # handler, and taking focus to the bare surface from inside that
        # press hands the same select to the surface -- where SELECT with
        # the chrome down is toggle_play_pause. The next episode then
        # started and instantly PAUSED. Exactly the failure _hide_skip
        # documents for the Skip pill; see _defer_focus_restore.
        #
        # Safe to leave focus on the (now hidden) Play Next button for the
        # ~200ms until the tick moves it: a second select there re-enters
        # play_next_up, and _next_up was cleared above, so it returns at
        # once.
        self._defer_focus_restore(self.getFocusId())
        self._start_playback()

    def _defer_focus_restore(self, control_id):
        """Park focus on `control_id` a little longer, then send it to the
        bare surface.

        For buttons whose own click handler takes their group off screen.
        Focus cannot STAY on a hidden control -- the d-pad dies there -- but
        it must not move from inside the press that is still being
        dispatched either: Kodi delivers one press twice, onClick on the
        Python thread and then onAction on the app thread, and the bare
        surface under that second dispatch is toggle_play_pause (10.2). That
        is how Skip Intro skipped and then paused, and how Play Next
        advanced and then paused. Both measured on the box.

        Keyed on the control so a restore deferred by one surface cannot
        fire against a different one that has since taken focus -- see the
        tick, where that exact collision is written up.
        """
        self._restore_focus_from = control_id
        self._restore_focus_at = time.monotonic() + DEFERRED_FOCUS_S

    def is_restarting(self) -> bool:
        return self._restarting

    def on_playback_started(self):
        """First frame is up: the opening overlay goes away, the ticker
        starts, and the chrome shows itself once so the user can see what
        they started (the reference app does the same) before the 4.0s
        auto-hide takes it back down."""
        # The replacement stream is up, so a stop from here on is a real one
        # again. Cleared here rather than at the end of _pick_quality because
        # Kodi delivers the stop callback asynchronously -- it can arrive
        # after the new play() call has already been made.
        self._restarting = False
        # Immediately, not on the next 200ms tick: Kodi raises its seekbar as
        # part of starting playback, and waiting a tick is exactly long
        # enough for the viewer to see the active skin's controls flash up
        # under ours.
        self._close_kodi_osd()
        # A stereoscopic file, and the viewer is on "Ask me": offer the same
        # choice Kodi would have, in our own panel. After the first frame,
        # deliberately -- the panel sits over the playing film rather than
        # holding it up, which is the main thing wrong with Kodi's.
        if (stereoscopic.should_ask() or self._stereo_saved) and \
                xbmc.getCondVisibility("VideoPlayer.IsStereoscopic"):
            self._stereo_pending = True
        # ...and the capsule gains its 3D button at this same moment, for the
        # same reason the question can only be asked now: onInit laid the
        # capsule out before there was a stream, so VideoPlayer.IsStereoscopic
        # was still false and the button was left out of a 3D film's chrome.
        # Measured on Hugo, 2026-08-15 -- five buttons, no glasses.
        self._layout_utility_capsule()
        self._duration_ms = self._resolve_duration_ms()
        # The markers need the duration to scale against, and this is the
        # first moment it exists.
        self._render_scrub_markers()
        if self._resume_pending_ms:
            # First frame is up, so the seek has something to land on --
            # seeking before onAVStarted is silently dropped.
            self._seek_to(self._resume_pending_ms)
            self._resume_pending_ms = None
        self.refresh_progress()
        self.reveal_chrome()
        self._ensure_ticker()

    def _ensure_ticker(self):
        """Start the 200ms OSD tick, at most once per window.

        Called from _start_playback the moment play() has been issued, NOT
        only from on_playback_started as it used to be. Kodi raises its busy
        spinner while it opens the stream -- i.e. between those two points --
        so a ticker that only began at first frame could not close it, and
        the viewer saw Kodi's spinner over the branded one the opening card
        exists to show. Reported from the box.

        Safe that early: everything _tick does before playback is running is
        a no-op or reads zero (no duration, no segments, chrome deadline
        unset), and it is guarded by _closing throughout.
        """
        if self._ticker is not None:
            return
        self._ticker = threading.Thread(target=self._tick_loop, name="tofa-player-osd")
        self._ticker.daemon = True
        self._ticker.start()

    def _log_kodi_audio_pick(self) -> None:
        """What Kodi chose on its OWN, before we touch anything.

        Added 2026-08-19 for issue #67. Twice I explained why one box shows
        that bug and another does not, and twice the explanation was wrong,
        because the one thing that decides it is not recorded anywhere: which
        track KODI opened the file on, and whether the value we read back
        described the file we were about to judge.

        Both are in one line here, taken at the top of apply_track_selection()
        -- the single place every played item passes through, on onAVStarted,
        before any switch. `showing_current` is the same check `_switch_audio`
        trusts its shortcut with, so the log now says whether that trust was
        warranted at the moment it mattered.

        Kodi's Python Player has no getAudioStreamIndex (see _current_stream),
        so the ACTIVE slot comes from JSON-RPC while the stream LIST comes
        from the Player object -- two sources for one line, which is why this
        is worth writing once here rather than at each call site.

        Best-effort: this is instrumentation, and it must never be the reason
        a track is not applied.
        """
        try:
            cached, _ = self._current_stream(subtitles=False)
            names = list(self.ui_player.getAvailableAudioStreams() or [])
            log.info("player: audio[open] kodi_streams=%r kodi_playing=%r "
                     "label=%r cached_index=%r"
                     % (names, self._playing_audio_slot(),
                        xbmc.getInfoLabel(self._AUDIO_LABELS[0]), cached))
        except Exception as exc:                            # noqa: BLE001
            log.debug(f"player: could not log Kodi's audio pick: {exc!r}")

    def apply_track_selection(self):
        """Apply 7.7's Audio/Subtitle picks to the running stream.

        Post-start rather than negotiated: /stream/{id}/info has no
        audio_stream_index or subtitle_stream_index parameter, because on
        DirectPlay the whole container arrives and the choice is the
        player's to make.

        Failures here are logged and dropped. A stream that ignored the
        preference still plays, and taking the window down over a track
        choice would be a worse outcome than the wrong language.

        Runs on every onAVStarted, which fires once per played item -- and
        would fire again for a second item if this window ever gained a
        queue, which is the right time to re-apply anyway.

        THE TWO HALVES ARE INDEPENDENT, and that is the whole point of the
        shape below. This used to read

            if audio_index is None and subtitle_index is None:
                apply the language preferences; return
            ...apply whichever explicit index is set...

        so a selection carrying ONLY a subtitle pick failed the `and`, skipped
        the language preferences entirely, and then set only subtitles --
        leaving audio on whatever the file listed first and never touching it.
        On a German-first file with an English profile that plays German, in
        silence, with nothing in the log.

        It was not hypothetical: 7.7's panel writes `subtitle_index` only when
        the Subtitles section is used and `audio_index` only when Audio is,
        and `DetailWindow.play_selection` outlives a play. So choosing a
        subtitle once on a title left every later Play from that page on the
        wrong audio. Reported from the cinema box 2026-08-12 on Murder, She
        Wrote S2 E1; the log shows Kodi opening the German stream and no
        switch ever following, while the next episode -- started from Up Next,
        which never touches that Selection -- switched correctly 0.7s in.
        """
        # Before anything is switched: what did Kodi land on by itself, and
        # can we trust a read of it? See _log_kodi_audio_pick.
        self._log_kodi_audio_pick()
        explicit_audio = self.selection.audio_index is not None
        explicit_subtitle = self.selection.subtitle_index is not None
        chosen_audio = None
        try:
            if explicit_audio:
                slot = self._stream_slot(self._audio_order, self.selection.audio_index,
                                         self.ui_player.getAvailableAudioStreams())
                if slot is not None:
                    self._switch_audio(slot)
                # Remembered for the subtitle half below: when the viewer
                # picked the audio by hand, whether subtitles are wanted is a
                # question about THAT language, not about the one the
                # preference would have chosen.
                chosen_audio = next(
                    (t for t in (self._audio_tracks or [])
                     if t.get("index") == self.selection.audio_index), None)
            if explicit_subtitle:
                if self.selection.subtitle_index == playoptions.OFF:
                    self.ui_player.showSubtitles(False)
                else:
                    if self._select_subtitle(self.selection.subtitle_index):
                        self.ui_player.showSubtitles(True)
        except (RuntimeError, AttributeError, TypeError) as exc:
            log.warning(f"player: could not apply track selection: {exc!r}")

        # Whichever half the viewer did NOT decide falls back to the profile's
        # languages. Both halves explicit is the only case with nothing left
        # to do here.
        if not (explicit_audio and explicit_subtitle):
            self._apply_language_preferences(
                apply_audio=not explicit_audio,
                apply_subtitles=not explicit_subtitle,
                audio_override=chosen_audio)
        self._log_subtitle_inventory("applied")

    def _playback_prefs(self) -> dict:
        """`preferences.playback`, falling back to the last copy we read.

        This runs inside onAVStarted, and it used to be a live `whoami()` with
        `{}` on failure -- which does NOT mean "no preference", it means the
        audio never gets switched and the file's first track plays. One failed
        request at the wrong instant was a German soundtrack on an English
        profile, logged at debug on a box with debug logging off. See
        playbackprefs.py for the report that found it.

        So: a failure now falls back to the remembered copy and says so at
        WARNING. Preferences change rarely; a stale copy is a far better
        answer than none.
        """
        if not self.client:
            return playbackprefs.last_known()
        try:
            playback = ((self.client.whoami() or {}).get("preferences")
                        or {}).get("playback") or {}
        except http.ApiError as exc:
            remembered = playbackprefs.last_known()
            log.warning(
                "player: could not read playback preferences (%r); "
                "%s" % (exc, "using the last known copy" if remembered else
                        "NO remembered copy, so track selection is skipped "
                        "and the file's first audio track will play"))
            return remembered
        playbackprefs.remember(playback)
        return playback

    @staticmethod
    def _first_by_language(track_list: list, languages: list) -> dict | None:
        """See tracks.choose_audio: preferred language first, then the best
        track we can actually play within it.

        Detail's Options panel resolves its default with the SAME call, so
        what the panel shows is what will actually play. They were separate
        once, and disagreed: the panel offered German on an English profile
        for a disc whose German track comes first.
        """
        return tracks.choose_audio(track_list, languages,
                                   playable=_PLAYABLE_AUDIO_CODECS)

    def _apply_language_preferences(self, *, apply_audio: bool = True,
                                    apply_subtitles: bool = True,
                                    audio_override: dict | None = None):
        """Pick tracks from the profile's language preferences.

        Covers whichever half the viewer did NOT decide in 7.7's Options
        panel -- an explicit choice always wins, but only over its OWN half.
        Without this the stream kept whatever the file listed first, so a
        German-first file played German to an English profile. Reported from
        the box.

        `audio_override` is the track an explicit audio pick landed on, so the
        subtitle half can reason about the language actually being heard even
        though it did not choose it.

        Rules, from the settings' own wording ("Turn subtitles on even when
        the audio matches your language"):
          - audio: the highest-priority preferred language present.
          - subtitles: on if `always_enable_subtitles`, OR if the audio we
            ended up with is not one the viewer asked for; off otherwise.

        Best-effort throughout, like the explicit path: a stream that ignored
        the preference still plays.
        """
        playback_prefs = self._playback_prefs()
        if not playback_prefs:
            return
        audio_langs = [str(c).lower() for c in
                       (playback_prefs.get("preferred_audio_languages") or [])]
        sub_langs = [str(c).lower() for c in
                     (playback_prefs.get("preferred_subtitle_languages") or [])]
        always_subs = prefs.as_bool(playback_prefs, "always_enable_subtitles", False)

        chosen_audio = audio_override
        if apply_audio:
            try:
                if audio_langs and self._audio_tracks:
                    chosen_audio = self._first_by_language(self._audio_tracks, audio_langs)
                    if chosen_audio is not None:
                        slot = self._stream_slot(
                            self._audio_order, chosen_audio.get("index"),
                            self.ui_player.getAvailableAudioStreams())
                        if slot is not None:
                            self._switch_audio(slot)
            except (RuntimeError, AttributeError, TypeError) as exc:
                log.warning(f"player: could not apply audio language: {exc!r}")

        if not apply_subtitles:
            return

        # What is actually playing, which is not necessarily what we asked
        # for -- if none of the preferred languages is in the file the audio
        # stays on the file's first track, and THAT is what decides whether
        # subtitles are wanted.
        playing_lang = str((chosen_audio or (self._audio_tracks or [{}])[0])
                           .get("language") or "").lower()
        # Equivalence here too, and for the same reason as the track pick: a
        # `ger` preference against a `deu` track is a MATCH, so subtitles
        # must stay off. Comparing spellings would have turned every
        # correctly-matched foreign audio track into an unwanted subtitle.
        try:
            if always_subs:
                # Full subtitles, down the server 0.9.33 chain: a preferred
                # language, else the language of the audio actually being
                # heard, else a track nobody tagged, else off. The web
                # player used to grab the file's first track whatever its
                # language, and the fix's ordering is the sensible one for
                # us too -- each rung shows something the viewer can use,
                # where the old behaviour showed whatever came first.
                # Within a rung: a forced track is not "subtitles on", a
                # plain track beats an SDH one, and a text track beats a
                # picture one -- langcodes ranks all three.
                track = (langcodes.first_subtitle_by_language(
                    self._subtitle_tracks, sub_langs) if sub_langs else None)
                if track is None and playing_lang:
                    track = langcodes.first_subtitle_by_language(
                        self._subtitle_tracks, [playing_lang])
                if track is None:
                    track = langcodes.first_untagged_subtitle(
                        self._subtitle_tracks)
            else:
                # OFF does not mean silence: the disc's FORCED track for the
                # language being heard still gets shown, so the lines the
                # audio does not cover are translated. Every other tofa
                # client does this, and the viewer can still switch it off by
                # hand. Matched to the audio's language rather than to a
                # subtitle preference, which is the pairing that makes sense.
                track = langcodes.forced_subtitle_for(
                    self._subtitle_tracks, playing_lang)
            if track is None:
                # Nothing suitable. Turning on an arbitrary track would be
                # worse than leaving them off.
                self.ui_player.showSubtitles(False)
                return
            if self._select_subtitle(track.get("index")):
                self.ui_player.showSubtitles(True)
        except (RuntimeError, AttributeError, TypeError) as exc:
            log.warning(f"player: could not apply subtitle language: {exc!r}")
        self._log_subtitle_inventory("auto")

    def _switch_audio(self, slot: int) -> bool:
        """setAudioStream(slot), but only when it would change something.

        Switching a stream re-configures the renderer, and doing that just
        after playback starts is a documented way to upset A/V sync. The
        common case does not need it at all: an English-first file with an
        English preference resolves to the track Kodi already picked, and we
        were switching to it anyway on EVERY item -- so every episode of a
        run paid for a renderer change that could not change anything.

        This is a deliberately small guard rather than the several hundred
        lines of post-switch re-seek and stall detection plex-for-kodi
        carries. Their machinery does not fully work -- desync after a few
        consecutive episodes, cured by seeking back, is exactly what it is
        supposed to prevent -- so the better move is to do less to the
        renderer, not to add more code to repair it afterwards.
        """
        # NOT _current_stream(): its index is a second old on a changeover
        # and has cost this bug twice. See _playing_audio_slot.
        self._arm_audio_confirmation(slot)
        if self._playing_audio_slot() == slot:
            log.debug(f"player: audio already on slot {slot}; not switching")
            return False
        self.ui_player.setAudioStream(slot)
        return True

    def _switch_subtitle(self, slot: int) -> bool:
        """setSubtitleStream(slot), but only when it would change something.
        Same reasoning as _switch_audio."""
        # `subtitleenabled` is read from JSON-RPC (it is not cached); the
        # INDEX beside it is, so the slot comes from _playing_subtitle_slot.
        _current, enabled = self._current_stream(subtitles=True)
        if enabled and self._playing_subtitle_slot() == slot:
            log.debug(f"player: subtitles already on slot {slot}; not switching")
            return False
        self.ui_player.setSubtitleStream(slot)
        return True

    def _log_subtitle_inventory(self, when: str) -> None:
        """Everything needed to explain the subtitle panel, in one line.

        Exists because this panel cannot be diagnosed from a screenshot: the
        row COUNT is the same for several different faults, and the interesting
        state (which streams are Kodi's own versus ones we fetched) is not on
        screen at all. Reading this back from kodi.log is the difference
        between reasoning about the panel and knowing what it did."""
        try:
            streams = self._kodi_subtitle_streams()
        except Exception:                                   # noqa: BLE001
            streams = []
        loaded = set(self._loaded_subtitle_slots.values())
        native = [st for i, st in enumerate(streams) if i not in loaded]
        server_ext = [t for t in self._subtitle_tracks if t.get("external")]
        log.debug(
            "player: subs[%s] server=%d (ext %d) kodi=%d native=%d "
            "loaded=%r active=%r" % (
                when, len(self._subtitle_tracks), len(server_ext),
                len(streams), len(native), self._loaded_subtitle_slots,
                self._active_subtitle_index))

    def _select_subtitle(self, server_index) -> bool:
        """Turn a SERVER subtitle index on, however the track can be reached.

        Kodi can only select a subtitle that is a STREAM in what it is
        playing. Two common cases are not:

          * an EXTERNAL sidecar (.srt next to the video). The API says so
            outright: those indices are synthetic, start at 1000, and do not
            address a stream in the container at all.
          * ANY track at all while the server is TRANSCODING. Measured on
            "The Hourglass Sanatorium" 2026-08-06: the server offers 9
            subtitle tracks, and Kodi reports **0** subtitle streams for the
            transcoded output. Audio survives (3 streams); subtitles are not
            muxed in at all. So every track in the picker was unreachable,
            which is the "listed in the options dialog, disappears in the
            player" report.

        _stream_slot() returned None for all of them and both callers quietly
        moved on -- correct behaviour for an index it cannot map, but nobody
        had told the layer above that some tracks are never going to have a
        slot. It failed silently in exactly the case a viewer notices.

        So: use the stream when there IS one, and otherwise let Kodi fetch the
        track from the server as WebVTT. Verified that endpoint serves real
        content for a live session (HTTP 200, WEBVTT, correct cues); a 503
        right after the session opens is extraction still running.
        """
        track = next((t for t in self._subtitle_tracks
                      if t.get("index") == server_index), None)
        # Already fetched once this session: switch to the stream it became.
        # setSubtitles() APPENDS a new external stream every time it is
        # called, so without this a viewer who tries three tracks ends up with
        # three extra entries in Kodi's list, all named after the URL's last
        # segment -- "full", "full", "full". Observed exactly that.
        slot = self._loaded_subtitle_slots.get(server_index)
        if slot is not None:
            self._active_subtitle_index = server_index
            return self._switch_subtitle(slot)
        if not (track is not None and track.get("external")):
            slot = self._stream_slot(self._subtitle_order, server_index,
                                     self.ui_player.getAvailableSubtitleStreams())
            if slot is not None:
                self._active_subtitle_index = server_index
                return self._switch_subtitle(slot)
        url = self._external_subtitle_url(server_index)
        if not url:
            log.debug(f"player: no stream slot and no URL for subtitle {server_index}")
            return False
        try:
            before = len(self.ui_player.getAvailableSubtitleStreams())
        except (RuntimeError, AttributeError):
            before = None
        # setSubtitles() both loads AND enables, so a showSubtitles(True) after
        # it is a no-op rather than a fight.
        self.ui_player.setSubtitles(url)
        if before is not None:
            # Kodi appends, so the new stream is the one past the end.
            self._loaded_subtitle_slots[server_index] = before
        self._active_subtitle_index = server_index
        log.debug(f"player: loaded subtitle {server_index} by URL as slot {before}")
        return True

    def _external_subtitle_url(self, server_index) -> str:
        """The server's own delivery of a track, in the format Kodi can read.

        `.vtt` rather than `.ass` for a TEXT track: Kodi renders both, but ASS
        carries styling the skin has no say over, and 8's subtitles are meant
        to look like the rest of the app.

        A VobSub sidecar is the one exception, and it cannot be a `.vtt` at
        all -- it is a pair of bitmap files, and the server answers 400 for
        any bitmap track asked for as WebVTT. Server 0.9.32 serves that pair
        as `full.idx` plus a companion `full.sub`, and we ask for the `.idx`
        half only: Kodi DERIVES the `.sub` itself (`CVideoPlayer::
        AddSubtitleFile` -> `CUtil::GetVobSubSubFromIdx` ->
        `URIUtils::ReplaceExtension`).

        That derivation is why the extension has to sit where it does. For a
        URL, ReplaceExtension goes through `CURL`, which holds the query
        string separately from the filename -- so `full.idx?st=<token>`
        becomes `full.sub?st=<token>`, token intact, rather than the
        `full.idx?st=....sub` a plain string swap would produce. MEASURED on
        Kodi 21.3 against a mock of these two routes that 401s without the
        token: Kodi asked for `full.idx?st=...`, then HEADed
        `full.sub?st=...`, then range-read both, and rendered the cues.

        `.sup` (PGS) is deliberately NOT mapped here even though the server
        offers that route too: it is a separate delivery path with its own
        demuxer and nothing has measured it. Bitmap PGS reaches this method
        only under a transcode, where it is a pre-existing 400 rather than
        something this change introduces.

        The endpoint wants the scoped session token as `st`, the same one the
        progress and teardown calls use."""
        nego = self._nego or {}
        session_id, token = nego.get("session_id"), nego.get("session_token")
        if not (session_id and token and self.client):
            return ""
        track = next((t for t in self._subtitle_tracks
                      if t.get("index") == server_index), None)
        name = "full.idx" if self._is_vobsub_sidecar(track) else "full.vtt"
        return self.client.resolve_url(
            f"/api/v1/stream/s/{session_id}/subtitles/{server_index}"
            f"/{name}?st={urllib.parse.quote(str(token))}")

    @staticmethod
    def _is_vobsub_sidecar(track) -> bool:
        """Whether this track is one the `full.idx`/`full.sub` routes serve.

        BOTH halves are required. The routes answer 400 for anything that is
        not "a paired VobSub sidecar", and an EMBEDDED `dvd_subtitle` -- an
        old disc rip muxed into the container -- is a real thing that reaches
        the URL path whenever the server is transcoding and Kodi therefore
        has no subtitle stream to select. Asking for `.idx` there would turn
        a track that merely does not appear into a 400."""
        if not track:
            return False
        return (str(track.get("codec") or "").strip().lower() == "dvd_subtitle"
                and bool(track.get("external")))

    @staticmethod
    def _stream_slot(order: list, server_index: int, available: list):
        """Map a server stream index onto Kodi's own position among the
        streams of that ONE kind.

        Kodi numbers audio streams 0..n-1 in the order it finds them, which
        is not the server's absolute stream index -- track "1" of a file
        whose stream 0 is video is Kodi's audio stream 0. The two lists
        describe the same file in the same order, so position IS the
        mapping; `order` is the server's index sequence taken from the
        negotiation THIS playback ran, not from the dry run the dialog was
        built on, so a server that reordered or dropped a track in between
        cannot silently shift the pick onto its neighbour.

        Returns None rather than guessing when the counts disagree: a wrong
        track applied confidently is worse than the file's own default."""
        try:
            slot = order.index(server_index)
        except ValueError:
            return None
        return slot if slot < len(available) else None

    # ------------------------------------------------------------------
    # chrome mode
    # ------------------------------------------------------------------

    def reveal_chrome(self, focus_id: int | None = None):
        """Show the transport chrome and (re-)anchor its auto-hide.

        Every reveal lands focus on play/pause, never on the scrubber --
        measured on the reference app, and it is the safer default: the
        scrubber's left/right are destructive-ish, the transport row's are
        not."""
        first = not self._chrome_deadline
        self._chrome_deadline = time.monotonic() + CHROME_AUTO_HIDE_S
        self._pause_card_deadline = 0.0
        self.setProperty("player_chrome", "1")
        self.setProperty("player_pause_card", "")
        if self._modal:
            # A panel owns focus while it is up, and revealing the chrome
            # underneath it must not take that away. The stereoscopic
            # question is the case that found this: it raises ITSELF from the
            # tick, and on_playback_started arms it several statements before
            # it calls the first reveal_chrome(). Everything in between --
            # resolving the duration, rendering the markers, a resume seek --
            # is slow enough on an older box for a tick to land in the
            # middle, so the panel opens first and the reveal then arrives
            # with `first` still True and drags focus to play/pause.
            #
            # Measured on the AM6B+ (Kodi 21.3, 4.9 kernel) with Hugo:
            # panel on screen, focus on 9121, no row highlighted, and no way
            # to reach the panel at all -- its nav targets are all NAV_STOP,
            # so it is only ever reachable by a programmatic focus.
            return
        if first or focus_id is not None:
            self.setFocusId(focus_id or self.PLAYPAUSE_ID)

    def anchor_chrome(self):
        """Push the auto-hide out without changing focus. Every key press
        that the chrome itself consumed does this (10.3: any toggle restarts
        the chrome's auto-hide clock)."""
        if self._chrome_deadline:
            self._chrome_deadline = time.monotonic() + CHROME_AUTO_HIDE_S

    def hide_chrome(self):
        """Drop the chrome and park focus on the bare surface. Also cancels
        any pending scrub -- 10.1 folds those two into one back press, and
        an auto-hide that left a scrub armed but invisible would be worse."""
        self._chrome_deadline = 0.0
        self._scrub_ms = None
        self.setProperty("player_scrubbing", "")
        self.setProperty("player_chrome", "")
        self.setFocusId(self.SURFACE_ID)
        # 8.8's pause card is revealed 5.0s AFTER the chrome goes, not 5.0s
        # after the pause -- so it is armed here, not in onPlayBackPaused.
        if self.getProperty("player_state") == self.STATE_PAUSED:
            self._pause_card_deadline = time.monotonic() + PAUSE_CARD_DELAY_S

    def on_paused(self):
        """Arm the pause card for a pause this window did not itself handle.

        8.8 reveals the card 5.0s after the CHROME goes, so hide_chrome()
        arms it -- which works when the pause came through our own onAction,
        because that reveals the chrome first and the auto-hide follows.

        A remote's PAUSE key does not necessarily reach us: Kodi's global
        keymap can act on it and pause the player directly, so onAction never
        runs, the chrome is never revealed, hide_chrome() never fires and the
        card was never armed. Reported from the box as "playback pauses but
        the pause screen doesn't appear".

        With the chrome already down there is no chrome-hide to wait for, so
        the same delay is measured from the pause itself."""
        # BEFORE the early return below: the countdown has to stop whether or
        # not the chrome happens to be up, and that return is only about
        # which thing arms the pause card.
        self._hold_next_up()
        if self._chrome_deadline:
            return          # chrome is up -- hide_chrome() arms it as usual
        if self.getProperty("player_state") == self.STATE_PAUSED:
            self._pause_card_deadline = time.monotonic() + PAUSE_CARD_DELAY_S

    def hide_pause_card(self):
        self._pause_card_deadline = 0.0
        self.setProperty("player_pause_card", "")

    def toggle_play_pause(self):
        """300ms debounce (10.3/10.6). Kodi's own pause action is level-
        triggered, so a remote that repeats the key would otherwise
        stutter play/pause several times per press."""
        if self._restarting:
            # Mid-changeover: the item has been replaced and the new one has
            # not started. There is nothing to pause, and the only presses
            # that arrive here are the tail of the one that CAUSED the
            # changeover -- see _play_episode. Pausing on it is how "Play
            # Next switches episode and then playback pauses" happened.
            log.debug("player: ignoring play/pause during a changeover")
            return
        now = time.monotonic()
        if now - self._last_toggle < PLAY_PAUSE_DEBOUNCE_S:
            return
        self._last_toggle = now
        # Logged because "playback paused itself" has now been reported
        # twice, and the only way to tell OUR pause from Kodi's own is to
        # see whether this line ran. Cheap: once per deliberate press.
        log.debug(f"player: toggle_play_pause from control {self.getFocusId()}")
        try:
            self.ui_player.pause()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # seeking
    # ------------------------------------------------------------------

    def _position_ms(self) -> int:
        """Where we are in the FILE, which is not always where Kodi thinks.

        On an HLS session the server cut at a resume offset, Kodi's clock
        starts at zero for a stream whose first frame is already
        _time_offset_ms into the title. Every consumer of this -- the
        scrubber, the OSD clock, skip segments, Next Up's end detection,
        the progress written on close-out -- wants file coordinates, so the
        offset is added here once rather than at each of them.

        The last live reading is cached because the most interesting callers
        run AFTER Kodi has torn the player down -- onPlayBackEnded asking how
        far in we got, the close-out writing the resume point. getTime()
        raises there, and answering 0 would say "never started" about an
        episode somebody watched most of. Same reasoning, same fix as
        monitor.TofaPlayer._position_ms."""
        try:
            ms = int(self.ui_player.getTime() * 1000) + self._time_offset_ms
        except (RuntimeError, AttributeError):
            # AttributeError: onClosed has released ui_player. Same answer as
            # a torn-down player -- the last reading we trusted.
            return self._last_live_position_ms
        # Never before the start of the file. Kodi's clock reads slightly
        # negative between play() and the first frame, which is a window this
        # window is always awake for -- and everything downstream treats the
        # number as a file coordinate: the scrubber would compute a negative
        # fraction, the OSD clock would print a negative time, and the
        # close-out would write it as a resume point. Same clamp, same
        # reason, as monitor.TofaPlayer._position_ms.
        self._last_live_position_ms = ms = max(0, ms)
        return ms

    def _resolve_duration_ms(self) -> int:
        """How long the TITLE is, in ms.

        The negotiation's `duration_ms` wins over Kodi's getTotalTime(),
        because on a server-cut HLS session Kodi is timing the STREAM it
        was handed -- which begins at the resume offset and is therefore
        shorter than the film. Trusting it there put the scrubber's full
        width on the remaining part of the episode and made Next Up's
        "30s from the end" fire at the wrong moment.

        Kodi's own reading stays the fallback, for a DirectPlay stream or a
        negotiation that did not carry a duration. Same choice the web
        client makes -- see its knownDurationSec."""
        try:
            declared = int((self._nego or {}).get("duration_ms") or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > 0:
            return declared
        try:
            return int(self.ui_player.getTotalTime() * 1000)
        except (RuntimeError, AttributeError):
            return 0

    def _media_ms(self, file_ms: int) -> float:
        """File coordinates -> the media clock Kodi's seekTime() wants."""
        return max(0, file_ms - self._time_offset_ms) / 1000.0

    # ------------------------------------------------------------------
    # seek ladder
    # ------------------------------------------------------------------
    #: Rungs, in ms, used when Kodi's own setting cannot be read. Kodi's
    #: default videoplayer.seeksteps is the same shape.
    _SEEK_LADDER_FALLBACK = (10_000, 30_000, 60_000, 180_000, 300_000, 600_000)

    #: ADJUSTABLE, and worth knowing how far it travels. The rungs above are
    #: Kodi's videoplayer.seeksteps default, and the escalation is
    #: CUMULATIVE, so a burst of presses in one direction adds up fast:
    #:
    #:   press   1     2     3      4      5       6      7+
    #:   step    10s   30s   60s    3min   5min    10min  10min
    #:   total   0:10  0:40  1:40   4:40   9:40    19:40  +10min each
    #:
    #: Four quick presses is already ~4:40 and six is nearly twenty minutes;
    #: the 60s -> 180s jump is where it runs away. Raised as "it goes too far
    #: up" (2026-08-05) and deliberately NOT changed: these are the viewer's
    #: own Kodi numbers, so someone who edits videoplayer.seeksteps expects
    #: to get them, and capping ours would silently diverge from the setting
    #: we chose to read.
    #:
    #: If it does need taming, the two honest levers are capping the ladder
    #: (slice the rungs in _seek_ladder) or requiring two presses per rung
    #: (in _seek_step_ms). Both are a couple of lines. _SEEK_LADDER_DECAY_S
    #: below is the third, and already softens the common case.

    #: A burst of presses escalates; a pause drops back to the bottom rung.
    #: plex-for-kodi has no such decay -- its ladder only resets on a commit
    #: or a direction change, so six slow deliberate taps still end up
    #: jumping ten minutes. 1.5s is comfortably longer than a key-repeat
    #: interval and comfortably shorter than "I thought about it".
    _SEEK_LADDER_DECAY_S = 1.5

    def _seek_ladder(self) -> tuple:
        """The rungs, from Kodi's own `videoplayer.seeksteps`.

        Read from Kodi rather than invented, for the same reason the number
        formatting is: it is a real setting the viewer can change, and
        plex-for-kodi reads exactly this. The setting is a symmetric list in
        SECONDS (-600...-10, 10...600); only the positive half is needed,
        since direction is handled separately.

        Cached: it cannot change while a video plays."""
        if self._seek_ladder_cache is not None:
            return self._seek_ladder_cache
        rungs = ()
        try:
            raw = xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "Settings.GetSettingValue",
                "params": {"setting": "videoplayer.seeksteps"},
            }))
            value = json.loads(raw).get("result", {}).get("value") or []
            rungs = tuple(int(s) * 1000 for s in sorted(value) if int(s) > 0)
        except Exception as exc:
            log.debug("player: seeksteps unreadable, using fallback ({0})".format(exc))
        self._seek_ladder_cache = rungs or self._SEEK_LADDER_FALLBACK
        return self._seek_ladder_cache

    def _seek_step_ms(self, forward: bool) -> int:
        """The next step, escalating on repeated presses in one direction.

        Three rules, two of them from plex-for-kodi's determineSkipStep and
        the third ours:

        * same direction again -> climb one rung, clamped at the top
        * REVERSE -> walk back one rung and apply that rung inverted, so a
          correction undoes what the last press did instead of flinging the
          viewer the other way at the rung they had climbed to
        * idle longer than the decay -> drop to the bottom rung, so slow
          deliberate taps stay at 10s and only a fast burst travels far
        """
        ladder = self._seek_ladder()
        now = time.monotonic()
        same = (self._seek_dir == forward)
        stale = (now - self._seek_last_at) > self._SEEK_LADDER_DECAY_S
        self._seek_last_at = now

        if stale or self._seek_rung < 0:
            self._seek_rung = 0
        elif same:
            self._seek_rung = min(self._seek_rung + 1, len(ladder) - 1)
        else:
            # Reversing. Return the rung the last press used and only THEN
            # step down, so the first press back is worth exactly what the
            # last one forward was and the two cancel. Stepping down first
            # returns the rung below and the correction undershoots -- which
            # is what the first version here did (180 forward, 60 back).
            step = ladder[self._seek_rung]
            self._seek_rung = max(0, self._seek_rung - 1)
            self._seek_dir = forward
            return step
        self._seek_dir = forward
        return ladder[self._seek_rung]

    def _reset_seek_ladder(self):
        """Back to the bottom rung. Called when a seek is committed or the
        chrome is dismissed -- the next press starts a new gesture."""
        self._seek_rung = -1
        self._seek_dir = None
        self._seek_last_at = 0.0

    def quick_seek(self, forward: bool):
        """10.4's chrome-hidden seek, with 8.9's toast.

        The step ESCALATES on repeated presses (see _seek_step_ms). 10.4
        sanctions "a flat +/-10s per OS key-repeat" as the fallback where
        press phases cannot be told apart, and Kodi genuinely cannot --
        onAction only ever sees an already-debounced action. But counting
        repeats is a lever Kodi does give, plex-for-kodi uses exactly that,
        and on a three-hour film a flat 10s is unusable. Approved as a
        divergence 2026-08-04; see internal-docs/DIVERGENCES.md.

        A single press is still 10s, so nothing about the simple case moved.
        """
        step = self._seek_step_ms(forward)
        self._seek_to(self._position_ms() + (step if forward else -step))
        self.setProperty("player_seek_toast", "forward" if forward else "back")
        # The toast DOES announce the amount. It had "10s" hardcoded in the
        # XML, which stopped being true the moment the step escalated -- a
        # 10-minute jump captioned "10s". An earlier pass here concluded the
        # toast had no slot for it and dropped the property; the slot was
        # there all along, just frozen.
        self.setProperty("player_seek_amount", _seek_amount_label(step))
        self._toast_deadline = time.monotonic() + SEEK_TOAST_S

    def chapter_seek(self, forward: bool):
        """Kodi's chapter keys, served from QuickView's chapter list.

        Back gets a 2s grace before it counts as "already at the start", so
        the first press restarts the CHAPTER YOU ARE IN and only a second
        one goes back past it -- the way track-previous works on a CD.
        Kodi's own key does SeekChapter(chapter - 1), which always jumps a
        whole chapter back and makes restarting the current one impossible;
        plex-for-kodi's seekdialog.skipChapter uses the grace, and it is the
        better behaviour.

        With no chapters at all it falls back to a big step, which is
        exactly what Kodi's ACTION_CHAPTER_OR_BIG_STEP_* does when a file
        has none -- the action is named for that fallback."""
        position = self._position_ms()
        if not self._chapters:
            step = self._scrub_step_ms()
            self._seek_to(position + (step if forward else -step))
            self.setProperty("player_seek_toast", "forward" if forward else "back")
            self._toast_deadline = time.monotonic() + SEEK_TOAST_S
            return
        starts = [start for start, _label in self._chapters]
        if forward:
            target = next((s for s in starts if s > position), None)
            if target is None:
                return
        else:
            limit = max(0, position - _CHAPTER_BACK_GRACE_MS)
            earlier = [s for s in starts if s <= limit]
            target = earlier[-1] if earlier else 0
        self._seek_to(target)
        self.refresh_progress()

    def _seek_to(self, target_ms: int):
        """Seek to a position in the FILE. The only seek in this window.

        On DirectPlay this is Kodi's own seek and always was. On an HLS
        session it may not be: the server produces that stream sequentially
        from wherever it was cut, so a target outside what has been produced
        is a seek into content that does not exist yet, and Kodi stalls on it
        until it gives up. That is the "playback never starts, then drops
        back to Detail" failure.

        So a target the current stream cannot serve is handed to the server,
        which re-cuts the session at that position -- see _seek_via_session.
        """
        target_ms = max(0, min(target_ms, self._duration_ms or target_ms))
        if self._needs_session_seek(target_ms):
            if self._seek_via_session(target_ms):
                return
            # Fell through: the session seek failed and said so. Kodi's own
            # seek will not land on an HLS playlist (see
            # _needs_session_seek), so this is not a real fallback -- but it
            # costs nothing, and it is the right thing for the case where
            # the session has gone and the stream is no longer HLS.
        try:
            self.ui_player.seekTime(self._media_ms(target_ms))
        except RuntimeError:
            pass

    #: A seek small enough not to be worth a stream re-cut. Kodi reports
    #: whole seconds, so anything under a second cannot be distinguished
    #: from where we already are.
    SEEK_NOOP_MS = 1_000

    def _needs_session_seek(self, target_ms: int) -> bool:
        """Whether this seek has to be re-cut by the server.

        ON AN HLS SESSION, ALWAYS -- Kodi cannot seek these streams at all.

        Measured on the CoreELEC box 2026-08-07, forcing HlsRemux and
        calling seekTime() directly at +10s, +30s, +60s, +120s and +300s
        from the play head: not one landed. The clock simply carried on
        playing, so a "seek" was indistinguishable from doing nothing.

        The mechanism is in the playlist the server serves, and it is not a
        bug on either side:

            #EXT-X-PLAYLIST-TYPE:EVENT
            #EXT-X-MEDIA-SEQUENCE:150
            (no #EXT-X-ENDLIST)

        An EVENT playlist with no ENDLIST is a growing one by the HLS spec.
        Players treat it as live, and live streams are not arbitrarily
        seekable -- so Kodi is right to refuse. The server's own
        /stream/s/{id}/seek exists precisely because this is how the
        playlist is shaped.

        This method used to allow a local seek within
        HLS_LOCAL_SEEK_AHEAD_MS (30s) of the play head, on the guess that a
        short hop would land in produced content. The guess was wrong in
        kind rather than degree: distance was never the constraint,
        seekability was. The web client gets away with a local fast path
        only because hls.js manages its own buffer and can be asked what it
        holds; Kodi exposes no equivalent, just a cache percentage with no
        time axis.
        """
        if not self._hls_session():
            return False
        return abs(target_ms - self._position_ms()) >= self.SEEK_NOOP_MS

    def _hls_session(self) -> tuple:
        """(session_id, session_token) when the playing stream is a
        server-managed HLS session that can be re-cut, else ()."""
        nego = self._nego or {}
        if playback.is_whole_file(nego):
            return ()
        sid, token = nego.get("session_id"), nego.get("session_token")
        return (sid, token) if sid and token else ()

    def _seek_via_session(self, target_ms: int) -> bool:
        """Ask the server to re-cut this session at `target_ms`, then reopen.

        POST /stream/s/{id}/seek answers with a fresh stream_url and the
        position it actually landed on -- keyframe-aligned, so a little off
        what was asked for, which the API documents. That answer becomes the
        new time offset, exactly as the web client does it.

        Kodi has no equivalent of hls.js's loadSource(), so the reopen is a
        play() on the same window. That re-enters onAVStarted, which is
        wanted: track selection and the refresh rate get re-applied to what
        is genuinely a new stream.

        Returns whether the seek was taken. False leaves the caller to fall
        back rather than silently swallowing a press.
        """
        session = self._hls_session()
        if not (session and self.client):
            return False
        sid, token = session
        try:
            resp = self.client.seek_stream(sid, token, target_ms)
        except http.ApiError as exc:
            if exc.status in (404, 410):
                # The session is gone. Nothing to re-cut, and the stream we
                # are playing is on borrowed time; renegotiating from
                # scratch is the honest recovery.
                log.warning(f"player: session gone on seek ({exc}); renegotiating")
                self.resume_ms = target_ms
                self._restarting = True
                self.setProperty("player_state", self.STATE_OPENING)
                self._start_playback()
                return True
            log.warning(f"player: session seek failed: {exc}")
            return False
        except Exception as exc:                        # noqa: BLE001
            log.warning(f"player: session seek failed: {exc!r}")
            return False

        url = resp.get("stream_url")
        if not url:
            return False
        landed_ms = playback.start_offset_ms(resp)
        log.info("player: session re-cut at %dms (asked %dms)" % (landed_ms, target_ms))
        self._time_offset_ms = landed_ms
        self._publish_time_offset()
        # The scrub head should sit where the viewer asked immediately,
        # rather than snapping back to zero while the new stream opens.
        self._duration_ms = self._resolve_duration_ms()
        self.setProperty("player_state", self.STATE_OPENING)
        self._stream_url = self.client.resolve_url(url)
        # _restarting so onPlayBackStopped does not tear this window down
        # when Kodi closes the outgoing stream to open the new one.
        self._restarting = True
        try:
            li = playback.build_list_item(
                {"stream_url": self._stream_url,
                 "duration_ms": self._duration_ms,
                 "play_method": (self._nego or {}).get("play_method")},
                title=self.title or "")
            self.ui_player.play(self._stream_url, li)
        except Exception as exc:                        # noqa: BLE001
            log.warning(f"player: could not reopen after seek: {exc!r}")
            self._restarting = False
            return False
        self.refresh_progress()
        return True

    def _publish_time_offset(self):
        """Tell monitor.py (in service.py) where this stream starts.

        It reports progress from Kodi's clock, which on a server-cut session
        is short by the offset -- so without this a transcoded resume would
        write back a position earlier than where the viewer actually is, and
        the next resume would drift backwards every time.

        A Window(10000) property because that is the only channel to the
        other process, and the same one the session handoff already uses.
        Written on every change (a session re-cut moves it) and cleared when
        the window closes.
        """
        monitor.publish_time_offset(self._time_offset_ms)

    def _scrub_step_ms(self) -> int:
        """10.4/10.6's clamp(duration/60, 10s, 60s)."""
        if not self._duration_ms:
            return SCRUB_STEP_MIN_MS
        return max(SCRUB_STEP_MIN_MS, min(self._duration_ms // 60, SCRUB_STEP_MAX_MS))

    def scrub(self, forward: bool):
        """Move the pending scrub target. Nothing is seeked until select
        commits it -- which is what makes back able to cancel.

        Uses the same escalating ladder as the chrome-hidden seek, so the
        two surfaces behave alike; plex-for-kodi routes both through one
        determineSkipStep for the same reason. The old flat
        clamp(duration/60, 10s, 60s) is now only the FIRST rung's neighbour
        in spirit -- a single press still moves a small, predictable amount.
        """
        step = self._seek_step_ms(forward)
        base = self._scrub_ms if self._scrub_ms is not None else self._position_ms()
        self._scrub_ms = max(0, min(base + (step if forward else -step),
                                    self._duration_ms or base))
        self.setProperty("player_scrubbing", "1")
        self.anchor_chrome()
        self.refresh_progress()

    def commit_scrub(self):
        # A committed seek ends the gesture; the next press starts over at
        # the bottom rung rather than continuing from where this one climbed.
        self._reset_seek_ladder()
        if self._scrub_ms is None:
            return False
        self._seek_to(self._scrub_ms)
        self._scrub_ms = None
        self.setProperty("player_scrubbing", "")
        self.refresh_progress()
        return True

    def cancel_scrub(self):
        if self._scrub_ms is None:
            return False
        self._scrub_ms = None
        self.setProperty("player_scrubbing", "")
        self.refresh_progress()
        return True

    # ------------------------------------------------------------------
    # the ticker
    # ------------------------------------------------------------------

    def _tick_loop(self):
        while not self._stop_tick.wait(_TICK_S):
            if self._closing:
                return
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - a ticker must never die
                log.warning(f"player: OSD tick failed: {exc!r}")

    #: Kodi's own fullscreen video window, which now OWNS the screen.
    _KODI_FULLSCREEN_VIDEO = 12005

    def _close_kodi_osd(self):
        """Keep Kodi's own OSD off the screen.

        This REPLACES _reclaim_from_kodi_osd(). That one existed because our
        window replaced Kodi's video window, so Kodi raising FullScreenVideo
        (its "return to playback" button does exactly that) put a second
        player UI over a stream we were driving, and stopping from the wrong
        one left a black screen. It took the screen back with ReplaceWindow.

        Now Kodi owns the screen and we are a dialog on top of it, so there
        is nothing to take back -- FullScreenVideo being up is the NORMAL
        state. What must not appear is Kodi's `videoosd`, which its own skin
        raises on input and which would sit alongside our chrome saying the
        same things differently. plex-for-kodi does exactly this
        (seekdialog.py: Dialog.Close(videoosd,true)).

        `busydialog` goes with it, and that one is what a viewer actually
        NOTICES: reported from the box as "I see the Estuary spinner", on an
        episode start, with no seekbar in the log -- Kodi's busy spinner
        during the stream open, raised after our dialog and therefore on top
        of the branded one we put in the opening card for exactly this job.
        Two spinners for one wait, the wrong one in front.

        Closed unconditionally while this player is alive, which is narrower
        than it sounds: this method only runs from our own tick, so the
        window is precisely "tofa is playing something", and throughout it we
        are already showing our own indicator -- the opening card's arc
        before first frame, 8.6's rebuffer badge after. plex guards theirs
        with `+ !Player.Caching` because they only mean to clear a STUCK
        dialog; we mean to clear it always, because ours replaces it.

        ONLY `videoosd`, deliberately. Kodi 21 also raises `seekbar`
        (DialogSeekBar.xml, plus whatever the active skin hangs off it --
        Estuary adds Custom_1109_TopBarOverlay) for ~3.5s at playback start,
        which is what "for the first few seconds I see Estuary's player
        controls" is. Closing that one from this method was measured and
        REVERTED: Kodi re-raises it at once, so the 200ms tick produced a
        Deinit/Init pair every ~350ms for the whole 3.5s. Trading a bar that
        sits still for one that strobes is not a fix.

        The seek bar is deliberately NOT touched here. See the block below
        this method for what was measured and why both available fixes fail.

        `sliderdialog` joined the list for the Adjust panel's subtitle row.
        Kodi has no `Player.SetSubtitleDelay` -- confirmed by introspecting
        the running Kodi 22 on the box, not just the 21.3 binary -- so the
        only lever is `Action(subtitledelayplus)`, and Kodi answers that by
        raising its OWN slider, drawn by whatever skin is installed. Reported
        from the box as "the default Estuary bar also appears". Unlike
        `seekbar`, Kodi raises this one per PRESS rather than continuously,
        so closing it sticks -- the same reasoning that lets us adopt
        `playerprocessinfo`.
        """
        if self._closing:
            return
        for dialog in ("videoosd", "busydialog", "busydialognocancel",
                       "sliderdialog"):
            try:
                if xbmc.getCondVisibility(f"Window.IsActive({dialog})"):
                    xbmc.executebuiltin(f"Dialog.Close({dialog},true)")
            except Exception:                               # noqa: BLE001
                pass

    # `playerprocessinfo` IS KODI'S, and we no longer take it.
    #
    # We used to: Kodi's global keymap opens the active skin's
    # DialogPlayerProcessInfo before our window sees the key at all, so the
    # tick watched for that dialog, closed it, and showed 8.11 instead.
    # Adrian, 2026-08-11: "the skin's default panel flashes before ours is
    # coming up." That flash is not a bug in the adoption, it is the shape of
    # it -- Kodi draws its panel, we notice a tick later (up to 200ms) and
    # close it. There is no earlier hook, because the keymap runs above us.
    #
    # So the trade was: our panel reachable by the familiar key, at the cost
    # of a visible flash on every press. Adrian's call is to give the key
    # back. 8.11 is reached from the utility capsule's stats button
    # (STATS_ID) and the digit keys, both of which are ours end to end and
    # neither of which flashes. Kodi's own panel does whatever Kodi does.
    #
    # If it is ever wanted back, the flash is the thing to solve first, and
    # the only real fix is a keymap that stops Kodi acting on the key --
    # a <keymap> in userdata, which is outside the add-on and needs asking
    # (feedback_consent_before_touching_outside).

    # NOT handled here, and now for a measured reason rather than an unknown
    # one. Kodi raises `seekbar` (DialogSeekBar, plus whatever the skin hangs
    # off it -- Estuary adds Custom_1109_TopBarOverlay across the TOP of the
    # screen) for ~3.3s after any seek it runs itself, including our resume
    # seek and, per the owner, a mid-playback subtitle change.
    #
    # The docstring above used to say no condition could detect it. FALSE, and
    # corrected 2026-08-06: sampling XBMC.GetInfoBooleans at 3.5Hz across a
    # seek, `Window.IsActive(seekbar)`, `Window.IsActive(10115)` and
    # `Window.IsActive(1109)` all read TRUE together for ~3.3s and then clear.
    # The earlier reading was presumably taken at playback start, where the
    # timing differs. So the trigger exists.
    #
    # Both things you can do WITH that trigger were then built and measured,
    # and both fail:
    #
    #   * re-show this dialog to out-rank it (plex-for-kodi's shape,
    #     SeekHandler.onVideoOSD -> showOSD). Ran -- the debug line is in the
    #     log twice -- and a frame captured while the condition read TRUE
    #     still shows Estuary's bar on top. show() on an already-active
    #     dialog does not move it up Kodi's dialog stack.
    #   * close it once, edge-triggered rather than the old every-tick close
    #     that made it strobe. `Dialog.Close(seekbar,true)` executed (the
    #     harness logged it) and the bar stayed up until its own timer expired.
    #
    # THE RE-ARCHITECTURE WOULD NOT HAVE HELPED, and that was measured before
    # building it rather than after. plex-for-kodi's shape is "one dialog
    # shown once and never re-shown, OSD visibility a property on it" -- but
    # this window IS already that: a ControlledDialog whose chrome is driven
    # by _chrome_deadline, shown once. The other half of plex's approach,
    # "commit with seekTime() rather than letting Kodi run its own seek
    # action", does not help either. Measured, one operation at a time, with
    # the bar sampled at 3.3Hz after each:
    #
    #     our quick-seek, right key (seekTime)   RAISES IT
    #     our quick-seek, left key  (seekTime)   RAISES IT
    #     JSON-RPC Player.Seek                   RAISES IT
    #     switch subtitle stream                 clean
    #     switch subtitle off                    clean
    #     switch audio stream                    clean
    #
    # So EVERY seek raises it, seekTime() included -- the older note here
    # claiming our own quick-seek was clean is wrong -- and no stream switch
    # does. (Which also means the reported "I see it after changing
    # subtitles" is a seek near the change, not the change.)
    #
    # Every route out is now closed by measurement:
    #   * close it            -- Dialog.Close(seekbar,true) executed, bar
    #                            stayed up until its own timer expired
    #   * re-show ours over it-- show() reaches xbmcgui.WindowXMLDialog.show,
    #                            so it is a real call, and a frame captured
    #                            while the condition read TRUE still had
    #                            Estuary's bar on top. A dialog cannot
    #                            out-rank a dialog Kodi activated later.
    #   * seekTime()          -- see the table
    #   * a Kodi setting      -- there is none; only seeksteps/seekdelay
    #   * not seeking         -- not an option
    #
    # The one route left is not in the add-on at all: inject a <visible>
    # condition into the ACTIVE SKIN's DialogSeekBar.xml, gated on one of our
    # own Window properties, the same mechanism fontinstall.py uses on
    # Font.xml. Surgical (Kodi's bar keeps working outside tofa) but it edits
    # a skin the user installed, so it needs asking first -- see
    # feedback_consent_before_touching_outside. Not done.

    def _tick(self):
        now = time.monotonic()
        if self._restore_focus_at and now >= self._restore_focus_at:
            expected, self._restore_focus_at = self._restore_focus_from, 0.0
            self._restore_focus_from = None
            try:
                # ONLY if that same control still holds focus. Keyed on the
                # control rather than on a set of candidates because the
                # candidates overlap in time: the Skip pill defers a restore,
                # and 200ms later the Next Up rail takes focus for its own
                # Play Next button. A set-membership test then fired the
                # pill's restore against the RAIL, dropping focus onto the
                # bare surface with the rail still up -- so the viewer's
                # press reached the surface and toggled pause instead of
                # playing the next episode. Measured, not theorised.
                if expected is not None and self.getFocusId() == expected:
                    self.setFocusId(self.SURFACE_ID)
            except RuntimeError:
                pass
        self._close_kodi_osd()
        self._confirm_audio_slot(now)
        # Anything a `stats` notification asked for, applied HERE because
        # this is the UI thread; see request_stats_mode.
        self._apply_stats_request()
        self._hold_panel_focus(now)
        # Raised from the tick, not from on_playback_started: the panel
        # steals focus, and doing that in the middle of the start sequence
        # races reveal_chrome(). One tick later everything has settled.
        if self._stereo_pending and not self.getProperty("player_panel"):
            self.offer_stereo_mode()
        if self._chrome_deadline and not self._modal and now >= self._chrome_deadline:
            self.hide_chrome()
        if self._stats_mode and now >= self._stats_next_refresh:
            self._stats_next_refresh = now + STATS_REFRESH_S
            self._refresh_stats()
        if self._pause_card_deadline and now >= self._pause_card_deadline:
            if self._stats_mode:
                # A stats readout owns the screen. Push the card out rather
                # than dropping it, so closing the stats while still paused
                # gets the card's full 5.0s instead of it snapping straight in
                # on a deadline that expired minutes ago.
                self._pause_card_deadline = now + PAUSE_CARD_DELAY_S
            else:
                self._pause_card_deadline = 0.0
                self.setProperty("player_pause_card", "1")
                self.setProperty(
                    "player_time_left",
                    _format_remaining(self._duration_ms - self._position_ms()))
        if self.getProperty("player_pause_card"):
            # 8.8's live clock, ticking once per second. Follows Kodi's own
            # regional setting: 22:41 on a 24-hour region, 10:41 PM on a
            # 12-hour one. This used to force "%H:%M" precisely BECAUSE
            # $INFO[System.Time(hh:mm)] renders 12-hour -- i.e. it overrode
            # the region on purpose. Overridden back by the user 2026-08-04:
            # the tofa API has no say here (its `region` drives ratings and
            # age restrictions, not clocks), so the Kodi setting wins because
            # it is the one the viewer can actually change.
            self.setProperty("player_clock", regional.clock())
        if self._toast_deadline and now >= self._toast_deadline:
            self._toast_deadline = 0.0
            self.setProperty("player_seek_toast", "")
        # Everything below asks Kodi about the stream, and there is no stream
        # once playback has gone. Each of those calls raises inside Kodi and
        # is logged there as `EXCEPTION: Kodi is not playing any media file`
        # -- at 5Hz, from a ticker that outlives the player. The box's log
        # carried ~99 of them per 10s window after the 2026-08-08 stall, and
        # in the middle of them sat two 20s `CCurlFile::Stat` retries against
        # the dead stream URL, while Kodi's own CloseFile waited. The window
        # stayed on a black screen for 57s before it finally closed.
        #
        # The chrome, focus and clock work above still runs: 8.7's card is
        # displayed by this same window, so the ticker must keep serving it.
        if not self._playback_live():
            # Whatever the chip was saying about a stream that no longer
            # exists, it is not saying it any more.
            self._clear_rebuffer()
            return
        self._tick_rebuffer(now)
        self._tick_skip(now, self._position_ms())
        self._tick_next_up(now)
        if self._chrome_deadline:
            self.refresh_progress()

    def _playback_live(self) -> bool:
        """Is there still a stream to ask questions about?

        isPlaying() is the one player call that answers rather than raising
        when the answer is no, which is what makes it usable as the guard."""
        try:
            return bool(self.ui_player and self.ui_player.isPlaying())
        except RuntimeError:
            return False

    def _tick_next_up(self, now: float):
        """8.3's reveal and its countdown, both driven off the same clock.

        The rail is armed by POSITION and expires by WALL CLOCK, which is
        deliberate: it should appear 30s before the end of the episode, but
        once it is up the 20,000ms countdown is a stated contract and has to
        run at that rate whether or not playback is still moving -- pausing
        under an open rail must not freeze the timer into a rail that never
        resolves."""
        if self._next_up_open:
            # Only `auto` has a deadline; `ask` shows the same rail and
            # waits, so the countdown block is skipped and the rail simply
            # stays up until it is pressed or dismissed.
            if self._next_up_deadline:
                remaining = self._next_up_deadline - now
                if remaining <= 0:
                    self.play_next_up()
                    return
                self.setProperty("nextup_seconds", str(int(remaining) + 1))
                step = int(round(NEXT_UP_RING_STEPS * remaining / NEXT_UP_COUNTDOWN_S))
                self.setProperty(
                    "nextup_ring",
                    "nextup-ring/{0}.png".format(max(0, min(NEXT_UP_RING_STEPS, step))))
            if self._next_up_focus_at and now >= self._next_up_focus_at:
                self._next_up_focus_at = 0.0
                try:
                    self.setFocusId(self.NEXT_UP_PLAY_ID)
                except RuntimeError:
                    pass
            return
        if self._next_up is None or self._next_up_dismissed or not self._duration_ms:
            return
        # `none` means the rail never appears, so the reveal is not even
        # evaluated -- and because nothing opens, nothing auto-advances.
        if self._auto_play_next_mode() == AUTO_PLAY_NEXT_NONE:
            return
        if self._position_ms() >= self._next_up_reveal_ms():
            self.show_next_up()

    def _hold_next_up(self):
        """Park the countdown for the duration of a pause.

        8.3 calls the 20,000ms a hard contract, and this window used to read
        that as "run it by wall clock whatever playback is doing" -- so
        pausing under an open rail still advanced the next episode, and you
        came back to find it already playing. The contract is about how LONG
        the countdown is, not about ignoring the one key whose entire meaning
        is "hold everything". The spec says nothing either way; this is the
        behaviour Adrian expected without having read it.

        The old worry was a timer frozen into a rail that never resolves.
        That is not reachable: a hold only exists while Kodi reports the
        stream paused, and the very next resume re-arms it."""
        if self._next_up_open and self._next_up_deadline and not self._next_up_hold:
            self._next_up_hold = max(
                0.0, self._next_up_deadline - time.monotonic())
            self._next_up_deadline = 0.0

    def _release_next_up(self):
        """Give back exactly what was left, not a fresh 20s."""
        if self._next_up_hold:
            self._next_up_deadline = time.monotonic() + self._next_up_hold
            self._next_up_hold = 0.0

    def _paused(self) -> bool:
        return self.getProperty("player_state") == self.STATE_PAUSED

    def _outro_start_ms(self):
        """Where the credits start, or None if nothing detected them.

        The LAST outro when there are several: that is the one that runs into
        the end of the file. _load_segments has already dropped anything below
        8.5's confidence floor, so whatever survives here is trusted."""
        starts = [s[1] for s in self._segments if s[0] == "outro"]
        return max(starts) if starts else None

    def rail_owns_outro(self) -> bool:
        """Is 8.3's rail going to take the outro moment for itself?

        When it is, 8.5's pill must not also offer it -- see _tick_skip. When
        it is NOT (a series finale with no next episode, or a viewer who set
        auto-play to `none`) the pill is the only thing offering to move on,
        so it stays."""
        return (self._next_up is not None
                and self._auto_play_next_mode() != AUTO_PLAY_NEXT_NONE)

    def _next_up_reveal_ms(self) -> int:
        """The position 8.3's rail opens at.

        The plain reading of the spec is "~30s before content end absent an
        outro marker, clamped <=6min from true end" -- so the 30s is the
        FALLBACK and the marker is the real answer. player.py used to take
        the fallback unconditionally, on the recorded grounds that the server
        exposed no outro marker. It does now: they arrive on the QuickView
        segments response, which is why they were not found under a name like
        /markers, and _load_segments has been reading them for 8.5 all along.

        Taking 30s when a marker existed is what put the rail and the Skip
        Credits pill seconds apart describing the same moment: an outro
        detected at 0:36 from the end raised the pill, and the rail replaced
        it at 0:30. One moment, one surface."""
        default_at = self._duration_ms - int(NEXT_UP_LEAD_S * 1000)
        outro = self._outro_start_ms()
        if outro is None:
            return default_at
        # Never LATER than the fallback: an outro detected 10s from the end
        # would otherwise delay a rail that 8.3 wants up at 30s. And never
        # more than 6 min early, which is the spec's own clamp and what keeps
        # a mis-detected marker mid-episode from opening the rail there.
        earliest = self._duration_ms - int(NEXT_UP_LEAD_MARKER_MAX_S * 1000)
        return max(earliest, min(outro, default_at))

    def refresh_progress(self):
        """Drive the fill, the scrub head and the floating preview off ONE
        position, so they can never disagree: while a scrub is pending that
        position is the target, not where the player actually is."""
        if not self._duration_ms:
            self._duration_ms = self._resolve_duration_ms()
            if not self._duration_ms:
                return
        pos_ms = self._scrub_ms if self._scrub_ms is not None else self._position_ms()
        pct = max(0.0, min(1.0, pos_ms / self._duration_ms))
        # The fill is an ordinary image resized from here, not a Kodi
        # progress control -- see the XML's own note on why. Its width never
        # drops below the capsule's own height: a 9-patch narrower than its
        # two caps renders them overlapped and mangled, and at 11px the
        # difference is the head's own width anyway.
        fill_w = max(11, int(round(pct * _TRACK_W)))
        self.setProperty("player_progress", "1" if pct > 0 else "")
        self.setProperty("player_scrub_time", _format_time(pos_ms))
        self.setProperty("player_elapsed", _format_time(pos_ms))
        self.setProperty("player_remaining",
                         "-" + _format_time(max(0, self._duration_ms - pos_ms)))
        # 8.2's buffered range. Player.ProgressCache is how far into the
        # FILE the cache reaches as a percent, so it is an absolute
        # position on the track, not an amount ahead of the head.
        try:
            cached = float(xbmc.getInfoLabel("Player.ProgressCache") or 0)
        except ValueError:
            cached = 0.0
        cached_w = int(round(max(0.0, min(100.0, cached)) / 100.0 * _TRACK_W))
        self.setProperty("player_buffered", "1" if cached_w > 11 else "")
        try:
            if cached_w > 11:
                self.getControl(self.BUFFERED_ID).setWidth(cached_w)
            self.getControl(self.FILL_ID).setWidth(fill_w)
            head_x = _TRACK_X + int(round(pct * _TRACK_W))
            # The head is CENTRED on the position, so its own width is
            # halved out; the two textures differ in width, hence two sums.
            self.getControl(self.HEAD_ID).setPosition(head_x - 2, 934)
            self.getControl(self.HEAD_DRAG_ID).setPosition(head_x - 3, 931)
            # 8.2's bubble rides the same head. Clamped to the screen so it
            # cannot hang off either end at the extremes of the track.
            bubble_x = max(20, min(head_x - _PREVIEW_TILE_W // 2,
                                   1920 - 20 - _PREVIEW_TILE_W))
            for cid in self.PREVIEW_BUBBLE_IDS:
                try:
                    self.getControl(cid).setPosition(bubble_x, _PREVIEW_TILE_Y)
                except RuntimeError as exc:
                    log.debug(f"player: preview control {cid} not placeable: {exc!r}")
            self._refresh_preview(pos_ms)
            has_tile = bool(self.getProperty("player_preview_ready"))
            if has_tile:
                try:
                    self.getControl(self.PREVIEW_SHADOW_ID).setPosition(
                        bubble_x - _PREVIEW_SHADOW_PAD,
                        _PREVIEW_TILE_Y - _PREVIEW_SHADOW_PAD)
                except RuntimeError:
                    pass
            # The readout follows the BUBBLE once there is one, not the
            # head: the bubble is clamped at the ends of the track and a
            # timecode still centred on the head would drift off it.
            centre = (bubble_x + _PREVIEW_TILE_W // 2 if has_tile else head_x)
            self._place_scrub_readout(centre, pos_ms,
                                      _PREVIEW_TIME_Y_WITH_TILE if has_tile
                                      else _PREVIEW_TIME_Y)
        except (RuntimeError, TypeError):
            # getControl raises until the XML has loaded, and again once the
            # window is being torn down. Neither is worth a stack trace.
            pass

    # ------------------------------------------------------------------
    # utility buttons
    # ------------------------------------------------------------------

    def onClick(self, controlID):
        if controlID == self.PLAYPAUSE_ID:
            self.toggle_play_pause()
        elif controlID == self.BACK10_ID:
            if self.getProperty("player_is_episode"):
                self.play_prev_episode()
            else:
                self._seek_to(self._position_ms() - SEEK_STEP_MS)
        elif controlID == self.FWD10_ID:
            if self.getProperty("player_is_episode"):
                self.play_next_up()
            else:
                self._seek_to(self._position_ms() + SEEK_STEP_MS)
        elif controlID == self.SCRUBBER_ID:
            # 10.2: select on a focused scrubber applies a pending scrub;
            # with nothing pending it acts as play/pause instead.
            if not self.commit_scrub():
                self.toggle_play_pause()
        elif controlID == self.SUBTITLES_ID:
            self._pick_stream(subtitles=True)
        elif controlID == self.AUDIO_ID:
            self._pick_stream(subtitles=False)
        elif controlID == self.STEREO_ID:
            self.open_stereo_panel()
        elif controlID == self.QUALITY_ID:
            self._pick_quality()
        elif controlID == self.ADJUST_ID:
            self.open_adjust_panel()
        elif controlID == self.STATS_ID:
            self.cycle_stats()
        elif controlID == self.ERROR_CLOSE_ID:
            self._exit()
            return
        elif controlID == self.PANEL_LIST_ID:
            self._panel_clicked()
            return
        elif controlID == self.SKIP_BUTTON_ID:
            self.take_skip()
            return
        elif controlID == self.EPISODES_ID:
            self.toggle_drawer()
            return
        elif controlID in (self.DRAWER_SEASONS_ID, self.DRAWER_EPISODES_ID):
            self._drawer_clicked(controlID)
            return
        elif controlID == self.NEXT_UP_PLAY_ID:
            self.play_next_up()
            return
        elif controlID == self.NEXT_UP_DISMISS_ID:
            self.dismiss_next_up()
            return
        self.anchor_chrome()

    def _pick_stream(self, *, subtitles: bool):
        """Live audio/subtitle switching, read straight off the running
        player rather than off the negotiation.

        Kodi's own stream lists ARE the truth once playback is up -- they
        already reflect what the container actually delivered, including a
        transcode having collapsed the audio down to the single track the
        server picked. Going back to /stream/{id}/info here would describe a
        file that is not necessarily what is playing."""
        # The list and the current index are fetched separately, each in its
        # own try: Kodi's getSubtitleStreamIndex() RAISES rather than
        # returning -1 when nothing is selected, and folding both calls into
        # one try meant a file with subtitles available but none active
        # dropped the whole panel on the floor -- a visibly focused button
        # that did nothing at all when pressed.
        try:
            if subtitles:
                names = list(self.ui_player.getAvailableSubtitleStreams())
            else:
                names = list(self.ui_player.getAvailableAudioStreams())
        except (RuntimeError, AttributeError):
            return
        current, enabled = self._current_stream(subtitles)
        if not names and not subtitles:
            # Audio with no tracks is the one case with genuinely nothing to
            # offer. Subtitles always have at least "Off", so the panel still
            # opens there -- pressing a visible button must never be a no-op,
            # which is exactly what an early return here used to be on a file
            # Kodi reports no subtitle streams for.
            log.warning("player: no audio streams to offer")
            return

        # NEITHER list alone is right for subtitles, so the panel is the
        # UNION of both. Measured on "The Hourglass Sanatorium":
        #
        #   server  11 -- 9 embedded, all render=text, plus 2 external
        #                 sidecars at synthetic indices 1000/1001
        #   Kodi    13 -- the same 9 PLUS four PGS tracks the server does not
        #                 list at all, and renders fine on a DirectPlay file
        #   transcode  Kodi reports 0: subtitles are not muxed into the HLS
        #
        # Kodi-only loses the sidecars and offers nothing on a transcode.
        # Server-only loses the four PGS tracks. So: Kodi's own streams, plus
        # every external the server knows about; and the server's WHOLE list
        # when Kodi has no native streams of its own.
        #
        # "NATIVE" is the load-bearing word. Testing `names` for emptiness was
        # wrong: the moment one external is fetched by URL, Kodi has a stream
        # and the panel concluded Kodi was covering the embedded tracks too.
        # Under a transcode that left "Off", the loaded track and the two
        # sidecars -- the nine embedded ones, all reachable by URL, silently
        # dropped. Anything WE loaded is discounted before deciding.
        #
        # Rows keep the Detail panel's wording wherever the two lists can be
        # joined. Kodi publishes `language` and `name` per stream over
        # JSON-RPC, so a Kodi stream is matched to the server's track by
        # (language, title) and takes the server's label and codec detail;
        # only a track the server never described (the PGS ones) falls back
        # to Kodi's own naming. Positional mapping cannot do this -- the two
        # lists are different lengths precisely because of those PGS tracks.
        offset = 1 if subtitles else 0
        rows = []
        picks: list = []
        selected = 0
        if not subtitles:
            for i, (label, detail) in enumerate(self._track_rows(names, subtitles)):
                rows.append((label, i == current, None, detail))
            selected = current if (current is not None and current >= 0) else 0
        else:
            rows.append(("Off", not enabled, None, ""))
            loaded = set(self._loaded_subtitle_slots.values())
            streams = self._kodi_subtitle_streams()
            native = [st for i, st in enumerate(streams) if i not in loaded]
            by_key = {self._join_key(t.get("language"), t.get("title")): t
                      for t in self._subtitle_tracks if not t.get("external")}
            if native:
                fallback = self._track_rows(names, subtitles)
                for st in native:
                    i = st.get("index")
                    match = by_key.get(self._join_key(st.get("language"), st.get("name")))
                    if match is not None:
                        label, detail = tracks.subtitle_track_label(match)
                    elif 0 <= (i or 0) < len(fallback):
                        label, detail = fallback[i]
                    else:
                        label, detail = (st.get("name") or "Subtitle", "")
                    on = enabled and i == current
                    rows.append((label, on, None, detail))
                    picks.append(("slot", i))
                    if on:
                        selected = len(rows) - 1
                extra = [t for t in self._subtitle_tracks if t.get("external")]
            else:
                extra = list(self._subtitle_tracks)
            if extra:
                labels = tracks.disambiguate(
                    [tracks.subtitle_track_label(t) for t in extra])
                for t, (label, detail) in zip(extra, labels):
                    on = enabled and t.get("index") == self._active_subtitle_index
                    rows.append((label, on, None, detail))
                    picks.append(("server", t.get("index")))
                    if on:
                        selected = len(rows) - 1
            log.debug("player: subs[panel] native=%d extra=%d -> %d rows"
                      % (len(native), len(extra), len(rows)))
            # Only now, across the finished list, so a PGS row and its text
            # twin do not both read "English . Yellow Veil".
            deduped = tracks.disambiguate([(r[0], r[3]) for r in rows[1:]])
            rows[1:] = [(lbl, rows[i + 1][1], None, det)
                        for i, (lbl, det) in enumerate(deduped)]

        def apply(idx):
            # Through the same guards as the automatic path: re-picking the
            # row that is already playing is a common thing to do in a
            # picker, and it should cost nothing.
            try:
                if subtitles:
                    if idx == 0:
                        self.ui_player.showSubtitles(False)
                        self._active_subtitle_index = None
                        return
                    kind, ref = picks[idx - 1]
                    if kind == "slot":
                        self._switch_subtitle(ref)
                        self._active_subtitle_index = None
                        self.ui_player.showSubtitles(True)
                    elif self._select_subtitle(ref):
                        self.ui_player.showSubtitles(True)
                else:
                    self._switch_audio(idx)
            except (RuntimeError, TypeError, IndexError) as exc:
                log.warning(f"player: could not switch stream: {exc!r}")

        self._open_panel(
            title="Subtitles" if subtitles else "Audio",
            glyph="\uE3A4" if subtitles else "\uE1AB",
            rows=rows,
            selected=max(0, selected),
            apply=apply,
        )

    #: The InfoLabels that describe the audio Kodi is ACTUALLY decoding.
    #: Language alone identifies the track on nearly every file; the other
    #: two only break a tie between two tracks in the same language.
    _AUDIO_LABELS = ("VideoPlayer.AudioLanguage", "VideoPlayer.AudioCodec",
                     "VideoPlayer.AudioChannels")

    def _kodi_audio_streams(self) -> list:
        """Kodi's audio streams as OBJECTS, the twin of
        _kodi_subtitle_streams.

        getAvailableAudioStreams() returns bare name strings, which cannot be
        joined to anything; JSON-RPC carries `language`, `codec` and
        `channels` per stream. Measured fresh: on a changeover this list is
        the NEW file's within ~160ms of the open, well before onAVStarted --
        it is the INDEX of the current stream that lags, not the inventory.
        """
        try:
            active = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetActivePlayers",
            }))).get("result") or []
            video = next((p for p in active if p.get("type") == "video"), None)
            if video is None:
                return []
            props = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetProperties",
                "params": {"playerid": video["playerid"],
                           "properties": ["audiostreams"]},
            }))).get("result") or {}
        except (ValueError, KeyError, TypeError) as exc:
            log.warning(f"player: could not read audio streams: {exc!r}")
            return []
        return list(props.get("audiostreams") or [])

    def _playing_audio_slot(self):
        """The slot Kodi is REALLY playing, or None when it cannot be told.

        NOT `currentaudiostream`'s index, which is the read that has now cost
        this bug twice. That index comes from
        `CApplicationPlayer::GetAudioStream()`, which is a **one-second
        cache** (ApplicationPlayer.cpp: `m_audioStreamUpdate.Set(1000ms)`).
        `CApplicationPlayer::OpenFile` expires it, but it expires it as the
        open is QUEUED -- so any reader in the window before the new audio
        stream opens re-fills it with the OUTGOING file's index, and that
        answer then stands for a full second into the new episode.

        On the cinema box there is such a reader: two clients sit on Kodi's
        JSON-RPC port polling the player. That is also why neither local Kodi
        nor the AM6B+ ever reproduced this -- nothing was polling them.

        Reproduced deliberately, 2026-08-19, on local Kodi with two plain
        mkvs (ger default, eng second) and a 40ms poller, no add-on involved:

            t      currentaudiostream   VideoPlayer.AudioLanguage   file
            +0.30s index 1 ("eng")      ger                         epB
            +1.00s index 1 ("eng")      ger                         epB
            +1.08s index 0 ("ger")      ger                         epB

        With the poller off, the same read is right from +0.30s. The file
        identity is fresh throughout, which is why PR #68's
        `_showing_current_item()` could not catch it: `Player.GetItem` is not
        behind that cache, so it said "yes, the new episode" while the index
        still described the old one.

        So the current track is resolved from the two surfaces that told the
        truth in every sample: the stream INVENTORY, and the InfoLabels for
        what is being decoded. Ambiguity answers None, and the caller then
        switches -- the behaviour from before the shortcut existed.
        """
        streams = self._kodi_audio_streams()
        if not streams:
            return None
        language = (xbmc.getInfoLabel(self._AUDIO_LABELS[0]) or "").strip().lower()
        if not language:
            return None
        matches = [s for s in streams
                   if str(s.get("language") or "").strip().lower() == language]
        if len(matches) > 1:
            # Two tracks in one language -- a commentary, or a second mix.
            codec = (xbmc.getInfoLabel(self._AUDIO_LABELS[1]) or "").strip().lower()
            channels = (xbmc.getInfoLabel(self._AUDIO_LABELS[2]) or "").strip()
            matches = [s for s in matches
                       if str(s.get("codec") or "").strip().lower() == codec
                       and str(s.get("channels") or "") == channels]
        if len(matches) != 1:
            return None
        slot = matches[0].get("index")
        return slot if isinstance(slot, int) else None

    def _playing_subtitle_slot(self):
        """_playing_audio_slot for subtitles: same cache, same lie.

        `CApplicationPlayer::GetSubtitle()` carries the identical 1000ms
        cache (`m_subtitleStreamUpdate`), so `currentsubtitle`'s index is
        just as stale on a changeover. `subtitleenabled` is NOT cached, so
        the caller still reads that from JSON-RPC.

        Subtitle tracks share a language far more often than audio ones
        (full, forced and SDH are all `eng`) and no InfoLabel distinguishes
        them, so this answers None more often than its audio twin. That
        costs a needless setSubtitleStream, which is cheap -- unlike an
        audio switch it does not reconfigure the renderer.
        """
        streams = self._kodi_subtitle_streams()
        if not streams:
            return None
        language = (xbmc.getInfoLabel("VideoPlayer.SubtitlesLanguage") or "").strip().lower()
        if not language:
            return None
        matches = [s for s in streams
                   if str(s.get("language") or "").strip().lower() == language]
        if len(matches) != 1:
            return None
        slot = matches[0].get("index")
        return slot if isinstance(slot, int) else None

    def _arm_audio_confirmation(self, slot: int) -> None:
        """Remember the slot just asked for, and when to check it landed."""
        self._audio_confirm_slot = slot
        self._audio_confirm_at = time.monotonic() + _AUDIO_CONFIRM_S

    def _confirm_audio_slot(self, now: float) -> None:
        """Belt and braces: a beat after the switch, did the audio LAND?

        Two fixes for this bug have shipped on the strength of a read that
        was believed fresh, and both were wrong about a different surface. So
        the outcome is now checked once per item, _AUDIO_CONFIRM_S after the
        choice was applied -- by which time every cache Kodi holds has
        expired -- and corrected if the wrong LANGUAGE is playing.

        Only on the language, and only once. A different track in the same
        language is a tie this cannot break and must not fight over, and a
        viewer who changes the track by hand during those two seconds keeps
        their choice because the panel arms this with the slot THEY asked
        for.
        """
        if not self._audio_confirm_at or now < self._audio_confirm_at:
            return
        self._audio_confirm_at = 0.0
        wanted = self._audio_confirm_slot
        if wanted is None:
            return
        try:
            playing = self._playing_audio_slot()
            if playing is None or playing == wanted:
                return
            by_slot = {s.get("index"): s for s in self._kodi_audio_streams()}
            want_lang = str((by_slot.get(wanted) or {}).get("language") or "").lower()
            got_lang = str((by_slot.get(playing) or {}).get("language") or "").lower()
            if not want_lang or want_lang == got_lang:
                return
            log.info("player: audio landed on slot %s (%s), correcting to "
                     "slot %s (%s)" % (playing, got_lang, wanted, want_lang))
            self.ui_player.setAudioStream(wanted)
        except (RuntimeError, AttributeError, TypeError) as exc:
            log.warning(f"player: could not confirm the audio track: {exc!r}")

    def _current_stream(self, subtitles: bool) -> tuple:
        """(index of the active track, is it on) from JSON-RPC.

        Not from the Player object: Kodi's Python Player has NO
        getAudioStreamIndex or getSubtitleStreamIndex -- the methods simply
        do not exist, so the old calls raised AttributeError every time and
        were swallowed. The effect was silent: no row ever carried the
        "currently playing" check, and subtitles always claimed to be Off.

        JSON-RPC is the only place Kodi publishes this."""
        wanted = (["currentsubtitle", "subtitleenabled"] if subtitles
                  else ["currentaudiostream"])
        try:
            active = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetActivePlayers",
            }))).get("result") or []
            video = next((p for p in active if p.get("type") == "video"), None)
            if video is None:
                return None, not subtitles
            props = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetProperties",
                "params": {"playerid": video["playerid"], "properties": wanted},
            }))).get("result") or {}
        except (ValueError, KeyError, TypeError) as exc:
            log.warning(f"player: could not read the active stream: {exc!r}")
            return None, not subtitles
        if subtitles:
            index = (props.get("currentsubtitle") or {}).get("index")
            return index, bool(props.get("subtitleenabled")) and index is not None
        return (props.get("currentaudiostream") or {}).get("index"), True

    def _kodi_subtitle_streams(self) -> list:
        """Kodi's subtitle streams as OBJECTS, not the bare name strings
        getAvailableSubtitleStreams() returns.

        JSON-RPC carries `language` and `name` per stream; the Player API
        carries neither. That is what lets a Kodi stream be joined to the
        server's description of the same track, and so lets a row keep the
        language and codec the Options panel on Detail shows."""
        try:
            active = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetActivePlayers",
            }))).get("result") or []
            video = next((p for p in active if p.get("type") == "video"), None)
            if video is None:
                return []
            props = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetProperties",
                "params": {"playerid": video["playerid"],
                           "properties": ["subtitles"]},
            }))).get("result") or {}
        except (ValueError, KeyError, TypeError) as exc:
            log.warning(f"player: could not read subtitle streams: {exc!r}")
            return []
        return list(props.get("subtitles") or [])

    @staticmethod
    def _join_key(language, title) -> tuple:
        return ((language or "").strip().lower(),
                (title or "").strip().lower())

    def _track_rows(self, names: list, subtitles: bool) -> list:
        """[(label, detail)] for the track picker, preferring the SERVER's
        description of each track over Kodi's.

        The server's dicts are what tracks.py's helpers were written for, so
        going through them makes an in-player row read exactly like the
        pre-play Options panel's: "English | DTS-HD MA 7.1" rather than a
        bare "eng". Kodi's own stream list only ever carries a language tag.

        Use the server's rows only when it described the same NUMBER of
        tracks Kodi found: positional mapping is the only thing tying the two
        lists together, so a length mismatch makes every row a guess.

        The fallback is a real path, not defensive padding, but it is rarer
        than this docstring used to claim. It said the server reports
        `subtitle_tracks: []` on Hugo while the container carries three. It
        does not: measured on 0.9.29, Hugo answers with all three PGS tracks.
        The `[]` came from probing the endpoint WITHOUT the capability
        profile -- absent `client_render_bitmap_subtitles` means false, and
        the server then correctly routes PGS to `burn_in_subtitle_tracks`
        instead. We send it true (profile.py), so bitmap subtitles arrive in
        the list proper. See issue #7 for the full measurement.

        What can still make the counts disagree: subtitle codecs the server
        drops from BOTH of its lists -- teletext and EIA-608, acknowledged by
        tofa 2026-08-12 and still open -- and any external/sidecar track Kodi
        knows about that the negotiation did not describe."""
        server = self._subtitle_tracks if subtitles else self._audio_tracks
        if server and len(server) == len(names):
            label_of = tracks.subtitle_track_label if subtitles else tracks.audio_track_label
            return tracks.disambiguate([label_of(t) for t in server])
        if server:
            log.warning(
                f"player: server described {len(server)} "
                f"{'subtitle' if subtitles else 'audio'} tracks but Kodi found "
                f"{len(names)}; falling back to Kodi's own names")
        return [(_stream_label(name, i), "") for i, name in enumerate(names)]

    def _pick_quality(self):
        """Quality is the SERVER's decision, so unlike audio/subtitles it
        cannot be applied to the running stream -- it needs a fresh
        negotiation. The stream is therefore torn down and restarted at the
        position it was at, which is the only honest way to offer the
        control mid-playback."""
        if not (self.client and self.file_id):
            return
        try:
            info = self.client.stream_info(
                self.file_id,
                CapabilityProfile.for_device(
                    max_bitrate=self.selection.max_bitrate,
                    quality_mode=self.selection.quality_mode),
                dry_run=True,
            )
        except http.ApiError as exc:
            log.warning(f"player: stream info for quality failed: {exc!r}")
            return
        section = next((s for s in playoptions.build_sections(info, self.selection)
                        if s["key"] == playoptions.QUALITY), None)
        if not section:
            return
        options, current = section["options"], section["selected"]
        rows = [(o["label"], i == current, None, o.get("detail") or "")
                for i, o in enumerate(options)]

        def apply(idx):
            if idx == current:
                return
            option = options[idx]
            # Same mapping playoptions' own commit uses: Original means
            # "send no ceiling at all", not "send the original's own
            # bitrate".
            self.selection.quality_tag = None if option["is_original"] else option["tag"]
            self.selection.max_bitrate = (
                None if option["is_original"] else option["bitrate_kbps"])
            # A DELIBERATE Original is not the same as never having been
            # asked, even though both send no ceiling. Same line as the
            # pre-play panel's, so mid-playback and pre-play agree.
            self.selection.quality_mode = "original" if option["is_original"] else None
            self.resume_ms = self._position_ms()
            self._restarting = True
            try:
                self.ui_player.stop()
            except RuntimeError:
                pass
            self.setProperty("player_state", self.STATE_OPENING)
            self._start_playback()

        self._open_panel(title="Quality", glyph="\uE29A", rows=rows,
                         selected=max(0, current), apply=apply)

    # ------------------------------------------------------------------
    # 8.11 stats
    # ------------------------------------------------------------------

    def set_stats_mode(self, mode: str):
        """off -> pill -> panel, the three states 8.11 defines.

        The utility button's "on" tint follows either readout being up, so
        the button reads as engaged in both -- it is one control with three
        positions, not two independent toggles."""
        self._stats_mode = mode
        self.setProperty("player_stats", mode)
        self.setProperty(f"player_util_{self.STATS_ID}", "on" if mode else "")
        if mode:
            # 8.8's pause card and a stats readout would occupy the same
            # screen at the same time, and the card is the dispensable one:
            # a viewer who opened the stats is looking at them.
            self.hide_pause_card()
            self._refresh_stats()
        self._stats_next_refresh = 0.0

    def cycle_stats(self):
        index = playerstats.CYCLE.index(self._stats_mode) if self._stats_mode in playerstats.CYCLE else 0
        self.set_stats_mode(playerstats.CYCLE[(index + 1) % len(playerstats.CYCLE)])

    #: What a `stats` notification asked for, waiting to be applied by the
    #: tick. See _StatsNotifyMonitor for why it is parked rather than applied
    #: where it arrives.
    _stats_request: Optional[str] = None

    def request_stats_mode(self, mode: str):
        """Queue a stats mode for the next tick. Safe to call OFF-THREAD.

        Kodi delivers notifications on its own thread, and everything
        set_stats_mode reaches from there is GUI work -- window properties,
        and a ManagedControlList rebuild for the panel. Doing that from a
        second thread is the shape of bug that shows up as a wrong-looking
        list once a week and never reproduces (see
        reference_kodi_listitem_guilock, project_kodi_addlistitems_focus_race).
        So the notification only parks a string, and the 200ms tick -- which
        already owns every other timed change to this window -- applies it.

        A repeat inside one tick is not a double-fire, it is the last one
        winning, which is what a viewer holding a remote button means.
        """
        self._stats_request = mode

    def _apply_stats_request(self):
        """Consume a parked stats request, on the UI thread."""
        mode, self._stats_request = self._stats_request, None
        if mode is None:
            return
        if mode == STATS_CYCLE:
            self.cycle_stats()
        elif mode in playerstats.CYCLE:
            self.set_stats_mode(mode)
        else:
            log.warning(f"player: ignoring unknown stats mode {mode!r}")

    # A debounce used to live here, because ONE info press reached the cycle
    # by two routes at once on the box -- our onAction branch for
    # ACTION_PLAYER_PROCESS_INFO, and the tick noticing Kodi's own dialog for
    # the same press -- and every press advanced two steps, off -> pill ->
    # panel, leaving the pill unreachable from off.
    #
    # Both routes are gone with the key itself, so the double-fire cannot
    # happen and the debounce would only mask a real one. The stats button
    # and the digit keys each reach cycle_stats/set_stats_mode exactly once.
    # If a JSON-RPC route is added later, check whether it can race the
    # button before assuming it needs no guard.

    def _stats_list(self):
        """The panel's single row list, built once and then filled in place.

        One list, not two: a row now carries the SAME fact twice (as sent, as
        played) and the pair only reads as a pair if both halves sit on one
        line. Two lists put unrelated facts side by side."""
        if self._stats_rows is None:
            self._stats_rows = kodigui.ManagedControlList(
                self, self.STATS_ROWS_ID, 24)
        return self._stats_rows

    @staticmethod
    def _with_spacers(rows):
        """A blank slot above every section heading except the first.

        Kodi cannot vary itemheight per item, so a heading cannot simply be
        given more room above it -- the breathing space has to be a row of
        its own. Done here rather than in playerstats so the model stays a
        description of the readings and the pruning rules do not have to
        learn about a row that carries nothing.

        `(None, None)` rather than `("", None)`: it is a heading as far as
        every consumer is concerned, and the None says the blankness is
        deliberate rather than a title that failed to arrive."""
        out = []
        for entry in rows:
            if len(entry) == 2 and out:
                out.append((None, None))
            out.append(entry)
        return out

    @staticmethod
    def _stats_items(rows):
        items = []
        for entry in rows:
            if len(entry) == 2:
                item = kodigui.ManagedListItem(entry[0] or "")
                item.setProperty("header", "1")
            else:
                key, source, output, _kind, warn = entry
                item = kodigui.ManagedListItem(key)
                item.setLabel2(source)
                item.setProperty("header", "")
                item.setProperty("out", output)
                # Drives the arrow and the output cell's colour in the skin.
                # A property rather than inline [COLOR] markup so the two
                # cells can be tinted together without wrapping either.
                item.setProperty("warn", "1" if warn else "")
                item.setProperty("paired", _paired(source, output))
            items.append(item)
        return items

    def _fill_stats_panel(self, position: str):
        """Repaint the panel's rows.

        Rebuilt only when the SHAPE changes -- how many rows exist and what
        they are called. That set is fixed for a given file on a given box,
        so in practice it is built once per playback and then every refresh
        just writes new values into the items that are already there.

        In place because a rebuild every STATS_REFRESH_S would flicker, and
        because setting a ListItem property is what invalidates a list item's
        cached layout (main.py says the same of the Browse pills). CPU,
        memory, buffer and position all move; nothing else does."""
        rows = self._with_spacers(
            playerstats.rows(self._nego, self.selection, position))
        mcl = self._stats_list()
        shape = tuple(e[0] for e in rows)
        if shape != self._stats_shape:
            self._stats_shape = shape
            mcl.reset()
            mcl.addItems(self._stats_items(rows))
            return
        for item, entry in zip(mcl, rows):
            if len(entry) != 2:
                item.setLabel2(entry[1])
                item.setProperty("out", entry[2])
                item.setProperty("warn", "1" if entry[4] else "")
                item.setProperty("paired", _paired(entry[1], entry[2]))

    def _refresh_stats(self):
        position = f"{_format_time(self._position_ms())} / {_format_time(self._duration_ms)}"
        self._fill_stats_panel(position)
        props = playerstats.build(self._nego, self.selection, position)
        props["stats_heading"] = "PLAYBACK STATS"
        # No verdict word. The reference app puts one top-right, but ours
        # could only ever restate the delivery decision -- Kodi reports no
        # drop or jitter counters, so it never described playback health --
        # and the Method row now says the same thing in the same words, with
        # the decision mode beside it. Two labels for one fact.
        for key, value in props.items():
            self.setProperty(key, value)
        if self._stats_mode == playerstats.PILL:
            self._size_stats_pill(props.get("stats_pill", ""))

    def _size_stats_pill(self, text: str):
        """Fit the capsule to its own text, centred on x=960.

        Kodi strips [COLOR] markup before drawing, so the markup must come
        out before counting characters or every tinted run would widen the
        pill by the length of its own tag."""
        plain = re.sub(r"\[/?COLOR[^\]]*\]", "", text)
        width = int(round(len(plain) * _STATS_CHAR_W)) + 2 * _STATS_PAD_X
        width = max(_STATS_MIN_W, min(width, _STATS_MAX_W))
        left = _STATS_CENTRE_X - width // 2
        try:
            for control_id in (self.STATS_PILL_BG_ID, self.STATS_PILL_OUTLINE_ID,
                               self.STATS_PILL_LABEL_ID):
                control = self.getControl(control_id)
                control.setWidth(width)
                control.setPosition(left, 44)
        except (RuntimeError, TypeError):
            # Same reason refresh_progress swallows these: getControl raises
            # before the XML has loaded and again during teardown.
            pass

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------

    # 10.4: up/down and any other key reveal the chrome. Deliberately a
    # denylist-by-omission rather than "everything not handled above":
    # ACTION_MOUSE_MOVE fires from a stray pointer and must not count, and
    # neither should a volume key.
    _REVEAL_ACTIONS = _actions(
        "ACTION_MOVE_UP", "ACTION_MOVE_DOWN",
        "ACTION_MOVE_LEFT", "ACTION_MOVE_RIGHT",
        "ACTION_SHOW_INFO", "ACTION_SHOW_OSD", "ACTION_SHOW_GUI",
        "ACTION_PAGE_UP", "ACTION_PAGE_DOWN", "ACTION_CONTEXT_MENU",
    )
    _PLAY_PAUSE_ACTIONS = _actions(
        "ACTION_PLAYER_PLAY", "ACTION_PAUSE", "ACTION_PLAYER_PLAYPAUSE")
    _SELECT_ACTIONS = _actions("ACTION_SELECT_ITEM", "ACTION_MOUSE_LEFT_CLICK")
    _BACK_ACTIONS = _actions("ACTION_NAV_BACK", "ACTION_PREVIOUS_MENU")
    _STOP_ACTIONS = _actions("ACTION_STOP")
    # The transport keys a CEC remote, a keyboard or a phone app actually
    # sends. 10.3 asks for FF/RW to be served as registered 10s skips rather
    # than as raw key handling, and Kodi's media-session equivalent is these
    # actions -- so they land on the same +/-10s the on-screen buttons use
    # instead of engine fast-forward, which this player has no UI for.
    _SEEK_FWD_ACTIONS = _actions(
        "ACTION_PLAYER_FORWARD", "ACTION_STEP_FORWARD", "ACTION_BIG_STEP_FORWARD")
    _SEEK_BACK_ACTIONS = _actions(
        "ACTION_PLAYER_REWIND", "ACTION_STEP_BACK", "ACTION_BIG_STEP_BACK")
    # Kodi's own chapter keys (",' and '.' on a keyboard, the chapter buttons
    # on a remote). Handled here rather than passed through because OUR
    # chapters come from QuickView, which the server knows for a transcode
    # too -- Kodi's demuxer only knows them on a direct play, so passing
    # through would make the same key work on some titles and not others.
    _CHAPTER_FWD_ACTIONS = _actions(
        "ACTION_CHAPTER_OR_BIG_STEP_FORWARD", "ACTION_NEXT_SCENE")
    _CHAPTER_BACK_ACTIONS = _actions(
        "ACTION_CHAPTER_OR_BIG_STEP_BACK", "ACTION_PREV_SCENE")
    _NEXT_ITEM_ACTIONS = _actions("ACTION_NEXT_ITEM")
    _PREV_ITEM_ACTIONS = _actions("ACTION_PREV_ITEM")

    # ACTION_PLAYER_PROCESS_INFO is deliberately NOT listed here; see the
    # block where _adopt_process_info used to live. The key belongs to Kodi.
    #
    # Digit keys select a stats mode directly. Two ids per key because the
    # same digit arrives as REMOTE_<n> through the keyboard keymap and as
    # ACTION_JUMP_SMS<n> through a remote's; the SMS ids are named for the
    # key they sit on (SMS2 is the "2" key), and there is no SMS1.
    _STATS_DIGIT_ACTIONS = {
        **{aid: playerstats.PILL for aid in _actions("REMOTE_1")},
        **{aid: playerstats.PANEL for aid in _actions("REMOTE_2", "ACTION_JUMP_SMS2")},
        **{aid: playerstats.OFF for aid in _actions("REMOTE_3", "ACTION_JUMP_SMS3")},
    }

    def onAction(self, action):
        aid = action.getId()
        chrome_up = bool(self._chrome_deadline)

        # Media keys are handled the same either way and always re-anchor.
        if aid in self._PLAY_PAUSE_ACTIONS:
            self.toggle_play_pause()
            self.reveal_chrome()
            return

        # A stepper panel owns the arrows outright, in EITHER chrome state.
        # Placed this high on purpose: further down, left/right mean seek on
        # the bare surface and belong to the focus engine with the chrome up,
        # and a focused stepper row must not be able to fall through to
        # either. Dedicated media keys below still work, which is what a
        # viewer nudging sync against a running film actually wants.
        if (self._panel_steppers is not None
                and aid in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT)
                and self.nudge_stepper(aid == xbmcgui.ACTION_MOVE_RIGHT)):
            return

        # Transport keys work in either chrome state, and reveal the chrome
        # so the seek is visible -- pressing skip on a remote and seeing
        # nothing move would read as a dead button.
        if aid in self._SEEK_FWD_ACTIONS or aid in self._SEEK_BACK_ACTIONS:
            self.quick_seek(aid in self._SEEK_FWD_ACTIONS)
            self.reveal_chrome()
            return

        if aid in self._CHAPTER_FWD_ACTIONS or aid in self._CHAPTER_BACK_ACTIONS:
            self.chapter_seek(aid in self._CHAPTER_FWD_ACTIONS)
            self.reveal_chrome()
            return

        # Kodi's next/previous ITEM keys (a remote's skip-track buttons).
        # plex-for-kodi points them at its play queue; ours has none, so
        # they mean the same thing the transport's own outer pair does on an
        # episode, and nothing at all on a movie -- rather than silently
        # falling through to something unrelated.
        if aid in self._NEXT_ITEM_ACTIONS or aid in self._PREV_ITEM_ACTIONS:
            if self.getProperty("player_is_episode"):
                if aid in self._NEXT_ITEM_ACTIONS:
                    self.play_next_up()
                else:
                    self.play_prev_episode()
            return

        # Stats work in either chrome state and deliberately do NOT reveal the
        # chrome: the readout is meant to be watched against moving video, and
        # popping the transport up over it would hide the bottom of the panel.
        if aid in self._STATS_DIGIT_ACTIONS:
            self.set_stats_mode(self._STATS_DIGIT_ACTIONS[aid])
            self.anchor_chrome()
            return

        if aid in self._BACK_ACTIONS:
            self._on_back()
            return

        if aid in self._STOP_ACTIONS:
            self._exit()
            return

        if self.getFocusId() == self.SKIP_BUTTON_ID:
            # 8.5's pill is an ordinary button once focused, so the focus
            # engine owns SELECT, not 10.2's play/pause.
            #
            # It does NOT own the arrows, though, because the pill carries no
            # <onup>/<ondown>/<onleft>/<onright> in the XML: handing the
            # d-pad to the focus engine here left the viewer stranded on it
            # with no way back, which is the other half of "impossible to
            # hit". Any direction leaves, landing wherever makes sense for
            # the state the chrome is in.
            if aid in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN,
                       xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                self.setFocusId(self.PLAYPAUSE_ID if chrome_up else self.SURFACE_ID)
                if chrome_up:
                    self.anchor_chrome()
                return
            kodigui.ControlledDialog.onAction(self, action)
            return
        if self.getProperty("player_episodes"):
            # Same reason as the rail below: the drawer's lists are real
            # focusable controls, so the focus engine has to own the d-pad
            # rather than the chrome-down branch turning left/right into a
            # seek under an open panel.
            kodigui.ControlledDialog.onAction(self, action)
            return
        if self._next_up_open or self.getFocusId() in (self.NEXT_UP_PLAY_ID,
                                                       self.NEXT_UP_DISMISS_ID):
            # 8.3's rail owns the d-pad while it is up. Its two buttons are
            # real focusable controls, so left/right have to move between
            # them rather than seek, and select has to press one rather than
            # toggle playback -- neither of which the chrome-down branch
            # below would do.
            #
            # ...and it keeps owning them for as long as FOCUS is still on
            # one of its buttons, which outlasts _next_up_open by design.
            # Both of those buttons clear the flag in their own click
            # handler, and Kodi then delivers the SAME press a second time
            # here, on the app thread -- measured ~285ms later. Testing only
            # the flag let that second dispatch fall through to the
            # chrome-down branch below, where select is toggle_play_pause:
            # Play Next started the next episode and instantly paused it,
            # and Dismiss paused the episode still playing. The focus test
            # is what the Skip pill above already does, for the same reason;
            # _defer_focus_restore is what holds focus here long enough for
            # it to work.
            kodigui.ControlledDialog.onAction(self, action)
            return

        if not chrome_up:
            # 10.4: left/right seek, EVERYTHING else reveals. Select is the
            # documented exception -- on the bare surface it toggles
            # play/pause (10.2) rather than bringing the chrome up.
            if aid == xbmcgui.ACTION_MOVE_LEFT:
                self.quick_seek(False)
            elif aid == xbmcgui.ACTION_MOVE_RIGHT:
                self.quick_seek(True)
            elif aid in self._SELECT_ACTIONS:
                self.toggle_play_pause()
                self.reveal_chrome()
            elif aid == xbmcgui.ACTION_MOVE_DOWN and self.getProperty("player_skip"):
                # Down goes TO the pill rather than revealing the chrome,
                # which is the only way to reach it while the chrome is
                # hidden -- and the state 8.5 expects it to be used in.
                self.setFocusId(self.SKIP_BUTTON_ID)
            elif aid in self._REVEAL_ACTIONS:
                self.reveal_chrome()
            return

        # Chrome up: the focus engine owns the d-pad, except on the
        # scrubber, where left/right belong to the scrub (10.4).
        if aid in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
            if self.getFocusId() == self.SCRUBBER_ID:
                self.scrub(aid == xbmcgui.ACTION_MOVE_RIGHT)
                return
        # UP reaches the pill while the chrome is up. The pill sits ABOVE the
        # transport (the group slides to -106 on player_chrome), but nothing
        # in the chrome carries an <onup> to it, so the focus engine could
        # not get there and revealing the controls made the pill unreachable
        # -- it stayed on screen and stopped being usable, which is the
        # combination that was reported.
        #
        # Deliberately NOT excluding the scrubber, though that looks like the
        # careful thing to do. Raising the chrome from the bare surface lands
        # focus on the SCRUBBER, not the transport, so excluding it excluded
        # the one case this exists for -- measured, after the first attempt
        # did exactly that. The scrubber's left/right belong to the scrub and
        # are handled above; its UP was doing nothing.
        if aid == xbmcgui.ACTION_MOVE_UP and self.getProperty("player_skip"):
            self.setFocusId(self.SKIP_BUTTON_ID)
            self.anchor_chrome()
            return
        self.anchor_chrome()
        kodigui.ControlledDialog.onAction(self, action)

    def _on_back(self):
        """10.1's player ladder, top priority first. Each press reduces
        exactly one thing; only the last rung exits.

        Rungs this window does not have yet (skip pill, end-of-series
        rail) slot in above the chrome rung when they land."""
        if self.getProperty("player_error"):
            # 8.7's card is terminal: there is nothing to reduce to, so back
            # means the same as its own Close.
            self._exit()
            return
        if self.getProperty("player_panel"):
            # 8.4's panel owns the screen and the focus while it is up.
            self.close_panel()
            return
        if self.getProperty("player_skip"):
            # Back declines the offer. Above the chrome rung for the same
            # reason the stats panel is: a viewer who just saw a pill appear
            # and pressed back means "not that".
            self._hide_skip(used=True)
            return
        if self.getProperty("player_episodes"):
            # 8.10's drawer owns the screen and the focus while it is up, so
            # back closes it and nothing else.
            self.close_drawer()
            return
        if self._next_up_open:
            # 8.3: back under an open rail dismisses it, and only it. Above
            # even the scrub rung because the rail owns the screen and the
            # focus while it is up.
            self.dismiss_next_up()
            return
        if self.cancel_scrub():
            # A pending scrub is cancelled AND the chrome goes, in one press.
            self.hide_chrome()
            return
        if self._stats_mode:
            # Above the chrome rung: a viewer with the panel up who presses
            # back means "close this", and dropping the chrome underneath it
            # first would look like the press did nothing.
            self.set_stats_mode(playerstats.OFF)
            return
        if self._chrome_deadline:
            self.hide_chrome()
            return
        # Stamp the unwind clock before closing, exactly as
        # ControlledWindow.onAction does for the windows whose Back it
        # handles itself. Without it MainWindow's held-Back guard never
        # arms, and the tail of the SAME press -- the player takes ~700ms
        # to hand back, which is long enough for a remote's auto-repeat to
        # outlive it -- reaches Home as a fresh Back and walks straight out
        # of the add-on.
        kodigui.note_back_close()
        self._exit()

    def _exit(self):
        # Leaving the player ON PURPOSE. Flagged so onClosed does not stash a
        # resume context: Back means "I am done with this", and coming back
        # into the add-on should not drop the viewer into a film they just
        # walked out of.
        self._stopping = True
        # Explicit stop before close -- don't rely solely on the async
        # onPlayBackStopped callback for this window's own exit path.
        if self.ui_player and self.ui_player.isPlaying():
            self.ui_player.stop()
        self.closeNow()

    #: The player's own Kodi window id, so a later launch can bring THIS
    #: window back rather than building another one.
    WINDOW_ID_PROPERTY = "tofa.player_winid"

    def _remember_window_id(self):
        try:
            if self._winID:
                xbmcgui.Window(10000).setProperty(
                    self.WINDOW_ID_PROPERTY, str(self._winID))
        except Exception:
            pass

    @classmethod
    def reactivate_if_backgrounded(cls) -> bool:
        """Bring a still-live player back to the front. True if it did.

        Kodi's Home button does NOT close this window: it activates another
        one on top. Our Python stays parked in its modal wait, the window
        keeps every bit of its state, and `player_open` is still set --
        onClosed never ran. Verified directly: after Home the property reads
        "1" and the stream is still playing.

        So returning to playback is not a re-attach problem at all. There is
        nothing to rebuild and no session to renegotiate; the window just has
        to be raised again. An earlier version of this stashed the whole
        negotiation response to reconstruct a second window, which would have
        opened a duplicate server session to recreate state that had never
        been lost.

        Both conditions are required. `player_open` alone could be a window
        left over from playback that has since ended, and raising that shows
        a player bound to a finished stream.
        """
        window = xbmcgui.Window(10000)
        if not window.getProperty(_REENTRANCY_PROPERTY):
            return False
        win_id = window.getProperty(cls.WINDOW_ID_PROPERTY)
        if not win_id:
            return False
        try:
            if not xbmc.Player().isPlaying():
                return False
        except Exception:
            return False
        log.debug("player: re-activating backgrounded window {0}".format(win_id))
        xbmc.executebuiltin("ActivateWindow({0})".format(win_id))
        return True

    def onClosed(self):
        # Give the viewer their stereoscopic setting back before anything
        # else here can throw.
        stereoscopic.restore()
        # Dropped explicitly rather than left to the weakref: the tick that
        # would apply a late request is about to stop, so a notification
        # arriving now would park a mode nothing consumes.
        self._stats_monitor = None
        self._stats_request = None
        self._stop_tick.set()
        # The tile loader waits on its own event, so setting the stop flag
        # is not enough to get it out of that wait promptly.
        self._tile_wake.set()
        # Nothing to undo for the display: the refresh-rate switch is Kodi's
        # own (see match_refresh_rate), so Kodi reverts it when playback
        # stops, and respects "on start" by not reverting at all. Measured on
        # the box -- the mode goes back on stop even from outside fullscreen
        # video. Restoring it here as well would fight Kodi for it.
        xbmcgui.Window(10000).clearProperty(_REENTRANCY_PROPERTY)
        # ...and the offset published for monitor.py, or the next thing
        # played through the plain directory route would have this stream's
        # offset added to its positions.
        monitor.publish_time_offset(0)
        # LET GO OF THE PLAYER. An xbmc.Player subclass keeps receiving
        # callbacks for as long as it is alive -- Kodi does not know or care
        # that the window that made it has closed. Dropping our reference is
        # what unregisters it.
        #
        # Without this they pile up, and every one of them answers
        # onAVStarted for playbacks it has nothing to do with, running
        # apply_track_selection() against ITS OWN long-dead _nego. Measured
        # on local Kodi 2026-08-08 by counting the handlers that ran for a
        # single playback: 1, then 2, then 4 across successive plays.
        #
        # This is the stale-subtitle 410 from the box. An episode was watched
        # to the end, the Next Up rail ran out without advancing
        # (auto_play_next=ask), and the next episode was started from Detail
        # -- so the finished episode's window answered the new episode's
        # onAVStarted and asked the server for a subtitle belonging to the
        # session it had already ended. Hence a `.vtt` URL carrying the
        # PREVIOUS session id and media id, a 410, `Unable to create subtitle
        # parser`, and Kodi holding one more subtitle stream than the server
        # had described.
        #
        # Only the natural end leaked: stopping with Back tore the window
        # down in a way that let it be collected, which is why this went
        # unnoticed for so long and why it takes finishing an episode to see.
        self.ui_player = None
