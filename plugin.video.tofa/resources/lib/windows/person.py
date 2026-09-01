# -*- coding: utf-8 -*-
"""Person / filmography window (TV-DESIGN 7.4).

Opened by clicking a face in the detail screen's Cast or Crew grid, which
was a dead end before this existed.

Two sources, concatenated into one grid:

  in library      GET /media?cast=<name>            (per media_type)
  not in library  GET /discovery/person?name=<name>

The server strips owned titles out of the discovery half, so the two never
overlap and no client-side dedupe is needed. There is no person ID anywhere
in the API -- both calls match on the exact name string, which is also why
this window takes a name rather than an id.

The layout's one deliberate divergence (sticky section label instead of two
inline headings) is explained in the template header, not repeated here.
"""
from __future__ import annotations

from . import cards, focusmemory, kodigui, profile_select, theme
from .. import api, artcache, auth, http, regional
from ..api import MediaServerClient
from ..skin import icon_glyphs

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


def _titles_phrase(n: int) -> str:
    return "1 title" if n == 1 else "{0} titles".format(regional.number(n))


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

    def __init__(self, *args, **kwargs):
        self.person_name = kwargs.pop("name", "") or ""
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

        owned, owned_failed = self._load_owned(client)
        discover, discover_failed = self._load_discover(client)

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

        # 7.4: the empty state appears only when BOTH halves resolve empty.
        # A half that FAILED is not a half that is empty, so a partial
        # failure shows the loaded half plus a quiet note rather than the
        # full-page empty state.
        if items:
            self._set_state("", "", "")
        elif owned_failed or discover_failed:
            self._set_state("error", "Couldn't load this filmography",
                            "Something went wrong reaching the server. Try again later.")
        else:
            self._set_state("empty", "Nothing on file",
                            "We don't have any credits for {0} yet.".format(
                                self.person_name))

        self.setProperty("person_subtitle", self._subtitle(owned_failed, discover_failed))
        self._section_shown = None
        self._sync_section_label()
        if items:
            self.setFocusId(self.GRID_ID)

    def _subtitle(self, owned_failed: bool, discover_failed: bool) -> str:
        n = self._counts[IN_LIBRARY]
        if owned_failed:
            return "Couldn't load your library"
        base = "{0} in your library".format(_titles_phrase(n))
        # Don't silently imply the discover half is empty when it errored.
        return base + "  ·  rest unavailable" if discover_failed else base

    def _load_owned(self, client: MediaServerClient) -> tuple[list[dict], bool]:
        """The in-library half. /media takes one media_type per call, so
        movies and shows are two requests merged newest-first-ish by the
        order the server returns them."""
        out: list[dict] = []
        failed = False
        for media_type in ("movie", "tv"):
            try:
                resp = client.media_list(media_type, cast=self.person_name, per_page=100)
            except http.ApiError as exc:
                kodigui.ERROR("person.py: media?cast={0} ({1}) failed: {2}".format(
                    self.person_name, media_type, exc))
                failed = True
                continue
            items = resp.get("items") if isinstance(resp, dict) else resp
            for it in (items or []):
                it.setdefault("media_type", media_type)
                out.append(it)
        return out, failed

    def _load_discover(self, client: MediaServerClient) -> tuple[list[dict], bool]:
        try:
            resp = client.person_filmography(self.person_name)
        except http.ApiError as exc:
            kodigui.ERROR("person.py: discovery/person failed: {0}".format(exc))
            return [], True
        items = resp.get("items") if isinstance(resp, dict) else resp
        # Defensive: the endpoint is documented to drop owned titles, and the
        # probe agreed, but it still returns an `in_library` flag. Honour it
        # rather than trusting the contract, so a server-side change can't
        # put a title in both halves.
        return [it for it in (items or []) if not it.get("in_library")], False

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
        # 7.4's "requestable treatment": plus chip, and deliberately NO
        # rating badge -- the real app shows one only on owned cards
        # (internal-docs/atv-reference/person-not-in-library.png).
        mli.setProperty("rating", "")
        mli.setProperty("watchlist_glyph", chr(icon_glyphs.PLUS))
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
        title = "In your library" if section == IN_LIBRARY else "Not in your library"
        count = self._counts[section]
        # Inline markup rather than a second control: see the template.
        # TEXT_TERTIARY is "0xAARRGGBB"; Kodi's [COLOR] wants it without the
        # 0x prefix.
        tint = theme.TEXT_TERTIARY[2:]
        self.setProperty(
            "section_title",
            u"{0}   [COLOR {1}]{2}[/COLOR]".format(title, tint, count),
        )

    def onAction(self, action):
        # The grid is one control, so onFocus never fires as the selection
        # moves between items -- the label has to be re-checked per keypress.
        # _sync_section_label() is a no-op unless the section actually
        # changed, so this costs a comparison.
        kodigui.ControlledWindow.onAction(self, action)
        self._sync_section_label()

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


def show(name: str, client: MediaServerClient | None = None) -> None:
    """Open the filmography for `name`. Silently does nothing without a
    name: a cast entry can carry an empty name string, and looking that up
    would just render a confusing empty page."""
    if not name:
        return
    w = PersonWindow.open(name=name, client=client)
    del w
