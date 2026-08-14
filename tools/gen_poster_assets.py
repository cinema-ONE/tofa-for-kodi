"""Generates the poster-card assets for the Apple-TV-matching redesign:
rounded corners, a track-less progress bar with a rounded left cap, and a
soft focus glow -- tracked as not-real-designed-assets on
https://github.com/cinema-ONE/tofa-kodi/issues/6.

Dev-only tool (needs Pillow, which Kodi's own Python environment doesn't
have) -- run by hand when one of these needs tweaking, output goes
straight into plugin.video.tofa/resources/skins/Main/media/. See
resources/lib/skin/fragments.py:poster_card() for how each is used.

Measurements this is built from (pixel-measured against a live Apple TV
Home screenshot): poster corner radius ~20px on a 248x372 card, focused
or not; progress bar has no visible track, ~10px thick, inset ~6px from
the poster's bottom edge, rounded left end, flat/square right end (the
fill cutoff); focus glow is a soft ~20-30px halo with gradual falloff,
accent-tinted.

The progress bar can't just be a single 9-slice texture stretched to a
data-bound width -- Kodi's WindowXML `<width>` tags don't accept $INFO[]
expressions, so there's no way to size a *control* by list-item
percentage. `progress/<even-pct>.png` (51 pre-rendered flat-fill strips,
already shipped, shared by Player's seekbar and Detail's hero bar at their
own different stretched sizes) is this codebase's existing answer to that
constraint. A flat rectangle stretches to any size with zero distortion,
which is exactly why sharing one folder across differently-sized controls
has worked so far -- but a rounded cap does NOT stretch cleanly, so poster
cards get their own `poster-progress/<even-pct>.png` folder instead of
resizing the shared one (which would visibly distort Player/Detail's
bars).

Usage:
    python3 tools/gen_poster_assets.py
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Supersample factor for the drawing master, and how many OUTPUT pixels we
# emit per unit of the 1920x1080 coordinate space.
#
# ASSET_SCALE exists because the coordinate space is not the screen. The
# CoreELEC box runs its GUI at 3840x2160, so Kodi draws a 252-wide poster
# into 504 physical pixels; a texture authored at 252 is upscaled 2x and its
# 2px border lands as a soft 4px smear. Emitting at 2x puts these back at
# roughly 1:1 on a 4K panel and costs nothing at 1080p, where Kodi scales
# them back down.
#
# This is only sound for textures Kodi scales WHOLE. It is NOT applied to
# 9-patch art (anything drawn with a `border=` attribute): there the border
# value slices the source in texture pixels AND sets the drawn corner size,
# so a bigger texture would need a bigger border, which would draw a
# geometrically bigger corner. See tools/gen_capsule_pill_assets.py.
ASSET_SCALE = 2
S = 4 * ASSET_SCALE  # supersample factor, kept at 4x the emitted size

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)

POSTER_W, POSTER_H = 252, 378  # keep in step with skin/tokens.py

# Corner radii come from the spec, not from eyeballing the app. 4 puts
# "TV poster cards" at 14 and 7.9.3 states the open card's outright:
# "its width falls out of 16:9 (378 -> 672, radius 12)".
#
# These are directly applicable rather than needing the half-density scaling
# 3/6's numbers do, because 7.9's own geometry is already our canvas:
# it specifies a 252x378 poster (ours 248x372) and a 672x378 open card
# (ours exactly that). Both previously sat at a hand-fitted 16.
POSTER_RADIUS = 14
DISCOVER_WIDE_RADIUS = 12
BORDER_STROKE = 2

# tokens.CANVAS (0xFF030B10) as RGB. Scrims are canvas-tinted, not black --
# black over a blue-tinted canvas greys the artwork's shadows.
CANVAS_RGB = (0x03, 0x0B, 0x10)

# 6 bottom-aligns the progress bar inside the poster and allows it 3-6px of
# height. The top of that range -- the real Apple TV app measures 6px too (Continue Watching,
# JetKVM capture 2026-08-02, fill spanning rows 973-978). Was 10, which was
# nobody's number.
BAR_W, BAR_H = POSTER_W, 6  # spans the poster's full width
BAR_CAP = BAR_H // 2  # pill-style rounded left end

BADGE_W, BADGE_H = 52, 28
BADGE_RADIUS = 8
BADGE_STROKE = 1  # dedicated exact-size asset, thin 1px stroke -- the
# shared white-outline-rounded.png's 4px-thick 9-slice cap looked heavy
# at this badge's small size.

# Room poster_card() carves out of its item cell for the glow to bleed
# into, uniform on all 4 sides. Bounded by the top: the poster/badge/
# progress-bar block shifts down by this amount, and that shift plus the
# poster's height plus the caption block must still fit the 438-tall
# cell -- ceiling is 12px, 10 leaves a couple px of margin.
GLOW_PAD = 10

# Discover's wide focused card (fragments.py:discover_card).
DISCOVER_WIDE_W, DISCOVER_WIDE_H = 672, 378

# 7.5's collections tile (fragments.py:collection_card) -- the one landscape
# 16:9 tile in an app of 2:3 portraits. Keep in step with tokens.py's
# COLLECTION_TILE_W / COLLECTION_TILE_H / COLLECTION_RADIUS.
COLLECTION_W, COLLECTION_H = 448, 252
COLLECTION_RADIUS = 14
GLOW_ALPHA = 90  # peak opacity (0-255) of the glow's uniform interior --
# flat translucent wash near the border, falloff reserved for the outer
# edge only, fading fully to invisible there.


def _save(im: Image.Image, name: str, size: tuple[int, int]) -> None:
    """`size` is in 1080-space units; the file lands at ASSET_SCALE times it."""
    im = im.resize((size[0] * ASSET_SCALE, size[1] * ASSET_SCALE), Image.LANCZOS)
    path = os.path.join(_MEDIA_DIR, name)
    im.save(path)
    print("saved", name, im.size, "(=%dx%d @%dx)" % (size[0], size[1], ASSET_SCALE))


def gen_poster_mask() -> None:
    """White-opaque rounded-rect on transparent, exactly poster-sized --
    applied as a `diffuse` mask over both the dynamic poster art texture
    and the muted placeholder tile, so their square corners get clipped to
    match Apple TV's rounded ones. 1:1 sized to the control it masks (no
    9-slice/border needed), avoiding any stretch-distortion question."""
    sz = (POSTER_W * S, POSTER_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=POSTER_RADIUS * S, fill="white")
    _save(im, "poster-mask.png", (POSTER_W, POSTER_H))


def gen_discover_wide_mask() -> None:
    """Mask for Discover's WIDE focused card (672x378).

    Same 1:1 rule as poster-mask.png, and the reason this file exists at all:
    reusing the 248x372 poster mask on a 672-wide control let Kodi stretch it,
    turning each 16px corner into a 43x16 ellipse -- a corner so shallow the
    card read as square. A mask must be built at the size it masks."""
    W, H = DISCOVER_WIDE_W, DISCOVER_WIDE_H
    sz = (W * S, H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=DISCOVER_WIDE_RADIUS * S, fill="white")
    _save(im, "discover-wide-mask.png", (W, H))


def gen_discover_wide_border() -> None:
    """Thin focus border for Discover's wide card, exactly card-sized.

    Same 1:1 rule and the same radius as the mask beside it, so the border
    and the artwork's rounded edge can't disagree -- which is the whole point
    of gen_poster_border() existing for the portrait card."""
    W, H = DISCOVER_WIDE_W, DISCOVER_WIDE_H
    sz = (W * S, H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        [0, 0, sz[0] - 1, sz[1] - 1],
        radius=DISCOVER_WIDE_RADIUS * S, outline="white", width=BORDER_STROKE * S,
    )
    _save(im, "discover-wide-border.png", (W, H))


def gen_discover_wide_glow() -> None:
    """Focus glow for Discover's wide card.

    card-glow.png is built around the 248x372 poster; stretched to the wide
    card its corner halo turns elliptical and stops following the card's own
    rounded corner. Same construction as gen_card_glow(), just at this card's
    size."""
    W, H = DISCOVER_WIDE_W, DISCOVER_WIDE_H
    w = (W + GLOW_PAD * 2) * S
    h = (H + GLOW_PAD * 2) * S
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    box = [GLOW_PAD * S, GLOW_PAD * S, GLOW_PAD * S + W * S - 1, GLOW_PAD * S + H * S - 1]
    d.rounded_rectangle(box, radius=DISCOVER_WIDE_RADIUS * S + GLOW_PAD * S // 2, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "discover-wide-glow.png", (W + GLOW_PAD * 2, H + GLOW_PAD * 2))


def gen_poster_progress_strips() -> None:
    """Poster-card progress fill: one POSTER_W x BAR_H image per even percentage
    (0-100), matching home.py's existing rounding-to-even bucketing.
    Each strip is white, rounded-left-cap, flat/square right (the fill
    cutoff), filled from x=0 to the percentage's cutoff x, transparent
    beyond it -- no track. `resources/lib/windows/home.py` points
    ListItem.Property(progress_fill) at `poster-progress/<pct>.png`;
    runtime colordiffuse tints white -> the current accent.

    Sits flush with the poster's bottom edge (posy = POSTER_H - BAR_H in
    fragments.py), so a plain rectangular strip would spill past the
    poster-mask's rounded corners at both bottom ends. Fixed by
    multiplying each strip's alpha by the matching bottom band of
    poster-mask.png's own rounded-rect shape, clipping the strip to the
    poster's corner curve."""
    out_dir = os.path.join(_MEDIA_DIR, "poster-progress")
    os.makedirs(out_dir, exist_ok=True)
    w, h = BAR_W * S, BAR_H * S

    clip = Image.new("L", (POSTER_W * S, POSTER_H * S), 0)
    cd = ImageDraw.Draw(clip)
    cd.rounded_rectangle(
        [0, 0, POSTER_W * S - 1, POSTER_H * S - 1], radius=POSTER_RADIUS * S, fill=255
    )
    clip_band = clip.crop((0, POSTER_H * S - h, POSTER_W * S, POSTER_H * S))

    for pct in range(0, 101, 2):
        fill_w = max(1, round(w * pct / 100))
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if fill_w > 0:
            d = ImageDraw.Draw(im)
            radius = min(BAR_CAP * S, fill_w // 2, h // 2)
            d.rounded_rectangle([0, 0, fill_w - 1, h - 1], radius=radius, fill="white")
            if fill_w > radius:
                d.rectangle([radius, 0, fill_w - 1, h - 1], fill="white")
        alpha = ImageChops.multiply(im.getchannel("A"), clip_band)
        im.putalpha(alpha)
        im = im.resize((BAR_W * ASSET_SCALE, max(1, BAR_H * ASSET_SCALE)), Image.LANCZOS)
        im.save(os.path.join(out_dir, "{0}.png".format(pct)))
    print("saved poster-progress/ (51 strips, {0}x{1})".format(BAR_W, BAR_H))


def gen_poster_border() -> None:
    """Focus-border outline, exactly poster-sized (no 9-slice/border attr
    -- same reasoning as gen_poster_mask()), replacing the old shared
    white-outline-rounded.png (border=8) whose baked-in corner radius was
    only ~5px against this control's old un-rounded corners -- now needs
    to match the mask's radius exactly or the border and the art's
    rounded edge visibly disagree."""
    sz = (POSTER_W * S, POSTER_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=POSTER_RADIUS * S, outline="white", width=BORDER_STROKE * S)
    _save(im, "poster-border.png", (POSTER_W, POSTER_H))


def gen_badge_outline() -> None:
    """Rating-badge outline, exactly badge-sized (same reasoning as
    gen_poster_border()) -- replaces the shared white-outline-rounded.png
    (border=4, a 4px-thick 9-slice cap) with a thin 1px stroke sized to
    just this 52x28 badge."""
    sz = (BADGE_W * S, BADGE_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sz[0] - 1, sz[1] - 1], radius=BADGE_RADIUS * S, outline="white", width=BADGE_STROKE * S)
    _save(im, "badge-outline.png", (BADGE_W, BADGE_H))


