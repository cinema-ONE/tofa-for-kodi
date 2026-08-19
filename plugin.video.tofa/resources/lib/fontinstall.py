"""Injects tofa's bundled fonts into whichever Kodi skin is currently active.
Kodi's `GUIFontManager` only ever loads `Font.xml` from the active skin --
there is no supported way for an add-on to ship fonts for its own
`WindowXMLDialog` screens. Same hack a Kodi dev documented on the official
forum in 2013 (https://forum.kodi.tv/showthread.php?tid=174694) and it still
holds: copy font files + append namespaced `<font>` entries into the active
skin's own `Font.xml`, then restart (fonts only load once).

Nothing is written without consent. The dialog comes FIRST, before any file
is copied or any Font.xml touched, because this edits a skin the user
installed and did not ask us to modify. Declining writes nothing at all,
and is remembered (as the declined FONT_SET_VERSION) so it costs one dialog
rather than one per window open; Settings > Appearance > "Install tofa
fonts" is the way back in, and a later font set asks again by itself.

Checked from two places, both calling the same cheap, idempotent
ensure_tofa_fonts_installed(): service.py at Kodi startup, and every window
class's open()/create() choke point in windows/kodigui.py. The latter is
needed because service.py's check runs once per Kodi process start -- an
in-place add-on update (FONT_SET_VERSION bump) without a full Kodi restart
would otherwise go undetected until the next restart.

Every injected font id/filename is prefixed `tofa_` so this can never
collide with the host skin's own fonts -- must be a no-op for anyone not
using tofa's screens.

CoreELEC's bundled skin.estuary lives on a read-only squashfs `/`, so
`Font.xml` can't be edited in place there. Fix: copy the whole skin into
the writable `special://home/addons/` first (Kodi prefers a userdata copy
over the read-only original by id match), then patch that copy instead.

**Windows is the same shape for a different reason**: Kodi installs under
`C:\\Program Files\\Kodi`, and no ordinary user may write there. It went
unnoticed until 2026-08-16 because the writability probe was
`os.access(..., W_OK)`, which on Windows reports the read-only ATTRIBUTE and
never the ACL -- so it answered True, the copy never happened, and both
callers failed on the write. See `_is_writable`.
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from typing import Optional

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import log

# Bump whenever FONTS or the bundled .ttf files change. Idempotency only
# checks for this marker, not actual content, so a version number must
# never be reused (even for a reverted change) -- a dev instance that
# already injected that version under different content would wrongly
# skip re-injection.
#
# Profile avatars (the "Who's watching?" picker) deliberately do NOT go
# through this mechanism -- they're bespoke full-color SVGs rasterized to
# PNG (see tools/gen_avatar_assets.py), and a font glyph can only ever be
# one solid color, which can't reproduce multi-color artwork.
FONT_SET_VERSION = 25
_VERSION_MARKER = f"<!-- tofa-fonts-v{FONT_SET_VERSION} -->"

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
_ = ADDON.getLocalizedString

# tofa_font_<role> -> (source .ttf in resources/skins/Main/fonts/, size, style)
# Inter Tight's sizes below are ~2x Kodi's old font12/13/30 fallback-font
# equivalents, not a typo: its unusually generous vertical metrics/leading
# make it render visibly smaller than Kodi's fallback font at the same
# nominal <size>. Roboto Mono's metrics needed no such correction.
FONTS: dict[str, tuple[str, int, str]] = {
    "tofa_font_caption": ("inter_tight_semibold.ttf", 25, "Regular"),
    "tofa_font_body": ("inter_tight_regular.ttf", 24, "Regular"),
    "tofa_font_heading": ("inter_tight_bold.ttf", 57, "Regular"),
    # 7.2's card-options panel title, stated as 34/Bold. 7.2 is 1:1 with
    # our canvas (its row label of 26 is exactly tofa_font_row_title), so
    # 34 is literal rather than a half-density value needing scaling.
    "tofa_font_dialog_title": ("inter_tight_bold.ttf", 34, "Regular"),
    "tofa_font_button": ("inter_tight_semibold.ttf", 28, "Regular"),
    "tofa_font_link": ("RobotoMono-Bold.ttf", 32, "Regular"),
    "tofa_font_code": ("RobotoMono-Bold.ttf", 66, "Regular"),
    # General TV type-scale roles (tofa UX/styleguide.md).
    #
    # 77 is §3's hero, and it is RIGHT -- but only where it is a screen
    # HEADING. Measured 2026-08-19 against the live Apple TV: the Switch
    # Server page's "Pick where to watch from." caps at 56px, which is
    # exactly 77 through Inter Tight's 0.7275 cap ratio, cross-checked on
    # x-height (its 'o' and ours both 40px). Its one caller is
    # script-tofa-serverpicker.xml.
    "tofa_font_hero": ("inter_tight_bold.ttf", 77, "Regular"),
    # The hero TITLE on Home and Detail, which is a different thing: it
    # renders only when a title has no logo art, standing in for artwork
    # rather than heading a screen, and the app sets it visibly smaller.
    # Measured off live captures of the SAME logo-less title on both
    # screens (cap height, glyph-anchored threshold -- calibrated, it
    # predicts our own 77 to the pixel):
    #
    #     Home    cap 43px -> 59      Detail  cap 46px -> 63
    #
    # The app really does use two sizes there (cap ratio 1.070, line-pitch
    # ratio 1.079 -- two independent metrics agreeing). 61 is one value for
    # both, Adrian's explicit call, and lands within 3-4% of each -- under
    # the 7% that itself took two agreeing metrics to see.
    #
    # Weight stays bold: stem/cap measures 0.186 on Home and 0.179 on the
    # picker against our 0.196, all inside the +/-1px (~10%) a stem this
    # size can be read to. Detail reads 0.239, but its glyph sits over a
    # bright backdrop that fattens antialiased strokes at a fixed
    # threshold -- not a weight signal.
    "tofa_font_hero_title": ("inter_tight_bold.ttf", 61, "Regular"),
    "tofa_font_section_title": ("inter_tight_semibold.ttf", 39, "Regular"),
    "tofa_font_row_title": ("inter_tight_semibold.ttf", 26, "Regular"),
    "tofa_font_micro": ("inter_tight_regular.ttf", 16, "Regular"),
    # eyebrow: section labels -- design spec calls for letterspacing, which
    # Kodi has no control for, so only size/weight are replicated. metadata:
    # sidebar row counts, smaller/Regular-weight. Sort/Filter/Quality/
    # genre-pill text reuses tofa_font_row_title (same scale as the nav
    # bar's own tabs), not a new role.
    "tofa_font_eyebrow": ("inter_tight_bold.ttf", 17, "Regular"),
    "tofa_font_metadata": ("inter_tight_regular.ttf", 23, "Regular"),
    # Settings' identity card, first line. SMALLER and HEAVIER than
    # tofa_font_metadata, because the app's is: measured off a build 17
    # capture against ours, its ink is 31px tall to our 34 with a mean
    # stroke of 3.44px to our 2.97 -- smaller and thicker at once, which is
    # a weight change, not a size one. 23 * 31/34 = 21, and the
    # stroke-to-height ratio (0.111 vs 0.087) is regular -> semibold.
    # 20, not the 23 * 31/34 = 21 the arithmetic suggests: 21 measured 33px
    # of ink against the app's 31, held across every threshold from 60 to
    # 110, so it was a real 2px rather than antialiasing. The size is also
    # what lets the card show a full address where ours had to truncate.
    "tofa_font_account": ("inter_tight_semibold.ttf", 20, "Regular"),
    "tofa_font_sidebar_label": ("inter_tight_regular.ttf", 26, "Regular"),
    "tofa_font_poster_title": ("inter_tight_semibold.ttf", 24, "Regular"),
    # 7.3's Top Result hero, sized to CAP HEIGHT measured off the real Apple
    # TV (2026-08-06, query "up": title cap 38px, eyebrow cap 10px) exactly
    # like the two player roles below.
    #
    # 7.3 states the title as "50pt bold". That is 50pt of SF Pro; Inter
    # Tight's cap is 0.7275/em, so 50 would render a 36.4px cap against the
    # app's 38. 52 is what the spec's own number MEANS once converted through
    # the typeface we actually ship -- matching nominal <size> across two
    # different faces is the mistake, not the fix.
    #
    # The eyebrow has no size in 7.3 (it gives weight, tracking and colour
    # only); 14 is the cap-10 equivalent. It is NOT tofa_font_eyebrow, which
    # is 17 and caps at 12.4 -- visibly heavier than the app's.
    # 7.3's "quiet Results for <query>" caption. REGULAR, not the semibold
    # tofa_font_section_title it used to borrow: side by side against the app
    # that role was both a weight and a size too heavy.
    #
    # Cap 17, measured off the 'R' of "Results" ALONE on a live capture. A
    # first pass measured the whole string and got 22, but " and p overshoot
    # the cap band at both ends -- isolate one cap-height glyph or the number
    # comes out ~30% high. 17 / 0.7275 = 23.4.
    "tofa_font_results_caption": ("inter_tight_regular.ttf", 23, "Regular"),
    "tofa_font_top_result_title": ("inter_tight_bold.ttf", 52, "Regular"),
    "tofa_font_top_result_eyebrow": ("inter_tight_bold.ttf", 14, "Regular"),
    # Player chrome's top-left title block. Sized to CAP HEIGHT measured off
    # the real Apple TV player (34px title / 22px subtitle, see
    # internal-docs/atv-reference/player-measurements.md), then converted
    # through Inter Tight's own metrics rather than pasted as-is: bold 45
    # renders a 34px cap, regular 30 a 22px cap. Matching cap height is the
    # right equivalence between two different typefaces -- matching nominal
    # <size> is not.
    "tofa_font_player_title": ("inter_tight_bold.ttf", 45, "Regular"),
    "tofa_font_player_subtitle": ("inter_tight_regular.ttf", 30, "Regular"),
    # 8.8's pause-card clock. REGULAR, not the bold tofa_font_heading it used
    # to borrow: measured against the real Apple TV (both the stored
    # player-pause-card.png and a fresh 2026-08-13 capture, which agree to the
    # pixel) the app's digits are 37px tall with a median stroke of 4-5px, a
    # stroke-to-height ratio of 0.108/0.135 at thresholds 170/140. Inter Tight
    # regular at 51 reproduces BOTH numbers exactly; semibold reads 0.162/0.189
    # and bold 0.216 -- a weight and a half too heavy. 51 is also what the
    # cap-height convention gives on its own: 37 / 0.7275 = 50.9.
    #
    # The line under it stays bold on the app -- the emphasis is on the time
    # remaining, not on the clock.
    "tofa_font_player_clock": ("inter_tight_regular.ttf", 51, "Regular"),
    # ...and the line under it, which borrowed tofa_font_button (semibold 28)
    # and was a size AND a weight light. Measured on the 'm' of "min" -- one
    # glyph with neither ascender nor descender, so its ink IS the x-height --
    # at half of each band's own peak, which is the one stroke metric a blurry
    # HDMI capture and a clean render can share:
    #
    #     app (live)    w 27  x-height 18  stem 5   ratio 0.278
    #     app (stored)  w 26  x-height 18  stem 5   ratio 0.278
    #     ours (was)    w 22  x-height 15  stem 4   ratio 0.267
    #
    # Bold 33 reproduces all four of the app's numbers; semibold 33 gets the
    # x-height right and the stem one pixel light. 18 / 33 is also exactly
    # Inter Tight's x-height/em, the same metric conversion the roles above use.
    "tofa_font_player_timeleft": ("inter_tight_bold.ttf", 33, "Regular"),
    # 8.11's stats readouts, sized from the reference captures the same
    # cap-height way as the two roles above: the pill's and the panel's
    # values measure an 11px cap, the panel's section eyebrows an 8px one.
    # Values are MONOSPACE on purpose -- they are numbers that tick once a
    # second, and a proportional face makes the whole row shuffle sideways
    # every time a digit changes width. Roboto Mono's cap is ~0.71em, so 11
    # needs 16; Inter Tight's is ~0.735, so the 11px key column needs 15 and
    # the 8px eyebrow 11.
    "tofa_font_stats_value": ("RobotoMono-Regular.ttf", 16, "Regular"),
    "tofa_font_stats_key": ("inter_tight_regular.ttf", 15, "Regular"),
    "tofa_font_stats_eyebrow": ("inter_tight_bold.ttf", 11, "Regular"),
    "tofa_font_stats_title": ("inter_tight_bold.ttf", 14, "Regular"),
    # Icon-font roles, one per pixel footprint the UI uses. Sizes are
    # literal target px -- icon fonts fill their em-square, unlike Inter
    # Tight's correction above -- but verify live before reusing for a
    # new size.
    #
    # The footprints below are what the skin ACTUALLY draws, re-derived by
    # counting <font> references per role (2026-08-19). Three of these
    # comments had drifted: a role is named for a number, not a place, so
    # nothing catches it when the place moves. If you move an icon, fix the
    # comment in the same commit -- the design-language page states these
    # callers and is generated from the skin, so the two will disagree.
    #
    #   36 -- nav-bar tabs, episode + collection card marks, player transport
    #   26 -- the player OSD, all 25 callers. NOT sidebar rows: those are 24
    #   24 -- sidebar / picker / card-options row icons, pill icons
    #   19 -- chevrons and inline marks; the most-used icon role
    "tofa_font_icons_36": ("lucide-icons.ttf", 36, "Regular"),
    "tofa_font_icons_26": ("lucide-icons.ttf", 26, "Regular"),
    "tofa_font_icons_24": ("lucide-icons.ttf", 24, "Regular"),
    "tofa_font_icons_19": ("lucide-icons.ttf", 19, "Regular"),
    # 56 is the placeholder size: BOTH card placeholders live here
    # (poster_visual()'s film glyph and person_card()'s user-round), plus
    # Search's other empty states and the player's skip-back/forward.
    # 80 and 64 are one caller each and neither is a placeholder -- 80 is
    # sign-in's expired-code clock, 64 is Search's idle / first-run empty
    # state. They shared this comment until 2026-08-19 and it described 56.
    "tofa_font_icons_80": ("lucide-icons.ttf", 80, "Regular"),
    "tofa_font_icons_64": ("lucide-icons.ttf", 64, "Regular"),
    "tofa_font_icons_56": ("lucide-icons.ttf", 56, "Regular"),
    # Search spacerow's backspace icon (24 * 1.2, rounded).
    "tofa_font_icons_29": ("lucide-icons.ttf", 29, "Regular"),
}

_SOURCE_FONTS_DIR = os.path.join(ADDON_PATH, "resources", "skins", "Main", "fonts")


def _font_entry_xml(name: str, filename: str, size: int, style: str) -> str:
    return (
        f"        <font>\n"
        f"            <name>{name}</name>\n"
        f"            <filename>tofa_{filename}</filename>\n"
        f"            <size>{size}</size>\n"
        f"            <style>{style}</style>\n"
        f"        </font>\n"
    )


def _is_writable(path: str) -> bool:
    """Can we actually create a file in this directory?

    This used to be `os.access(path, os.W_OK)`, which **lies on Windows**:
    there it reports only the read-only file ATTRIBUTE and never consults
    ACLs, so `C:\\Program Files\\Kodi\\addons\\skin.estuary` -- which no
    ordinary user may write -- came back True. The copy-to-a-writable-place
    fallback below therefore never ran, and both callers died on the write
    itself with `[Errno 13] Permission denied`: no fonts (so every Lucide
    glyph rendered as tofu) and an unpatched seek bar. Worse, the consent
    dialog re-asked on EVERY launch, because nothing it promised had
    happened.

    The only portable answer is to try it. Create a uniquely-named file and
    delete it again -- `os.access` cannot be fixed, only avoided.
    """
    probe = os.path.join(path, f".tofa-write-probe-{uuid.uuid4().hex}")
    try:
        with open(probe, "w"):
            pass
    except OSError:
        return False
    finally:
        # The probe must never outlive this call, even if the write raced
        # something else away: a stray dotfile inside a SKIN is the kind of
        # litter nobody goes looking for.
        try:
            os.remove(probe)
        except OSError:
            pass
    return True


def _find_font_xml_files(skin_path: str) -> list[str]:
    """A skin's Font.xml location varies by convention (`xml/Font.xml` on
    modern skins, a resolution folder like `1080i/Font.xml` on older ones)
    and a skin can define more than one. Walk and inject into every one
    found rather than guessing which the user's skin/resolution loads."""
    found = []
    for root, _dirs, files in os.walk(skin_path):
        if "Font.xml" in files:
            found.append(os.path.join(root, "Font.xml"))
    return found


