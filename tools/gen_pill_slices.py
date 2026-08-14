"""Generates the 3-slice pill art that replaces the capsule 9-patches.

WHY THIS EXISTS. A Kodi 9-patch corner cannot be shipped at higher
resolution: `border="30"` says both "cut 30 pixels out of the file" and
"draw that corner 30 units wide", so a denser texture needs a bigger border,
which draws a bigger corner. On a 4K GUI every capsule corner is therefore
upscaled 2x from art authored for the 1080 coordinate space.

Slicing it ourselves breaks the coupling. A pill is a flat middle between
two half-stadium caps, and a cap's aspect is ALWAYS 1:2 -- width is half the
height at every size -- so one pair of caps drawn at 200x400 serves a 24px
badge and an 88px transport pill alike, and lands crisp on any panel. The
middle is flat colour, which stretches losslessly from a few pixels.

Kodi never sees a border: each piece is a whole texture scaled into its own
control, so there is nothing to slice and nothing to couple.

resources/lib/skin/build.py does the substitution on the rendered XML --
see `_slice_pills()` there for which controls qualify and which are left
as 9-patches.

SOLID FILLS, plus outlined CIRCLES. An outline's stroke has to stay 2px
however big the shape is, and a shared cap scaled from 400 tall down to 64
would render its stroke at a third of a pixel -- so stroked art has to be
per-size. That is cheap for a circle, whose only dimension is its height, and
it is why `pill-circle-outline-h<N>.png` exists per height. It is NOT cheap
for a stroked PILL, whose art would additionally depend on its width, and
where a slice seam would fall in the middle of a bright 2px hairline rather
than in flat colour. Outlined pills keep their 9-patch art.

Dev-only tool (needs Pillow). Output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_pill_slices.py
"""
import os

from PIL import Image, ImageDraw

S = 4  # supersample factor

# Caps are authored far larger than any pill they will serve: a solid shape
# scales down losslessly, so one size covers every height and there is no
# reason to be frugal. 400 is 4.5x the tallest capsule in the app (88).
CAP_H = 400
CAP_W = CAP_H // 2
CIRCLE = 400
# The middle is flat, so it only needs enough pixels to survive resampling.
MID = 16

# Stroked art cannot be shared across sizes, so outlined circles are drawn
# one per height, at OUTLINE_SCALE times the height they will be drawn at.
# The stroke is scaled with them so it still lands as 2 units on screen.
OUTLINE_SCALE = 2
OUTLINE_STROKE = 2
# Every height that has a capsule. Kept in step with
# tools/gen_capsule_pill_assets.py:_HEIGHTS by hand -- generating all of them
# rather than only the ones in use today means a new pill height needs no
# second edit here, and each file is a few hundred bytes.
_HEIGHTS = (11, 20, 24, 28, 38, 52, 54, 58, 60, 64, 66, 68, 72, 76, 78, 88)

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str, size: tuple[int, int]) -> None:
    im = im.resize(size, Image.LANCZOS)
    im.save(os.path.join(_MEDIA_DIR, name))
    print("saved", name, size)


def gen_caps() -> None:
    """Left and right half-stadiums.

    Drawn as a full stadium twice the width, then cropped down the middle,
    so both halves come off the same curve and butt-join without a step.
    Kodi cannot mirror a texture, hence two files rather than one.
    """
    w, h = CAP_W * 2 * S, CAP_H * S
    full = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(full).rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill="white")
    _save(full.crop((0, 0, w // 2, h)), "pill-cap-left.png", (CAP_W, CAP_H))
    _save(full.crop((w // 2, 0, w, h)), "pill-cap-right.png", (CAP_W, CAP_H))


def gen_middle() -> None:
    """The flat span between the caps. Opaque white; the control tints it."""
    im = Image.new("RGBA", (MID, MID), (255, 255, 255, 255))
    im.save(os.path.join(_MEDIA_DIR, "pill-mid.png"))
    print("saved pill-mid.png", (MID, MID))


def gen_circle() -> None:
    """A capsule drawn square IS a circle, and 120 of them are.

    Those need no slicing at all -- one texture, no border, scaled into the
    control. Kept separate from the avatar circle.png, which is bound up
    with `scalediffuse="false"` masking and must not be disturbed.
    """
    sz = CIRCLE * S
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, sz - 1, sz - 1], fill="white")
    _save(im, "pill-circle.png", (CIRCLE, CIRCLE))


def gen_circle_outlines() -> None:
    """One stroked ring per height, drawn at OUTLINE_SCALE times its size.

    Kodi draws these with no border at all, so the file is simply scaled into
    the control: at 2x it lands 1:1 on a 4K panel instead of being upscaled
    from art authored for the 1080 coordinate space. The stroke is scaled
    with the canvas so it still measures 2 units when drawn.
    """
    for h in _HEIGHTS:
        px = h * OUTLINE_SCALE
        sz = px * S
        im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse(
            [0, 0, sz - 1, sz - 1],
            outline=(255, 255, 255, 255),
            width=OUTLINE_STROKE * OUTLINE_SCALE * S,
        )
        _save(im, f"pill-circle-outline-h{h}.png", (px, px))


def verify() -> None:
    """The caps must butt-join into a true stadium.

    Checks the seam: the right column of the left cap and the left column of
    the right cap are both the shape's waist, so both must be fully opaque
    top to bottom. A gap here would show as a hairline through every pill.
    """
    left = Image.open(os.path.join(_MEDIA_DIR, "pill-cap-left.png")).convert("RGBA")
    right = Image.open(os.path.join(_MEDIA_DIR, "pill-cap-right.png")).convert("RGBA")
    for name, im, x in (("pill-cap-left.png", left, left.width - 1),
                        ("pill-cap-right.png", right, 0)):
        alpha = im.split()[3]
        column = [alpha.getpixel((x, y)) for y in range(im.height)]
        worst = min(column)
        status = "ok" if worst >= 254 else "FAIL"
        print(f"  verify {name}: seam column min alpha {worst} [{status}]")
        if worst < 254:
            raise SystemExit(
                f"{name}'s seam column is not solid (min alpha {worst}); the "
                f"two caps would not meet the middle cleanly.")
    # ...and the outer edge must be a true semicircle, not a flattened one.
    alpha = left.split()[3]
    mid_y = left.height // 2
    row = [alpha.getpixel((x, mid_y)) for x in range(left.width)]
    first = next(x for x, a in enumerate(row) if a >= 128)
    print(f"  verify pill-cap-left.png: waist reaches the left edge at x={first} "
          f"[{'ok' if first == 0 else 'FAIL'}]")
    if first != 0:
        raise SystemExit("the cap's widest point is not at its outer edge")


def main() -> None:
    gen_caps()
    gen_middle()
    gen_circle()
    gen_circle_outlines()
    verify()


if __name__ == "__main__":
    main()
