# -*- coding: utf-8 -*-
"""The last playback preferences we successfully read, kept on disk.

WHY THIS EXISTS
===============

Which audio track plays is decided by the CLIENT (see tracks.choose_audio and
[[project_track_selection]]) from `preferences.playback`, and the player used
to read those by calling `whoami()` -- a LIVE, uncached `/api/v1/users/me`
request -- from inside `onAVStarted`. On any failure it did this:

    except http.ApiError as exc:
        log.debug(f"player: no playback preferences: {exc!r}")
        return {}

and `{}` means `_apply_language_preferences` returns immediately, so the audio
is never switched at all and the stream keeps whatever the file lists FIRST.

On a German-first file with an English-first profile, one failed HTTP request
at the wrong moment is a German soundtrack -- reported from the cinema box
2026-08-12 on Murder, She Wrote S2 E1. The box log shows Kodi opening the
German stream with no switch ever following, while the SAME episode replayed
13 minutes later switched to English correctly. Nothing was logged either
time, because the only record of the failure was at debug level and debug
logging is off on that box.

Two things were wrong and both are fixed:

- **It was silent.** A wrong-language soundtrack is a user-visible outcome,
  not a debug detail, so the failure now logs at WARNING.
- **It was fragile.** One request at one instant decided it, with no memory.
  Preferences change rarely -- a stale copy is a far better answer than no
  copy, because "no copy" does not mean "no preference", it means "play
  whatever the file happens to list first".

So every successful read is remembered here, and the player falls back to it.
The windows that already fetch preferences for their own reasons
(`DetailWindow._ensure_preferences`, `MainWindow._ensure_preferences`) also
remember, which is what covers the case that actually bit: the FIRST play
after a Kodi start, when the player itself has never had a successful read.

Keyed by profile id, like search_history.py and for the same reason: two
household profiles have different languages and must not inherit each
other's.
"""
from __future__ import annotations

import json
import os

import xbmcaddon
import xbmcvfs

_FILENAME = "playback_prefs.json"


def _path() -> str:
    directory = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(directory)
    return os.path.join(directory, _FILENAME)


def _profile_id() -> str:
    """The signed-in profile, or "" when we cannot tell.

    "" is a usable key rather than an error: a single-profile install still
    gets a remembered copy, it just files it under the empty string.
    """
    try:
        from . import auth
        return str(auth.load().profile_id or "")
    except Exception:                                       # noqa: BLE001
        return ""


def _read_all() -> dict:
    try:
        path = _path()
        if not xbmcvfs.exists(path):
            return {}
        handle = xbmcvfs.File(path)
        try:
            raw = handle.read()
        finally:
            handle.close()
        return json.loads(raw) if raw else {}
    except Exception:                                       # noqa: BLE001
        # A corrupt or unreadable file must not stop playback. Losing the
        # remembered copy costs the fallback, not the stream.
        return {}


def remember(playback: dict | None) -> None:
    """Store `preferences.playback` for this profile. Never raises.

    Called from every place that successfully reads preferences, not just the
    player -- the point is that the player has something to fall back to
    BEFORE its own first read, which is precisely the moment that failed.
    """
    if not playback:
        return
    try:
        store = _read_all()
        if store.get(_profile_id()) == playback:
            return                                          # nothing changed
        store[_profile_id()] = playback
        handle = xbmcvfs.File(_path(), "w")
        try:
            handle.write(json.dumps(store))
        finally:
            handle.close()
    except Exception:                                       # noqa: BLE001
        pass


def last_known() -> dict:
    """The most recent successfully-read preferences, or {}."""
    return _read_all().get(_profile_id()) or {}