# Circular person tiles, at EVERY size the app draws one. Kept in step with
# fragments.py:person_card()'s callers by hand -- this tool is dev-only and
# deliberately imports nothing from the add-on.
#
#   190  tokens.CAST_PHOTO -- Detail's Cast & Crew grids
#   130  Search's Actors row (screens.py, photo_size=130)
#
# Two sizes and therefore two sets of files, named for the size like
# capsule-h<N>.png, because that is the whole point of an exact-size asset:
# Kodi scales a texture's stroke along with the texture, so ONE 190px ring
# drawn into a 130px control renders its 2px stroke at 1.4px. That is what
# shipped -- Search's actors wore a visibly finer ring than Detail's cast,
# and their halo's fade band was squeezed into 7 of the 10px the control
# reserves for it, leaving a hard-edged collar of flat accent around each
# photo. The single-size assets are gone; the names carry the size now so
# the next person_card() caller at a new size cannot silently reuse one.
#   180  Search's Actors shelf (7.3, "circular headshots 180pt"; the live
#        app measures 181 on a 256 pitch). It was 130 -- nobody's number,
#        ~28% under both the spec and the app.
PERSON_PHOTOS = (190, 180)


def gen_person_border(photo: int) -> None:
    """The focus ring for a circular person tile, at BORDER_STROKE like every
    other focus border in the UI.

    Its own EXACT-SIZE asset rather than the shared circle-outline.png,
    which is a 400px texture with a 7px stroke: scaled down to a 200px
    control that stroke renders at 4px, twice the 2px a focused poster
    gets, and the two sit one screen apart. Kodi scales a texture's stroke
    along with the texture, so the only way to pin a stroke width is to
    author the asset at the size it will be drawn -- the same reason
    poster-border.png is authored at POSTER_W x POSTER_H.

    Authored at the PHOTO's own size, so the caller draws it over the photo
    and the ring lands ON that edge, the way a focused poster's border sits
    on the poster. It used to be 10px larger, drawn on a box grown around
    the photo, which floated the ring out in the halo band with a visible
    gap of background between picture and rim -- it read as a loose hoop
    around the tile rather than as the tile being focused. The halo still
    fades outward from there (gen_person_glow), which is the arrangement
    measured on the real app."""
    size = photo * S
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], outline="white", width=BORDER_STROKE * S)
    _save(im, "person-border-{0}.png".format(photo), (photo, photo))


