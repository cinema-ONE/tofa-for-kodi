# -*- coding: utf-8 -*-
"""Discover's Coming Up planner (app 2.1.0): seven-day pages of dated releases.

A port of the web app's planner over the server's spotlight shelves
(`coming_up=spotlight`): pages, day labels, the hero's lines and how focus
moves. Dates are ISO strings; "today" is the window's first day, as on the
web. No Kodi imports, so it tests without one.
"""
from __future__ import annotations

import datetime

#: The server's page length when the shelf does not say.
PAGE_DAYS = 7
#: A day with more than this many entries shows MORE_AT of them and "N more".
MAX_SHOWN, MORE_AT = 15, 14
#: Rows: a one-line title fits beside its thumb; each further line adds to it.
ROW_MIN_H, ROW_BASE_H, ROW_LINE_H = 81, 41, 27.5


def _date(iso: str) -> datetime.date:
    return datetime.date.fromisoformat(iso[:10])


def _add(iso: str, days: int) -> str:
    return (_date(iso) + datetime.timedelta(days=days)).isoformat()


def days_between(a: str, b: str) -> int:
    return (_date(b) - _date(a)).days


def entries(shelf: dict) -> list:
    """Every dated item as {key, item, release}, in the server's order."""
    out = []
    for i, item in enumerate(shelf.get("items") or []):
        release = item.get("release")
        if release and release.get("date"):
            out.append({"key": "{0}:{1}:{2}:{3}".format(
                item.get("type"), item.get("tmdb_id"), release["date"], i),
                "item": item, "release": release})
    return out


def window(shelf: dict, found: list) -> dict:
    """{from, to, page_days}; the first release stands in for a missing window."""
    win = shelf.get("window") or {}
    start = win.get("from") or (found[0]["release"]["date"] if found else "1970-01-01")
    days = win.get("page_days") or PAGE_DAYS
    return {"from": start, "to": win.get("to") or start, "page_days": days if days > 0 else PAGE_DAYS}


def beyond(found: list, after: str):
    """The earliest entry dated after `after`, or None."""
    later = [e for e in found if e["release"]["date"] > after]
    return min(later, key=lambda e: e["release"]["date"]) if later else None


