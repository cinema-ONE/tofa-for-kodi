"""Generates the rounded-rect panel background/outline textures for the
custom Sort/Filter/Quality picker dialog (resources/lib/windows/picker.py) --
same reasoning as gen_pill_assets.py, just a larger corner radius (~24px,
matching a modal sheet rather than a capsule pill). white-square-rounded.png's
baked-in ~4px radius reads as barely-rounded at this panel's scale.

Dev-only tool, not shipped with the add-on and never imported by it (needs
Pillow). Run by hand, output goes straight into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_panel_assets.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

S = 4  # supersample factor
RADIUS = 24
CANVAS = 96
OUTLINE_STROKE = 2

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def _save(im: Image.Image, name: str) -> None:
    im = im.resize((CANVAS, CANVAS), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name)


def gen_fill() -> None:
    sz = CANVAS * S
    r = RADIUS * S
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz - 1, sz - 1], radius=r, fill=(255, 255, 255, 255))
    _save(im, "panel-fill.png")


def gen_outline() -> None:
    sz = CANVAS * S
    r = RADIUS * S
    stroke = OUTLINE_STROKE * S
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        [stroke / 2, stroke / 2, sz - 1 - stroke / 2, sz - 1 - stroke / 2],
        radius=r, outline=(255, 255, 255, 255), width=stroke,
    )
    _save(im, "panel-outline.png")


def _rounded(name: str, radius: int, stroke: int | None = None) -> None:
    """One rounded-rect 9-patch whose corner radius EQUALS the border it will
    be sliced at. A 9-patch corner is drawn unscaled, so an asset whose radius
    differs from its border renders a slice of the wrong arc -- which is why
    these can't just reuse panel-fill.png (radius 24) at border=22.

    Canvas is 2*radius+2: two radii of corner plus a 2px straight band for
    the 9-patch to stretch."""
    size = radius * 2 + 2
    n = size * S
    r = radius * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if stroke is None:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=r, fill=(255, 255, 255, 255))
    else:
        # Stroked from the FULL canvas box, not inset by stroke/2: an inset
        # outline's silhouette diverges from the fill's at the cap extremes,
        # and the two get layered on the same panel.
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=r,
                            outline=(255, 255, 255, 255), width=stroke * S)
    im = im.resize((size, size), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name, im.size, "radius", radius)


def gen_card_options_assets() -> None:
    """7.2's panel (radius 22), its option rows (radius 14), the row focus
    rim, and the panel's drop shadow."""
    _rounded("panel-r22.png", 22)
    _rounded("panel-r22-outline.png", 22, stroke=1)
    _rounded("rounded-14.png", 14)
    # Row focus rim. 2px, not 1.5: 13's reduced-tier compensation widens the
    # rim 1.5 -> 2 precisely because the focus LIFT is dropped, and a
    # Kodi-class client is reduced-tier unconditionally.
    _rounded("rounded-14-outline.png", 14, stroke=2)
    _panel_shadow()


def gen_selection_panel_assets() -> None:
    """8.4's panel (radius 20) and its rows (radius 8).

    Both exist because the panel was first drawn with rounded-14.png sliced
    at border 20 and its rows at border 8 -- neither of which is 14, so both
    rendered the wrong arc and visibly bulged."""
    _rounded("rounded-20.png", 20)
    _rounded("rounded-20-outline.png", 20, stroke=1)
    _rounded("rounded-8.png", 8)
    # The scrub preview bubble's rim. It used rounded-14-outline at
    # border=8 -- 8px cropped out of a 14px arc, so the drawn corner was
    # a truncated, flatter curve and the leftover 6px of arc got
    # stretched along the edges. The bubble's own shadow is baked at
    # radius 8 (gen_player_assets.gen_preview_shadow), so 8 was always
    # the intended radius and the ASSET was the wrong one.
    _rounded("rounded-8-outline.png", 8, stroke=2)


