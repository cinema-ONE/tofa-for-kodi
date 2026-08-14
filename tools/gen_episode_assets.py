"""Generates the episode-card assets for Detail's Episodes tab grid:
rounded corners, focus border, and a soft focus glow -- the same
treatment poster_visual() already gives every poster card.

Dev-only tool (needs Pillow) -- run by hand when one of these needs
tweaking, output goes straight into
plugin.video.tofa/resources/skins/Main/media/. See
resources/lib/skin/fragments.py:episode_card() for how each is used.
Mirrors tools/gen_poster_assets.py's technique exactly (exact-size
assets, not 9-slice, to sidestep any stretch-distortion question).

Usage:
    python3 tools/gen_episode_assets.py
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

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

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)

THUMB_W, THUMB_H = 330, 186  # 16:9 episode still
CORNER_RADIUS = 16  # comparable to poster-mask.png's own 16px
BORDER_STROKE = 2  # same as poster-border.png

# Must match fragments.py:episode_card()'s HPAD/TOP_PAD -- the cell only
# has 20px of horizontal slack (350-330) for the glow to bleed into
# before it's clipped by the list's cell bounds, so there's no margin to
# raise this without also widening the cell.
GLOW_PAD = 10
GLOW_ALPHA = 90  # same peak interior opacity as card-glow.png


def _save(im: Image.Image, name: str, size: tuple[int, int]) -> None:
    """`size` is in 1080-space units; the file lands at ASSET_SCALE times it."""
    im = im.resize((size[0] * ASSET_SCALE, size[1] * ASSET_SCALE), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name, size)


def gen_episode_mask() -> None:
    sz = (THUMB_W * S, THUMB_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=CORNER_RADIUS * S, fill="white")
    _save(im, "episode-mask.png", (THUMB_W, THUMB_H))


def gen_episode_border() -> None:
    sz = (THUMB_W * S, THUMB_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=CORNER_RADIUS * S, outline="white", width=BORDER_STROKE * S)
    _save(im, "episode-border.png", (THUMB_W, THUMB_H))


def gen_episode_glow() -> None:
    w = (THUMB_W + GLOW_PAD * 2) * S
    h = (THUMB_H + GLOW_PAD * 2) * S
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    box = [GLOW_PAD * S, GLOW_PAD * S, GLOW_PAD * S + THUMB_W * S - 1, GLOW_PAD * S + THUMB_H * S - 1]
    outer_radius = CORNER_RADIUS * S + GLOW_PAD * S // 2
    d.rounded_rectangle(box, radius=outer_radius, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "episode-glow.png", (THUMB_W + GLOW_PAD * 2, THUMB_H + GLOW_PAD * 2))


# 6px, matching the poster card's bar rather than 7.1's 4pt. 4 was genuinely
# hard to see -- but most of that was the bar being inset, thin AND
# track-less at once, which is all fixed now. One bar height across the UI
# beats a per-card one, and at 6 both cards lose the same 2px to the focus
# border's bottom stroke.
BAR_H = 6
BAR_CAP = BAR_H // 2


def gen_episode_progress_strips() -> None:
    """Episode-card progress fill: one THUMB_W x BAR_H strip per even
    percentage, the 16:9 twin of gen_poster_assets.py's poster-progress/ set.

    Needed because the bar now sits FLUSH with the still's bottom edge
    (left, bottom and right, matching the poster card) instead of the 6px
    side / 5px bottom inset 7.1 describes. Inset, a plain rectangle was
    fine -- it never reached the corners. Flush, it would spill past the
    rounded silhouette at both ends, so each strip's alpha is multiplied by
    the matching bottom band of the same rounded-rect this card's mask uses.

    `100.png` doubles as the track: it is the full-width strip, already
    clipped to the corners, so tinting it SURFACE_TRACK gives a track that
    follows the curve without a second asset."""
    out_dir = os.path.join(_MEDIA_DIR, "episode-progress")
    os.makedirs(out_dir, exist_ok=True)
    w, h = THUMB_W * S, BAR_H * S

    clip = Image.new("L", (THUMB_W * S, THUMB_H * S), 0)
    ImageDraw.Draw(clip).rounded_rectangle(
        [0, 0, THUMB_W * S - 1, THUMB_H * S - 1], radius=CORNER_RADIUS * S, fill=255
    )
    clip_band = clip.crop((0, THUMB_H * S - h, THUMB_W * S, THUMB_H * S))

    for pct in range(0, 101, 2):
        fill_w = max(1, round(w * pct / 100))
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        radius = min(BAR_CAP * S, fill_w // 2, h // 2)
        d.rounded_rectangle([0, 0, fill_w - 1, h - 1], radius=radius, fill="white")
        if fill_w > radius:
            d.rectangle([radius, 0, fill_w - 1, h - 1], fill="white")
        im.putalpha(ImageChops.multiply(im.getchannel("A"), clip_band))
        im.resize((THUMB_W * ASSET_SCALE, max(1, BAR_H * ASSET_SCALE)), Image.LANCZOS).save(
            os.path.join(out_dir, "{0}.png".format(pct)))
    print("saved episode-progress/ (51 strips, {0}x{1})".format(THUMB_W, BAR_H))


def main() -> None:
    gen_episode_mask()
    gen_episode_border()
    gen_episode_glow()
    gen_episode_progress_strips()


if __name__ == "__main__":
    main()
