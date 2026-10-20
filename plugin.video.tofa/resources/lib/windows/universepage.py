# -*- coding: utf-8 -*-
"""A universe's page (server 0.12.0, Apple TV app 2.1.0).

The universe over its up-next title's backdrop, a Continue pill and a Story
or Release order pill, then a strip of every member's poster. Focusing a
poster turns the hero into that title, with Play and Details.

Down from the strip opens a grid of every member by chapter. Continue and
Play open the title's page, as the card menu's Play does: Detail owns the
edition, resume and request choices. The app's Request missing is not here.
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from .. import http, regional, textmetrics, universe
from ..skin import icon_glyphs
from ..skin import tokens as T

STORY, RELEASE = "story", "release"


def play_label(u: dict) -> str:
    """"Continue · 6 The Incredible Hulk", "Continue · Star Trek S1 E1", or
    Play when nothing in the universe has been started yet, as tofa's apps word it."""
    member = u["next_up"]
    if member is None:
        return ""
    verb = "Continue" if member["started"] or u["watched_count"] else "Play"
    code = universe.episode_code(member)
    if code:
        return "{0} · {1} {2}".format(verb, member["item"].get("title"), code)
    return "{0} · {1} {2}".format(verb, member["position"], member["title"])


def summary(u: dict, order: str) -> str:
    """The app's line under the name; release order says so."""
    line = universe.summary(u)
    return line if order == STORY else line.replace(" in story order", " in release order", 1)


def member_meta(member: dict, next_key) -> str:
    """"2008 · Up next" under a focused poster's title."""
    year = member["item"].get("year") or (member["item"].get("release_date") or "")[:4]
    return " · ".join(str(p) for p in (year, universe.member_status(member, next_key)) if p)


def grid_status(member: dict, next_key) -> str:
    """A grid poster's status, its season first when it is one ("Season 1 · Watched")."""
    status = universe.member_status(member, next_key)
    season = member["item"].get("season_number")
    if season is None:
        return status
    name = (member["item"].get("season_name") or "").strip() or (
        "Specials" if season == 0 else "Season {0}".format(season))
    return "{0} · {1}".format(name, status)


def grid_blocks(u: dict, order: str) -> list:
    """(chapter name, members) per grid block: the chapters in story order,
    else the whole universe as one unnamed block."""
    members = universe.ordered(u, order)
    if order != STORY or not u.get("chapters"):
        return [("", members)]
    blocks = [(name, members[start:end + 1]) for name, start, end in u["chapters"]]
    covered = {m["key"] for _name, ms in blocks for m in ms}
    rest = [m for m in members if m["key"] not in covered]
    return blocks + ([("", rest)] if rest else [])


def two_lines(text: str) -> str:
    """Two lines of the body face, the second cut with an ellipsis, as the app does."""
    lines = textmetrics.wrap_lines(text or "", T.UNI_OVERVIEW_W, 2, 24)

    def wide(line: str) -> bool:
        return textmetrics.text_width(line) * 24 / textmetrics.SIZE > T.UNI_OVERVIEW_W * 0.97

    if len(lines) == 2 and wide(lines[1]):
        last = lines[1]
        while last and wide(last + "\u2026"):
            last = last[:-1]
        lines[1] = last.rstrip() + "\u2026"
    return "[CR]".join(lines)


def pill_width(label: str, icon: bool) -> int:
    """A pill's width for `label` in its 25px semibold face: the metrics are
    the 23px regular one, and semibold runs ~4% wider."""
    text = int(round(textmetrics.text_width(label) * 25 / textmetrics.SIZE * 1.04)) + 4
    return text + 2 * T.UNI_PILL_PAD + (T.UNI_PILL_ICON_W + T.UNI_PILL_ICON_GAP if icon else 0)


