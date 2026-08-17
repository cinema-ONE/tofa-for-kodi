# -*- coding: utf-8 -*-
"""How far into a title the viewer is -- asked here, by everyone.

Progress is the one piece of state in this add-on that changes while the
user is looking at something else. A screen loads it, the viewer watches ten
minutes, backs out, and the screen is still holding the figure it fetched
before any of that happened. It also changes on other devices, which no
amount of local bookkeeping would catch.

So there is no cached progress anywhere. Every surface asks the server, and
asks at the moment the answer matters:

- **when play is pressed** -- `resume_position_ms()`. Never pass a screen's
  own copy of `position_ms` as the resume point; that is how "resume, skip
  forward, exit, play again" replayed the same ten minutes twice.
- **when a screen comes back to the front** -- each window's
  `refresh_watch_progress()`, called from its `onReInit()`. Kodi re-inits the
  window underneath whenever the one above it closes, so that hook fires
  after playback, after a Detail page closes, after anything.

A surface that displays a position implements `refresh_watch_progress()` and
calls it from `onReInit()`. Today that is Home's Continue Watching row and
the Detail page (its primary pill and its episode rows). The plugin://
directory listing needs nothing: Kodi re-runs it per navigation, so it is
never stale in the first place.

The arithmetic lives here too, because three surfaces were each rounding a
percentage into a pre-rendered fill asset with their own copy of the same
expression.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from . import http, log
from .api import MediaServerClient


def fetch_one(client: MediaServerClient, file_id: str) -> Optional[dict]:
    """This file's progress record, or None if it has none / the call failed.

    None is deliberately not distinguishable from "no progress" -- every
    caller treats both as "start from the beginning", and a screen that
    guessed differently on a transient error would offer a resume point it
    could not justify."""
    if not file_id:
        return None
    try:
        return client.get_progress(file_id) or None
    except http.ApiError as exc:
        log.warning(f"progress: could not read progress for {file_id}: {exc}")
        return None


def fetch_many(client: MediaServerClient, file_ids: list, *,
               required: bool = False) -> dict[str, dict]:
    """{file_id: record} for a whole row in ONE request.

    A per-card call would put twenty round trips on the GUI thread every time
    Home came back to the front.

    An empty map on failure reads as "none of these has been watched" -- a
    claim about the LIBRARY that the request never actually established.
    Harmless where there is nothing on screen to contradict; a lie where
    there is. `required=True` re-raises instead, for callers repainting
    something already correct. Measured cost of not having this, 2026-08-09:
    a profile token that expired mid-episode 401'd this call, and the Detail
    page underneath went back to offering S1 E1 on a show whose S1 E14 had
    just been watched."""
    wanted = [f for f in dict.fromkeys(file_ids) if f]
    if not wanted:
        return {}
    try:
        resp = client.media_progress_batch(wanted) or {}
    except http.ApiError as exc:
        log.warning(f"progress: batch read failed for {len(wanted)} files: {exc}")
        if required:
            raise
        return {}
    return {p.get("media_file_id"): p for p in (resp.get("items") or []) if p.get("media_file_id")}


def position_of(record: Optional[dict]) -> tuple[int, bool]:
    """(position_ms, completed) from a record that may be None."""
    if not record:
        return 0, False
    return int(record.get("position_ms") or 0), bool(record.get("completed"))


def episode_candidates(seasons: Any) -> list:
    """(season_number, episode_number, episode, first available file) for
    every playable episode of a show, in season/episode order.

    Specials (season_number 0) are excluded: they are not part of the
    running order, so neither next-up nor "the episode this page offers"
    should ever land on one."""
    candidates = []
    for season in seasons or []:
        if (season.get("season_number") or 0) == 0:
            continue
        for ep in season.get("episodes") or []:
            avail = [f for f in (ep.get("files") or []) if f.get("available")]
            if avail:
                candidates.append(
                    (season.get("season_number"), ep.get("episode_number") or 0, ep, avail[0]))
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates


def next_up(candidates: list, progress_map: dict, prefer_file_id: Any = None):
    """Which of `candidates` a show should offer, or None if there are none.

    The rule, in order of preference:

      0. one the CALLER named (Continue Watching knows its own episode)
      1. one already STARTED and not finished -- the MOST RECENTLY one,
         broken by `updated_at`, when several are part-watched
      2. the first not-yet-completed AFTER the highest completed episode
      3. the first not-yet-completed, when there is no usable frontier
      4. the first episode, when everything is completed

    Pure and side-effect free so both the detail hero and the card context
    menu can ask the same question and get the same answer. Detail owns the
    prose on WHY each rule exists -- see DetailWindow._next_up_episode.
    """
    if not candidates:
        return None
    if prefer_file_id:
        for c in candidates:
            if str(c[3].get("id")) == str(prefer_file_id):
                return c
    started = [
        c for c in candidates
        if (progress_map.get(c[3].get("id")) or {}).get("position_ms")
        and not (progress_map.get(c[3].get("id")) or {}).get("completed")
    ]
    if started:
        return max(started,
                   key=lambda c: (progress_map.get(c[3].get("id")) or {}).get("updated_at") or "")
    # (2) Scanning from the top alone offers S1 E1 to a viewer whose history
    # is a finished late season -- the same disagreement with Continue
    # Watching that rule (1) exists to prevent, since the server promotes the
    # episode after the last one FINISHED, not the earliest gap. A gap behind
    # the frontier was skipped on purpose; ahead of it is where they are.
    completed = [
        c for c in candidates
        if (progress_map.get(c[3].get("id")) or {}).get("completed")
    ]
    if completed:
        frontier = max(completed, key=lambda c: (c[0], c[1]))
        for c in candidates:
            if (c[0], c[1]) <= (frontier[0], frontier[1]):
                continue
            prog = progress_map.get(c[3].get("id"))
            if not prog or not prog.get("completed"):
                return c
    for c in candidates:
        prog = progress_map.get(c[3].get("id"))
        if not prog or not prog.get("completed"):
            return c
    return candidates[0]


def resume_position_ms(
    client: MediaServerClient, file_id: str, fallback: Optional[int] = None
) -> Optional[int]:
    """Where this file should resume from, asked at the moment of play.

    Returns None for "start from the beginning" -- either there is no
    progress, or the title is completed, which is a rewatch.

    On an API failure the caller's own value is handed back rather than
    None: a stale resume point is a much smaller injury than silently
    restarting a film someone is an hour into. That is also why this cannot
    just be `fetch_one()` at the call site -- the two disagree about what a
    failure means, on purpose.
    """
    try:
        record = client.get_progress(file_id)
    except http.ApiError as exc:
        log.warning(f"progress: could not read resume position for {file_id}: {exc}")
        return fallback
    position_ms, completed = position_of(record)
    if completed:
        return None
    return position_ms or None


def fraction(position_ms: Any, duration_ms: Any) -> float:
    """0.0-1.0, clamped, and 0.0 whenever the answer cannot be known."""
    try:
        position_ms, duration_ms = float(position_ms or 0), float(duration_ms or 0)
    except (TypeError, ValueError):
        return 0.0
    if duration_ms <= 0:
        return 0.0
    return max(0.0, min(1.0, position_ms / duration_ms))


def fill_step(position_ms: Any, duration_ms: Any) -> int:
    """The pre-rendered progress strip to use, as an even 2..100, or 0.

    Kodi item layouts cannot size a texture per item, so a progress bar is
    one of 51 pre-rendered assets picked by rounded percentage. Never 0 for a
    title with real progress: the strips carry a rounded left cap, and the
    empty one would draw nothing where the viewer expects a sliver."""
    pct = fraction(position_ms, duration_ms)
    if not pct:
        return 0
    return max(2, min(100, int(round(pct * 100 / 2.0)) * 2))


def minutes_left_label(position_ms: Any, duration_ms: Any) -> str:
    """`116 MIN LEFT`, or "" when there is nothing left to say."""
    try:
        remaining = float(duration_ms or 0) - float(position_ms or 0)
    except (TypeError, ValueError):
        return ""
    if remaining <= 0:
        return ""
    return "{0} MIN LEFT".format(int(math.ceil(remaining / 60000.0)))
