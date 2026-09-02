"""Generates tools/icon_reference.html -- a self-contained visual reference
of every Lucide glyph wired into the add-on's UI (icon_glyphs.py), plus a
searchable browser of the full 2,027-icon catalog to find a better-matching
replacement. The bundled lucide-icons.ttf and a few local system/repo fonts
are embedded as base64 data URIs so it renders identically anywhere,
offline, with no network requests.

**Regenerate this whenever icon_glyphs.py changes** (a new icon wired up,
an existing one swapped for a better-matching glyph) -- run:

    python3 tools/gen_icon_reference.py

WIRED_GROUPS below is hand-curated (which UI area each icon renders in)
and deliberately not derived automatically from icon_glyphs.py, since
"used in the Browse sidebar's Watchlist row" isn't machine-readable
anywhere else. `_validate()` asserts WIRED_GROUPS and icon_glyphs.py's own
constants stay in exact 1:1 agreement, hard-failing rather than emitting a
stale page the moment a constant is added/removed/reassigned without
updating WIRED_GROUPS. When it fails, fix WIRED_GROUPS, not the
validation.

Dev-only tool, not shipped with the add-on and never imported by it. Needs
the three local fonts in tools/icon_reference_fonts/ (committed, see that
directory's own LICENSE.txt) plus resource.font.tofa/resources/
tofa_lucide-icons.ttf (the add-on's own real font) and tools/lucide_font_src/
codepoints.json (the full Lucide name<->codepoint catalog, dev reference
only per that directory's own README).
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os

_TOOLS_DIR = os.path.dirname(__file__)
_ADDON_DIR = os.path.join(_TOOLS_DIR, "..", "plugin.video.tofa")
_OUTPUT_PATH = os.path.join(_TOOLS_DIR, "icon_reference.html")

_LUCIDE_TTF = os.path.join(_ADDON_DIR, "..", "resource.font.tofa", "resources",
                           "tofa_lucide-icons.ttf")
_CODEPOINTS_JSON = os.path.join(_TOOLS_DIR, "lucide_font_src", "codepoints.json")
_ICON_GLYPHS_PY = os.path.join(_ADDON_DIR, "resources", "lib", "skin", "icon_glyphs.py")

_FONTS_DIR = os.path.join(_TOOLS_DIR, "icon_reference_fonts")
_SCP_BLACK = os.path.join(_FONTS_DIR, "SourceCodePro-Black.otf")
_SCP_REGULAR = os.path.join(_FONTS_DIR, "SourceCodePro-Regular.otf")
_OPEN_SANS = os.path.join(_FONTS_DIR, "OpenSans-Regular.ttf")

# name -> (source file, "used in..." description). Groups render in this
# order, top to bottom. See the module docstring for why this is
# hand-maintained and what enforces it staying accurate.
WIRED_GROUPS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Top nav bar", "resources/lib/windows/navbar.py", [
        ("HOUSE", "Home tab"),
        ("LAYOUT_GRID", "Browse tab"),
        ("SPARKLES", "Discover tab"),
        ("SEARCH", "Search tab"),
        ("SETTINGS", "Settings tab"),
    ]),
    ("Card corner chips", "resources/lib/skin/fragments.py – watchlist/cinema chips", [
        ("PLUS", "“Not in library” badge on a Discover card (§11's own pairing —\n"
                 "            NOT a watchlist glyph, which is BOOKMARK)"),
    ]),
    ("Exit confirmation", "resources/lib/windows/cardoptions.py – EXIT/MINIMIZE rows", [
        ("LOG_OUT", "“Exit tofa” row"),
        ("MINIMIZE", "“Minimize” row (add-on keeps running behind Kodi's home)"),
    ]),
    ("Detail screen", "resources/lib/skin/templates/detail.xml.tpl", [
        ("INFO", "“Plays as X” audio caveat line"),
        ("BOOKMARK_OFF", "Watchlist pill, title already saved (paired with BOOKMARK)"),
        ("USERS", "Cast &amp; Crew tab, empty state (matches the Apple TV app)"),
        ("GALLERY_VERTICAL_END", "More Like This tab, empty state (matches the Apple TV app)"),
        ("SLIDERS_HORIZONTAL", "Options pill, and the player's own Quality / stream panels.\n"
                               "            Browse's Filter used to share this mark and no longer\n"
                               "            does — see LIST_FILTER"),
    ]),
    ("Empty / error scaffold", "resources/lib/skin/fragments.py – empty_state()", [
        ("TRIANGLE_ALERT", "9.7's error flavour, tinted status-red"),
    ]),
    ("Browse sidebar", "resources/lib/windows/main.py – _browse_build_sidebar()", [
        ("BOOKMARK", "Watchlist row"),
        ("ROTATE_CCW_CLOCK", "History row"),
        ("LAYERS", "Collections row"),
        ("SHUFFLE", "Surprise Me row \u2014 and the Browse Sort pill whenever Shuffle\n            is the sort, which is the one sort with no direction to point.\n            Same mark for the same idea, not a collision"),
        ("CLAPPERBOARD", "Movie library row; also the in-cinemas card chip"),
        ("TV", "TV show library row"),
        ("VIDEO", "Library row, media_type=“other”"),
    ]),
    ("Sort / Filter / Genre buttons", "resources/lib/skin/templates/main.xml.tpl", [
        ("LIST_FILTER", "Filter button icon — three plain decreasing lines.\n"
                        "            NOT sliders-horizontal, which Detail's Options pill uses;\n"
                        "            this is also the mark the real app draws on Filter"),
        ("TAG", "Genre button icon"),
        ("CHEVRONS_UP_DOWN", "Dropdown chevron: all 4 buttons, Detail's Options and Edition pills, collapsed options sections"),
    ]),
    ("Sign-in dialog", "resources/skins/Main/1080i/script-tofa-signin.xml", [
        ("CLOCK", "Countdown line (19px) and the expired state's amber mark (80px)"),
        ("REFRESH_CW", "\"Generate new code\" pill"),
    ]),
    ("Detail page 2", "resources/lib/skin/templates/detail.xml.tpl", [
        ("CHEVRON_DOWN", "Scroll-down-for-page-2 hint, its one remaining use: here it means a DIRECTION, not a dropdown"),
    ]),
    ("Player transport &amp; drawer", "resources/skins/Main/1080i/script-tofa-player.xml", [
        ("SKIP_BACK", "Transport capsule, previous EPISODE (a movie shows -10s instead)"),
        ("SKIP_FORWARD", "Transport capsule, next EPISODE (a movie shows +10s instead)"),
        ("LIST", "Utility capsule, opens 8.10's episode drawer (TV only)"),
        ("CIRCLE_PLAY", "8.10 drawer, “this one is playing” badge on an episode row's still"),
    ]),
    ("PickerDialog rows", "resources/lib/windows/picker.py", [
        ("CHECK", "Selected row checkmark; also the just-added watchlist card chip"),
        ("ARROW_UP", "Sort: ascending \u2014 on the picker's active row AND on the\n            Browse Sort pill itself"),
        ("ARROW_DOWN", "Sort: descending \u2014 on the picker's active row AND on the\n            Browse Sort pill itself"),
    ]),
    ("Profile picker & PIN entry", "resources/skins/Main/1080i/script-tofa-profile.xml", [
        ("LOCK", "Locked-profile badge"),
        ("DELETE", "PIN keypad backspace key"),
    ]),
    ("Search section", "resources/lib/skin/templates/main.xml.tpl / windows/main.py", [
        ("FILM", "Top Result poster placeholder (no poster art)"),
        ("USER_ROUND", "Actors shelf placeholder (no photo)"),
        ("GLOBE", "Keyboard language-switcher icon (decorative -- no multi-language support)"),
    ]),
    ("Detail screen", "resources/lib/skin/templates/detail.xml.tpl", [
        ("PLAY", "Primary Play/Resume pill icon"),
    ]),
    ("Card options panel (7.2)", "resources/lib/windows/cardoptions.py", [
        ("CHEVRON_RIGHT", "“Go to Details” row (SF chevron.right)"),
        ("MINUS_CIRCLE", "“Mark as Unwatched” row (SF minus.circle)"),
        ("CIRCLE_X", "“Remove from Continue Watching” and “Cancel” rows (SF xmark.circle)"),
    ]),
    ("Player transport (8.1)", "resources/skins/Main/1080i/script-tofa-player.xml", [
        ("PAUSE", "Prominent play/pause button, playing state (SF pause.fill)"),
        ("ROTATE_CCW", "-10s button and the back quick-seek toast; the “10” is a\n"
                       "            separate label centred in the arc (SF gobackward.10)"),
        ("ROTATE_CW", "+10s button and the forward quick-seek toast (SF goforward.10)"),
        ("CAPTIONS", "Subtitles button, utility capsule slot 1 (SF captions.bubble)"),
        ("VOLUME_2", "Audio button, utility capsule slot 2 (SF speaker.wave.2.fill)"),
        ("GLASSES", "3D button, straight after Audio — stereoscopic files only —\n"
                    "            and the header of the panel it opens, which is the same\n"
                    "            panel a 3D film raises when it starts"),
        ("ACTIVITY", "Stats overlay toggle, utility capsule slot 4 (SF waveform.path.ecg)"),
        ("WRENCH", "Adjust panel: audio sync and subtitle sync. 3D was a third row\n"
                   "            here until it became its own button — see GLASSES"),
        ("CHEVRONS_RIGHT", "8.5's skip-segment pill; deliberately NOT skip-forward, which\n"
                           "            already means “next episode” on the transport"),
    ]),
    # Only the two icons this screen introduced. Its other four sidebar
    # marks -- USER_ROUND, PLAY, CAPTIONS, TV -- plus USERS, LOG_OUT and
    # CHEVRON_RIGHT were already wired elsewhere and are reused verbatim, and
    # _validate() requires each constant to appear in exactly one group.
    ("Settings sidebar (9)", "resources/lib/settings_pages.py", [
        ("PALETTE", "Appearance page"),
        ("HAND", "Privacy &amp; About page"),
    ]),
    ("Settings account rows", "resources/lib/windows/main.py – Account page", [
        ("SERVER", "“Switch Server” row; Lucide's rack unit, not hard-drive (a disk)\n"
                   "            and not globe (the cloud account, which is the row above)"),
    ]),
    ("Fox picker (9.4)", "resources/lib/skin/fragments.py \u2013 settings_fox_tile()", [
        ("STAR", "\u201cThe original\u201d badge on the default Tofa Fox tile; a star\n"
                 "            rather than a check, which would read as \u201cselected\u201d"),
    ]),
    ("Browse collection drill-down", "resources/lib/skin/screens.py – collection_back pill", [
        ("CHEVRON_LEFT", "“All Collections” pill, back out of an open collection"),
    ]),
]


def _load_icon_glyphs() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location("icon_glyphs", _ICON_GLYPHS_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {k: v for k, v in vars(module).items() if k.isupper() and isinstance(v, int)}


def _validate(icon_glyphs: dict[str, int]) -> None:
    grouped_names = {name for _, _, items in WIRED_GROUPS for name, _ in items}
    actual_names = set(icon_glyphs)

    missing = actual_names - grouped_names
    if missing:
        raise SystemExit(
            "icon_glyphs.py has constants WIRED_GROUPS doesn't know about "
            f"(add them to a group in tools/gen_icon_reference.py): {sorted(missing)}"
        )
    stale = grouped_names - actual_names
    if stale:
        raise SystemExit(
            "WIRED_GROUPS references constants that no longer exist in "
            f"icon_glyphs.py (remove them from tools/gen_icon_reference.py): {sorted(stale)}"
        )

    seen: dict[str, str] = {}
    for area, _src, items in WIRED_GROUPS:
        for name, _used in items:
            if name in seen:
                raise SystemExit(f"{name!r} is listed twice in WIRED_GROUPS ({seen[name]!r} and {area!r})")
            seen[name] = area


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def build() -> str:
    icon_glyphs = _load_icon_glyphs()
    _validate(icon_glyphs)

    lucide_catalog = json.load(open(_CODEPOINTS_JSON))  # name -> decimal codepoint
    catalog = [{"n": name, "c": cp} for name, cp in sorted(lucide_catalog.items())]
    lucide_by_cp = {cp: name for name, cp in lucide_catalog.items()}

    wired_flat = []
    for area, src, items in WIRED_GROUPS:
        for const, used in items:
            cp = icon_glyphs[const]
            wired_flat.append({
                "area": area, "src": src, "const": const, "cp": cp,
                "used": used, "lucide": lucide_by_cp.get(cp, "?"),
            })

    fonts = {
        "lucide": _b64(_LUCIDE_TTF),
        "scp_black": _b64(_SCP_BLACK),
        "scp_regular": _b64(_SCP_REGULAR),
        "opensans_regular": _b64(_OPEN_SANS),
    }

    wired_json = json.dumps(wired_flat)
    catalog_json = json.dumps(catalog, separators=(",", ":"))

    parts: list[str] = []
    parts.append(
        "<!-- GENERATED by tools/gen_icon_reference.py. DO NOT HAND-EDIT.\n"
        "     Run `python3 tools/gen_icon_reference.py` to refresh after\n"
        "     changing resources/lib/skin/icon_glyphs.py. -->\n"
    )
    # Must come before the first non-ASCII byte, and inside the first 1024.
    # Without it a browser guesses, and guesses latin-1 for this file: the
    # em dash in the title below renders as "â€"", as do the curly quotes
    # and dashes throughout the dek and the section headings.
    parts.append("<meta charset=\"utf-8\" />\n")
    parts.append("<title>tofa for Kodi — Icon Glyph Reference</title>\n")
    parts.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n")
    parts.append("<style>\n")
    parts.append(f"""
