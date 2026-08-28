"""Generates the 9-patch capsule textures: one pair per pill HEIGHT.

THE RULE. Kodi draws a 9-patch's CORNERS UNSCALED -- only the edge and
middle strips stretch -- so the corner art's own radius IS the rendered
corner radius. A capsule of height N therefore needs an asset whose baked
radius equals the border it will be sliced at:

    capsule-h<N>.png   (N+2)x(N+2), corner radius N//2 + 1
    <texture border="N//2">capsule-h<N>.png</texture>

The +2 leaves a 2px straight band for the 9-patch to stretch, and it sits at
the equator where the edge is already vertical, so stretching or dropping it
costs nothing.

This replaced a single shared 80x80 texture whose docstring claimed it
worked "at border=height/2" for any height. That is false for every height
but 80, and it shipped visibly pinched capsule ends across the whole app:
5.3px off a true semicircle on Discover's 54px tab pills, 1.4-4.8px
elsewhere. Retired along with pill-fill/pill-outline and capsule-button.

Outlines are stroked from the FULL canvas box, never a stroke/2 inset: PIL
strokes inward, so an inset outline's silhouette diverges from the fill's by
~1/sin(angle) horizontally -- 3-5px at the cap extremes -- and the two get
layered on the same control.

verify() is the guard, not your eyes: it re-renders each asset the way Kodi
will and fails if the cap is more than 1px off a true semicircle. The old
shared texture measures 18.6px there. This error is invisible at 1x, which
is exactly why it survived so long.

Dev-only tool (needs Pillow). Output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_capsule_pill_assets.py
"""
import os

from PIL import Image, ImageDraw

S = 4  # supersample factor
CANVAS = 80
OUTLINE_STROKE = 2

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str) -> None:
    im = im.resize((CANVAS, CANVAS), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name)


def gen_height_capsule(height: int) -> None:
    """One exact-size stadium pair for pills of `height`, sliced at
    border=height//2. Radius is height//2 + 1 against a (height+2) canvas:
    the extra 2px is the straight band a 9-patch needs to stretch, and it
    lands at the equator where the edge is already vertical, so dropping or
    stretching it costs nothing. Measured best of the candidates."""
    b = height // 2
    size = height + 2
    radius = b + 1
    for name, outline in ((f"capsule-h{height}.png", False),
                          (f"capsule-h{height}-outline.png", True)):
        sz = size * S
        im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if outline:
            # Full canvas box, NOT the legacy stroke/2 inset: PIL strokes
            # inward from the given box, so this puts the outline's outer
            # edge exactly where the fill's is. They get layered on the same
            # pill, and an inset outline silhouette diverges from the fill's
            # by ~1/sin(angle) horizontally -- 4px at the cap extremes, where
            # the edge is nearly horizontal.
            d.rounded_rectangle(
                [0, 0, sz - 1, sz - 1], radius=radius * S,
                outline=(255, 255, 255, 255), width=OUTLINE_STROKE * S,
            )
        else:
            d.rounded_rectangle([0, 0, sz - 1, sz - 1], radius=radius * S,
                                fill=(255, 255, 255, 255))
        im = im.resize((size, size), Image.LANCZOS)
        im.save(os.path.join(_MEDIA_DIR, name))
        print(f"saved {name}  ({size}x{size}, radius {radius}, use border={b})")


def _ninepatch(src: Image.Image, w: int, h: int, b: int) -> Image.Image:
    """Kodi's 9-patch, reproduced: CORNERS ARE DRAWN UNSCALED, only the
    edge/middle strips stretch. That one fact is the whole trap this file
    guards against."""
    size = src.size[0]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mid_src, mid_w, mid_h = size - 2 * b, w - 2 * b, h - 2 * b
    cut = src.crop
    out.paste(cut((0, 0, b, b)), (0, 0))
    out.paste(cut((size - b, 0, size, b)), (w - b, 0))
    out.paste(cut((0, size - b, b, size)), (0, h - b))
    out.paste(cut((size - b, size - b, size, size)), (w - b, h - b))
    if mid_w > 0 and mid_src > 0:
        out.paste(cut((b, 0, size - b, b)).resize((mid_w, b)), (b, 0))
        out.paste(cut((b, size - b, size - b, size)).resize((mid_w, b)), (b, h - b))
    if mid_h > 0 and mid_src > 0:
        out.paste(cut((0, b, b, size - b)).resize((b, mid_h)), (0, b))
        out.paste(cut((size - b, b, size, size - b)).resize((b, mid_h)), (w - b, b))
    if mid_w > 0 and mid_h > 0 and mid_src > 0:
        out.paste(cut((b, b, size - b, size - b)).resize((mid_w, mid_h)), (b, b))
    return out