def _already_injected(font_xml_files: list[str]) -> bool:
    if not font_xml_files:
        return False
    for path in font_xml_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                if _VERSION_MARKER not in f.read():
                    return False
        except OSError:
            return False
    return True


_OLD_ENTRY_RE = re.compile(
    r"[ \t]*<!--\s*tofa-fonts-v\d+\s*-->\n?"
    r"|[ \t]*<font>\s*<name>tofa_font_\w+</name>.*?</font>\s*\n?",
    re.DOTALL,
)


def ensure_writable_skin_path(skin_id: str, current_path: str) -> str:
    """Public because seekbarpatch.py patches the same skin and must do
    this identical dance -- CoreELEC ships skin.estuary on a read-only
    squashfs, so it has to be copied into the writable add-on dir first.
    Two implementations would mean two chances to get it wrong, and two
    copies of the skin if they disagreed on the destination."""
    if _is_writable(current_path):
        return current_path

    writable_path = os.path.join(xbmcvfs.translatePath("special://home/addons/"), skin_id)
    if not xbmcvfs.exists(writable_path + "/"):
        log.debug(f"fontinstall: {skin_id} isn't writable at {current_path} -- copying to {writable_path}")
        shutil.copytree(current_path, writable_path)
    return writable_path


def _inject_fonts(skin_path: str, font_xml_files: list[str]) -> None:
    fonts_dir = os.path.join(skin_path, "fonts")
    xbmcvfs.mkdirs(fonts_dir)
    for source_filename in {f[0] for f in FONTS.values()}:
        shutil.copyfile(
            os.path.join(_SOURCE_FONTS_DIR, source_filename),
            os.path.join(fonts_dir, f"tofa_{source_filename}"),
        )

    block = _VERSION_MARKER + "\n" + "".join(_font_entry_xml(name, *spec) for name, spec in FONTS.items())
    for path in font_xml_files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip any previously-injected tofa entries (any version) first --
        # never leave a stale set behind a fresh one; Kodi's behavior on a
        # duplicate <name> is undefined, so this must not just append.
        content = _OLD_ENTRY_RE.sub("", content)
        patched = content.replace("</fontset>", block + "</fontset>")
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
        log.debug(f"fontinstall: injected tofa fonts v{FONT_SET_VERSION} into {path}")


