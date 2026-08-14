"""Generates one texture per exact size, for shapes a 9-patch can't sharpen.

WHY. Kodi's `border=N` is both the source slice and the drawn corner size, so
a 9-patch corner can never carry more pixels than the coordinate space it was
authored for -- on a 4K GUI it is upscaled 2x and there is no way to ship
better art for it (see resources/lib/skin/build.py:_slice_pills). Solid pills
escaped that by being sliced into caps and a middle, but a STROKED pill
cannot: its 2px rim has to stay 2px at every size, so shared art would have
to be scaled, and scaling is what softens it again.

The way out is to stop sharing. Draw the shape once at exactly the size it is
used at, with the stroke baked at the right thickness, and hand Kodi a plain
texture with no border at all. Nothing is stretched, so nothing drifts.

WHAT KEEPS IT HONEST. An exact-size asset is pinned to one width and height,
so it is wrong the moment a layout number moves. This tool does not carry a
list of sizes -- it ASKS the renderer, which is the only thing that knows:

    build.collect_exact_requests()  ->  {filename: {width, height, radius, stroke}}

Change a width in tokens.py and the answer changes with it. Run this, and
tools/check_xml.py will tell you if anything is still missing or has gone
stale. That loop is what makes exact art maintainable rather than a trap.

Files land at EXACT_SCALE times their layout size, so they are ~1:1 on a 4K
panel; the stroke is scaled with them so it still measures 2 units on screen.

Dev-only tool (needs Pillow). Output goes into
plugin.video.tofa/resources/skins/Main/media/.

Usage:
    python3 tools/gen_exact_assets.py           generate what is missing
    python3 tools/gen_exact_assets.py --force    redraw everything
    python3 tools/gen_exact_assets.py --prune    also delete what is unused
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "plugin.video.tofa", "resources"))
from lib.skin import build  # noqa: E402

S = 4            # supersample factor
EXACT_SCALE = 2  # output pixels per layout unit

_MEDIA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "plugin.video.tofa",
    "resources", "skins", "Main", "media",
)


def draw(spec: dict) -> Image.Image:
    """The shape at `spec`'s exact size, stroked or filled.

    Stroked from the FULL canvas box, never a stroke/2 inset -- the same rule
    gen_capsule_pill_assets.py follows, and for the same reason: PIL strokes
    inward, so an inset outline's silhouette diverges from the fill it is
    layered on by several pixels at the cap extremes.
    """
    w = spec["width"] * EXACT_SCALE * S
    h = spec["height"] * EXACT_SCALE * S
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    box = [0, 0, w - 1, h - 1]
    radius = spec["radius"] * EXACT_SCALE * S
    if spec["stroke"]:
        ImageDraw.Draw(im).rounded_rectangle(
            box, radius=radius, outline=(255, 255, 255, 255),
            width=spec["stroke"] * EXACT_SCALE * S)
    else:
        ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 255))
    return im.resize((spec["width"] * EXACT_SCALE, spec["height"] * EXACT_SCALE),
                     Image.LANCZOS)


def _draw_at_unit_scale(spec: dict) -> Image.Image:
    """The same shape at 1:1, for comparing geometry against the original."""
    w, h = spec["width"] * S, spec["height"] * S
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    box, radius = [0, 0, w - 1, h - 1], spec["radius"] * S
    if spec["stroke"]:
        ImageDraw.Draw(im).rounded_rectangle(
            box, radius=radius, outline=(255, 255, 255, 255), width=spec["stroke"] * S)
    else:
        ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 255))
    return im.resize((spec["width"], spec["height"]), Image.LANCZOS)


def _ninepatch(src: Image.Image, w: int, h: int, b: int) -> Image.Image:
    """Kodi's 9-patch, reproduced: corners unscaled, edges and middle
    stretched. Same routine as gen_capsule_pill_assets, restated here so the
    comparison below does not depend on that file's capsule assumptions."""
    sw, sh = src.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cut = src.crop
    out.paste(cut((0, 0, b, b)), (0, 0))
    out.paste(cut((sw - b, 0, sw, b)), (w - b, 0))
    out.paste(cut((0, sh - b, b, sh)), (0, h - b))
    out.paste(cut((sw - b, sh - b, sw, sh)), (w - b, h - b))
    mid_w, mid_h = w - 2 * b, h - 2 * b
    if mid_w > 0:
        out.paste(cut((b, 0, sw - b, b)).resize((mid_w, b)), (b, 0))
        out.paste(cut((b, sh - b, sw - b, sh)).resize((mid_w, b)), (b, h - b))
    if mid_h > 0:
        out.paste(cut((0, b, b, sh - b)).resize((b, mid_h)), (0, b))
        out.paste(cut((sw - b, b, sw, sh - b)).resize((b, mid_h)), (w - b, b))
    if mid_w > 0 and mid_h > 0:
        out.paste(cut((b, b, sw - b, sh - b)).resize((mid_w, mid_h)), (b, b))
    return out


