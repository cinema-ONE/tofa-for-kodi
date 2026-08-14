"""Builds the add-on's icon.png: the tofa fox on the brand canvas.

What Kodi shows in Settings > Add-ons and in its add-on grid is
plugin.video.tofa/icon.png, declared in addon.xml's <assets>. It shipped as
a placeholder -- a teal disc with a lowercase "t" -- which is not the tofa
mark.

Rendered from the SVG rather than scaled from a PNG, for the same reason
gen_logo_assets.py draws all 14 accent marks that way: the icon is 512px of a
drawing that is mostly edges, and upsampling any raster softens all of them.
`tofa UX/android-tv/logo-svgs/fox_tofa.svg` is the vector, and it is tofa's
own file, not a trace.

Kodi wants a square icon, 512x512 for a plugin. The mark is portrait
(527x632), so it sits on a field rather than being stretched -- the same
composition the placeholder used, on the app's own canvas colour so the icon
and the add-on agree.

Dev-only tool (needs Pillow + cairosvg). Run by hand:

    python3 tools/gen_addon_icon.py
"""
from __future__ import annotations

import io
import os
import sys

import cairosvg
from PIL import Image

_HERE = os.path.dirname(__file__)
# gen_logo_assets owns the question of WHERE the fox SVGs are -- this repo
# keeps them beside the APK captures, the public one has only the vectors.
# Importing it keeps one answer rather than two that can drift apart.
sys.path.insert(0, _HERE)
from gen_logo_assets import _SVG_DIR  # noqa: E402

_SVG = os.path.join(_SVG_DIR, "fox_tofa.svg")
_OUT = os.path.join(_HERE, "..", "plugin.video.tofa", "icon.png")

SIZE = 512
# tokens.py's CANVAS, the app's own page background, so the icon and the
# screens it launches are the same colour.
FIELD = (3, 11, 16)
# Fraction of the icon's height the mark occupies. 0.70 leaves a margin that
# survives Kodi drawing the icon small in a list and rounding its corners.
MARK_HEIGHT = 0.70


def main() -> None:
    mark_h = int(SIZE * MARK_HEIGHT)
    # Render at 2x and downsample: cairosvg's own antialiasing at the final
    # size leaves the thin outline strokes ragged.
    png = cairosvg.svg2png(url=os.path.abspath(_SVG), output_height=mark_h * 2)
    mark = Image.open(io.BytesIO(png)).convert("RGBA")
    mark = mark.resize((mark.width // 2, mark.height // 2), Image.LANCZOS)

    icon = Image.new("RGBA", (SIZE, SIZE), FIELD + (255,))
    icon.alpha_composite(
        mark, ((SIZE - mark.width) // 2, (SIZE - mark.height) // 2))
    icon.save(os.path.abspath(_OUT))
    print("saved {0} ({1}x{1}, mark {2}x{3})".format(
        os.path.relpath(_OUT, _HERE), SIZE, mark.width, mark.height))


if __name__ == "__main__":
    main()
