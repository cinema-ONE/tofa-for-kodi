"""Every Conditional fade in the rendered skin names its start alpha.

Kodi leaves a reversed Conditional animation APPLIED at its start value, and a
fade's default start is 0: one without `start` hides its control for good once
the condition has been true (Discover's sub-tabs after Coming Up, 1.3.0-1.4.0).

Run:  python3 test_conditional_fades.py
"""
import glob
import os
import re

SKIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "plugin.video.tofa", "resources", "skins", "Main", "1080i", "*.xml")
FADE = re.compile(r'<animation\b[^>]*effect="fade"[^>]*>Conditional</animation>')

missing = [(os.path.basename(path), tag) for path in sorted(glob.glob(SKIN))
           for tag in FADE.findall(open(path, encoding="utf-8").read()) if "start=" not in tag]
total = sum(len(FADE.findall(open(p, encoding="utf-8").read())) for p in glob.glob(SKIN))
for name, tag in missing:
    print("FAIL  %s: %s" % (name, tag))
print("%d Conditional fade(s), %d without a start" % (total, len(missing)))
raise SystemExit(1 if missing or not total else 0)
