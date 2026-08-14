# -*- coding: utf-8 -*-
"""Audio and subtitle sync -- the two corrections that can only be judged
against the picture.

WHY THIS EXISTS. Kodi's own OSD carries both, but its dialogs are drawn by
the active skin and, since the player became a dialog over Kodi's fullscreen
video, they render ON TOP of our chrome saying the same things in a different
visual language. The values themselves are reachable without them; this module
is the reachable part, kept out of windows/player.py so it can be tested
without a window.

THE TWO ARE NOT SYMMETRIC, and the asymmetry is Kodi's, not a design choice:

  audio     `Player.SetAudioDelay` / `Player.GetAudioDelay` -- an absolute
            setter WITH read-back. The schema pins the value to a multiple of
            0.025 over +/-10s, so those are not numbers we picked.

  subtitle  no JSON-RPC exists at all. Enumerating every `Player.*` method in
            the Kodi 21.3 binary gives `SetAudioDelay` and no
            `SetSubtitleDelay`. The only lever is
            `Action(subtitledelayplus|subtitledelayminus)`, which steps 0.1s
            and reports NOTHING back -- so the value here is a SHADOW we keep
            ourselves, and it is only true for as long as nothing else moves
            it. Reset it whenever playback restarts (see `SubtitleOffset`).

The step sizes differ for the same reason the problems differ. Lip-sync is
argued about in tens of milliseconds, which is why Kodi's own quantum is
0.025s. Subtitle timing is argued about in whole seconds, and 0.1s of
subtitle offset is imperceptible -- so the coarser step Kodi forces on us
costs nothing here.
"""
import json
import os
import re
import sqlite3
from typing import Optional

import xbmc
import xbmcvfs

from . import log

#: Kodi's own quantum. `Player.SetAudioDelay`'s schema: "The value should be a
#: multiple of 0.025 in a range of +/-10". Sending anything else is rejected.
AUDIO_STEP = 0.025

#: What one press of `Action(subtitledelayplus)` moves. Not ours to choose.
SUBTITLE_STEP = 0.1

#: `advancedsettings.xml` can widen this (<audiodelayrange>); we clamp to the
#: documented default rather than reading a setting that is usually absent.
#: Clamping matters because the RPC silently ignores an out-of-range offset,
#: which would leave our displayed value lying about the stream.
RANGE = 10.0


def _rpc(method: str, params: Optional[dict] = None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload))).get("result")
    except (ValueError, TypeError, AttributeError) as exc:
        log.debug(f"playbacksync: rpc {method} failed: {exc!r}")
        return None


def _video_player_id() -> Optional[int]:
    active = _rpc("Player.GetActivePlayers") or []
    if not isinstance(active, list):
        return None
    video = next((p for p in active if p.get("type") == "video"), None)
    return video.get("playerid") if video else None


def quantise(seconds: float, step: float) -> float:
    """Snap to a multiple of `step`, then clamp into range.

    Rounded through an INTEGER count of steps rather than by arithmetic on
    the float: 0.025 has no exact binary form, so accumulating it lands on
    values like 0.30000000000000004, which the RPC then rejects as not a
    multiple of 0.025. Counting steps keeps every value exact by
    construction."""
    steps = int(round(float(seconds) / step))
    limit = int(RANGE / step)
    steps = max(-limit, min(limit, steps))
    return round(steps * step, 6)


def format_offset(seconds: float, step: float) -> str:
    """"0.00 s" / "+0.05 s" / "-0.30 s".

    Zero used to read "In sync", and that was wrong -- owner's call, and he
    is right: we do not know whether the stream is in sync. Nothing measures
    it. Zero means only that we have applied no correction, which is the
    state every one of these controls exists BECAUSE it might be wrong. A
    number claims nothing.

    The decimal count follows the step, so a row never shows a digit it
    cannot move."""
    value = quantise(seconds, step)
    # Enough decimals to show the step EXACTLY. Two was wrong for audio:
    # 0.025 displayed as "0.03", so two presses read as +0.03 then +0.05 and
    # the row looked like it was rounding badly. Owner reported it; three
    # decimals show 0.025 for what it is.
    decimals = next(d for d in (1, 2, 3, 4)
                    if abs(round(step, d) - step) < 1e-9)
    sign = "+" if value > 0 else ("-" if value < 0 else "")
    return "{0}{1:.{2}f} s".format(sign, abs(value), decimals)


# ----------------------------------------------------------------------
# Audio -- absolute, with read-back
# ----------------------------------------------------------------------

def audio_offset() -> Optional[float]:
    """The delay Kodi is actually applying, or None if it will not say.

    None is not zero and must not be shown as "In sync": between `play()` and
    the first frame there is no player to ask, and a row that claimed the
    stream was in sync while the answer was simply unavailable would be a
    lie the viewer cannot see through."""
    result = _rpc("Player.GetAudioDelay")
    if not isinstance(result, dict) or "offset" not in result:
        return None
    try:
        return float(result["offset"])
    except (TypeError, ValueError):
        return None


def set_audio_offset(seconds: float) -> Optional[float]:
    """Apply an absolute audio delay. Returns the value actually sent."""
    player_id = _video_player_id()
    if player_id is None:
        return None
    value = quantise(seconds, AUDIO_STEP)
    if _rpc("Player.SetAudioDelay",
            {"playerid": player_id, "offset": value}) is None:
        return None
    log.debug(f"playbacksync: audio offset -> {value}")
    return value


def nudge_audio(current: Optional[float], forward: bool) -> Optional[float]:
    """One press. `current` may be None -- then the press starts from zero."""
    base = 0.0 if current is None else current
    return set_audio_offset(base + (AUDIO_STEP if forward else -AUDIO_STEP))


