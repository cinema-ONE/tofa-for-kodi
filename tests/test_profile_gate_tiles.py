"""Who's watching as the Apple TV app 2.0 draws it (captured 2026-10-09).

Three 220 portraits a row on a 311 pitch, one list per row (Python centres
each, so a short last row centres itself). At rest a 1px hairline; the
profile in use keeps a white ring; locked ones carry a 75px glass chip 143
right and 142 down from the portrait's corner. Focused: lifted 1.08 with an
accent rim and halo, but only while that row has focus, since a list draws
its selected item's focused layout even unfocused. No wash, no stars; Cancel
is a 112x64 pill. The PIN pad: 96 keys on a 116 pitch.

Run:  python3 test_profile_gate_tiles.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin.video.tofa"))
import kodi_stubs  # noqa: F401,E402

HERE = os.path.dirname(os.path.abspath(__file__))
XML = open(os.path.join(HERE, "..", "plugin.video.tofa", "resources", "skins", "Main",
                        "1080i", "script-tofa-profile.xml"), encoding="utf-8").read()
MEDIA = os.path.join(HERE, "..", "plugin.video.tofa", "resources", "skins", "Main", "media")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


lists = re.findall(r'<control type="list" id="(80[0-9])">(.*?)</focusedlayout>', XML, re.S)
check("three row lists, 800-802", [i for i, _ in lists] == ["800", "801", "802"], repr([i for i, _ in lists]))
for lid, body in lists:
    rest, focused = body.split("<focusedlayout", 1)
    check("row %s: 311-wide cells" % lid, 'itemlayout width="311"' in body)
    check("row %s at rest: 220 portrait at 45,10 with a hairline" % lid,
          "<posx>45</posx><posy>10</posy><width>220</width><height>220</height>" in rest
          and "hairline-ring-220.png" in rest)
    check("row %s: the signed-in ring at rest" % lid,
          "active-ring-220.png" in rest and "ListItem.Property(active)" in rest)
    check("row %s: lock chip at 188,152, 75 across" % lid,
          "<posx>188</posx><posy>152</posy><width>75</width><height>75</height>" in rest)
    check("row %s: preset art 150 at 80,45" % lid,
          "<posx>80</posx><posy>45</posy><width>150</width><height>150</height>" in rest)
    zooms = re.findall(r'effect="zoom" start="100" end="([\d.]+)" center="155,120"', focused)
    check("row %s focused: lifts 1.08 about the portrait" % lid,
          zooms and set(zooms) == {"108"}, repr(zooms))
    check("row %s focused: rim and halo only with the row's focus" % lid,
          "outer-rim-220.png" in focused and "ring-glow-220.png" in focused
          and "Control.HasFocus(%s)" % lid in focused and "!Control.HasFocus(%s)" % lid in focused)
check("no wash and no stars", "profile-wash.png" not in XML and "bg-stars.png" not in XML)
check("Cancel: a 112x64 pill at 904,940",
      "<posx>904</posx><posy>940</posy>" in XML and "<width>112</width><height>64</height>" in XML)
keys = re.findall(r"<posx>(\d+)</posx><posy>(\d+)</posy>\s*<visible>String.IsEqual\(Window.Property\(state\),pin\)",
                  XML)
check("eleven PIN keys on the 116 grid", len(keys) == 11
      and {k[0] for k in keys} == {"796", "912", "1028"}
      and {k[1] for k in keys} == {"367", "483", "599", "715"}, repr(keys))
for asset in ("hairline-ring-220.png", "hairline-ring-75.png", "outer-rim-220.png", "ring-glow-220.png",
              "active-ring-220.png"):
    check("asset %s exists" % asset, os.path.exists(os.path.join(MEDIA, asset)))


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("Who's watching as measured (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
