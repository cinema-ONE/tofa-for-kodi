# -*- coding: utf-8 -*-
"""Universes (server 0.12.0): a franchise in story order, built from a curated collection.

The server sends the members with their library and watch state; what is up
next, what counts as watched and how far along a profile is are worked out
here, the same way tofa's apps do. No Kodi imports, so it tests without one.
"""
from __future__ import annotations

import datetime
import math
import struct
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from . import http, log, regional

#: Request statuses that mean nothing is on its way.
_REQUEST_DEAD = frozenset(("denied", "failed", "declined", "cancelled", "canceled"))


def _is_show(media_type) -> bool:
    return media_type in ("tv", "show", "series")


def _key(item: dict, season=None) -> str:
    base = item.get("local_media_id") or "{0}-{1}".format(item.get("type"), item.get("tmdb_id"))
    return base if season is None else "{0}#season-{1}".format(base, season)


def build(collection: dict) -> dict:
    """A universe from GET /collections/{id}: its members, counts and next title."""
    items = collection.get("items") or []
    seen_keys: dict[str, int] = {}
    for item in items:
        seen_keys[_key(item)] = seen_keys.get(_key(item), 0) + 1
    members = []
    for position, item in enumerate(items, 1):
        show = _is_show(item.get("type"))
        upcoming = item.get("upcoming") is True
        owned = bool(item.get("in_library")) and not upcoming
        episodes = item.get("episode_count")
        watched_eps = item.get("watched_episode_count") or 0
        if not owned:
            watched = False
        elif show:
            watched = watched_eps > 0 and (item.get("unwatched_episode_count") == 0
                                           or (bool(episodes) and watched_eps >= episodes))
        else:
            watched = item.get("watched") is True
        started = (not upcoming and not watched
                   and ((item.get("progress_percent") or 0) > 0 or watched_eps > 0))
        status = item.get("request_status") or ""
        season = item.get("season_number")
        label = None
        if season is not None and seen_keys[_key(item)] > 1:
            label = (item.get("season_name") or "").strip() or (
                "Specials" if season == 0 else "Season {0}".format(season))
        members.append({
            "key": _key(item, season),
            "position": position,
            "item": item,
            "is_show": show,
            "owned": owned,
            "watched": watched,
            "started": started,
            "requested": bool(status) and status not in _REQUEST_DEAD,
            "upcoming": upcoming,
            "state": ("upcoming" if upcoming else "watched" if watched
                      else "owned" if owned else "missing"),
            "title": "{0}, {1}".format(item.get("title"), label) if label else item.get("title") or "",
            "chapter": (item.get("chapter") or "").strip() or None,
        })
    released = [m for m in members if not m["upcoming"]]
    watched_count = sum(1 for m in members if m["watched"])
    next_up = next((m for m in members if m["owned"] and not m["watched"]), None)
    coming_next = None
    if next_up is None and released and watched_count == len(released):
        coming_next = next((m for m in members if m["upcoming"]), None)
    return {
        "id": collection.get("id"),
        "name": collection.get("name") or "",
        "overview": collection.get("overview") or "",
        "backdrop": collection.get("backdrop_url") or "",
        "poster": collection.get("poster_url") or "",
        "members": members,
        "chapters": _chapters(members),
        "released_count": len(released),
        "upcoming_count": len(members) - len(released),
        "owned_count": sum(1 for m in members if m["owned"]),
        "watched_count": watched_count,
        "next_up": next_up,
        "coming_next": coming_next,
        "in_progress": next_up is not None and any(m["watched"] or m["started"] for m in members),
    }


def _chapters(members: list) -> list:
    """(name, first index, last index) for each run of one chapter."""
    out = []
    for index, member in enumerate(members):
        name = member["chapter"]
        if not name:
            continue
        if out and out[-1][0] == name and out[-1][2] == index - 1:
            out[-1] = (name, out[-1][1], index)
        else:
            out.append((name, index, index))
    return out


