"""xbmc.Player subclass -> progress reporting.

Runs inside service.py, the only component of this add-on whose process
survives between playback events -- addon.py exits right after
setResolvedUrl, so it hands off the session via a Window(10000) property;
this module reads it once and clears it immediately (one-shot), so a video
played elsewhere in Kodi is never mistaken for a tofa session.

`position_ticks` on the session-scoped PROGRESS endpoint is milliseconds.
That is not directly documented, and the inference that used to be recorded
here -- "resume_ticks/start_position_ticks echo 1:1 with ms values sent
elsewhere" -- was WRONG and cost us a long detour: those echoed 1:1 because
the server faithfully returns whatever you send it, and what we were sending
was the wrong unit. Everything on the STREAM endpoints (resume_ticks,
start_position_ticks, /seek's position_ticks) is 100-nanosecond ticks; see
playback.TICKS_PER_MS. This endpoint really does take milliseconds, which is
why the two sit side by side in _report.

Every heartbeat reports to both progress mechanisms: the session-scoped
endpoint (concurrent-stream bookkeeping) and /media/{file_id}/progress,
which is what actually persists the resume point -- the session endpoint
alone does NOT update it.
"""
from __future__ import annotations

import json
import time
from typing import Optional

import xbmc
import xbmcgui

from . import addonref, api, auth, http, log, telemetry, toast
from .api import MediaServerClient

HANDOFF_PROPERTY = "plugin.video.tofa.pending_session"

# How long onAVStarted may take after addon.py hands off a resolved URL,
# and how long the position may fail to advance before we give up --
# distinct "opening timeout" vs. "stalled" states (matching tofa's Android
# app) instead of one generic retry message.
OPENING_TIMEOUT_SECONDS = 25.0
STALL_TIMEOUT_SECONDS = 30.0
STALL_EPSILON_MS = 500  # clock/reporting jitter tolerance, not real progress

# The heartbeat's own HTTP budget, deliberately far below http.py's 15s
# default. _report() runs INLINE in service.py's loop, which is `tick();
# waitForAbort(TICK_SECONDS)` -- so every second a progress call blocks is a
# second the whole loop is late, including the stall check.
#
# Measured against a real outage (2026-08-08, box log): with the 15s default,
# a dead server cost 15s on the primary base_url plus an instant refusal on
# the fallback, twice per tick (session + media), making ticks 40s apart
# instead of 10s. A heartbeat is fire-and-forget -- the next tick carries the
# position anyway -- so it gets a short budget and no second chance.
PROGRESS_TIMEOUT_SECONDS = 5.0

# How far back a single heartbeat may move the resume point without being
# asked to prove it. Well beyond any real drift between two ~10s reads, and
# an ordinary rewind clears the baseline via onPlayBackSeek long before it
# reaches here. See _regression_unconfirmed.
POSITION_REGRESSION_MS = 60_000

#: Telemetry cadence, in ticks of service.py's ~10s loop: a heartbeat every
#: third tick. The route answers 429 when it is fed too often; a heartbeat
#: is the one report that carries nothing a later one will not, so it is
#: the one to ration. State changes and the session's start and end go
#: immediately. On a 429 the whole channel goes quiet for TELEMETRY_BACKOFF_S.
TELEMETRY_HEARTBEAT_TICKS = 3
TELEMETRY_BACKOFF_S = 120.0
#: How long the position may sit still before it counts as a rebuffer for
#: the QoE counters. Deliberately shorter than the 8.6 chip's delay in the
#: window: this is a measurement, not a piece of chrome, and a two-second
#: freeze is a stall whether or not it was worth telling the viewer about.
TELEMETRY_STALL_AFTER_S = 2.0

# Lazy, see addonref.py. ADDON and ADDON_NAME were both defined here and
# neither was ever read; only the string lookup survives.
_ = addonref.localize


def stash_pending_session(file_id: str, media_id: Optional[str], session_id: str, session_token: str) -> None:
    """Called by addon.py immediately before setResolvedUrl."""
    xbmcgui.Window(10000).setProperty(
        HANDOFF_PROPERTY,
        json.dumps(
            {
                "file_id": file_id,
                "media_id": media_id,
                "session_id": session_id,
                "session_token": session_token,
                "stashed_at": time.time(),
            }
        ),
    )


