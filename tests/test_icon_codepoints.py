"""Every icon codepoint we emit is a real Lucide glyph, and the right one.

Adrian, 2026-08-31, comparing our Detail against the reference capture
`tofa UX/apple-tv/tv-detail-hero.webp`: the Rewatch pill drew a TOGGLE SWITCH
where the app draws a counterclockwise arrow. It had shipped as a hardcoded
`&#xE18B;`, which is Lucide `toggle-left`. The comment one line above it said
the icon was `arrow.counterclockwise` / Replay, so the intent was recorded
correctly and the number simply did not match it -- which is exactly what a
raw codepoint buys you.

Auditing all 78 raw codepoints across the skin sources at the same time found
that one and no others; this test is that audit, kept.

WHAT IT CANNOT CATCH. A codepoint that is a valid glyph but the WRONG glyph
still passes the resolve check -- `toggle-left` is a perfectly real icon. Only
the named assertions below catch that class, so add one for any icon whose
identity actually matters.

Run:  python3 test_icon_codepoints.py
"""
import json
import pathlib
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.skin import icon_glyphs

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIN = ROOT / "plugin.video.tofa" / "resources" / "lib" / "skin"
CODEPOINTS = ROOT / "tools" / "lucide_font_src" / "codepoints.json"

raw = json.loads(CODEPOINTS.read_text())
BY_CODE = {(int(v, 16) if isinstance(v, str) else int(v)): k for k, v in raw.items()}
check("the Lucide codepoint map loads", len(BY_CODE) > 100, str(len(BY_CODE)))


def emitted():
    """(file, line, codepoint, context) for every &#xNNNN; we ship."""
    out = []
    for path in sorted(list(SKIN.rglob("*.py")) + list((SKIN / "static").rglob("*.xml"))):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for m in re.finditer(r"&#x([0-9A-Fa-f]{4});", line):
                out.append((path.name, lineno, int(m.group(1), 16), line.strip()[:70]))
    return out


found = emitted()
check("we found the codepoints to check", len(found) > 40, str(len(found)))

unknown = [(f, n, hex(c), ctx) for f, n, c, ctx in found if c not in BY_CODE]
check("every emitted codepoint is a real Lucide glyph",
      not unknown, "; ".join(f"{f}:{n} {c}" for f, n, c, _ in unknown[:5]))

# --- the ones whose identity is load-bearing --------------------------
# name -> (codepoint, the label it sits next to)
NAMED = {
    "rotate-ccw": (icon_glyphs.ROTATE_CCW, "Rewatch"),
}
for want, (code, label) in NAMED.items():
    check(f"{label} uses Lucide {want}", BY_CODE.get(code) == want,
          f"{hex(code)} is {BY_CODE.get(code)!r}")

# The specific regression: Rewatch must not be a toggle again.
detail = (SKIN / "screens.py").read_text()
rewatch = [l for l in detail.splitlines() if '"Rewatch"' in l]
check("the Rewatch pill exists in screens.py", len(rewatch) == 1, str(rewatch))
check("...and does NOT hardcode a raw codepoint",
      not any(re.search(r"&#x[0-9A-Fa-f]{4};", l) for l in rewatch), str(rewatch))
check("...toggle-left is not used anywhere",
      not any(c == 0xE18B for _, _, c, _ in found),
      "0xE18B (toggle-left) is back")

# --- the rendered XML really carries the fixed glyph -------------------
rendered = (ROOT / "plugin.video.tofa" / "resources" / "skins" / "Main" / "1080i"
            / "script-tofa-detail.xml").read_text()
check("the rendered Detail XML emits rotate-ccw",
      f"&#x{icon_glyphs.ROTATE_CCW:X};" in rendered)
check("...and no longer emits toggle-left", "&#xE18B;" not in rendered)

failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"all {len(RESULTS)} checks passed" if not failed
      else f"{len(failed)} of {len(RESULTS)} checks FAILED")
raise SystemExit(1 if failed else 0)
