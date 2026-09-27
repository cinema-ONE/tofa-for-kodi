""""Plays as 1080p" only when Kodi will really show a file at 1080p.

Kodi matches a whitelisted mode on either axis, so a cropped 3840x2076
encode plays at 3840x2160. Matching on height alone sent it to the current
screen instead, and a box whose menus run at 1080p claimed "Plays as 1080p".

Run:  python3 test_plays_as_resolution.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities as caps

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


# A real whitelist: 2160p at every rate, 1080p only as 3D modes.
BOX_WHITELIST = [
    "0384002160060.00000pstd", "0384002160050.00000pstd",
    "0384002160024.00000pstd", "0384002160023.97602pstd",
    "0192001080024.00000ptabfrp", "0192001080023.97602ptabfrp",
]


def video_caps(whitelist, screen=(1920, 1080), switches=True):
    caps._setting = lambda sid: whitelist if sid == "videoscreen.whitelist" else None
    return {"known": True, "hdr_capable": True, "dolby_vision": True,
            "hdr10_plus": True, "modes": [], "refresh_rates": [],
            "whitelist_modes": caps._whitelist_modes(), "switches_modes": switches,
            "screen_width": screen[0], "screen_height": screen[1]}


def plays_as(vcaps, resolution, fps=None):
    width, height = (int(n) for n in resolution.split("x"))
    return caps.delivery({"video": {"dynamic_range": "sdr"}}, vcaps, {"known": False},
                         file_height=height, fps=fps, file_width=width)


def main():
    box = video_caps(BOX_WHITELIST)
    check("a full-frame 4K file needs no caveat", plays_as(box, "3840x2160", 23.976) == [])
    check("a cropped 4K file matches 2160p by its width",
          plays_as(box, "3840x2076", 24.0) == [], str(plays_as(box, "3840x2076", 24.0)))
    check("an odd-width one takes the closest size at its rate",
          plays_as(box, "3836x2072", 23.976) == [], str(plays_as(box, "3836x2072", 23.976)))
    check("...but without a rate we can't prove that, so the screen's mode stands",
          plays_as(box, "3836x2072") == ["1080p"])
    check("3D entries are never a 2D file's mode",
          all(m[1] == 2160 for m in box["whitelist_modes"]), str(box["whitelist_modes"]))

    only_3d = video_caps(["0192001080023.97602ptabfrp"], screen=(3840, 2160))
    check("...so a 3D-only 1080p entry doesn't downgrade a 4K file",
          plays_as(only_3d, "3840x2160", 23.976) == [])
    small = video_caps(["0192001080023.97602pstd"], screen=(3840, 2160))
    check("a 1080p-only whitelist does downgrade it",
          plays_as(small, "3840x2160", 23.976) == ["1080p"])
    fixed = video_caps(BOX_WHITELIST, switches=False)
    check("with switching off, the screen's mode is what plays",
          plays_as(fixed, "3840x2160", 23.976) == ["1080p"])

    check("the width comes from the file's resolution",
          caps.file_width({"resolution": "3840x2076"}) == 3840
          and caps.file_width({}) == 0 and caps.file_width(None) == 0)

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
