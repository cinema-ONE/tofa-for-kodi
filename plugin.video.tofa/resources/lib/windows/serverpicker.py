# -*- coding: utf-8 -*-
"""The "Pick where to watch from." screen, behind Settings > Account >
Switch Server.

This used to borrow PickerDialog, the same glass panel Sort/Filter/Quality
use. The real Apple TV app gives the choice its own full page instead (build
17), and it is right to: every other picker changes how one screen behaves,
while this one changes where the entire library comes from. The screen also
has room to show WHICH server each card is, by id -- a two-server household
with two servers called "tofa" cannot tell them apart from the name alone,
which is exactly the case this client was built against.

Layout and measurements live in skin/static/script-tofa-serverpicker.xml.
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from .. import addonref
from ..skin import icon_glyphs

_ = addonref.localize  # lazy, see addonref.py

#: How much of a server id fits on one card line, in characters. A mono font
#: is the only reason this can be counted rather than measured -- textmetrics
#: knows Inter Tight and nothing else.
#:
#: MEASURED, not derived. The arithmetic said 33: a 321-unit line in a 16px
#: Roboto Mono, whose advance is 0.6em, is 321 / 9.6 cells. On screen a cell
#: is 9.84, Kodi clipped the last one, and appended its own "..." to a string
#: that had already been ellipsised -- "…e22-8e364313...", which reads as a
#: bug in this function. 31 leaves a cell of headroom.
ID_MAX_CHARS = 31


def middle_ellipsis(text: str, max_chars: int = ID_MAX_CHARS) -> str:
    """A 36-character uuid, shortened from the MIDDLE.

    Both ends of a server id carry information -- the app shows
    "7d2a19c4-5e83-4...60-2c1ab84de905" -- and a tail-truncated uuid would
    make two servers created in the same minute look identical."""
    if len(text) <= max_chars:
        return text
    keep = max_chars - 1                       # the ellipsis takes one cell
    head = keep - keep // 2
    return text[:head] + "…" + text[len(text) - keep // 2:]


class ServerPickerDialog(kodigui.BaseDialog):
    xmlFile = "script-tofa-serverpicker.xml"
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    LIST_ID = 700
    BACK_ID = 720

    def __init__(self, *args, **kwargs):
        # Each server: the /servers item dict, as the cloud returns it.
        self._servers = kwargs.pop("servers", [])
        # Which one this device is on now, or None when there is no such
        # server: it may be offline and filtered out before we get here, and
        # during PAIRING there is no current server at all. Either way no
        # card gets the CURRENT badge, which is the truth in both cases.
        self._current_idx = kwargs.pop("current_idx", None)
        # The eyebrow over the headline. "SWITCH SERVER" is only right when
        # there is something to switch FROM; pairing asks the same question
        # of a device that has never had a server, and says so.
        self._eyebrow = kwargs.pop("eyebrow", None)
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self._list = None
        # Read by signin.interactive_switch_server after open() returns.
        self.picked_idx: int | None = None
        self.canceled = False

    def onFirstInit(self):
        # A dialog gets its own property store; MainWindow's is not
        # inherited. The accent IS the account's here (unlike the profile
        # gate, where no profile has been chosen yet).
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("eyebrow", (self._eyebrow or _(31116)).upper())
        self.setProperty("heading", _(31117))
        self.setProperty("back_label", _(31118))
        self.setProperty("back_glyph", chr(icon_glyphs.CHEVRON_LEFT))
        self._build_list()
        self.setFocusId(self.LIST_ID)
        self._focus_current_server()

    def _build_list(self):
        lst = kodigui.ManagedControlList(self, self.LIST_ID,
                                         max(1, len(self._servers)))
        items = []
        for i, server in enumerate(self._servers):
            name = server.get("name") or ""
            mli = kodigui.ManagedListItem(label=name)
            mli.setProperty("name", name)
            mli.setProperty("server_id", middle_ellipsis(server.get("id") or ""))
            mli.setProperty("icon_glyph", chr(icon_glyphs.SERVER))
            mli.setProperty("current_label",
                            _(31054).upper() if i == self._current_idx else "")
            items.append(mli)
        lst.reset()
        lst.addItems(items)
        self._list = lst

    def _focus_current_server(self):
        """Open ON the server this device is already using, the same rule as
        the profile gate: coming back to where you were should not depend on
        counting across the row."""
        if self._current_idx is None or not self._list:
            return
        try:
            self._list.setSelectedItemByPos(self._current_idx)
        except Exception:  # noqa: BLE001 - never block the picker
            pass

    def onClick(self, controlID):
        if controlID == self.BACK_ID:
            self.canceled = True
            self.doClose()
            return
        if controlID != self.LIST_ID:
            return
        idx = self._list.getSelectedPosition()
        if idx < 0:
            return
        # Picking the server you are already on is reported as a pick, not
        # swallowed here: the caller compares ids and treats it as "nothing
        # changed", which is the same answer with one fewer place to keep it.
        self.picked_idx = idx
        self.doClose()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.canceled = True
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)
