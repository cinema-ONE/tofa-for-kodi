# -*- coding: utf-8 -*-
"""Seen it and Not interested (server 0.12.0): a profile's own marks on a title.

Keyed by TMDB id, so they work on titles the library does not hold. Only
discovery payloads say whether a mark is set, so the rows are offered where
one of those is at hand.
"""
from __future__ import annotations

from typing import Optional

from . import cardoptions, kodigui
from .. import http, toast

KEYS = frozenset((cardoptions.SEEN_ADD, cardoptions.SEEN_REMOVE,
                  cardoptions.NOT_INTERESTED_ADD, cardoptions.NOT_INTERESTED_REMOVE))


def offered(data: dict, media_type: Optional[str] = None,
            tmdb_id=None) -> tuple[Optional[bool], Optional[bool]]:
    """(seen, not_interested) for cardoptions.option_keys; None = no row.

    Seen it is for titles the library does not hold: a held one has Mark
    as Watched."""
    if not (tmdb_id or data.get("tmdb_id")) or not (
            media_type or data.get("type") or data.get("media_type")):
        return None, None
    seen = (bool(data["seen"]) if "seen" in data
            and not (data.get("in_library") or data.get("local_media_id")) else None)
    not_interested = (bool(data["not_interested"]) if "not_interested" in data else None)
    return seen, not_interested


def apply(client, picked: str, data: dict, media_type: Optional[str] = None,
          tmdb_id=None) -> Optional[bool]:
    """Carry out one mark choice and record it in `data`: True when it was
    saved, False when the server refused, None when `picked` is not a mark.

    Success is silent, as on the Apple TV app (2.1.0); a failure says so."""
    if picked not in KEYS:
        return None
    media_type = media_type or data.get("type") or data.get("media_type")
    tmdb_id = tmdb_id or data.get("tmdb_id")
    on = picked in (cardoptions.SEEN_ADD, cardoptions.NOT_INTERESTED_ADD)
    seen_row = picked in (cardoptions.SEEN_ADD, cardoptions.SEEN_REMOVE)
    try:
        if seen_row:
            client.set_seen(media_type, tmdb_id, on)
        else:
            client.set_not_interested(media_type, tmdb_id, on)
    except http.ApiError as exc:
        kodigui.ERROR("titlemarks: {0} failed: {1}".format(picked, exc))
        toast.show("Couldn't update {0}, try again later".format(
            "Seen it" if seen_row else "Not interested"))
        return False
    data["seen" if seen_row else "not_interested"] = on
    return True
