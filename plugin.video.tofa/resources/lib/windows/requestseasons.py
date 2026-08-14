# -*- coding: utf-8 -*-
"""7.6's Request dialog: what exactly to ask the server to acquire.

Opened from the out-of-library detail page's Request pill (detail.py). For a
SHOW it lists the seasons; for a MOVIE it has no list at all and exists only
when there is a quality decision to make. Both shapes can carry the HD/4K
pills and the *arr quality-profile row.

Returns {"seasons": [1, 2, ...]|None, "is4k": bool|None,
"quality_profile_id": int|None} from ask(), or None when the viewer cancelled
or ticked nothing.
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from ..skin import icon_glyphs


class RequestSeasonsDialog(kodigui.BaseDialog):
    xmlFile = "script-tofa-requestseasons.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    LIST_ID = 100
    HD_ID = 110
    FOURK_ID = 111
    QUALITY_GROUP_ID = 112
    REQUEST_ID = 120
    CANCEL_ID = 121
    FOOTER_GROUP_ID = 122
    PROFILE_GROUP_ID = 130
    PROFILE_ID = 131
    PANEL_FILL_ID = 90
    PANEL_OUTLINE_ID = 91

    def __init__(self, *args, **kwargs):
        self._heading = kwargs.pop("heading", "")
        self._eyebrow = kwargs.pop("eyebrow", "Select Seasons")
        # [(season_number, label, detail, already_requested)]
        self._rows = kwargs.pop("rows", [])
        self._show_quality = kwargs.pop("show_quality", False)
        self._multi = kwargs.pop("multi", False)
        # [{"id": int, "name": str}] of the service this title routes to,
        # already filtered to "more than one, so there is a choice".
        self._profiles = kwargs.pop("profiles", [])
        self._profile_idx = kwargs.pop("profile_idx", 0)
        self.result = None
        self.canceled = False
        self._quality = "hd"
        self._checked: set[int] = set()
        self.season_list = None
        kodigui.BaseDialog.__init__(self, *args, **kwargs)

    @classmethod
    def ask(cls, *, title: str, seasons: list, is4k_capable: bool,
            media_type: str = "tv", can_request_4k: bool = True,
            requested: set | None = None, profiles: list | None = None,
            default_profile_id: int | None = None):
        """Build the dialog for this title and run it. None when nothing was
        chosen.

        SPECIALS ARE EXCLUDED. The server returns season 0 (37 episodes for
        Attack on Titan) but the real app lists only Seasons 1-4 and offers
        "Request 4 Seasons" -- specials are not what anyone means by "the
        show", and requesting them silently would be a surprise.
        """
        requested = requested or set()
        is_movie = media_type == "movie"
        rows = []
        for season in (() if is_movie else (seasons or [])):
            try:
                number = int(season.get("season_number"))
            except (TypeError, ValueError):
                continue
            if number == 0:
                continue
            episodes = season.get("episode_count")
            detail = ("{0} episodes".format(episodes)
                      if isinstance(episodes, int) and episodes else "")
            rows.append((number, "Season {0}".format(number), detail,
                         number in requested))
        if not rows and not is_movie:
            return None
        # 7.6 gates the pills on the TITLE being 4K-eligible; the viewer's own
        # permission gates them too, since offering a choice the server will
        # refuse is worse than not offering it.
        show_quality = bool(is4k_capable and can_request_4k)

        # One profile is not a choice, and neither is none: the server picks
        # its instance default in both cases.
        profiles = [p for p in (profiles or []) if p.get("id") is not None]
        offer_profiles = len(profiles) > 1
        profile_idx = 0
        if offer_profiles:
            for i, profile in enumerate(profiles):
                if profile.get("id") == default_profile_id:
                    profile_idx = i
                    break

        outstanding = [number for number, _l, _d, already in rows if not already]
        if not outstanding and not is_movie:
            return None         # every season is already on request
        # A MOVIE with nothing to decide goes straight through, the way the
        # real Apple TV app fires a movie request the moment Request is
        # pressed. A SHOW always opens the dialog, even with one season:
        # Adrian's call 2026-08-08, made against the macOS "tofa Desktop
        # Player", which shows the dialog for every show -- the Apple TV app
        # that the earlier skip-it rule was measured on is behind it.
        if is_movie and not show_quality and not offer_profiles:
            return {"seasons": None, "is4k": None, "quality_profile_id": None}

        dialog = cls.open(
            heading=title,
            eyebrow="Request" if is_movie else "Select Seasons",
            rows=rows,
            show_quality=show_quality,
            multi=len(rows) > 1,
            profiles=profiles if offer_profiles else [],
            profile_idx=profile_idx,
        )
        if not dialog or dialog.canceled:
            return None
        return dialog.result

    def onFirstInit(self):
        # A dialog has its own property store and inherits nothing from the
        # window underneath it.
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("accent_wash", theme.accent_with_alpha("42"))
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("heading", self._heading)
        self.setProperty("eyebrow", self._eyebrow)
        self.setProperty("show_quality", "1" if self._show_quality else "")
        self.setProperty("show_profile", "1" if self._profiles else "")
        # CHEVRONS_UP_DOWN, not chevron-right: this client's mark for "this
        # row opens a list of choices" (Browse's buttons, Detail's Options
        # and Edition pills all carry it).
        self.setProperty("profile_chevron", chr(icon_glyphs.CHEVRONS_UP_DOWN))
        self._apply_quality()
        self._apply_profile()
        self._build_rows()
        self._layout_panel()
        self._refresh_footer()
        self._wire_nav()
        # 7.6: initial focus is All Seasons, else the first season. A movie
        # has neither, so it starts on whatever decision it opened FOR.
        if self.season_list and self.season_list.size():
            target = self.LIST_ID
        elif self._show_quality:
            target = self.HD_ID
        elif self._profile_visible():
            target = self.PROFILE_ID
        else:
            target = self.REQUEST_ID
        self.setFocusId(target)

    # ------------------------------------------------------------------ rows

    def _build_rows(self):
        items = []
        # "All Seasons" only for a multi-season show -- 7.6, and a single
        # season would make it a second way to press the same thing.
        if self._multi:
            items.append(self._row(None, "All Seasons", "", False))
        for number, label, detail, already in self._rows:
            items.append(self._row(number, label, detail, already))
            if not already:
                # Everything starts ticked, like the app: the common ask is
                # the whole show, and an empty list would make the footer
                # dead on arrival.
                self._checked.add(number)
        self.season_list = kodigui.ManagedControlList(
            self, self.LIST_ID, max(1, len(items)))
        self.season_list.reset()
        if items:
            self.season_list.addItems(items)
            self.season_list.selectItem(0)
        self._refresh_checks()

    def _row(self, number, label, detail, already):
        mli = kodigui.ManagedListItem(label=label)
        mli.setProperty("detail", "Requested" if already else detail)
        # data_source carries the season number, or None for the All row.
        mli.dataSource = number
        mli.setProperty("already", "1" if already else "")
        return mli

    def _all_selectable(self) -> list:
        return [n for n, _l, _d, already in self._rows if not already]

    def _refresh_checks(self):
        if self.season_list is None:
            return
        every = self._all_selectable()
        for i in range(self.season_list.size()):
            li = self.season_list[i]
            if li is None:
                continue
            number = li.dataSource
            if number is None:
                on = bool(every) and all(n in self._checked for n in every)
            else:
                on = number in self._checked or li.getProperty("already")
            li.setProperty("check_glyph", chr(icon_glyphs.CHECK) if on else "")

    def _refresh_footer(self):
        # A movie asks for the whole title; there is no count to report.
        if not self._rows:
            self.setProperty("request_label", "Request")
            self.setProperty("request_text", theme.TEXT_PRIMARY)
            return
        count = len(self._checked)
        self.setProperty(
            "request_label",
            "Request {0} Season{1}".format(count, "" if count == 1 else "s")
            if count else "Request Seasons")
        # 7.6 dims the button rather than hiding it when nothing is ticked.
        self.setProperty(
            "request_text",
            theme.TEXT_PRIMARY if count else theme.TEXT_TERTIARY)

    def _apply_quality(self):
        self.setProperty("quality", self._quality)
        on_accent = theme.on_accent_text()
        self.setProperty("hd_text",
                         on_accent if self._quality == "hd" else theme.TEXT_SECONDARY)
        self.setProperty("fourk_text",
                         on_accent if self._quality == "4k" else theme.TEXT_SECONDARY)
        self.setProperty("show_profile", "1" if self._profile_visible() else "")

    def _profile_visible(self) -> bool:
        """The 4K tier always uses its own instance's default profile, so a 4K
        request has no profile to pick and the row goes away with it."""
        return bool(self._profiles) and self._quality != "4k"

    def _apply_profile(self):
        name = ""
        if self._profiles:
            name = self._profiles[self._profile_idx].get("name") or ""
        self.setProperty("profile_name", name)

    #: Panel geometry the XML is authored to, so Python can re-derive it.
    ROW_H = 76
    LIST_MAX_H = 440            # 7.6 caps the scrolling list
    LIST_Y_WITH_QUALITY = 214
    LIST_Y_NO_QUALITY = 154     # straight under the title, same 40 gap
    PROFILE_H = 68
    PROFILE_GAP = 20
    FOOTER_GAP = 26
    PANEL_BOTTOM_PAD = 40

    def _layout_panel(self):
        """Size the panel to what it actually contains.

        Kodi cannot do this itself, and a fixed height is wrong several times
        over: a 4K-ineligible title has no quality row, a movie has no season
        list at all, a one-season show has one row where the XML reserves
        enough for six, and the profile row is only there when the viewer may
        choose one. Each left the panel with a large dead area.
        """
        rows = self.season_list.size() if self.season_list else 0
        y = (self.LIST_Y_WITH_QUALITY if self._show_quality
             else self.LIST_Y_NO_QUALITY)
        list_h = min(self.LIST_MAX_H, rows * self.ROW_H)
        try:
            lst = self.getControl(self.LIST_ID)
            lst.setPosition(lst.getX(), y)
            lst.setHeight(list_h)
            if rows:
                y += list_h
            if self._profile_visible():
                y += self.PROFILE_GAP
                profile = self.getControl(self.PROFILE_GROUP_ID)
                profile.setPosition(profile.getX(), y)
                y += self.PROFILE_H
            footer_y = y + self.FOOTER_GAP
            footer = self.getControl(self.FOOTER_GROUP_ID)
            footer.setPosition(footer.getX(), footer_y)
            panel_h = footer_y + 68 + self.PANEL_BOTTOM_PAD
            for control_id in (self.PANEL_FILL_ID, self.PANEL_OUTLINE_ID):
                self.getControl(control_id).setHeight(panel_h)
        except Exception:
            pass

    def _wire_nav(self):
        """Chain up/down over the rows this dialog actually drew.

        The XML's own <onup>/<ondown> are the all-present case; a movie has no
        list and a 4K-ineligible title no quality pills, so a static chain
        walks focus into a control that is not there. Same runtime-rewire the
        detail page's action row uses.
        """
        levels = []
        if self._show_quality:
            levels.append((self.HD_ID, self.FOURK_ID))
        if self.season_list and self.season_list.size():
            levels.append((self.LIST_ID,))
        if self._profile_visible():
            levels.append((self.PROFILE_ID,))
        levels.append((self.REQUEST_ID, self.CANCEL_ID))
        try:
            for i, level in enumerate(levels):
                above = levels[i - 1] if i else level
                below = levels[i + 1] if i < len(levels) - 1 else level
                for control_id in level:
                    control = self.getControl(control_id)
                    control.controlUp(self.getControl(above[0]))
                    control.controlDown(self.getControl(below[0]))
        except Exception:
            pass

    # --------------------------------------------------------------- events

    def onClick(self, controlID):
        if controlID == self.LIST_ID:
            self._row_clicked()
        elif controlID == self.HD_ID:
            self._quality = "hd"
            self._apply_quality()
            self._layout_panel()
            self._wire_nav()
        elif controlID == self.FOURK_ID:
            self._quality = "4k"
            self._apply_quality()
            self._layout_panel()
            self._wire_nav()
        elif controlID == self.PROFILE_ID:
            self._profile_clicked()
        elif controlID == self.REQUEST_ID:
            if self._rows and not self._checked:
                return          # dimmed; 7.6 keeps it visible but inert
            profile_id = None
            if self._profile_visible():
                profile_id = self._profiles[self._profile_idx].get("id")
            self.result = {
                "seasons": sorted(self._checked) if self._rows else None,
                "is4k": (self._quality == "4k") if self._show_quality else None,
                "quality_profile_id": profile_id,
            }
            self.doClose()
        elif controlID == self.CANCEL_ID:
            self.canceled = True
            self.doClose()

    def _row_clicked(self):
        item = self.season_list.getSelectedItem()
        if item is None:
            return
        # An already-requested season is checked and inert (7.6) -- there is
        # nothing to ask for twice.
        if item.getProperty("already"):
            return
        number = item.dataSource
        if number is None:
            every = self._all_selectable()
            if all(n in self._checked for n in every):
                self._checked.clear()
            else:
                self._checked.update(every)
        elif number in self._checked:
            self._checked.discard(number)
        else:
            self._checked.add(number)
        self._refresh_checks()
        self._refresh_footer()

    def _profile_clicked(self):
        """Pick the *arr quality profile through the shared PickerDialog
        rather than a dropdown -- there is no such thing on a remote, and this
        is the same surface every other choice in this client opens."""
        from .picker import PickerDialog

        rows = [(profile.get("name") or "", i == self._profile_idx, None)
                for i, profile in enumerate(self._profiles)]
        dialog = PickerDialog.open(
            heading="Quality Profile",
            rows=rows,
            selected_idx=self._profile_idx,
        )
        if not dialog or dialog.canceled or dialog.picked_idx is None:
            return
        self._profile_idx = dialog.picked_idx
        self._apply_profile()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.canceled = True
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)
