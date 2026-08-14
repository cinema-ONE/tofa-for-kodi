"""Exact-size art must never land on a control the add-on resizes.

THE BUG THIS LOCKS OUT, 2026-08-10, and not the first time it had been
chased. Exact-size art carries no `border`, so Kodi stretches the WHOLE
texture -- corners included -- to whatever size the control ends up at. The
player's 8.4 panel is authored 287x492 and `_size_panel()` sets it from 222
to 812 by row count, so its 20px corners were drawn as 20x9 on a two-row
panel and 20x31 on a nine-row one: unequal radii, inverted above six rows.

It was invisible to every test that drew the shape at its authored size,
which is why it survived so long. The check is therefore structural, not
visual: find the controls Python resizes, and refuse border-less art on them.

Run:  python3 test_exact_art_not_resized.py
"""
import importlib.util
import os
import pathlib
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.skin import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
RENDERED = ROOT / "plugin.video.tofa" / "resources" / "skins" / "Main" / "1080i"

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


spec = importlib.util.spec_from_file_location("cx", ROOT / "tools" / "check_xml.py")
cx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cx)

resized = cx._runtime_resized_ids()
check("the scanner finds controls that get resized", len(resized) > 5, str(len(resized)))
# The 8.4 panel's own three: shadow, fill, outline. If these ever drop out,
# the guard has stopped guarding the thing it was written for.
for cid, what in ((9901, "panel shadow"), (9902, "panel fill"), (9903, "panel outline")):
    check(f"{what} ({cid}) is seen as runtime-resized", cid in resized)

problems = cx._resized_exact_problems([str(p) for p in sorted(RENDERED.glob("*.xml"))])
check("no shipped screen puts exact art on a resized control",
      not problems, "; ".join(problems))

# ...and the guard actually fires. Feed it the exact fault that shipped.
fault = '''<control type="image" id="9902">
                <width>287</width>
                <height>492</height>
                <texture>exact-rounded-20-287x492.png</texture>
            </control>'''
tmp = RENDERED.parent / "_guard_selftest.xml"
tmp.write_text(fault)
try:
    fired = cx._resized_exact_problems([str(tmp)])
finally:
    os.unlink(tmp)
check("the guard fires on the fault that shipped", len(fired) == 1, str(fired))

# The renderer's half: a marked control keeps its nine-patch.
marked = f'''    <control type="image" id="4242">
        <!-- {build.RESIZED_MARKER} -->
        <width>287</width>
        <height>492</height>
        <texture border="20">rounded-20.png</texture>
    </control>'''
out, _stats = build._swap_exact_rects(marked)
check("a marked control keeps its border", 'border="20"' in out, out)

plain = marked.replace(f"<!-- {build.RESIZED_MARKER} -->\n        ", "")
check("...and the marker is what did it (control differs only by the marker)",
      plain != marked)

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