@font-face {{
  font-family: "Lucide";
  src: url(data:font/ttf;base64,{fonts['lucide']}) format("truetype");
  font-display: swap;
}}
@font-face {{
  font-family: "SCP Black";
  src: url(data:font/otf;base64,{fonts['scp_black']}) format("opentype");
  font-weight: 900;
  font-display: swap;
}}
@font-face {{
  font-family: "SCP";
  src: url(data:font/otf;base64,{fonts['scp_regular']}) format("opentype");
  font-weight: 400;
  font-display: swap;
}}
@font-face {{
  font-family: "Open Sans";
  src: url(data:font/ttf;base64,{fonts['opensans_regular']}) format("truetype");
  font-weight: 400;
  font-display: swap;
}}
""")
    parts.append("""
:root {
  --bg: #0a0e10;
  --bg-panel: #12181b;
  --bg-inset: #171e22;
  --bg-tile: #141a1d;
  --border: #232c30;
  --border-soft: #1a2124;
  --text: #dce6e8;
  --text-dim: #8ca0a6;
  --text-faint: #56676c;
  --accent: #2dd4bf;
  --accent-soft: rgba(45, 212, 191, 0.13);
  --accent-strong: #7ef0e0;
  color-scheme: dark;
}
:root[data-theme="light"] {
  --bg: #f4f7f7;
  --bg-panel: #ffffff;
  --bg-inset: #eef2f2;
  --bg-tile: #ffffff;
  --border: #d6dee0;
  --border-soft: #e3e9ea;
  --text: #10191b;
  --text-dim: #4d6167;
  --text-faint: #8ea0a5;
  --accent: #0f9c8b;
  --accent-soft: rgba(15, 156, 139, 0.1);
  --accent-strong: #0b7568;
  color-scheme: light;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f4f7f7;
    --bg-panel: #ffffff;
    --bg-inset: #eef2f2;
    --bg-tile: #ffffff;
    --border: #d6dee0;
    --border-soft: #e3e9ea;
    --text: #10191b;
    --text-dim: #4d6167;
    --text-faint: #8ea0a5;
    --accent: #0f9c8b;
    --accent-soft: rgba(15, 156, 139, 0.1);
    --accent-strong: #0b7568;
    color-scheme: light;
  }
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: "Open Sans", system-ui, sans-serif;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
::selection { background: var(--accent-soft); color: var(--accent-strong); }

