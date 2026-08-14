"""Generates exact-size true-capsule pill assets for Detail's tab bar
(Episodes/Cast & Crew/About/More Like This), one fill+outline pair per
tab's own width, all at the shared 44px height.

Don't reuse the shared capsule-pill.png/-outline.png (80x80) here via
Kodi's 9-patch `border` attribute: that asset is a pure circle with no
straight edge anywhere on its boundary, and 9-patch border-stretching
needs a straight edge outside the corner to tile the middle segment --
stretching a shape that's pure curve everywhere warps it into an
arrow-like bulge, worse at narrower widths. Same fix as
poster_visual()/episode_card(): skip 9-patch, generate an exact-size
asset (`rounded_rectangle` at radius=height/2, which has genuine straight
edges between the semicircle ends) per tab's known width, referenced with
no `border` attribute.

Dev-only tool (needs Pillow) -- run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/. See
resources/lib/skin/templates/detail.xml.tpl's tab bar for usage.

Usage:
    python3 tools/gen_tab_pill_assets.py
"""
import os

from PIL import Image, ImageDraw

# How many OUTPUT pixels we emit per unit of the 1920x1080 coordinate space.
# The CoreELEC box runs its GUI at 3840x2160, so a texture authored 1:1 for
# the coordinate space is upscaled 2x before it reaches the panel and every
# hard edge softens. Emitting at 2x lands these ~1:1 on a 4K screen and
# costs nothing at 1080p, where Kodi scales them back down.
#
# Only sound for textures Kodi scales WHOLE. Never apply it to 9-patch art
# (anything drawn with a `border=` attribute): there the border slices the
# source in texture pixels AND sets the drawn corner size, so a bigger
# texture would need a bigger border and would draw a bigger corner.
ASSET_SCALE = 2
S = 4 * ASSET_SCALE  # supersample factor, kept at 4x the emitted size
HEIGHT = 44
RADIUS = HEIGHT // 2  # true capsule
OUTLINE_STROKE = 2

# (name, width) -- must match detail.xml.tpl's own tab widths exactly.
TABS = [
    ("episodes", 190),
    ("castcrew", 220),
    ("about", 140),
    ("morelikethis", 230),
]

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str, size: tuple[int, int]) -> None:
    """`size` is in 1080-space units; the file lands at ASSET_SCALE times it."""
    im = im.resize((size[0] * ASSET_SCALE, size[1] * ASSET_SCALE), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name, size)


def gen_fill(name: str, w: int) -> None:
    sz = (w * S, HEIGHT * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=RADIUS * S, fill="white")
    _save(im, f"tab-pill-{name}.png", (w, HEIGHT))


def gen_outline(name: str, w: int) -> None:
    sz = (w * S, HEIGHT * S)
    stroke = OUTLINE_STROKE * S
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        [stroke / 2, stroke / 2, sz[0] - 1 - stroke / 2, sz[1] - 1 - stroke / 2],
        radius=RADIUS * S, outline="white", width=stroke,
    )
    _save(im, f"tab-pill-{name}-outline.png", (w, HEIGHT))


def main() -> None:
    for name, w in TABS:
        gen_fill(name, w)
        gen_outline(name, w)


if __name__ == "__main__":
    main()
