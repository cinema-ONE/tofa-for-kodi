# -*- coding: utf-8 -*-
"""Person / filmography window (TV-DESIGN 7.4).

Opened by clicking a face in the detail screen's Cast or Crew grid, which
was a dead end before this existed.

One source, split into two sections: the server's PersonPage (0.12.0),
by person id when the cast entry has one, else by name. Its credits cover
crew as well as cast and flag the owned ones with `local_media_id`.

The layout's one deliberate divergence (sticky section label instead of two
inline headings) is explained in the template header, not repeated here.
"""
from __future__ import annotations

from . import cards, focusmemory, kodigui, profile_select, theme
from .. import api, artcache, auth, http, regional
from ..api import MediaServerClient

IN_LIBRARY = "library"
NOT_IN_LIBRARY = "discover"


def _year(item: dict) -> str:
    year = item.get("year")
    if year:
        return str(year)
    date = item.get("release_date") or item.get("air_date") or item.get("theatrical_release_date")
    if date and len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    return ""


def _sort_title(title: str) -> str:
    low = title.lower()
    return low[4:] if low.startswith("the ") else low


def _credits_line(items: list) -> str:
    """ "41 credits from 1994 to 2026", over both halves."""
    n = len(items)
    line = "1 credit" if n == 1 else "{0} credits".format(regional.number(n))
    years = sorted(int(y) for y in (_year(it) for it in items) if y.isdigit())
    if years:
        line += (" in {0}".format(years[0]) if years[0] == years[-1]
                 else " from {0} to {1}".format(years[0], years[-1]))
    return line


def _titles_phrase(n: int) -> str:
    return "1 title" if n == 1 else "{0} titles".format(regional.number(n))


def split_credits(credits) -> tuple[list, list]:
    """(owned, not owned). An owned credit gets `id` = its local_media_id,
    so it opens and badges like a library card."""
    owned, discover = [], []
    for it in credits or []:
        if it.get("in_library") and it.get("local_media_id"):
            owned.append(dict(it, id=it["local_media_id"]))
        else:
            discover.append(it)
    return owned, discover


