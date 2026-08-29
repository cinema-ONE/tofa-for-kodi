"""Generates the Next Up rail's countdown ring (TV-DESIGN 8.3).

Kodi has no arc primitive and cannot draw a sweep from a number, so the ring
is a pre-rendered frame per step and Python picks the texture -- the same
technique the poster cards' progress strips use, in polar form.

8.3 asks for a ring of about 48pt with a 2-4pt stroke, the accent sweeping
from twelve o'clock over a track of the accent at 22%.
The track is a full ring in one file; each frame carries only the SWEEP, so
the two can be tinted independently at runtime (the track is the accent at
22%, the sweep the accent at full) without baking either colour in.

STEPS is the resolution of the countdown, not its length: 8.3's countdown is
a 20,000ms hard contract, and the ticker that drives it runs at 0.2s, so 40
frames gives a visibly smooth sweep at one frame per 500ms.

Dev-only tool (needs Pillow) -- run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/nextup-ring/.

Usage:
    python3 tools/gen_nextup_assets.py
"""
import os

from PIL import Image, ImageChops, ImageDraw

# How many OUTPUT pixels we emit per unit of the 1920x1080 coordinate space.
# The box runs its GUI at 3840x2160, so art authored 1:1 for the coordinate
# space is upscaled 2x before it reaches the panel and every hard edge
# softens. Emitting at 2x lands it ~1:1 there and costs nothing at 1080p.
# Never apply this to 9-patch art (anything drawn with a `border=`): there
# the border slices the source AND sets the drawn corner size.
ASSET_SCALE = 2
S = 4  # supersample factor

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)

RING = 48        # 8.3's "~48pt", 1:1 on our 1920 canvas
STROKE = 3       # within 8.3's 2-4pt
STEPS = 40

# The rail: 8.3's "40% of screen width, clamp 440-860" and "padding 54".
# 780 rather than a literal 40% of 1920 (768) because 780 - 2*54 leaves 672,
# which is EXACTLY 16:9 at 378 -- so the hero still needs no rounding and
# lands on whole pixels. Still inside the clamp, and 0.6% off the 40%.
RAIL_W = 780
RAIL_PAD = 54
STILL_W = RAIL_W - 2 * RAIL_PAD   # 672
STILL_H = STILL_W * 9 // 16       # 378
STILL_RADIUS = 16                 # 8.3, verbatim

# The scrim reaches full strength BEFORE the rail starts, so it is wider
# than the rail and hangs SCRIM_RAMP px off its leading edge. Ramping inside
# the rail instead (over the 54px padding) is what the first cut did, and it
# read as a hard vertical wall slicing through whatever was on screen --
# 8.3 asks for an edge scrim, not a letterbox bar.
SCRIM_RAMP = 260
SCRIM_W = RAIL_W + SCRIM_RAMP


