"""Generates the eight monogram discs -- the colour behind a profile's initials.

WHY THESE ARE TEXTURES AND NOT A TINT. Kodi's `colordiffuse` multiplies one
colour through a texture, which can tint `circle.png` flat but cannot draw a
two-stop gradient. tofa's disc is a 135-degree gradient, so the gradient has
to be baked: one file per palette entry, masked to the circle.

The palette and its ORDER are the contract (resources/lib/monogram.py says
why), so this tool reads them from there rather than carrying a copy. A
reordering there repaints the household; a reordering here would silently
disagree with the index the client computes.

Authored at DISC_PX, which is 2x the largest place the disc is drawn (the
180-unit profile tile), matching circle.png's own convention -- the nav
avatar and the settings row scale the same file down.

Dev-only tool (needs Pillow). Output goes into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_monogram_assets.py            generate what is missing
    python3 tools/gen_monogram_assets.py --force    redraw everything
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugin.video.tofa", "resources"))
from lib import monogram                                    # noqa: E402

S = 4                       # supersample factor, as the other shape tools use
DISC_PX = 360               # 2x the 180-unit profile tile

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _rgb(text: str) -> tuple:
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def _disc(start: str, end: str) -> Image.Image:
    """One disc: a 135-degree two-stop gradient, circle-masked.

    135 degrees in CSS runs top-left to bottom-right, and its gradient LINE is
    the box diagonal rather than its width -- so the projection is normalised
    over 2r*sqrt(2), not 2r. Getting that wrong compresses both stops toward
    the middle, which is the mistake that made tofa's palette look like a
    different one when we first measured it.
    """
    size = DISC_PX * S
    a, b = _rgb(start), _rgb(end)
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    half = size / 2.0
    span = size * (2 ** 0.5)                    # the diagonal, per CSS
    for y in range(size):
        for x in range(size):
            # distance along the top-left -> bottom-right axis, 0..1
            t = ((x - half) + (y - half)) / (2 ** 0.5) / span + 0.5
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out.resize((DISC_PX, DISC_PX), Image.LANCZOS)


def main() -> int:
    force = "--force" in sys.argv
    written = 0
    for index, (start, end) in enumerate(monogram.PALETTE):
        path = os.path.join(_MEDIA_DIR, "monogram-%d.png" % index)
        if os.path.exists(path) and not force:
            continue
        _disc(start, end).save(path, optimize=True)
        written += 1
        print("wrote %s  %s -> %s" % (os.path.basename(path), start, end))
    print("%d file(s) written, %d in the set" % (written, len(monogram.PALETTE)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
