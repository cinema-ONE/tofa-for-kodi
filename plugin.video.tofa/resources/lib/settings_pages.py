# -*- coding: utf-8 -*-
"""The Settings section's six pages, in sidebar order.

Single source of truth for both halves of the screen: skin/screens.py builds
one empty scaffold per not-yet-built page from this table, and
windows/main.py populates the sidebar list and the detail heading from the
same rows. They used to be the same list typed twice in the Home section and
that is exactly how a row goes missing from one of them.

Five pages mirror the real Apple TV app (see
internal-docs/atv-reference/settings-*.png). "This Device" is ours: the
add-on has genuinely Kodi-only settings -- skin-font installation, the local
accent fallback, the device id -- that the app has no equivalent of, and
putting them on their own page keeps the other five a faithful mirror rather
than a mirror with Kodi bolted into it.
"""
from __future__ import annotations

from .skin import icon_glyphs


class Page:
    __slots__ = ("key", "label", "glyph", "title", "subtitle", "built",
                 "opens_native")

    def __init__(self, key: str, label: str, glyph: int, title: str,
                 subtitle: str, built: bool = False,
                 opens_native: bool = False):
        self.key = key
        self.label = label
        self.glyph = glyph
        self.title = title
        # Kept for the shape of the constructor, but nothing sets it any
        # more: the bridge to Kodi's own settings dialog existed only while
        # This Device was unbuilt, and every setting that lived there has a
        # home now.
        self.opens_native = opens_native
        # The line under the page title. The app's are all of the form "...
        # on this Apple TV"; ours say "this device", since the same add-on
        # runs on a CoreELEC box, an Android box and a desktop.
        self.subtitle = subtitle
        # False renders 9.7's empty scaffold instead of the page. Flip as
        # each page lands.
        self.built = built


PAGES: tuple[Page, ...] = (
    Page("account", "Account", icon_glyphs.USER_ROUND,
         "Account", "Your account and connected server on this device",
         built=True),
    # "Playback & Video", the app's own name for this page in both the
    # sidebar and the heading. The subtitle already said what the app's says,
    # adapted for the device; only the name was ours.
    Page("playback", "Playback & Video", icon_glyphs.PLAY,
         "Playback & Video", "How titles play on this device", built=True),
    # Subtitle wording taken verbatim from the web app's own bundle, so the
    # same setting reads the same sentence on every tofa surface.
    Page("audio", "Audio & Subtitles", icon_glyphs.CAPTIONS,
         "Audio & Subtitles", "Language and subtitle defaults",
         built=True),
    Page("appearance", "Appearance", icon_glyphs.PALETTE,
         "Appearance", "Accent colour and how the library looks",
         built=True),
    # Privacy & About LAST: it is the reference section (diagnostics, version,
    # licences), not something a viewer sets, so it belongs after the ones
    # they do.
    Page("device", "This Device", icon_glyphs.TV,
         "This Device", "Settings that apply to this Kodi install only",
         built=True),
    Page("privacy", "Privacy & About", icon_glyphs.HAND,
         "Privacy & About", "Diagnostics, version, and legal", built=True),
)

# Scaffold copy for a page that is not built. Every page is built now, so
# this is unused in practice -- kept because the next new page will want it
# before it has content.
SCAFFOLD_MESSAGE = "Change this on the web app for now — the Account page has a QR code."
SCAFFOLD_MESSAGE_NATIVE = SCAFFOLD_MESSAGE

# Page key -> the control the sidebar's Right key should land on. A page with
# nothing focusable keeps focus in the sidebar rather than dropping it into a
# dead pane; MainWindow re-points the sidebar's Right target per page at
# runtime, the same way every other section re-points the nav bar's Down (a
# fragment baked once into static XML cannot vary by which page is showing).
RIGHT_TARGETS: dict[str, int] = {
    "account": 8110,
    # 8470 (Streaming quality), not 8460 (Next episode) and not 8410
    # (Intro): entering a page lands on its FIRST row, and QUALITY is now
    # the group above NEXT EPISODE. This entry has been wrong once per new
    # top group -- left stale, the new row can only be reached by pressing
    # Up from the top of the page, which reads as the row not being there.
    # 8911 is Streaming quality's FIRST PILL. Was 8470, the list that row
    # used to be; the segmented rows became groups of focusable pills and a
    # stale id here means Right does nothing at all, which is how this was
    # found. The comment above has now been earned twice.
    "playback": 8911,
    "audio": 8510,
    "appearance": 8200,
    "privacy": 8620,
    "device": 8710,
}


def by_key(key: str) -> Page | None:
    for page in PAGES:
        if page.key == key:
            return page
    return None
