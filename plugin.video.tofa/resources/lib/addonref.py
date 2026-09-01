# -*- coding: utf-8 -*-
"""Our own `xbmcaddon.Addon` handle, resolved on first USE rather than on import.

Kodi deregisters an add-on before registering its replacement, and inside that
window `xbmcaddon.Addon()` raises

    RuntimeError: Unknown addon id 'plugin.video.tofa'

Ten modules used to take the handle at MODULE SCOPE, so an import landing in
that window took the whole script down and Kodi popped its own error
notification at the viewer. Seen on the cinema box updating 0.9.24 -> 0.9.25
(2026-09-01, 14:59:43.102): the outgoing service re-imported `fontinstall`
0.7s before Kodi unpacked the new zip. Nothing was left broken -- the
replacement service started 2.6s later and the add-on read enabled and
unbroken -- but the toast reached the television, and it did not reproduce on
the other two boxes, which is what a one-frame race looks like.

Deferring the lookup does not make it impossible, it makes it very unlikely:
first use is somewhere inside a running screen rather than at the top of every
import chain, and the whole window is under a second.

`ADDON` is a PROXY rather than a `get_addon()` function on purpose. Some
twenty call sites across the windows read `kodigui.ADDON.getAddonInfo("path")`
and its siblings; a proxy leaves every one of them untouched, where an
accessor would have meant editing them all to prove a one-line point.

The handle is cached only on SUCCESS, so a call that does land in the window
raises there and the next one retries. Caching the failure would turn a
one-frame race into a dead interpreter.

What is NOT here: anything derivable from `addon.xml` without asking Kodi at
all. The name and the id are read by `branding.py`, which parses the file
directly and therefore cannot fail this way in the first place.
"""
from __future__ import annotations

import xbmcaddon

_addon = None


def addon():
    """Our Addon handle.

    Raises RuntimeError while Kodi is swapping the add-on out, which is the
    same thing the module-level lookups used to do -- only now at a moment
    with no importers behind it.
    """
    global _addon
    if _addon is None:
        _addon = xbmcaddon.Addon()
    return _addon


class _LazyAddon:
    """Forwards every attribute to the real Addon, resolved on first touch."""

    def __getattr__(self, name):
        return getattr(addon(), name)


#: Drop-in for a module-level `ADDON = xbmcaddon.Addon()`.
ADDON = _LazyAddon()


def localize(string_id: int) -> str:
    """Drop-in for a module-level `_ = ADDON.getLocalizedString`."""
    return addon().getLocalizedString(string_id)
