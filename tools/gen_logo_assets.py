"""Renders the 14 accent fox logos from tofa's own SVG source.

WHAT THESE ARE. theme.PRESETS maps each of the 14 accents to a
`tofa-logo-<slug>.png` -- the fox mark in that accent's colours. The artwork
cannot be tinted at runtime the way flat chrome can (the mark is a shaded
drawing, not a silhouette), so each accent ships its own raster and the skin
just draws the one the accent names.

WHERE THE ART COMES FROM. `tofa UX/android-tv/logo-svgs/fox_<slug>.svg` are
tofa's own resources, lifted from the Android TV APK unmodified -- verified
byte-identical against the 2026-08-09 beta, where they are named `fox_tofa`,
`fox_amber`, ... exactly as here. They are flat vector, no gradients; that is
what the app itself draws.

WHY THIS TOOL EXISTS. The 13 non-default rasters were hand-exported from
those SVGs through Inkscape and the default teal one was not -- it came in a
day earlier at 213x256 from an unknown source, with smooth gradients the
vector does not have. So the set was inconsistent in both size and treatment,
and nothing regenerated it. This makes all 14 one command from one source.

RESAMPLING. resvg at the target size antialiases harder than Inkscape did.
Rendering at 2x and downsampling LANCZOS lands closer to the art it replaces
(p99 10/255 against 6, worst case 44 against 68) and carries a comparable
number of distinct colours, so the edges keep their smoothness. 3x measures
no better than 2x.

The slug list is read out of theme.py rather than repeated here: which
accents exist is that file's business, and a preset added there without art
should fail loudly rather than silently ship 14 of 15.

Dev-only tool (needs Pillow + resvg_py), and it needs the SVG sources, which
live outside the add-on and may not be present in every checkout.

Usage:
    python3 tools/gen_logo_assets.py            render all 14
    python3 tools/gen_logo_assets.py --check    compare, write nothing
"""
from __future__ import annotations

import io
import os
import re
import sys

import resvg_py
from PIL import Image, ImageChops

_HERE = os.path.dirname(__file__)


def _svg_dir() -> str:
    """Where tofa's fox SVGs are, in whichever checkout this is running in.

    They sit under `tofa UX/android-tv/` here, beside the APK captures they
    were pulled from. The public repository takes the SVGs and none of the
    captures, so there they are `art/logo-svgs/` -- a `tofa UX/android-tv/`
    holding one folder of vectors would name something that is not there.

    Neither location is a fallback for the other; both are real, and the
    first that exists wins. The missing-directory message below is what a
    checkout without either gets."""
    for parts in (("art", "logo-svgs"),
                  ("tofa UX", "android-tv", "logo-svgs")):
        candidate = os.path.join(_HERE, "..", *parts)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(_HERE, "..", "art", "logo-svgs")


_SVG_DIR = _svg_dir()
_MEDIA = os.path.join(_HERE, "..", "plugin.video.tofa", "resources", "skins",
                      "Main", "media")
_THEME = os.path.join(_HERE, "..", "plugin.video.tofa", "resources", "lib",
                      "windows", "theme.py")

#: Output width. The mark's viewBox is 527x632, so the height follows from it
#: rather than being typed -- a change here stays in proportion.
WIDTH = 640
_VIEWBOX = (527, 632)
HEIGHT = round(WIDTH * _VIEWBOX[1] / _VIEWBOX[0])   # 768
SS = 2                                              # supersample factor


def presets() -> list[tuple[str, str]]:
    """[(slug, output filename)] straight out of theme.PRESETS.

    Parsed, not imported: theme.py reaches for kodigui and therefore for
    Kodi's own modules, which do not exist outside Kodi."""
    body = re.search(r"PRESETS = \((.*?)\n\)", open(_THEME).read(), re.S)
    if not body:
        raise SystemExit("theme.py: could not find PRESETS")
    rows = re.findall(r'\("([^"]+)",\s*"[0-9A-Fa-f]{6}",\s*"([^"]+)"\)',
                      body.group(1))
    if not rows:
        raise SystemExit("theme.py: PRESETS matched no rows -- shape changed?")
    return [(name.lower(), filename) for name, filename in rows]


def render(svg_path: str) -> Image.Image:
    """The mark at WIDTH x HEIGHT, supersampled."""
    with open(svg_path, encoding="utf-8") as f:
        svg = f.read()
    raw = resvg_py.svg_to_bytes(svg_string=svg, width=WIDTH * SS,
                                height=HEIGHT * SS)
    big = Image.open(io.BytesIO(bytes(raw))).convert("RGBA")
    return big.resize((WIDTH, HEIGHT), Image.LANCZOS)


def _deviation(new: Image.Image, path: str) -> str:
    """How far the render sits from the file it replaces, if there is one.

    Composited onto black first. A fully transparent pixel still carries RGB,
    and two renderers disagree about what it should be -- comparing raw RGBA
    reports 255/255 across the whole background and says nothing."""
    if not os.path.exists(path):
        return "new"
    old = Image.open(path).convert("RGBA")
    if old.size != new.size:
        return f"replaces {old.size[0]}x{old.size[1]}"

    def flat(im):
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        return bg.convert("L")

    d = sorted(ImageChops.difference(flat(new), flat(old)).tobytes())
    return f"p99 {d[int(len(d) * .99)]}/255, max {d[-1]}"


def main() -> None:
    check = "--check" in sys.argv
    if not os.path.isdir(_SVG_DIR):
        raise SystemExit(
            f"missing {os.path.normpath(_SVG_DIR)} -- tofa's logo SVGs are not "
            f"part of the add-on and are not in every checkout. The rendered "
            f"tofa-logo*.png are committed, so nothing needs this tool to "
            f"build or run the add-on; it is only needed to redraw them.")

    for slug, filename in presets():
        svg_path = os.path.join(_SVG_DIR, f"fox_{slug}.svg")
        out_path = os.path.join(_MEDIA, filename)
        if not os.path.exists(svg_path):
            raise SystemExit(
                f"theme.PRESETS names {filename} but there is no "
                f"fox_{slug}.svg to draw it from.")
        im = render(svg_path)
        note = _deviation(im, out_path)
        if not check:
            im.save(out_path, optimize=True)
        print(f"{'would draw' if check else 'saved'} {filename:24} "
              f"{WIDTH}x{HEIGHT}  ({note})")


if __name__ == "__main__":
    main()
