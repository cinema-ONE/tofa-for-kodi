"""Renders one pill image per card format badge.

WHY IMAGES AND NOT LABELS. Each pill hugs its own text -- "DV" is narrow,
"DTS-HD MA" is wide -- and Kodi cannot size a control to a LIST ITEM's own
text: width is fixed in an item layout, and nothing binds it to an InfoLabel.
A label with a background image would need the image to follow the text width,
which no Kodi control does.

So each badge ships as a finished pill: rounded scrim plus its text, baked in
at the right width. The skin draws it into a generous box with
`aspectratio=keep` and `align=left`, which renders the pill at its true aspect
against the box's left edge and leaves the rest transparent. The visible pill
is therefore exactly as wide as its text, from a fixed-size control.

The label set comes from resources/lib/badges.py, which the runtime filters
against too, so the assets and the code cannot drift apart.

2x, like all whole-scaled art (project_asset_scale_2x): a pill is neither a
9-patch nor a gradient.

    python3 tools/gen_badge_assets.py [--prune]
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "plugin.video.tofa", "resources", "skins", "Main")
MEDIA = os.path.join(SKIN, "media")
FONTS = os.path.join(SKIN, "fonts")

sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources", "lib"))
import badges as badge_defs  # noqa: E402

SCALE = 2
#: In 1080p canvas units, measured off the macOS app: pills sit on a 30px
#: pitch with ~22 of ink, so 22 high with 8 of padding either side of the text.
HEIGHT = 22
PAD_X = 8
#: Matched to the rating chip, measured off badge-outline.png: 2px of stroke
#: at 2x and a ~12px corner there. The rating chip stays the taller of the two
#: on purpose; only the border weight is shared, so the stack reads as one
#: family rather than as two different components.
RADIUS = 6
FONT = "inter_tight_semibold.ttf"
#: 15 reads at the same weight as the app's against a 22-tall pill.
FONT_SIZE = 15
#: Matches tokens.BADGE_SCRIM (0x99000000), the fill the rating chip already
#: uses, so the two stacks look like one system.
FILL = (0, 0, 0, 0x99)
INK = (255, 255, 255, 255)
#: badge-outline.png carries white at alpha 239 and is then tinted by
#: BORDER (0x40FFFFFF), so what lands on screen is white at ~60/255. These
#: pills are baked rather than colordiffused, so that product is baked in.
OUTLINE = (255, 255, 255, 60)
OUTLINE_W = 1

PREFIX = "badge-fmt-"


def _slug(label: str) -> str:
    # ":" for DTS:X. A colon is legal in a Linux filename but not on every
    # filesystem this add-on gets copied to, and the name is what Kodi looks
    # a skin texture up by -- so it is flattened here rather than shipped.
    return (label.lower().replace("+", "plus").replace(" ", "-")
            .replace("/", "-").replace(":", "-"))


def render(label: str) -> Image.Image:
    font = ImageFont.truetype(os.path.join(FONTS, FONT), FONT_SIZE * SCALE)
    box = font.getbbox(label)
    text_w = box[2] - box[0]
    width = text_w + PAD_X * 2 * SCALE
    height = HEIGHT * SCALE
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1),
                           radius=RADIUS * SCALE, fill=FILL,
                           outline=OUTLINE, width=OUTLINE_W * SCALE)
    # Placed by the text's own ink box so every pill's glyphs sit on one
    # optical centre, rather than by the font's line box which carries
    # different slack per string.
    draw.text((PAD_X * SCALE - box[0], (height - (box[3] - box[1])) // 2 - box[1]),
              label, font=font, fill=INK)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prune", action="store_true",
                        help="delete pills for labels no longer in badges.py")
    args = parser.parse_args()

    wanted = {}
    for label in badge_defs.CARD_BADGES:
        name = PREFIX + _slug(label) + ".png"
        image = render(label)
        image.save(os.path.join(MEDIA, name))
        wanted[name] = image.size

    have = {n for n in os.listdir(MEDIA) if n.startswith(PREFIX)}
    stale = sorted(have - set(wanted))
    for name in stale:
        if args.prune:
            os.remove(os.path.join(MEDIA, name))
            print("removed %s" % name)
        else:
            print("STALE   %s (nothing references it; --prune to delete)" % name)

    total = sum(os.path.getsize(os.path.join(MEDIA, n)) for n in wanted)
    for name, size in sorted(wanted.items()):
        print("  %-28s %dx%d" % (name, size[0], size[1]))
    print("%d pills, %.1f KB total%s"
          % (len(wanted), total / 1024.0,
             "" if args.prune or not stale else ", %d stale" % len(stale)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
