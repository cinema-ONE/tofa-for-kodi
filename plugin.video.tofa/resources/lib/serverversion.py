# -*- coding: utf-8 -*-
"""Refuse to pretend an old server is a current one.

Adrian's rule for this client is that we do NOT carry backward-compatibility
paths: the add-on targets the current server and says so. That is cheap to
build and honest to read, but it has one failure mode -- an older server
does not announce itself, it just returns less. Rows go missing, avatars
fall back to initials, badges vanish. Every one of those looks like a bug in
the client.

So this exists to turn "quietly wrong" into "told you once".

MIN_SERVER_VERSION is the oldest server every screen is correct against. It
is not the oldest that WORKS -- most of the add-on is fine further back --
so this warns rather than blocks. Blocking would be the wrong trade for
someone who cannot update their server tonight and just wants to watch
something.
"""
from __future__ import annotations

from typing import Optional, Tuple

import xbmcgui

from . import log

#: Bump this with the feature, in the same commit, or it is decoration.
#:
#: 0.9.29: the 44 pixel-art profile avatars (the six emoji-only presets are
#: gone), uploaded profile photos, and the split Recently Released Movies /
#: TV Shows home rows.
#:
#: 0.9.33: `client_render_embedded_vobsub_subtitles` -- an older server
#: ignores the flag and a DirectPlay file's embedded VobSub tracks stay
#: out of the subtitle panel, which reads as this client losing them.
#:
#: 0.9.34: NO feature, which makes this the exception to the rule above.
#: The vendored spec moved to 0.9.34, and the spec may lag the floor but
#: never lead it -- a newer spec means we hold a contract we do not claim
#: to support. 0.9.34's one client-facing addition, `audio_lane_mode` on
#: /stream/{id}/info, is OPT-IN: omitting it still advertises every audio
#: lane, measured against a live 0.9.34 server, so nothing here changed
#: behaviour. Adopt the parameter and this entry earns its keep; until
#: then it is bookkeeping, and honest to say so.
MIN_SERVER_VERSION: Tuple[int, int, int] = (0, 9, 35)

#: Warn once per KODI session, not once per add-on run. The add-on is
#: relaunched constantly -- from the Programs tile, from a profile switch,
#: from Back at the top level -- and a dialog on every one of those would be
#: nagging rather than informing. A window property on Kodi's home window
#: lives exactly as long as we want: it survives our process and dies with
#: Kodi. (Note this is the OPPOSITE of what stereoscopic.py needs, where a
#: marker dying with Kodi was the bug -- there it had to outlive a crash.)
_SESSION_WINDOW = 10000
_WARNED_PROPERTY = "tofa.server_version_warned"


def parse(version: Optional[str]) -> Optional[Tuple[int, ...]]:
    """`"0.9.29"` -> `(0, 9, 29)`. None when it is not a version at all.

    Tolerates a suffix (`"0.9.29-beta.2"`, `"0.9.29+build7"`) by reading
    only the leading dotted integers, and tolerates a short one (`"0.9"`).
    A server that answers something unparseable is treated as UNKNOWN rather
    than as old: refusing to guess is the whole point, and a spurious
    "update your server" is worse than silence.
    """
    if not version:
        return None
    head = str(version).strip().split("+")[0].split("-")[0]
    parts = []
    for piece in head.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) if parts else None


def is_supported(version: Optional[str]) -> bool:
    """False ONLY when we can read the version and it is genuinely older.

    Unknown counts as supported. See parse()."""
    found = parse(version)
    if found is None:
        return True
    # Compared as tuples, so (0, 9, 30) > (0, 9, 29) and (0, 10) > (0, 9, 29)
    # both come out right -- a plain string compare gets the second wrong.
    return found >= MIN_SERVER_VERSION


def format_version(version: Tuple[int, ...]) -> str:
    return ".".join(str(p) for p in version)


def warn_if_old(version: Optional[str], *, alert, localize) -> bool:
    """Show the one warning, if it is owed. Returns True if it was shown.

    `alert` and `localize` are passed in rather than imported: this module
    is pure enough to test without Kodi's dialog stack, and the one that
    matters is testable precisely because the decision is separable from
    the dialog."""
    if is_supported(version):
        return False
    window = xbmcgui.Window(_SESSION_WINDOW)
    if window.getProperty(_WARNED_PROPERTY):
        return False
    window.setProperty(_WARNED_PROPERTY, "1")
    log.warning(
        f"server {version} is older than the required "
        f"{format_version(MIN_SERVER_VERSION)}")
    alert(localize(31115),
          localize(31114).format(version or "?",
                                 format_version(MIN_SERVER_VERSION)),
          error=True)
    return True