def _take_pending_session() -> Optional[dict]:
    win = xbmcgui.Window(10000)
    raw = win.getProperty(HANDOFF_PROPERTY)
    if not raw:
        return None
    win.clearProperty(HANDOFF_PROPERTY)
    try:
        return json.loads(raw)
    except ValueError:
        return None


#: Where the playing stream's first frame sits in the file, in ms, published
#: by PlayerWindow. See publish_time_offset.
TIME_OFFSET_PROPERTY = "plugin.video.tofa.time_offset_ms"


def publish_time_offset(offset_ms: int) -> None:
    """Tell this process how far into the file the playing stream starts.

    Zero (or absent) means Kodi's clock IS the file clock, which is the case
    for DirectPlay and for anything played through addon.py's plain
    directory route. Non-zero means the server cut an HLS session at a
    resume offset, so every position read here is short by that much.

    Written by PlayerWindow, which is in the OTHER process -- hence a
    Window(10000) property rather than a call.
    """
    win = xbmcgui.Window(10000)
    if offset_ms:
        win.setProperty(TIME_OFFSET_PROPERTY, str(int(offset_ms)))
    else:
        win.clearProperty(TIME_OFFSET_PROPERTY)


def _time_offset_ms() -> int:
    try:
        return int(xbmcgui.Window(10000).getProperty(TIME_OFFSET_PROPERTY) or 0)
    except (TypeError, ValueError):
        return 0


def _pending_file_id() -> Optional[str]:
    """The file a handoff has been stashed for but not yet adopted, if any.

    Read WITHOUT consuming it -- _take_pending_session is the consumer, on
    onAVStarted. This exists only to answer "is another item already on its
    way in?", which is what makes a position read during the changeover
    untrustworthy. See _report.
    """
    raw = xbmcgui.Window(10000).getProperty(HANDOFF_PROPERTY)
    if not raw:
        return None
    try:
        return (json.loads(raw) or {}).get("file_id")
    except ValueError:
        return None