def gen_person_glow(photo: int) -> None:
    """The circular sibling of gen_card_glow(), for a focused cast or crew
    tile.

    Measured on the real Apple TV app 2026-08-01 (Hugo, Cast & Crew, first
    tile focused): the accent ring is wrapped in a soft teal halo fading
    outward over roughly 18px. We had no glow there at all -- posters,
    episodes and Discover's wide cards each got one and the round tiles
    never did.

    Same construction as the rounded-rect version, so the whole UI's focus
    halo is one look: a FILLED shape at the glow's outer extent, blurred,
    then flattened to GLOW_ALPHA. A filled shape blurred this way holds
    near-constant alpha away from its edge and ramps down only within a
    blur radius of the boundary, which is what gives "uniform interior,
    fades only at the outside" -- a stroked ring would need its inner and
    outer fades tracked separately, and the inner half is covered by the
    photo anyway."""
    size = (photo + GLOW_PAD * 2) * S
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    # The filled disc reaches half the pad beyond the photo, exactly as the
    # card version's outer_radius does, so both fade over the same distance.
    inset = (GLOW_PAD * S) // 2
    d.ellipse([inset, inset, size - 1 - inset, size - 1 - inset], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "person-glow-{0}.png".format(photo),
          (photo + GLOW_PAD * 2, photo + GLOW_PAD * 2))


