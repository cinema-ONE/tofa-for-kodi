"""Generates the five shape primitives the skin builds everything else on.

WHY THIS FILE EXISTS AT ALL. These five were the last textures still shipped
byte-for-byte from plex-for-kodi -- a white fill, a 1px fill, a rounded fill
and its outline, and a transparent spacer. Nothing about them is authored:
they are the shapes their names describe, and every one is under 600 bytes.
Redrawing them costs nothing and lets the add-on's README stop crediting
someone else's project for a white square.

THE TWO ROUNDED ONES ARE NOT ARBITRARY. build.py's _EXACT_RECTS pins them at
radius 6 (stroke 5 for the outline), a number that was found by sweeping a
redrawn rounded rect against the old art until the corners matched, and that
76 exact-size textures are already drawn from. The old art's corner was not a
clean arc, so those exact textures had to carry a loosened tolerance to pass
gen_exact_assets.py's geometry check. Drawing the source as the arc the rest
of the pipeline assumes closes that gap instead of widening it -- run
gen_exact_assets.py after this and the drift it reports should be single
digits, not 20-45.

Supersampled and downsampled like every other shape tool here, so the arc has
the same antialiased band as the exact-size art it now agrees with.

Dev-only tool (needs Pillow). Output goes into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_primitive_assets.py
"""
import os

from PIL import Image, ImageDraw

S = 4                    # supersample factor
ROUND_SIZE = 100         # both rounded primitives, unchanged from the art
ROUND_RADIUS = 6         # build.py:_EXACT_RECTS
ROUND_STROKE = 5         # ditto, for the outline

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _rounded(stroke: int = 0) -> Image.Image:
    """A white rounded square at ROUND_SIZE, filled or stroked.

    Stroked from the FULL canvas box rather than a stroke/2 inset, the rule
    gen_exact_assets.py and gen_capsule_pill_assets.py both follow: PIL
    strokes inward, so an inset outline's silhouette drifts from the fill it
    is layered over."""
    n = ROUND_SIZE * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    box, radius = [0, 0, n - 1, n - 1], ROUND_RADIUS * S
    draw = ImageDraw.Draw(im)
    if stroke:
        draw.rounded_rectangle(box, radius=radius, outline=(255, 255, 255, 255),
                               width=stroke * S)
    else:
        draw.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 255))
    # LANCZOS, to match gen_exact_assets.py. These two are the SOURCE its
    # geometry check measures the 76 exact-size textures against, so the two
    # have to be antialiased the same way or the check is comparing filters
    # rather than shapes. A box filter reads as the better choice in
    # isolation -- it is a true area average, no ringing -- and it is the
    # wrong one here: its harder edge ramp (96/191/255 against LANCZOS's
    # 104/202/250) pushed exact-white-square-rounded-200x34 to 49/255, past
    # the allowance, at a call site that slices this art at border=2.
    #
    # What LANCZOS costs is ringing on the flat runs, 253/254 where 255 is
    # meant, which a 9-patch would then stretch across a whole control. So
    # snap the flat ends back and leave the arc's band alone.
    out = im.resize((ROUND_SIZE, ROUND_SIZE), Image.LANCZOS)
    r, g, b, a = out.split()
    return Image.merge("RGBA", (r.point(_snap), g.point(_snap), b.point(_snap),
                                a.point(_snap)))


def _snap(v: int) -> int:
    """Pull a channel that resampling left just short of flat back to flat."""
    return 255 if v >= 250 else (0 if v <= 5 else v)


def build() -> list[str]:
    written = []
    # A flat fill is scale-free -- Kodi stretches it to whatever the control
    # asks for -- so the only thing that matters is that it is white and
    # opaque. 10x10 and 1x1 both exist because two call sites ask for them by
    # name; there is no rendering difference between them.
    art = {
        "white-square.png": Image.new("RGB", (10, 10), (255, 255, 255)),
        "white-square-1px.png": Image.new("RGB", (1, 1), (255, 255, 255)),
        # A hole, not a shape: the texture a focusable control points at when
        # it must not draw a focus rect of its own.
        "transparent-6px.png": Image.new("LA", (6, 6), (0, 0)),
        "white-square-rounded.png": _rounded(),
        "white-outline-rounded.png": _rounded(stroke=ROUND_STROKE),
    }
    for name, im in art.items():
        path = os.path.join(_MEDIA_DIR, name)
        im.save(path, optimize=True)
        written.append(f"{name}  {im.size[0]}x{im.size[1]} {im.mode} "
                       f"{os.path.getsize(path)}B")
    return written


if __name__ == "__main__":
    for line in build():
        print("wrote", line)