def match_source(name: str, spec: dict) -> int:
    """Prove the redrawn shape still IS the 9-patch it replaces.

    An exact-size texture is a swap, not a redesign: if the calibrated radius
    or stroke ever drifts from what the original art renders, every surface
    using it changes shape and nothing else would say so. This renders the
    ORIGINAL 9-patch at the same size and compares the corner alpha.

    Compares SHAPES, at 1:1, not the saved file: the shipped asset is drawn
    at EXACT_SCALE and reading it back through a downsample would measure
    resampling noise in the antialiased band (~37/255 on a large panel)
    rather than whether the geometry is right.

    The allowance comes from the spec (build.py:_EXACT_TOLERANCE). It is
    tight for shapes that reproduce exactly and wider for the two legacy
    textures whose corners are not circular arcs -- but always well below
    the 50-250 a wrong radius produces, which is how rounded-20-outline was
    caught stroking at 1 unit rather than 2.
    """
    src_path = os.path.join(_MEDIA_DIR, spec["source"] + ".png")
    src = Image.open(src_path).convert("RGBA")
    b = min(spec.get("border", spec["radius"]), src.size[0] // 2, src.size[1] // 2)
    ref = _ninepatch(src, spec["width"], spec["height"], b)
    got = draw(dict(spec, width=spec["width"] // EXACT_SCALE * EXACT_SCALE)).resize(
        (spec["width"], spec["height"]), Image.LANCZOS) if False else _draw_at_unit_scale(spec)
    ra, ga = ref.split()[3], got.split()[3]
    n = min(40, spec["width"] // 2, spec["height"] // 2)
    worst = max(abs(ra.getpixel((x, y)) - ga.getpixel((x, y)))
                for y in range(n) for x in range(n))
    if worst > spec.get("tolerance", 8):
        raise SystemExit(
            f"{name}: corner differs from {spec['source']}.png by {worst}/255. "
            f"The calibrated radius/stroke in build.py:_EXACT_RECTS no longer "
            f"describes that art (allowed {spec.get('tolerance', 8)}) -- "
            f"re-sweep before shipping this.")
    return worst


def verify(name: str, spec: dict) -> None:
    """The rim must be a closed ring of the right thickness.

    Reads the file back and measures the stroke where it is unambiguous --
    the top edge at mid-width, which is flat on a stadium -- against what was
    asked for. A silent half-thickness rim is the failure this catches.
    """
    im = Image.open(os.path.join(_MEDIA_DIR, name)).convert("RGBA")
    alpha = im.split()[3]
    x = im.width // 2
    run = 0
    for y in range(im.height):
        if alpha.getpixel((x, y)) < 128:
            break
        run += 1
    want = spec["stroke"] * EXACT_SCALE
    if abs(run - want) > 1:
        raise SystemExit(
            f"{name}: top rim measures {run}px, expected {want}px "
            f"(stroke {spec['stroke']} units at {EXACT_SCALE}x)")
    return run


def main() -> None:
    force = "--force" in sys.argv
    prune = "--prune" in sys.argv
    wanted = build.collect_exact_requests()
    made = kept = 0
    for name, spec in sorted(wanted.items()):
        path = os.path.join(_MEDIA_DIR, name)
        if os.path.exists(path) and not force:
            kept += 1
            continue
        draw(spec).save(path)
        made += 1
        if spec["source"]:
            dev = match_source(name, spec)
            print(f"saved {name}  {spec['width']}x{spec['height']} units, "
                  f"matches {spec['source']}.png within {dev}/255")
        else:
            rim = verify(name, spec)
            print(f"saved {name}  {spec['width']}x{spec['height']} units "
                  f"-> {spec['width']*EXACT_SCALE}x{spec['height']*EXACT_SCALE}px, rim {rim}px")
    stale = sorted(n for n in os.listdir(_MEDIA_DIR)
                   if n.startswith(("pill-outline-", "exact-")) and n not in wanted)
    for name in stale:
        if prune:
            os.remove(os.path.join(_MEDIA_DIR, name))
            print("removed", name, "(nothing references it)")
        else:
            print("STALE  ", name, "(nothing references it; --prune to delete)")
    print(f"\n{made} generated, {kept} already current, {len(stale)} stale")


if __name__ == "__main__":
    main()