a { color: var(--accent-strong); }

.mono { font-family: "SCP", ui-monospace, monospace; }

.wrap {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 28px 96px;
}

header.masthead {
  border-bottom: 1px solid var(--border);
  background:
    linear-gradient(180deg, var(--accent-soft), transparent 140px),
    var(--bg);
}
.masthead-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 40px 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
}
.prompt {
  font-family: "SCP", monospace;
  font-size: 13px;
  letter-spacing: 0.02em;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 8px;
}
.prompt .cursor {
  display: inline-block;
  width: 8px;
  height: 15px;
  background: var(--accent);
  animation: blink 1.1s steps(1) infinite;
}
@media (prefers-reduced-motion: reduce) { .prompt .cursor { animation: none; } }
@keyframes blink { 50% { opacity: 0; } }

h1.title {
  font-family: "SCP Black", "SCP", monospace;
  font-weight: 900;
  font-size: clamp(28px, 4vw, 40px);
  letter-spacing: -0.01em;
  margin: 0;
  text-wrap: balance;
}
h1.title .dim { color: var(--text-dim); font-weight: 900; }

p.dek {
  max-width: 62ch;
  color: var(--text-dim);
  font-size: 15.5px;
  margin: 0;
}
p.dek code { color: var(--text); }

.masthead-stats {
  display: flex;
  gap: 28px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat .n {
  font-family: "SCP Black", monospace;
  font-size: 22px;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.stat .l {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.theme-toggle {
  position: absolute;
  top: 24px;
  right: 28px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-family: "SCP", monospace;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 5px;
  cursor: pointer;
}
.theme-toggle:hover { color: var(--text); border-color: var(--text-dim); }

section { margin-top: 56px; }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
  margin-bottom: 22px;
  flex-wrap: wrap;
}
h2.section-title {
  font-family: "SCP Black", monospace;
  font-weight: 900;
  font-size: 13px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
h2.section-title .idx { color: var(--accent); }
.section-note { color: var(--text-faint); font-size: 13px; }

.group { margin-bottom: 34px; }
.group-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.group-head h3 { font-size: 15px; margin: 0; color: var(--text); font-weight: 700; }
.group-head .src { font-family: "SCP", monospace; font-size: 11.5px; color: var(--text-faint); }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}
.card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: border-color 0.15s ease;
}
.card:hover { border-color: var(--accent); }
.card-top { display: flex; align-items: center; gap: 12px; }
.glyph {
  font-family: "Lucide";
  font-size: 30px;
  line-height: 1;
  width: 44px;
  height: 44px;
  min-width: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--bg-inset);
  color: var(--accent);
}
.card-id { min-width: 0; }
.card-const {
  font-family: "SCP", monospace;
  font-weight: 700;
  font-size: 13.5px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-lucide { font-family: "SCP", monospace; font-size: 11.5px; color: var(--text-faint); }
.card-used {
  font-size: 12.5px;
  color: var(--text-dim);
  border-top: 1px solid var(--border-soft);
  padding-top: 9px;
}
.card-cp { font-family: "SCP", monospace; font-size: 11px; color: var(--text-faint); letter-spacing: 0.02em; }

.catalog-controls { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.search-box { flex: 1; min-width: 220px; position: relative; }
.search-box input {
  width: 100%;
  background: var(--bg-inset);
  border: 1px solid var(--border);
  color: var(--text);
  font-family: "SCP", monospace;
  font-size: 14px;
  padding: 11px 14px 11px 34px;
  border-radius: 8px;
  outline: none;
}
.search-box input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.search-box::before {
  content: "\\2315";
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-52%);
  color: var(--text-faint);
  font-size: 15px;
  pointer-events: none;
}
.catalog-count { font-family: "SCP", monospace; font-size: 12px; color: var(--text-faint); white-space: nowrap; }
.copy-toast { font-family: "SCP", monospace; font-size: 12px; color: var(--accent); min-height: 16px; }

.catalog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(108px, 1fr)); gap: 6px; }
.tile {
  background: var(--bg-tile);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 12px 6px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
}
.tile:hover, .tile:focus-visible { border-color: var(--accent); background: var(--accent-soft); outline: none; }
.tile:focus-visible { box-shadow: 0 0 0 2px var(--accent-soft); }
.tile .glyph { background: none; width: auto; height: auto; min-width: 0; font-size: 22px; }
.tile .tname {
  font-family: "SCP", monospace;
  font-size: 9.5px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}
