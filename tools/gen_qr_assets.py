"""Generates resources/skins/Main/media/qr-<slug>.png -- the QR codes the
Settings screen shows in its right-hand rail ("Manage account" on Account,
"Report a problem" on Privacy & About).

Why these are baked assets rather than generated at runtime: both codes
encode a plain static URL with no device, account or session token in them
(decoded straight off an Apple TV capture, see internal-docs/atv-reference/
settings-account.png and settings-privacy-about.png). The tofa API has no
general-purpose QR endpoint either -- POST /device/code returns a
`qr_code_svg`, but only ever of its own pairing URL, which is why
signin.py's `_qr_svg_to_png()` exists and is NOT what this replaces.

Geometry is measured off those captures, not guessed:

    symbol        244 x 244 px  = 41 x 41 modules  (QR version 6)
    quiet zone    24 px         = 4 modules, all four sides
    white card    292 x 292 px  = 49 modules, corner radius 20

41x41 is the only standard version that lands a 4-module-quiet-zone card on
292px (version 5's 37 modules would give 322, version 7's 45 would give 265),
so the real app is pinning version 6 rather than letting the encoder pick --
27 bytes of URL would otherwise fit in a version 2. We pin it the same way so
ours is the same shape, and take error correction H since it is free at that
size and a TV is the worst case for a camera.

Rendered at 2x (588px card, 12px modules) because Kodi's WindowXML canvas is
capped at 1080i while the box may output 4K -- crispness has to come from a
higher-resolution asset, not from bigger coordinates.

Dev-only tool, not shipped with the add-on and never imported by it (needs
segno). Run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_qr_assets.py
"""
import os

import segno
from PIL import Image, ImageDraw

# slug -> the URL the code resolves to. Both decoded from the real Apple TV
# app rather than invented; keep them byte-identical to what it encodes so a
# phone that has scanned one lands in the same place from either client.
QR_URLS: dict[str, str] = {
    "account": "https://app.tofa.tv/account",
    # DELIBERATELY NOT the Apple TV app's `accounts.tofa.tv/support`. A problem
    # with THIS add-on is not something tofa's support desk can fix, and the
    # reports were arriving where nobody could act on them. Ours goes to the
    # issue tracker of the repository the add-on is built from. Account and
    # server problems still belong to tofa, which is what the caption says.
    #
    # 50 bytes against version 6's 58-byte budget at error correction H, so
    # the card keeps the measured geometry below rather than growing a version.
    "support": "https://github.com/cinema-ONE/tofa-for-kodi/issues",
}

# See the module docstring -- every one of these is measured, not chosen.
VERSION = 6           # 41 x 41 modules (version n is 4n+17 modules square)
ERROR = "h"
QUIET_MODULES = 4
CARD_MODULES = 41 + 2 * QUIET_MODULES   # 49
MODULE_PX = 12                          # 2x the app's 5.951px
CARD_PX = CARD_MODULES * MODULE_PX      # 588
RADIUS_PX = 40                          # 2x the measured radius of 20

MEDIA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugin.video.tofa", "resources", "skins", "Main", "media",
)


def render(url: str) -> Image.Image:
    """One white rounded card with the QR centred in it, transparent outside
    the corner radius so it can sit straight on the glass panel without a
    separate card texture underneath (and without square corners poking out
    of a rounded one)."""
    qr = segno.make(url, version=VERSION, error=ERROR, boost_error=False)
    matrix = [list(row) for row in qr.matrix]
    if len(matrix) != 41:
        raise SystemExit(f"expected a 41x41 symbol, got {len(matrix)}x{len(matrix)}")

    card = Image.new("RGBA", (CARD_PX, CARD_PX), (0, 0, 0, 0))

    # The white card itself, drawn as a mask so the corners are antialiased
    # rather than stair-stepped -- it is composited at 292px, where a hard
    # edge would be visible.
    mask = Image.new("L", (CARD_PX * 4, CARD_PX * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, CARD_PX * 4 - 1, CARD_PX * 4 - 1), radius=RADIUS_PX * 4, fill=255)
    mask = mask.resize((CARD_PX, CARD_PX), Image.LANCZOS)
    card.paste(Image.new("RGBA", (CARD_PX, CARD_PX), (255, 255, 255, 255)), (0, 0), mask)

    # Dark modules, drawn on integer boundaries so every module is exactly
    # MODULE_PX square with no resampling.
    draw = ImageDraw.Draw(card)
    origin = QUIET_MODULES * MODULE_PX
    for row, bits in enumerate(matrix):
        for col, bit in enumerate(bits):
            if not bit:
                continue
            x0 = origin + col * MODULE_PX
            y0 = origin + row * MODULE_PX
            draw.rectangle((x0, y0, x0 + MODULE_PX - 1, y0 + MODULE_PX - 1),
                           fill=(0, 0, 0, 255))
    return card


def main() -> None:
    for slug, url in sorted(QR_URLS.items()):
        path = os.path.join(MEDIA_DIR, f"qr-{slug}.png")
        render(url).save(path, "PNG", optimize=True)
        print(f"{path}  <-  {url}")


if __name__ == "__main__":
    main()
