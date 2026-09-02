"""Validates every skin XML in the add-on, generated and hand-written alike.

Exists because of one recurring mistake: `--` inside an XML comment is
ILLEGAL, and prose comments want to use it constantly ("this is X -- not
Y"). Kodi's own parser rejects the file, and what you see is not an error
message but a screen that silently keeps its previous layout, or a window
that will not open at all.

resources/lib/skin/build.py already guards the GENERATED screens, but the
player's XML is hand-written and had no guard, which is where this kept
biting. Run this after touching any XML:

    python3 tools/check_xml.py

Every check here guards a SILENT failure. That is the whole selection
rule: Kodi does not refuse any of these, log any of them, or draw anything
that looks like an error. It just renders something subtly wrong, which is
why they survive a screenshot and reach the box.

Checks, per file:
  1. it parses at all
  2. no `--` inside a comment
  3. every `<control>` id is unique within the file, since a duplicate id
     silently shadows the first and Python's getControl() then addresses
     whichever Kodi resolved
  4. every texture it names exists in media/. A missing texture draws as
     NOTHING: glass_pill(height=56) once asked for a capsule-h56.png that
     was never generated, and the pill rendered as bare unbacked text.
  5. every font it names is one that fontinstall.py registers. A font name
     Kodi cannot resolve falls back to the ACTIVE SKIN's font of that name,
     or to its default -- so the text still appears, at the wrong size, and
     the screen looks merely badly proportioned rather than broken. A whole
     pass of 49 such host-skin references had to be cleaned up once.

Plus, once per run:
  * every .ttf fontinstall.py names exists in fonts/
  * both directions of the exact-size asset loop
  * nothing in media/ is orphaned. The opposite of check 4, and the one
    check here that guards rot rather than a silent failure: art nobody can
    draw is harmless to ship but accumulates, and six files ported from
    plex-for-kodi in the first commit lasted until 2026-08-06 -- by which
    time the only mentions of them were comments saying they were replaced.
    Comments are therefore stripped before the sweep, and usage is read from
    three places, since a texture reaches Kodi three ways. See _usage_index.

    python3 tools/check_xml.py
"""
from __future__ import annotations

import collections
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

_ADDON = os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa")
_SKIN_DIR = os.path.join(_ADDON, "resources", "skins")
_MEDIA_DIR = os.path.join(_SKIN_DIR, "Main", "media")
#: The fonts live in resource.font.tofa now, prefixed so the active skin's
#: own fonts/ cannot shadow them -- see fontinstall.py's docstring.
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..",
                         "resource.font.tofa", "resources")
_FONT_PREFIX = "tofa_"
_FONTINSTALL = os.path.join(_ADDON, "resources", "lib", "fontinstall.py")

_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
# <texture>, <texturefocus>, <texturenofocus>, <midtexture>, and whatever
# else Kodi grows: any tag with "texture" in its name carries an asset path.
_TEXTURE = re.compile(r"<([a-z]*texture[a-z]*)\b[^>]*>([^<]*)</\1>")
_FONT = re.compile(r"<font>([^<]*)</font>")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _assets() -> set[str]:
    """Every file under media/, as the forward-slash relative path a
    <texture> would name it by."""
    found = set()
    for dirpath, _, filenames in os.walk(_MEDIA_DIR):
        rel = os.path.relpath(dirpath, _MEDIA_DIR)
        for name in filenames:
            path = name if rel == "." else rel.replace(os.sep, "/") + "/" + name
            found.add(path)
    return found


def _registered_fonts() -> set[str]:
    """The keys of fontinstall.py's FONTS table.

    Read as text rather than imported: fontinstall imports xbmcaddon at
    module level, which does not exist outside Kodi."""
    text = open(_FONTINSTALL, encoding="utf-8").read()
    body = text[text.index("FONTS: dict"):]
    return set(re.findall(r'"(tofa_font_[a-z0-9_]+)"\s*:', body))


