"""Cuts the startup splash into the vertical strips its wipe animation needs.

WHY STRIPS. The real tofa apps reveal the logo with a left-to-right wipe: the
mark does not move, it is uncovered in place, and the wordmark is uncovered by
a second, later wipe. Kodi has no clip, mask or crop animation -- `slide`,
`zoom`, `rotate` and `fade` move or blend a WHOLE control, and a texture is
always drawn entire. The only way to uncover an image in place is to cut it up
beforehand and fade the pieces in one after another.

That costs nothing in pixels: the strips together are exactly the source
image, not N copies of it. It costs FILES, which is why the strips are as wide
as they can be while still reading as a moving edge (STRIP_W) rather than as
one-pixel-perfect columns.

Timing lives in the skin fragment, not here -- each strip gets a WindowOpen
fade whose `delay` is its position along the wipe, so Kodi runs the whole
animation with no Python driving it.

Measured off a genuine cold start recorded from the Android TV app over ADB
(`screenrecord`, 1920x1080), at internal-docs/ if kept:

    mark      213x259 at centre (961, 454)   wipe 120ms -> ~1400ms, ease-out
    wordmark  173x85  at centre (957, 691)   wipe 840ms -> ~1200ms
    then both hold ~2.5s before the app appears

The wordmark is TYPE, not art: Inter Tight Regular at 103 reproduces the app's
"tofa" to the pixel (173px wide), verified against a crop of the recording. It
is rendered here rather than drawn as a Kodi label because a label cannot be
cut into strips.

    python3 tools/gen_splash_assets.py [--check]
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import zlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "plugin.video.tofa", "resources"))
from lib.skin import tokens as _T  # noqa: E402
import sys

# Tolerated rather than required: the mark and wordmark render TEXT and need
# Pillow, but the glow is arithmetic, and --glow-only must work on a machine
# without it. main() refuses the PIL paths with a clear message instead of an
# ImportError three frames deep.
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                   # pragma: no cover
    Image = ImageDraw = ImageFont = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "plugin.video.tofa", "resources", "skins", "Main")
MEDIA = os.path.join(SKIN, "media")
FONTS = os.path.join(SKIN, "fonts")

#: The mark comes from the SHIPPED fox rasters, media/tofa-logo[-<slug>].png --
#: the same files the nav bar draws, one per accent. See _mark().
#:
#: This used to say the mark had to come from vector source, because
#: tofa-logo.png was 213x256 and would be upscaled on the 4K box. That stopped
#: being true when the logos were regenerated at 640x768 (project_asset_scale_2x);
#: the splash needs 426x512, so these DOWNSCALE. The note outlived the fact and
#: was still steering this file in 2026-08-13.

#: Measured from the recording, in 1080p canvas units.
MARK_W, MARK_H = 213, 256

#: Whole-scaled art ships at 2x for the 4K GUI. Strips are whole-scaled art:
#: not 9-patch (which provably cannot) and not a gradient (which should not).
SCALE = 2
WORD_TEXT = "tofa"
WORD_FONT = "inter_tight_regular.ttf"
WORD_SIZE = 103
WORD_W, WORD_H = 173, 85
WORD_RGB = (238, 242, 242)

#: Wide enough to keep the file count sane, narrow enough that a staggered
#: fade reads as one moving edge rather than as blocks lighting up. At 16 the
#: mark is 14 strips and the wordmark 11.
#: Imported rather than restated: fragments.py:splash_wipe() lays the strips
#: out using the SAME rule (fixed width, remainder last), and the two silently
#: disagreeing is exactly what dented the mark's right end -- the layout used
#: to divide the width into equal shares while the cutter used a fixed step.
STRIP_W = _T.SPLASH_STRIP_W   # in 1080p canvas units; files are STRIP_W*SCALE wide

#: The soft teal radial behind the mark. A gradient, so deliberately NOT 2x
#: (see project_asset_scale_2x) -- it is stretched to full screen and scaling
#: a smooth gradient costs nothing.
#:
#: SQUARE, and that is the whole point. It was 640x360, drawn into a 1100x1100
#: control with <aspectratio>stretch</aspectratio>, so a circle authored here
#: came out 1.78x taller than wide on screen. Reported as "the background glow
#: is oval". _glow() always drew a true circle -- it normalises both axes by
#: min(cx, cy) -- so the fault was never in the maths, only in the canvas it
#: was drawn into. Keep this square or the oval comes back.
GLOW_SIZE = (1024, 1024)
#: WHITE, and tinted at runtime. The glow is the one splash asset that is a
#: single flat colour behind an alpha ramp, so Kodi's colordiffuse -- a
#: multiply -- reproduces any accent from it exactly, including a custom hex
#: the 14 foxes cannot express. It used to be baked teal (0,190,180), which
#: multiplied against an accent would have given accent x teal.
GLOW_RGB = (255, 255, 255)
GLOW_PEAK_ALPHA = 34


def _slice(image: Image.Image, prefix: str) -> list[tuple[str, int, int]]:
    """Cut `image` into STRIP_W-wide columns. Returns (filename, x, width)."""
    out = []
    step = STRIP_W * SCALE
    for index, x in enumerate(range(0, image.width, step)):
        width = min(step, image.width - x)
        strip = image.crop((x, 0, x + width, image.height))
        name = "%s-%02d.png" % (prefix, index)
        strip.save(os.path.join(MEDIA, name))
        out.append((name, x, width))
    return out


#: The 14 foxes, READ OUT OF theme.py rather than restated here.
#:
#: They have to agree exactly: theme.PRESETS decides which fox the running app
#: thinks it is showing, and this decides which files exist for it to show. A
#: hand-copied second list is the bug where one accent silently has no strips
#: and the splash draws nothing. theme.py cannot be imported outside Kodi (it
#: pulls in xbmc through kodigui), so it is parsed, and the parse is asserted
#: rather than trusted -- 14 entries or this refuses to run.
_THEME_PY = os.path.join(ROOT, "plugin.video.tofa", "resources", "lib",
                         "windows", "theme.py")
_PRESET_RE = re.compile(r'^\s*\("([A-Za-z]+)",\s*"([0-9A-Fa-f]{6})",', re.M)


def _presets() -> list[tuple[str, str]]:
    """[(slug, RRGGBB)] for every fox, in theme.PRESETS order."""
    with open(_THEME_PY, "r", encoding="utf-8") as handle:
        body = handle.read()
    block = body.partition("PRESETS = (")[2].partition(")\n")[0]
    found = [(name.lower(), hexrgb.upper()) for name, hexrgb in _PRESET_RE.findall(block)]
    if len(found) != 14:
        raise SystemExit(
            "expected 14 foxes in theme.PRESETS, parsed %d (%s). Fix the parse "
            "or the table; do NOT hand-copy the palette here."
            % (len(found), ", ".join(n for n, _ in found)))
    return found


def _logo_png(slug: str) -> str:
    """The SHIPPED fox raster for one accent, which is the same art the nav
    bar draws."""
    return os.path.join(MEDIA, "tofa-logo.png" if slug == "tofa"
                        else "tofa-logo-%s.png" % slug)


def _mark(slug: str) -> Image.Image:
    """The fox mark at SCALE, in `slug`'s colours.

    STRAIGHT FROM THE SHIPPED LOGO RASTER, which is the same file the nav bar
    draws. Nothing is recoloured here.

    It was recoloured here, once. The first build re-hued the vector source
    per accent with a transform of my own -- take each fill to the accent's
    hue, scale its saturation and value by the accent's ratio to Tofa's. The
    hues came out right and the rest did not: measured against the shipped
    amber logo, the generated fox read sat 0.97 / val 0.73 against its
    0.88 / 0.68, and Adrian spotted it on the box as "more saturated than the
    fox in the main screen" before any of this was measured.

    The lesson is not that the transform needed tuning. It is that the 14
    recoloured foxes ALREADY EXIST as design output, and a formula that
    re-derives them can only ever approximate what a designer chose by eye --
    while guaranteeing the splash and the nav bar disagree about the same fox.

    Two things make this safe that were not true when the comment here still
    said the PNG was 213x256:

    * The logos are 640x768, comfortably above the 426x512 the splash needs,
      so this DOWNSCALES. That old note is why the vector route existed at all.
    * The aspect matches exactly (640:768 and 213:256 are both 0.833), so the
      resize is not a squash.

    The Tofa artwork itself was checked against the vector before this switch:
    body #03A39B from the PNG against #04A099 from the SVG, hue 177.2 vs
    177.4. They are the same drawing; only the recolours differ.
    """
    path = _logo_png(slug)
    if not os.path.exists(path):
        raise SystemExit(
            "no fox raster for %r at %s -- theme.PRESETS names an accent whose "
            "logo is not in media/. Add the art or fix the table; do NOT fall "
            "back to recolouring, which is what this replaced." % (slug, path))
    return Image.open(path).convert("RGBA").resize(
        (MARK_W * SCALE, MARK_H * SCALE), Image.LANCZOS)


def _wordmark() -> Image.Image:
    """The wordmark at SCALE. Type, not art -- rendered from the bundled font
    at SCALE rather than rasterised small and blown up."""
    font = ImageFont.truetype(os.path.join(FONTS, WORD_FONT), WORD_SIZE * SCALE)
    box = font.getbbox(WORD_TEXT)
    width, height = WORD_W * SCALE, WORD_H * SCALE
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Sit the glyphs on the canvas by their own ink box, so the PNG's edges are
    # the wordmark's edges and the skin can place it by measured centre.
    draw.text((-box[0], -box[1] + (height - (box[3] - box[1])) // 2),
              WORD_TEXT, font=font, fill=WORD_RGB + (255,))
    return image


def _write_glow(path: str) -> None:
    """The radial, written straight to PNG with no PIL.

    Everything else here renders TEXT and needs Pillow for it; the glow is
    arithmetic and a zlib stream. Keeping it PIL-free means the one asset most
    likely to need a tweak can be regenerated anywhere -- including this
    machine, which has no Pillow -- with `--glow-only`.
    """
    width, height = GLOW_SIZE
    cx, cy = width / 2.0, height / 2.0
    radius = min(cx, cy)
    red, green, blue = GLOW_RGB
    rows = bytearray()
    for y in range(height):
        rows.append(0)                     # filter: none
        dy = ((y - cy) / radius) ** 2
        for x in range(width):
            d = (((x - cx) / radius) ** 2 + dy) ** 0.5
            if d >= 1.0:
                rows += b"\x00\x00\x00\x00"
                continue
            # smoothstep falloff: no visible rim where it meets the background
            t = 1.0 - d
            alpha = int(round(GLOW_PEAK_ALPHA * t * t * (3 - 2 * t)))
            rows += bytes((red, green, blue, alpha)) if alpha else b"\x00\x00\x00\x00"

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="report what would be written, write nothing")
    parser.add_argument("--glow-only", action="store_true",
                        help="rewrite splash-glow.png alone (needs no Pillow)")
    args = parser.parse_args()

    if Image is None and not args.glow_only:
        print("this needs Pillow (pip install Pillow) -- or use --glow-only, "
              "which does not")
        return 1

    if args.glow_only:
        _write_glow(os.path.join(MEDIA, "splash-glow.png"))
        print("glow  %dx%d" % GLOW_SIZE)
        return 0

    presets = _presets()
    word = _wordmark()

    if args.check:
        # Divide by the SCALED step, as _slice does. Dividing by STRIP_W here
        # reported 27/22 against a real 14/11.
        step = STRIP_W * SCALE
        per_fox = -(-(MARK_W * SCALE) // step)
        print("would write %d foxes x %d mark strips = %d, + %d word strips "
              "+ splash-glow.png" % (len(presets), per_fox, len(presets) * per_fox,
                                     -(-word.width // step)))
        return 0

    for stale in sorted(os.listdir(MEDIA)):
        if stale.startswith(("splash-mark-", "splash-word-")):
            os.remove(os.path.join(MEDIA, stale))

    # ONE set of strips per fox. The wordmark is NOT repeated: the real app
    # leaves it white whatever the accent is (measured on a live Android
    # capture of the Amber fox, where the mark is amber and "tofa" is not), so
    # 14 identical copies of it would be 14 copies of nothing.
    mark_strips = []
    for slug, _hexrgb in presets:
        mark_strips = _slice(_mark(slug), "splash-mark-%s" % slug)
    word_strips = _slice(word, "splash-word")
    _write_glow(os.path.join(MEDIA, "splash-glow.png"))

    total = sum(os.path.getsize(os.path.join(MEDIA, n))
                for n in os.listdir(MEDIA)
                if n.startswith(("splash-mark-", "splash-word-", "splash-glow")))
    print("mark  %d foxes x %2d strips of %dpx @%dx (%s)"
          % (len(presets), len(mark_strips), STRIP_W, SCALE,
             ", ".join(s for s, _ in presets)))
    print("word  %2d strips of %dpx @%dx (%dx%d)" % (len(word_strips), STRIP_W, SCALE, *word.size))
    print("glow  %dx%d" % GLOW_SIZE)
    print("%d files, %.0f KB total"
          % (len(presets) * len(mark_strips) + len(word_strips) + 1, total / 1024.0))
    print("\nskin/tokens.py expects: SPLASH_MARK_STRIPS = %d, SPLASH_WORD_STRIPS = %d"
          % (len(mark_strips), len(word_strips)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
