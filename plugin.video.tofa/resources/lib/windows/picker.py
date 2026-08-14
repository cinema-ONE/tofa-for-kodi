# -*- coding: utf-8 -*-
"""Custom Sort/Filter/Quality picker matching tofa's Apple TV app instead of
Kodi's native xbmcgui.Dialog().select() -- fixed-position glass panel, pill
rows, accent-colored focus/active states, Lucide check/arrow glyphs.

The check is LEADING, the same row grammar as the options panel, the request
dialog's season list and the real app's own track panels
(atv-reference/player-episode-audio-panel.png). It used to trail.

Two shapes share one XML/class:
  - single-section (Sort, Quality): pass rows=/selected_idx=; picking a row
    closes the dialog immediately, no Done button.
  - multi-section (Filter): pass sections=, a list of {"eyebrow", "rows",
    "selected_idx"} dicts; picks accumulate until Done (Back discards them).
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from ..skin import icon_glyphs


class PickerDialog(kodigui.BaseDialog):
    xmlFile = "script-tofa-picker.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    LIST_ID = 100
    SECTION_LIST_IDS = (101, 102)
    DONE_BUTTON_ID = 103

    def __init__(self, *args, **kwargs):
        self._heading = kwargs.pop("heading", "")
        self._hint = kwargs.pop("hint", "")
        # Each row: (label, active, order) with an OPTIONAL 4th, detail.
        # active = currently-applied choice; order = "asc"/"desc"/None (None
        # = no direction, e.g. Shuffle); detail = small right-aligned text,
        # e.g. the Genre picker's counts. Caller flips order on a reverse
        # toggle; this just renders it. See _build_rows_list on why the
        # detail column is gated rather than always present.
        self._rows = kwargs.pop("rows", [])
        self._selected_idx = kwargs.pop("selected_idx", 0)
        # Multi-section (Filter) mode: list of {"eyebrow", "rows",
        # "selected_idx"}. Always exactly len(SECTION_LIST_IDS) sections
        # (only Filter's own two: Watch Status, Year).
        self._sections = kwargs.pop("sections", None)
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.option_list = None
        self._section_lists: dict[int, kodigui.ManagedControlList] = {}
        self._current_idx: list[int] = [s["selected_idx"] for s in (self._sections or [])]
        # Read by the caller after open() returns. Single-section: one of
        # picked_idx/reselected/canceled. Multi-section: section_results
        # (only if Done was pressed) or canceled -- picks before a Back
        # are discarded, never reported.
        self.picked_idx: int | None = None
        self.reselected = False
        self.canceled = False
        self.section_results: list[int] | None = None

    def onFirstInit(self):
        # Dialog has its own property store -- doesn't inherit MainWindow's,
        # must be set here explicitly.
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("heading", self._heading)
        if self._sections is not None:
            self.setProperty("mode", "multi")
            for list_id, section in zip(self.SECTION_LIST_IDS, self._sections):
                self.setProperty("eyebrow_{0}".format(list_id), section.get("eyebrow") or "")
                lst = self._build_rows_list(list_id, section["rows"], section["selected_idx"])
                self._section_lists[list_id] = lst
            self.setFocusId(self.SECTION_LIST_IDS[0])
        else:
            self.setProperty("mode", "single")
            self.setProperty("hint", self._hint)
            self.setBoolProperty("has_hint", bool(self._hint))
            self.option_list = self._build_rows_list(self.LIST_ID, self._rows, self._selected_idx)
            self.setFocusId(self.LIST_ID)

    def _build_rows_list(self, list_id: int, rows, selected_idx: int) -> kodigui.ManagedControlList:
        lst = kodigui.ManagedControlList(self, list_id, max(1, len(rows)))
        items = []
        for row in rows:
            # Rows are (label, active, order) plus an OPTIONAL 4th element, a
            # right-hand detail column -- the Genre picker's per-genre counts.
            #
            # A detail column lived here before and was removed, for a reason
            # worth not repeating: it was unconditional, so it sat empty on
            # every caller that had no detail while still taking 250px off the
            # label, which is what truncated "Ultra-HD/HD-1080p". The column
            # is now GATED -- the XML carries two label variants, a full-width
            # one shown while ListItem.Property(detail) is empty and a
            # narrower one shown when it is not (skin/static/
            # script-tofa-picker.xml). So a caller that passes no detail gets
            # exactly the layout it had before, byte for byte, and only the
            # rows that earn the column pay for it.
            label, active, order = row[0], row[1], row[2]
            detail = row[3] if len(row) > 3 else ""
            mli = kodigui.ManagedListItem(label=label)
            mli.setProperty("detail", detail or "")
            mli.setProperty("check_glyph", chr(icon_glyphs.CHECK) if active else "")
            if active and order:
                arrow = icon_glyphs.ARROW_DOWN if order == "desc" else icon_glyphs.ARROW_UP
                mli.setProperty("direction_glyph", chr(arrow))
            else:
                mli.setProperty("direction_glyph", "")
            items.append(mli)
        lst.reset()
        lst.addItems(items)
        lst.selectItem(selected_idx)
        return lst

    def _refresh_section_checks(self, list_id: int, new_idx: int) -> None:
        lst = self._section_lists[list_id]
        for i in range(lst.size()):
            li = lst[i]
            if li:
                li.setProperty("check_glyph", chr(icon_glyphs.CHECK) if i == new_idx else "")

    def onClick(self, controlID):
        if self._sections is not None:
            if controlID == self.DONE_BUTTON_ID:
                self.section_results = list(self._current_idx)
                self.doClose()
                return
            if controlID in self._section_lists:
                idx = self._section_lists[controlID].getSelectedPosition()
                if idx < 0:
                    return
                slot = self.SECTION_LIST_IDS.index(controlID)
                self._current_idx[slot] = idx
                self._refresh_section_checks(controlID, idx)
            return
        if controlID != self.LIST_ID:
            return
        idx = self.option_list.getSelectedPosition()
        if idx < 0:
            return
        if idx == self._selected_idx:
            self.reselected = True
        else:
            self.picked_idx = idx
        self.doClose()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.canceled = True
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)