def _panel_shadow() -> None:
    """7.2's floating-panel shadow: black at 62%, blurred 42, offset y18.
    The panel floats, which is the whole reason it may cast anything at all
    -- the one documented exception to 4's Hairline Rule that resting chrome
    casts no shadow.

    A 9-patch whose border covers the blur falloff PLUS the corner radius
    (42 + 22 = 64), so the soft corner is never stretched. Opacity is left
    at full here and applied by colordiffuse at the call site, so the 62%
    lives next to the other 7.2 alphas rather than being baked in."""
    BLUR, RADIUS = 42, 22
    border = BLUR + RADIUS
    size = border * 2 + 2
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([BLUR, BLUR, size - 1 - BLUR, size - 1 - BLUR],
                        radius=RADIUS, fill=(255, 255, 255, 255))
    im = im.filter(ImageFilter.GaussianBlur(BLUR / 2))
    path = os.path.join(_MEDIA_DIR, "panel-shadow-r22.png")
    im.save(path)
    print("saved panel-shadow-r22.png", im.size, "border", border)


def gen_person_bg() -> None:
    """7.4's full-screen vertical gradient for the person/filmography page.

    Kodi has no gradient primitive, so this is a real texture. It is 2px
    wide rather than 1px: a 1px-wide image stretched across 1920 is fine in
    principle, but some Kodi renderers sample the single column at its edge
    and band. Height is the full 1080 so the ramp is never resampled
    vertically, which is where banding would actually show.

    Endpoints are measured, not from the prose -- see PERSON_BG_* in
    skin/tokens.py. Emitted as a plain opaque RGB ramp, so the control
    needs no colordiffuse."""
    top, bottom = (0x19, 0x1A, 0x22), (0x11, 0x12, 0x16)
    h, w = 1080, 2
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        f = y / (h - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
        for x in range(w):
            px[x, y] = c
    path = os.path.join(_MEDIA_DIR, "person-bg.png")
    im.save(path)
    print("saved person-bg.png", im.size)


if __name__ == "__main__":
    gen_fill()
    gen_outline()
    gen_card_options_assets()
    gen_selection_panel_assets()
    gen_person_bg()


#: 8.4's trailing panel, sliced HORIZONTALLY into a top cap, a stretched
#: middle and a bottom cap -- the same trick gen_pill_slices.py plays on a
#: capsule, turned ninety degrees.
#:
#: WHY. A nine-patch corner cannot carry more pixels than the coordinate
#: space, because `border=N` is both the source slice and the drawn corner
#: size; on the 4K box every one is upscaled 2x. Exact art escapes that but
#: is pinned to one size, and this panel's height changes with its row count
#: (2026-08-10: giving it exact art is what drew its corners as ellipses).
#:
#: Slicing horizontally gets both. The panel's WIDTH never changes, so the
#: caps are fixed-size art and can be drawn at 2x; the middle carries no
#: curvature at all, so stretching it is free. And the seam runs across a
#: flat vertical section, which is where gen_pill_slices puts its seams too --
#: not through a corner.
PANEL_SLICE_SCALE = 2
PANEL_W = 382
PANEL_R = 22
PANEL_CAP_H = 24          # radius + 2, so the seam is clear of the arc


def gen_panel_slices() -> None:
    from PIL import ImageDraw as _D
    S = 4
    w, h, r = PANEL_W, PANEL_CAP_H, PANEL_R
    for name, stroke in (("panel-cap", None), ("panel-cap-outline", 1)):
        for edge in ("top", "bottom"):
            # Draw the WHOLE panel tall enough that both ends are true, then
            # keep only the cap. Drawing a short rounded rect instead would
            # round the seam edge as well.
            full_h = h * 3
            im = Image.new("RGBA", (w * S, full_h * S), (0, 0, 0, 0))
            box = [0, 0, w * S - 1, full_h * S - 1]
            if stroke is None:
                _D.Draw(im).rounded_rectangle(box, radius=r * S, fill="white")
            else:
                _D.Draw(im).rounded_rectangle(box, radius=r * S, outline="white",
                                              width=stroke * S)
            im = im.resize((w * PANEL_SLICE_SCALE, full_h * PANEL_SLICE_SCALE),
                           Image.LANCZOS)
            cap = h * PANEL_SLICE_SCALE
            im = (im.crop((0, 0, im.width, cap)) if edge == "top"
                  else im.crop((0, im.height - cap, im.width, im.height)))
            out = f"{name}-{edge}.png"
            im.save(os.path.join(_MEDIA_DIR, out))
            print(f"saved {out}  {im.size}  ({w}x{h} units at "
                  f"{PANEL_SLICE_SCALE}x)")
