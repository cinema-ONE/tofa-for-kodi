"""Stops the host skin's own seek bar drawing over tofa's player.

tofa's player is a `WindowXMLDialog` sitting on top of Kodi's fullscreen
video, and it draws its own transport and scrubber. Kodi's skin draws one
too (`DialogSeekBar`), and the two land on screen together: ours at the
bottom, the skin's sliding in over it. Only one of them is ours to style.

There is no API for this. Everything else was tried and measured first:

  * `Dialog.Close(seekbar, true)` -- closes it, and the very next seek
    reopens it. plex-for-kodi reached the same conclusion and left the
    call commented out in their source with "Doesn't work :)".
  * Re-showing our own dialog to out-rank it -- Kodi's OSD dialogs sit at
    `DepthOSD`, above add-on dialogs, so raising ours changes nothing.
  * Waiting it out -- `Player.HasPerformedSeek(3)` keeps it up for three
    seconds after EVERY seek, including the ones we make ourselves via
    `seekTime()` for resume and for skip-intro.
  * A Kodi setting -- there is none. The visibility rules live entirely
    in the skin's own XML.

What plex-for-kodi does at RUNTIME is SYNCHRONISE: they poll
`Window.IsActive(seekbar)` and show their own OSD whenever Kodi's appears,
so the two agree. That works for a skin-shaped OSD; it does not work for a
player that is meant to look like tofa's Apple TV app.

And what they do about it properly is exactly this. Their companion skin
skin.plextuary ships a modified DialogSeekBar.xml whose visibility rule
reads, in part:

    [Skin.HasSetting(OSDBackgroundPause)
     + String.IsEmpty(Window(10000).Property(script.plex.is_active))
     + Player.Paused + !Player.Caching]

Same idea, same Window(10000), same shape of property. They go further
than we do -- they also delete `Player.HasPerformedSeek(3)` from the rule
outright, for all playback by anyone. This patch is deliberately more
conservative: it only ANDs a condition on top, so the skin's own logic is
left intact and the change is confined to the window where our player is
open. The two compose without conflict if the user runs Plextuary.

So this edits the skin, the same way fontinstall.py does, and under the
same rules: consent FIRST, one namespaced marker so it is idempotent and
removable, and never a hand-edit of anything else in the file. The edit is
a single extra top-level `<visible>` condition on the seek bar's window,
which Kodi ANDs with the skin's own:

    <visible>String.IsEmpty(Window(10000).Property(plugin.video.tofa.player_open))</visible>

That property is set by windows/player.py for exactly as long as our player
is open, so the host skin's seek bar behaves normally for every other
add-on and for Kodi's own playback -- it is suppressed only while tofa is
the thing playing. Removing the patch (or switching skin) restores it.

Same read-only-squashfs handling as the fonts: CoreELEC ships skin.estuary
on a read-only `/`, so the skin is copied into `special://home/addons/`
before it is touched.
"""
from __future__ import annotations

import os
import re

import xbmc
import xbmcaddon
import xbmcvfs

from . import log
from .fontinstall import ensure_writable_skin_path

# Bump if the injected condition changes. As with the fonts, idempotency
# tests only for the marker, so a number must never be reused.
SEEKBAR_PATCH_VERSION = 1
_VERSION_MARKER = f"<!-- tofa-seekbar-v{SEEKBAR_PATCH_VERSION} -->"

# The Window.Property windows/player.py sets on Window(10000) for the
# lifetime of the player dialog. Keep in step with player._REENTRANCY_PROPERTY.
PLAYER_OPEN_PROPERTY = "plugin.video.tofa.player_open"

_CONDITION = f"<visible>String.IsEmpty(Window(10000).Property({PLAYER_OPEN_PROPERTY}))</visible>"

# Matches a block from ANY version of this patch, so a version bump (and
# remove_patch) replaces cleanly instead of stacking conditions. `\r` is
# allowed at both line ends because a skin's XML may well be CRLF -- without
# it the removal silently matches nothing and a bump stacks a second
# condition instead of replacing the first.
_OLD_BLOCK_RE = re.compile(
    r"[ \t]*<!-- tofa-seekbar-v\d+ -->[ \t\r]*\n[ \t]*<visible>[^\r\n]*plugin\.video\.tofa\.player_open[^\r\n]*</visible>[ \t\r]*\n",
    re.IGNORECASE,
)

