"""Kodi's own `advancedsettings.xml`, for the one setting our artwork needs.

Kodi caps the height of every texture it CACHES, before anything is drawn,
at `<imageres>` -- which defaults to **720**. Our server sends backdrops at
1920x1080 and posters at 500x750, so out of the box Kodi stores them as
1280x720 and 474x720 and then upscales to draw. Measured on a 1080p GUI, not
just a 4K one: a full-screen backdrop is drawn at 1920x1080 from a 1280x720
texture, so the loss is visible on any panel worth the name. This is why it
is not gated on screen size.

The downscale happens on the way INTO the cache, so no amount of higher-res
source art can compensate -- see tools/gen_exact_assets.py and the 2x asset
pass, both of which are defeated by it.

`<fanartres>` is deliberately NOT written. It already defaults to 1080, and
it never governed our backdrops anyway: Kodi only applies it to art it
classifies as fanart, and ours arrive as plain textures. Setting it would be
a no-op that looks meaningful, which is worse than leaving it out.

WHY TEXT SURGERY AND NOT ElementTree: this is the user's own config file. It
may hold their tuning, and it very often holds their comments about why.
Parsing and re-serialising with ElementTree silently drops every comment. So
the file is edited as text: one element is replaced or inserted and every
other byte survives.

Nothing here is written without consent -- hostsetup.py owns that dialog, the
same way it does for fontinstall.py.
"""
from __future__ import annotations

import re

import xbmcvfs

from . import log

#: What Kodi caps cached texture height at unless told otherwise
#: (`AdvancedSettings.cpp`: `m_imageRes = 720`).
KODI_DEFAULT_IMAGERES = 720

#: What we need. Exactly the tallest art the server sends -- going higher
#: would not gain anything, since Kodi never upscales INTO the cache.
WANTED_IMAGERES = 1080

#: Kodi reads advancedsettings.xml from the master profile's userdata. Not
#: `special://profile/`: that is the *current* Kodi profile, and this file is
#: global -- a household using Kodi profiles would otherwise get the setting
#: written somewhere Kodi does not read it back from.
ADVANCEDSETTINGS = "special://masterprofile/advancedsettings.xml"

_IMAGERES_RE = re.compile(r"<imageres>\s*(\d+)\s*</imageres>", re.I)
_ROOT_CLOSE_RE = re.compile(r"</advancedsettings>", re.I)
_ROOT_OPEN_RE = re.compile(r"<advancedsettings\s*>", re.I)

_NEW_FILE = """<advancedsettings>
{entry}
</advancedsettings>
"""

_ENTRY = """  <!-- Added by the tofa add-on. Kodi caps CACHED texture height at this
       before anything is drawn; the default of 720 stored tofa's 1920x1080
       backdrops as 1280x720 and upscaled them to fill the screen. Remove
       this element to go back to Kodi's default. -->
  <imageres>{value}</imageres>"""


def _read() -> str | None:
    """The file's text, or None if it isn't there. An unreadable file is
    reported as unreadable rather than as absent -- overwriting a file we
    merely failed to open would be the one unrecoverable mistake here."""
    if not xbmcvfs.exists(ADVANCEDSETTINGS):
        return None
    handle = xbmcvfs.File(ADVANCEDSETTINGS)
    try:
        return handle.read()
    finally:
        handle.close()


def current_imageres() -> int:
    """What Kodi will actually use: the file's value, or Kodi's default when
    the file has no opinion. Unreadable counts as "already fine" so a broken
    read can never trigger a write."""
    try:
        text = _read()
    except Exception as exc:
        log.warning(f"hostconfig: could not read {ADVANCEDSETTINGS}: {exc}")
        return WANTED_IMAGERES
    if text is None:
        return KODI_DEFAULT_IMAGERES
    match = _IMAGERES_RE.search(text)
    if not match:
        return KODI_DEFAULT_IMAGERES
    try:
        return int(match.group(1))
    except ValueError:
        return KODI_DEFAULT_IMAGERES


def imageres_needed() -> bool:
    """True when Kodi would cache our artwork smaller than the server sends
    it. A user who has already set this HIGHER than we ask is left alone."""
    return current_imageres() < WANTED_IMAGERES


def apply_imageres() -> bool:
    """Raise `<imageres>` to WANTED_IMAGERES, preserving the rest of the file
    byte for byte. Returns True if the file was changed.

    Takes effect only after a Kodi restart -- advancedsettings.xml is parsed
    once at startup and there is no reload path. The caller owns that.
    """
    # Guarded here as well as in imageres_needed(), not only there. A user who
    # has set this HIGHER than we ask has made a deliberate choice about their
    # own config file, and lowering it to our number would be a regression we
    # caused. hostsetup never calls this in that state, but this function
    # writes to a file we do not own and must not depend on its caller for
    # that. (A test caught exactly this: 2160 was being rewritten to 1080.)
    if not imageres_needed():
        return False
    try:
        text = _read()
    except Exception as exc:
        log.warning(f"hostconfig: refusing to write, {ADVANCEDSETTINGS} unreadable: {exc}")
        return False

    if text is None:
        updated = _NEW_FILE.format(entry=_ENTRY.format(value=WANTED_IMAGERES))
    elif _IMAGERES_RE.search(text):
        # Replace the value in place; the surrounding formatting and any
        # comment the user wrote above it stay exactly as they were.
        updated = _IMAGERES_RE.sub(f"<imageres>{WANTED_IMAGERES}</imageres>", text, count=1)
    elif _ROOT_CLOSE_RE.search(text):
        entry = _ENTRY.format(value=WANTED_IMAGERES)
        updated = _ROOT_CLOSE_RE.sub(lambda m: f"{entry}\n</advancedsettings>", text, count=1)
    else:
        # No root close tag: either not an advancedsettings document or
        # truncated. Guessing where the element belongs risks corrupting a
        # file we do not own, so do nothing and say why.
        log.warning("hostconfig: advancedsettings.xml has no </advancedsettings>, leaving it alone")
        return False

    if updated == text:
        return False

    handle = xbmcvfs.File(ADVANCEDSETTINGS, "w")
    try:
        if not handle.write(updated):
            log.warning(f"hostconfig: write to {ADVANCEDSETTINGS} reported failure")
            return False
    finally:
        handle.close()
    log.debug(f"hostconfig: set <imageres> to {WANTED_IMAGERES}")
    return True
