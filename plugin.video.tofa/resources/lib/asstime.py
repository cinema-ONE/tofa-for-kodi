# -*- coding: utf-8 -*-
"""ASS events moved onto a server-cut session's clock.

The server sends `full.ass` on the file's clock, but a transcode resumed or
seeked mid-file starts at the cut, so Kodi would show every event late or
early by that much. `full.vtt` arrives already shifted.
"""
from __future__ import annotations

import re
from typing import Optional

_TIME = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})\.(\d{1,3})$")
_EVENTS = ("dialogue", "comment")


def _parse(value: str) -> Optional[int]:
    """`H:MM:SS.cc` as milliseconds, or None."""
    m = _TIME.match(value.strip())
    if not m:
        return None
    h, mi, s, frac = m.groups()
    return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def _format(ms: int) -> str:
    cs = (ms + 5) // 10
    h, rest = divmod(cs, 360000)
    mi, rest = divmod(rest, 6000)
    s, c = divmod(rest, 100)
    return "%d:%02d:%02d.%02d" % (h, mi, s, c)


def _lead(field: str) -> str:
    return field[:len(field) - len(field.lstrip())]


def shift(text: str, offset_ms: int) -> str:
    """Move every event `offset_ms` earlier and drop those that end before 0.

    Everything else, line endings included, is passed through untouched."""
    if offset_ms <= 0:
        return text
    out = []
    in_events = False
    fields: list = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        head = body.strip().lstrip("﻿")
        key = head.split(":", 1)[0].strip().lower() if ":" in head else ""
        if head.startswith("[") and head.endswith("]"):
            in_events = head.lower() == "[events]"
            fields = []
        elif in_events and key == "format":
            fields = [f.strip().lower() for f in head.split(":", 1)[1].split(",")]
        elif in_events and key in _EVENTS and "start" in fields and "end" in fields:
            kind, rest = body.split(":", 1)
            parts = rest.split(",", len(fields) - 1)
            si, ei = fields.index("start"), fields.index("end")
            start, end = _parse(parts[si]), _parse(parts[ei])
            if start is not None and end is not None:
                if end - offset_ms <= 0:
                    continue
                parts[si] = _lead(parts[si]) + _format(max(0, start - offset_ms))
                parts[ei] = _lead(parts[ei]) + _format(end - offset_ms)
                line = kind + ":" + ",".join(parts) + line[len(body):]
        out.append(line)
    return "".join(out)
