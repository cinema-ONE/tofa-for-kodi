""""Plays as" names the screen mode Kodi will really switch to.

Kodi's mode search (CResolutionUtils::FindResolutionFromWhitelist) comes in
three variants -- upstream, CoreELEC 21 and CoreELEC 22 -- and each treats an
empty whitelist, the frame rate and 3D modes differently. The add-on used to
match on height alone, so a cropped 3840x2076 encode on a box with 1080p
menus claimed "Plays as 1080p" although Kodi switched to 2160p.

Run:  python3 test_plays_as_resolution.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities as caps

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


def ids(*modes):
    """Kodi mode ids from "3840x2160@23.97602" shorthand, "+3d" for tab/frp."""
    out = []
    for mode in modes:
        size, _, rest = mode.partition("@")
        hz, _, flag = rest.partition("+")
        w, h = size.split("x")
        out.append("%05d%05d%09.5f%s" % (int(w), int(h), float(hz), "ptabfrp" if flag else "pstd"))
    return out


RATES_4K = ["60", "59.94006", "50", "30", "29.97003", "25", "24", "23.97602"]
# The AM9 Pro's whitelist and the display's own mode list, as read off the box.
AM9_WHITELIST = ids(*["3840x2160@" + r for r in RATES_4K],
                    "1920x1080@24+3d", "1920x1080@23.97602+3d")
AM9_DISPLAY = ids(*["3840x2160@" + r for r in RATES_4K],
                  *["1920x1080@" + r for r in ("120", "100", "60", "59.94006", "50",
                                                "30", "29.97003", "25", "24", "23.97602")],
                  "1920x1080@24+3d", "1920x1080@23.97602+3d")


def box(whitelist, coreelec=True, kodi=22, screen=(1920, 1080, 60.0), switches=True,
        pulldown=True, double=False, display=AM9_DISPLAY):
    return {"known": True, "hdr_capable": True, "dolby_vision": True, "hdr10_plus": True,
            "modes": caps._modes_from_ids(display),
            "whitelist_modes": caps._modes_from_ids(whitelist),
            "screen_width": screen[0], "screen_height": screen[1], "screen_hz": screen[2],
            "switches_modes": switches, "whitelist_pulldown": pulldown,
            "whitelist_double": double, "whitelist_wholenumber": False,
            "coreelec": coreelec, "kodi_major": kodi}


def plays_as(vcaps, resolution, fps):
    width, height = (int(n) for n in resolution.split("x"))
    return caps.delivery({"video": {"dynamic_range": "sdr"}}, vcaps, {"known": False},
                         file_height=height, fps=fps, file_width=width)


def main():
    am9 = box(AM9_WHITELIST)
    check("CoreELEC 22: a full 4K file plays at 2160p", plays_as(am9, "3840x2160", 23.976), [])
    check("...a cropped one too, matched by its width", plays_as(am9, "3840x2076", 24.0), [])
    check("...an odd width takes the closest size at its rate",
          plays_as(am9, "3836x2072", 23.976), [])
    check("...and 25 fps finds 2160p25", plays_as(am9, "3840x2160", 25.0), [])

    empty = box([])
    check("CoreELEC 22, empty whitelist: 4K still switches up to 2160p",
          plays_as(empty, "3840x2160", 23.976), [])
    check("...but 25 fps is left out of the default list, so 1080p60 stays",
          plays_as(empty, "3840x2160", 25.0), ["1080p", "60Hz"])
    check("...and 1080p at 23.976 is shown at its own rate",
          plays_as(empty, "1920x1080", 23.976), [])

    upstream = box([], coreelec=False, pulldown=False)
    check("upstream, empty whitelist: 4K switches up to 2160p",
          plays_as(upstream, "3840x2160", 23.976), [])
    check("...and 25 fps doubles to 2160p50", plays_as(upstream, "3840x2160", 25.0), [])
    upstream_4k = box(ids(*["3840x2160@" + r for r in RATES_4K]), coreelec=False)
    check("upstream has no closest step: an odd width stays at 1080p60",
          plays_as(upstream_4k, "3836x2072", 23.976), ["1080p", "60Hz"])
    check("...while an exact width still switches", plays_as(upstream_4k, "3840x2076", 24.0), [])

    only_3d = box(ids("1920x1080@23.97602+3d"), screen=(3840, 2160, 60.0))
    check("CoreELEC 22 never gives a 2D film a 3D mode, so 2160p60 stays",
          plays_as(only_3d, "3840x2160", 23.976), ["60Hz"])
    ce21 = box(ids("1920x1080@23.97602+3d"), kodi=21, screen=(3840, 2160, 60.0))
    check("...CoreELEC 21 does, and that is a real 1080p",
          plays_as(ce21, "3840x2160", 23.976), ["1080p"])
    small = box(ids("1920x1080@23.97602"), screen=(3840, 2160, 60.0))
    check("a 1080p-only whitelist downgrades 4K", plays_as(small, "3840x2160", 23.976), ["1080p"])

    judder = box(ids("3840x2160@60"))
    check("24 fps on 60 Hz (3:2 pulldown) is named", plays_as(judder, "3840x2160", 24.0), ["60Hz"])
    doubled = box(ids("3840x2160@47.95204"), double=True,
                  display=AM9_DISPLAY + ids("3840x2160@47.95204"))
    check("...a whole multiple is not", plays_as(doubled, "3840x2160", 23.976), [])

    fixed = box(AM9_WHITELIST, switches=False)
    check("switching off: the screen's mode, and no rate claim",
          plays_as(fixed, "3840x2160", 23.976), ["1080p"])
    check("no frame rate: a whitelisted size of its own still counts",
          plays_as(am9, "3840x2076", None), [])
    check("...anything else claims nothing", plays_as(am9, "3836x2072", None), [])
    check("...and nor does an empty whitelist", plays_as(empty, "3840x2160", None), [])

    nuc = box(ids(*["7680x4320@" + r for r in ("60", "50", "25", "24", "23.97602")]),
              coreelec=False, pulldown=False, screen=(4096, 2160, 60.0),
              display=ids(*["4096x2160@" + r for r in ("60", "50", "25", "24", "23.976")],
                          *["3840x2160@" + r for r in ("60", "50", "25", "24", "23.976")]))
    check("an 8K entry the display no longer offers acts as its nearest mode, 4096x2160",
          [m[:2] for m in caps._whitelisted(nuc)], [(4096, 2160)] * 5)
    check("...so an odd width reaches 4096x2160 at its rate by the desktop step",
          plays_as(nuc, "3836x2072", 23.976), [])
    check("interlaced ids are dropped, 3D ids flagged",
          caps._modes_from_ids(["0192001080050.00000istd", "0192001080024.00000ptabfrp",
                                "0384002160060.00000pstd"]),
          [(1920, 1080, 24.0, True), (3840, 2160, 60.0, False)])
    caps._all_settings = lambda: [{"id": "videoscreen.whitelist", "options": [],
                                   "definition": {"options": [{"value": AM9_DISPLAY[0]}]}}]
    check("Kodi 22 nests the display's modes under the definition",
          caps._display_modes(), [(3840, 2160, 60.0, False)])
    check("the screen's rate comes off its label",
          caps._parse_hz("3840x2160 @ 23.98 Hz - Full screen"), 23.98)
    check("the width comes from the file's resolution",
          (caps.file_width({"resolution": "3840x2076"}), caps.file_width(None)), (3840, 0))

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
