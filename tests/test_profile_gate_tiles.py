"""9.2's profile tiles as measured on the Apple TV app (2026-09-22).

At rest: a 1px hairline on the 220 portrait, and locked profiles carry a 75px
glass chip whose centre sits 71 right and 69 down from the portrait's, with a
lock about 35px tall. Focused: the portrait lifts 1.06 (233px against 220 at
rest), a 2px accent rim hugs it from outside (238px across, as measured), a
halo stays outside it, and the name stays white. Every one of the five
pre-centred lists must carry the same tile.

Run:  python3 test_profile_gate_tiles.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
XML = open(os.path.join(HERE, "..", "plugin.video.tofa", "resources", "skins", "Main",
                        "1080i", "script-tofa-profile.xml"), encoding="utf-8").read()
MEDIA = os.path.join(HERE, "..", "plugin.video.tofa", "resources", "skins", "Main", "media")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


lists = re.findall(r'<control type="list" id="80[0-4]">(.*?)</focusedlayout>', XML, re.S)
check("five pre-centred lists", len(lists) == 5, str(len(lists)))
for n, body in enumerate(lists, 1):
    rest, focused = body.split("<focusedlayout", 1)
    check("list %d at rest: hairline ring, no old outline" % n,
          "hairline-ring-220.png" in rest and "circle-outline.png" not in rest)
    for layout, text in (("rest", rest), ("focused", focused)):
        check("list %d %s: 75px lock chip at 167,152 with a 36px lock" % (n, layout),
              text.count("<posx>167</posx><posy>152</posy><width>75</width><height>75</height>") == 3
              and "tofa_font_icons_36" in text and "hairline-ring-75.png" in text)
    zooms = re.findall(r'effect="zoom" start="100" end="([\d.]+)" center="134,120"', focused)
    check("list %d focused: ten layers lift 1.06 about the portrait" % n,
          zooms == ["106"] * 10, repr(zooms))
    check("list %d focused: outside rim at 22,8 size 224, halo outside" % n,
          "<posx>22</posx><posy>8</posy><width>224</width><height>224</height>" in focused
          and "outer-rim-220.png" in focused and "ring-glow-220.png" in focused)
    name = re.search(r"<textcolor>([^<]*)</textcolor>\s*<label>\$INFO\[ListItem.Property\(name\)\]", focused)
    check("list %d focused: the name stays white" % n,
          bool(name) and "text_primary" in name.group(1), name and name.group(1))
for asset in ("hairline-ring-220.png", "hairline-ring-75.png", "outer-rim-220.png", "ring-glow-220.png"):
    check("asset %s exists" % asset, os.path.exists(os.path.join(MEDIA, asset)))


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("9.2's tiles as measured (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
