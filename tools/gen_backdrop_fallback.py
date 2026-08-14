"""The wash Detail shows when a title has no backdrop at all.

An item with no artwork (the whole "Videos" library is like this) leaves
Detail's full-bleed backdrop control with nothing to draw, so the window's
flat `backgroundcolor` shows through and the page reads as unfinished rather
than as sparse. The tofa apps put a soft diagonal wash there instead.

Sampled off the Android TV app's Detail for an artwork-less item. Mostly a
HORIZONTAL ramp -- dark left, bright right -- with a mild vertical dim:

    top-left      (16, 15, 18)        top-right     (66, 63, 72)
    bottom-left   (10,  9, 11)        bottom-right  (42, 40, 46)

Near-neutral with a faint violet cast (B > R > G).

Those corners are taken from y=20 and y=760, NOT from the frame's actual
corners. The first attempt sampled y=1020 and produced a wash whose centre
came out at (27, 25, 29) against a measured (39, 37, 43) -- because below
~y800 the app darkens further for the title and buttons. That is a text
scrim, a separate element, and folding it into the wash would have darkened
the whole image to compensate for something drawn on top of it anyway.

Deliberately small and NOT 2x. It is a smooth gradient stretched to full
screen, and scaling one costs nothing -- the same reasoning that keeps
splash-glow.png small (project_asset_scale_2x).

    python3 tools/gen_backdrop_fallback.py
"""
from __future__ import annotations

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "plugin.video.tofa", "resources", "skins", "Main", "media")
OUT = os.path.join(MEDIA, "detail-no-backdrop.png")

SIZE = (480, 270)

#: The poster placeholder is a different shape and a different wash: the macOS
#: app fills an artwork-less card with a blue-tinted RADIAL glow, brightest at
#: the centre, not the flat tile the TV apps use. Sampled off that app:
#: centre (35,68,85), corners about (18,34,50).
POSTER_OUT = os.path.join(MEDIA, "poster-placeholder.png")
POSTER_SIZE = (252, 378)
POSTER_CENTRE = (35, 68, 85)
POSTER_EDGE = (18, 34, 50)
TOP_LEFT = (16, 15, 18)
TOP_RIGHT = (66, 63, 72)
BOTTOM_LEFT = (10, 9, 11)
BOTTOM_RIGHT = (42, 40, 46)


def main() -> int:
    width, height = SIZE
    image = Image.new("RGB", SIZE)
    pixels = image.load()
    for y in range(height):
        fy = y / float(height - 1)
        left = [TOP_LEFT[i] + (BOTTOM_LEFT[i] - TOP_LEFT[i]) * fy for i in range(3)]
        right = [TOP_RIGHT[i] + (BOTTOM_RIGHT[i] - TOP_RIGHT[i]) * fy for i in range(3)]
        for x in range(width):
            fx = x / float(width - 1)
            pixels[x, y] = tuple(
                int(round(left[i] + (right[i] - left[i]) * fx)) for i in range(3))
    image.save(OUT)

    poster = Image.new("RGB", POSTER_SIZE)
    px = poster.load()
    pw, ph = POSTER_SIZE
    for y in range(ph):
        for x in range(pw):
            # Normalised radius from the centre; the corners sit at 1.0 so the
            # glow reaches the edge rather than banding before it.
            dx = (x - pw / 2.0) / (pw / 2.0)
            dy = (y - ph / 2.0) / (ph / 2.0)
            d = min(1.0, (dx * dx + dy * dy) ** 0.5 / (2 ** 0.5))
            px[x, y] = tuple(
                int(round(POSTER_CENTRE[i] + (POSTER_EDGE[i] - POSTER_CENTRE[i]) * d))
                for i in range(3))
    poster.save(POSTER_OUT)
    print("%s  %dx%d  centre %s" % (os.path.relpath(POSTER_OUT, ROOT), pw, ph,
                                    poster.getpixel((pw // 2, ph // 2))))

    centre = image.getpixel((width // 2, height // 2))
    print("%s  %dx%d  %.1f KB"
          % (os.path.relpath(OUT, ROOT), width, height,
             os.path.getsize(OUT) / 1024.0))
    print("centre %s (app measured (39, 37, 42))" % (centre,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