# Kodi's own seek bar window. A skin that renames the file is not patched
# (and not broken) -- seekbar_patch_needed() simply answers False.
_SEEKBAR_XML = "DialogSeekBar.xml"

_WINDOW_OPEN_RE = re.compile(r"<window(?:\s[^>]*)?>")

"""Remembers a SEEKBAR_PATCH_VERSION the user said no to, so declining
costs one dialog rather than one per player open."""
DECLINED_SETTING = "seekbar_declined_version"


def _find_seekbar_xml_files(skin_path: str) -> list[str]:
    """Same reasoning as fontinstall._find_font_xml_files: the file's
    folder is a per-skin convention (`xml/` on modern skins, a resolution
    folder on older ones) and a skin may ship more than one."""
    found = []
    for root, _dirs, files in os.walk(skin_path):
        if _SEEKBAR_XML in files:
            found.append(os.path.join(root, _SEEKBAR_XML))
    return found


def _already_patched(xml_files: list[str]) -> bool:
    for path in xml_files:
        try:
            with open(path, encoding="utf-8") as f:
                if _VERSION_MARKER not in f.read():
                    return False
        except OSError:
            return False
    return True


def _patch_file(path: str) -> bool:
    """Insert the condition directly after the opening `<window>` tag.

    Kodi ANDs every top-level `<visible>` on a window, so appending one
    can only ever make the seek bar *less* visible -- it cannot turn it on
    in a state the skin meant to hide it.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    text = _OLD_BLOCK_RE.sub("", text)

    match = _WINDOW_OPEN_RE.search(text)
    if not match:
        log.warning(f"seekbarpatch: no <window> element in {path}, skipping")
        return False

    block = f"\n\t{_VERSION_MARKER}\n\t{_CONDITION}"
    text = text[:match.end()] + block + text[match.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    log.debug(f"seekbarpatch: patched {path} (v{SEEKBAR_PATCH_VERSION})")
    return True


def _active_skin() -> tuple[str, str]:
    skin_id = xbmc.getSkinDir()
    return skin_id, xbmcvfs.translatePath(xbmcaddon.Addon(skin_id).getAddonInfo("path"))


def patch_needed() -> bool:
    """True when the active skin's seek bar is not suppressed yet.

    Answers False on any failure to inspect the skin: not finding the file
    is not a licence to start writing into it.
    """
    try:
        skin_id, current_path = _active_skin()
        xml_files = _find_seekbar_xml_files(current_path)
        if not xml_files:
            log.debug(f"seekbarpatch: no {_SEEKBAR_XML} under active skin {skin_id}, nothing to suppress")
            return False
        return not _already_patched(xml_files)
    except Exception as exc:
        log.warning(f"seekbarpatch: could not inspect the active skin: {exc}")
        return False


def apply_patch() -> bool:
    """Patch the active skin. Returns True if anything was written.

    Consent is the CALLER's job (hostsetup.py) and must already have been
    given -- this function asks nothing and writes immediately.
    """
    try:
        skin_id, current_path = _active_skin()
        if not _find_seekbar_xml_files(current_path):
            return False

        writable_path = ensure_writable_skin_path(skin_id, current_path)
        xml_files = _find_seekbar_xml_files(writable_path)

        return any([_patch_file(path) for path in xml_files])
    except Exception as exc:
        log.warning(f"seekbarpatch: failed, leaving the skin's seek bar in place: {exc}")
        return False


def remove_patch() -> bool:
    """Undo the patch wherever it is found, at any version. Returns True if
    anything was written. The route back for anyone who wants their skin's
    seek bar during tofa playback after all."""
    try:
        skin_id, current_path = _active_skin()
        writable_path = ensure_writable_skin_path(skin_id, current_path)

        changed = False
        for path in _find_seekbar_xml_files(writable_path):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            stripped = _OLD_BLOCK_RE.sub("", text)
            if stripped != text:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(stripped)
                log.debug(f"seekbarpatch: removed the patch from {path}")
                changed = True
        return changed
    except Exception as exc:
        log.warning(f"seekbarpatch: could not remove the patch: {exc}")
        return False