def _font_files() -> list[str]:
    """The .ttf filenames FONTS maps to, in declaration order."""
    text = open(_FONTINSTALL, encoding="utf-8").read()
    body = text[text.index("FONTS: dict"):]
    return re.findall(r':\s*\("([^"]+\.ttf)"', body)


def _is_dynamic(ref: str) -> bool:
    """Values this checker cannot and should not resolve.

    `-` is Kodi's own idiom for "no texture", not a filename. `$INFO[...]`
    and friends are resolved at runtime, and `special://`/`http` point
    outside the skin (cached artwork, downloaded tiles)."""
    return (not ref or ref == "-" or "$" in ref
            or ref.startswith(("special://", "http://", "https://")))


_LIB_DIR = os.path.join(_ADDON, "resources", "lib")
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# Any media filename token, wherever it appears. Deliberately blunter than
# _TEXTURE above: a mask is named in a `diffuse="..."` ATTRIBUTE, not in
# element text, and there are `<bordertexture>`/`<texturefocus>` spellings
# too. For "is this file used at all?" over-capturing is the safe direction.
_MEDIA_TOKEN = re.compile(r"[A-Za-z0-9_./-]+\.(?:png|gif|jpg)")

# A texture name BUILT rather than written out: some literal head, then a
# placeholder. Catches all three spellings in use -- "poster-progress/{0}.png",
# "badge-fmt-%s.png", f"avatar-{slug}.png" -- and keeps the literal head, so
# one hit covers a whole folder or name family.
_BUILT_TOKEN = re.compile(
    r"""["'](?P<head>[a-z0-9][a-z0-9/_-]*?)"""
    r"""(?:\{[^}"']*\}|%[sd])[^"']*\.(?:png|gif|jpg)["']"""
)

# A texture name built by KODI rather than by Python: $INFO's three-argument
# form, `$INFO[Window.Property(x),head-,-00.png]`, wraps the property in a
# prefix and postfix at draw time. The splash's 14 foxes are named this way --
# one property picks 196 files -- and without this the whole set reads as
# orphaned, which is exactly the "cries wolf every run" failure the orphan
# check is written to avoid.
_INFO_BUILT = re.compile(
    r"""\$INFO\[[^\],]+,\s*(?P<head>[A-Za-z0-9][A-Za-z0-9/_-]*?)\s*,[^\]]*?\.(?:png|gif|jpg)\]"""
)

_PY_COMMENT = re.compile(r"#[^\n]*")
_PY_DOCSTRING = re.compile(r'"""(?:(?!""").)*"""|\'\'\'(?:(?!\'\'\').)*\'\'\'', re.S)


def _scan(text: str) -> tuple[set[str], set[str]]:
    """(exact filenames, family prefixes) named by one file's real code."""
    built = {m.group("head") for m in _BUILT_TOKEN.finditer(text) if m.group("head")}
    built |= {m.group("head") for m in _INFO_BUILT.finditer(text) if m.group("head")}
    return set(_MEDIA_TOKEN.findall(text)), built


