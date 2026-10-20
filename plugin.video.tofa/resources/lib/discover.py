# -*- coding: utf-8 -*-
"""Discover's tabs as the Apple TV app 2.1.0 draws them (server 0.12.0, layout 2).

The server groups its shelves (For You, Trending, Coming Up, Best Of, Genres)
and lists the genre lanes; Universes is the client's own tab, before Genres,
as tofa's web app puts it. No Kodi imports, so it tests without one.
"""
from __future__ import annotations

#: Shelves of a group this client does not know land here rather than vanish.
FALLBACK_TAB = "for-you"


def group_shelves(page: dict, tabs: tuple) -> dict:
    """{tab key: [shelf, ...]} in the server's order; empty shelves dropped,
    except Coming Up's planner views, which say "Nothing dated" instead."""
    known = {key for key, _label in tabs}
    grouped: dict = {key: [] for key in known}
    for shelf in page.get("shelves") or []:
        if not (shelf.get("items") or shelf.get("tiles") or shelf.get("form") == "spotlight"):
            continue
        group = shelf.get("group") or FALLBACK_TAB
        grouped.setdefault(group if group in known else FALLBACK_TAB, []).append(shelf)
    return grouped


def saved_filters(prefs: dict | None, keys) -> dict:
    """The profile's `discover_filters`, read as the web reads them: only a real true is on."""
    saved = (prefs or {}).get("discover_filters")
    saved = saved if isinstance(saved, dict) else {}
    return {key: saved.get(key) is True for key in keys}


def is_tiles(shelf: dict) -> bool:
    """A row of picture tiles (Genres to Try, By Decade) rather than titles."""
    return shelf.get("form") == "tiles"


def is_ranked(shelf: dict) -> bool:
    """Numbered cards: the server says so (Trending's rows)."""
    return bool(shelf.get("ranked"))


def lane_tiles(page: dict) -> list:
    """The Genres wall: one tile per lane, as the server orders them."""
    return [{"key": lane.get("slug"), "title": lane.get("title") or "",
             "artwork": lane.get("artwork") or "", "target": "lane"}
            for lane in page.get("lanes") or [] if lane.get("slug")]