.tile.is-wired { border-color: var(--accent); background: var(--accent-soft); }
.tile.is-wired .tname { color: var(--accent-strong); }

.catalog-empty { color: var(--text-faint); font-size: 13px; padding: 30px 0; text-align: center; display: none; }

footer {
  margin-top: 70px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 12.5px;
}
footer p { max-width: 72ch; margin: 6px 0; }
footer code { font-family: "SCP", monospace; background: var(--bg-inset); padding: 1px 5px; border-radius: 4px; color: var(--text-dim); }

@media (max-width: 640px) {
  .theme-toggle { position: static; margin-top: 4px; align-self: flex-start; }
  .masthead-stats { gap: 18px; }
}
""")
    parts.append("</style>\n")

    parts.append("<header class=\"masthead\">\n<div class=\"masthead-inner\">\n")
    parts.append("<button class=\"theme-toggle\" id=\"themeToggle\" type=\"button\" aria-label=\"Toggle color theme\">◐ theme</button>\n")
    parts.append("<div class=\"prompt\">tofa-for-kodi / resources/lib/skin/icon_glyphs.py<span class=\"cursor\"></span></div>\n")
    parts.append("<h1 class=\"title\">Icon Glyph Reference<span class=\"dim\">.</span></h1>\n")
    parts.append(
        "<p class=\"dek\">Every Lucide glyph currently wired into the add-on’s UI, rendered from "
        "the exact font file the app ships (<code>lucide-icons.ttf</code>) — plus the full "
        "2,027-icon catalog below it to browse for a better-matching replacement. "
        "Click any catalog tile to copy its codepoint.</p>\n"
    )
    parts.append(f"""<div class="masthead-stats">
  <div class="stat"><span class="n">{len(wired_flat)}</span><span class="l">wired up</span></div>
  <div class="stat"><span class="n">{len(catalog)}</span><span class="l">in lucide-icons.ttf</span></div>
  <div class="stat"><span class="n">{len(WIRED_GROUPS)}</span><span class="l">ui areas</span></div>
