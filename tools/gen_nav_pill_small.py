"""Generates nav-pill-small.png -- the smaller "active tab, focus moved
off the nav bar" pill background used by resources/lib/skin/fragments.py:
nav_bar()'s focusedlayout.

Deliberately not a nine-slice corner tile the way nav-pill.png is.
Reusing nav-pill.png's fixed 70x70/~30px-radius canvas at a smaller
height by lowering the <texture border="N"> value doesn't rescale the
curve -- border only picks how much of the source's fixed corner art to
use, so it crops an incomplete window of the same 30px arc, producing a
corner whose quarter-circle sweep never completes. Since the unfocused
pill's size is a fixed constant (not stretched to content), this instead
bakes a flat pill already at its exact final render size, radius correct
by construction, referenced with no border= in fragments.py.

White-on-transparent so Kodi's colordiffuse can tint it to the current
accent at runtime, same convention as nav-pill.png and the nav-*.png tab
icons.

RENDER_SCALE=3: the skin is authored at 1080i (WIDTH x HEIGHT = 188x44 is
that 1080i control size), but Kodi stretches the whole UI to the real
display resolution. Saving this asset at exactly 1080i size would force
Kodi to upscale an already-final-resolution image and blur on denser
screens; saving 3x oversampled means even 4K is downscaling a bigger
source. <width>/<height> in nav_bar() stay at 188x44; only the saved file
is bigger.

Dev-only tool, not shipped with the add-on and never imported by it (needs
Pillow, which Kodi's own Python environment doesn't have) -- run by hand
when this pill's size needs tweaking, output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_nav_pill_small.py
"""
import os

from PIL import Image, ImageDraw

S = 4  # extra supersample factor for anti-aliasing during the draw step
RENDER_SCALE = 3  # oversampling vs. the 1080i render size -- see docstring
WIDTH = 188   # 1080i render width (fragments.py's <width>)
HEIGHT = 44   # 1080i render height (fragments.py's <height>)

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def main() -> None:
    draw_w, draw_h = WIDTH * RENDER_SCALE * S, HEIGHT * RENDER_SCALE * S
    im = Image.new("RGBA", (draw_w, draw_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Full stadium: radius = half the height, same shape convention as
    # nav-pill.png's own 60-tall/30-radius pill.
    d.rounded_rectangle([0, 0, draw_w - 1, draw_h - 1], radius=draw_h // 2, fill="white")
    saved_w, saved_h = WIDTH * RENDER_SCALE, HEIGHT * RENDER_SCALE
    im = im.resize((saved_w, saved_h), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, "nav-pill-small.png")
    im.save(path)
    print("saved nav-pill-small.png", im.size, "for a {0}x{1} 1080i render target".format(WIDTH, HEIGHT))


if __name__ == "__main__":
    main()
