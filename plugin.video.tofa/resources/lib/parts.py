# -*- coding: utf-8 -*-
"""Split files: one film or episode delivered as several files, played as one.

The server marks each member of a multi-part set with `part_number` and
`part_count` (server 0.11.0). Members of one set are played back to back;
members whose edition differs are alternatives, as other versions are.

The server finishes a FILE at 90% of its length or 5 minutes before its end,
and finishing any part finishes the whole title. So a part that is not the
last is never reported past just under that point.
"""
from __future__ import annotations

from typing import Optional

#: The server's own finish rule, per file (measured 2026-09-21).
FINISH_FRACTION = 0.90
FINISH_LEFT_MS = 300_000
#: How far short of that point a non-final part's progress is kept.
FINISH_MARGIN_MS = 5_000


def _key(f: dict) -> tuple:
    return (f.get("edition") or "", f.get("part_count"))


def sets(files: list) -> list:
    """`files` grouped into what can be played: each entry is a list of
    files, one for a plain file, every part in order for a complete set. A
    set with a part missing falls apart into its members, as before."""
    out, groups = [], {}
    for f in files or []:
        if f.get("part_number") and (f.get("part_count") or 0) > 1:
            groups.setdefault(_key(f), []).append(f)
        else:
            out.append([f])
    for members in groups.values():
        members.sort(key=lambda f: f.get("part_number") or 0)
        numbers = [f.get("part_number") for f in members]
        if numbers == list(range(1, (members[0].get("part_count") or 0) + 1)):
            out.append(members)
        else:
            out.extend([f] for f in members)
    order = {id(f): i for i, f in enumerate(files or [])}
    out.sort(key=lambda group: min(order.get(id(f), 0) for f in group))
    return out


def set_of(files: list, file_id: str) -> list:
    """The complete set `file_id` belongs to, or [] when it plays alone."""
    for group in sets(files):
        if len(group) > 1 and any(f.get("id") == file_id for f in group):
            return group
    return []


def duration_ms(group: list) -> int:
    return sum(int(f.get("duration_ms") or 0) for f in group or [])


def start_ms(group: list, index: int) -> int:
    """Where part `index` begins on the title's own clock."""
    return duration_ms(group[:index])


def locate(group: list, title_ms: int) -> tuple:
    """(part index, position in that part) for a position on the title."""
    for i, f in enumerate(group):
        length = int(f.get("duration_ms") or 0)
        if title_ms < length or i == len(group) - 1:
            return i, max(0, min(title_ms, length))
        title_ms -= length
    return 0, 0


def finish_point_ms(part_duration_ms: int) -> int:
    """Where the server counts a file finished."""
    return int(min(part_duration_ms * FINISH_FRACTION, part_duration_ms - FINISH_LEFT_MS))


def progress_cap_ms(part_duration_ms: int) -> int:
    """The furthest a non-final part may be reported without the server
    finishing it, and with it the whole title."""
    return max(0, finish_point_ms(part_duration_ms) - FINISH_MARGIN_MS)


def resume_point(group: list, progress: dict) -> tuple:
    """(part index, position) to resume a set from, given each part's
    progress record by file id ({position_ms, completed, updated_at}). The
    part written last decides, as Continue Watching does; after a finished
    part, the next one from its start."""
    recorded = [(str((progress.get(f.get("id")) or {}).get("updated_at") or ""), i)
                for i, f in enumerate(group) if progress.get(f.get("id"))]
    if not recorded:
        return 0, 0
    _when, i = max(recorded)
    rec = progress[group[i].get("id")]
    if rec.get("completed"):
        return (i + 1, 0) if i + 1 < len(group) else (0, 0)
    return i, int(rec.get("position_ms") or 0)


def label(group: list) -> Optional[str]:
    """"2 parts" for a set, None for a single file."""
    return "{0} parts".format(len(group)) if len(group) > 1 else None
