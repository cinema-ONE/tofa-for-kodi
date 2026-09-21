"""pgstime.shift moves PGS display sets onto a cut session's clock.

The server's full.sup is on the file's clock; a transcode resumed mid-file
starts at the cut, so every display set moves back by it.

Run:  python3 test_pgs_time_shift.py
"""
import struct

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import pgstime

RESULTS = []
PCS, WDS, PDS, ODS, END = 0x16, 0x17, 0x14, 0x15, 0x80


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def seg(kind, seconds, payload=b"\x00" * 11, dts=0):
    return b"PG" + struct.pack(">IIBH", int(seconds * 90000), dts, kind, len(payload)) + payload


def display_set(seconds, dts=0):
    return b"".join(seg(k, seconds, dts=dts) for k in (PCS, WDS, PDS, ODS, END))


def sets(data):
    """(pts seconds, dts, segment kinds) per display set."""
    out, i = [], 0
    while i + 13 <= len(data):
        pts, dts, kind, size = struct.unpack(">IIBH", data[i + 2:i + 13])
        if kind == PCS:
            out.append([round(pts / 90000, 3), dts, []])
        out[-1][2].append(kind)
        i += 13 + size
    return out


def run():
    data = display_set(5.0) + display_set(10.5) + display_set(20.25, dts=20 * 90000)
    check("offset 0 changes nothing", pgstime.shift(data, 0) == data)
    out = sets(pgstime.shift(data, 8000))
    check("a display set before the cut is dropped whole", len(out) == 2, repr(out))
    check("later sets move back by the cut", [s[0] for s in out] == [2.5, 12.25], repr(out))
    check("every segment of a set survives with it",
          all(s[2] == [PCS, WDS, PDS, ODS, END] for s in out), repr(out))
    check("a zero DTS stays zero, a real one moves", out[0][1] == 0 and out[1][1] == 12 * 90000, repr(out))
    check("a cut past everything leaves nothing", pgstime.shift(data, 60000) == b"")
    check("data that is not PGS yields nothing", pgstime.shift(b"WEBVTT\n\n", 1000) == b"")

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("PGS display sets move onto the session clock (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
