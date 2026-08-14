"""The edition pill says a NAME or a short resolution -- never raw pixels.

The bug this guards, seen while taking the add-on's screenshots: a title
with two files and no edition names put `1920x1080` in a pill laid out for
"1080p", and Kodi clipped it to "192...". A label that says less than
nothing, two lines under a format badge already reading "1080p".

The fallback chain reached `file.resolution`, which is raw dimensions. The
badge beside it has always derived "4K"/"1080p" from the height instead, and
the pill now shares that derivation, so the two agree by construction.

Measured against the reference library (2026-08-14), which is why the pill
carries names at all: of six multi-edition titles, five have BOTH editions
at the same resolution -- "1408" is 2160 twice, "1941" 1080 twice -- so a
resolution token would print the same word on both rows and answer nothing.
Names are what the viewer is choosing between:

    Theatrical Cut / Director's Cut / Extended Cut / Special Edition
    Illusion-O Version / Black and White Version / Color Version
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows.detail import DetailWindow  # noqa: E402
from lib.skin import fragments as F  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def label(**file_fields):
    return DetailWindow._version_pill_label(file_fields)


def main() -> int:
    # --- what the pill says -------------------------------------------
    check("a named edition wins outright",
          label(edition="Director's Cut", height=2160,
                format={"resolution_label": "4K"}) == "Director's Cut")
    check("the server's own short label is next",
          label(height=1080, format={"resolution_label": "1080p"}) == "1080p")
    check("then the SAME derivation the format badge uses",
          label(height=1080, format={}) == "1080p")
    check("...which gives 4K above 2000",
          label(height=2160, format={}) == "4K")
    check("...and 720p for a smaller file",
          label(height=720, format={}) == "720p")
    check("nothing at all still says something",
          label(format={}) == "Version")

    # The actual regression: raw dimensions must never reach the pill, no
    # matter what else the file carries.
    for res in ("1920x1080", "4000x2250", "3840x1600"):
        got = label(resolution=res, format={})
        check("%r never reaches the pill" % res, res not in got, got)
    check("a file with ONLY raw dimensions falls through to Version",
          label(resolution="1920x1080", format={}) == "Version")
    check("...and with a height, to the derived token",
          label(resolution="4000x2250", height=2250, format={}) == "4K")

    # --- anchored, not centred as a group ------------------------------
    # Every pill puts its icon at the same inset and its chevron at the same
    # one, so the icons line up down the row. They did not: centring each
    # group put them at 75, 88, 84, 26 and 45.
    geo = {name: F.action_pill_layout(w, trailing=t) for name, w, t in [
        ("primary", 360, False), ("options", F.ACTION_PILL_W, True),
        ("rewatch", F.ACTION_PILL_W, False), ("watchlist", F.ACTION_PILL_W, False),
        ("edition", F.ACTION_PILL_W, True)]}
    check("every icon sits at the same inset",
          len({g[0] for g in geo.values()}) == 1,
          str({n: g[0] for n, g in geo.items()}))
    check("every label starts at the same x",
          len({g[1] for g in geo.values()}) == 1,
          str({n: g[1] for n, g in geo.items()}))
    check("the chevron is pinned to the right inset, not to the text",
          geo["options"][3] == F.ACTION_PILL_W - F.ACTION_PILL_INSET - F.ACTION_ICON_W)
    # Tighter than the app's measured 40, and deliberately: 40 in its
    # 258-wide pill is 15% of it, and the same 40 in our 325 leaves the icon
    # marooned. It also buys the symmetric box the 32px "Cancel request"
    # needs.
    check("the inset is tighter than the app's 40", F.ACTION_PILL_INSET < 40,
          str(F.ACTION_PILL_INSET))
    check("a chevron does not cost the label any room",
          geo["options"][2] == geo["watchlist"][2],
          "%d vs %d" % (geo["options"][2], geo["watchlist"][2]))
    check("...and the chevron still clears the label box",
          geo["options"][1] + geo["options"][2] <= geo["options"][3],
          "label ends %d, chevron at %d"
          % (geo["options"][1] + geo["options"][2], geo["options"][3]))
    check("the label box holds the edition pattern that repeats",
          geo["edition"][2] >= 168, "label box %d" % geo["edition"][2])
    check("nothing overhangs the pill",
          all(g[1] + g[2] <= (360 if n == "primary" else F.ACTION_PILL_W)
              for n, g in geo.items()))

    # --- one width for every pill but the primary ----------------------
    PRIMARY = 5210
    widths = {pid: entry[1] for pid, entry in DetailWindow.PILL_LAYOUT.items()}
    others = {pid: w for pid, w in widths.items() if pid != PRIMARY}
    check("the primary pill keeps its own width", widths[PRIMARY] == 360,
          str(widths[PRIMARY]))
    check("every other pill shares one width",
          set(others.values()) == {F.ACTION_PILL_W}, str(others))
    check("and one gap",
          {e[2] for p, e in DetailWindow.PILL_LAYOUT.items() if p != PRIMARY}
          == {F.ACTION_PILL_GAP})

    # The row has a hard right edge, and five pills is a real row: a watched
    # multi-edition title shows Resume, Edition, Options, Rewatch, Watchlist.
    # 330 apiece wanted 1747 of the 1740 there is, which is why it is 325.
    ORIGIN, MARGIN = 100, 80
    avail = 1920 - MARGIN - ORIGIN
    five = 360 + 4 * (F.ACTION_PILL_GAP + F.ACTION_PILL_W)
    check("all five pills fit the row", five <= avail,
          "needs %d, has %d" % (five, avail))
    check("...with the margin actually respected, not just reached",
          avail - five >= 10, "%d px spare" % (avail - five))

    # The picker is where the FULL name has to be readable without moving:
    # "Black and White Version" measures 270 in the row-title font.
    inner = F.EDITION_PANEL_W - 2 * F.PLAYOPT_PAD
    name_col = ((inner - 24 - F.EDITION_DETAIL_W)
                - (24 + F.PLAYOPT_CHECK_W + F.PLAYOPT_CHECK_GAP) - 16)
    check("the picker's name column holds the longest real edition name",
          name_col >= 270, "name column %d" % name_col)
    check("...without taking it from the detail column, which needs 555",
          F.EDITION_DETAIL_W >= 555, str(F.EDITION_DETAIL_W))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("edition pill: a name, or a short resolution, and room for it "
          "(%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
