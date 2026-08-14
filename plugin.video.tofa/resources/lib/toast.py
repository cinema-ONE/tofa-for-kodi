# -*- coding: utf-8 -*-
"""8.9's transient toast, in our own skin instead of Kodi's.

`xbmcgui.Dialog().notification()` draws in the HOST skin, which is the same
objection 9.2 raises against a modal for a wrong PIN: it is not our surface,
it does not look like the app, and no animation we write can reach it (so
8.9's "all toasts fade <300ms" is unreachable through it by construction).

    from .. import toast
    toast.show("Could not request this title")

WHERE IT DRAWS. The message goes on window 10000 and each window renders it
from its own XML via skin.fragments.toast(). Window properties are the only
store a background service and a window can both reach, and the service is
where two of these messages come from. Nothing here opens a dialog: a
self-raised dialog steals focus from whatever the viewer was using, which is
why the player's own toasts have always been controls inside its window
rather than windows of their own.

ONLY WINDOWS THAT CARRY THE FRAGMENT CAN SHOW IT. Today that is the player
and Detail. A message raised while neither is up sets a property nobody
draws, so callers in that position keep using Kodi's notification on
purpose -- see `notify_or_host`. Three of them are correct to do so: sign-in
finishing (its window is closing), switch_profile failing before any dialog
exists, and kodigui's "Possibly broken XML file", which fires exactly when
our own skin failed to load.
"""
from __future__ import annotations

import threading

import xbmc
import xbmcgui

#: Must match skin.fragments.TOAST_PROPERTY; test_toast_surface.py asserts it.
PROPERTY = "tofa_toast"

#: Long enough to read a sentence, short enough not to sit over the film.
#: Kodi's own notification defaults to 5s; this is deliberately close, so
#: replacing one does not change how long the viewer has to read it.
DEFAULT_SECONDS = 4.5

_STORE = 10000


def show(message: str, seconds: float = DEFAULT_SECONDS) -> None:
    """Put `message` in the toast for `seconds`. Safe from any thread and
    any process."""
    if not message:
        return
    xbmcgui.Window(_STORE).setProperty(PROPERTY, message)
    threading.Thread(target=_expire, args=(message, seconds), daemon=True).start()


def clear() -> None:
    xbmcgui.Window(_STORE).clearProperty(PROPERTY)


def _expire(message: str, seconds: float) -> None:
    """Clear the toast, but only if it is still the one we set.

    A second toast raised during the first one's lifetime would otherwise be
    cut short by the first one's timer -- which is exactly the case that
    matters here, since these are error messages and errors arrive in
    bursts."""
    xbmc.sleep(int(seconds * 1000))
    win = xbmcgui.Window(_STORE)
    if win.getProperty(PROPERTY) == message:
        win.clearProperty(PROPERTY)


def notify_or_host(message: str, icon: str, header: str,
                   seconds: float = DEFAULT_SECONDS) -> None:
    """Our toast when one of our windows is up to draw it, Kodi's own
    notification when none is.

    The check is `Window(10000).Property(tofa_window)` / `tofa_dialog`,
    which XMLBase.onInit sets to the class name and doClose clears -- the
    same signal kodictl asserts on, and the only one that works, since Kodi
    reports System.CurrentWindow as "System" for every Python WindowXML."""
    if _ours_is_up():
        show(message, seconds)
    else:
        xbmcgui.Dialog().notification(header, message, icon)


def _ours_is_up() -> bool:
    win = xbmcgui.Window(_STORE)
    return bool(win.getProperty("tofa_window") or win.getProperty("tofa_dialog"))
