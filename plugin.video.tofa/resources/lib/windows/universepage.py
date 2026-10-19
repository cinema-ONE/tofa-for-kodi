# -*- coding: utf-8 -*-
"""A universe's page (server 0.12.0, Apple TV app 2.1.0).

The universe over its up-next title's backdrop, a Continue pill and a Story
or Release order pill, then a strip of every member's poster. Focusing a
poster turns the hero into that title, with Play and Details.

Continue and Play open the title's page, as the card menu's Play does: Detail
owns the edition, resume and request choices. The app's chapter grid and its
Request missing pill are not here yet.
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from .. import http, regional, textmetrics, universe
from ..skin import tokens as T

STORY, RELEASE = "story", "release"


def play_label(u: dict) -> str:
    """"Continue · 6 The Incredible Hulk", or the next show's episode."""
    member = u["next_up"]
    if member is None:
        return ""
    code = universe.episode_code(member)
    title = "{0} {1}".format(member["item"].get("title"), code) if code else member["title"]
    return "Continue · {0} {1}".format(member["position"], title)


def summary(u: dict, order: str) -> str:
    """The app's line under the name; release order says so."""
    line = universe.summary(u)
    return line if order == STORY else line.replace(" in story order", " in release order", 1)


def member_meta(member: dict, next_key) -> str:
    """"2008 · Up next" under a focused poster's title."""
    year = member["item"].get("year") or (member["item"].get("release_date") or "")[:4]
    return " · ".join(str(p) for p in (year, universe.member_status(member, next_key)) if p)


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

    def __init__(self, *args, **kwargs):
        self.universe = kwargs.pop("universe", None) or {}
        self.client = kwargs.pop("client", None)
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.order = STORY
        self.strip: kodigui.ManagedControlList | None = None
        self._shown_key = None
        self._return_focus = None

    def onFirstInit(self):
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("u_details_label", "Details")
        self.strip = kodigui.ManagedControlList(self, self.STRIP_ID, 30)
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
            self._render(keep=True)
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
        self._fill_strip(keep)
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
        back = action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK)
        if back and self.getProperty("u_state") and self.getFocusId() != self.STRIP_ID:
            # Back from a title's pills returns to the universe, then closes.
            self._show_universe()
            self.setFocusId(self.CONTINUE_ID if self.getProperty("u_play_label") else self.ORDER_ID)
            return
        kodigui.ControlledWindow.onAction(self, action)
        if self.getFocusId() == self.STRIP_ID:
            self._sync_member()

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