</div>
""")
    parts.append("</div>\n</header>\n")

    parts.append("<div class=\"wrap\">\n")

    parts.append("<section id=\"wired\">\n")
    parts.append(
        "<div class=\"section-head\"><h2 class=\"section-title\"><span class=\"idx\">01</span> Wired up</h2>"
        "<span class=\"section-note\">grouped by where each glyph renders on screen</span></div>\n"
    )
    for area, src, items in WIRED_GROUPS:
        parts.append("<div class=\"group\">\n")
        parts.append(f"<div class=\"group-head\"><h3>{area}</h3><span class=\"src\">{src}</span></div>\n")
        parts.append("<div class=\"card-grid\">\n")
        for const, used in items:
            cp = icon_glyphs[const]
            lname = lucide_by_cp.get(cp, "?")
            parts.append(f"""<div class="card">
  <div class="card-top">
    <div class="glyph">&#x{cp:04X};</div>
    <div class="card-id">
      <div class="card-const">{const}</div>
      <div class="card-lucide">{lname}</div>
    </div>
  </div>
  <div class="card-used">{used}</div>
  <div class="card-cp">0x{cp:04X}</div>
</div>
""")
        parts.append("</div>\n</div>\n")
    parts.append("</section>\n")

    parts.append("<section id=\"catalog\">\n")
    parts.append(
        "<div class=\"section-head\"><h2 class=\"section-title\"><span class=\"idx\">02</span> Full Lucide catalog</h2>"
        "<span class=\"section-note\">from lucide-icons.ttf — the bundled font already has every one of "
        "these, no new asset needed to swap</span></div>\n"
    )
    parts.append("""<div class="catalog-controls">
  <div class="search-box"><input id="catalogSearch" type="text" placeholder="Filter by name or codepoint (e.g. “play”, “e0f5”)…" autocomplete="off" spellcheck="false" /></div>
  <span class="catalog-count" id="catalogCount"></span>
