"""Every id the settings pane navigates to must exist in the rendered XML.

RIGHT_TARGETS maps a sidebar page to the control Right lands on. Its own
comment says it "has been wrong once per new top group" -- and it went wrong
a second time when the segmented rows stopped being lists: "playback" still
pointed at 8470, the deleted Streaming quality list, so Right did nothing at
all on that page.

A stale id here is silent. Kodi does not complain, the pane simply refuses
to be entered, and it reads as the page being broken rather than one number
being wrong.

The same class of failure killed the Appearance chain: _settings_wire_
appearance_nav called getControl on the deleted rating list, which RAISED
and aborted the whole try block, so even foxes->spotlight went unwired and
Down from the fox grid did nothing.

Run:  python3 test_settings_nav_targets.py
"""
from __future__ import annotations
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import settings_pages, settings_options  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


XML = open(os.path.join(ROOT, "plugin.video.tofa", "resources", "skins",
                        "Main", "1080i", "script-tofa-main.xml")).read()
IDS = {int(i) for i in re.findall(r'id="(\d+)"', XML)}

missing = {page: cid for page, cid in settings_pages.RIGHT_TARGETS.items()
           if cid not in IDS}
check("every RIGHT_TARGETS id exists in the rendered window",
      not missing,
      "Right does nothing on these pages: %s" % missing)

seg_missing = [(k, i) for k, gid, sids, _p in settings_options.SEGMENTED_GROUPS
               for i in (gid,) + sids if i not in IDS]
check("every segmented group and pill id exists",
      not seg_missing, str(seg_missing))

# The pane is entered by Right, so a target that is not a segmented pill or
# a real row is worth a second look -- but the only hard rule is existence.
check("playback's target is one of Streaming quality's pills",
      settings_pages.RIGHT_TARGETS["playback"] in
      dict((k, s) for k, _g, s, _p in settings_options.SEGMENTED_GROUPS)["quality"],
      "entering the page should land on its FIRST row")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
