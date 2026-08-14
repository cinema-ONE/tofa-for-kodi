"""Generates the five alpha-only mask textures whose origin nobody could
account for: circle.png, circle-outline.png and the three edge fades.

Why they are generated rather than kept: issue #4 flagged that these five
arrived with PR #1 and match nothing in plex-for-kodi, with FontAwesome's
`circle`/`circle-o` as the suspected source -- which would need a CC BY 4.0
credit. Inspected, all five turn out to be pure white with an alpha channel
and nothing else: a disc, a ring and three eased ramps. There is no
authorship in a geometric primitive, but "probably fine" is not an answer to
carry into a public release (#5), so they are reproduced here instead and
the question stops existing.

Every constant below was MEASURED off the originals rather than chosen, so
the output is a faithful reproduction and not a redesign:

  circle.png          400x400 disc, antialiased, 50%-alpha radius 199.8 --
                      very slightly inside the canvas edge.
  circle-outline.png  400x400 ring, antialiased, 50%-alpha radii 189.3 and
                      196.2: a ~6.9px stroke.
  fade-bottom.png     256px alpha ramp, 16px across: alpha = t ** 1.2.
  fade-top/left.png   the COMPLEMENT of it, 1 - t ** 1.2 -- not a mirror
                      image. Mirroring fade-bottom gives (1-t) ** 1.2, which
                      is a visibly different curve (34/255 off at midpoint);
                      the complement reproduces the originals to within
                      1/255 across all 256 steps.

  Every radius above is the measured 50%-alpha crossing of a radial
  profile, not a guess from one scanline. An early pass read a single row
  outward from the centre, found no partial alphas on it, and concluded the
  disc was hard-edged -- that row is the one where the circle runs tangent
  to the canvas edge and clips. It has 2544 antialiased pixels.

Dev-only tool, not shipped with the add-on and never imported by it (needs
Pillow). Run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_mask_assets.py
"""
import os

from PIL import Image, ImageDraw

S = 8  # supersample factor for the antialiased ring

CIRCLE_CANVAS = 400
CIRCLE_RADIUS = 199.8        # all three measured at the 50%-alpha crossing
RING_OUTER = 196.2
RING_INNER = 189.3

FADE_LENGTH = 256
FADE_THICKNESS = 16
FADE_GAMMA = 1.2

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str) -> None:
    path = os.path.normpath(os.path.join(_MEDIA_DIR, name))
    im.save(path, "PNG", optimize=True)
    print(f"wrote {path} ({im.size[0]}x{im.size[1]})")


def _white(alpha: Image.Image) -> Image.Image:
    """An alpha channel becomes a white RGBA image. All five originals are
    pure white and carry their whole shape in alpha, which is what lets Kodi
    tint them with <colordiffuse> instead of shipping one per colour."""
    out = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def _discs(*rings: tuple[float, int]) -> Image.Image:
    """Supersampled concentric discs, painted outermost first, downsampled to
    the final canvas. `rings` is (radius, fill) pairs -- a ring is an opaque
    disc with a transparent one punched out of it."""
    size = CIRCLE_CANVAS * S
    centre = size / 2
    alpha = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(alpha)
    for radius, fill in rings:
        r = radius * S
        # Filled discs rather than a stroked ellipse: PIL's `width=` straddles
        # the path unevenly at large radii, and these boundaries are measured.
        draw.ellipse((centre - r, centre - r, centre + r - 1, centre + r - 1),
                     fill=fill)
    return alpha.resize((CIRCLE_CANVAS, CIRCLE_CANVAS), Image.BOX)


def circle() -> None:
    _save(_white(_discs((CIRCLE_RADIUS, 255))), "circle.png")


def circle_outline() -> None:
    _save(_white(_discs((RING_OUTER, 255), (RING_INNER, 0))),
          "circle-outline.png")


def fades() -> None:
    ramp = [round(255 * (i / (FADE_LENGTH - 1)) ** FADE_GAMMA)
            for i in range(FADE_LENGTH)]

    # The complement, NOT the reverse. fade-top and fade-left run 255 -> 0,
    # and mirroring the rising ramp would give (1-t)**1.2 where the originals
    # are 1-(t**1.2) -- 34/255 apart at the midpoint, which is a visibly
    # different falloff on a scrim this size.
    inverse = [255 - v for v in ramp]

    # Names are the edge each sits ON, not the direction it fades towards.
    vertical = Image.new("L", (FADE_THICKNESS, FADE_LENGTH))
    vertical.putdata([v for v in ramp for _ in range(FADE_THICKNESS)])
    _save(_white(vertical), "fade-bottom.png")

    vertical_inverse = Image.new("L", (FADE_THICKNESS, FADE_LENGTH))
    vertical_inverse.putdata([v for v in inverse for _ in range(FADE_THICKNESS)])
    _save(_white(vertical_inverse), "fade-top.png")

    horizontal = Image.new("L", (FADE_LENGTH, FADE_THICKNESS))
    horizontal.putdata(inverse * FADE_THICKNESS)
    _save(_white(horizontal), "fade-left.png")


if __name__ == "__main__":
    circle()
    circle_outline()
    fades()
