"""Builds the add-on's fanart: the startup splash, held at its final frame.

WHAT KODI DOES WITH IT. addon.xml's <assets><fanart> is the backdrop Kodi
draws behind the add-on in its own browser, and it is what a repository shows
next to the entry. It shipped as a placeholder -- one flat colour, 1920x1080,
literally a single RGB value in the whole file.

WHY THE SPLASH. It is the one full-screen composition the add-on already owns,
it is the first thing a user sees when they launch it, and it is measured off
tofa's real app rather than invented. So the browser entry and the app agree.

ASSEMBLED FROM THE SHIPPED STRIPS, not re-rendered. The splash exists as 14 +
11 vertical slices because Kodi has no clip animation and a wipe has to be
faked by fading strips in one after another (see gen_splash_assets.py). Gluing
those back together reproduces the final frame exactly, and it dodges the one
thing that does NOT reproduce across machines: the wordmark is type, and
FreeType lays it out fractionally differently on macOS than on the Linux box
the shipped strips were rendered on (project_macbook_migration). Re-rendering
the text here would make the fanart disagree with the splash by a pixel or
two, on a lockup where that reads as a mistake.

Geometry is imported from tokens.py -- the same numbers the skin lays the
splash out with, so a change there moves both.

Dev-only tool (needs Pillow).

    python3 tools/gen_fanart.py [--jpg] [--check]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "plugin.video.tofa", "resources"))
from lib.skin import tokens as T  # noqa: E402

from PIL import Image  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "plugin.video.tofa")
MEDIA = os.path.join(ADDON, "resources", "skins", "Main", "media")

SIZE = (1920, 1080)
#: tokens.SPLASH_BG is Kodi's AARRGGBB; the canvas here is plain RGB.
BG = tuple(int(T.SPLASH_BG[i:i + 2], 16) for i in (2, 4, 6))
#: Where the skin puts the glow, straight out of the rendered splash: a
#: square radial hanging off the top of the screen, not centred on it.
GLOW_POS = (410, -96)
GLOW_SIZE = (T.SPLASH_GLOW_W, T.SPLASH_GLOW_H)


def _assembled(prefix: str, count: int, size: tuple[int, int]) -> Image.Image:
    """Glue a wipe's strips back into the whole image, at `size`.

    The strips are 2x art (whole-scaled, per project_asset_scale_2x), so this
    reassembles at 2x and comes down to the 1080p canvas in one resample
    rather than scaling each slice and accumulating seams."""
    strips = []
    for index in range(count):
        path = os.path.join(MEDIA, "%s-%02d.png" % (prefix, index))
        if not os.path.exists(path):
            raise SystemExit(
                "%s is missing -- run tools/gen_splash_assets.py first; this "
                "tool only reassembles what the splash already ships."
                % os.path.relpath(path, ROOT))
        strips.append(Image.open(path).convert("RGBA"))
    whole = Image.new("RGBA", (sum(s.width for s in strips), strips[0].height),
                      (0, 0, 0, 0))
    x = 0
    for strip in strips:
        whole.paste(strip, (x, 0))
        x += strip.width
    return whole.resize(size, Image.LANCZOS)


def build() -> Image.Image:
    canvas = Image.new("RGBA", SIZE, BG + (255,))
    glow = Image.open(os.path.join(MEDIA, "splash-glow.png")).convert("RGBA")
    canvas.alpha_composite(glow.resize(GLOW_SIZE, Image.LANCZOS), GLOW_POS)
    canvas.alpha_composite(
        _assembled("splash-mark", T.SPLASH_MARK_STRIPS,
                   (T.SPLASH_MARK_W, T.SPLASH_MARK_H)),
        (T.SPLASH_MARK_X, T.SPLASH_MARK_Y))
    canvas.alpha_composite(
        _assembled("splash-word", T.SPLASH_WORD_STRIPS,
                   (T.SPLASH_WORD_W, T.SPLASH_WORD_H)),
        (T.SPLASH_WORD_X, T.SPLASH_WORD_Y))
    return canvas.convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jpg", action="store_true",
                    help="write fanart.jpg instead. Measured, not assumed: at "
                         "q92 4:4:4 the JPEG is 19KB smaller and rings visibly "
                         "along the mark and the glyph edges, which is what a "
                         "near-black gradient under flat art costs. Kodi accepts "
                         "either -- its own repo carries 95 fanart.png against "
                         "580 .jpg. Update addon.xml's <fanart> if you switch.")
    ap.add_argument("--check", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    art = build()
    name = "fanart.jpg" if args.jpg else "fanart.png"
    out = os.path.join(ADDON, name)
    if args.check:
        print("would write %s  %dx%d" % (name, *art.size))
        return 0
    if not args.jpg:
        art.save(out, optimize=True)
    else:
        # 92 rather than the default 75: the composition is a near-black
        # gradient, which is the worst case for JPEG -- the banding shows as
        # rings around the glow long before it shows anywhere else.
        art.save(out, quality=92, subsampling=0, optimize=True)
    print("%s  %dx%d  %.1f KB"
          % (os.path.relpath(out, ROOT), art.size[0], art.size[1],
             os.path.getsize(out) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