# 7.3's Top Result hero poster. A DIFFERENT size from the grid poster above,
# not a variant of it: the spec says "bare poster 220x330pt" and the live
# Apple TV measures exactly that (ratio 0.667), against the grid card's
# 252x378. Its own mask/border/glow/placeholder, for the same reason
# person-border ships one file per photo size -- Kodi scales a texture's
# stroke and corner radius with the texture, so reusing the 252-wide art here
# would render a 12.2px radius and a 1.7px border instead of 14 and 2.
TOP_RESULT_W, TOP_RESULT_H = 220, 330


def gen_top_result_assets() -> None:
    """Mask, focus border and focus glow for the Top Result's bare poster."""
    sz = (TOP_RESULT_W * S, TOP_RESULT_H * S)
    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, sz[0] - 1, sz[1] - 1], radius=POSTER_RADIUS * S, fill="white")
    _save(im, "top-result-mask.png", (TOP_RESULT_W, TOP_RESULT_H))

    im = Image.new("RGBA", sz, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, sz[0] - 1, sz[1] - 1], radius=POSTER_RADIUS * S,
        outline="white", width=BORDER_STROKE * S)
    _save(im, "top-result-border.png", (TOP_RESULT_W, TOP_RESULT_H))

    w = (TOP_RESULT_W + GLOW_PAD * 2) * S
    h = (TOP_RESULT_H + GLOW_PAD * 2) * S
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [GLOW_PAD * S, GLOW_PAD * S,
         GLOW_PAD * S + TOP_RESULT_W * S - 1, GLOW_PAD * S + TOP_RESULT_H * S - 1],
        radius=POSTER_RADIUS * S + GLOW_PAD * S // 2, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "top-result-glow.png",
          (TOP_RESULT_W + GLOW_PAD * 2, TOP_RESULT_H + GLOW_PAD * 2))