def pages(shelf: dict) -> list:
    """The window cut into pages of page_days days, each day with its entries."""
    found = entries(shelf)
    win = window(shelf, found)
    by_day: dict = {}
    for e in found:
        if win["from"] <= e["release"]["date"] <= win["to"]:
            by_day.setdefault(e["release"]["date"], []).append(e)
    size = win["page_days"]
    count = max(1, max(0, days_between(win["from"], win["to"])) // size + 1)
    out = []
    for index in range(count):
        start = _add(win["from"], index * size)
        days = [{"iso": _add(start, d), "entries": by_day.get(_add(start, d), [])}
                for d in range(size)]
        out.append({"index": index, "from": start, "to": _add(start, size - 1), "days": days,
                    "count": sum(len(d["entries"]) for d in days)})
    return out


def last_page(all_pages: list, more_beyond: bool) -> int:
    """The last page worth paging to: all of them when something lies beyond."""
    if more_beyond:
        return len(all_pages) - 1
    for i in range(len(all_pages) - 1, 0, -1):
        if all_pages[i]["count"]:
            return i
    return 0


def shown(day: dict) -> tuple:
    """(entries drawn, how many more) -- a crowded day shows 14 and "N more"."""
    found = day["entries"]
    if len(found) > MAX_SHOWN:
        return found[:MORE_AT], len(found) - MORE_AT
    return found, 0


def stops(day: dict) -> int:
    """Focusable rows in a day: its entries, plus "N more" when there is one."""
    rows, more = shown(day)
    return len(rows) + (1 if more else 0)


# ------------------------------------------------------------------ focus --
# A stop is (page, day, row); day -1 is the page's "Next:" line when the page
# is empty. Moves answer ("focus", stop), ("leave",) or ("stay",).

def first_stop(all_pages: list, page: int) -> tuple:
    days = all_pages[page]["days"] if 0 <= page < len(all_pages) else []
    for d, day in enumerate(days):
        if day["entries"]:
            return page, d, 0
    return page, -1, 0


def _enter(all_pages: list, page: int, step: int, row: int) -> tuple:
    days = all_pages[page]["days"]
    order = range(len(days)) if step == 1 else range(len(days) - 1, -1, -1)
    for d in order:
        if days[d]["entries"]:
            return page, d, min(row, stops(days[d]) - 1)
    return page, -1, 0


def move(all_pages: list, stop: tuple, direction: str, last: int) -> tuple:
    """Where `direction` (up/down/left/right) takes focus from `stop`."""
    page, day, row = stop
    if not 0 <= page < len(all_pages):
        return ("stay",)
    days = all_pages[page]["days"]
    if day == -1:
        if direction == "up":
            return ("leave",)
        if direction == "down":
            return ("stay",)
    else:
        n = stops(days[day])
        if direction == "up":
            return ("focus", (page, day, row - 1)) if row > 0 else ("leave",)
        if direction == "down":
            return ("focus", (page, day, row + 1)) if row + 1 < n else ("stay",)
    step = 1 if direction == "right" else -1
    if day != -1:
        d = day + step
        while 0 <= d < len(days):
            n = stops(days[d])
            if n:
                return ("focus", (page, d, min(row, n - 1)))
            d += step
    target = page + step
    if target < 0 or target >= len(all_pages) or target > last:
        return ("stay",)
    return ("focus", _enter(all_pages, target, step, 0 if day == -1 else row))


# ----------------------------------------------------------------- labels --

def relative(iso: str, today: str):
    """Today, Tomorrow, "in 3 days"; None for a past day."""
    n = days_between(today, iso)
    if n < 0:
        return None
    return "Today" if n == 0 else "Tomorrow" if n == 1 else "in {0} days".format(n)


def is_weekend(iso: str) -> bool:
    return _date(iso).weekday() >= 5


def episode_label(release: dict):
    """"S1 E3", "S1 E3–4" for a run of episodes; None for a film."""
    if release.get("venue") != "episode" or release.get("episode_number") is None:
        return None
    season = release.get("season_number")
    head = "" if season is None else "S{0} ".format(season)
    first, last = release["episode_number"], release.get("episode_number_last")
    if last is not None and last > first:
        return "{0}E{1}–{2}".format(head, first, last)
    return "{0}E{1}".format(head, first)


def venue_label(release: dict):
    """"In cinemas", "At home", or the episode."""
    venue = release.get("venue")
    if venue == "cinema":
        return "In cinemas"
    if venue == "home":
        return "At home"
    return episode_label(release)


def hero_meta(release: dict, today: str, long_date) -> list:
    """The hero's first line: what, when, and how soon."""
    return [part for part in (venue_label(release), long_date(release["date"]),
                              relative(release["date"], today)) if part]


def genre_line(item: dict) -> str:
    """"Mystery, Drama · TV-PG"."""
    genres = ", ".join((item.get("genres") or [])[:2])
    return " · ".join(part for part in (genres, item.get("content_rating")) if part)


def overview(entry: dict) -> str:
    return entry["release"].get("episode_overview") or entry["item"].get("overview") or ""


def next_line(entry: dict, long_date) -> str:
    """An empty page's pointer: "Next: Dune in cinemas on Fri 4 Dec"."""
    release = entry["release"]
    when = "on " + long_date(release["date"])
    venue = release.get("venue")
    if venue == "cinema":
        tail = "in cinemas " + when
    elif venue == "home":
        tail = "at home " + when
    else:
        ep = episode_label(release)
        tail = "{0} {1}".format(ep, when) if ep else when
    return "Next: {0} {1}".format(entry["item"].get("title") or "", tail)


def wrap(text: str, width: float, measure) -> list:
    """Greedy word wrap, as Kodi breaks a label; a word too long stays whole."""
    lines, line = [], ""
    for word in (text or "").split():
        candidate = word if not line else line + " " + word
        if line and measure(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def row_height(lines: int) -> int:
    """A thumb row's height: the thumb's, or the title's lines and the meta."""
    return int(round(max(ROW_MIN_H, ROW_BASE_H + ROW_LINE_H * lines)))
