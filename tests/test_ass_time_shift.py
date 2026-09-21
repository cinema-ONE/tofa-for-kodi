"""asstime.shift moves ASS events onto a cut session's clock.

A transcode resumed mid-file starts at the cut; the server's full.ass keeps
the file's clock, so every event has to move back by the cut.

Run:  python3 test_ass_time_shift.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import asstime

RESULTS = []

SCRIPT = (
    "﻿[Script Info]\r\n"
    "PlayResY: 1080\r\n"
    "\r\n"
    "[V4+ Styles]\r\n"
    "Format: Name, Fontname, Fontsize\r\n"
    "Style: Default,Arial,58\r\n"
    "\r\n"
    "[Events]\r\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n"
    "Dialogue: 0,0:00:10.06,0:00:11.18,Default,,0,0,0,,{\\b1}SHAGGY, early{\\b0}\r\n"
    "Dialogue: 0,0:03:01.00,0:03:05.50,Default,,0,0,0,,spans the cut\r\n"
    "Comment: 0,0:03:12.86,0:03:16.14,insert,,0,80,350,,a comment\r\n"
    "Dialogue: 0,0:03:12.86,0:03:16.14,insert,,0,80,350,,{\\an8}UNSER, REGULÄRES\r\n"
    "Dialogue: 0,1:02:03.45,1:02:04.00,Default,,0,0,0,,an hour in\r\n"
)


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def events(text):
    return [l for l in text.splitlines() if l.startswith(("Dialogue:", "Comment:"))]


def run():
    check("offset 0 changes nothing", asstime.shift(SCRIPT, 0) == SCRIPT)

    out = asstime.shift(SCRIPT, 181998)
    ev = events(out)
    check("an event that ends before the cut is dropped",
          not any("SHAGGY" in e for e in ev), repr(ev[:1]))
    check("an event spanning the cut starts at zero",
          "Dialogue: 0,0:00:00.00,0:00:03.50,Default,,0,0,0,,spans the cut" in ev, repr(ev))
    check("times round to centiseconds (192.86 - 181.998 = 10.862)",
          "Dialogue: 0,0:00:10.86,0:00:14.14,insert,,0,80,350,,{\\an8}UNSER, REGULÄRES" in ev,
          repr(ev))
    check("comments move too",
          "Comment: 0,0:00:10.86,0:00:14.14,insert,,0,80,350,,a comment" in ev, repr(ev))
    check("hours carry", "Dialogue: 0,0:59:01.45,0:59:02.00,Default,,0,0,0,,an hour in" in ev,
          repr(ev))
    check("styles, BOM and CRLF pass through",
          out.startswith("﻿[Script Info]\r\n")
          and "Style: Default,Arial,58\r\n" in out and out.count("\r\n") == SCRIPT.count("\r\n") - 1,
          repr(out[:40]))

    reordered = ("[Events]\nFormat: Start, End, Layer, Style, Text\n"
                 "Dialogue: 0:00:20.00,0:00:25.00,0,Default,commas, kept\n")
    check("the Format line decides which fields are times",
          events(asstime.shift(reordered, 5000)) == ["Dialogue: 0:00:15.00,0:00:20.00,0,Default,commas, kept"],
          repr(events(asstime.shift(reordered, 5000))))

    outside = "[Script Info]\nDialogue: not an event here\n"
    check("lines outside [Events] are left alone", asstime.shift(outside, 5000) == outside)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("ASS events move onto the session clock (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