def _usage_index(xml_paths: list[str]) -> tuple[set[str], set[str]]:
    """What the codebase can actually name, ignoring prose.

    COMMENTS ARE STRIPPED FIRST, and that is the point. The six files this
    check was written for -- busy.gif and friends, ported from plex-for-kodi
    in the first commit -- were mentioned in exactly two places by 2026-08-06,
    both of them comments SAYING THEY WERE REPLACED. A sweep that counts prose
    as usage would have called them live forever.

    Three sources, because a texture reaches Kodi three ways:
      * the RENDERED skin XML -- ground truth for what Kodi loads, since
        build.py rewrites textures on the way out (_slice_pills, exact-size
        substitution), so source and output genuinely disagree;
      * resources/lib Python -- names written out (theme.py's accent-logo
        table) and names assembled (the 12 avatars, the 18 format badges);
      * tools/ -- a generator that WRITES a file declares it wanted even if
        no screen names it today, and gen_exact_assets.py READS source PNGs.
        Capsule art is the case in point: _slice_pills replaces most of it
        with pre-cut slices, but build.py falls back to the 9-patch whenever
        it cannot prove the slice safe, so the files have to stay.

    Docstrings are stripped from tools/ (prose about assets) but NOT from
    resources/lib, where fragments.py holds every texture reference inside
    triple-quoted XML. This file is skipped entirely -- it names assets in
    its own explanation.
    """
    exact, families = set(), set()
    for path in xml_paths:
        text = _COMMENT.sub("", open(path, encoding="utf-8").read())
        e, f = _scan(text)
        exact |= e
        families |= f

    for root, strip_docstrings in ((_LIB_DIR, False), (_TOOLS_DIR, True)):
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                path = os.path.join(dirpath, name)
                if not name.endswith(".py") or os.path.abspath(path) == os.path.abspath(__file__):
                    continue
                text = open(path, encoding="utf-8").read()
                if strip_docstrings:
                    text = _PY_DOCSTRING.sub("", text)
                text = _PY_COMMENT.sub("", text)
                e, f = _scan(text)
                exact |= e
                families |= f

    return {os.path.basename(r) for r in exact} | exact, families


def _unused_asset_problems(assets: set[str], xml_paths: list[str]) -> list[str]:
    """Art in media/ that nothing can draw.

    Harmless to ship, but it is how a folder rots: six files ported from
    plex-for-kodi in the very first commit survived until 2026-08-06, one of
    them still described as the player's spinner in a published doc page long
    after spinner-arc.png replaced it.

    Generous on purpose. A family prefix covers everything under it, so the
    three capsule heights whose OUTLINE variant nothing draws are not
    reported: gen_capsule_pill_assets.py emits a fill and an outline per
    height, so they would come straight back, and a check that cries wolf
    every run is one everybody learns to ignore.
    """
    referenced, families = _usage_index(xml_paths)
    orphans = [
        rel for rel in sorted(assets)
        if rel not in referenced
        and os.path.basename(rel) not in referenced
        and not any(rel.startswith(p) for p in families)
        and os.path.splitext(rel)[1].lower() in (".png", ".gif", ".jpg")
    ]
    return ["%s: no screen names it, no runtime name builds it, no tool "
            "writes or reads it" % rel for rel in orphans]


def check(path: str, assets: set[str], fonts: set[str]) -> list[str]:
    text = open(path, encoding="utf-8").read()
    problems = []

    for match in _COMMENT.finditer(text):
        if "--" in match.group(1):
            problems.append(
                "line %d: '--' inside an XML comment (use ';' or a comma)"
                % _line_of(text, match.start()))

    ids = [m.group(1) for m in re.finditer(r'<control\b[^>]*\bid="(\d+)"', text)]
    for cid, count in collections.Counter(ids).items():
        if count > 1:
            problems.append("control id %s declared %d times" % (cid, count))

    for match in _TEXTURE.finditer(text):
        ref = match.group(2).strip()
        if not _is_dynamic(ref) and ref not in assets:
            problems.append(
                "line %d: <%s> names %s, which is not in media/"
                % (_line_of(text, match.start()), match.group(1), ref))

    for match in _FONT.finditer(text):
        ref = match.group(1).strip()
        if not _is_dynamic(ref) and ref not in fonts:
            problems.append(
                "line %d: font %s is not one fontinstall.py registers "
                "(it would silently resolve against the HOST skin)"
                % (_line_of(text, match.start()), ref))

    try:
        ET.fromstring(text)
    except ET.ParseError as exc:
        problems.append("does not parse: %s" % exc)

    return problems