# ----------------------------------------------------------------------
# Subtitles -- stepping only, so the value is ours to remember
# ----------------------------------------------------------------------

def _video_db_path() -> Optional[str]:
    """Kodi's newest MyVideos database, or None.

    The number is the schema version and rises with Kodi releases; the box
    carries 145, 146 and 147 side by side and only the highest is live."""
    folder = xbmcvfs.translatePath("special://database/")
    try:
        names = [n for n in xbmcvfs.listdir(folder)[1]
                 if re.fullmatch(r"MyVideos\d+\.db", n)]
    except Exception:                                   # noqa: BLE001
        return None
    if not names:
        return None
    newest = max(names, key=lambda n: int(re.search(r"\d+", n).group()))
    return os.path.join(folder, newest)


def kodi_subtitle_delay(file_id) -> Optional[float]:
    """The offset KODI has stored for this file -- the real answer.

    There is no getter in the API (no `Player.SetSubtitleDelay`, no property,
    confirmed against a running Kodi 22), but Kodi does not keep the value to
    itself: it writes it to its own video database and re-applies it on the
    next play. That database is the only place the truth exists, so this is
    where we read it.

    The join is exact rather than fuzzy because of how Kodi stores our
    streams, measured on the box:

        strPath      http://host:port/api/v1/stream/{file_id}/
        strFilename  direct

    -- the `st=` session token lives in the query and Kodi drops it, so the
    stable tofa file id is right there in the path. That is also WHY Kodi
    remembers at all, which the first version of this module got wrong.

    Read-only, and best-effort: a locked or missing database is a reason to
    show nothing useful, never to fail a playback."""
    path = _video_db_path()
    if not path or file_id is None:
        return None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error as exc:
        log.debug(f"playbacksync: no video db ({exc})")
        return None
    try:
        row = connection.execute(
            "SELECT s.SubtitleDelay FROM settings s "
            "JOIN files f ON f.idFile = s.idFile "
            "JOIN path p ON p.idPath = f.idPath "
            "WHERE p.strPath LIKE ?",
            (f"%/stream/{file_id}/%",)).fetchone()
    except sqlite3.Error as exc:
        log.debug(f"playbacksync: could not read subtitle delay ({exc})")
        return None
    finally:
        connection.close()
    if not row or row[0] is None:
        return None
    return quantise(float(row[0]), SUBTITLE_STEP)


class SubtitleOffset:
    """A shadow of Kodi's subtitle delay, because Kodi will not report it.

    IT STARTS FROM WHAT WE STORED, NOT FROM ZERO. The original version reset
    to zero at every playback on the reasoning that Kodi could not remember:
    our stream URL carries a per-session `st=` token, so surely every play is
    a new `idFile`. Read off the box's own MyVideos DB on 2026-08-10, that is
    false --

        idFile=1005  SubtitleDelay=3.299999  strFilename=direct
        idFile=1043  SubtitleDelay=10.700005 AudioDelay=0.025

    -- because Kodi keys the row on the PATH, and the path carries the stable
    `{file_id}`; the token lives in the query, which Kodi drops. So Kodi
    remembers the offset and re-applies it, while the panel, having reset,
    displayed "0.00 s". Owner's repro nailed it exactly: early on the one
    episode he had adjusted, in sync on every other, in sync for that same
    episode on another device.

    So we mirror Kodi instead of fighting it: the value is persisted per tofa
    file id and loaded back at playback start, which keeps our number and
    Kodi's actual offset in step for as long as we are the only thing moving
    it. Nothing inside our player can reach Kodi's own OSD, so in practice we
    are.

    The audio row needs none of this -- `Player.GetAudioDelay` reads the real
    value, so it cannot drift whatever Kodi remembers. This whole class is
    the cost of subtitles having no getter."""

    def __init__(self):
        self.value = 0.0
        self._file_id = None

    def load(self, file_id) -> float:
        """Seed from what KODI has stored, which is what it is about to
        apply. Reading it beats remembering it ourselves: our own copy would
        be one more thing that can disagree with the player, and this one
        cannot."""
        self._file_id = str(file_id) if file_id is not None else None
        stored = kodi_subtitle_delay(file_id)
        self.value = stored if stored is not None else 0.0
        log.info(f"playbacksync: subtitle offset for {self._file_id} = {self.value}")
        return self.value

    def reset(self):
        """Forget the offset WITHOUT touching Kodi. Only for a file we have
        no id for -- otherwise use load()."""
        self.value = 0.0

    def nudge(self, forward: bool) -> float:
        target = quantise(self.value + (SUBTITLE_STEP if forward
                                        else -SUBTITLE_STEP), SUBTITLE_STEP)
        if target == self.value:
            # Already at the clamp. Sending the action anyway would move
            # Kodi past where we think it is and desynchronise the shadow.
            return self.value
        xbmc.executebuiltin("Action({0})".format(
            "subtitledelayplus" if forward else "subtitledelayminus"))
        # Kodi answers that action by raising its OWN slider, drawn by
        # whatever skin is installed -- reported from the box as "the default
        # Estuary bar also appears". Close it on the same press rather than
        # waiting for the player's 200ms tick to notice, which would let it
        # flash. The tick closes it too, as a backstop for a press that
        # arrives from somewhere other than the panel.
        xbmc.executebuiltin("Dialog.Close(sliderdialog,true)")
        self.value = target
        log.debug(f"playbacksync: subtitle offset -> {self.value}")
        return self.value

    def label(self) -> str:
        return format_offset(self.value, SUBTITLE_STEP)

    def walk_to_zero(self) -> None:
        """Step back to no offset. There is no absolute setter, so the only
        way to move Kodi is to send every step."""
        guard = 0
        while self.value and guard < int(2 * RANGE / SUBTITLE_STEP):
            self.nudge(self.value < 0)
            guard += 1
