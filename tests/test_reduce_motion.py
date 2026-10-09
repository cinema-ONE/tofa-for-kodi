"""Reduce motion: every zoom, slide and drift runs only while motion is on.

skin/build.py gates each timed animation on Home's tofa_reduce_motion
property. Fades, instant layout animations and the loading spinner are left
alone; a Conditional move that places something gets an instant twin, so a
screen still lands where it should with motion off.

Run:  python3 test_reduce_motion.py
"""
from __future__ import annotations
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa"))

import kodi_stubs  # noqa: F401,E402
from resources.lib.skin import build  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


OK = build.MOTION_OK
gate = lambda xml: build._gate_motion(xml)[0]  # noqa: E731

lift = gate('<animation effect="zoom" start="100" end="108" time="140">Focus</animation>')
check("a focus lift needs motion", f'condition="{OK}"' in lift and "time=\"0\"" not in lift)
fade = '<animation effect="fade" start="0" end="100" time="140">Visible</animation>'
check("a fade is left alone", gate(fade) == fade)
instant = '<animation effect="zoom" end="69" time="0" condition="true">Conditional</animation>'
check("an instant layout zoom is left alone", gate(instant) == instant)
spin = '<animation effect="rotate" end="-360" time="1000" loop="true" condition="true">Conditional</animation>'
check("the spinner keeps turning", gate(spin) == spin)
drift = gate('<animation effect="slide" end="-100,0" time="9000" loop="true" condition="true">Conditional</animation>')
check("a drifting wall stops, with no twin", drift.count("<animation") == 1 and OK in drift)
place = gate('<animation effect="slide" end="0,-239" time="200" condition="A">Conditional</animation>')
check("a placing slide gets an instant twin",
      place.count("<animation") == 2 and f"[A] + {OK}" in place and f"[A] + !{OK}" in place
      and place.count('time="0"') == 1)
focus_zoom = gate('<animation effect="zoom" end="103" time="140" condition="Control.HasFocus(1)">Conditional</animation>')
check("a focus-keyed zoom is a lift: no twin", focus_zoom.count("<animation") == 1)

rendered = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(
    ROOT, "plugin.video.tofa", "resources", "skins", "Main", "1080i", "script-tofa-*.xml")))
ungated = [a for a in re.findall(r"<animation[^>]*>\w+</animation>", rendered)
           if 'effect="fade"' not in a and not re.search(r'time="0"|loop="true"', a)
           and "tofa_reduce_motion" not in a and 'effect="rotate"' not in a]
check("every timed move in the rendered skin is gated", not ungated, ungated[:2])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
