"""Generates tools/design_language.html -- a self-contained visual style
guide covering every distinctly-styled UI element in plugin.video.tofa
(cards, pills/buttons, list rows, badges, input controls, panels, empty
states, player chrome): what it looks like in each state, and the exact
fill/border/radius/font/color values driving it, pulled directly from
fragments.py, theme.py, fontinstall.py, and the hand-authored screen XML
-- not eyeballed off screenshots.

The bundled Inter Tight weights, lucide-icons.ttf, and Roboto Mono are
embedded as base64 data URIs (same technique as gen_icon_reference.py) so
every mock renders in the app's actual typefaces and icon glyphs, offline.

Every swatch is built from four generic CSS/JS primitives (pill, row,
card, circle) fed by a plain data array, since ~30 hand-rolled Kodi
controls reduce to those same four visual shapes plus a shared 4-step
glass-fill ladder. Kodi itself still needs a distinct 9-patch PNG per
unique corner radius (border="N" is a literal pixel crop, not a
resolution-independent radius -- see project_kodi_9patch_needs_straight_edges),
so the XML can't be this DRY; this page is the reference for what should
converge next time a screen is touched.

Values are not hand-typed here. Colours and geometry come from
skin/tokens.py, the type scale from fontinstall.py:FONTS, and the accent
presets from theme.py:PRESETS; `_verify_against_sources()` then re-reads the
finished HTML and refuses to write it if any value in the page has no
counterpart in those modules. That check exists because this file *was* a
hand-maintained parallel description and drifted silently -- it went on
claiming a 296x438 poster cell and a 0x1EFFFFFF glass step long after
tokens.py changed both. gen_icon_reference.py guards icon_glyphs.py the
same way.

Regenerate whenever fragments.py/tokens.py/theme.py/fontinstall.py's FONTS
or the hand-authored pill/row/badge markup in main.xml.tpl /
detail.xml.tpl changes:

    python3 tools/gen_design_language.py
"""
from __future__ import annotations

import base64
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(__file__)
_ADDON_DIR = os.path.join(_TOOLS_DIR, "..", "plugin.video.tofa")
_OUTPUT_PATH = os.path.join(_TOOLS_DIR, "design_language.html")
_FONTS_DIR = os.path.join(_ADDON_DIR, "resources", "skins", "Main", "fonts")

# The add-on's own modules are the source of truth for every value below.
# tokens.py is deliberately stdlib-only, so it imports cleanly out here;
# theme.py and fontinstall.py both pull in xbmc, which only exists inside
# Kodi, so their two tables get read textually instead.
sys.path.insert(0, os.path.normpath(_ADDON_DIR))
from resources.lib.skin import tokens as T  # noqa: E402

_LIB_DIR = os.path.join(_ADDON_DIR, "resources", "lib")


