"""Generates a true capsule/"pill"-radius rounded-rect texture pair
(tag-pill.png / tag-pill-outline.png) for small rounded-rect chips --
the profile picker's "Kids" tag (script-tofa-profile.xml, fill only) and
sign-in's device-code tiles (script-tofa-signin.xml, fill+outline). Same
reasoning as gen_pill_assets.py: Kodi's 9-patch `border` can't manufacture
a bigger corner curve than the source texture has baked in, so a real
pill shape needs its own correctly-radiused asset.

RADIUS=13 matches the Kids tag's own 26px height (half-height = true
capsule) and is shared by the device-code tiles too, which have plenty of
margin for it. Don't bump this radius: the Kids tag is already at the
geometric limit for a true capsule (2*13 = 26 = full height), and a
radius nudge would make the corner crops overlap, warping the shape (see
project_kodi_9patch_needs_straight_edges). Canvas 60x60 keeps a flat
margin for the 9-patch's stretchable middle at both callers' typical
widths (~70-93px).

Dev-only tool, not shipped with the add-on and never imported by it (needs
Pillow). Run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_tag_asset.py
"""
import os

from PIL import Image, ImageDraw

S = 4  # supersample factor
RADIUS = 13
CANVAS = 60
OUTLINE_STROKE = 2  # matches every other *-outline.png generator in tools/

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str) -> None:
    im = im.resize((CANVAS, CANVAS), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", path)


def gen_fill() -> None:
    sz = CANVAS * S
    r = RADIUS * S
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz - 1, sz - 1], radius=r, fill=(255, 255, 255, 255))
    _save(im, "tag-pill.png")


def gen_outline() -> None:
    sz = CANVAS * S
    r = RADIUS * S
    stroke = OUTLINE_STROKE * S
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Full canvas box, NOT a stroke/2 inset: PIL strokes inward, so this
    # puts the outline's outer edge exactly where the fill's is. An inset
    # outline's silhouette diverges from the fill's by ~1/sin(angle)
    # horizontally -- 3.3px at this asset's corners -- and the two get
    # layered on the same control. See feedback_capsule_ninepatch_rule.
    d.rounded_rectangle(
        [0, 0, sz - 1, sz - 1],
        radius=r, outline=(255, 255, 255, 255), width=stroke,
    )
    _save(im, "tag-pill-outline.png")


if __name__ == "__main__":
    gen_fill()
    gen_outline()