</div>
<div class="copy-toast" id="copyToast">&nbsp;</div>
<div class="catalog-grid" id="catalogGrid"></div>
<div class="catalog-empty" id="catalogEmpty">No icon matches that search.</div>
""")
    parts.append("</section>\n")

    parts.append(f"""<footer>
  <p><strong>Wiring a replacement:</strong> copy the hex codepoint from a catalog tile, set it as the new value in <code>icon_glyphs.py</code>, then use it either as <code>&amp;#x{{CODEPOINT:04X}};</code> inside a static skin XML <code>&lt;label&gt;</code>, or <code>chr(icon_glyphs.NAME)</code> when setting a <code>ListItem</code>/<code>Window</code> property from Python. A <code>&lt;label&gt;</code> showing a glyph needs <code>&lt;width&gt;</code>/<code>&lt;height&gt;</code> ≥ the icon font’s own point size or Kodi renders a solid dot instead of the glyph. Then re-run <code>python3 tools/gen_icon_reference.py</code> so this page catches up.</p>
  <p>Source of truth for the full catalog: <code>tools/lucide_font_src/codepoints.json</code> (dev reference, not shipped with the add-on). Font license: ISC (Lucide) / MIT (icons derived from Feather) — see <code>resources/skins/Main/media/LUCIDE_LICENSE.txt</code>.</p>
