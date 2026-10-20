# -*- coding: utf-8 -*-
"""A universe's page (server 0.12.0, Apple TV app 2.1.0).

The universe over its up-next title's backdrop, a Continue pill and a Story
or Release order pill, then a strip of every member's poster. Focusing a
poster turns the hero into that title, with Play and Details.

Down from the strip opens a grid of every member by chapter. Continue and
Play open the title's page, as the card menu's Play does: Detail owns the
edition, resume and request choices. Request N missing (the whole universe,
or one chapter) asks for what the library lacks, as tofa's apps do.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import xbmcgui

from . import kodigui, theme
from .. import http, regional, textmetrics, toast, universe
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

    CONTINUE_ID, ORDER_ID, DETAILS_ID, REQUEST_ID, STRIP_ID = 9101, 9102, 9103, 9104, 9200
    GROUP_IDS = {CONTINUE_ID: 9151, ORDER_ID: 9152, DETAILS_ID: 9153, REQUEST_ID: 9154}
    GRID_PANEL_IDS = tuple(9301 + 10 * i for i in range(T.UNI_GRID_BLOCKS))
    GRID_REQUEST_IDS = tuple(9302 + 10 * i for i in range(T.UNI_GRID_BLOCKS))

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
        self._services = (False, False)  # (films, shows) the server can request
        self._requested: set = set()    # member keys asked for on this page
        self._block_chapters: dict = {}  # grid block -> chapter index, for its Request
        self._requesting = False

    def onFirstInit(self):
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("u_details_label", "Details")
        self.strip = kodigui.ManagedControlList(self, self.STRIP_ID, 30)
        self.panels = [kodigui.ManagedControlList(self, pid, 21) for pid in self.GRID_PANEL_IDS]
        self._services = self._request_services()
        self._render()
        self.setFocusId(self.CONTINUE_ID if self.universe.get("next_up") else self.ORDER_ID)

    def onReInit(self):
        """Back from a title's page: watching it may have moved up next."""
        self._refresh()
        if self._return_focus:
            # Kodi refocuses the default control; go back to the one used.
            self.setFocusId(self._return_focus)

    def _refresh(self):
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
        count = len(self._missing())
        self.setProperty("u_request_label", "Request {0} missing".format(
            regional.number(count)) if count else "")
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
            self._layout_block_request(index, name)
            shown.append(self.GRID_PANEL_IDS[index])
        self._grid_shown = shown
        for index, panel_id in enumerate(shown):
            block = self.GRID_PANEL_IDS.index(panel_id)
            above = shown[index - 1] if index else None
            request = self.GRID_REQUEST_IDS[block]
            try:
                panel = self.getControl(panel_id)
                if index + 1 < len(shown):
                    panel.controlDown(self.getControl(shown[index + 1]))
                if self.getProperty("u_block{0}_request".format(block)):
                    button = self.getControl(request)
                    panel.controlUp(button)
                    button.controlDown(panel)
                    if above:
                        button.controlUp(self.getControl(above))
                elif above:
                    panel.controlUp(self.getControl(above))
            except RuntimeError:
                pass

    def _layout_block_request(self, index: int, name: str):
        """A chapter's "+ Request N", placed after its name as the app draws it."""
        chapter = next((i for i, (n, _s, _e) in enumerate(self.universe.get("chapters") or [])
                        if n == name), None) if name and self.order == STORY else None
        self._block_chapters[index] = chapter
        count = len(self._missing(chapter)) if chapter is not None else 0
        label = "+  Request {0}".format(regional.number(count)) if count else ""
        self.setProperty("u_block{0}_request".format(index), label)
        if not label:
            return
        # The eyebrow face is bold capitals at 17px; the metrics are 23px regular.
        x = int(textmetrics.text_width(name.upper()) * 17 / textmetrics.SIZE * 1.18) + 18
        width = int(textmetrics.text_width(label) * 22 / textmetrics.SIZE * 1.04) + 36
        try:
            self.getControl(self.GRID_REQUEST_IDS[index]).setPosition(x, 15)
            self.getControl(self.GRID_REQUEST_IDS[index]).setWidth(width)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Request missing
    # ------------------------------------------------------------------

    def _request_services(self) -> tuple:
        """(films, shows): whether the server has Radarr / Sonarr to ask."""
        try:
            status = (self.client.integrations_status() if self.client else None) or {}
        except http.ApiError as exc:
            kodigui.ERROR("universepage: integrations failed: {0}".format(exc))
            status = {}
        return status.get("radarr") is not None, status.get("sonarr") is not None

    def _missing(self, chapter=None) -> list:
        films, shows = self._services
        return universe.missing_rows(self.universe, chapter, films, shows,
                                     frozenset(self._requested))

    def _request_missing(self, chapter=None):
        """List what is missing, let the viewer untick, then ask for the rest."""
        if self._requesting:
            return
        rows = self._missing(chapter)
        if not rows:
            return
        listing, plan = self._request_listing(rows)
        if not listing:
            toast.show("Everything here is in your library or already requested")
            return
        from .requestseasons import RequestSeasonsDialog
        name = self.universe["chapters"][chapter][0] if chapter is not None else self.universe["name"]
        chosen = RequestSeasonsDialog.pick(heading=name, eyebrow="Request missing",
                                           rows=listing, noun="Title", all_label="All Titles")
        if not chosen:
            return
        self._requesting = True
        threading.Thread(target=self._send_requests, args=([plan[k] for k in chosen],),
                         daemon=True).start()

    def _request_listing(self, rows: list) -> tuple:
        """([(key, title, detail)], {key: request}) -- a series only with seasons to ask for."""
        series = [r for r in rows if r["kind"] == "series"]

        def detail(row):
            try:
                return row["key"], self.client.discovery_detail("tv", row["tmdb_id"]) or {}
            except http.ApiError as exc:
                kodigui.ERROR("universepage: seasons of {0}: {1}".format(row["title"], exc))
                return row["key"], None

        with ThreadPoolExecutor(max_workers=4) as pool:
            details = dict(pool.map(detail, series))
        listing, plan = [], {}
        for row in rows:
            year = str(row["year"]) if row["year"] else ""
            if row["kind"] == "film":
                listing.append((row["key"], row["title"], " · ".join(p for p in ("Film", year) if p)))
                plan[row["key"]] = (row, None, None)
                continue
            found = details.get(row["key"])
            seasons = universe.default_seasons(row, universe.requestable_seasons(found)) if found else []
            if not seasons:
                continue
            listing.append((row["key"], row["title"], " · ".join(
                p for p in ("Series", year, universe.seasons_label(seasons)) if p)))
            plan[row["key"]] = (row, seasons, found.get("tvdb_id"))
        return listing, plan

    def _send_requests(self, plan: list):
        """One request at a time, as the web app sends them; one sentence at the end."""
        results = []
        try:
            toast.show("Requesting {0} title{1}".format(len(plan), "" if len(plan) == 1 else "s"))
            for row, seasons, tvdb_id in plan:
                try:
                    if row["kind"] == "film":
                        self.client.create_request("movie", row["title"], row["tmdb_id"])
                    else:
                        self.client.create_request("tv", row["title"], row["tmdb_id"],
                                                   seasons=seasons, tvdb_id=tvdb_id)
                    self._requested.update(m["key"] for m in row["members"])
                    results.append((row["kind"], True))
                except http.ApiError as exc:
                    kodigui.ERROR("universepage: request {0}: {1}".format(row["title"], exc))
                    results.append((row["kind"], False))
            outcome = universe.request_outcome(results)
            if outcome:
                toast.show(outcome)
        finally:
            self._requesting = False
        universe.forget()
        focus = self.getFocusId()
        self._refresh()
        # A pill with nothing left to request goes; focus moves to its neighbour.
        if focus == self.REQUEST_ID and not self.getProperty("u_request_label"):
            self.setFocusId(self.ORDER_ID)
        elif focus in self.GRID_REQUEST_IDS and not self.getProperty(
                "u_block{0}_request".format(self.GRID_REQUEST_IDS.index(focus))):
            self.setFocusId(self.GRID_PANEL_IDS[self.GRID_REQUEST_IDS.index(focus)])

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
        pills = [(self.CONTINUE_ID, play, True)]
        if title_state:
            pills.append((self.DETAILS_ID, self.getProperty("u_details_label"), False))
        else:
            pills.append((self.ORDER_ID, self.getProperty("u_order_label"), True))
            pills.append((self.REQUEST_ID, self.getProperty("u_request_label"), True))
        for control_id, label, icon in pills:
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
            first_request = (self.GRID_REQUEST_IDS[self.GRID_PANEL_IDS.index(self._grid_shown[0])]
                             if self._grid_shown else None)
            if (action.getId() == xbmcgui.ACTION_MOVE_UP and focus == was == first_request):
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
        elif controlId == self.REQUEST_ID:
            self._request_missing()
        elif controlId in self.GRID_REQUEST_IDS:
            self._request_missing(self._block_chapters.get(self.GRID_REQUEST_IDS.index(controlId)))
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
