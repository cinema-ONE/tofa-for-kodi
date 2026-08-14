# -*- coding: utf-8 -*-
"""How an episode's season/number is written, in one place.

WHY THIS EXISTS. One file can carry several episodes -- `S04E19E20` on disk --
and server 0.9.27 started saying so: `Episode.episode_number_end` holds the
last number covered, and is NULL for the ordinary one-episode row
(`episode_number=19, episode_number_end=20`). Before that a double episode
showed only its first number, which made the second look missing from the
library.

The number is rendered in five places (Continue Watching captions, the
player's now-playing line, the Next Up rail, the episode drawer, the
directory listing), and a range that appeared in some of them but not others
would read as a different episode depending on where you looked -- so the
formatting lives here rather than in each of them.

FORM. `S4 E19-E20`, extending this client's existing `S1 E2`: a space between
the season and the episode, no zero padding, and no letter-spacing (Kodi has
none). tofa's own surfaces write `S04E19-E20` because that is the web app's
padded style; the range is what has to agree, not the padding, and being
internally consistent beats matching a different client's spelling of the
season -- the same call already made for the player's separator.
"""
from __future__ import annotations

from typing import Any, Optional


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def number_text(episode: Any, episode_end: Any = None) -> str:
    """`19`, or `19-E20` when one file covers a range.

    The trailing `E` is part of the range, not a prefix, so a caller that has
    already written `E` gets `E19-E20` rather than `E19-20`. That is the form
    tofa uses and it is unambiguous about the second number being an episode
    rather than a part or a minute.
    """
    start = _as_int(episode)
    if start is None:
        return ""
    end = _as_int(episode_end)
    # A NULL end is the ordinary case. An end that is not AFTER the start is
    # ignored rather than trusted: a row saying 19-19 (or 19-18) describes one
    # episode, and printing the range would invent a second one.
    if end is None or end <= start:
        return str(start)
    return "{0}-E{1}".format(start, end)


def number_label(season: Any, episode: Any, episode_end: Any = None) -> str:
    """`S4 E19`, or `S4 E19-E20`. Empty when either number is missing."""
    season_num = _as_int(season)
    body = number_text(episode, episode_end)
    if season_num is None or not body:
        return ""
    return "S{0} E{1}".format(season_num, body)


def title_or_number(ep: dict) -> str:
    """An episode's own title, falling back to `Episode 19` / `Episode 19-E20`.

    The fallback carries the range too: a titleless double episode listed as
    "Episode 19" is the very thing that made the 20th look absent.
    """
    title = (ep or {}).get("title")
    if title:
        return str(title)
    body = number_text((ep or {}).get("episode_number"),
                       (ep or {}).get("episode_number_end"))
    return "Episode {0}".format(body) if body else ""
