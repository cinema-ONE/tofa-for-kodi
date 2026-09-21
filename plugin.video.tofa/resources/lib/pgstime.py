# -*- coding: utf-8 -*-
"""PGS display sets moved onto a server-cut session's clock.

The server sends `full.sup` on the file's clock, as it does `full.ass`, and
a session resumed or seeked mid-file starts at the cut.
"""
from __future__ import annotations

import struct

_PCS = 0x16


def shift(data: bytes, offset_ms: int) -> bytes:
    """Move every display set `offset_ms` earlier and drop those before it.

    A display set starts at a presentation composition segment, and its
    other segments share that segment's fate. Timestamps are 90 kHz."""
    if offset_ms <= 0:
        return data
    delta = offset_ms * 90
    out = bytearray()
    keep = False
    i = 0
    while i + 13 <= len(data) and data[i:i + 2] == b"PG":
        pts, dts = struct.unpack(">II", data[i + 2:i + 10])
        size = struct.unpack(">H", data[i + 11:i + 13])[0]
        if data[i + 10] == _PCS:
            keep = pts >= delta
        if keep:
            seg = bytearray(data[i:i + 13 + size])
            struct.pack_into(">II", seg, 2, max(0, pts - delta), max(0, dts - delta) if dts else 0)
            out += seg
        i += 13 + size
    return bytes(out)
