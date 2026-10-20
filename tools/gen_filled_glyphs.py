"""Add filled glyphs to our Lucide icon font, as the Apple TV app draws a set mark.

Lucide is outlines only; app 2.1.0 shows Seen as a filled circle with the
check cut out and Hidden from suggestions as a filled thumbs-down. Both are
built from Lucide's own outlines: the holes are dropped, and the check is
turned into one. They go at U+F8E0 up, clear of Lucide's range.

Re-running replaces them. After a change, bump resource.font.tofa's version
and the plugin's minversion (tests/test_font_resource_addon.py checks both).
Dev-only (needs fontTools).  Usage:  python3 tools/gen_filled_glyphs.py
"""
import os

from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "resource.font.tofa", "resources", "tofa_lucide-icons.ttf")

#: (new codepoint, name, Lucide source codepoint, which contours to cut back out)
FILLED = (
    (0xF8E0, "tofa-circle-check-filled", 0xE226, "inner"),   # check-circle-2
    (0xF8E1, "tofa-thumbs-down-filled", 0xE189, None),       # thumbs-down
)


def _contours(font, name):
    """The glyph's contours as recorded pen calls, in glyf order."""
    rec = RecordingPen()
    font.getGlyphSet()[name].draw(rec)
    out, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def _points(contour):
    return [pt for _op, args in contour for pt in args if pt is not None]


def _inside(pt, poly) -> bool:
    x, y, inside = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _depths(contours):
    polys = [_points(c) for c in contours]
    return [sum(1 for j, other in enumerate(polys) if j != i and _inside(polys[i][0], other))
            for i in range(len(polys))]


def _build(font, source_name, cut):
    """Outer contours filled; with `cut`, the innermost ones become holes."""
    contours = _contours(font, source_name)
    depths = _depths(contours)
    pen = TTGlyphPen(font.getGlyphSet())
    for contour, depth in zip(contours, depths):
        if depth == 0:
            target = pen
        elif depth >= 2 and cut:
            target = ReverseContourPen(pen)
        else:
            continue
        for op, args in contour:
            getattr(target, op)(*args)
    return pen.glyph()


def main():
    font = TTFont(FONT)
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()
    for codepoint, name, source, cut in FILLED:
        glyph = _build(font, cmap[source], cut)
        if name not in order:
            order.append(name)
        font["glyf"][name] = glyph
        font["hmtx"][name] = font["hmtx"][cmap[source]]
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[codepoint] = name
        print("U+{0:04X} {1} from U+{2:04X}".format(codepoint, name, source))
    font.setGlyphOrder(order)
    font["maxp"].numGlyphs = len(order)
    font.save(FONT)


if __name__ == "__main__":
    main()