class PersonWindow(focusmemory.FocusMemory, kodigui.ControlledWindow):
    xmlFile = "script-tofa-person.xml"
    # Same as DetailWindow/MainWindow: actually remove the native Kodi window
    # on a real Back, instead of leaving it for GC. Without it a pushed
    # window lingers behind whatever the user backs out to.
    dismissOnClose = True
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    GRID_ID = 8000
    SECTION_LABEL_ID = 8010
    PILL_ID = 8020          # Filmography
    FILM_LIST_ID = 8030     # the Filmography panel's rows

    def __init__(self, *args, **kwargs):
        self.person_name = kwargs.pop("name", "") or ""
        self.person_id = kwargs.pop("person_id", "") or ""
        # From the cast entry that opened this page: who they played there.
        self.person_role = kwargs.pop("role", "") or ""
        self.from_title = kwargs.pop("title", "") or ""
        self.person_photo = kwargs.pop("photo", "") or ""
        # The caller (detail.py) already holds an authenticated client;
        # reusing it keeps this window from re-running the profile gate,
        # which would pop a dialog on top of an already-signed-in session.
        self.client = kwargs.pop("client", None)
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.grid: kodigui.ManagedControlList | None = None
        # Index of the first not-in-library item, i.e. the section boundary.
        # None means there is no second section at all.
        self._boundary: int | None = None
        self._counts = {IN_LIBRARY: 0, NOT_IN_LIBRARY: 0}
        self._preferences: dict | None = None
        self._section_shown: str | None = None
        self.film_list: kodigui.ManagedControlList | None = None
        self._film_rows: list = []

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def onFirstInit(self):
        # Window.Property is per-window; without this block every textcolor
        # bound to a tier resolves empty and the labels render invisible.
        # Same preamble every window class in this package carries.
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("accent_wash_focus", theme.accent_with_alpha("42"))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)

        self.setProperty("person_name", self.person_name)
        self.setProperty("person_photo", self.person_photo)
        self.setProperty("person_initials", "".join(w[0] for w in self.person_name.split()[:2]).upper())
        role = self.person_role
        self.setProperty("person_role", "{0} in {1}".format(role, self.from_title)
                         if role and self.from_title else role)
        self.film_list = kodigui.ManagedControlList(self, self.FILM_LIST_ID, 12)
        # Capacity, not the item count: ManagedControlList's third arg is
        # max_view_index, and passing the real count leaves every row but the
        # last blank (see cardoptions.py, which hit exactly that).
        self.grid = kodigui.ManagedControlList(self, self.GRID_ID, 60)

        self._load()

    def _get_client(self) -> MediaServerClient | None:
        """Same construction as detail.py's, for the case where this window
        is reached without one being handed in."""
        if self.client and not self.client.profile_token_expired():
            return self.client
        try:
            session = http.new_session()
            tok = auth.ensure_fresh(session)
            tok = profile_select.ensure_profile_selected(session, tok)
            self.client = api.client_for(session, tok)
        except (auth.NotSignedIn, profile_select.ProfileCanceled, http.ApiError):
            self.client = None
        return self.client

    def _set_state(self, state: str, title: str, message: str) -> None:
        """Drive 9.7's shared scaffold. `state` is "" (content), "empty" or
        "error"; the template has one block per flavour and both read these
        same two strings, so a new thing to say is a call, not more XML."""
        self.setProperty("person_state", state)
        self.setProperty("empty_title", title)
        self.setProperty("empty_message", message)

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------

    def _load(self):
        client = self._get_client()
        if client is None:
            self._set_state("error", "Couldn't reach the server",
                            "Check the connection and try again.")
            return

        try:
            page = client.person_page(self.person_name, self.person_id) or {}
            failed = False
        except http.ApiError as exc:
            # 404 is the server's "nobody by that name": the empty state.
            if exc.status != 404:
                kodigui.ERROR("person.py: person page failed: {0}".format(exc))
            page, failed = {}, exc.status != 404
        owned, discover = split_credits(page.get("credits"))
        if not self.person_photo and page.get("profile_url"):
            self.person_photo = client.resolve_image_url(page["profile_url"]) or ""
            self.setProperty("person_photo", self.person_photo)
        # The app lists what you have by title, "The" set aside.
        owned.sort(key=lambda it: _sort_title(it.get("title") or ""))
        # Newest first, and A to Z within a year.
        self._film_rows = sorted(
            [(it, True) for it in owned] + [(it, False) for it in discover],
            key=lambda row: (-int(_year(row[0]) or 0), _sort_title(row[0].get("title") or "")))
        self.setProperty("person_credits", _credits_line(owned + discover))
        n = len(self._film_rows)
        self.setProperty("person_film_count", "1 title" if n == 1 else "{0} titles".format(
            regional.number(n)))

        self._counts[IN_LIBRARY] = len(owned)
        self._counts[NOT_IN_LIBRARY] = len(discover)
        self._boundary = len(owned) if discover else None

        # One pass for the whole filmography, owned and discover together:
        # stage_pairs knows which of them are ours to stage (a discover
        # entry's poster is on the tofa cloud CDN, tokenless and already
        # stable) and deduplicates a title that appears in both.
        artcache.prefetch(client.stage_pairs(owned + discover, "poster_path"))
        items = [self._owned_item(client, it) for it in owned]
        items += [self._discover_item(client, it) for it in discover]

        self.grid.reset()
        if items:
            self.grid.addItems(items)
            self.grid.selectItem(0)

        if items:
            self._set_state("", "", "")
        elif failed:
            self._set_state("error", "Couldn't load this filmography",
                            "Something went wrong reaching the server. Try again later.")
        else:
            self._set_state("empty", "Nothing on file",
                            "We don't have any credits for {0} yet.".format(
                                self.person_name))

        self.setProperty("person_subtitle", "{0} in your library".format(
            _titles_phrase(self._counts[IN_LIBRARY])))
        self._section_shown = None
        self._sync_section_label()
        if items:
            self.setFocusId(self.GRID_ID)

    # ------------------------------------------------------------------
    # items
    # ------------------------------------------------------------------

    def _owned_item(self, client: MediaServerClient, item: dict) -> kodigui.ManagedListItem:
        poster = client.resolve_image_url(item.get("poster_path")) or ""
        # offscreen: built detached, handed to addItems. See issue #11.
        mli = cards.poster_item(item, poster, prefs=self._ensure_preferences(),
                                offscreen=True)
        mli.setProperty("caption_meta", _year(item))
        media_id = item.get("id") or item.get("media_id")
        mli.setProperty("media_id", str(media_id) if media_id else "")
        mli.setProperty("section", IN_LIBRARY)
        # No chip: the plus means "not in your library", so an owned title
        # must not carry one.
        mli.setProperty("watchlist_glyph", "")
        return mli

    def _discover_item(self, client: MediaServerClient, item: dict) -> kodigui.ManagedListItem:
        poster = client.resolve_image_url(item.get("poster_path")) or ""
        # offscreen: built detached, handed to addItems. See issue #11.
        mli = kodigui.ManagedListItem(
            label=item.get("title") or "", thumbnailImage=poster,
            data_source=item, offscreen=True)
        mli.setArt({"poster": poster})
        mli.setProperty("caption_meta", _year(item))
        # App 2.0 rates these too, with the plus (or the clock when coming).
        mli.setProperty("rating", theme.card_rating_text(item, self._ensure_preferences()))
        cards.apply_library_badge(mli, item, in_library=False)
        mli.setProperty("tmdb_id", str(item.get("tmdb_id") or ""))
        mli.setProperty("media_type", item.get("type") or item.get("media_type") or "")
        mli.setProperty("section", NOT_IN_LIBRARY)
        return mli

    def _ensure_preferences(self) -> dict:
        """The profile's preferences blob, fetched at most once per window.
        Needed for the rating badge, which honours show_card_ratings and
        preferred_card_rating."""
        if self._preferences is None:
            client = self._get_client()
            if not client:
                return {}
            try:
                self._preferences = ((client.whoami() or {}).get("preferences")) or {}
            except http.ApiError as exc:
                kodigui.ERROR("person.py: whoami failed: {0}".format(exc))
                self._preferences = {}
        return self._preferences

    # ------------------------------------------------------------------
    # sticky section label
    # ------------------------------------------------------------------

    def _current_section(self) -> str:
        if self._boundary is None:
            return IN_LIBRARY if self._counts[IN_LIBRARY] else NOT_IN_LIBRARY
        try:
            pos = self.grid.getSelectedPosition()
        except Exception:
            return IN_LIBRARY
        return IN_LIBRARY if pos < self._boundary else NOT_IN_LIBRARY

    def _sync_section_label(self):
        if self.grid is None:
            return
        # Nothing to label. 9.7's scaffold is the whole answer on an empty or
        # failed screen, so don't caption it with "In your library   0".
        if not (self._counts[IN_LIBRARY] or self._counts[NOT_IN_LIBRARY]):
            self._section_shown = None
            self.setProperty("section_title", "")
            return
        section = self._current_section()
        if section == self._section_shown:
            return
        self._section_shown = section
        title = "IN YOUR LIBRARY" if section == IN_LIBRARY else "MORE OF THEIR WORK"
        self.setProperty("section_title", u"{0} \u00b7 {1}".format(
            title, regional.number(self._counts[section])))

    def onAction(self, action):
        import xbmcgui
        if (action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK)
                and self.getProperty("person_film_open")):
            self._film_close()
            return
        # The grid is one control, so onFocus never fires as the selection
        # moves between items -- the label has to be re-checked per keypress.
        # _sync_section_label() is a no-op unless the section actually
        # changed, so this costs a comparison.
        kodigui.ControlledWindow.onAction(self, action)
        self._sync_section_label()

    # ------------------------------------------------------------------
    # Filmography panel
    # ------------------------------------------------------------------

    def _film_open(self):
        if not self._film_rows:
            return
        items = []
        for it, owned in self._film_rows:
            mli = kodigui.ManagedListItem(label=it.get("title") or it.get("name") or "",
                                          label2=_year(it), data_source=it)
            mli.setProperty("in_library", "1" if owned else "")
            items.append(mli)
        self.film_list.reset()
        self.film_list.addItems(items)
        self.setProperty("person_film_open", "1")
        self.film_list.selectItem(0)
        self.setFocusId(self.FILM_LIST_ID)

    def _film_close(self):
        self.setProperty("person_film_open", "")
        self.setFocusId(self.PILL_ID)

    def _film_clicked(self):
        item = self.film_list.getSelectedItem()
        data = (item.dataSource if item else None) or {}
        self._open_title(data, bool(item and item.getProperty("in_library")))

    def _open_title(self, data: dict, owned: bool):
        from .detail import DetailWindow
        media_id = (data.get("id") or data.get("media_id")) if owned else None
        if media_id:
            DetailWindow.open(media_id=str(media_id))
            return
        tmdb_id = data.get("tmdb_id")
        media_type = data.get("type") or data.get("media_type")
        if tmdb_id and media_type:
            DetailWindow.open(discovery_id=str(tmdb_id), media_type=media_type)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------

    def onReInit(self):
        """A filmography card opens a Detail page over this window, and
        Kodi's <defaultcontrol always="true">8000</defaultcontrol> would
        otherwise drop focus on the sidebar when it closes."""
        self.restore_focus()

    def focus_memory_list(self, control_id):
        return self.grid if control_id == self.GRID_ID else None

    def onClick(self, controlID):
        self.remember_focus(controlID)
        if controlID == self.PILL_ID:
            self._film_open()
            return
        if controlID == self.FILM_LIST_ID:
            self._film_clicked()
            return
        if controlID != self.GRID_ID or self.grid is None:
            return
        item = self.grid.getSelectedItem()
        if item is None:
            return
        from .detail import DetailWindow
        media_id = item.getProperty("media_id")
        if media_id:
            DetailWindow.open(media_id=media_id)
            return
        tmdb_id = item.getProperty("tmdb_id")
        media_type = item.getProperty("media_type")
        if tmdb_id and media_type:
            DetailWindow.open(discovery_id=tmdb_id, media_type=media_type)


def show(name: str, client: MediaServerClient | None = None, *, role: str = "",
         title: str = "", photo: str = "", person_id: str = "") -> None:
    """Open the filmography for `name`. Silently does nothing without a
    name: a cast entry can carry an empty name string, and looking that up
    would just render a confusing empty page."""
    if not name:
        return
    w = PersonWindow.open(name=name, client=client, role=role, title=title, photo=photo,
                          person_id=person_id)
    del w
