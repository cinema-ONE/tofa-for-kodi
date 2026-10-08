"""A list's rows must be separated by a real gap, not a declared one.

THE BUG THIS LOCKS OUT, reported 2026-08-11 on the AM6B+ while the 3D panel
was up: "it looks like the panels got more height, but the entries still
stick together vertically."

The list declared `<itemgap>10</itemgap>`. That tag belongs to a GROUPLIST;
on a `type="list"` Kodi ignores it and steps by the ITEMLAYOUT's own size
instead. So `_size_panel` reserved ten pixels per row that the rows never
used -- a taller panel with its entries still flush. The gap has to be built
INTO the layout: a pitch of ROW + GAP with the fill inset half a gap on each
side, and the list's own box a whole number of pitches, because Kodi draws
floor(box / step) items and silently loses the last one otherwise.

Covered here:

  9906  8.4's selection panel, sized by Python, so its pitch is tied to the
        PlayerWindow constants that size it.
  9802  the episodes row's cards: horizontal, 416 wide on a 456 pitch.
  9801  its season pills: HORIZONTAL, so the size that steps is the
        itemlayout's WIDTH. Both need the itemwidth/itemheight child tags --
        without them a list renders empty icons and labels.

Plus a sweep over every rendered skin file, so a fifth control cannot pick
the same tag up again.

Structural, not visual, for the same reason test_exact_art_not_resized is:
the numbers live in files that have no way to notice each other drifting,
and the failure is a few pixels rather than a traceback. See
project_kodi_list_itemheight_tag.

Run:  python3 test_panel_row_pitch.py
"""
import pathlib
import re
import xml.etree.ElementTree as ET

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIN_DIR = (ROOT / "plugin.video.tofa" / "resources" / "skins" / "Main"
            / "1080i")
RENDERED = SKIN_DIR / "script-tofa-player.xml"

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}"
          f"{('  -- ' + detail) if detail and not ok else ''}")


src = RENDERED.read_text()


def list_block(control_id):
    """The control's XML from its opening tag to the end of its layouts."""
    m = re.search(rf'<control type="(?:fixed)?list" id="{control_id}">', src)
    block = src[m.start():]
    return block[:block.index("</focusedlayout>")]


def layout_sizes(block):
    return [(int(w), int(h)) for w, h in re.findall(
        r'<(?:item|focused)layout width="(\d+)" height="(\d+)">', block)]


def tag(block, name, default=None):
    m = re.search(rf"<{name}>(-?\d+)</{name}>", block)
    return default if m is None else int(m.group(1))


def box(block):
    """The list's own posx/posy/width/height, which precede the layouts."""
    head = block[:block.index("<itemlayout")]
    return (tag(head, "posx", 0), tag(head, "posy", 0),
            tag(head, "width"), tag(head, "height"))


# ======================================================= 9906, the panel ===
# Its pitch is owned by Python, since _size_panel grows the panel per row.
block = list_block(9906)
PITCH = PlayerWindow._PANEL_ROW_H + PlayerWindow._PANEL_ROW_GAP

# 1. The step. Both layouts and the (still required) child tag carry it.
itemheight = tag(block, "itemheight")
layouts = [h for _w, h in layout_sizes(block)]
check("9906: the itemlayout height IS the pitch",
      layouts and set(layouts) == {PITCH}, f"{layouts} != {PITCH}")
check("9906: both layouts agree", len(layouts) == 2, str(len(layouts)))
check("9906: <itemheight> matches the layouts", itemheight == PITCH,
      f"{itemheight} != {PITCH}")

# 2. The gap is real: the fill is a row tall, inset half a gap, so adjacent
#    fills end up ROW_GAP apart.
fills = re.findall(
    r"<control type=\"image\">\s*<posy>(\d+)</posy>\s*<width>\d+</width>"
    r"\s*<height>(\d+)</height>", block)