#: Every universe, per server and profile, for a minute (the web's own staleness).
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
CACHE_S = 60


def everything(client, workers: int = 4) -> list:
    """Every universe with members, in the server's order, cached a minute.

    One request per universe, as the web app makes them; a few at a time,
    since Home waits on this row."""
    key = (getattr(client, "base_url", None), getattr(client, "profile_id", None))
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    ids = from_payload(client.collections(curated=True))

    def one(collection_id):
        try:
            data = client.collection(collection_id) or {}
        except http.ApiError as exc:
            log.warning("universe {0}: {1}".format(collection_id, exc))
            return None
        return build(data) if data.get("kind") == "curated" else None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        built = [u for u in pool.map(one, ids) if u and u["members"]]
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), built)
    return built


def forget() -> None:
    """Drop the cache: a title was marked, so up next may have moved."""
    with _CACHE_LOCK:
        _CACHE.clear()


def continuing(client, workers: int = 4) -> list:
    """The universes Continue the saga shows, in the server's order."""
    return [u for u in everything(client, workers) if continues(u)]


def entries(universe: dict, media_id=None, tmdb_id=None, media_type=None) -> list:
    """The members that are this title: by library id, else TMDB id and type."""
    return [m for m in universe["members"]
            if (media_id is not None and m["item"].get("local_media_id") == media_id)
            or (tmdb_id is not None and m["item"].get("tmdb_id") == tmdb_id
                and _is_show(m["item"].get("type")) == _is_show(media_type))]


def hero_item(universe: dict) -> dict:
    """The title a saga card stands for: up next, else the next to come."""
    member = universe["next_up"] or universe["coming_next"]
    return member["item"] if member else {}


def card_art(universe: dict) -> str:
    """A saga card's picture: its title's backdrop, else the universe's."""
    return hero_item(universe).get("backdrop_path") or universe["backdrop"]


def continues(universe: dict) -> bool:
    """Whether it belongs on Continue the saga: started, or caught up with more to come."""
    return universe["in_progress"] or universe["coming_next"] is not None


def ordered(universe: dict, order: str = "story") -> list:
    """Members in story order, or by year with what is still to come last."""
    if order == "story":
        return list(universe["members"])
    def key(pair):
        index, m = pair
        if m["upcoming"]:
            return (1, m["item"].get("release_date") or "￿", index)
        return (0, m["item"].get("year") or 9999, index)
    return [m for _i, m in sorted(enumerate(universe["members"]), key=key)]


def episode_code(member: dict) -> str:
    """"S1 E1" for a show's next episode, else ""."""
    nxt = member["item"].get("next_episode") or {}
    if not member["is_show"] or not nxt:
        return ""
    return "S{0} E{1}".format(nxt.get("season_number"), nxt.get("episode_number"))


def coming_label(member: dict, today: Optional[datetime.date] = None) -> str:
    """"Coming Dec 18" (with the year when it is not this one), or "Coming soon"."""
    raw = (member["item"].get("release_date") or "")[:10]
    try:
        when = datetime.date.fromisoformat(raw)
    except ValueError:
        return "Coming soon"
    today = today or datetime.date.today()
    if when.year != today.year:
        return "Coming " + regional.day_month_year(when)
    return "Coming " + regional.day_and_month(when)


def card_title(universe: dict) -> str:
    """The line over a Continue the saga card's art."""
    member = universe["next_up"]
    if member is not None:
        code = episode_code(member)
        if code:
            return "{0} {1}".format(member["item"].get("title"), code)
        return "{0} · {1}".format(member["position"], member["title"])
    member = universe["coming_next"]
    return "Up next: {0} · {1}".format(member["title"], coming_label(member)) if member else ""