def _cap_deviation(img: Image.Image) -> tuple[float, float]:
    """(max, mean) px deviation of the rendered left cap from a true
    semicircle of radius height/2, read off the alpha channel's 50%
    crossing with sub-pixel interpolation."""
    import math

    alpha = img.split()[3]
    w, h = img.size
    px = list(alpha.getdata())
    r, yc, errs = h / 2.0, (h - 1) / 2.0, []
    for y in range(h):
        row = px[y * w:(y + 1) * w]
        idx = next((i for i, v in enumerate(row) if v > 127), None)
        if idx is None:
            continue
        if idx == 0:
            x = 0.0
        else:
            c0, c1 = row[idx - 1], row[idx]
            x = idx - 1 + ((127.5 - c0) / (c1 - c0) if c1 != c0 else 0.0)
        dy = y - yc
        if abs(dy) <= r - 0.5:
            errs.append(abs(x - (r - math.sqrt(max(r * r - dy * dy, 0)))))
    return (max(errs), sum(errs) / len(errs)) if errs else (0.0, 0.0)


# A cap this far off a true semicircle is invisible; anything worse is the
# bug this file exists to prevent (the old shared texture measured 5.1px).
_MAX_CAP_DEVIATION_PX = 1.0


def verify(height: int) -> None:
    """Fail loudly if a generated capsule doesn't render a round cap.

    Renders the asset the way Kodi will -- a wide pill at this height -- and
    measures the cap against a true semicircle. Do NOT replace this with
    looking at a screenshot: the 5.1px error in the old shared texture
    survived many screenshots precisely because it is invisible at 1x."""
    b = height // 2
    for name in (f"capsule-h{height}.png", f"capsule-h{height}-outline.png"):
        src = Image.open(os.path.join(_MEDIA_DIR, name)).convert("RGBA")
        mx, mean = _cap_deviation(_ninepatch(src, height * 2 + 56, height, b))
        status = "ok" if mx <= _MAX_CAP_DEVIATION_PX else "FAIL"
        print(f"  verify {name}: cap deviation max {mx:.2f}px mean {mean:.2f}px [{status}]")
        if mx > _MAX_CAP_DEVIATION_PX:
            raise SystemExit(
                f"{name} renders a cap {mx:.2f}px off a true semicircle "
                f"(limit {_MAX_CAP_DEVIATION_PX}px). The corner radius must "
                f"equal the border it is sliced at -- see this file's header."
            )


# Heights that have a dedicated capsule. Add one entry per new pill height,
# then point the caller at capsule-h<N>.png with border=N//2.
_HEIGHTS = (
    11,   # player scrubber track (§8.2's 11pt pill, measured 11px on tvOS)
    20,   # player scrubber groove behind the track
    24,   # episode card's unaired badge (§7.1's capsule; the real app's
          # measures ~22 tall, 24 is the nearest even height)
    28,   # card corner chips (drawn 28x28 = a true circle)
    38,   # player's stats pill (§8.11, measured 38px on the reference)
    43,   # episode drawer's season chips. Was borrowing capsule-h38 at
          # border=21 -- 21px taken from a 19px arc, which is the
          # radius!=border fault feedback_capsule_ninepatch_rule exists
          # to stop.
    42,   # focus ring AROUND a 38-high control: the settings segments and
          # the home-row switch, which are both 38. Drawn outside, on the
          # row surface, so no bright fill sits under its anti-aliased
          # edge. 38 + 2x2 because the stroke is 2 units wide, so a 2px pad
          # lands the ring's INNER edge flush on the control -- at 3 a
          # 1px line of row surface shows between the two.
    52,   # player transport buttons (drawn 52x52 = a true circle)
    54,   # Discover tab pills
    58,   # Browse's Sort/Filter/Quality/Genre pills
    60,   # nav bar's focused tab pill
    64,   # Detail's action row; picker's buttons
    66,   # sign-in's link pill
    68,   # nav bar panel; player's prominent play/pause ring (68x68 circle)
    72,   # player's bottom-right utility pill (52 button + 2x10 padding)
    76,   # sign-in / profile buttons
    78,   # Detail's action row (matches the reference app)
    88,   # player's bottom-left transport pill (68 play button + 2x10 padding)
)


if __name__ == "__main__":
    for _h in _HEIGHTS:
        gen_height_capsule(_h)
        verify(_h)
