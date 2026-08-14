"""What this add-on is called, read from the one place that defines it.

`addon.xml` is the definition. Kodi shows that name in its own surfaces --
the Program add-ons tile, the add-on manager, every `Dialog().notification`
header -- so a second copy in Python could never be more than a copy that
drifts. It had already drifted once: addon.xml said "tofa" while ABOUT's card
said "tofa for Kodi".

Two callers, and they need it at different TIMES, which is why this is a
module rather than a constant:

- at RUNTIME, `xbmcaddon.Addon().getAddonInfo("name")` is the direct route
  and every existing `ADDON_NAME` already uses it. `app_name()` exists for
  the callers that have no Addon handle -- notably the skin renderer, which
  `build.render_all()` can run entirely outside Kodi.
- at BUILD time, the renderer bakes the name into ABOUT's card. That is why
  addon.xml is in build._SOURCE_FILES: without it, renaming the add-on would
  leave the card showing the old name, because the content hash would not
  have moved. See project_skin_render_stale_hash for what that failure looks
  like.

Parsed rather than imported so it works in both worlds with no xbmc stubs.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

#: Last-resort value if addon.xml is unreadable. Never expected to be used;
#: a missing addon.xml means Kodi could not have loaded us in the first
#: place. Present so a rendering run cannot die on a name lookup.
_FALLBACK_NAME = "tofa for Kodi"

ADDON_XML = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "addon.xml"))

_cached: dict[str, str] = {}


def _addon_attr(attr: str, fallback: str) -> str:
    if attr not in _cached:
        try:
            _cached[attr] = ET.parse(ADDON_XML).getroot().attrib.get(attr) or fallback
        except (OSError, ET.ParseError):
            return fallback
    return _cached[attr]


def app_name() -> str:
    """The add-on's display name, e.g. "tofa for Kodi"."""
    return _addon_attr("name", _FALLBACK_NAME)


def app_version() -> str:
    """The add-on's version, e.g. "0.9.1"."""
    return _addon_attr("version", "0.0.0")