"""Remembers a FONT_SET_VERSION the user said no to, so declining costs one
dialog rather than one per window open. Stored as the version declined, not
a bare flag: a later font set is a new question, and gets asked again."""
DECLINED_SETTING = "fonts_declined_version"


def fonts_needed() -> bool:
    """True when this font set is not in the active skin's Font.xml yet.

    Deliberately answers False on any failure to inspect the skin: a missing
    Font.xml or an unreadable skin is not a licence to start writing into it.
    """
    try:
        skin_id = xbmc.getSkinDir()
        current_path = xbmcvfs.translatePath(xbmcaddon.Addon(skin_id).getAddonInfo("path"))
        font_xml_files = _find_font_xml_files(current_path)
        if not font_xml_files:
            log.warning(f"fontinstall: no Font.xml found under active skin {skin_id}, skipping")
            return False
        return not _already_injected(font_xml_files)
    except Exception as exc:
        log.warning(f"fontinstall: could not inspect the active skin: {exc}")
        return False


def apply_fonts() -> bool:
    """Copy the fonts in and patch the active skin's Font.xml. Returns True
    if anything was written.

    Consent is the CALLER's job (hostsetup.py) and must already have been
    given -- this function asks nothing and writes immediately."""
    try:
        skin_id = xbmc.getSkinDir()
        current_path = xbmcvfs.translatePath(xbmcaddon.Addon(skin_id).getAddonInfo("path"))
        font_xml_files = _find_font_xml_files(current_path)
        if not font_xml_files:
            return False

        writable_path = ensure_writable_skin_path(skin_id, current_path)
        if writable_path != current_path:
            font_xml_files = _find_font_xml_files(writable_path)

        _inject_fonts(writable_path, font_xml_files)
        return True
    except Exception as exc:
        log.warning(f"fontinstall: failed, continuing with default fonts: {exc}")
        return False