# The nav bar's profile avatar sits on the Home hero's own artwork, which can
# be anything from black to a sunlit face, so it needs to carry its own
# separation. 4 allows floating chrome a soft, large shadow, but only where
# it floats over artwork -- this is that case, and the only one in the nav row.
#
# Every number below is FITTED to the real Apple TV, not chosen: a frame was
# captured with the hero on a bright shot (2026-08-06) and the shadow's alpha
# sampled radially outward from the 64px circle, in eight directions. It is
# bottom-weighted -- 0.27 alpha just below the circle against 0.15 just above
# -- and gone by 16px out. A blurred disc offset 3px down reproduces that
# profile to within 0.005 alpha at every sample.
AVATAR_SIZE = 64
AVATAR_SHADOW_PAD = 16
_AVATAR_SHADOW_DISC_R = 32
_AVATAR_SHADOW_BLUR = 7
_AVATAR_SHADOW_ALPHA = 128   # 0.50, the disc's interior before the avatar covers it
_AVATAR_SHADOW_DY = 3


def gen_avatar_shadow() -> None:
    """Soft drop shadow behind the nav bar's profile avatar."""
    size = (AVATAR_SIZE + AVATAR_SHADOW_PAD * 2) * S
    mask = Image.new("L", (size, size), 0)
    centre = size / 2.0
    cy = centre + _AVATAR_SHADOW_DY * S
    r = _AVATAR_SHADOW_DISC_R * S
    ImageDraw.Draw(mask).ellipse(
        [centre - r, cy - r, centre + r, cy + r], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(_AVATAR_SHADOW_BLUR * S))
    mask = mask.point(lambda v: v * _AVATAR_SHADOW_ALPHA // 255)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.putalpha(mask)
    _save(im, "avatar-shadow.png",
          (AVATAR_SIZE + AVATAR_SHADOW_PAD * 2,) * 2)


def gen_collection_mask() -> None:
    """Rounded-corner mask for 7.5's collections tile.

    There was already a collection-mask.png, but it was authored 1:1 -- the
    only mask in the card family that was, every other one having been moved
    to ASSET_SCALE. On the 4K box Kodi draws this 448-wide tile into 896
    physical pixels, so a 1:1 mask is upscaled 2x and its 14px corner arrives
    as a soft smear while the poster beside it stays crisp. Same file name,
    same geometry, twice the pixels."""
    sz = (COLLECTION_W * S, COLLECTION_H * S)
    im = Image.new("RGBA", sz, (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        [0, 0, sz[0] - 1, sz[1] - 1], radius=COLLECTION_RADIUS * S, fill="white")
    _save(im, "collection-mask.png", (COLLECTION_W, COLLECTION_H))


def gen_collection_glow() -> None:
    """The collections tile's focus halo -- the last card in the family that
    did not have one.

    Posters, episodes, Discover's wide cards and (since 2026-08-01) the round
    person tiles all get an accent halo on focus; the collections tile got
    only a rim, so focusing one read as a flatter, cheaper state than
    focusing anything else in the app. Same construction as gen_card_glow(),
    just this tile's shape: a FILLED rounded-rect at the glow's outer extent,
    blurred, flattened to GLOW_ALPHA, so the interior stays near-constant and
    the ramp lives in the outer GLOW_PAD.

    Unlike the poster row, the collections grid has real slack around each
    tile (COLLECTION_GAP_X 30, GAP_Y 44), so the glow does not have to be
    borrowed out of the cell -- collection_card() draws it at -GLOW_PAD and
    the gap absorbs it."""
    w = (COLLECTION_W + GLOW_PAD * 2) * S
    h = (COLLECTION_H + GLOW_PAD * 2) * S
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    box = [GLOW_PAD * S, GLOW_PAD * S,
           GLOW_PAD * S + COLLECTION_W * S - 1, GLOW_PAD * S + COLLECTION_H * S - 1]
    d.rounded_rectangle(
        box, radius=COLLECTION_RADIUS * S + GLOW_PAD * S // 2, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "collection-glow.png",
          (COLLECTION_W + GLOW_PAD * 2, COLLECTION_H + GLOW_PAD * 2))


def gen_card_glow() -> None:
    """Soft accent-tintable focus glow that bleeds *outward* beyond the
    card's own border, matching Apple TV's soft halo (poster+border draw
    on top and cover the inward half, leaving only the outward-fading
    glow visible) -- uniform, flat translucency near the border, fading
    only at the true outer edge, uniformly on all 4 sides.

    The poster row is a `<list>` with itemwidth/itemheight exactly
    matching the itemlayout's declared size (zero slack), so Kodi clips
    each item strictly to its cell -- anything positioned outside it
    never draws. poster_card() wraps its poster/border/badge/progress-bar
    block in a group offset by (GLOW_PAD, GLOW_PAD) to borrow real but
    limited existing cell slack (296-248=48px horizontal either side of
    the poster) rather than growing the cell, which would ripple into
    every row-to-row spacing constant and row-slide offset across 4
    screens.

    Draws a *filled* rounded-rect (not a stroke) covering the glow's full
    outer extent, blurs it, then scales alpha down to a flat interior
    level -- a filled shape blurred this way stays near-constant alpha
    away from its edges and only ramps down within one blur radius of the
    boundary, giving "uniform interior, fades to zero only at the
    outside" without needing to separately track inner/outer fade
    regions the way a stroke would.

    GLOW_PAD=10 on all sides is the largest uniform value that fits: the
    top pad shifts the poster (and captions, to keep their gap looking
    consistent) down within the cell, and poster_top(GLOW_PAD) +
    poster_height(372) + caption_block(54) must not exceed the cell's
    438px -- ceiling is 12px, 10 leaves a couple px of margin. The bottom
    pad has no such ceiling (the glow renders *underneath* the caption
    text, since it draws before the caption labels in z-order) but is
    kept equal to the other 3 sides for a non-lopsided halo rather than
    used to its full ~50px budget."""
    w = (POSTER_W + GLOW_PAD * 2) * S
    h = (POSTER_H + GLOW_PAD * 2) * S
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    box = [GLOW_PAD * S, GLOW_PAD * S, GLOW_PAD * S + POSTER_W * S - 1, GLOW_PAD * S + POSTER_H * S - 1]
    outer_radius = POSTER_RADIUS * S + GLOW_PAD * S // 2
    d.rounded_rectangle(box, radius=outer_radius, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(GLOW_PAD * S // 2))
    mask = mask.point(lambda v: v * GLOW_ALPHA // 255)
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(mask)
    _save(im, "card-glow.png", (POSTER_W + GLOW_PAD * 2, POSTER_H + GLOW_PAD * 2))


def gen_discover_open_scrim() -> None:
    """The open card's legibility scrim (672x378, exact card size).

    TV-DESIGN 7.9.4 is specific and explains itself: the scrim runs
    left-to-right rather than bottom-up, because the copy sits in the left
    third and dimming the far corner only dulls artwork that no text ever
    covers. We shipped a bottom-up fade, which
    dims the full width of the bottom edge including the right half where no
    text ever lands.

    Two gradients, screened together:
      horizontal  92% -> 72% at 34% -> 12% at 68% -> clear
      bottom-up   55% at the bottom edge -> clear 44% of the way up
    then the whole thing scaled by the shipped strength dial 0.6. The dial is
    not decoration: at full strength the one open card is the only filtered
    artwork in its row and reads dimmer than the plain posters either side of
    it, which is the consistency question this card always has to answer.

    Canvas-tinted rather than black, per 7.9.4's "canvas-tinted stops" --
    a black scrim over a blue-tinted canvas greys the artwork's shadows.

    Built 1:1 because it's drawn through discover-wide-mask.png; a stretched
    gradient would drag the mask's corners with it (the same trap
    gen_discover_wide_mask exists to avoid)."""
    W, H = DISCOVER_WIDE_W, DISCOVER_WIDE_H
    STRENGTH = 0.6

    def _ramp(t: float, stops: list[tuple[float, float]]) -> float:
        """Piecewise-linear interpolation through (position, alpha) stops."""
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if t <= p1:
                span = p1 - p0
                return a0 if span <= 0 else a0 + (a1 - a0) * (t - p0) / span
        return stops[-1][1]

    h_stops = [(0.0, 0.92), (0.34, 0.72), (0.68, 0.12), (1.0, 0.0)]
    v_stops = [(0.0, 0.0), (0.56, 0.0), (1.0, 0.55)]

    im = Image.new("RGBA", (W, H), CANVAS_RGB + (0,))
    alpha = Image.new("L", (W, H))
    px = alpha.load()
    for x in range(W):
        h = _ramp(x / (W - 1), h_stops)
        for y in range(H):
            v = _ramp(y / (H - 1), v_stops)
            # Screen the two so neither can push the other past opaque.
            px[x, y] = int(round(255 * STRENGTH * (1.0 - (1.0 - h) * (1.0 - v))))
    im.putalpha(alpha)
    _save(im, "discover-open-scrim.png", (W, H))


def main() -> None:
    gen_poster_mask()
    gen_discover_wide_mask()
    gen_discover_wide_border()
    gen_discover_wide_glow()
    gen_discover_open_scrim()
    gen_poster_progress_strips()
    gen_poster_border()
    gen_badge_outline()
    gen_card_glow()
    for photo in PERSON_PHOTOS:
        gen_person_glow(photo)
        gen_person_border(photo)
    gen_top_result_assets()
    gen_avatar_shadow()
    gen_collection_mask()
    gen_collection_glow()


if __name__ == "__main__":
    main()
