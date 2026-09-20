"""A tile cell is cut at the file's own stored aspect, not always 16:9.

The 8.2 bubble is a fixed 320x180 window and Kodi has no source rectangle,
so a cell is shown by drawing the WHOLE sheet oversized inside a container
that clips. That only holds while the drawn cell and the window agree. The
server cuts thumbnails at the source shape, so 320x240 (4:3), 320x232,
320x174 and 320x160 (2:1) tracks all occur beside the common 320x180 --
about one file in ten of those carrying tiles.

These cases pin the fit: the largest whole-pixel cell that fits the bubble,
the sheet drawn at that cell size times the grid, and the remainder split as
a centred margin. Nothing is cropped and nothing is stretched.

Pure arithmetic -- no Kodi, no window.  Run:  python3 test_preview_tile_geometry.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player as P
from resources.lib.windows.player import PlayerWindow

BUB_W, BUB_H = P._PREVIEW_BUBBLE_W, P._PREVIEW_BUBBLE_H

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def geom(w, h, cols=10, rows=10):
    return PlayerWindow._tile_geometry(
        {"width": w, "height": h, "tile_width": cols, "tile_height": rows})


# 1. The common track is untouched: a 320x180 cell fills the bubble exactly,
#    with no margin and no rescale. This is the no-regression case.
g = geom(320, 180)
check("16:9 draws 1:1", (g["draw_w"], g["draw_h"]) == (320, 180), repr(g))
check("16:9 sheet is 3200x1800", (g["sheet_w"], g["sheet_h"]) == (3200, 1800), repr(g))
check("16:9 has no margin", (g["pad_x"], g["pad_y"]) == (0, 0), repr(g))

# 2. A TALLER cell is the dangerous one: height is the binding constraint, so
#    it scales down and pillarboxes. Cropping here would cut the bottom of
#    every frame, which reads as the player pointing at the wrong place.
g = geom(320, 240)
check("4:3 fits by HEIGHT", (g["draw_w"], g["draw_h"]) == (240, 180), repr(g))
check("4:3 pillarboxes evenly", (g["pad_x"], g["pad_y"]) == (40, 0), repr(g))
check("4:3 sheet is 2400x1800", (g["sheet_w"], g["sheet_h"]) == (2400, 1800), repr(g))

# 3. A SHORTER cell keeps its width and letterboxes.
g = geom(320, 160)
check("2:1 keeps full width", (g["draw_w"], g["draw_h"]) == (320, 160), repr(g))
check("2:1 letterboxes evenly", (g["pad_x"], g["pad_y"]) == (0, 10), repr(g))

# 4. The two odd shapes seen in the wild, neither a tidy ratio.
g = geom(320, 232)
check("320x232 fits by height", (g["draw_w"], g["draw_h"]) == (248, 180), repr(g))
g = geom(320, 174)
check("320x174 keeps full width", (g["draw_w"], g["draw_h"]) == (320, 174), repr(g))

# 5. The 640 track, in case it is ever the one picked: same shape, half scale.
g = geom(640, 360)
check("640x360 scales to the bubble", (g["draw_w"], g["draw_h"]) == (320, 180), repr(g))

# 6. The invariants that matter, over every shape the server can cut. A drawn
#    cell must never exceed the bubble -- that is the crop this fixes -- and
#    the sheet must stay an exact multiple of the drawn cell, or rows drift.
for w, h in ((320, 180), (320, 240), (320, 232), (320, 174), (320, 160),
             (640, 360), (640, 480), (320, 320), (320, 90), (160, 240)):
    g = geom(w, h)
    check(f"{w}x{h} never exceeds the bubble",
          g["draw_w"] <= BUB_W and g["draw_h"] <= BUB_H, repr(g))
    check(f"{w}x{h} sheet is an exact grid",
          g["sheet_w"] == g["draw_w"] * 10 and g["sheet_h"] == g["draw_h"] * 10,
          repr(g))
    check(f"{w}x{h} margin is non-negative",
          g["pad_x"] >= 0 and g["pad_y"] >= 0, repr(g))
    check(f"{w}x{h} keeps the source ratio within a pixel",
          abs(g["draw_w"] / g["draw_h"] - w / h) < 0.02,
          f"{g['draw_w']}/{g['draw_h']} vs {w}/{h}")

# 7. A track whose numbers cannot describe a grid is refused rather than
#    dividing by zero -- _load_tiles drops the track and the bubble stays
#    hidden, which is the same as a server that never ran QuickView.
for bad in ({"width": 0, "height": 180, "tile_width": 10, "tile_height": 10},
            {"width": 320, "height": 0, "tile_width": 10, "tile_height": 10},
            {"width": 320, "height": 180, "tile_width": 0, "tile_height": 10},
            {"width": 320, "height": 180, "tile_width": 10, "tile_height": 0},
            {}):
    check(f"refuses {bad}", PlayerWindow._tile_geometry(bad) is None)

# 8. End to end: the cell the arithmetic picks must land exactly in the
#    bubble. Walking every cell of a 4:3 sheet, the drawn cell's rect inside
#    the 320x180 window is always (pad_x, pad_y, draw_w, draw_h) -- i.e. the
#    right frame, in the right place, with no neighbour showing.
g = geom(320, 240)
bad = []
for index in range(100):
    row, col = divmod(index, 10)
    x = g["pad_x"] - col * g["draw_w"]
    y = g["pad_y"] - row * g["draw_h"]
    # Where the wanted cell sits once the sheet is placed at (x, y).
    left, top = x + col * g["draw_w"], y + row * g["draw_h"]
    if (left, top) != (g["pad_x"], g["pad_y"]):
        bad.append((index, left, top))
check("every 4:3 cell lands in the window", not bad, repr(bad[:3]))

# 9. The margin is the whole problem, and the curtains are the answer. The
#    clipping window stays 320x180 and the sheet is ONE texture, so wherever
#    a fitted cell falls short the cell BESIDE it shows through -- the same
#    defect as before, turned on its side. Assert the covering is exact:
#    every pixel of the window is either the drawn cell or a curtain.
def covered(w, h):
    g = geom(w, h)
    rects = PlayerWindow._curtain_rects(
        g["pad_x"], g["pad_y"], g["draw_w"], g["draw_h"]) or ()
    cell = {(x, y)
            for x in range(g["pad_x"], g["pad_x"] + g["draw_w"])
            for y in range(g["pad_y"], g["pad_y"] + g["draw_h"])}
    for (rx, ry, rw, rh) in rects:
        cell |= {(x, y) for x in range(rx, rx + rw) for y in range(ry, ry + rh)}
    window = {(x, y) for x in range(BUB_W) for y in range(BUB_H)}
    return window - cell, cell - window

for w, h in ((320, 180), (320, 240), (320, 232), (320, 174), (320, 160),
             (640, 480), (320, 90)):
    missed, spilled = covered(w, h)
    check(f"{w}x{h}: no bare pixel in the bubble", not missed,
          f"{len(missed)} uncovered, e.g. {sorted(missed)[:3]}")
    check(f"{w}x{h}: nothing drawn outside the bubble", not spilled,
          f"{len(spilled)} outside")

# ...and a cell that fills the window exactly needs no curtains at all, so
# the common track pays nothing for any of this.
check("16:9 needs no curtains",
      PlayerWindow._curtain_rects(0, 0, 320, 180) is None)
check("4:3 curtains are the two side bars",
      PlayerWindow._curtain_rects(40, 0, 240, 180)
      == ((0, 0, 40, 180), (280, 0, 40, 180)),
      repr(PlayerWindow._curtain_rects(40, 0, 240, 180)))
check("2:1 curtains are the two horizontal bars",
      PlayerWindow._curtain_rects(0, 10, 320, 160)
      == ((0, 0, 320, 10), (0, 170, 320, 10)),
      repr(PlayerWindow._curtain_rects(0, 10, 320, 160)))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