class UniverseWindow(kodigui.ControlledWindow):
    xmlFile = "script-tofa-universe.xml"
    dismissOnClose = True
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    CONTINUE_ID, ORDER_ID, DETAILS_ID, STRIP_ID = 9101, 9102, 9103, 9200
    GROUP_IDS = {CONTINUE_ID: 9151, ORDER_ID: 9152, DETAILS_ID: 9153}
    GRID_PANEL_IDS = tuple(9301 + 10 * i for i in range(T.UNI_GRID_BLOCKS))

    def __init__(self, *args, **kwargs):
        self.universe = kwargs.pop("universe", None) or {}
        self.client = kwargs.pop("client", None)
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.order = STORY
        self.strip: kodigui.ManagedControlList | None = None
        self._shown_key = None
        self._return_focus = None
        self.panels: list = []
        self._grid_shown: list = []
        self._grid_at = (None, None)    # (panel, row) before the last key
        self._was = None                # focus before the last key: onAction sees it after
        self._moved_to = None

    def onFirstInit(self):
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("u_details_label", "Details")
        self.strip = kodigui.ManagedControlList(self, self.STRIP_ID, 30)
        self.panels = [kodigui.ManagedControlList(self, pid, 21) for pid in self.GRID_PANEL_IDS]
        self._render()
        self.setFocusId(self.CONTINUE_ID if self.universe.get("next_up") else self.ORDER_ID)

    def onReInit(self):
        """Back from a title's page: watching it may have moved up next."""
        try:
            fresh = self.client.collection(self.universe["id"]) if self.client else None
        except http.ApiError as exc:
            kodigui.ERROR("universepage: refresh failed: {0}".format(exc))
            fresh = None
        if fresh and fresh.get("items"):
            self.universe = universe.build(fresh)
            key = self._focused_key()
            self._render(keep=True)
            if self.getProperty("u_grid"):
                self._select_in_grid(key)
        if self._return_focus:
            # Kodi refocuses the default control; go back to the one used.
            self.setFocusId(self._return_focus)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------

    def _render(self, keep: bool = False):
        u = self.universe
        self.setProperty("u_name", u.get("name") or "")
        self.setProperty("u_summary", summary(u, self.order))
        self.setProperty("u_overview", two_lines(u.get("overview")))
        self.setProperty("u_order_label", "Story order" if self.order == STORY else "Release order")
        self.setProperty("u_chapters", "1" if self.order == STORY and u.get("chapters") else "")
        self.setProperty("u_all_label", "ALL {0}".format(regional.number(len(u.get("members") or []))))
        self.setProperty("u_name_upper", (u.get("name") or "").upper())
        self._fill_strip(keep)
        self._fill_grid()
        if not keep or not self.getProperty("u_state"):
            self._show_universe()

    def _fill_strip(self, keep: bool):
        selected = self.strip.getSelectedItem() if keep else None
        keep_key = selected.dataSource["key"] if selected is not None else None
        next_key = (self.universe.get("next_up") or {}).get("key")
        starts = {start for _name, start, _end in self.universe.get("chapters") or ()}
        members = universe.ordered(self.universe, self.order)
        items, select = [], 0
        for index, member in enumerate(members):
            item = member["item"]
            poster = self.client.resolve_image_url(item.get("poster_path")) if self.client else ""
            mli = kodigui.ManagedListItem(label=member["title"], data_source=member, offscreen=True)
            mli.setArt({"poster": poster or ""})
            dim = member["state"] in ("missing", "upcoming")
            mli.setProperty("tint", "0xFF4D4D4D" if dim else "0xFFFFFFFF")
            mli.setProperty("up_next", "1" if member["key"] == next_key else "")
            if self.order == STORY and member["position"] - 1 in starts:
                mli.setProperty("chapter", member["chapter"] or "")
            if member["key"] == (keep_key or next_key):
                select = index
            items.append(mli)
        self.strip.reset()
        self.strip.addItems(items)
        self.strip.selectItem(select)

    def _fill_grid(self):
        """One block per chapter, sized to its rows; unused blocks hidden."""
        next_key = (self.universe.get("next_up") or {}).get("key")
        blocks = grid_blocks(self.universe, self.order)[:len(self.panels)]
        number = 0
        shown = []
        for index, panel in enumerate(self.panels):
            panel.reset()
            if index >= len(blocks):
                self.setProperty("u_block{0}".format(index), "")
                continue
            name, members = blocks[index]
            items = []
            for member in members:
                number += 1
                items.append(self._grid_item(member, number, next_key))
            panel.addItems(items)
            rows = max(1, (len(items) + T.UNI_GRID_COLS - 1) // T.UNI_GRID_COLS)
            try:
                self.getControl(self.GRID_PANEL_IDS[index] - 1).setHeight(
                    T.UNI_GRID_HEAD_H + rows * T.UNI_GRID_ROW_H)
                self.getControl(self.GRID_PANEL_IDS[index]).setHeight(rows * T.UNI_GRID_ROW_H)
            except RuntimeError:
                pass
            self.setProperty("u_block{0}".format(index), "1")
            self.setProperty("u_block{0}_name".format(index), name.upper())
            shown.append(self.GRID_PANEL_IDS[index])
        self._grid_shown = shown
        for above, below in zip(shown, shown[1:]):
            try:
                self.getControl(above).controlDown(self.getControl(below))
                self.getControl(below).controlUp(self.getControl(above))
            except RuntimeError:
                pass

    def _grid_item(self, member: dict, number: int, next_key) -> kodigui.ManagedListItem:
        item = member["item"]
        poster = self.client.resolve_image_url(item.get("poster_path")) if self.client else ""
        mli = kodigui.ManagedListItem(label=item.get("title") or member["title"],
                                      label2=grid_status(member, next_key),
                                      data_source=member, offscreen=True)
        mli.setArt({"poster": poster or ""})
        mli.setProperty("number", regional.number(number))
        dim = member["state"] in ("missing", "upcoming")
        mli.setProperty("tint", "0xFF4D4D4D" if dim else "0xFFFFFFFF")
        mark = (icon_glyphs.CHECK if member["watched"]
                else icon_glyphs.PLUS if member["state"] == "missing" else None)
        mli.setProperty("mark", chr(mark) if mark else "")
        return mli

    def _open_grid(self):
        """Down from the strip: the grid, on the poster the strip was on."""
        key = self._focused_key()
        self.setProperty("u_grid", "1")
        self._select_in_grid(key)

    def _close_grid(self):
        """Back, or Up from the grid's top row: the hero, on the same title."""
        key = self._focused_key()
        self.setProperty("u_grid", "")
        for index, item in enumerate(self.strip or []):
            if item.dataSource and item.dataSource["key"] == key:
                self.strip.selectItem(index)
                break
        self._focus(self.STRIP_ID)
        self._shown_key = None
        self._sync_member()

    def _select_in_grid(self, key):
        for pid, panel in zip(self.GRID_PANEL_IDS, self.panels):
            for index, item in enumerate(panel):
                if item.dataSource and item.dataSource["key"] == key:
                    panel.selectItem(index)
                    self._focus(pid)
                    self._grid_at = (pid, index // T.UNI_GRID_COLS)
                    return
        if self._grid_shown:
            self._focus(self._grid_shown[0])

    def _focused_key(self):
        """The key of the member focused in the grid, else in the strip."""
        focus = self.getFocusId()
        lists = dict(zip(self.GRID_PANEL_IDS, self.panels))
        lst = lists.get(focus) or self.strip
        item = lst.getSelectedItem() if lst is not None else None
        return item.dataSource["key"] if item is not None and item.dataSource else None

    def _show_universe(self):
        """The hero as the page opens: the universe, Continue and the order."""
        u = self.universe
        self.setProperty("u_state", "")
        self._shown_key = None
        hero = universe.hero_item(u)
        self._set_backdrop(hero.get("backdrop_path") or u.get("backdrop"))
        self.setProperty("u_play_label", play_label(u))
        self._layout_pills()

    def _show_member(self, member: dict):
        """The hero as a focused poster's title."""
        if member["key"] == self._shown_key:
            return
        self._shown_key = member["key"]
        u = self.universe
        item = member["item"]
        self.setProperty("u_state", "title")
        self.setProperty("u_position", "{0} of {1}".format(
            regional.number(member["position"]), regional.number(len(u["members"]))))
        self.setProperty("u_title", member["title"])
        self.setProperty("u_meta", member_meta(member, (u.get("next_up") or {}).get("key")))
        self.setProperty("u_title_overview", two_lines(item.get("overview")))
        self._set_backdrop(item.get("backdrop_path") or u.get("backdrop"))
        self.setProperty("u_play_label", "Play" if member["owned"] else "")
        self._layout_pills()

    def _set_backdrop(self, path):
        url = self.client.resolve_image_url(path) if self.client and path else ""
        self.setProperty("u_backdrop", url or "")

    def _layout_pills(self):
        """Kodi cannot size a button to its text: widths and x from the fonts."""
        title_state = bool(self.getProperty("u_state"))
        play = self.getProperty("u_play_label")
        x = T.UNI_LEFT
        second = (self.DETAILS_ID, self.getProperty("u_details_label"), False) if title_state \
            else (self.ORDER_ID, self.getProperty("u_order_label"), True)
        for control_id, label, icon in ((self.CONTINUE_ID, play, True), second):
            if not label:
                continue
            width = pill_width(label, icon)
            try:
                self.getControl(self.GROUP_IDS[control_id]).setPosition(x, T.UNI_PILL_Y)
                self.getControl(control_id).setWidth(width)
            except RuntimeError:
                pass
            x += width + T.UNI_PILL_GAP

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------

    def onAction(self, action):
        self._moved_to = None
        self._on_action(action, self._was)
        self._was = self._moved_to or self.getFocusId()

    def _focus(self, control_id: int):
        """setFocusId lands later; remember where focus is going now."""
        self.setFocusId(control_id)
        self._moved_to = control_id

    def _on_action(self, action, was):
        back = action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK)
        focus = self.getFocusId()
        if self.getProperty("u_grid"):
            if back:
                self._close_grid()
                return
            if focus in self.GRID_PANEL_IDS:
                at, top = (focus, self._grid_row(focus)), (self._grid_shown[:1] or [None])[0]
                was, self._grid_at = self._grid_at, at
                if action.getId() == xbmcgui.ACTION_MOVE_UP and at == was == (top, 0):
                    # Up that went nowhere from the first row: back to the hero.
                    self._close_grid()
                    return
            kodigui.ControlledWindow.onAction(self, action)
            return
        if action.getId() == xbmcgui.ACTION_MOVE_DOWN and focus == was == self.STRIP_ID:
            self._open_grid()
            return
        if back and self.getProperty("u_state") and self.getFocusId() != self.STRIP_ID:
            # Back from a title's pills returns to the universe, then closes.
            self._show_universe()
            self.setFocusId(self.CONTINUE_ID if self.getProperty("u_play_label") else self.ORDER_ID)
            return
        kodigui.ControlledWindow.onAction(self, action)
        if self.getFocusId() == self.STRIP_ID:
            self._sync_member()

    def _grid_row(self, panel_id) -> int:
        panel = dict(zip(self.GRID_PANEL_IDS, self.panels)).get(panel_id)
        try:
            return panel.getSelectedPosition() // T.UNI_GRID_COLS
        except Exception:
            return 0

    def onFocus(self, controlId):
        if controlId == self.STRIP_ID:
            self._sync_member()

    def _sync_member(self):
        item = self.strip.getSelectedItem() if self.strip is not None else None
        if item is not None and item.dataSource:
            self._show_member(item.dataSource)

    def onClick(self, controlId):
        if controlId == self.ORDER_ID:
            self.order = RELEASE if self.order == STORY else STORY
            self._render()
            self.setFocusId(self.ORDER_ID)
        elif controlId == self.CONTINUE_ID:
            member = self._focused_member() if self.getProperty("u_state") else self.universe.get("next_up")
            self._open(member)
        elif controlId in (self.DETAILS_ID, self.STRIP_ID):
            self._open(self._focused_member())
        elif controlId in self.GRID_PANEL_IDS:
            panel = dict(zip(self.GRID_PANEL_IDS, self.panels))[controlId]
            item = panel.getSelectedItem()
            self._open(item.dataSource if item is not None else None)

    def _focused_member(self):
        item = self.strip.getSelectedItem() if self.strip is not None else None
        return item.dataSource if item is not None else None

    def _open(self, member):
        if not member:
            return
        from .detail import DetailWindow
        self._return_focus = self.getFocusId()
        item = member["item"]
        if member["owned"] and item.get("local_media_id"):
            DetailWindow.open(media_id=str(item["local_media_id"]))
        elif item.get("tmdb_id") and item.get("type"):
            DetailWindow.open(discovery_id=str(item["tmdb_id"]), media_type=item["type"],
                              discovery_item=item)


def show(u: dict, client) -> None:
    """Open universe `u` (a universe.build() result)."""
    if not u:
        return
    w = UniverseWindow.open(universe=u, client=client)
    del w