</footer>
""")

    parts.append("</div>\n")

    parts.append("<script>\n")
    parts.append(f"const WIRED = {wired_json};\n")
    parts.append(f"const CATALOG = {catalog_json};\n")
    parts.append(r"""
const wiredByCp = new Set(WIRED.map(w => w.cp));

const grid = document.getElementById('catalogGrid');
const empty = document.getElementById('catalogEmpty');
const countEl = document.getElementById('catalogCount');
const toast = document.getElementById('copyToast');
let toastTimer = null;

function hex4(n) { return n.toString(16).toUpperCase().padStart(4, '0'); }

function render(list) {
  grid.innerHTML = '';
  const frag = document.createDocumentFragment();
  for (const item of list) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tile' + (wiredByCp.has(item.c) ? ' is-wired' : '');
    btn.title = item.n + '  —  0x' + hex4(item.c) + (wiredByCp.has(item.c) ? '  (already wired up)' : '');
    btn.innerHTML = '<span class="glyph">&#x' + hex4(item.c) + ';</span><span class="tname">' + item.n + '</span>';
    btn.addEventListener('click', () => copyTile(item));
    frag.appendChild(btn);
  }
  grid.appendChild(frag);
  countEl.textContent = list.length + ' / ' + CATALOG.length;
  empty.style.display = list.length ? 'none' : 'block';
}

function copyTile(item) {
  const text = '0x' + hex4(item.c) + '  (' + item.n + ')';
  const payload = '0x' + hex4(item.c);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(payload).catch(() => {});
  }
  clearTimeout(toastTimer);
  toast.textContent = 'Copied ' + text;
  toastTimer = setTimeout(() => { toast.textContent = ' '; }, 2200);
}

render(CATALOG);

const search = document.getElementById('catalogSearch');
search.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  if (!q) { render(CATALOG); return; }
  const asHex = q.replace(/^0x/, '');
  const filtered = CATALOG.filter(item => {
    if (item.n.toLowerCase().includes(q)) return true;
    const h = hex4(item.c).toLowerCase();
    if (h.includes(asHex)) return true;
    return false;
  });
  render(filtered);
});

const toggle = document.getElementById('themeToggle');
const root = document.documentElement;
toggle.addEventListener('click', () => {
  const current = root.getAttribute('data-theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  root.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
});
""")
    parts.append("</script>\n")

    return "".join(parts)


if __name__ == "__main__":
    html = build()
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {_OUTPUT_PATH} ({len(html):,} bytes)")