def _exact_asset_problems() -> list[str]:
    """Both directions of the exact-size asset loop.

    An exact-size texture is pinned to one width and height, so it silently
    stops being right when a layout number moves. The renderer knows what is
    wanted -- it computes it from the same fragments the XML comes from -- so
    ask it, and compare against what is on disk:

      * WANTED BUT MISSING: build.py leaves the 9-patch in place rather than
        emitting a texture that does not exist, so nothing breaks; the shape
        just keeps its old soft corners. Silent, which is why it is reported.
      * PRESENT BUT UNWANTED: art for a size nothing uses any more. Harmless
        to ship, but it is how a media folder rots.

    Both are fixed by running tools/gen_exact_assets.py (with --prune for
    the second). Skipped quietly if the renderer cannot be imported, so this
    tool keeps working as a plain XML checker outside a full checkout.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                        "plugin.video.tofa", "resources"))
        from lib.skin import build
    except Exception:
        return []
    try:
        wanted = build.collect_exact_requests()
    except Exception as exc:
        return ["could not ask the renderer for exact-asset sizes: %s" % exc]
    have = {n for n in os.listdir(_MEDIA_DIR)
            if n.startswith(("pill-outline-", "exact-"))}
    problems = []
    for name in sorted(set(wanted) - have):
        spec = wanted[name]
        problems.append(
            "%s is needed at %dx%d but does not exist; that shape is "
            "still shipping its old 9-patch. Run tools/gen_exact_assets.py"
            % (name, spec["width"], spec["height"]))
    for name in sorted(have - set(wanted)):
        problems.append(
            "%s is not referenced by any screen any more. Run "
            "tools/gen_exact_assets.py --prune" % name)
    return problems


#: XML we ship that is NOT skin XML. The texture/font/control-id checks mean
#: nothing here, but the two that guard silent failures do: it has to parse,
#: and `--` inside a comment is illegal. Added after resources/settings.xml
#: was found to have carried an illegal `--` since it was written -- Kodi's
#: own TinyXML tolerates it where a strict parser does not, so it had never
#: surfaced, and a settings file Kodi fails to read means settings that
#: silently do not persist.
_OTHER_XML = ("addon.xml", os.path.join("resources", "settings.xml"))



_RADIUS_NAME = re.compile(r"^rounded-(\d+)$")
_CAPSULE_NAME = re.compile(r"^capsule-h(\d+)$")


def _radius_problems(xml_paths: list) -> list:
    """A nine-patch corner is copied from the source UNSCALED, so the border
    a texture is sliced at must equal the radius baked into it. Slice a
    radius-14 asset at 8 and Kodi draws 8px of a 14px arc, then stretches the
    leftover curve along the edges -- corners that do not match each other,
    which is what "the radii are not uniform" looks like.

    The asset NAMES are the spec and need no pixel measurement:
    `rounded-R` is baked at radius R, and `capsule-hN` is a stadium N tall,
    so its corner is N//2. Both conventions are enforced by the generators
    (gen_panel_assets._rounded, gen_capsule_pill_assets.gen_height_capsule).

    This check exists because the fault keeps coming back: it has been found
    by eye on Discover's tab pills, on 8.4's panel rows ("bulged"), and again
    on the player's scrub bubble and season chips. Every one of those shipped
    for a while first. See feedback_capsule_ninepatch_rule.
    """
    problems = []
    for path in xml_paths:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for match in re.finditer(
                r'<texture[^>]*border="(\d+)"[^>]*>([^<]+)</texture>', text):
            border, ref = int(match.group(1)), match.group(2).strip()
            stem = os.path.basename(ref)[:-4].replace("-outline", "")
            named = _RADIUS_NAME.match(stem) or _CAPSULE_NAME.match(stem)
            if not named:
                continue
            want = (int(named.group(1)) if stem.startswith("rounded-")
                    else int(named.group(1)) // 2)
            # GREATER than the radius is fine, and is what the Options
            # dialog does: panel-r22 (radius 22) sliced at border 24. The
            # border only has to ENCLOSE the corner, and a couple of units of
            # margin puts the seam in the straight section where a rounding
            # error cannot land on the curve. Only a border SMALLER than the
            # radius truncates the arc, which is the actual fault.
            if border < want:
                problems.append(
                    "%s:%d %s is baked at radius %d but is sliced at "
                    "border=%d, which cuts the arc short; slice at %d or more"
                    % (os.path.basename(path), _line_of(text, match.start()),
                       ref, want, border, want))
    return problems



_ID_CONST = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(\(?[\d,\s]+\)?)\s*$", re.M)
_RESIZE_CALL = re.compile(r"\.set(?:Height|Width)\s*\(")


def _runtime_resized_ids() -> set:
    """Every control id the add-on resizes AFTER the window has loaded.

    Found by reading the windows themselves rather than from a hand-kept
    list, because a hand-kept list is what goes stale. Constants are plain
    ints or tuples of ints in a class body, so they resolve exactly; a
    resize call is attributed to whatever id constants appear in the few
    lines leading up to it, which covers both `getControl(self.X).setHeight`
    and the `for cid in self.XS:` loop form.
    """
    ids = set()
    windows = os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa",
                           "resources", "lib", "windows")
    for name in sorted(os.listdir(windows)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(windows, name), encoding="utf-8") as handle:
            text = handle.read()
        consts = {}
        for const, raw in _ID_CONST.findall(text):
            values = [int(v) for v in re.findall(r"\d+", raw)]
            if values and all(1000 <= v <= 99999 for v in values):
                consts[const] = values
        lines = text.split("\n")
        # Methods that resize something themselves. A call to one of these is
        # as good as a setHeight() for our purposes -- without this the guard
        # goes blind the moment somebody factors the resize into a helper,
        # which is exactly what happened to _size_panel's `_place()` and what
        # tests/test_exact_art_not_resized.py caught.
        resizers = set()
        current = None
        for line in lines:
            match = re.match(r"\s*def\s+(\w+)\s*\(", line)
            if match:
                current = match.group(1)
            elif current and _RESIZE_CALL.search(line):
                resizers.add(current)
        call = (re.compile(r"\b(?:" + "|".join(re.escape(n) for n in resizers) + r")\s*\(")
                if resizers else None)
        for i, line in enumerate(lines):
            if not _RESIZE_CALL.search(line) and not (call and call.search(line)):
                continue
            for back in range(max(0, i - 6), i + 1):
                for const, values in consts.items():
                    if re.search(r"\b" + const + r"\b", lines[back]):
                        ids.update(values)
    return ids


def _resized_exact_problems(xml_paths: list) -> list:
    """An exact-size texture has NO border, so Kodi stretches the WHOLE image
    -- corners included -- to whatever size the control ends up at. On a
    control the add-on resizes after load that turns a fixed corner radius
    into an ellipse: the player's 8.4 panel is authored 287x492 and sized
    222..812 by row count, which drew its 20px corners as 20x9 and 20x31.

    Cost an afternoon on 2026-08-10, and not for the first time. Mark such a
    control `resized-at-runtime` (skin/build.py RESIZED_MARKER) and the
    renderer will leave its nine-patch alone, which resizes correctly because
    a nine-patch draws its corners at a fixed size.
    """
    resized = _runtime_resized_ids()
    problems = []
    for path in xml_paths:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for match in re.finditer(
                r'<control type="image" id="(\d+)">'
                r'((?:(?!</control>).)*?)</control>', text, re.S):
            cid, body = int(match.group(1)), match.group(2)
            if cid not in resized:
                continue
            tex = re.search(r"<texture(?P<attrs>[^>]*)>([^<]+)</texture>", body)
            if not tex or 'border=' in tex.group("attrs"):
                continue
            if not tex.group(2).startswith("exact-"):
                continue
            problems.append(
                "%s:%d control %d is resized at runtime but ships border-less "
                "exact art (%s); Kodi will stretch its corners. Add the "
                "resized-at-runtime marker to the control in the skin source."
                % (os.path.basename(path), _line_of(text, match.start()), cid,
                   tex.group(2)))
    return problems


_LOCALIZE = re.compile(r"\$LOCALIZE\[(\d+)\]")


def check_basic(path: str) -> list[str]:
    """The subset of checks that apply to any XML document at all."""
    text = open(path, encoding="utf-8").read()
    problems = []
    for match in _COMMENT.finditer(text):
        if "--" in match.group(1):
            problems.append(
                "line %d: '--' inside an XML comment (use ';' or a comma)"
                % _line_of(text, match.start()))
    # $LOCALIZE in a window XML resolves against the ACTIVE SKIN's strings,
    # never this add-on's, and 31000-31999 is precisely the range skins use
    # for their own. Estuary's #31122 is "Unwatched TV Shows", which is what
    # the home-row note under Settings displayed until 2026-08-27 -- no
    # error, a plausible-looking string, and a different one per skin.
    #
    # Kodi's OWN strings (below 31000) would resolve, but there is no reason
    # for this add-on to reach for one, so the check covers every id.
    for match in _LOCALIZE.finditer(text):
        problems.append(
            "line %d: $LOCALIZE[%s] reads the ACTIVE SKIN's strings, not "
            "ours; set a window property from Python with _(%s) instead"
            % (_line_of(text, match.start()), match.group(1), match.group(1)))
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        problems.append("does not parse: %s" % exc)
    return problems


def main() -> int:
    paths = sorted(glob.glob(os.path.join(_SKIN_DIR, "**", "*.xml"), recursive=True))
    if not paths:
        print("no skin XML found", file=sys.stderr)
        return 2

    assets, fonts = _assets(), _registered_fonts()
    failed = 0

    missing_ttf = [f for f in _font_files()
                   if not os.path.exists(os.path.join(_FONT_DIR, _FONT_PREFIX + f))]
    if missing_ttf:
        failed += 1
        print("resources/lib/fontinstall.py")
        for name in sorted(set(missing_ttf)):
            print("    FONTS names %s, which resource.font.tofa does not ship"
                  " as %s%s" % (name, _FONT_PREFIX, name))

    exact_problems = _exact_asset_problems()
    if exact_problems:
        failed += 1
        print("exact-size assets")
        for problem in exact_problems:
            print("    " + problem)

    resized_problems = _resized_exact_problems(paths)
    if resized_problems:
        failed += 1
        print("exact art on a control that is resized at runtime")
        for problem in resized_problems:
            print("    " + problem)

    # The SOURCE templates, not the rendered output this file otherwise
    # checks. An illegal XML comment stops render_all() dead, so the
    # rendered XML stays STALE and every check below happily passes on
    # yesterday's file. Checking it here is what stops a green run from
    # meaning nothing. See tools/check_xml_comments.py.
    import check_xml_comments
    comment_problems = []
    for src in check_xml_comments._walk(check_xml_comments.DEFAULT_PATHS):
        comment_problems.extend(check_xml_comments.check(src))
    if comment_problems:
        failed += 1
        print("illegal XML comment in a skin SOURCE file (the skin will not re-render)")
        for problem in comment_problems:
            print("    " + problem)

    radius_problems = _radius_problems(paths)
    if radius_problems:
        failed += 1
        print("nine-patch radius != border")
        for problem in radius_problems:
            print("    " + problem)

    unused = _unused_asset_problems(assets, paths)
    if unused:
        failed += 1
        print("unused media")
        for problem in unused:
            print("    " + problem)

    for path in paths:
        problems = check(path, assets, fonts)
        if problems:
            failed += 1
            print(os.path.relpath(path, os.path.dirname(__file__)))
            for problem in problems:
                print("    " + problem)

    other = [os.path.join(_ADDON, name) for name in _OTHER_XML]
    other = [p for p in other if os.path.exists(p)]
    for path in other:
        problems = check_basic(path)
        if problems:
            failed += 1
            print(os.path.relpath(path, os.path.dirname(__file__)))
            for problem in problems:
                print("    " + problem)

    print("checked %d skin + %d other files against %d assets and %d fonts, "
          "%d with problems"
          % (len(paths), len(other), len(assets), len(fonts), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