def card_line(universe: dict) -> str:
    """"33 of 77 watched", plus the next show's episodes, as the Apple TV app
    (2.1.0) words it: out of every title, where the web counts released ones."""
    line = "{0} of {1} watched".format(universe["watched_count"], len(universe["members"]))
    member = universe["next_up"]
    if member is not None and member["is_show"] and member["item"].get("episode_count"):
        line += " · {0} of {1} episodes".format(
            member["item"].get("watched_episode_count") or 0, member["item"]["episode_count"])
    return line


def summary(universe: dict) -> str:
    """"77 titles in story order · 58 in your library · 33 watched", as the
    Apple TV app (2.1.0) heads the page; it leaves out the web's "· 2 coming"."""
    count = len(universe["members"])
    parts = ["{0} {1} in story order".format(count, "title" if count == 1 else "titles")]
    parts.append("{0} in your library".format(universe["owned_count"])
                 if universe["owned_count"] else "none in your library yet")
    if universe["watched_count"]:
        parts.append("{0} watched".format(universe["watched_count"]))
    return " · ".join(parts)


def member_status(member: dict, next_key: Optional[str]) -> str:
    """A member's label: Watched, Up next, In progress, In your library, ..."""
    if member["upcoming"]:
        return coming_label(member)
    if member["watched"]:
        return "Watched"
    code = episode_code(member)
    if member["key"] == next_key:
        return "Up next: {0}".format(code) if code else (
            "Up next, in progress" if member["started"] else "Up next")
    if member["owned"]:
        if code and member["started"]:
            return "Next: {0}".format(code)
        return "In progress" if member["started"] else "In your library"
    return "Requested" if member["requested"] else "Not in your library"


def strip_png(universe: dict, width: int, height: int, edge: bool = True,
              radius: int = 0, up_next: bool = False) -> bytes:
    """The segmented strip as a PNG: one segment per member, shaded by state.

    Kodi has no way to draw a variable number of shapes in a list item, so
    the strip is a picture. `edge` is the card-bottom variant, whose up-next
    segment is left out to be drawn on its own in the accent: `up_next`
    gives that segment alone, in white. `radius` rounds the card's corners."""
    members = universe["members"]
    count = max(1, len(members))
    gap = max(1, width // 278)          # 2px on a 556px card, as the app draws it
    if width < count * gap * 3:
        gap = 0
    next_key = (universe["next_up"] or {}).get("key")
    fills = {"watched": (255, 255, 255, 255), "owned": (255, 255, 255, 92),
             "missing": (255, 255, 255, 28), "upcoming": (0, 0, 0, 0)}
    row = []
    for x in range(width):
        index = min(count - 1, x * count // width)
        start = index * width // count
        end = (index + 1) * width // count
        member = members[index] if members else None
        is_next = edge and member is not None and member["key"] == next_key
        if member is None or (gap and x >= end - gap and index < count - 1):
            colour = (0, 0, 0, 0)
        elif up_next or is_next:
            colour = (255, 255, 255, 255) if is_next and up_next else (0, 0, 0, 0)
        elif member["state"] == "upcoming":
            colour = (255, 255, 255, 56) if x in (start, end - 1 - gap) else (0, 0, 0, 0)
        else:
            colour = fills[member["state"]]
        row.append(colour)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        rise = height - y - 0.5          # this line's height above the card's bottom edge
        for x, (r, g, b, a) in enumerate(row):
            if radius and a and rise < radius:
                across = min(x + 0.5, width - x - 0.5)
                if across < radius:
                    dist = math.hypot(radius - across, radius - rise)
                    a = int(a * max(0.0, min(1.0, radius - dist + 0.5)))
            raw.extend((r, g, b, a))
    return _png(width, height, bytes(raw))


def _png(width: int, height: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def from_payload(payload: Any) -> list:
    """Every curated collection id in a GET /collections?curated=true answer."""
    found = (payload or {}).get("collections") if isinstance(payload, dict) else payload
    return [c.get("id") for c in found or [] if c.get("kind") == "curated" and c.get("id")]
