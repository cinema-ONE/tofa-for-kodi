# -*- coding: utf-8 -*-
"""The top bar's list (NAV_LIST_ID, 3000): four text tabs and the Settings
gear, one ListItem each. Pairs with fragments.nav_bar(), whose layouts key
off each item's nav_idx and is_current properties, so the current tab keeps
its dot even after focus has gone down into the page.
"""
from __future__ import annotations

import xbmcgui

from ..skin import icon_glyphs

# (label, target, glyph) -- target is what _nav_clicked compares against a
# window's own `current_target` to find both "which tab am I" and "what to
# open on click".
#
# Settings used to be a "__settings__" sentinel here that opened Kodi's own
# ADDON.openSettings() dialog instead of a screen. It is an ordinary section
# now, like the other four.
NAV_TABS = (
    ("Home", "home_window", icon_glyphs.HOUSE),
    ("Browse", "browse_window", icon_glyphs.LAYOUT_GRID),
    ("Discover", "discover_window", icon_glyphs.SPARKLES),
    ("Search", "search_window", icon_glyphs.SEARCH),
    ("Settings", "settings_window", icon_glyphs.SETTINGS),
)


def build_nav(window, nav_list_id: int, current_target: str) -> None:
    """Populate `nav_list_id` with NAV_TABS, flagging + selecting whichever
    tab matches `current_target` (e.g. "home_window")."""
    nav_list = window.getControl(nav_list_id)
    current_index = 0
    for idx, (label, target, glyph) in enumerate(NAV_TABS):
        li = xbmcgui.ListItem(label=label)
        li.setProperty("icon_glyph", chr(glyph))
        # Each slot draws at its own measured spot (fragments._nav_slot).
        li.setProperty("nav_idx", str(idx))
        if target == current_target:
            li.setProperty("is_current", "1")
            current_index = idx
        nav_list.addItem(li)
    # Land the nav selection on the current tab rather than the first item,
    # so opening the window doesn't make Home look active by default.
    nav_list.selectItem(current_index)


def set_current(window, nav_list_id: int, current_target: str) -> None:
    """Update which tab's is_current property is set, without touching
    anything else -- for the merged single-window model (see
    windows/main.py:MainWindow), called every time the active section
    changes. build_nav() only runs once, at window construction; is_current
    needs to keep tracking whichever section is active after that, so the
    persistent pill (fragments.py:nav_bar()'s itemlayout/focusedlayout)
    follows the real current section instead of staying stuck on whichever
    one the window happened to start on."""
    nav_list = window.getControl(nav_list_id)
    for idx, (_label, target, _icon) in enumerate(NAV_TABS):
        li = nav_list.getListItem(idx)
        li.setProperty("is_current", "1" if target == current_target else "")


def resolve_nav_click(window, nav_list_id: int, current_target: str) -> str | None:
    """Return the clicked tab's target string, or None if the click should
    be a no-op (already on that tab). Callers still do their own
    window-opening + closeNow(), since that needs each window's own lazy
    sibling imports."""
    nav_list = window.getControl(nav_list_id)
    index = nav_list.getSelectedPosition()
    if index < 0 or index >= len(NAV_TABS):
        return None
    _label, target, _icon = NAV_TABS[index]
    if target == current_target:
        return None
    return target


def resolve_nav_focus(window, nav_list_id: int, current_target: str) -> str | None:
    """Like resolve_nav_click, but for focus-driven navigation (Left/Right
    while the nav list itself has focus, tvOS-style "load as soon as the tab
    is highlighted" instead of waiting for Select).

    Reads the list's CURRENT selected position directly, no +/-1 arithmetic
    -- Kodi's native list widget already applies Left/Right cursor movement
    before onAction is even invoked, regardless of whether the base class
    gets called, so adding an offset on top would double-apply the step.

    Settings used to be excluded here, because scrolling onto the tab would
    otherwise have popped Kodi's settings DIALOG open from an arrow key. Now
    that it is an ordinary section, it loads on focus like the rest."""
    nav_list = window.getControl(nav_list_id)
    index = nav_list.getSelectedPosition()
    if index < 0 or index >= len(NAV_TABS):
        return None
    _label, target, _icon = NAV_TABS[index]
    if target == current_target:
        return None
    return target