def _ring_image(sweep_degrees: float) -> Image.Image:
    size = RING * S
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    if sweep_degrees <= 0:
        return im.resize((RING * ASSET_SCALE, RING * ASSET_SCALE), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    inset = STROKE * S // 2
    box = [inset, inset, size - 1 - inset, size - 1 - inset]
    # -90 is 12 o'clock in Pillow's convention too, so 8.3's start angle
    # carries over as written.
    d.arc(box, start=-90, end=-90 + sweep_degrees, fill="white", width=STROKE * S)
    return im.resize((RING * ASSET_SCALE, RING * ASSET_SCALE), Image.LANCZOS)


def gen_countdown_ring() -> None:
    out_dir = os.path.join(_MEDIA_DIR, "nextup-ring")
    os.makedirs(out_dir, exist_ok=True)
    for step in range(STEPS + 1):
        im = _ring_image(360.0 * step / STEPS)
        im.save(os.path.join(out_dir, "{0}.png".format(step)))
    # The unfilled track: a complete ring, tinted down at runtime.
    _ring_image(359.999).save(os.path.join(_MEDIA_DIR, "nextup-ring-track.png"))
    print("saved nextup-ring/ ({0} frames, {1}x{1}) + nextup-ring-track.png".format(
        STEPS + 1, RING))


def gen_still_mask() -> None:
    """Rounded-corner mask for the hero still.

    Its own file at its own size rather than a border-stretched shared
    rounded texture: white-square-rounded.png only ever has a ~4px radius
    however it is sliced, so 8.3's 16 has to be baked at the final size."""
    size = (STILL_W * S, STILL_H * S)
    im = Image.new("RGBA", size, (255, 255, 255, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=STILL_RADIUS * S, fill="white")
    im = im.resize((STILL_W * ASSET_SCALE, STILL_H * ASSET_SCALE), Image.LANCZOS)
    im.save(os.path.join(_MEDIA_DIR, "nextup-still-mask.png"))
    print("saved nextup-still-mask.png ({0}x{1}, r{2})".format(
        STILL_W, STILL_H, STILL_RADIUS))


# 8.3 also asks for a soft black shadow at about 50%, radius 24, under the
# still. Deliberately
# NOT generated: the rail's own edge scrim already puts the still on an
# 84%-black backing, so a 50%-black shadow has almost nothing left to
# darken. Measured on a live frame it moved the pixels just outside the
# still from RGB 11.7 to 11.1 out of 255 -- an asset that provably renders
# nothing. The hairline below, on the same edge, lifts it 81 -> 88 and is
# what actually separates the still from the scrim.


def gen_still_outline() -> None:
    """8.3's hairline on the hero still: white 8%, same radius as the mask.

    A ring, not a filled rect, so it can be laid over the still and tinted
    to the 8% at render time."""
    size = (STILL_W * S, STILL_H * S)
    im = Image.new("RGBA", size, (255, 255, 255, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=STILL_RADIUS * S,
        outline="white", width=S)
    im.resize((STILL_W * ASSET_SCALE, STILL_H * ASSET_SCALE), Image.LANCZOS).save(
        os.path.join(_MEDIA_DIR, "nextup-still-outline.png"))
    print("saved nextup-still-outline.png ({0}x{1}, 1px hairline)".format(
        STILL_W, STILL_H))


# 8.10's episode-drawer row still: 16:9 at the drawer's own row height.
DRAWER_STILL_W = 140
DRAWER_STILL_H = 79
DRAWER_STILL_RADIUS = 8


def gen_drawer_still_mask() -> None:
    """Rounded mask for an episode row's still. Its own file at its own size
    for the same reason the Next Up one is: a shared rounded texture only
    ever carries a ~4px radius however it is sliced."""
    size = (DRAWER_STILL_W * S, DRAWER_STILL_H * S)
    im = Image.new("RGBA", size, (255, 255, 255, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=DRAWER_STILL_RADIUS * S, fill="white")
    im.resize((DRAWER_STILL_W * ASSET_SCALE, DRAWER_STILL_H * ASSET_SCALE), Image.LANCZOS).save(
        os.path.join(_MEDIA_DIR, "drawer-still-mask.png"))
    print("saved drawer-still-mask.png ({0}x{1}, r{2})".format(
        DRAWER_STILL_W, DRAWER_STILL_H, DRAWER_STILL_RADIUS))


DRAWER_BAR_H = 6
DRAWER_BAR_CAP = 3


def gen_drawer_progress_strips() -> None:
    """One 140x6 strip per even percent, for the drawer row's progress bar.

    A strip set rather than a width: Kodi does NOT evaluate $INFO inside a
    <width>, so a bar sized from a ListItem property silently renders at the
    parent's full width instead. The same reason the poster and episode
    cards use episode-progress/ -- this is that set at the drawer's size.

    Alpha is clipped to the still's own rounded bottom band so a full bar
    cannot spill past the corners, exactly as gen_episode_assets.py does.
    100.png doubles as the track."""
    out_dir = os.path.join(_MEDIA_DIR, "drawer-progress")
    os.makedirs(out_dir, exist_ok=True)
    w, h = DRAWER_STILL_W * S, DRAWER_BAR_H * S
    clip = Image.new("L", (DRAWER_STILL_W * S, DRAWER_STILL_H * S), 0)
    ImageDraw.Draw(clip).rounded_rectangle(
        [0, 0, DRAWER_STILL_W * S - 1, DRAWER_STILL_H * S - 1],
        radius=DRAWER_STILL_RADIUS * S, fill=255)
    band = clip.crop((0, DRAWER_STILL_H * S - h, DRAWER_STILL_W * S, DRAWER_STILL_H * S))
    for pct in range(0, 101, 2):
        fill_w = max(1, round(w * pct / 100))
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        radius = min(DRAWER_BAR_CAP * S, fill_w // 2, h // 2)
        d.rounded_rectangle([0, 0, fill_w - 1, h - 1], radius=radius, fill="white")
        if fill_w > radius:
            d.rectangle([radius, 0, fill_w - 1, h - 1], fill="white")
        im.putalpha(ImageChops.multiply(im.getchannel("A"), band))
        im.resize((DRAWER_STILL_W, DRAWER_BAR_H), Image.LANCZOS).save(
            os.path.join(out_dir, "{0}.png".format(pct)))
    print("saved drawer-progress/ (51 strips, {0}x{1})".format(
        DRAWER_STILL_W, DRAWER_BAR_H))


# 8.2's scrub bubble shows ONE cell of a QuickView sprite sheet, and Kodi
# rounds a corner only with a diffuse mask -- which is stretched to the
# whole control, i.e. the whole sheet. So the mask is a GRID of rounded
# rects, one per cell, at the sheet's rendered size: whichever cell the clip
# window lands on then has its own rounded corners.
TILE_GRID = 10               # the server's tile_width/tile_height
TILE_CELL_W = 320            # the 320-wide track, which is what we request
TILE_CELL_H = 180
TILE_CELL_RADIUS = 8         # 8.2, verbatim


def gen_tile_grid_mask() -> None:
    w, h = TILE_CELL_W * TILE_GRID, TILE_CELL_H * TILE_GRID
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    for row in range(TILE_GRID):
        for col in range(TILE_GRID):
            x0, y0 = col * TILE_CELL_W, row * TILE_CELL_H
            d.rounded_rectangle(
                [x0, y0, x0 + TILE_CELL_W - 1, y0 + TILE_CELL_H - 1],
                radius=TILE_CELL_RADIUS, fill="white")
    im.save(os.path.join(_MEDIA_DIR, "tile-grid-mask.png"))
    print("saved tile-grid-mask.png ({0}x{1}, {2}x{2} cells of {3}x{4} r{5})".format(
        w, h, TILE_GRID, TILE_CELL_W, TILE_CELL_H, TILE_CELL_RADIUS))


def gen_scrim() -> None:
    """8.3's edge scrim: transparent at the screen-facing edge, opaque by
    the time the content starts.

    White, not black -- the alpha ramp is the whole content of the file and
    the colour comes from <colordiffuse> at render time, which is what lets
    the same texture carry 8.3's "black 84%" without the number being baked
    into a PNG where nobody would find it."""
    im = Image.new("RGBA", (SCRIM_W, 16))
    px = im.load()
    for x in range(SCRIM_W):
        # smoothstep, not linear: a linear alpha ramp has a visible kink
        # where it meets the flat section.
        u = min(1.0, x / float(SCRIM_RAMP))
        a = int(round(255.0 * u * u * (3.0 - 2.0 * u)))
        for y in range(16):
            px[x, y] = (255, 255, 255, a)
    im.save(os.path.join(_MEDIA_DIR, "nextup-scrim.png"))
    print("saved nextup-scrim.png ({0}x16, ramp {1})".format(SCRIM_W, SCRIM_RAMP))


def main() -> None:
    gen_countdown_ring()
    gen_still_mask()
    gen_still_outline()
    gen_drawer_still_mask()
    gen_drawer_progress_strips()
    gen_tile_grid_mask()
    gen_scrim()


if __name__ == "__main__":
    main()