def _read(*parts: str) -> str:
    with open(os.path.join(_LIB_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def _theme_presets() -> list[tuple[str, str]]:
    """theme.py:PRESETS as (name, "RRGGBB")."""
    block = re.search(r"^PRESETS = \((.*?)^\)", _read("windows", "theme.py"), re.S | re.M)
    if not block:
        raise SystemExit("gen_design_language: theme.py:PRESETS not found")
    return [
        (name, hex_.lstrip("#").upper()[-6:])
        for name, hex_ in re.findall(
            r'\(\s*"([^"]+)"\s*,\s*"([0-9A-Fa-f]{6})"\s*,', block.group(1)
        )
    ]


# The .ttf filename fontinstall.py names -> how the page has to describe it.
# Weight is a property of the FILE (Inter Tight ships one file per weight),
# so a role's weight is not a free choice on the page -- it is derivable, and
# _verify_against_sources() therefore checks it rather than trusting the array.
_FAMILY_OF_TTF = {
    "inter_tight_regular.ttf": ("Inter Tight Regular", 400),
    "inter_tight_semibold.ttf": ("Inter Tight SemiBold", 600),
    "inter_tight_bold.ttf": ("Inter Tight Bold", 700),
    "RobotoMono-Regular.ttf": ("Roboto Mono Regular", 400),
    "RobotoMono-Bold.ttf": ("Roboto Mono Bold", 700),
    "lucide-icons.ttf": ("Lucide Icons", 400),
}


def _fonts() -> dict[str, tuple[str, int]]:
    """fontinstall.py:FONTS as role -> (source .ttf, Kodi <size>)."""
    fonts = {
        role: (ttf, int(size))
        for role, ttf, size in re.findall(
            r'"(tofa_font_\w+)":\s*\("([^"]+)",\s*(\d+)', _read("fontinstall.py")
        )
    }
    if not fonts:
        raise SystemExit("gen_design_language: fontinstall.py:FONTS not found")
    unknown = sorted({ttf for ttf, _ in fonts.values()} - set(_FAMILY_OF_TTF))
    if unknown:
        raise SystemExit(
            f"gen_design_language: fontinstall.py ships {unknown}, which "
            f"_FAMILY_OF_TTF has no display name/weight for"
        )
    return fonts


def _text_tiers() -> list[tuple[str, str]]:
    """theme.py's white-alpha text tiers as (TEXT_NAME, value), in file order.

    Read textually for the same reason PRESETS is: theme.py imports xbmc.
    The page's own swatch strip is checked against this -- the FOURTH tier
    (TEXT_STRONG, 2026-08-13) went in without the page noticing, because
    nothing here used to look."""
    src = _read("windows", "theme.py")
    tiers = re.findall(r'^(TEXT_[A-Z]+) = "([^"]+)"', src, re.M)
    if not tiers:
        raise SystemExit("gen_design_language: theme.py TEXT_* tiers not found")
    return tiers


# Every 8-digit hex the page may state that is NOT a tokens.py value, each
# with the reason it legitimately isn't one. Anything outside this set and
# outside tokens.py trips _verify_against_sources() -- that is the whole
# point: a new literal has to be justified here or promoted to a token.
_NON_TOKEN_HEX = {
    # Text tiers live in theme.py, not tokens.py: they're pushed as
    # Window.Properties at runtime rather than baked into the XML.
    "0x9EFFFFFF": "theme.py:TEXT_SECONDARY",
    "0xFFFFFFFF": "plain white / theme.py:TEXT_PRIMARY",
    # Quoted by Finding 8 as a DEFECT, not used as a value: an off-tier 60%
    # white that came back into script-tofa-signin.xml after the 2026-07-30
    # sweep. Delete this entry when that line moves onto a tier.
    "0x99FFFFFF": "script-tofa-signin.xml:338 -- an off-tier literal the "
                  "page reports as a finding",
    "0xFF5EEAD4": "accent-bright, runtime-derived per accent (theme.py)",
    # Home hero gradient stack: one-off washes, not part of the ladder.
    "0xE6030B10": "Home hero bottom fade",
    "0x38030B10": "Home hero flat wash",
    # The four hand-authored screens (picker/signin/profile/player) never
    # pass through the fragments pipeline, so their literals can't be
    # tokenized without migrating the whole screen first. Each entry here is
    # a standing marker of that gap -- delete it when the screen migrates.
    "0xF2030B10": "script-tofa-picker.xml: panel fill, canvas at 95%",
    "0x1EFFFFFF": "script-tofa-picker.xml: panel outline -- the last "
                  "surviving pre-merge glass step anywhere in the app",
    "0x332DD4BF": "script-tofa-signin.xml: accent at 20%",
    "0x552DD4BF": "script-tofa-signin.xml: accent at 33%",
    "0xAA2A7A72": "script-tofa-signin.xml: desaturated accent, QR surround",
    "0xFF14262E": "script-tofa-signin.xml: raised panel",
    "0xFF2A3043": "script-tofa-signin.xml: input field fill",
    "0xFF16232B": "script-tofa-profile.xml: avatar tile fill",
    "0xB0030B10": "script-tofa-player.xml: OSD scrim",
    "0x40000000": "detail.xml.tpl: drop shadow under the hero art",
}


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _token_hexes() -> dict[str, str]:
    return {
        value.upper(): name
        for name, value in vars(T).items()
        if name.isupper() and isinstance(value, str) and value.startswith("0x")
    }


def _verify_against_sources(html: str) -> None:
    """Refuse to write a page that states values the add-on doesn't use.

    Checks the three things this file has actually drifted on before: colour
    literals, the type scale, and the accent presets. Raises rather than
    warns -- a style guide that quietly describes last month's design is
    worse than no style guide, since it gets cited as authority."""
    problems: list[str] = []

    known = _token_hexes()
    for hex_ in sorted(set(re.findall(r"0x[0-9A-Fa-f]{8}", html))):
        if hex_.upper() not in known and hex_.upper() not in {
            k.upper() for k in _NON_TOKEN_HEX
        }:
            problems.append(
                f"colour {hex_} is stated in the page but is neither a "
                f"tokens.py value nor listed in _NON_TOKEN_HEX"
            )

    # Type scale: role -> (family, pt size, CSS weight) as stated in the
    # page's TYPE SCALE array. Family and weight are checked too, not just
    # the size: both are derivable from the .ttf fontinstall.py names, so a
    # hand-typed "SemiBold" beside a regular file is drift the page can't
    # be trusted to notice on its own.
    stated_type = {
        role: (family, int(size), int(weight))
        for role, family, size, weight in re.findall(
            r"\['(tofa_font_\w+)', '([^']*)', (\d+), (\d+),", html
        )
    }
    if not stated_type:
        problems.append("type scale array not found -- the regex needs updating")
    real_fonts = _fonts()
    for role, (family, size, weight) in sorted(stated_type.items()):
        real = real_fonts.get(role)
        if real is None:
            problems.append(f"type scale lists {role}, which fontinstall.py no longer defines")
            continue
        ttf, real_size = real
        real_family, real_weight = _FAMILY_OF_TTF[ttf]
        if (family, size, weight) != (real_family, real_size, real_weight):
            problems.append(
                f"type scale says {role} is {family}/{size}pt/{weight}; "
                f"fontinstall.py ships {ttf} at {real_size}pt "
                f"({real_family}/{real_weight})"
            )
    missing = sorted(r for r in real_fonts if r not in stated_type)
    if missing:
        problems.append(f"type scale omits roles fontinstall.py defines: {missing}")

    # Text tiers. The page states each as "<2 hex digits> &middot; <pct>%"
    # in its swatch strip; primary is spelled "white" in theme.py and shows
    # as "white" on the page, so it is matched by name rather than by value.
    real_tiers = _text_tiers()
    for name, value in real_tiers:
        if value == "white":
            continue
        pair = value[2:4].upper()          # 0x9EFFFFFF -> 9E
        pct = round(int(pair, 16) / 255 * 100)
        if f"{pair} &middot; {pct}%" not in html:
            problems.append(
                f"text tier {name} ({value}, {pct}%) is not stated in the "
                f"page's swatch strip"
            )
    if len(re.findall(r'<div class="cap">(?:primary|strong|secondary|tertiary)<b>', html)) != len(real_tiers):
        problems.append(
            f"the text-tier swatch strip does not have one swatch per "
            f"theme.py tier ({[n for n, _ in real_tiers]})"
        )

    # Accent presets.
    stated_presets = [
        (name, hex_.upper())
        for name, hex_ in re.findall(r'\["(\w+)","([0-9A-Fa-f]{6})"\]', html)
    ]
    if stated_presets != _theme_presets():
        problems.append(
            f"accent presets differ from theme.py:PRESETS\n"
            f"      page:     {stated_presets}\n"
            f"      theme.py: {_theme_presets()}"
        )

    if problems:
        raise SystemExit(
            "gen_design_language: page has drifted from its sources; "
            "fix the page (or the token) before regenerating:\n  - "
            + "\n  - ".join(problems)
        )


def main() -> None:
    fonts = {
        "inter_reg": _b64(os.path.join(_FONTS_DIR, "inter_tight_regular.ttf")),
        "inter_semi": _b64(os.path.join(_FONTS_DIR, "inter_tight_semibold.ttf")),
        "inter_bold": _b64(os.path.join(_FONTS_DIR, "inter_tight_bold.ttf")),
        "lucide": _b64(os.path.join(_FONTS_DIR, "lucide-icons.ttf")),
        "mono_reg": _b64(os.path.join(_FONTS_DIR, "RobotoMono-Regular.ttf")),
        "mono_bold": _b64(os.path.join(_FONTS_DIR, "RobotoMono-Bold.ttf")),
    }

    # Geometry and colour come from tokens.py so the page can't restate them
    # wrongly; see _verify_against_sources() for what happens when it tries.
    values = {
        "glass_faint": T.SURFACE_FAINT,
        "glass_rest": T.SURFACE_REST,
        "glass_raised": T.SURFACE_RAISED,
        "glass_track": T.SURFACE_TRACK,
        "tab_font": T.FONT_BUTTON,
        "tab_faint_css": f"{int(T.SURFACE_FAINT[2:4],16)/255:.3f}",
        "tab_raised_css": f"{int(T.SURFACE_RAISED[2:4],16)/255:.3f}",
        "glass_divider": T.DIVIDER,
        "border_soft": T.BORDER_SOFT,
        "border": T.BORDER,
        "divider": T.DIVIDER,
        "badge_scrim": T.BADGE_SCRIM,
        "glass_faint_css": f"{int(T.SURFACE_FAINT[2:4], 16) / 255:.3f}",
        "glass_rest_css": f"{int(T.SURFACE_REST[2:4], 16) / 255:.3f}",
        "glass_raised_css": f"{int(T.SURFACE_RAISED[2:4], 16) / 255:.3f}",
        "cell_w": T.CELL_W,
        "cell_h": T.CELL_H,
        "grid_gap_browse": T.GRID_GAP_BROWSE,
        "grid_gap_person": T.GRID_GAP,
        "browse_cell_h": T.BROWSE_CELL_H,
        "person_cell_h": T.GRID_CELL_H,
        "poster_w": T.POSTER_W,
        "poster_h": T.POSTER_H,
    }

    html = HTML_TEMPLATE.format(**fonts, **values)
    _verify_against_sources(html)
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {_OUTPUT_PATH} ({len(html) / 1024:.0f} KB)")


HTML_TEMPLATE = r"""<meta charset="utf-8" />
<title>tofa for Kodi Design Language</title>
<style>
@font-face {{ font-family: 'Inter Tight'; font-weight: 400; src: url(data:font/ttf;base64,{inter_reg}) format('truetype'); }}
@font-face {{ font-family: 'Inter Tight'; font-weight: 600; src: url(data:font/ttf;base64,{inter_semi}) format('truetype'); }}
@font-face {{ font-family: 'Inter Tight'; font-weight: 700; src: url(data:font/ttf;base64,{inter_bold}) format('truetype'); }}
@font-face {{ font-family: 'tofa-lucide'; src: url(data:font/ttf;base64,{lucide}) format('truetype'); }}
@font-face {{ font-family: 'Roboto Mono'; font-weight: 400; src: url(data:font/ttf;base64,{mono_reg}) format('truetype'); }}
@font-face {{ font-family: 'Roboto Mono'; font-weight: 700; src: url(data:font/ttf;base64,{mono_bold}) format('truetype'); }}

:root {{
  --abyss: #030b10;
  --harbor: #071a26;
  --surface: #0c2a3d;
  --elevated: #10364d;
  --ar: 45; --ag: 212; --ab: 191; /* live accent rgb, JS-driven */
  --accent: rgb(var(--ar),var(--ag),var(--ab));
  --on-accent: #04211e; /* JS-computed per accent via real contrast, see setAccent() */
  --radius-doc: 16px;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: var(--abyss); color: #fff; }}
body {{
  font-family: 'Inter Tight', sans-serif;
  font-size: 15px;
  line-height: 1.55;
  min-height: 100vh;
  overflow-x: hidden;
}}
.mono {{ font-family: 'Roboto Mono', monospace; font-variant-numeric: tabular-nums; }}
.icon {{ font-family: 'tofa-lucide'; font-style: normal; line-height: 1; }}

a {{ color: var(--accent); }}

/* ---------- layout ---------- */
.shell {{ display: flex; min-height: 100vh; }}
.rail {{
  position: sticky; top: 0; align-self: flex-start; height: 100vh;
  width: 248px; flex: 0 0 auto; overflow-y: auto;
  background: var(--harbor);
  border-right: 1px solid rgba(255,255,255,0.08);
  padding: 28px 18px 28px;
}}
.rail-brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 22px; padding: 0 6px; }}
.rail-brand .icon {{ font-size: 26px; color: var(--accent); }}
.rail-brand b {{ font-weight: 700; font-size: 17px; letter-spacing: -0.2px; }}
.rail nav {{ display: flex; flex-direction: column; gap: 2px; margin-bottom: 26px; }}
.rail nav a {{
  color: rgba(255,255,255,0.7); text-decoration: none; font-size: 13.5px; font-weight: 600;
  padding: 7px 10px; border-radius: 8px; display: block;
}}
.rail nav a:hover {{ background: rgba(255,255,255,0.06); color: #fff; }}
.rail-section {{ font-family: 'Inter Tight'; font-weight: 700; font-size: 10px; letter-spacing: 1.4px;
  text-transform: uppercase; color: rgba(255,255,255,0.4); margin: 18px 10px 6px; }}
.accent-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; padding: 0 6px; }}
.accent-dot {{
  width: 30px; height: 30px; border-radius: 50%; cursor: pointer; border: 2px solid transparent;
  transition: transform .12s ease; padding: 0;
}}
.accent-dot:hover {{ transform: scale(1.12); }}
.accent-dot.active {{ border-color: #fff; }}
.rail-note {{ font-size: 11.5px; color: rgba(255,255,255,0.4); padding: 10px 6px 0; }}

.main {{ flex: 1 1 auto; padding: 56px 64px 120px; max-width: 1360px; }}
.hero h1 {{ font-size: 40px; font-weight: 700; margin: 0 0 10px; letter-spacing: -0.5px; text-wrap: balance; }}
.hero p {{ font-size: 16px; color: rgba(255,255,255,0.65); max-width: 760px; margin: 0 0 6px; }}
.hero .src {{ font-size: 12.5px; color: rgba(255,255,255,0.4); margin-top: 18px; }}

section.doc {{ margin-top: 76px; scroll-margin-top: 24px; }}
section.doc > h2 {{ font-size: 24px; font-weight: 700; margin: 0 0 6px; letter-spacing: -0.2px; }}
section.doc > .lede {{ color: rgba(255,255,255,0.6); max-width: 780px; margin: 0 0 32px; font-size: 14px; }}

/* ---------- component block ---------- */
.comp {{ margin-bottom: 52px; }}
.comp-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 20px; margin-bottom: 14px; flex-wrap: wrap; }}
.comp-head h3 {{ font-size: 18px; font-weight: 700; margin: 0; }}
.comp-src {{ font-family: 'Roboto Mono'; font-size: 11.5px; color: rgba(255,255,255,0.4); }}
.comp-desc {{ font-size: 13px; color: rgba(255,255,255,0.55); margin: 0 0 16px; max-width: 720px; }}

.stage {{
  background: var(--harbor);
  background-image: radial-gradient(circle at 15% 20%, rgba(255,255,255,0.05), transparent 45%);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px;
  padding: 28px;
  display: flex; flex-wrap: wrap; gap: 36px;
  align-items: flex-start;
}}
.state-slot {{ display: flex; flex-direction: column; align-items: flex-start; gap: 12px; }}
.state-label {{
  font-size: 10.5px; font-weight: 700; letter-spacing: 1.1px; text-transform: uppercase;
  color: rgba(255,255,255,0.45);
}}

.props {{ margin-top: 16px; width: 100%; border-collapse: collapse; font-size: 12.5px; }}
.props td {{ padding: 6px 14px 6px 0; border-top: 1px solid rgba(255,255,255,0.06); vertical-align: top; }}
.props td:first-child {{ color: rgba(255,255,255,0.45); white-space: nowrap; font-weight: 600; width: 130px; }}
.props td:last-child {{ font-family: 'Roboto Mono'; color: rgba(255,255,255,0.85); }}

/* ---------- primitives ---------- */
.p-pill {{ display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }}
.p-row {{ display: flex; align-items: center; gap: 12px; }}
.p-card {{ position: relative; }}
.p-caption {{ display: flex; flex-direction: column; gap: 2px; }}

/* ---------- token swatches ---------- */
.swatch-strip {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 8px; }}
.swatch {{ display: flex; flex-direction: column; gap: 8px; align-items: center; width: 108px; }}
.swatch .chip {{ width: 84px; height: 60px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); }}
.swatch .cap {{ font-size: 11px; color: rgba(255,255,255,0.55); text-align: center; }}
.swatch .cap b {{ display: block; color: #fff; font-family: 'Roboto Mono'; font-size: 11px; }}

.type-row {{ display: flex; align-items: baseline; gap: 22px; padding: 14px 0; border-top: 1px solid rgba(255,255,255,0.07); }}
.type-row:first-of-type {{ border-top: none; }}
.type-meta {{ width: 230px; flex: 0 0 auto; font-size: 12px; color: rgba(255,255,255,0.5); }}
.type-meta b {{ display: block; color: #fff; font-size: 13px; font-weight: 700; margin-bottom: 2px; }}
.type-note {{ display: block; margin-top: 3px; color: rgba(255,255,255,0.38); font-size: 11px; line-height: 1.4; }}
.type-sample {{ flex: 1 1 auto; }}

.radius-ruler {{ display: flex; align-items: flex-end; gap: 22px; flex-wrap: wrap; }}
.radius-ruler .r-item {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
.radius-ruler .r-box {{ width: 74px; height: 74px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16); }}
.radius-ruler .r-cap {{ font-size: 11px; font-family: 'Roboto Mono'; color: rgba(255,255,255,0.6); text-align: center; }}

.finding {{ display: flex; gap: 16px; padding: 20px 0; border-top: 1px solid rgba(255,255,255,0.08); }}
.finding:first-of-type {{ border-top: none; }}
.finding .n {{ font-family: 'Roboto Mono'; font-weight: 700; color: var(--accent); font-size: 15px; flex: 0 0 28px; }}
.finding h4 {{ margin: 0 0 6px; font-size: 15px; }}
.finding p {{ margin: 0; font-size: 13.5px; color: rgba(255,255,255,0.62); max-width: 760px; }}

.empty-mock {{ display: flex; flex-direction: column; align-items: center; gap: 14px; text-align: center; width: 340px; padding: 30px 0; }}
.empty-mock .icon {{ font-size: 52px; color: rgba(255,255,255,0.3); }}
.empty-mock h5 {{ margin: 0; font-size: 20px; }}
.empty-mock p {{ margin: 0; font-size: 13px; color: rgba(255,255,255,0.5); }}

footer {{ margin-top: 90px; padding-top: 24px; border-top: 1px solid rgba(255,255,255,0.08);
  font-size: 12px; color: rgba(255,255,255,0.4); }}
footer code {{ font-family: 'Roboto Mono'; background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; }}

@media (max-width: 900px) {{
  .rail {{ display: none; }}
  .main {{ padding: 32px 22px 90px; }}
}}
</style>

<div class="shell">
  <aside class="rail">
    <div class="rail-brand"><span class="icon">&#xE1F3;</span><b>tofa design language</b></div>
    <nav>
      <a href="#tokens">Foundations</a>
      <a href="#cards">Cards</a>
      <a href="#pills">Pills &amp; Buttons</a>
      <a href="#rows">Rows &amp; Lists</a>
      <a href="#badges">Badges &amp; Indicators</a>
      <a href="#input">Input Controls</a>
      <a href="#panels">Panels &amp; Empty States</a>
      <a href="#player">Player Chrome</a>
      <a href="#findings">Consolidation Findings</a>
    </nav>
    <div class="rail-section">Live accent (14 presets)</div>
    <div class="accent-grid" id="accentGrid"></div>
    <div class="rail-note">tofa has exactly one accent hue at a time (One Voice Rule) &mdash; every mock on this page redraws live when you pick one.</div>
  </aside>

  <main class="main">
    <div class="hero">
      <h1>tofa for Kodi Design Language</h1>
      <p>Every distinctly-styled control in the add-on's window UI &mdash; cards, pills, rows, badges, input, panels &mdash; in every state it actually renders, with the exact fill/border/radius/font/color values behind it. Built from <code class="mono">fragments.py</code>, <code class="mono">theme.py</code>, <code class="mono">fontinstall.py</code> and the hand-authored screen XML, not eyeballed off screenshots.</p>
      <p class="src">Real typefaces (Inter Tight, Roboto Mono) and the real Lucide icon glyphs are embedded &mdash; this renders in the exact fonts the live app uses. See the <a href="#" id="iconRefLink">icon reference tool</a> for the full 2,027-icon Lucide catalog; this page only shows the glyphs already wired into a component.</p>
    </div>

    <section class="doc" id="tokens">
      <h2>Foundations</h2>
      <p class="lede">tofa's internal TV-DESIGN.md spec defines these as cross-platform tokens (Android TV + tvOS); values below are what's actually implemented in this Kodi client, called out where it drifts from spec.</p>

      <div class="comp">
        <div class="comp-head"><h3>Surface ladder</h3><span class="comp-src">TV-DESIGN.md &sect;2, windows/theme.py</span></div>
        <p class="comp-desc">Kodi never draws these as flat fills the way the spec's token table implies &mdash; every screen sits on one photographic backdrop (blurred poster art / a flat abyss fallback) with washes of white-alpha layered on top, not a stack of literal surface colors. Shown here as swatches for reference since the hex values themselves are real (spec &sect;2, `/DESIGN.md`).</p>
        <div class="swatch-strip">
          <div class="swatch"><div class="chip" style="background:#030b10"></div><div class="cap">abyss<b>#030b10</b></div></div>
          <div class="swatch"><div class="chip" style="background:#071a26"></div><div class="cap">harbor<b>#071a26</b></div></div>
          <div class="swatch"><div class="chip" style="background:#0c2a3d"></div><div class="cap">surface<b>#0c2a3d</b></div></div>
          <div class="swatch"><div class="chip" style="background:#10364d"></div><div class="cap">elevated<b>#10364d</b></div></div>
        </div>
      </div>

      <div class="comp">
        <div class="comp-head"><h3>Accent (runtime variable, 14 presets)</h3><span class="comp-src">windows/theme.py:PRESETS</span></div>
        <p class="comp-desc">Sourced from the signed-in account's own server-side preference (<code class="mono">/api/v1/users/me</code>), never a hardcoded hex &mdash; the local Kodi setting is only an offline fallback. One accent at a time everywhere: pill fills, focus borders, progress bars, the fox logo (which snaps to whichever of these 14 raster variants is nearest by RGB distance &mdash; it can't be tinted arbitrarily like flat chrome can).</p>
        <div class="swatch-strip" id="presetStrip"></div>
      </div>

      <div class="comp">
        <div class="comp-head"><h3>Glass-fill ladder</h3><span class="comp-src">resources/lib/skin/tokens.py</span></div>
        <p class="comp-desc">RESOLVED (2026-07-31). The same progression &mdash; faint &rarr; resting glass &rarr; raised glass &rarr; active-tinted glass &rarr; solid accent &mdash; used to be hand-typed as a raw hex literal independently in at least 8 components (see <a href="#findings">Finding 1</a>), which is how it drifted to eight ad-hoc alphas. It is now one named ladder in <code class="mono">tokens.py</code>; the two steps that sat one alpha apart (0x1E/0x1F) merged into <code class="mono">SURFACE_RAISED</code>. The swatches below are read out of that module at generation time, not typed here.</p>
        <div class="swatch-strip">
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,{glass_faint_css});border-radius:999px"></div><div class="cap">faint<b>{glass_faint}</b></div></div>
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,{glass_rest_css});border-radius:999px"></div><div class="cap">rest<b>{glass_rest}</b></div></div>
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,{glass_raised_css});border-radius:999px"></div><div class="cap">raised<b>{glass_raised}</b></div></div>
          <div class="swatch"><div class="chip accent-tint" data-alpha="0.239" style="border-radius:999px"></div><div class="cap">active<b class="mono">accent_pill_fill<br>(0x3D + accent)</b></div></div>
          <div class="swatch"><div class="chip accent-solid" style="border-radius:999px"></div><div class="cap">solid<b>accent_color</b></div></div>
        </div>
      </div>

      <div class="comp">
        <div class="comp-head"><h3>Text tiers (white-alpha)</h3><span class="comp-src">theme.py:TEXT_PRIMARY/TEXT_STRONG/TEXT_SECONDARY/TEXT_TERTIARY</span></div>
        <p class="comp-desc">RESOLVED (2026-07-30), then <b>reopened by measurement</b> (2026-08-13): there are <b>FOUR</b> tiers, not three. Spec &sect;2 defines four of its own (100/62/42/24%); the codebase had drifted to ~18 distinct alpha values for text. The 2026-07-30 pass consolidated that to three, each confirmed by pixel-sampling real Apple TV reference captures rather than copied from the spec sight-unseen &mdash; alpha = (rendered&minus;background)/(255&minus;background) against the measured local background &mdash; and it explicitly found the 80&ndash;82% band <i>empty</i> in both the captures and the codebase, which is why three was the answer and not four. Spec's own fourth tier ("muted", 24%) had no callers and still has none.</p>
        <p class="comp-desc"><b>What reopened it:</b> &sect;8.8's pause card. Its "N min left" line measures a peak of 211 against its own clock's 251 on the live Apple TV &mdash; ~83%, landing squarely in that supposedly-empty band. Under "the shipped app is the design source" a measured value outranks the tidiness of a three-bucket split, so <code class="mono">TEXT_STRONG</code> (0xD4, 83%) exists. It has <b>exactly one user</b>, and theme.py's own comment says to keep it that way until another label is <i>measured</i> into it: a tier that starts collecting labels by eye is how the ~18 values this system replaced got here in the first place. Treat it as a measured exception, not as a general-purpose "slightly brighter than secondary".</p>
        <p class="comp-desc">Every tier is pushed as a Window.Property (<code>text_primary</code>/<code>text_strong</code>/<code>text_secondary</code>/<code>text_tertiary</code>) in each window's <code class="mono">onFirstInit</code>, and <code>&lt;textcolor&gt;</code> references the property rather than the hex &mdash; 182 primary, 104 secondary, 48 tertiary, 1 strong across the generated pipeline and the hand-authored screens. The 2026-07-30 claim that <i>zero</i> literal white-alpha textcolors remain is <b>no longer true</b>; three have reappeared since, see <a href="#findings">Findings</a>.</p>
        <div class="swatch-strip">
          <div class="swatch"><div class="chip" style="background:#fff"></div><div class="cap">primary<b>white &middot; ~97%</b></div></div>
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,0.831)"></div><div class="cap">strong<b>D4 &middot; 83%</b></div></div>
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,0.62)"></div><div class="cap">secondary<b>9E &middot; 62%</b></div></div>
          <div class="swatch"><div class="chip" style="background:rgba(255,255,255,0.42)"></div><div class="cap">tertiary<b>6B &middot; 42%</b></div></div>
        </div>
      </div>

      <div class="comp">
        <div class="comp-head"><h3>Typography &mdash; tofa_font_* roles</h3><span class="comp-src">resources/lib/fontinstall.py:FONTS</span></div>
        <p class="comp-desc">Inter Tight carries every text role, in three weights &mdash; and <b>weight is a property of the file, not a tag</b>: Kodi's <code class="mono">&lt;font&gt;</code> has no weight attribute, so "SemiBold" means fontinstall.py injected <code class="mono">inter_tight_semibold.ttf</code> under that role name. Three roles are Roboto Mono, and only three: sign-in's <code class="mono">tofa_font_link</code> and <code class="mono">tofa_font_code</code> (a pairing code has to survive being read aloud off a TV), and <code class="mono">tofa_font_stats_value</code> in the player's &sect;8.11 stats readout, where the numbers tick once a second and a proportional face would shuffle the whole row sideways every time a digit changed width. Ratings and PIN digits are <i>not</i> mono &mdash; the rating badge is <code class="mono">tofa_font_micro</code> and the PIN pad is <code class="mono">tofa_font_button</code>. The eight Lucide roles at the bottom are one per pixel footprint the UI actually draws at.</p>
        <p class="comp-desc"><b>Sizes are not one conversion.</b> The page used to say every size here was ~1.75&times; a spec point size; that is true of one group only, and stating it as a blanket rule invites the wrong arithmetic on the rest. There are three conventions in play, and which one a role used is recorded beside it in fontinstall.py:</p>
        <ul class="comp-desc">
          <li><b>&sect;3's type scale, &times;1.7 from half-density.</b> The spec's own preamble says its Android TV numbers are dp at half density and that absolute sizes scale to the platform canvas. Six roles came straight through it: hero 44&rarr;77, screen title 32&rarr;57, section title 22&rarr;39, row title 15&rarr;26, body 14&rarr;24, metadata 13&rarr;23.</li>
          <li><b>1:1, where the spec section is already on our canvas.</b> &sect;7.2 is 1:1 (its row label of 26 <i>is</i> <code class="mono">tofa_font_row_title</code>), so its "34/Bold" panel title is a literal 34 &mdash; <code class="mono">tofa_font_dialog_title</code>. Multiplying it would have been the mistake.</li>
          <li><b>Cap-height conversion, measured off the real Apple TV.</b> The newest roles were sized by measuring the app's own ink and converting through <i>Inter Tight's</i> metrics rather than reusing a nominal point size across two different typefaces. Inter Tight's cap is 0.7275/em, Roboto Mono's ~0.71, so &sect;7.3's "50pt bold" Top Result title becomes <b>52</b>, not 50 and not 87: 50pt of SF Pro caps at 38px, and 52 of Inter Tight is what reproduces 38. The player title (cap 34&rarr;45), subtitle (22&rarr;30), pause clock (37&rarr;51), and all four &sect;8.11 stats roles came the same way. Two of them also corrected a <i>weight</i> the same way: the pause clock reads regular, not the bold heading role it used to borrow (stroke-to-height 0.108/0.135, which bold overshoots at 0.216), and the line under it reads bold, not the semibold button role it used to borrow.</li>
        </ul>
        <p class="comp-desc">So: <b>sizes below are Kodi's actual injected values</b>, read out of <code class="mono">FONTS</code> at generation time. Don't back-derive a spec number from one by dividing.</p>
        <div id="typeScale"></div>
      </div>

      <div class="comp">
        <div class="comp-head"><h3>Corner radius</h3><span class="comp-src">border=&quot;N&quot; 9-patch crops + exact-size mask assets</span></div>
        <p class="comp-desc">Kodi's <code class="mono">&lt;texture border="N"&gt;</code> is a literal N&times;N pixel crop of the source PNG's own baked corner &mdash; not a resolution-independent radius &mdash; so every distinct radius below is a distinct source asset, not one parameter. Spec &sect;4 calls for a 4-step scale (8 / 12 / 14 / pill); the codebase had drifted to 9 numbers in use, but a 2026-07-30 pass (see <a href="#findings">Findings</a>) found several of those were the same ~4px asset wearing different border= labels &mdash; the genuinely distinct radii below are down to 7.</p>
        <div class="radius-ruler" id="radiusRuler"></div>
      </div>
    </section>

    <section class="doc" id="cards"><h2>Cards</h2><p class="lede">Every card in the app shares one construction: mask/border/glow drawn as exact-size assets (not stretched 9-patch) so the corner radius never warps under focus-zoom.</p><div id="cardsHost"></div></section>
    <section class="doc" id="pills"><h2>Pills &amp; Buttons</h2><p class="lede">Everything clickable that isn't a full list row reduces to a filled or outlined rounded rect, optionally with a leading icon and/or trailing chevron.</p><div id="pillsHost"></div></section>
    <section class="doc" id="rows"><h2>Rows &amp; Lists</h2><p class="lede">Sidebar rows, history rows, and picker rows all share the same accent-left-bar-on-active convention, each re-implemented by hand once per screen.</p><div id="rowsHost"></div></section>
    <section class="doc" id="badges"><h2>Badges &amp; Indicators</h2><p class="lede">Small, non-interactive (or barely-interactive) overlays: ratings, watchlist state, format tags, watched/lock markers.</p><div id="badgesHost"></div></section>
    <section class="doc" id="input"><h2>Input Controls</h2><p class="lede">Keyboard tiles, numeric keypad keys, and device-code tiles &mdash; all a square/circular key with a resting-vs-focused fill swap.</p><div id="inputHost"></div></section>
    <section class="doc" id="panels"><h2>Panels, Facts &amp; Empty States</h2><p class="lede">Dialog chrome and the two recurring "nothing here" layouts.</p><div id="panelsHost"></div></section>
    <section class="doc" id="player"><h2>Player Chrome</h2><p class="lede">Transport bar and buffering overlay &mdash; the one surface that isn't part of the fragments.py pipeline at all, still fully hand-authored XML.</p><div id="playerHost"></div></section>

    <section class="doc" id="findings">
      <h2>Consolidation findings</h2>
      <p class="lede">What building this catalog actually surfaced &mdash; concrete candidates for the "more template elements, fewer varieties" half of the brief, not just documentation.</p>
      <div id="findingsHost"></div>
    </section>

    <footer>
      Generated by <code>tools/gen_design_language.py</code> from the add-on's own source (no values hand-typed from a screenshot). Regenerate after any change to <code>fragments.py</code>, <code>theme.py</code>, <code>fontinstall.py</code>, or the pill/row/badge markup in <code>main.xml.tpl</code> / <code>detail.xml.tpl</code>: <code>python3 tools/gen_design_language.py</code>.
    </footer>
  </main>
</div>

<script>
const PRESETS = [
  ["Tofa","2DD4BF"],["Sky","38BDF8"],["Emerald","34D399"],["Indigo","818CF8"],["Violet","A78BFA"],
  ["Pink","F472B6"],["Rose","FB7185"],["Orange","FB923C"],["Amber","FBBF24"],["Crimson","A31621"],
  ["Forest","15803D"],["Ocean","1E40AF"],["Plum","6B21A8"],["Snow","F1EFE8"],
];

function hexToRgb(hex) {{
  const n = parseInt(hex, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}}
// Mirrors theme.py:on_accent_text() exactly -- real WCAG relative
// luminance, not a fixed literal, so switching accents here demonstrates
// actual contrast behavior instead of just describing it.
function relativeLuminance(r, g, b) {{
  const ch = v => {{ v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }};
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}}
function onAccentText(r, g, b) {{
  const accentLum = relativeLuminance(r, g, b);
  const darkLum = relativeLuminance(4, 33, 30); // #04211e
  const lighter = Math.max(accentLum, darkLum), darker = Math.min(accentLum, darkLum);
  const darkContrast = (lighter + 0.05) / (darker + 0.05);
  const lightContrast = (1.0 + 0.05) / (accentLum + 0.05);
  return darkContrast >= lightContrast ? '#04211e' : '#ffffff';
}}
function setAccent(hex) {{
  const [r, g, b] = hexToRgb(hex);
  document.documentElement.style.setProperty('--ar', r);
  document.documentElement.style.setProperty('--ag', g);
  document.documentElement.style.setProperty('--ab', b);
  document.documentElement.style.setProperty('--on-accent', onAccentText(r, g, b));
  document.querySelectorAll('.accent-tint').forEach(el => {{
    const a = parseFloat(el.dataset.alpha || '1');
    el.style.background = `rgba(${{r}},${{g}},${{b}},${{a}})`;
  }});
  document.querySelectorAll('.accent-solid').forEach(el => {{ el.style.background = `rgb(${{r}},${{g}},${{b}})`; }});
  document.querySelectorAll('.accent-dot').forEach(el => el.classList.toggle('active', el.dataset.hex === hex));
}}

const accentGrid = document.getElementById('accentGrid');
const presetStrip = document.getElementById('presetStrip');
PRESETS.forEach(([name, hex]) => {{
  const dot = document.createElement('button');
  dot.className = 'accent-dot';
  dot.style.background = '#' + hex;
  dot.dataset.hex = hex;
  dot.title = name;
  dot.onclick = () => setAccent(hex);
  accentGrid.appendChild(dot);

  const sw = document.createElement('div');
  sw.className = 'swatch';
  sw.innerHTML = `<div class="chip" style="background:#${{hex}}"></div><div class="cap">${{name}}<b>#${{hex}}</b></div>`;
  presetStrip.appendChild(sw);
}});
setAccent('2DD4BF');

// ---------- alpha helpers, matching real Kodi hex-alpha bytes ----------
const wa = h => `rgba(255,255,255,${{(parseInt(h,16)/255).toFixed(3)}})`;
const ba = h => `rgba(3,11,16,${{(parseInt(h,16)/255).toFixed(3)}})`;
function aa(h) {{ return `rgba(var(--ar),var(--ag),var(--ab),${{(parseInt(h,16)/255).toFixed(3)}})`; }}
const ACCENT = 'var(--accent)';
const ON_ACCENT = 'var(--on-accent)';

// ---------- primitive 1: pill (also covers badges/keys/tabs) ----------
function pill({{w, h, radius = h/2, fill = 'transparent', border, borderColor, borderW = 2,
                textColor = '#fff', label, icon, iconTrailing, font = 600, size = 14, align = 'center'}}) {{
  const style = [
    `width:${{w}}px`, h ? `height:${{h}}px` : '', `border-radius:${{radius}}px`,
    `background:${{fill}}`,
    border ? `box-shadow: inset 0 0 0 ${{borderW}}px ${{borderColor}}` : '',
    `display:flex`, `align-items:center`,
    `justify-content:${{align === 'left' ? 'flex-start' : 'center'}}`,
    `gap:8px`, `padding:0 ${{align === 'left' ? 18 : 14}}px`,
    `color:${{textColor}}`, `font-weight:${{font}}`, `font-size:${{size}}px`,
  ].filter(Boolean).join(';');
  const ic = icon ? `<span class="icon" style="font-size:${{size+4}}px">${{icon}}</span>` : '';
  const tr = iconTrailing ? `<span class="icon" style="font-size:${{size+2}}px;margin-left:auto;opacity:.85">${{iconTrailing}}</span>` : '';
  return `<div class="p-pill" style="${{style}}">${{ic}}<span>${{label||''}}</span>${{tr}}</div>`;
}}

// ---------- primitive 2: list row ----------
function row({{w = 300, h = 54, fill = 'transparent', border, borderColor, accentBar = false,
               icon, label, count, textColor = '#fff', countColor = 'rgba(255,255,255,0.62)'}}) {{
  const style = [
    `width:${{w}}px`, `height:${{h}}px`, `border-radius:16px`, `background:${{fill}}`,
    border ? `box-shadow: inset 0 0 0 2px ${{borderColor}}` : '',
    `padding:0 16px`, `position:relative`,
  ].filter(Boolean).join(';');
  const bar = accentBar ? `<div style="position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:2px;background:${{ACCENT}}"></div>` : '';
  const ic = icon ? `<span class="icon" style="font-size:22px;color:${{textColor}}">${{icon}}</span>` : '';
  return `<div class="p-row" style="${{style}}">${{bar}}${{ic}}<span style="color:${{textColor}};font-weight:600;font-size:14px;flex:1">${{label}}</span>${{count!=null?`<span class="mono" style="color:${{countColor}};font-size:12.5px">${{count}}</span>`:''}}</div>`;
}}

// ---------- primitive 3: card (poster/episode/person shape) ----------
function card({{w, h, radius = 14, glow = false, border, thumb = 'poster', badge, caption, title, watermark}}) {{
  const grad = thumb === 'poster'
    ? 'linear-gradient(160deg, #3a3f6b, #1c2340 55%, #10162b)'
    : 'linear-gradient(160deg, #2c4a52, #16262c)';
  const glowEl = glow ? `<div style="position:absolute;inset:-10px;border-radius:${{radius+8}}px;background:${{ACCENT}};opacity:.35;filter:blur(10px)"></div>` : '';
  const borderEl = border ? `<div style="position:absolute;inset:0;border-radius:${{radius}}px;box-shadow:inset 0 0 0 2px ${{ACCENT}}"></div>` : '';
  const badgeEl = badge ? `<div style="position:absolute;top:8px;left:8px;padding:3px 8px;border-radius:6px;background:rgba(0,0,0,0.6);box-shadow:inset 0 0 0 1px rgba(255,255,255,.25);font-size:11px;font-weight:700" class="mono">${{badge}}</div>` : '';
  const wm = watermark ? `<span class="icon" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:${{Math.min(w,h)*0.32}}px;color:rgba(255,255,255,.18)">${{watermark}}</span>` : '';
  const capEl = (caption || title) ? `<div class="p-caption" style="margin-top:10px;width:${{w}}px">${{caption?`<span style="font-size:11px;color:rgba(255,255,255,.6)">${{caption}}</span>`:''}}${{title?`<span style="font-size:14px;font-weight:600">${{title}}</span>`:''}}</div>` : '';
  return `<div class="p-card" style="width:${{w}}px">
    <div style="position:relative;width:${{w}}px;height:${{h}}px">
      ${{glowEl}}
      <div style="position:relative;width:100%;height:100%;border-radius:${{radius}}px;background:${{grad}};overflow:hidden">${{wm}}</div>
      ${{borderEl}}${{badgeEl}}
    </div>${{capEl}}
  </div>`;
}}

// ---------- primitive 4: circle (avatar/photo/key) ----------
function circle({{size, fill = 'rgba(255,255,255,0.08)', border, borderColor, glow = false,
                   icon, label, textColor = '#fff', badge}}) {{
  const glowEl = glow ? `<div style="position:absolute;inset:-8px;border-radius:50%;background:${{ACCENT}};opacity:.4;filter:blur(8px)"></div>` : '';
  const borderEl = border ? `<div style="position:absolute;inset:0;border-radius:50%;box-shadow:inset 0 0 0 2px ${{borderColor}}"></div>` : '';
  const content = icon
    ? `<span class="icon" style="font-size:${{size*0.4}}px;color:${{textColor}}">${{icon}}</span>`
    : `<span class="mono" style="font-size:${{size*0.28}}px;font-weight:700;color:${{textColor}}">${{label||''}}</span>`;
  const badgeEl = badge ? `<div style="position:absolute;right:-2px;bottom:-2px;width:${{size*0.32}}px;height:${{size*0.32}}px;border-radius:50%;background:${{ACCENT}};display:flex;align-items:center;justify-content:center"><span class="icon" style="font-size:${{size*0.18}}px;color:${{ON_ACCENT}}">${{badge}}</span></div>` : '';
  return `<div style="position:relative;width:${{size}}px;height:${{size}}px">
    ${{glowEl}}
    <div style="position:relative;width:100%;height:100%;border-radius:50%;background:${{fill}};display:flex;align-items:center;justify-content:center;overflow:hidden">${{content}}</div>
    ${{borderEl}}${{badgeEl}}
  </div>`;
}}

// ---------- generic component renderer ----------
function renderComponent(host, c) {{
  const el = document.createElement('div');
  el.className = 'comp';
  const stateHtml = c.states.map(s => `
    <div class="state-slot">
      <span class="state-label">${{s.label}}</span>
      ${{s.render()}}
    </div>`).join('');
  const propsHtml = c.props ? `<table class="props">${{c.props.map(([k,v]) => `<tr><td>${{k}}</td><td>${{v}}</td></tr>`).join('')}}</table>` : '';
  el.innerHTML = `
    <div class="comp-head"><h3>${{c.name}}</h3><span class="comp-src">${{c.src}}</span></div>
    ${{c.desc ? `<p class="comp-desc">${{c.desc}}</p>` : ''}}
    <div class="stage">${{stateHtml}}</div>
    ${{propsHtml}}`;
  host.appendChild(el);
}}

// =========================================================================
// CARDS
// =========================================================================
const cardsHost = document.getElementById('cardsHost');
[
  {{
    name: 'Poster Card', src: 'fragments.py:poster_card() / poster_visual()',
    desc: '{cell_w}&times;{cell_h} cell, {poster_w}&times;{poster_h} poster, 16px mask radius, rating badge top-left, optional accent progress-fill strip flush with the bottom edge. Used identically on Home, Browse, Discover, Search, Person. <strong>A vertical GRID must add a gap below the caption</strong> &mdash; see Grid Row Pitch below.',
    states: [
      {{ label: 'Resting', render: () => card({{w:180,h:270,radius:11,thumb:'poster',badge:'92%',caption:'2009 &middot; Animation',title:'Up'}}) }},
      {{ label: 'Focused', render: () => card({{w:180,h:270,radius:11,thumb:'poster',glow:true,border:true,badge:'92%',caption:'2009 &middot; Animation',title:'Up'}}) }},
    ],
    props: [['Cell / poster','{cell_w}&times;{cell_h} / {poster_w}&times;{poster_h}'],['Mask radius','14px (poster-mask.png) &mdash; &sect;4\'s "TV poster cards" radius, and 7.9.3 states it outright; it was a hand-fitted 16 before that'],['Rating badge','52&times;28, {badge_scrim} fill + 1px {border} outline'],['Progress fill','accent, flush with poster bottom, pre-rendered % strip'],['Focus glow','card-glow.png, accent, 10px bleed all sides, 104.5% zoom'],['Caption','title tofa_font_poster_title / text_primary; meta tofa_font_metadata / text_secondary. NEITHER changes tier on focus &mdash; the meta line used to rest at text_tertiary and lift, alone in the card family, and measures a flat 62-63% in both states on every reference capture.'],['Caption (trailing)','Continue Watching only, right-justified on the meta baseline: tofa_font_micro / text_tertiary, bottom-aligned so the two sizes share a baseline. &sect;6 asks for "micro/uppercase at white 50%" &mdash; the string is already uppercase from progress.py, and 50% is not on the tier scale, so this takes the nearest tier below rather than reintroduce a one-off alpha. NB the real app renders this half at the SAME size as the year, not smaller.'],['Badge on focus','cleared on Browse/Home, KEPT on Person &mdash; both are the real app&rsquo;s own behaviour on their own screen (poster_visual(hide_rating_on_focus=))']],
  }},
  {{
    name: 'Grid Row Pitch', src: 'tokens.py:GRID_GAP_* / *_CELL_H',
    desc: 'A vertical grid needs more air below the caption than a horizontal row does: in a grid the caption has another row&rsquo;s artwork directly beneath it, so at bare CELL_H it reads as belonging to the wrong card. <strong>The app does not use one value</strong> &mdash; measured art-top to art-top off the native-1080p reference captures. Add a token here for any new grid rather than reaching for CELL_H; that is exactly how the person grid first shipped, and it looked cramped.',
    states: [
      {{ label: 'Row (CELL_H)', render: () => card({{w:180,h:270,radius:11,thumb:'poster',badge:'92%',caption:'2009',title:'Up'}}) }},
      {{ label: 'Grid (+gap)', render: () => card({{w:180,h:270,radius:11,thumb:'poster',badge:'92%',caption:'2009',title:'Up'}}) }},
    ],
    props: [['Horizontal row','{cell_h} (CELL_H) &mdash; Home / Discover / Search shelves'],['Browse grid','{cell_h} + {grid_gap_browse} = {browse_cell_h} (app measures 505)'],['Poster grid (default)','{cell_h} + {grid_gap_person} = {person_cell_h} &mdash; GRID_CELL_H; Person + Detail&rsquo;s More Like This (app measures 489)'],['Gotcha','Kodi&rsquo;s row-to-row advance follows the ITEMLAYOUT&rsquo;s declared height, so a grid must BOTH pass poster_card(extra_bottom_pad=) and set the panel&rsquo;s &lt;itemheight&gt;. Setting only one silently does nothing.']],
  }},
  {{
    name: 'Person / Cast Card', src: 'fragments.py:person_card()',
    desc: "290&times;290 cell, 190px circular photo. `scale` + `scalediffuse=\"false\"` is required for a true cover-crop circle &mdash; the default behavior distorts the diffuse MASK to match the content's own transform, not just the photo.",
    states: [
      {{ label: 'No photo', render: () => circle({{size:120, fill:'rgba(255,255,255,0.078)', label:'EA', textColor:'rgba(255,255,255,0.42)'}}) }},
      {{ label: 'Resting', render: () => card({{w:120,h:120,radius:60,thumb:'photo',glow:false}}) }},
      {{ label: 'Focused', render: () => circle({{size:120, fill:'rgba(255,255,255,0.078)', border:true, borderColor:'var(--accent)', glow:true, icon:'&#xE468;'}}) }},
    ],
    props: [['Cell / photo','290&times;290 / 190&times;190 (Detail); 170&times;220 / 130 (Search&rsquo;s Actors row)'],['Fallback','initials or user-round glyph, text_tertiary&rarr;text_secondary on focus'],['Focus ring','person-border-&lt;photo&gt;.png, 2px, accent &mdash; ONE ASSET PER SIZE. Kodi scales a texture&rsquo;s stroke with the texture, so the single 190px ring this used to share rendered at 1.4px in the 130px Actors tile.'],['Focus halo','person-glow-&lt;photo&gt;.png, same per-size rule'],['Name / role gap','34px (widened from 28 per explicit request)'],['Name','tofa_font_row_title, text_primary'],['Role','tofa_font_metadata, text_secondary &mdash; NOT poster_title. &sect;7 is explicit: the name in row-title white, with the character or role under it in metadata at white 62%. It was the title font, making a supporting line as heavy as a poster&rsquo;s name.']],
  }},
  {{
    name: 'Episode Card', src: 'fragments.py:episode_card()',
    desc: '350&times;284 cell, 330&times;186 16:9 still. Same exact-size mask/border/glow technique as posters &mdash; added specifically so episodes get "rounded corners + border/glow comparable to posters" instead of a bare rectangle.',
    states: [
      {{ label: 'Resting', render: () => card({{w:180,h:101,radius:9,thumb:'still',caption:'E1 &middot; 24m &middot; 4K',title:'Pilot'}}) }},
      {{ label: 'Focused + watched', render: () => card({{w:180,h:101,radius:9,thumb:'still',glow:true,border:true,badge:'&#x2713;',caption:'E1 &middot; 24m &middot; 4K',title:'Pilot'}}) }},
    ],
    props: [['Cell / thumb','350&times;284 / 330&times;186'],['Row gap','~134px art-to-art, matching Browse\'s poster grid'],['Corner badges','both inset 8 (CHIP_INSET) from the still: unaired capsule top-LEADING, watched check top-TRAILING so one episode can carry both. Different heights (24 / 28), so the shorter one\'s y is COMPUTED to keep the two centre-aligned.'],['Watched badge','28&times;28 accent circle, checkmark glyph'],['Caption','tofa_font_micro, text_secondary &mdash; same in both states'],['Title','tofa_font_poster_title, text_primary &mdash; same in both states']],
  }},
  {{
    name: 'Top Result Card', src: 'fragments.py:top_result_card()',
    desc: 'Search\'s hero result: the same poster_visual() rendering (not a hand-copy) plus an eyebrow/title/meta/ratings/overview text block to the right, 1089&times;390 total.',
    states: [
      {{ label: 'Result', render: () => `<div style="display:flex;gap:20px">${{card({{w:110,h:165,radius:8,thumb:'poster'}})}}<div style="max-width:340px"><div style="font-size:10px;letter-spacing:1.4px;color:rgba(255,255,255,.5);font-weight:700">TOP RESULT</div><div style="font-size:22px;font-weight:600;margin:4px 0 8px">Up</div><div style="font-size:12px;color:rgba(255,255,255,.7)">2009 &middot; PG &middot; 1h 36m</div><div style="font-size:12px;color:rgba(255,255,255,.7);margin:2px 0 8px">Critics 93 &middot; Audience 82</div><div style="font-size:12px;color:rgba(255,255,255,.6)">By tying thousands of balloons to his house, 78-year-old Carl sets out to fulfill his lifelong dream&hellip;</div></div></div>` }},
    ],
    props: [['Cell','1089&times;390 (TOP_RESULT_CELL_W/H &mdash; tokens, because list 6805 in main.xml.tpl declares the same pair and a vertical list advances by the ITEMLAYOUT\'s height)'],['Text column','starts x=HPAD+POSTER_W+34=300, 700px wide (overview 760, the only line that wraps)'],['Eyebrow','tofa_font_eyebrow, text_tertiary'],['Title','tofa_font_section_title, white'],['Placeholder','poster_visual()\'s, and ONLY that one. This card carried a second hand-rolled 64pt film glyph from before poster_visual() had one, so an artwork-less result drew the mark twice, 15px apart, with only one of them zooming on focus.']],
  }},
  {{
    name: 'Collections Tile', src: 'fragments.py:collection_card()',
    desc: '7.5\'s collections index: the ONE landscape 16:9 tile in an app of 2:3 portraits, because "a collection is a set, not a title". Numbers are the spec\'s verbatim, and the Android TV app lays its own out at exactly the same values.',
    states: [
      {{ label: 'Resting', render: () => card({{w:200,h:113,radius:6,thumb:'still',title:'Studio Ghibli',caption:'24 titles'}}) }},
      {{ label: 'Focused', render: () => card({{w:200,h:113,radius:6,thumb:'still',glow:true,border:true,title:'Studio Ghibli',caption:'24 titles'}}) }},
    ],
    props: [['Tile / cell','448&times;252 / 478&times;382 (gaps 30/44)'],['Radius','14 (COLLECTION_RADIUS)'],['Caption','fixed 86 tall whatever the name wraps to, so a row of tiles stays aligned'],['Artwork ladder','backdrop cropped to fill &rarr; poster FITTED (never cropped to 16:9) over a dimmed copy of itself standing in for the spec\'s blurred plate, which Kodi cannot produce &rarr; plate + film-stack glyph'],['Focus glow','collection-glow.png &mdash; this tile was the last card in the family without one. Its cell\'s slack is all on the right/bottom, so the content group is offset by GLOW_PAD and panel 6210 pulled back to match; the grid lands on the same pixels either way.'],['Focus rim','rounded-14-outline.png written as a 9-patch, but SHIPPED exact-size: build.py collects it and gen_exact_assets.py emits exact-rounded-14-outline-448x252.png at 2x.'],['Caption zoom','NONE &mdash; it used to take the tile\'s focus zoom, alone in the family, about a centre 130px above itself, which pushed the name out of line with every neighbour\'s.']],
  }},
  {{
    name: 'Profile Avatar Card', src: 'script-tofa-profile.xml',
    desc: '"Who\'s watching?" picker. Photo &gt; 1 of 12 bespoke SVG avatars &gt; initial, in that priority &mdash; a font glyph can\'t reproduce multi-color avatar art, so these are pre-rasterized PNGs, the one card type that isn\'t vector/CSS-shape-driven.',
    states: [
      {{ label: 'Resting', render: () => circle({{size:120, fill:'rgba(255,255,255,0.16)', border:true, borderColor:'rgba(255,255,255,0.25)', icon:'&#xE468;'}}) }},
      {{ label: 'Focused', render: () => circle({{size:120, fill:'rgba(255,255,255,0.16)', border:true, borderColor:'var(--accent)', icon:'&#xE468;'}}) }},
      {{ label: 'Locked + Kids', render: () => `<div style="position:relative">${{circle({{size:120, fill:'rgba(255,255,255,0.16)', border:true, borderColor:'rgba(255,255,255,0.25)', icon:'&#xE468;', badge:'&#xE10B;'}})}}<div style="margin-top:10px">${{pill({{w:70,h:26,radius:13,fill:'rgba(255,255,255,0.12)',textColor:'rgba(255,255,255,0.6)',label:'Kids',size:11}})}}</div></div>` }},
    ],
    props: [['Cell / circle','300&times;360 / 180&times;180'],['Ring','0x40FFFFFF resting &rarr; accent focused'],['Lock badge','48&times;48, 0xFF16232B, lock glyph'],['Kids tag','tag-pill.png border=13, 70&times;26']],
  }},
].forEach(c => renderComponent(cardsHost, c));

// =========================================================================
// PILLS & BUTTONS
// =========================================================================
const pillsHost = document.getElementById('pillsHost');
[
  {{
    name: 'Primary CTA Pill (Play/Resume)', src: 'detail.xml.tpl id 5210',
    desc: 'The only fully solid-filled pill in the app &mdash; no glass state, just a focus-darken overlay. border=32 on a 64px-tall pill (radius = height/2, a true capsule).',
    states: [
      {{ label: 'Resting', render: () => pill({{w:170,h:56,fill:'var(--accent)',textColor:'var(--on-accent)',icon:'&#xE13C;',label:'Play'}}) }},
      {{ label: 'Focused', render: () => `<div style="position:relative">${{pill({{w:170,h:56,fill:'var(--accent)',textColor:'var(--on-accent)',icon:'&#xE13C;',label:'Play'}})}}<div style="position:absolute;inset:0;border-radius:28px;background:rgba(0,0,0,.25)"></div></div>` }},
    ],
    props: [['Size','280&times;64, radius 32'],['Fill','accent_color, solid'],['Focus','same texture + 0x40000000 darken overlay'],['Text','on_accent_color &mdash; contrast-picked per accent (0x04211E or white), see theme.py:on_accent_text()'],['Resume progress','232&times;3 strip flush bottom, on-accent color']],
  }},
  {{
    name: 'Glass Action Pill (Rewatch / Options / Watchlist)', src: 'fragments.py:glass_pill(), spliced into detail.xml.tpl as ids 5220/5225/5230',
    desc: 'The default "secondary button": faint always-on outline at rest, swaps to solid accent-tinted fill + accent outline on focus. Same state machine on all three.',
    states: [
      {{ label: 'Resting', render: () => pill({{w:170,h:56,fill:'rgba(255,255,255,0.078)',border:true,borderColor:'rgba(255,255,255,0.118)',textColor:'#fff',icon:'&#xE29A;',label:'Options',iconTrailing:'&#xE06D;'}}) }},
      {{ label: 'Focused', render: () => pill({{w:170,h:56,fill:'var(--accent-pill, rgba(var(--ar),var(--ag),var(--ab),0.239))',border:true,borderColor:'var(--accent)',textColor:'#fff',icon:'&#xE29A;',label:'Options',iconTrailing:'&#xE06D;'}}) }},
    ],
    props: [['Size','200/240&times;64, radius 32 (capsule-pill.png border=32)'],['Rest fill / outline','{glass_rest} / {glass_raised} (always drawn)'],['Focus fill / outline','accent_pill_fill (0x3D+accent) / accent_color'],['Text','white in both states'],['Icon alignment','left-aligned with text, not centered &mdash; avoids icon/label collision (a real bug fixed this session)']],
  }},
  {{
    name: 'Sort Pill (always-active)', src: 'fragments.py:browse_pill(), spliced into main.xml.tpl as id 6110',
    desc: 'Browse\'s Sort pill has no "inactive" concept &mdash; it always shows the current sort as accent-tinted text on an accent-tinted glass fill, only the outline responds to focus.',
    states: [
      {{ label: 'Unfocused', render: () => pill({{w:230,h:52,radius:26,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',textColor:'var(--accent)',icon:'&#xE37D;',label:'Sort: Date Added',iconTrailing:'&#xE06D;',size:13}}) }},
      {{ label: 'Focused', render: () => pill({{w:230,h:52,radius:26,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',border:true,borderColor:'#fff',textColor:'var(--accent)',icon:'&#xE37D;',label:'Sort: Date Added',iconTrailing:'&#xE06D;',size:13}}) }},
    ],
    props: [['Size','346&times;62, radius 29'],['Fill','accent_pill_fill in every state (no rest/active split)'],['Focus','adds white outline only'],['Text/icon','accent_color in every state']],
  }},
  {{
    name: 'Filter / Quality / Genre Pill (4-state)', src: 'fragments.py:browse_pill(), spliced into main.xml.tpl as ids 6120/6130/6100',
    desc: 'The one component with a genuine 2&times;2 state matrix: active-vs-inactive (does a filter apply?) crossed with focused-vs-not.',
    states: [
      {{ label: 'Inactive', render: () => pill({{w:180,h:52,radius:26,fill:'rgba(255,255,255,0.078)',textColor:'rgba(255,255,255,0.82)',icon:'&#xE29A;',label:'Filter',size:13}}) }},
      {{ label: 'Active', render: () => pill({{w:180,h:52,radius:26,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',textColor:'var(--accent)',icon:'&#xE29A;',label:'Filter',size:13}}) }},
      {{ label: 'Inactive, focused', render: () => pill({{w:180,h:52,radius:26,fill:'rgba(255,255,255,0.118)',border:true,borderColor:'var(--accent)',textColor:'#fff',icon:'&#xE29A;',label:'Filter',size:13}}) }},
      {{ label: 'Active, focused', render: () => pill({{w:180,h:52,radius:26,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',border:true,borderColor:'#fff',textColor:'var(--accent)',icon:'&#xE29A;',label:'Filter',size:13}}) }},
    ],
    props: [['Size','346&times;62, radius 29'],['Active gate','ListItem.Property(active)'],['Focus gate','Control.HasFocus(id) &mdash; re-armed independently of active state']],
  }},
  {{
    name: 'Discover Tab Pill (Now / Acclaimed / Genres / Decades)', src: 'fragments.py:discover_tab_pill(), ids 6900/6910/6920/6930',
    desc: 'Groups the server\'s 32 flat shelves into four tabs by each shelf\'s own <code class="mono">kind</code>. Four separate 1-item lists rather than one 4-item list: a Kodi list has a single itemwidth, and these pills hug their labels (110/186/144/165 measured off the real app, = label width at {tab_font} plus 26px padding a side). Active state is gated on <code class="mono">Window.Property(discover_tab)</code>, NOT on itemlayout-vs-focusedlayout &mdash; a 1-item list\'s sole item is always "current", so Kodi draws every pill through focusedlayout and all four rendered accent-filled on the first attempt.',
    states: [
      {{ label: 'Inactive', render: () => pill({{w:144,h:54,radius:27,fill:'rgba(255,255,255,{tab_faint_css})',border:true,borderColor:'rgba(255,255,255,{tab_raised_css})',textColor:'#fff',label:'Genres',size:15}}) }},
      {{ label: 'Active', render: () => pill({{w:110,h:54,radius:27,fill:'var(--accent)',textColor:'var(--on-accent)',label:'Now',size:15}}) }},
      {{ label: 'Active, focused', render: () => pill({{w:110,h:54,radius:27,fill:'var(--accent)',border:true,borderColor:'#fff',textColor:'var(--on-accent)',label:'Now',size:15}}) }},
    ],
    props: [['Size','height 54, width per label (110/186/144/165)'],['Layout','x from CONTENT_LEFT, 18px gaps &mdash; fragments.discover_tab_positions()'],['Active gate','Window.Property(discover_tab) equals the pill\'s own key'],['Focus','white outline over whichever fill is showing, so colour identity is kept']],
  }},
  {{
    name: 'Tab Bar Pill (Detail)', src: 'detail.xml.tpl &mdash; exact-size PNGs, no 9-patch',
    desc: 'The one pill family that abandoned border-attribute 9-patch entirely: at ~140-230px wide with a 22px radius, the source asset\'s corner art ran out of straight middle section to stretch, rendering as "an arrow at the left/right, bulging top/bottom." Fixed with one dedicated exact-size PNG per tab.',
    states: [
      {{ label: 'Resting', render: () => pill({{w:150,h:40,radius:20,fill:'rgba(255,255,255,0.118)',textColor:'rgba(255,255,255,0.54)',label:'About',size:13}}) }},
      {{ label: 'Active, unfocused', render: () => pill({{w:150,h:40,radius:20,fill:'rgba(255,255,255,0.118)',border:true,borderColor:'#fff',textColor:'#fff',label:'Cast &amp; Crew',size:13}}) }},
      {{ label: 'Active, focused', render: () => pill({{w:150,h:40,radius:20,fill:'rgba(255,255,255,0.118)',border:true,borderColor:'var(--accent)',textColor:'var(--accent)',label:'Cast &amp; Crew',size:13}}) }},
    ],
    props: [['Height','44px, radius 22 (baked into each tab\'s own asset)'],['Active underline','3px accent bar, centered under label text, 3px below pill'],['Why no border=','9-patch needs real straight edge to sample; too narrow here &mdash; see project_kodi_9patch_needs_straight_edges']],
  }},
  {{
    name: 'Ghost Button (Retry / Cancel / Back)', src: 'script-tofa-signin.xml, script-tofa-profile.xml',
    desc: 'Outline-only at rest, no fill until focused. Its own dedicated capsule asset at border=38/90px &mdash; NOT the sign-in pill\'s border=33/80px asset, since one 9-patch source can\'t serve two different radii.',
    states: [
      {{ label: 'Resting', render: () => pill({{w:160,h:64,fill:'rgba(var(--ar),var(--ag),var(--ab),0.2)',border:true,borderColor:'var(--accent)',textColor:'var(--accent)',icon:'&#xE0A5;',label:'Retry'}}) }},
      {{ label: 'Focused', render: () => pill({{w:160,h:64,fill:'rgba(var(--ar),var(--ag),var(--ab),0.333)',border:true,borderColor:'var(--accent)',textColor:'var(--accent)',icon:'&#xE0A5;',label:'Retry'}}) }},
    ],
    props: [['Size','366&times;76 (Retry) / 300&times;76 (Cancel)'],['Fill rest / focus','0x332DD4BF / 0x552DD4BF (Retry) or 0x1FFFFFFF static (Cancel)'],['Outline','always drawn, not focus-gated (unlike most other pills)']],
  }},
  {{
    name: 'Done Button (PickerDialog)', src: 'script-tofa-picker.xml id 103',
    desc: 'Always solid accent-filled, same "no inactive state" pattern as the Primary CTA and Sort pill.',
    states: [
      {{ label: 'Resting', render: () => pill({{w:200,h:56,fill:'var(--accent)',textColor:'var(--on-accent)',label:'Done'}}) }},
      {{ label: 'Focused', render: () => pill({{w:200,h:56,fill:'var(--accent)',border:true,borderColor:'#fff',textColor:'var(--on-accent)',label:'Done'}}) }},
    ],
    props: [['Size','572&times;64, radius 29'],['Fill','accent, always'],['Focus','adds white outline ring only']],
  }},
  {{
    name: 'Sign-in Link Pill', src: 'script-tofa-signin.xml',
    desc: 'The one pill in the app with an opaque non-glass, non-accent fill (a fixed slate) &mdash; it displays a plain URL, not an accent-brand action.',
    states: [
      {{ label: 'Static (no focus state)', render: () => pill({{w:280,h:52,radius:26,fill:'#2A3043',border:true,borderColor:'rgba(255,255,255,0.2)',textColor:'#fff',icon:'&#xE1DB;',label:'tofa.tv/link',size:14}}) }},
    ],
    props: [['Size','416&times;66, radius 33'],['Fill','0xFF2A3043 (opaque slate, not glass)'],['Icon','tofa teal, fixed &mdash; not accent-derived'],['Text','Roboto Mono (only pill using the mono family)']],
  }},
].forEach(c => renderComponent(pillsHost, c));

// =========================================================================
// ROWS & LISTS
// =========================================================================
const rowsHost = document.getElementById('rowsHost');
[
  {{
    name: 'Top Nav Bar Tab', src: 'fragments.py:nav_bar()',
    desc: 'Two focus sizes for the same tab: a full 204&times;64 pill while the nav bar itself has literal cursor focus, shrinking to an inset 188&times;44 "still selected, but focus moved into the screen" pill otherwise.',
    states: [
      {{ label: 'Resting', render: () => pill({{w:150,h:56,radius:22,textColor:'#fff',icon:'&#xE1F3;',label:'Home',align:'left'}}) }},
      {{ label: 'Selected (nav has focus)', render: () => pill({{w:150,h:56,radius:22,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',textColor:'var(--accent)',icon:'&#xE1F3;',label:'Home',align:'left'}}) }},
      {{ label: 'Selected (focus moved away)', render: () => pill({{w:135,h:40,radius:16,fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)',textColor:'var(--accent)',icon:'&#xE1F3;',label:'Home',align:'left',size:12}}) }},
    ],
    props: [['Full / small pill','204&times;60 / 188&times;44, both accent_pill_fill'],['Small pill inset','8px on every side &mdash; a dedicated flat asset, not a smaller border= on the same 9-patch'],['Fill both states','accent_pill_fill (0x3D+accent)']],
  }},
  {{
    name: 'Sidebar Row (Browse sources / Season list)', src: 'fragments.py:sidebar_row() &rarr; main.xml.tpl 6000/6010; detail.xml.tpl 6400 stays hand-typed',
    desc: 'Reused verbatim (down to the exact focus-vs-selected gating logic) between Browse\'s library sidebar and Detail\'s season sidebar &mdash; a good candidate for one shared fragments.py row() the way poster_card() already unified posters.',
    states: [
      {{ label: 'Resting', render: () => row({{w:260,h:52,icon:'&#xE1CE;',label:'Movies',count:734,textColor:'rgba(255,255,255,0.82)'}}) }},
      {{ label: 'Active (list unfocused)', render: () => row({{w:260,h:52,fill:'rgba(255,255,255,0.06)',accentBar:true,icon:'&#xE1CE;',label:'Movies',count:734,textColor:'var(--accent)',countColor:'var(--accent)'}}) }},
      {{ label: 'Active + focused', render: () => row({{w:260,h:52,fill:'rgba(255,255,255,0.12)',border:true,borderColor:'var(--accent)',accentBar:true,icon:'&#xE1CE;',label:'Movies',count:734,textColor:'#fff'}}) }},
    ],
    props: [['Cell','300&times;60 (Browse) / 260&times;60 (Season, narrower, no icon)'],['Accent left bar','3&times;42, inset 8px top/bottom'],['Why focus is a separate gate','Kodi renders focusedlayout for the CURRENT item even without real keyboard focus &mdash; every accent layer is re-gated on Control.HasFocus(id) so an unfocused-but-selected row reads as "selected," not "focused"']],
  }},
  {{
    name: 'Search History Row', src: 'main.xml.tpl id 6860',
    desc: 'Simpler cousin of the sidebar row &mdash; no active/selected concept (a search history entry has no "current" state), just resting vs. focused.',
    states: [
      {{ label: 'Resting', render: () => row({{w:340,h:48,icon:'&#xE1F5;',label:'The Bear',textColor:'rgba(255,255,255,0.82)'}}) }},
      {{ label: 'Focused', render: () => row({{w:340,h:48,fill:'rgba(255,255,255,0.118)',icon:'&#xE1F5;',label:'The Bear',textColor:'#fff'}}) }},
    ],
    props: [['Cell','600&times;58, visible 600&times;54'],['Focus fill','0x1FFFFFFF'],['Icon focus color','accent_color']],
  }},
  {{
    name: 'Picker Row (single &amp; multi mode)', src: 'script-tofa-picker.xml',
    desc: 'Sort/Quality use single-select (a direction glyph on the active row); Watch Status/Year use multi-select (checkmark only, no direction).',
    states: [
      {{ label: 'Resting', render: () => row({{w:340,h:54,label:'Date Added',textColor:'rgba(255,255,255,0.82)'}}) }},
      {{ label: 'Selected', render: () => `<div style="width:340px;height:54px;border-radius:16px;background:var(--accent);display:flex;align-items:center;padding:0 16px;color:var(--on-accent);font-weight:600;font-size:14px;justify-content:space-between">Date Added <span class="icon">&#xE06C;</span></div>` }},
      {{ label: 'Focused (unselected)', render: () => row({{w:340,h:54,border:true,borderColor:'#fff',label:'Date Added',textColor:'#fff'}}) }},
    ],
    props: [['Cell','572&times;70 (single) / 572&times;54 (multi)'],['Selected fill','accent_color, solid'],['Selected text','on-accent literal']],
  }},
  {{
    name: 'abc / 123 Tab Switcher', src: 'main.xml.tpl id 6702',
    desc: 'A segmented control inside Search\'s keyboard pane: one flat track end to end, with the selected mode signalled by label colour alone. Corrected 2026-07-31 against a live capture of the real Apple TV app, which draws no fill behind the selected segment and whose track measured {glass_track} (the Kodi build had a {glass_divider} track plus a 0x40 pill, ~6&times; the ladder ceiling). Kodi\'s d-pad focus is a separate concern and keeps the solid white tile, matching the letter keys either side of it.',
    states: [
      {{ label: 'Non-current', render: () => pill({{w:100,h:44,radius:20,textColor:'rgba(255,255,255,0.62)',label:'123'}}) }},
      {{ label: 'Current (selected mode)', render: () => pill({{w:100,h:44,radius:20,textColor:'#fff',label:'abc'}}) }},
      {{ label: 'Current, focused', render: () => pill({{w:100,h:44,radius:20,fill:'#fff',textColor:'var(--on-accent)',label:'abc'}}) }},
    ],
    props: [['Track','444&times;60, {glass_track} (SURFACE_TRACK), always drawn behind both items'],['Item','222&times;60, visible 214&times;52'],['Selected','label text_primary; no fill'],['Unselected','label text_secondary, same tier as the letter keys']],
  }},
].forEach(c => renderComponent(rowsHost, c));

// =========================================================================
// BADGES & INDICATORS
// =========================================================================
const badgesHost = document.getElementById('badgesHost');
[
  {{
    name: 'Rating Badge', src: 'fragments.py:rating_badge()',
    desc: 'Top-left on every poster card everywhere. A dedicated 52&times;28 outline asset replaced a shared 4px-border 9-patch that read too heavy at this size.',
    states: [{{ label: 'On poster', render: () => pill({{w:52,h:28,radius:6,fill:'rgba(0,0,0,0.6)',border:true,borderColor:'rgba(255,255,255,0.25)',textColor:'rgba(255,255,255,0.92)',label:'92%',size:11}}) }}],
    props: [['Size','52&times;28'],['Fill','0x99000000'],['Outline','1px, badge-outline.png, 0x40FFFFFF'],['Font','tofa_font_micro']],
  }},
  {{
    name: 'Watchlist Badge (Discover)', src: 'fragments.py:watchlist_badge_item/_focused()',
    desc: 'Top-right, +/checkmark toggle. Circular, unlike every other badge on this page.',
    states: [
      {{ label: 'Not in list', render: () => circle({{size:28,fill:'rgba(3,11,16,0.7)',border:true,borderColor:'rgba(255,255,255,0.2)',label:'+',textColor:'rgba(255,255,255,0.9)'}}) }},
      {{ label: 'Focused', render: () => circle({{size:28,fill:'var(--accent)',label:'+',textColor:'var(--on-accent)'}}) }},
    ],
    props: [['Size','28&times;28, same 8px inset as rating badge'],['Focus fill','solid accent'],['Focus text','on-accent literal']],
  }},
  {{
    name: 'Format Badge', src: 'detail.xml.tpl hero + About tab',
    desc: 'Static, informational only &mdash; no focus/active state at all. Tightest radius of any pill-shaped element in the app (border=6 vs. 16+ everywhere else).',
    states: [
      {{ label: '3-slot row', render: () => `<div style="display:flex;gap:8px">${{pill({{w:80,h:28,radius:4,fill:'rgba(255,255,255,0.25)',textColor:'rgba(255,255,255,0.82)',label:'4K',size:11}})}}${{pill({{w:100,h:28,radius:4,fill:'rgba(255,255,255,0.25)',textColor:'rgba(255,255,255,0.82)',label:'HDR10',size:11}})}}${{pill({{w:130,h:28,radius:4,fill:'rgba(255,255,255,0.25)',textColor:'rgba(255,255,255,0.82)',label:'ATMOS 7.1',size:11}})}}</div>` }},
    ],
    props: [['Slot widths','150 / 150 / 200, fixed positional, not semantic'],['Fill','0x40FFFFFF'],['Font','tofa_font_micro']],
  }},
  {{
    name: 'Kids Tag', src: 'script-tofa-profile.xml',
    desc: 'Reuses tag-pill.png, the same asset the design spec earmarks for filter chips &mdash; currently its only caller.',
    states: [{{ label: 'On profile card', render: () => pill({{w:64,h:24,radius:12,fill:'rgba(255,255,255,0.12)',textColor:'rgba(255,255,255,0.6)',label:'Kids',size:10}}) }}],
    props: [['Size','70&times;26'],['Radius','13 (tag-pill.png border=13)']],
  }},
  {{
    name: 'Watched Checkmark', src: 'fragments.py:episode_card()',
    desc: 'Solid accent circle, top-right corner overlap on a thumbnail.',
    states: [{{ label: 'Watched', render: () => circle({{size:28,fill:'var(--accent)',icon:'&#xE06C;',textColor:'var(--on-accent)'}}) }}],
    props: [['Size','28&times;28'],['Fill','solid accent'],['Glyph color','on-accent literal']],
  }},
  {{
    name: 'PIN Progress Dot', src: 'script-tofa-profile.xml',
    desc: 'A 4-dot row tracking PIN entry progress, no interaction of its own.',
    states: [
      {{ label: 'Empty', render: () => circle({{size:16, fill:'transparent', border:true, borderColor:'rgba(255,255,255,0.25)'}}) }},
      {{ label: 'Filled', render: () => circle({{size:16, fill:'#fff'}}) }},
    ],
    props: [['Size','16&times;16, 40px pitch'],['Empty','circle-outline.png, 0x40FFFFFF'],['Filled','circle.png, white']],
  }},
].forEach(c => renderComponent(badgesHost, c));

// =========================================================================
// INPUT CONTROLS
// =========================================================================
const inputHost = document.getElementById('inputHost');
[
  {{
    name: 'Search Keyboard Tile', src: 'main.xml.tpl ids 6700/6703',
    desc: 'A 74&times;74 cell holding a smaller 60&times;60 focus square, with a 106% zoom pop on focus &mdash; the only alphabet/keypad control in the app with a scale animation, not just a fill swap.',
    states: [
      {{ label: 'Resting', render: () => `<div style="width:56px;height:56px;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:600;color:rgba(255,255,255,0.7)">u</div>` }},
      {{ label: 'Focused', render: () => pill({{w:56,h:56,radius:12,fill:'#fff',textColor:'var(--on-accent)',label:'u',size:20}}) }},
    ],
    props: [['Cell / focus square','74&times;74 / 60&times;60, inset 7px'],['Focus animation','zoom 100%&rarr;106%, 120ms'],['Focused fill','white, solid'],['Focused text','on-accent literal']],
  }},
  {{
    name: 'PIN Keypad Key', src: 'script-tofa-profile.xml ids 900-910',
    desc: '100px circular key, digit or backspace glyph. Same rest/focus ladder as the person-card focus ring, just opaque instead of a photo.',
    states: [
      {{ label: 'Resting', render: () => circle({{size:80, fill:'rgba(255,255,255,0.12)', label:'5'}}) }},
      {{ label: 'Focused', render: () => circle({{size:80, fill:'rgba(var(--ar),var(--ag),var(--ab),0.239)', border:true, borderColor:'var(--accent)', label:'5', textColor:'var(--accent)'}}) }},
    ],
    props: [['Size','100&times;100 circle'],['Grid pitch','116px both axes, 3 cols &times; 4 rows'],['Focus fill','accent_pill_fill'],['Backspace','tofa_font_icons_36 glyph instead of a digit']],
  }},
  {{
    name: 'Device-Code Tile', src: 'script-tofa-signin.xml',
    desc: 'The TV pairing-code display &mdash; 8 static tiles, no focus state (nothing to select, just a code to read/copy).',
    states: [{{ label: 'Static', render: () => `<div style="display:flex;gap:8px">${{['X','7','K','9'].map(c=>pill({{w:52,h:70,radius:10,fill:'rgba(20,38,46,1)',border:true,borderColor:'rgba(42,122,114,0.67)',textColor:'#fff',label:c,size:22}})).join('')}}</div>` }}],
    props: [['Tile','93&times;127, 14px gap, radius 14'],['Fill','0xFF14262E'],['Outline','0xAA2A7A72'],['Font','tofa_font_code (Roboto Mono Bold)']],
  }},
].forEach(c => renderComponent(inputHost, c));

// =========================================================================
// PANELS, FACTS & EMPTY STATES
// =========================================================================
const panelsHost = document.getElementById('panelsHost');
[
  {{
    name: 'PickerDialog Frame', src: 'script-tofa-picker.xml',
    desc: 'Sort/Filter/Quality/Genre share this one dialog shell &mdash; a dark glass card over whatever\'s behind it.',
    states: [{{ label: 'Frame', render: () => `<div style="width:280px;height:200px;border-radius:16px;background:rgba(3,11,16,0.95);box-shadow:inset 0 0 0 1px rgba(255,255,255,0.118);padding:16px"><div style="font-weight:700;font-size:14px;margin-bottom:10px">Sort By</div>${{row({{w:248,h:36,fill:'var(--accent)',label:'Date Added'}})}}</div>` }}],
    props: [['Size','620&times;760, radius 24'],['Fill','0xF2030B10'],['Outline','0x1EFFFFFF']],
  }},
  {{
    name: 'About Tab Facts Panel', src: 'detail.xml.tpl',
    desc: '5 fixed eyebrow/value slots, 92px pitch, each hidden independently when that field has no data.',
    states: [{{ label: 'Slot', render: () => `<div><div style="font-size:10px;letter-spacing:1.2px;color:rgba(255,255,255,0.5);font-weight:700">| RELEASED</div><div style="font-size:16px;margin-top:6px">May 29, 2009</div></div>` }}],
    props: [['Pitch','92px vertical'],['Eyebrow','tofa_font_eyebrow, text_tertiary, literal "| " prefix']],
  }},
  {{
    name: 'Empty State (no results / nothing similar)', src: 'main.xml.tpl + detail.xml.tpl',
    desc: 'Same icon &rarr; heading &rarr; subtext grammar reused for Search\'s "No results" and Detail\'s "Nothing similar yet."',
    states: [{{ label: 'Empty', render: () => `<div class="empty-mock"><span class="icon">&#xE529;</span><h5>Nothing similar yet</h5><p>We couldn't find related titles for this one.</p></div>` }}],
    props: [['Icon size','56pt or 64pt role depending on screen'],['Heading','font30, white'],['Subtext','font13, 0x9EFFFFFF']],
  }},
].forEach(c => renderComponent(panelsHost, c));

// =========================================================================
// PLAYER CHROME
// =========================================================================
const playerHost = document.getElementById('playerHost');
[
  {{
    name: 'Transport Bar', src: 'script-tofa-player.xml',
    desc: 'The one surface in the whole app never migrated onto the fragments.py pipeline &mdash; still fully hand-authored, no shared component reuse at all.',
    states: [{{ label: 'OSD', render: () => `<div style="width:420px;padding:16px;border-radius:12px;background:linear-gradient(180deg,transparent,rgba(3,11,16,0.9))"><div style="font-weight:600;margin-bottom:10px">Up</div><div style="height:4px;border-radius:2px;background:rgba(255,255,255,0.16);position:relative"><div style="position:absolute;left:0;top:0;bottom:0;width:38%;border-radius:2px;background:var(--accent)"></div></div><div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;color:rgba(255,255,255,0.62)" class="mono"><span>34:12</span><span>1:36:00</span></div></div>` }}],
    props: [['Scrim','fade-bottom.png, 1920&times;280, 0xC8030B10'],['Progress track','white-square.png, 4px, TofaHairlineHi'],['Progress fill','pre-rendered strip, TofaAccent'],['Timecodes','tofa_font_micro, 0x9EFFFFFF']],
  }},
  {{
    name: 'Buffering Overlay', src: 'script-tofa-player.xml',
    desc: 'Full-bleed scrim + spinner, shown during Opening/Buffering player states.',
    states: [{{ label: 'Buffering', render: () => `<div style="width:200px;height:140px;border-radius:12px;background:rgba(3,11,16,0.7);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px"><div style="width:36px;height:36px;border-radius:50%;border:3px solid rgba(255,255,255,0.2);border-top-color:var(--accent);animation:spin 1s linear infinite"></div><span style="font-size:12px;color:rgba(255,255,255,0.62)">Loading&hellip;</span></div><style>@keyframes spin{{to{{transform:rotate(360deg)}}}}</style>` }}],
    props: [['Scrim','0xB0030B10, full-bleed'],['Spinner','spinner-arc.png, an open ring, accent-tinted']],
  }},
].forEach(c => renderComponent(playerHost, c));

// =========================================================================
// TYPE SCALE
// =========================================================================
const typeScale = document.getElementById('typeScale');
[
  ['tofa_font_hero', 'Inter Tight Bold', 77, 700, 'Up'],
  ['tofa_font_heading', 'Inter Tight Bold', 57, 700, 'Change is in the air.'],
  ['tofa_font_dialog_title', 'Inter Tight Bold', 34, 700, 'Remove from Watchlist?'],
  ['tofa_font_section_title', 'Inter Tight SemiBold', 39, 600, 'Continue Watching'],
  ['tofa_font_row_title', 'Inter Tight SemiBold', 26, 600, 'Cast &amp; Crew'],
  ['tofa_font_poster_title', 'Inter Tight SemiBold', 24, 600, 'Up'],
  ['tofa_font_sidebar_label', 'Inter Tight Regular', 26, 400, 'Movies'],
  ['tofa_font_body', 'Inter Tight Regular', 24, 400, 'By tying thousands of balloons to his house&hellip;'],
  ['tofa_font_metadata', 'Inter Tight Regular', 23, 400, '10\'734 items'],
  ['tofa_font_account', 'Inter Tight SemiBold', 20, 600, 'firstname.lastname@example.com'],
  ['tofa_font_button', 'Inter Tight SemiBold', 28, 600, 'Retry'],
  ['tofa_font_caption', 'Inter Tight SemiBold', 25, 600, 'CODE EXPIRED'],
  ['tofa_font_eyebrow', 'Inter Tight Bold', 17, 700, '| RELEASED'],
  ['tofa_font_micro', 'Inter Tight Regular', 16, 400, '92%  &middot;  50 MIN LEFT'],
  ['tofa_font_link', 'Roboto Mono Bold', 32, 700, 'tofa.tv/link'],
  ['tofa_font_code', 'Roboto Mono Bold', 66, 700, 'X7K9'],
  ['tofa_font_top_result_title', 'Inter Tight Bold', 52, 700, 'Up'],
  ['tofa_font_top_result_eyebrow', 'Inter Tight Bold', 14, 700, 'TOP RESULT'],
  ['tofa_font_results_caption', 'Inter Tight Regular', 23, 400, 'Results for &quot;up&quot;'],
  ['tofa_font_player_title', 'Inter Tight Bold', 45, 700, 'Hokum'],
  ['tofa_font_player_subtitle', 'Inter Tight Regular', 30, 400, 'S1 E2 &middot; The Rite'],
  ['tofa_font_player_clock', 'Inter Tight Regular', 51, 400, '22:41'],
  ['tofa_font_player_timeleft', 'Inter Tight Bold', 33, 700, '2 h 4 min left'],
  ['tofa_font_stats_title', 'Inter Tight Bold', 14, 700, 'Playback Stats'],
  ['tofa_font_stats_eyebrow', 'Inter Tight Bold', 11, 700, 'VIDEO'],
  ['tofa_font_stats_key', 'Inter Tight Regular', 15, 400, 'Resolution'],
  ['tofa_font_stats_value', 'Roboto Mono Regular', 16, 400, '3840&times;2160'],
  // The icon roles. One per pixel footprint the UI actually draws at -- and
  // unlike Inter Tight above, these sizes are LITERAL target pixels, because
  // an icon font fills its em-square. The glyphs shown are real codepoints
  // read out of the skin at that size, and the footprint note is what the
  // skin really draws there today, which is not what fontinstall.py's own
  // comments still claim for three of them (see Findings).
  ['tofa_font_icons_80', 'Lucide Icons', 80, 400, '&#xE087;', 'ONE caller: sign-in\u2019s state=expired mark. A CLOCK, not an alert \u2014 the code timed out, nothing went wrong'],
  ['tofa_font_icons_64', 'Lucide Icons', 64, 400, '&#xE151;', 'ONE caller: Search\u2019s idle / first-run empty state (no history yet)'],
  ['tofa_font_icons_56', 'Lucide Icons', 56, 400, '&#xE0D0; &#xE468; &#xE149; &#xE148;', 'BOTH card placeholders (poster\u2019s film, person\u2019s user-round), Search\u2019s other empty states, player skip \u00b1'],
  ['tofa_font_icons_36', 'Lucide Icons', 36, 400, '&#xE13C; &#xE12E; &#xE0D0; &#xE0AE;', 'nav-bar tabs (runtime glyph), episode + collection card marks, player transport'],
  ['tofa_font_icons_29', 'Lucide Icons', 29, 400, '&#xE0AE;', 'Search spacerow\u2019s backspace \u2014 24 &times; 1.2, rounded; runtime-set glyph'],
  ['tofa_font_icons_26', 'Lucide Icons', 26, 400, '&#xE3A4; &#xE1AB; &#xE20D; &#xE106;', 'the player OSD \u2014 all 25 callers, and nothing else. NOT sidebar rows: those draw at 24'],
  ['tofa_font_icons_24', 'Lucide Icons', 24, 400, '&#xE06F; &#xE06C; &#xE060; &#xE13C;', 'sidebar + picker + card-options row icons, pill icons; runtime-set glyph'],
  ['tofa_font_icons_19', 'Lucide Icons', 19, 400, '&#xE10B; &#xE211; &#xE06C; &#xE073;', 'chevrons and inline marks, the most-used icon role'],
].forEach(([role, family, size, weight, sample, note]) => {{
  const el = document.createElement('div');
  el.className = 'type-row';
  const icon = family.startsWith('Lucide');
  const mono = family.startsWith('Roboto');
  const face = icon ? 'tofa-lucide' : mono ? 'Roboto Mono' : 'Inter Tight';
  // Text roles are shown at 0.62x so a 77pt hero fits the column; icon roles
  // are shown at their literal size, because that IS their pixel footprint.
  const px = icon ? size : Math.round(size * 0.62);
  el.innerHTML = `<div class="type-meta"><b>${{role}}</b>${{family}} &middot; ${{size}}${{icon ? 'px' : 'pt'}}${{note ? `<span class="type-note">${{note}}</span>` : ''}}</div><div class="type-sample" style="font-family:'${{face}}';font-weight:${{weight}};font-size:${{px}}px;line-height:1.1">${{sample}}</div>`;
  typeScale.appendChild(el);
}});

// =========================================================================
// RADIUS RULER
// =========================================================================
const radiusRuler = document.getElementById('radiusRuler');
[
  [4,'badge-outline (rating badge) / format badge'], [13,'tag-pill (Kids) / device-code tile / QR card'],
  [16,'poster / sidebar row'], [22,'tab bar pill'],
  [24,'panel-fill (dialogs)'], [29,'pill-fill (Sort/Filter/Done)'], [32,'action / primary pill / nav bar'],
  ['50%','circle (avatar / PIN key)'],
].forEach(([r, cap]) => {{
  const el = document.createElement('div');
  el.className = 'r-item';
  const radius = typeof r === 'string' ? r : r + 'px';
  el.innerHTML = `<div class="r-box" style="border-radius:${{radius}}"></div><div class="r-cap">${{typeof r === 'string' ? r : r + 'px'}}<br>${{cap}}</div>`;
  radiusRuler.appendChild(el);
}});

// =========================================================================
// FINDINGS
// =========================================================================
const findingsHost = document.getElementById('findingsHost');
[
  {{
    h: 'One glass-fill ladder, typed by hand ~8 times',
    p: 'RESOLVED (2026-07-31). Resting glass &rarr; raised glass &rarr; active-tinted glass (accent_pill_fill, 0x3D+accent) &rarr; solid accent is the real state machine behind the sidebar row, Sort/Filter/Quality/Genre pills, the action pills, the tab switcher and the search tiles, and every screen used to re-type the literal hex rather than call a shared helper. The two static steps are now <code class="mono">SURFACE_REST</code>/<code class="mono">SURFACE_RAISED</code> in skin/tokens.py: all 25 raw colour literals in fragments.py and every one in main.xml.tpl / detail.xml.tpl now reference a token, and the two steps that sat one alpha apart (0x1E/0x1F) merged. Verified by diffing the regenerated XML against the previous output &mdash; byte-identical apart from that deliberate 0x1E&rarr;0x1F merge. Not yet covered: script-tofa-picker/signin/profile/player.xml are hand-authored and never pass through the fragments pipeline, so their literals (including the last surviving 0x1EFFFFFF, the picker panel outline) stay raw until those screens are migrated.',
  }},
  {{
    h: 'RESOLVED (2026-07-30) &mdash; pills and rows consolidated where the pipeline actually reaches',
    p: 'fragments.py gained glass_pill() (Detail\'s Rewatch/Options/Watchlist), browse_pill() (Browse\'s Sort/Filter/Quality/Genre, one function covering both the always-active and active&times;focused-matrix shapes), and sidebar_row() (Browse\'s 2 sidebar lists). Each was verified byte-for-byte against the XML it replaced before going live -- diffed the generated output against git HEAD line-by-line, not just eyeballed. One assumption from the original finding turned out wrong on closer inspection: Detail\'s season sidebar looked like a 3rd sidebar_row() caller, but its itemlayout has real structural asymmetries (single always-on fill, no active/inactive count-color split) that the other two don\'t share -- rather than force it through the shared fragment and silently change its behavior, it stays hand-typed, with a comment explaining why. Done/Retry/Cancel/tab-switcher remain out of scope -- they live in script-tofa-picker/signin/profile.xml, none of which go through the fragments.py pipeline at all (confirmed via build.py\'s SCREENS dict), so consolidating those would mean migrating a whole screen onto the pipeline first, not just extracting a function.',
  }},
  {{
    h: 'RESOLVED (2026-07-30) &mdash; radius count reduced to the assets that are genuinely different, not just renumbered',
    p: 'The original finding counted 9 distinct border values (4, 6, 13, 14, 16, 22, 24, 29, 32-34) as 9 distinct radii. Measuring white-square-rounded.png\'s own alpha channel directly overturned that: this one shared asset only has a true baked radius of ~4px, and 7 of those border values (4, 6, 14, 16, 24, 26, 30) were already being cropped against it &mdash; meaning they render the identical ~4px curve regardless of the number, which only changes how much corner area is treated as unstretched vs. stretchable middle (invisible on a solid fill). Format badge\'s border="6" was changed to border="4" to match the rating badge it already looked identical to, removing a difference that never visually existed. tag-pill (Kids, radius 13) and rounded-14 (device-code tile, radius 14) were genuinely different dedicated assets, unlike the case above &mdash; converged onto 13 (tag-pill.png/tag-pill-outline.png now serve both, plus the QR card background), chosen over 14 because the 70&times;26 Kids tag is already at the geometric limit for a true capsule (2&times;13=26=full height) and nudging to 14 would make its corner crops overlap. Bonus find: nav-panel.png/nav-pill.png (the nav bar\'s full/small pill fills) both measured as true circles, same signature as capsule-pill.png, just older duplicate assets predating it &mdash; retired in favor of the existing capsule-pill.png/capsule-pill-outline.png at their same border values. The "bigger" radii asked about directly (pill-fill 29, capsule-pill 32-34, tab-pill 22, panel-fill 24) were checked and are genuinely distinct dedicated assets sized for controls of real differing heights &mdash; no further consolidation recommended there. badge-outline.png\'s own internal 8px radius (vs. the fill\'s now-4px crop) is a small pre-existing mismatch, left alone as out of scope.',
  }},
  {{
    h: 'RESOLVED (2026-07-30) &mdash; on-accent text now picked by real contrast, not a fixed literal',
    p: 'theme.py gained on_accent_text(): computes real WCAG relative luminance for the current accent and returns whichever of the dark literal (0xFF04211E) or white gives higher contrast. Computing it for all 14 presets (not just eyeballing the two extremes) found the actual split is Crimson / Forest / Ocean / Plum &rarr; white, all other 10 presets (including both lightness extremes, Amber and Snow) &rarr; the original dark literal -- Ocean and Plum weren\'t even on this page\'s own radar until the real numbers were run. Wired as a new on_accent_color Window.Property (set alongside accent_color/accent_pill_fill in every window that already sets those) and swapped into every genuinely-on-accent-fill spot: the Primary CTA pill, Done button, watchlist-added badge, and episode watched badge. The handful of textcolor:0x04211E spots that sit on a plain WHITE fill instead (the abc/123 tab switcher, search keyboard tiles) were deliberately left alone -- those were never the bug, swapping them would have been wrong.',
  }},
  {{
    h: 'Player chrome never joined the fragments.py pipeline',
    p: 'Every other screen migrated onto generated XML at least in part (Detail\'s cards, Home/Browse/Discover/Search\'s nav bar and posters); script-tofa-player.xml is still 100% hand-authored, sharing none of the glass-fill ladder or radius tokens documented above by construction rather than by choice. Not urgent (the OSD is visually simple and has had no reported drift bugs), but worth knowing it\'s the one surface where a future color/radius token change won\'t propagate automatically.',
  }},
  {{
    h: 'RESOLVED &mdash; the spec\'s Collections tile (7.5) is built, and is the one landscape card',
    p: 'TV-DESIGN.md &sect;7.5 specifies a 448pt-wide, radius-14, 3-column Collections grid as a distinct card family from the poster grid. When this finding was first written nothing rendered it. <code class="mono">fragments.py:collection_card()</code> now does, at the spec\'s verbatim numbers (tile 448&times;252, radius 14, gaps 30/44, caption a fixed 86 so rows stay aligned whatever a name wraps to) &mdash; independently confirmed against the Android TV app, which lays its own out at exactly those values. It is the only 16:9 tile in an app of 2:3 portraits, and it carries 7.5\'s artwork ladder: backdrop cropped to fill, else poster FITTED over a dimmed copy of itself (Kodi has no blur, so the spec\'s blurred backing plate becomes a cropped dimmed one), else the film-stack glyph on a plate.',
  }},
  {{
    h: 'RESOLVED (2026-08-06) &mdash; the card family audited as a matrix rather than one screenshot at a time',
    p: 'Six card fragments (poster, top-result, person, episode, discover, collection) had accumulated the same shape of defect repeatedly: one card missing something its siblings already did correctly, each found by symptom from a screenshot rather than by comparing the fragments. Building the matrix deliberately &mdash; every fragment &times; every shared concern &mdash; found eleven more. The visible ones: Search\'s Top Result drew its placeholder TWICE (its own 64pt film glyph, written before poster_visual() grew one, plus poster_visual()\'s at 56pt, 15px apart and only one of them zooming on focus); Search\'s Actors row drew a 190px person ring into a 130px tile, rendering its 2px stroke at 1.4 and squeezing the halo\'s fade band into 7 of the 10px reserved for it (now one asset per size, named for it, like capsule-h&lt;N&gt;.png); the Collections tile zoomed its own CAPTION about the tile\'s centre 130px above it, so focusing a collection pushed its name out of line with every neighbour\'s; and the Collections tile was the last card in the family with no focus halo at all. The rest were latent &mdash; glow pads and caption widths written as literals beside the tokens they were supposed to derive from, one constant used as both an x and a y, and a cell size typed independently in both the fragment and the template. Two type/colour questions the matrix raised were settled against the spec and by pixel-measuring the reference captures, not by eye: the person tile\'s role line was set in the font every OTHER card uses for its TITLE (now metadata, per &sect;7\'s "name (row-title) over character/role (metadata, white 62%)"), and the poster card was alone in resting its metadata line at tertiary and lifting it on focus &mdash; measured flat at 62-63% in both states on every reference capture, which is what its three siblings already did.',
  }},
  {{
    h: 'RESOLVED (2026-07-30), then REOPENED BY MEASUREMENT (2026-08-13) &mdash; the app has FOUR text tiers, not 3',
    p: 'The Text Tiers section above documented ~18 distinct white-alpha values for text, drifted from spec\'s own 4-tier scale. Pixel-sampled real Apple TV reference captures (not just copied the spec\'s numbers) to confirm two clean, real clusters at ~97% and ~62%, plus a real third cluster at ~42-49% (small-caps eyebrows, inactive keyboard keys) that a first pass had folded into secondary before deciding a 3rd shade was warranted. theme.py gained TEXT_PRIMARY/TEXT_SECONDARY/TEXT_TERTIARY constants; every window class now sets matching text_primary/text_secondary/text_tertiary Window.Properties in onFirstInit (including script-tofa-player.xml and script-tofa-signin.xml, which had no color-property infrastructure at all before this); every one of the ~219 textcolor attributes across the whole app -- generated pipeline and all 4 hand-authored screens -- now references one of those three properties instead of a raw hex literal. The 2 "no art available" placeholder-icon glyphs (previously one-off literals at 25%/38%) now fold into tertiary (42%) rather than staying unexplained exceptions.<br><br><b>The 3-tier answer did not survive contact with &sect;8.8.</b> This round measured the 80-82% band as EMPTY -- in the reference captures and in the codebase both -- and that was an honest reading of the evidence available. The pause card is the counter-example: its "N min left" line peaks at 211 against its own clock&rsquo;s 251 on the live Apple TV, i.e. ~83%. theme.py gained TEXT_STRONG (0xD4) and player.py sets a fourth Window.Property, text_strong. It has exactly ONE caller and the constant carries a comment saying to keep it that way until another label is MEASURED into it. The lesson worth keeping is not "we were wrong about three" -- it is that a gap found empty is a statement about the evidence you had, not a law, and the tier system is only worth anything while every member of it is a measurement. <b>This page itself is the cautionary tale:</b> the fourth tier shipped on 2026-08-13 and this section still said "three" until 2026-08-19, because the generator&rsquo;s guard checked colours, sizes and presets but never looked at theme.py&rsquo;s tiers. It does now.',
  }},
  {{
    h: 'OPEN (found 2026-08-19) &mdash; three literal white-alpha textcolors have come back',
    p: 'The 2026-07-30 sweep ended at zero literal <code class="mono">&lt;textcolor&gt;</code> hexes anywhere in the app, and this page said so until today. Three have reappeared since, all in code written after the sweep, which is exactly the failure mode the tier system exists to prevent -- and none of them tripped anything, because the generator\'s guard only ever looked at colours the PAGE states, never at the app\'s own textcolor attributes. <b>fragments.py (the toast label)</b> and <b>script-tofa-player.xml (the player\'s hand-copied duplicate of the same toast)</b> both hard-code <code class="mono">0xFFFFFFFF</code> where <code class="mono">text_primary</code> would say the same thing and stay attached to the tier; the fragments.py one is the more notable of the two because it is INSIDE the generated pipeline, i.e. the one place a literal was supposed to be impossible. <b>script-tofa-signin.xml:338</b> hard-codes <code class="mono">0x99FFFFFF</code> on an icon glyph -- 60%, which is not a tier at all: it is a near-miss for secondary\'s 62%, and a 2% difference nobody can see is precisely how the original ~18 values accumulated. Recommended: the two toasts take text_primary, and the sign-in glyph is either measured (and justified) or moved to secondary. Not fixed here -- this page and its generator are the change; the add-on\'s own source is a separate call.',
  }},
  {{
    h: 'OPEN (found 2026-08-19) &mdash; three icon-role comments in fontinstall.py describe footprints that moved',
    p: 'The icon roles are named for the pixel footprint they serve, and fontinstall.py annotates each with where that footprint is. Three of those annotations are now wrong, and because a role name carries a number rather than a place, nothing catches it. <code class="mono">tofa_font_icons_26</code> is commented \'sidebar rows 26\'; its 25 callers are ALL in the player OSD and the sidebar rows draw at <code class="mono">icons_24</code>. <code class="mono">tofa_font_icons_80</code> and <code class="mono">tofa_font_icons_64</code> sit under a comment reading \'Search\'s Top Result poster placeholder / Actors shelf circular placeholder\'; that is true of 56 alone (fragments.py draws both card placeholders there), while 80\'s single caller is sign-in\'s expired-code clock and 64\'s single caller is Search\'s first-run empty state. Harmless to rendering and cheap to fix, but worth logging rather than quietly correcting: the type scale above now states each icon role\'s REAL callers, read out of the skin, so the page and the comment disagree until the comment is updated. Verified by counting every <code class="mono">&lt;font&gt;</code> reference per role across static XML, templates and fragments.py -- not by reading the comments.',
  }},
].forEach((f, i) => {{
  const el = document.createElement('div');
  el.className = 'finding';
  el.innerHTML = `<div class="n">${{String(i+1).padStart(2,'0')}}</div><div><h4>${{f.h}}</h4><p>${{f.p}}</p></div>`;
  findingsHost.appendChild(el);
}});

document.getElementById('iconRefLink').addEventListener('click', e => {{ e.preventDefault(); alert('See the separately-published icon reference artifact (tools/icon_reference.html) for the full Lucide catalog.'); }});
</script>
"""

if __name__ == "__main__":
    main()
