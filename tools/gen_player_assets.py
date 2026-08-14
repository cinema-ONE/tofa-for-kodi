"""Generates the player scrubber's two head textures.

Exact-size assets, not 9-patches: at 4x17 and 6x22 there is no straight
band left to stretch, and a bordered texture at that scale bulges into an
arrow (see project_kodi_9patch_needs_straight_edges). Kodi draws these
plain, at exactly the size baked in here.

Sizes are measured off the real Apple TV app, not the design spec -- though
the two agree: internal-docs/atv-reference/player-measurements.md records
4x17 focused / 6x22 dragging, and TV-DESIGN 8.2 states "4x16pt -> 6x22pt
while dragging".

Rendered white; the caller tints with colordiffuse if it ever needs to.

Dev-only tool (needs Pillow). Output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_player_assets.py
"""
import os

from PIL import Image, ImageDraw

# How many OUTPUT pixels we emit per unit of the 1920x1080 coordinate space.
# The box runs its GUI at 3840x2160, so art authored 1:1 for the coordinate
# space is upscaled 2x before it reaches the panel and every hard edge
# softens. Emitting at 2x lands it ~1:1 there and costs nothing at 1080p.
# Never apply this to 9-patch art (anything drawn with a `border=`): there
# the border slices the source AND sets the drawn corner size.
ASSET_SCALE = 2
S = 8  # supersample factor

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)

# name -> (width, height, corner radius)
_HEADS = {
    "scrub-head.png": (4, 17, 2),
    "scrub-head-drag.png": (6, 22, 3),
}

# 8.6's accent spinner for the initial-load screen. An actual arc, because
# the assets the player used before this (busy.gif / busy-back.png, ported
# from plex-for-kodi and referenced nowhere else in the app) are FULLY
# OPAQUE blocks -- 90x38 and 240x150 with no transparency. Stretched into a
# 70x70 slot and tinted with the accent, they rendered as a green square on
# a dark box, which is what shipped.
_SPINNER = "spinner-arc.png"
_SPINNER_SIZE = 64
_SPINNER_STROKE = 6
_SPINNER_SWEEP = 280  # degrees; the gap is what makes rotation legible


def gen(name: str, w: int, h: int, radius: int) -> None:
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, w * S - 1, h * S - 1], radius=radius * S,
        fill=(255, 255, 255, 255),
    )
    im = im.resize((w * ASSET_SCALE, h * ASSET_SCALE), Image.LANCZOS)
    im.save(os.path.join(_MEDIA_DIR, name))
    print(f"saved {name}  ({w}x{h} units at {ASSET_SCALE}x = {im.size[0]}x{im.size[1]}px)")


def gen_preview_shadow() -> None:
    """Drop shadow under 8.2's scrub thumbnail bubble.

    The reference app really does draw one -- clearly visible under the
    bubble in the JetKVM capture the user took, since unlike 8.3's rail the
    bubble sits over BARE VIDEO with no scrim behind it to swallow a shadow.

    Baked at the bubble's exact size plus a bleed for the blur, because a
    border-stretched rounded texture warps in Kodi (see
    project_kodi_9patch_needs_straight_edges). Full alpha here; the opacity
    is the <colordiffuse>."""
    from PIL import ImageFilter
    w, h, radius, pad, blur = 320, 180, 8, 40, 12
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (255, 255, 255, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [pad, pad, pad + w - 1, pad + h - 1], radius=radius, fill="white")
    im = im.filter(ImageFilter.GaussianBlur(blur))
    im.save(os.path.join(_MEDIA_DIR, "preview-shadow.png"))
    print("saved preview-shadow.png ({0}x{1}, blur {2})".format(
        w + 2 * pad, h + 2 * pad, blur))


def gen_rebuffer_ring() -> None:
    """8.6's determinate rebuffer ring: "46pt, accent stroke 4pt".

    Frames rather than an arc drawn at runtime, for the same reason 8.3's
    countdown ring is: Kodi has no arc primitive. 21 steps is one per 5% of
    Player.CacheLevel, which is itself only reported to the nearest
    percent."""
    out_dir = os.path.join(_MEDIA_DIR, "rebuffer-ring")
    os.makedirs(out_dir, exist_ok=True)
    size, stroke, steps = 46, 4, 20
    for step in range(steps + 1):
        n = size * S
        im = Image.new("RGBA", (n, n), (255, 255, 255, 0))
        if step:
            inset = stroke * S // 2
            ImageDraw.Draw(im).arc(
                [inset, inset, n - 1 - inset, n - 1 - inset],
                start=-90, end=-90 + 360.0 * step / steps,
                fill="white", width=stroke * S)
        im.resize((size * ASSET_SCALE, size * ASSET_SCALE), Image.LANCZOS).save(
            os.path.join(out_dir, "{0}.png".format(step)))
    print("saved rebuffer-ring/ ({0} frames, {1}x{1}, stroke {2})".format(
        steps + 1, size, stroke))


def gen_spinner() -> None:
    """An open ring, drawn white so the caller tints it with colordiffuse.

    Square canvas with the arc centred in it, because Kodi's rotate
    animation spins about the control's own centre -- an off-centre arc
    would wobble instead of spin."""
    s = _SPINNER_SIZE * S
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    inset = _SPINNER_STROKE * S // 2
    ImageDraw.Draw(im).arc(
        [inset, inset, s - 1 - inset, s - 1 - inset],
        start=-90, end=-90 + _SPINNER_SWEEP,
        fill=(255, 255, 255, 255), width=_SPINNER_STROKE * S,
    )
    im = im.resize((_SPINNER_SIZE * ASSET_SCALE, _SPINNER_SIZE * ASSET_SCALE), Image.LANCZOS)
    im.save(os.path.join(_MEDIA_DIR, _SPINNER))
    print(f"saved {_SPINNER}  ({_SPINNER_SIZE}x{_SPINNER_SIZE}, "
          f"{_SPINNER_SWEEP}deg arc, stroke {_SPINNER_STROKE})")


if __name__ == "__main__":
    for _name, (_w, _h, _r) in _HEADS.items():
        gen(_name, _w, _h, _r)
    gen_spinner()
    gen_preview_shadow()
    gen_rebuffer_ring()
