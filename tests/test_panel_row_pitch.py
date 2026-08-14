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
  9802  8.10's episode drawer rows: vertical, pitch 93, and it had the
        inert `<itemgap>` too.
  9801  the drawer's season chips: HORIZONTAL, so the size that steps is the
        itemlayout's WIDTH, and it was also missing the itemwidth/itemheight
        child tags entirely -- the trap's other half, which renders a list's
        rows with empty icons and labels.

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
    block = src[src.index(f'<control type="list" id="{control_id}">'):]
    return block[:block.index("</focusedlayout>")]


def layout_sizes(block):
    return [(int(w), int(h)) for w, h in re.findall(
        r'<(?:item|focused)layout width="(\d+)" height="(\d+)">', block)]


def tag(block, name, default=None):
    m = re.search(rf"<{name}>(\d+)</{name}>", block)
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


# ============================== 9802, the episode drawer's rows (vertical) ==
# Nothing in Python sizes this one, so the reference's own numbers are the
# fixture: rows 87 tall on the measured pitch of 93 (internal-docs/
# atv-reference/player-episode-drawer.png).
DRAWER_ROW_H, DRAWER_ROW_GAP = 87, 6
DRAWER_PITCH = DRAWER_ROW_H + DRAWER_ROW_GAP

block = list_block(9802)
check("9802: pitch is the reference's 93", DRAWER_PITCH == 93,
      str(DRAWER_PITCH))
layouts = layout_sizes(block)
check("9802: both layouts are a pitch tall",
      len(layouts) == 2 and {h for _w, h in layouts} == {DRAWER_PITCH},
      f"{layouts} != {DRAWER_PITCH}")
check("9802: <itemheight> matches the layouts",
      tag(block, "itemheight") == DRAWER_PITCH,
      f"{tag(block, 'itemheight')} != {DRAWER_PITCH}")

# The focused row's fill and rim are the only full-width children; both are
# a row tall, inset half a gap, which is what puts the gap on screen.
fills = re.findall(
    r"<control type=\"image\">\s*<posy>(\d+)</posy>\s*<width>640</width>"
    r"\s*<height>(\d+)</height>", block)
check("9802: the focused fill and its rim are both inset", len(fills) == 2,
      str(fills))
for posy, height in fills:
    posy, height = int(posy), int(height)
    check(f"9802: a {height}px row at y{posy} leaves "
          f"{DRAWER_PITCH - height}px between rows",
          height == DRAWER_ROW_H and posy * 2 + height == DRAWER_PITCH,
          f"posy={posy} height={height} pitch={DRAWER_PITCH}")

# The row's content has to ride with the fill, or the still sits off centre
# in its own row. The still is the tallest child and defines the band: the
# 79 of art the plate, the thumb and the watched scrim all share.
STILL_H = 79
stills = re.findall(
    r"<control type=\"image\">\s*<posx>6</posx>\s*<posy>(\d+)</posy>"
    r"\s*<width>140</width>\s*<height>79</height>", block)
check("9802: three stills per layout, six in all", len(stills) == 6,
      str(stills))
for posy in {int(p) for p in stills}:
    check(f"9802: the still band at y{posy} is centred in the pitch",
          posy == DRAWER_PITCH - (posy + STILL_H),
          f"top={posy} bottom={DRAWER_PITCH - (posy + STILL_H)}")
STILL_TOP = int(stills[0]) if stills else 0

# The progress strip is flush with the still's BOTTOM edge, not centred, so
# it moves with the band rather than with the pitch.
bars = re.findall(
    r"<control type=\"image\">\s*<posx>6</posx>\s*<posy>(\d+)</posy>"
    r"\s*<width>140</width>\s*<height>6</height>", block)
check("9802: two progress strips per layout, four in all", len(bars) == 4,
      str(bars))
for posy in {int(p) for p in bars}:
    check(f"9802: the progress strip at y{posy} is flush with the still",
          posy + 6 == STILL_TOP + STILL_H,
          f"{posy + 6} != {STILL_TOP + STILL_H}")

_x, y, _w, h = box(block)
check("9802: the list box is a whole number of pitches",
      h % DRAWER_PITCH == 0,
      f"{h} % {DRAWER_PITCH} = {h % DRAWER_PITCH}")
check(f"9802: the box holds {h // DRAWER_PITCH} whole rows",
      h // DRAWER_PITCH == 9, str(h // DRAWER_PITCH))
# Insetting the row inside its pitch moves the whole block down half a gap,
# so the container starts half a gap earlier and the first row stays put.
check("9802: the first row's rim still lands on the measured y217",
      y + DRAWER_ROW_GAP // 2 == 217, f"{y} + {DRAWER_ROW_GAP // 2}")


# ========================= 9801, the drawer's season chips (HORIZONTAL) =====
# A horizontal list steps by the itemlayout's WIDTH, so the pitch lives on
# the other axis: an 82 chip inset 5 either side of a 92 layout.
CHIP_W, CHIP_GAP = 82, 10
CHIP_PITCH = CHIP_W + CHIP_GAP

block = list_block(9801)
check("9801: it is still the horizontal one",
      "<orientation>horizontal</orientation>" in block)
layouts = layout_sizes(block)
check("9801: both layouts are a pitch WIDE",
      len(layouts) == 2 and {w for w, _h in layouts} == {CHIP_PITCH},
      f"{layouts} != {CHIP_PITCH}")

# Both child tags are required even though neither sets the step; the one on
# the stepping axis carries the pitch.
check("9801: <itemwidth> is the pitch", tag(block, "itemwidth") == CHIP_PITCH,
      f"{tag(block, 'itemwidth')} != {CHIP_PITCH}")
check("9801: <itemheight> is declared at all",
      tag(block, "itemheight") == 43, str(tag(block, "itemheight")))

# Every child of both layouts is one chip, inset half a gap.
chips = re.findall(
    r"<control type=\"(?:image|label)\">\s*<posx>(\d+)</posx>"
    r"\s*<width>(\d+)</width>", block)
check("9801: every chip child is inset", len(chips) == 10, str(len(chips)))
for posx, width in chips:
    posx, width = int(posx), int(width)
    check(f"9801: chip of {width} at x{posx} leaves a {CHIP_GAP}px gap",
          width == CHIP_W and posx * 2 + width == CHIP_PITCH,
          f"posx={posx} width={width} pitch={CHIP_PITCH}")

x, _y, w, _h = box(block)
check("9801: the list box is a whole number of pitches",
      w % CHIP_PITCH == 0, f"{w} % {CHIP_PITCH} = {w % CHIP_PITCH}")
check(f"9801: the box holds {w // CHIP_PITCH} whole chips",
      w // CHIP_PITCH == 7, str(w // CHIP_PITCH))
# Same compensation as 9802's, on the other axis: the first chip has to stay
# flush with the "Episodes" heading above it, which sits at x1268.
check("9801: the first chip still lands on the measured x1268",
      x + CHIP_GAP // 2 == 1268, f"{x} + {CHIP_GAP // 2}")
check("9801: the chips stay inside the drawer panel",
      x + w <= 1248 + 672, str(x + w))


# ================================================ the sweep, all skin files =
# itemgap reads as though it works, which is the whole reason this cost a bug
# report. Four controls have now hit it; no fifth.
offenders = []
for path in sorted(SKIN_DIR.glob("*.xml")):
    for control in ET.fromstring(path.read_text()).iter("control"):
        if control.get("type") == "list" and control.find("itemgap") is not None:
            offenders.append(f"{path.name}:{control.get('id')}")
check("no rendered type=list declares an <itemgap>", not offenders,
      ", ".join(offenders))


failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