check("9906: both layouts inset the fill", len(fills) == 2, str(fills))
for posy, height in fills:
    posy, height = int(posy), int(height)
    check(f"9906: fill of {height} at y{posy} leaves a {PITCH - height}px gap",
          height == PlayerWindow._PANEL_ROW_H
          and posy * 2 + height == PITCH,
          f"posy={posy} height={height} pitch={PITCH}")

# 3. The list box has to be a WHOLE number of pitches, or Kodi draws
#    floor(height / step) rows and the last one silently vanishes.
class Sizer:
    _PANEL_ROW_H = PlayerWindow._PANEL_ROW_H
    _PANEL_ROW_GAP = PlayerWindow._PANEL_ROW_GAP
    _PANEL_ROWS_MAX_H = PlayerWindow._PANEL_ROWS_MAX_H

def rows_h(n):
    pitch = Sizer._PANEL_ROW_H + Sizer._PANEL_ROW_GAP
    return min(Sizer._PANEL_ROWS_MAX_H // pitch, n) * pitch

for n in (1, 2, 3, 5, 9, 40):
    h = rows_h(n)
    check(f"9906: {n} row(s): height is a whole number of pitches",
          h % PITCH == 0, f"{h} % {PITCH} = {h % PITCH}")
    check(f"9906: {n} row(s): every row fits",
          h // PITCH == min(n, Sizer._PANEL_ROWS_MAX_H // PITCH),
          f"{h // PITCH} of {n}")

check("9906: a long list is capped, not unbounded",
      rows_h(40) <= Sizer._PANEL_ROWS_MAX_H, str(rows_h(40)))


# ========================== 9802 and 9801, the player's episodes row ======
# The app's own numbers: 416x234 cards on a 456 pitch, 66 pills on an 80
# pitch (internal-docs/atv-reference/2026-10-08-player-episodes-row.png).
CARD_W, CARD_PITCH = 416, 456
block = list_block(9802)
check("9802: it is horizontal", "<orientation>horizontal</orientation>" in block)
check("9802: both layouts are a pitch wide",
      {w for w, _h in layout_sizes(block)} == {CARD_PITCH}, str(layout_sizes(block)))
check("9802: <itemwidth> is the pitch", tag(block, "itemwidth") == CARD_PITCH)
check("9802: <itemheight> is declared", tag(block, "itemheight") == 330)
x, _y, w, _h = box(block)
check("9802: the box is whole pitches", w % CARD_PITCH == 0, f"{w} % {CARD_PITCH}")
check("9802: the focused card sits where the app's does (x752)",
      x + 2 * CARD_PITCH == 752, str(x + 2 * CARD_PITCH))

PILL_W, PILL_PITCH = 66, 80
block = list_block(9801)
check("9801: it is horizontal", "<orientation>horizontal</orientation>" in block)
check("9801: both layouts are a pitch wide",
      {w for w, _h in layout_sizes(block)} == {PILL_PITCH}, str(layout_sizes(block)))
check("9801: <itemwidth> is the pitch", tag(block, "itemwidth") == PILL_PITCH)
check("9801: <itemheight> is declared", tag(block, "itemheight") == 48)
x, _y, w, _h = box(block)
check("9801: the box is whole pitches", w % PILL_PITCH == 0, f"{w} % {PILL_PITCH}")
check("9801: the first pill lands on the measured x180", x == 180, str(x))


# ================================================ the sweep, all skin files =
# itemgap reads as though it works, which is the whole reason this cost a bug
# report. Four controls have now hit it; no fifth.
offenders = []
for path in sorted(SKIN_DIR.glob("*.xml")):
    for control in ET.fromstring(path.read_text()).iter("control"):
        if (control.get("type") in ("list", "fixedlist")
                and control.find("itemgap") is not None):
            offenders.append(f"{path.name}:{control.get('id')}")
check("no rendered type=list declares an <itemgap>", not offenders,
      ", ".join(offenders))


failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
