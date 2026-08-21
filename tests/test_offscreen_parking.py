"""Nothing may be hidden by parking it off-screen -- Kodi's zoom shows it.

Reported 2026-08-19 from the cinema box: "a white tick left of the scrub bar,
only visible if zoom is < 100%". Kodi's GUI zoom (lookandfeel.skinzoom,
-30%..+30%) scales the whole skin about the CENTRE, so below 100% the visible
skin area grows past the 1920x1080 frame -- at -30% it runs -411..2331 across
and -231..1311 down. Anything parked just outside comes back on screen.

What was parked there: the scrub marker pool. `_hide_marker()` moved unused
ticks to x=-50 instead of hiding them, on the reasoning that a static
`<visible>false</visible>` is a CONDITION Kodi re-evaluates, so setVisible(True)
could never win against it. True of the tag -- but these controls carry no tag,
so the Python call stands. 40 chapter ticks at 35% white plus the unused amber
segment ticks, stacked on one spot, read as a solid nick in the letterbox.

Reproduced locally at zoom -10%: skin x=-50 lands at 960 + (-50-960)*0.9 = 51,
and the tick was drawn at x=52.

Two halves, because the bug has two halves:

  1. the RUNTIME one -- _hide_marker must hide, not move. A static scan cannot
     see this: the XML places the pool at posx=20, on screen.
  2. the STATIC one -- no control that actually paints may sit entirely
     outside the frame in the rendered XML.

Run:  python3 test_offscreen_parking.py
"""
import glob
import os
import xml.etree.ElementTree as ET

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

W, H = 1920, 1080
#: The skin area Kodi shows at minimum zoom, per the arithmetic above.
ZOOM_MIN = 0.70
VIS_X, VIS_Y = 960 / ZOOM_MIN, 540 / ZOOM_MIN
SKINS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "plugin.video.tofa", "resources", "skins", "Main", "1080i")
#: Controls whose children are positioned relative to them.
CONTAINERS = {"group", "grouplist", "panel", "list", "fixedlist", "wraplist",
              "scrollbar", "togglebutton"}

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


# --- 1. the runtime half ---------------------------------------------------

class FakeControl:
    def __init__(self):
        self.positions = []
        self.visible = None

    def setPosition(self, x, y):
        self.positions.append((x, y))

    def setVisible(self, value):
        self.visible = value

    def setWidth(self, value):
        pass


class FakeWindow:
    def __init__(self):
        self.control = FakeControl()

    def getControl(self, _cid):
        return self.control


win = FakeWindow()
PlayerWindow._hide_marker(win, 9820)
check("_hide_marker hides the control", win.control.visible is False,
      "setVisible was called with %r" % (win.control.visible,))
check("_hide_marker does NOT move it off-screen", not win.control.positions,
      "moved to %r" % (win.control.positions,))


# --- 2. the static half ----------------------------------------------------

def num(control, tag, default=0):
    node = control.find(tag)
    if node is None or not (node.text or "").strip():
        return default
    try:
        return int(float(node.text.strip()))
    except ValueError:
        return None


def paints(control):
    """Would this control put anything on the screen at all?

    An empty label paints nothing, which is what the animation rig (control
    666, a 1x1 label at -100,-100 in every window) relies on.
    """
    kind = control.get("type") or ""
    if kind == "label":
        return bool((control.findtext("label") or "").strip())
    if kind in ("image", "button", "togglebutton", "progress", "textbox"):
        return True
    return kind not in CONTAINERS


def walk(control, ox, oy, out):
    x, y = num(control, "posx"), num(control, "posy")
    if x is None or y is None:
        return
    ax, ay = ox + x, oy + y
    kids = control.findall("control")
    if kids and (control.get("type") or "") in CONTAINERS:
        for kid in kids:
            walk(kid, ax, ay, out)
        return
    w, h = num(control, "width", 0) or 0, num(control, "height", 0) or 0
    out.append((ax, ay, w, h, control))


parked = []
for path in sorted(glob.glob(os.path.join(SKINS, "*.xml"))):
    controls = ET.parse(path).getroot().find("controls")
    if controls is None:
        continue
    found = []
    for control in controls.findall("control"):
        walk(control, 0, 0, found)
    for ax, ay, w, h, control in found:
        wholly_out = ax + w <= 0 or ay + h <= 0 or ax >= W or ay >= H
        revealed = (ax + w > 960 - VIS_X and ax < 960 + VIS_X
                    and ay + h > 540 - VIS_Y and ay < 540 + VIS_Y)
        if wholly_out and revealed and paints(control):
            parked.append("%s: %s#%s at (%d,%d) %dx%d"
                          % (os.path.basename(path), control.get("type"),
                             control.get("id") or "-", ax, ay, w, h))

check("no painting control sits entirely outside the frame", not parked,
      "; ".join(parked[:4]))
check("the scan actually walked the rendered windows",
      len(glob.glob(os.path.join(SKINS, "*.xml"))) >= 14)

print("")
failed = [n for n, ok in RESULTS if not ok]
print("off-screen parking: nothing hides where Kodi's zoom would show it "
      "(%d checks)" % len(RESULTS))
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
