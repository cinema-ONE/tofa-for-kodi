"""The card-options panel ends at its last row, as the app's menu does (2.1.0).

Run:  python3 test_cardoptions_fit.py
"""
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.skin import fragments as F, screens

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


pitch = F.OPTIONS_ROW_H + F.OPTIONS_ROW_GAP
four = F.cardoptions_geometry(4, eyebrow=False, subtitle=False)
six = F.cardoptions_geometry(6, eyebrow=False, subtitle=False)
check("two rows fewer, two pitches shorter", six["PANEL_H"] - four["PANEL_H"] == 2 * pitch,
      str((six["PANEL_H"], four["PANEL_H"])))
check("the panel stays centred", four["PANEL_Y"] == (1080 - four["PANEL_H"]) // 2)
check("no eyebrow: the title starts at the padding", four["TITLE_Y"] == F.OPTIONS_PAD)
check("no subtitle: rows start 62 under the title", four["ROWS_Y"] - four["TITLE_Y"] == 62)
full = F.cardoptions_geometry(6)
check("eyebrow and subtitle push the rows down",
      full["ROWS_Y"] > four["ROWS_Y"], str((full["ROWS_Y"], four["ROWS_Y"])))
check("the list is whole rows", four["ROWS_H"] == 4 * pitch)
check("more rows than the maximum are capped",
      F.cardoptions_geometry(9)["PANEL_H"] == full["PANEL_H"])

xml = screens.render_cardoptions()
m = re.search(r'id="202">\s*<posx>0</posx>\s*<posy>0</posy>\s*<width>\d+</width>\s*<height>(\d+)</height>', xml)
check("the XML is laid out for the tallest case",
      m is not None and int(m.group(1)) == full["PANEL_H"], m.group(1) if m else "no fill")
for control_id in ("200", "201", "202", "203", "204", "205"):
    check(f"control {control_id} exists for the runtime fit", f'id="{control_id}"' in xml)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