class TofaPlayer(xbmc.Player):
    def __init__(self) -> None:
        super().__init__()
        self._session: Optional[dict] = None
        self._is_paused = False
        self._last_position_ms = 0
        self._http_session = http.new_session()
        self._last_tick_position_ms: Optional[int] = None
        self._position_advanced_at: Optional[float] = None
        self._last_reported_position_ms: Optional[int] = None
        self._regression_held = False
        self._opening_timeout_warned_for: Optional[str] = None
        # -- telemetry ----------------------------------------------------
        self._qoe = telemetry.QoE()
        self._telemetry_ticks = 0
        self._telemetry_muted_until = 0.0
        self._stalled_since: Optional[float] = None
        self._bitrate_bps: Optional[int] = None

    def _client(self) -> Optional[MediaServerClient]:
        try:
            tok = auth.ensure_fresh(self._http_session)
        except (auth.NotSignedIn, http.ApiError):
            return None
        # Read-only: unlike interactive window call sites, this runs in
        # service.py's background process and must never pop a PIN dialog
        # mid-playback. Only update_progress/update_watched need profile
        # scoping; report_progress/report_stopped/end_session are secured
        # by session_token alone. If a locked profile's token expires
        # mid-playback, those two calls just 401 like any other transient
        # error -- playback itself is unaffected.
        #
        # Built per call, off tokens.json, on purpose: that is also how a
        # renewed token reaches this process. Once the viewer re-enters the
        # PIN in the foreground, the next heartbeat picks the new token up
        # with no signalling between the two processes.
        return api.client_for(self._http_session, tok)

    def _position_ms(self) -> int:
        """getTime() is unreliable by the time onPlayBackStopped/Ended fire
        -- Kodi has already torn down the player's internal state, so a
        live read there raises or silently returns 0. Cache the last
        successful read and fall back to it instead of losing the actual
        stopped position."""
        try:
            ms = int(self.getTime() * 1000) + _time_offset_ms()
        except RuntimeError:
            return self._last_position_ms
        # Kodi's clock can read slightly NEGATIVE before the first frame
        # lands -- measured -99ms on 2026-08-11, during a start that stalled
        # in the audio renderer and never produced one. The server rejects a
        # negative position outright (`HTTP 422: position_ticks must be
        # greater than or equal to zero`), so every heartbeat in that window
        # is thrown away, including the last one before the stall detector
        # gives up. Clamped here rather than at the call sites: a negative
        # playback position is meaningless to all of them.
        self._last_position_ms = ms = max(0, ms)
        return ms

    @staticmethod
    def _log_api_error(what: str, exc: http.ApiError) -> None:
        # 410 means the server already garbage-collected the session (idle
        # streams can go `Gone` well before the 24h `st` JWT expiry) -- the
        # end state we wanted anyway, not a real failure.
        log_fn = log.debug if exc.status == 410 else log.warning
        log_fn(f"monitor: {what} failed: {exc}")

    def _report(self, *, ended: bool = False, timeout: Optional[float] = None) -> None:
        """`timeout` is for the periodic heartbeat, which runs on a timer and
        must not hold the loop up. The FINAL report leaves it None on purpose:
        that write is the one that persists where the viewer got to, it
        happens once, and nothing is waiting behind it -- so it gets http.py's
        full budget and the fallback base_url as well."""
        if not self._session:
            return
        client = self._client()
        if not client:
            return
        position_ms = self._position_ms()
        # Independent calls: one failing (e.g. 410 on the session endpoint)
        # must not skip the other -- only update_progress persists resume.
        try:
            client.report_progress(
                self._session["session_id"],
                self._session["session_token"],
                position_ms,
                self._is_paused,
                ended,
                timeout=timeout,
            )
        except http.ApiError as exc:
            self._log_api_error("session progress", exc)

        # DO NOT persist a resume point during an episode changeover.
        #
        # PlayerWindow's Next Up advance replaces the playing item without
        # stopping it, and it stashes the incoming session BEFORE calling
        # play(). In the window between those two moments this player still
        # holds the OUTGOING episode's session, while getTime() has already
        # started answering for the INCOMING one -- so a callback landing
        # there (measured: one ~190ms after the advance) wrote the new
        # episode's position, near zero, against the old episode's file id.
        #
        # That is not a cosmetic drift. `ended=False` with a low position
        # RESETS the record: measured against the live server,
        # progress(pos=300, ended=False) turned completed:true back into
        # completed:false, position 300. So an episode the viewer had just
        # watched to the credits and pressed Play Next on came back as
        # barely started -- it stayed in Continue Watching, Detail showed no
        # tick, and the show's next-up never moved. Reported from the box as
        # "the Details screen is not updated, neither is Continue Watching".
        #
        # Skipping the write costs nothing: PlayerWindow._close_out_session
        # has already written the outgoing episode's real final state from
        # the position it captured while that episode was still the one
        # playing, and the incoming session's own heartbeats resume the
        # moment onAVStarted adopts it.
        pending = _pending_file_id()
        if pending and pending != self._session["file_id"]:
            log.debug("monitor: mid-changeover, not writing progress for "
                      f"{self._session['file_id']}")
            return
        if not ended and self._regression_unconfirmed(position_ms):
            return
        try:
            client.update_progress(self._session["file_id"], position_ms, ended, timeout=timeout)
        except http.ApiError as exc:
            self._log_api_error("media progress", exc)

    def _regression_unconfirmed(self, position_ms: int) -> bool:
        """Make a big backwards jump prove itself before it costs a resume.

        The resume point is written unguarded -- the server stores whatever
        arrives (`position_ms = $2`; only `progress_percent` is protected
        with GREATEST). So one bad reading is enough to move a viewer back to
        the start of something they had half-watched.

        And bad readings are not hypothetical. On the box 2026-08-08 a
        heartbeat reported `position_ms=50` about 17 minutes into an episode.
        That one happened to be the SESSION endpoint, so the resume point
        survived, but nothing about the code makes that the lucky case, and
        the cause is still unexplained.

        So: a jump further back than POSITION_REGRESSION_MS, with no seek to
        explain it, is held for one heartbeat. If the next reading agrees, it
        is written -- the position really did move. This deliberately cannot
        latch: at most one heartbeat (~10s) is ever skipped, so a genuine
        rewind is late, never lost. Skipping until it "looks right" would
        risk pinning the resume point forever, which is worse than the bug.

        onPlayBackSeek clears the baseline, so an ordinary rewind never gets
        here at all."""
        last = self._last_reported_position_ms
        regressed = last is not None and position_ms < last - POSITION_REGRESSION_MS
        # A FLAG, not the held value: comparing values would re-arm the hold
        # every time the suspect position differed slightly from the last
        # one, which is exactly what a stream playing on from a bad reading
        # would do -- and the resume point would then never move again.
        if regressed and not self._regression_held:
            self._regression_held = True
            log.warning(f"monitor: position jumped back {last}ms -> {position_ms}ms with no "
                        "seek; holding one heartbeat before moving the resume point")
            return True
        self._regression_held = False
        self._last_reported_position_ms = position_ms
        return False

    def _end_session(self) -> None:
        if not self._session:
            return
        client = self._client()
        if client:
            try:
                client.end_session(self._session["session_id"], self._session["session_token"])
            except http.ApiError as exc:
                self._log_api_error("end_session", exc)
        self._session = None
        self._is_paused = False
        self._last_position_ms = 0
        self._last_tick_position_ms = None
        self._position_advanced_at = None
        self._last_reported_position_ms = None
        self._regression_held = False

    # -- xbmc.Player callbacks ---------------------------------------------

    def onAVStarted(self) -> None:
        pending = _take_pending_session()
        if pending:
            self._session = pending
            self._is_paused = False
            self._last_position_ms = 0
            self._last_tick_position_ms = None
            self._position_advanced_at = None
            self._last_reported_position_ms = None
            self._regression_held = False
            self._opening_timeout_warned_for = None
            log.debug(f"monitor: adopted session {pending['session_id']}")
            self._qoe = telemetry.QoE()
            self._telemetry_ticks = 0
            self._stalled_since = None
            self._bitrate_bps = self._file_bitrate(pending)
            stashed = pending.get("stashed_at")
            if stashed:
                # Handoff to first frame. The stash is written right before
                # play() is called, so this is the whole of Kodi opening the
                # stream -- what the viewer waited through.
                self._qoe.time_to_first_frame_ms = max(0.0, (time.time() - stashed) * 1000.0)
            self._telemetry(telemetry.PLAYBACK_STARTED)

    def onPlayBackPaused(self) -> None:
        self._is_paused = True
        self._report()
        self._telemetry(telemetry.STATE_CHANGE)

    def onPlayBackResumed(self) -> None:
        self._is_paused = False
        self._report()
        self._telemetry(telemetry.STATE_CHANGE)

    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        # A backward seek would otherwise look like zero progress to the
        # stall check below and start counting it against the threshold.
        self._last_tick_position_ms = None
        self._position_advanced_at = None
        self._last_reported_position_ms = None
        self._regression_held = False
        self._report()
        # AFTER the report, not just before it. This callback can arrive
        # while getTime() still answers with the pre-seek position, and the
        # report above would then re-arm the baseline at the place we just
        # seeked away from -- making the next heartbeat, the first one
        # carrying the real new position, look like an unexplained jump
        # backwards. Clearing it again means the first post-seek reading is
        # always taken at face value, which is exactly right: a seek is the
        # one moment we KNOW the position moved on purpose.
        self._last_reported_position_ms = None
        self._regression_held = False

    def onPlayBackStopped(self) -> None:
        if self._session:
            client = self._client()
            # The final position FIRST, and only then "this session is over".
            # `report_stopped` retires the session id, so a heartbeat sent
            # after it is addressed to something the server has already
            # reaped -- it answers with `stream_session.validate_fail` /
            # `not_in_registry` and drops the write.
            #
            # Measured 2026-08-11 against the server's own log: the two
            # requests arrived 9-11ms apart, in that order, on EVERY stop --
            # a healthy playback and a stalled one alike. player.py's
            # close-out already had the order right (progress, then stopped,
            # then end_session); this is the same sequence.
            self._report()
            self._telemetry(telemetry.SESSION_END)
            if client:
                try:
                    client.report_stopped(self._session["session_id"], self._session["session_token"])
                except http.ApiError as exc:
                    self._log_api_error("report_stopped", exc)
        self._end_session()

    def onPlayBackEnded(self) -> None:
        # Mark watched explicitly rather than let the server infer
        # completion from the last heartbeat position.
        if self._session:
            client = self._client()
            if client:
                try:
                    client.update_watched(self._session["file_id"], True)
                except http.ApiError as exc:
                    self._log_api_error("update_watched", exc)
            self._report(ended=True)
            self._telemetry(telemetry.SESSION_END)
        self._end_session()

    def onPlayBackError(self) -> None:
        log.warning("monitor: onPlayBackError -- tearing down session")
        self._telemetry(telemetry.FATAL_ERROR, error={
            "code": "playback_error", "fatal": True,
            "message": "Kodi reported a playback error"})
        self._end_session()

    # -- called periodically by service.py's loop ---------------------------

    def _check_opening_timeout(self) -> None:
        """Kodi never got as far as onAVStarted for the URL addon.py handed
        it. Checked here (not a one-shot timer) since this process --
        service.py -- is the only one still running by the time it would
        matter; addon.py already exited right after setResolvedUrl."""
        if self._session:
            return
        win = xbmcgui.Window(10000)
        raw = win.getProperty(HANDOFF_PROPERTY)
        if not raw:
            return
        try:
            pending = json.loads(raw)
        except ValueError:
            win.clearProperty(HANDOFF_PROPERTY)
            return
        session_id = pending.get("session_id")
        if self._opening_timeout_warned_for == session_id:
            return  # already warned, and leaving the property so a late onAVStarted still adopts it
        if time.time() - pending.get("stashed_at", 0) < OPENING_TIMEOUT_SECONDS:
            return
        self._opening_timeout_warned_for = session_id
        log.warning(f"monitor: opening timeout -- no onAVStarted within {OPENING_TIMEOUT_SECONDS}s of handoff")
        toast.show(_(31034))

    def _check_stall(self, now: Optional[float] = None) -> None:
        """Give up on a stream whose position has not moved for real time.

        Deliberately measured against the WALL CLOCK rather than by counting
        ticks. Counting ticks assumes ticks are evenly spaced, and they are
        not: service.py's loop is `tick(); waitForAbort(TICK_SECONDS)`, so a
        tick that blocks in _report() pushes the next one out by however long
        the network took. The failure that motivates this is exactly the one
        that stretches ticks -- an unreachable server -- so the old
        three-ticks-in-a-row threshold got looser precisely when it needed to
        hold, and 30s of intent silently became minutes.

        `now` is injectable so the timing can be tested without sleeping.
        """
        if self._is_paused:
            # A paused position legitimately does not advance. Drop the
            # timestamp rather than freezing it, so the window restarts from
            # the resume rather than counting the pause against the stream.
            self._position_advanced_at = None
            return
        now = time.time() if now is None else now
        pos = self._position_ms()
        advanced = self._last_tick_position_ms is None or pos > self._last_tick_position_ms + STALL_EPSILON_MS
        self._last_tick_position_ms = pos
        if advanced or self._position_advanced_at is None:
            self._position_advanced_at = now
            return
        stalled_for = now - self._position_advanced_at
        if stalled_for >= STALL_TIMEOUT_SECONDS:
            log.warning(f"monitor: playback stalled at {pos}ms for {stalled_for:.0f}s, no recovery -- stopping")
            toast.show(_(31035))
            self._telemetry(telemetry.FATAL_ERROR, error={
                "code": "stall_timeout", "fatal": True,
                "message": f"position did not advance for {stalled_for:.0f}s"})
            self._position_advanced_at = None
            self.stop()  # triggers onPlayBackStopped -> normal teardown/reporting

    def tick(self) -> None:
        """~10s heartbeat while actively playing."""
        if self._session and self.isPlayingVideo():
            # Stall check FIRST: _report() is the call that can block, and a
            # stalled stream is worth acting on before spending the tick's
            # network budget reporting a position that has not moved.
            self._check_stall()
            self._report(timeout=PROGRESS_TIMEOUT_SECONDS)
            self._tick_telemetry()
        self._check_opening_timeout()  # no-op once self._session is set

    # -- telemetry ----------------------------------------------------------

    def _file_bitrate(self, session: dict) -> Optional[int]:
        """The playing file's bitrate in bits per second, from the server's own
        record of it (MediaFile.bitrate) -- the one input the box does not
        have for telemetry.buffer_ahead_ms. One request per session, at
        adoption; anything short of an answer is None and the buffer tile
        simply stays empty."""
        media_id, file_id = session.get("media_id"), session.get("file_id")
        if not media_id:
            return None
        client = self._client()
        if not client:
            return None
        try:
            record = client.media_detail(media_id) or {}
            files = record.get("files") or []
            match = next((f for f in files if f.get("id") == file_id), None) or (files[0] if files else {})
            bitrate = match.get("bitrate")
            return int(bitrate) if bitrate else None
        except Exception as exc:                                # noqa: BLE001
            log.debug(f"monitor: no bitrate for buffer telemetry: {exc!r}")
            return None

    def _player_state(self) -> str:
        if self._is_paused:
            return telemetry.PAUSED
        return telemetry.BUFFERING if self._qoe.buffering else telemetry.PLAYING

    def _tick_telemetry(self, now: Optional[float] = None) -> None:
        """Once per service tick, after the stall check has read the position.

        Two jobs. First the QoE transitions: a position that has not moved
        for TELEMETRY_STALL_AFTER_S while not paused, or Kodi refilling a
        buffer, is a rebuffer -- counted on the way in, timed on the way out,
        each edge sent as one state_change. Then the heartbeat, every
        TELEMETRY_HEARTBEAT_TICKS ticks.

        `now` is injectable, like _check_stall's, so the transitions can be
        tested without sleeping."""
        now = time.time() if now is None else now
        refilling = False
        try:
            refilling = bool(xbmc.getCondVisibility("Player.Caching"))
        except Exception:                                   # noqa: BLE001
            pass
        frozen = (not self._is_paused and self._position_advanced_at is not None
                  and now - self._position_advanced_at >= TELEMETRY_STALL_AFTER_S)
        if refilling or frozen:
            if self._qoe.buffering_began(now):
                self._telemetry(telemetry.STATE_CHANGE, now=now)
        elif self._qoe.buffering_ended(now):
            self._telemetry(telemetry.STATE_CHANGE, now=now)
        self._telemetry_ticks += 1
        if self._telemetry_ticks % TELEMETRY_HEARTBEAT_TICKS == 0:
            self._telemetry(telemetry.HEARTBEAT, now=now)

    def _telemetry(self, kind: str, *, error: Optional[dict] = None,
                   now: Optional[float] = None) -> None:
        """Send one report for the current session. Never raises, never
        blocks the loop for long, and never affects progress reporting: a
        failed report is a lost decoration on the server's Activity page,
        nothing more. A 429 mutes the channel for TELEMETRY_BACKOFF_S."""
        if not self._session:
            return
        now = time.time() if now is None else now
        if now < self._telemetry_muted_until:
            return
        client = self._client()
        if not client:
            return
        payload = telemetry.report(
            kind, position_ms=self._position_ms(), state=self._player_state(),
            qoe=self._qoe.as_dict(now), base_url=getattr(client, "base_url", ""),
            error=error, bitrate_bps=self._bitrate_bps, now=now)
        try:
            client.report_telemetry(
                self._session["session_id"], self._session["session_token"],
                payload, timeout=PROGRESS_TIMEOUT_SECONDS)
            # The server logs nothing for a 204 and the admin session list
            # carries no telemetry, so this line is the only trace that a
            # report went out at all. Debug level: one line per ~30s.
            log.debug(f"monitor: telemetry {kind} sent (state={payload['player_state']}, "
                      f"rebuffers={payload['qoe']['rebuffer_count']}, "
                      f"buffer_ahead_ms={payload['playback']['buffer_ahead_ms']})")
        except http.ApiError as exc:
            if getattr(exc, "status", None) == 429:
                self._telemetry_muted_until = now + TELEMETRY_BACKOFF_S
                log.debug(f"monitor: telemetry rate-limited, quiet for {TELEMETRY_BACKOFF_S:.0f}s")
            else:
                self._log_api_error("telemetry", exc)
        except Exception as exc:                                # noqa: BLE001
            # Not a narrower catch, on purpose. This runs inside the same
            # loop as the progress heartbeat and on the stop path ahead of
            # report_stopped -- the two writes that decide where the viewer
            # resumes. A bug in telemetry (a label Kodi answers oddly, a
            # client without the method) must cost the Activity page a
            # tile, never the resume point.
            log.warning(f"monitor: telemetry report dropped: {exc!r}")
