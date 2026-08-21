# -*- coding: utf-8 -*-
"""Media detail window controller.

Framework matches home.py: ControlledWindow subclass, onFirstInit,
_get_client/theme.default_accent patterns, ManagedControlList for the cast
grid, pre-rendered progress-strip for the Resume pill's underline.

The screen is two overlaid pages in one window XML. Page 1 is the hero;
page 2 is the tabbed cast/about view. onAction owns the vertical flip:
pressing Down on an action pill sets Window.Property(detailpage) to "page2"
and explicitly focuses a page-2 control (Kodi won't navigate focus into a
hidden group on its own). The two page groups toggle visibility on that
property via String.IsEqual (not the Kodi-v18-only StringCompare), with a
short fade/slide-in.
"""
from __future__ import annotations

import math
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import cardoptions, cards, focusmemory, kodigui, person, playoptions, profile_select, theme
from .. import api, artcache, auth, badges as fmt_badges, capabilities, http, log
from .. import playbackprefs
from .. import episodes as episodes_fmt
from .. import prefs, progress, regional, textmetrics, toast, tracks
from ..api import MediaServerClient
# Module level, not the local import a few methods use: PILL_LAYOUT below is
# evaluated when the class is defined. skin.fragments pulls in only
# icon_glyphs and tokens, so there is no cycle back to here.
from ..skin import fragments
from ..profile import CapabilityProfile
from ..skin import icon_glyphs
from ..skin import tokens as T

ADDON = xbmcaddon.Addon()


def _dot_join(*parts) -> str:
    return u" • ".join(p for p in parts if p)


def _year_from(item: dict) -> str:
    year = item.get("year")
    if year:
        return str(year)
    date = item.get("release_date") or item.get("air_date")
    if date and len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    return ""


def _runtime_str(minutes) -> str:
    if not minutes:
        return ""
    minutes = int(minutes)
    hours, mins = divmod(minutes, 60)
    return "{0} h {1} min".format(hours, mins) if hours else "{0} min".format(mins)


def _episode_runtime_minutes(episode: dict, file_obj) -> int:
    """How long this episode runs, preferring the FILE over TMDB.

    TMDB has no runtime for episodes of a season still airing -- Lioness S3
    reports `runtime_minutes: None` throughout -- but we hold the file, and
    its duration is both available and more truthful: it is what will
    actually play. The real Apple TV app does the same, captioning that same
    episode "49 min" from a 2,912,159ms file.

    Falls back to TMDB's figure for an episode with no file yet, which is the
    only thing there is to say about one."""
    duration_ms = (file_obj or {}).get("duration_ms")
    if duration_ms:
        return int(round(duration_ms / 60000.0))
    return int(episode.get("runtime_minutes") or 0)


def _unaired_label(episode: dict, file_obj) -> str:
    """7.1's unaired badge text: "Airs <date>" for an episode still to come,
    "Unavailable" for one that has aired but has no playable file, "" for a
    normal episode.

    Date formatting is locale-aware per 15, which wants air dates rendered
    through localised 'MMM d' templates, while the WIRE date is parsed as
    pinned ISO -- the same section pins ISO parsing deliberately."""
    if file_obj:
        return ""
    raw = (episode.get("air_date") or "").strip()
    if not raw:
        return "Unavailable"
    try:
        import datetime

        aired = datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return "Unavailable"
    today = datetime.date.today()
    if aired <= today:
        return "Unavailable"
    if aired == today + datetime.timedelta(days=1):
        return "Airs tomorrow"
    # regional.day_and_month, not strftime("%b %-d"): `%-d` is a glibc
    # extension that Android's bionic libc does not have (main.py's own
    # history-date helper documents exactly this and avoids it), and the
    # month/day ORDER is regional -- a German box wants "28. Jul".
    return "Airs {0}".format(regional.day_and_month(aired))


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


class DetailWindow(focusmemory.FocusMemory, kodigui.ControlledWindow):
    # See home.py's HomeWindow for why this is needed now that screens open
    # each other directly in-process.
    dismissOnClose = True

    xmlFile = "script-tofa-detail.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    PILL_PRIMARY = 5210
    PRIMARY_ICON = 5211
    PRIMARY_LABEL = 5212
    PILL_REWATCH = 5220
    PILL_OPTIONS = 5225
    PILL_WATCHLIST = 5230
    PILL_VERSION = 5240
    PILL_CANCEL_REQUEST = 5250
    PILL_RETRY = 5260
    TAB_EPISODES = 6100
    TAB_CAST = 6110
    TAB_ABOUT = 6120
    TAB_MORE = 6130
    TAB_BY_NAME = {
        "episodes": TAB_EPISODES, "cast": TAB_CAST,
        "about": TAB_ABOUT, "more": TAB_MORE,
    }
    TAB_HINTS = {
        "episodes": "EPISODES", "cast": "CAST",
        "about": "ABOUT", "more": "MORE",
    }
    CAST_LIST = 6200
    CREW_LIST = 6210
    SIMILAR_LIST = 6300
    DISCOVER_LIST = 6310
    SEASON_SIDEBAR_LIST = 6400
    EPISODE_GRID_PANEL = 6410

    def __init__(self, *args, **kwargs):
        # Popped before super() so they don't reach xbmcgui.WindowXML.
        self.media_id = kwargs.pop("media_id", None)
        self.discovery_id = kwargs.pop("discovery_id", None)
        self.discovery_media_type = kwargs.pop("media_type", None)
        #: The Discover/Search shelf item this page was opened from, when it
        #: was. /discovery/detail carries availability only, so this is the
        #: sole source of hero metadata for a title the server does not hold.
        self.discovery_item = kwargs.pop("discovery_item", None) or {}
        # The exact episode to offer, when the caller already knows it.
        # Continue Watching does: its card IS one episode's file. Every
        # other entry point (Browse, Search, Discover, a library row) opens
        # a show with no episode in mind, so this is None there and
        # _next_up_episode() works it out.
        self.prefer_file_id = kwargs.pop("play_file_id", None)
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.client: MediaServerClient | None = None
        #: True when _get_client came back empty because the viewer DECLINED
        #: the profile PIN, which is a choice rather than a failure -- so the
        #: page stays as it was instead of accusing the server.
        self._client_declined: bool = False
        #: {file_id: progress record} from the most recent _next_up_episode()
        #: batch, so the load path does not re-ask for what it just fetched.
        #: Only ever read straight after that call; see its own note.
        self._nextup_progress: dict = {}
        #: The episode _render_actions resolved, handed to _render_episodes so
        #: it does not resolve it a second time.
        self._nextup_episode: dict | None = None
        self.cast_list: kodigui.ManagedControlList | None = None
        self.crew_list: kodigui.ManagedControlList | None = None
        self.similar_list: kodigui.ManagedControlList | None = None
        self.discover_list: kodigui.ManagedControlList | None = None
        self.season_list: kodigui.ManagedControlList | None = None
        self.episode_list: kodigui.ManagedControlList | None = None
        self.media: dict = {}
        self.play_file_id: str | None = None
        # Pre-play Quality/Audio/Subtitles picks (7.7), carried from the
        # Options panel to Play. Per FILE, not per title: reset by
        # _select_file, since another edition's track indices mean something
        # else entirely and its tier ladder is a different ladder.
        self.play_selection = playoptions.Selection()
        self.resume_ms: int = 0
        # Duration of whatever play_file_id points at, kept so the action
        # row's progress sliver can be recomputed on a refresh without
        # re-fetching the file.
        self.play_duration_ms: int = 0
        # Whether the server calls this title finished. Held as its own flag
        # because it cannot be read back off the action row: Rewatch is no
        # longer shown on a completed title (the primary already says Play),
        # so `show_rewatch` stopped being a proxy for it.
        self.play_completed: bool = False
        self.is_playable: bool = False
        self.tmdb_id: int | None = None
        self.content_media_type: str | None = None
        # Request state, all of it rebuilt by _render_request_state() from
        # the /discovery/detail payload. Declared here because the pill row
        # is wired on the in-library path too, where none of it ever runs.
        self.discovery_detail: dict = {}
        self.request_id: str = ""
        self.request_status: str = ""
        self.can_request: bool = False
        self.can_retry_request: bool = False
        self.is4k_capable: bool = False
        self.disc_seasons: list = []
        self.on_watchlist: bool = False
        self.selected_season_number: int | None = None
        # The episode the primary action targets, for its label and the
        # hero's episode line. None on a movie.
        self._next_up_season = None
        self._next_up_episode_number = None
        self._next_up_title = ""
        self._next_up_overview = ""
        self._prev_focus_id = 0
        self._tab_just_arrived = False
        # The page-2 tabs this media type has, left to right.
        self._tabs: list[str] = []
        # whoami's preferences blob, fetched at most once (see
        # _ensure_preferences); card ratings honour a per-profile setting.
        self._preferences: dict | None = None

    def onFirstInit(self):
        self.setProperty("accent_color", theme.default_accent())
        # Translucent focused-glass-pill fill (24% alpha) -- same token
        # MainWindow's nav bar/pills use.
        self.setProperty("accent_pill_fill", theme.accent_with_alpha("3D"))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("detailpage", "page1")
        self.setProperty("detail_tab", "cast")
        self.setProperty("detail_tabs_hint", "CAST  ·  ABOUT  ·  MORE")
        # Both tabs that can come up empty start that way and are switched on
        # by their own render pass; the tab itself is always offered, only its
        # content swaps for 9.7's scaffold.
        self.setProperty("has_cast_content", "")
        self.setProperty("similar_state", "empty")
        # The conditional action pills stay HIDDEN until _layout_action_row
        # has packed them. Their XML x is the all-pills-visible position, so
        # a pill drawn before the pack appears at that x and then visibly
        # slides left when the pack runs -- reported as "Watchlist is drawn
        # on the right and then moves". A window id comes from a pool and is
        # reused, so this is cleared here rather than relying on it being
        # unset.
        self.setProperty("pills_packed", "")
        self.cast_list = kodigui.ManagedControlList(self, self.CAST_LIST, 6)
        self.crew_list = kodigui.ManagedControlList(self, self.CREW_LIST, 6)
        # Capacity, not the item count: a grid shows far more than the
        # single row's 6 did.
        self.similar_list = kodigui.ManagedControlList(self, self.SIMILAR_LIST, 40)
        self.discover_list = kodigui.ManagedControlList(self, self.DISCOVER_LIST, 40)
        self.season_list = kodigui.ManagedControlList(self, self.SEASON_SIDEBAR_LIST, 6)
        self.episode_list = kodigui.ManagedControlList(self, self.EPISODE_GRID_PANEL, 6)
        self._load()
        # Not blindly the primary: it is disabled whenever pressing it would
        # do nothing (an out-of-library "Requested", an owned title with no
        # available file), and setFocusId() onto a disabled control silently
        # leaves focus nowhere.
        self.setFocusId(self._page1_focus_id())

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------

    def _get_client(self) -> MediaServerClient | None:
        # Not `if self.client`: a locked profile's token dies of old age after
        # ~4h, and this page outlives that -- both by sitting open and by
        # holding a client handed in by the window that opened it. Past the
        # expiry the cached client is worse than no client, because every
        # call it makes 401s and reads back as "nothing watched".
        # ensure_profile_selected below is what re-verifies the PIN; see
        # MediaServerClient.profile_token_expired.
        if self.client and not self.client.profile_token_expired():
            return self.client
        try:
            session = http.new_session()
            tok = auth.ensure_fresh(session)
            tok = profile_select.ensure_profile_selected(session, tok)
            self.client = api.client_for(session, tok)
            self._client_declined = False
        except profile_select.ProfileCanceled:
            # NOT a failure: the viewer was asked for the PIN and said no.
            # Kept apart from the rest so _load can leave the page alone
            # instead of telling them their server is unreachable.
            self.client = None
            self._client_declined = True
        except (auth.NotSignedIn, http.ApiError):
            self.client = None
            self._client_declined = False
        return self.client

    @staticmethod
    def _load_error_copy(exc: http.ApiError | None) -> tuple[str, str]:
        """What to say about a failed load, which is not one thing.

        The TITLE carries the diagnosis and the message carries the advice.
        Both halves earn their place that way: on a 10-foot screen the red
        line is the biggest text and the first thing read, so spending it on
        a constant ("Couldn't load this title", which every branch would
        share) says nothing the empty page had not already said. The card is
        allowed the second line because it is a card; a toast gets one
        sentence and no room to explain.

        The branches exist because a wrong explanation is worse than a vague
        one. The failure that prompted all this was diagnosed as an expired
        PIN for the best part of an hour, on no more evidence than a log line
        naming the wrong address; a card that confidently blames the wrong
        thing does the same to the viewer, and they cannot read the log.

          reach   nothing answered. Their connection or their server, and
                  worth telling them to look.
          locked  the server answered and refused the profile (403 is the
                  locked primary, 401 an expired credential). Telling them
                  to check the connection would send them to look at
                  something that is working perfectly.
          gone    404. The server was reached and does not have it.
          other   it answered, badly. Say so without guessing why.
        """
        status = exc.status if exc else 0
        error = exc.error if exc else "connection_error"

        if exc is None or error in ("connection_error", "timeout") \
                or status in (0, 502, 503, 504) or error in api._RELAY_DOWN:
            return ("Couldn't reach your server",
                    "Check the connection and try again.")
        if status in (401, 403):
            # Retry reuses the credential the server has just refused, so
            # pointing at it here would point at the one action that cannot
            # work. Switching profile is what re-runs verify_pin.
            return ("This profile needs unlocking",
                    "Switch profile and back to enter its PIN.")
        if status == 404:
            return ("This title isn't on your server",
                    "It may have been removed from your library.")
        return ("Your server couldn't answer",
                "Something went wrong at its end. Try again in a moment.")

    def _set_load_error(self, title: str, message: str) -> None:
        """Drive 9.7's error scaffold on page 1 (screens.py:render_detail).

        The template hides the hero stack and the tab hint on this same
        property, so setting it is the whole switch: there is no second call
        to put the page into the failed state, and clearing it puts every
        block back.
        """
        self.setProperty("detail_error_title", title)
        self.setProperty("detail_error_message", message)
        self.setProperty("detail_state", "error")
        # Focus has to land on the one thing left on screen. Without this it
        # stays on whichever pill it was on, which is now hidden -- and Kodi
        # will happily hold focus on an invisible control, so the page looks
        # like it is ignoring the remote.
        self.setFocusId(self.PILL_RETRY)

    def _clear_load_error(self) -> None:
        self.setProperty("detail_state", "")

    def _load(self):
        # Cleared up front so a retry that succeeds puts the page back,
        # rather than drawing content underneath a stale error card.
        self._clear_load_error()
        client = self._get_client()
        if not client:
            if not self._client_declined:
                # No client at all: there is no exception to read, and the
                # reason is always reach (sign-in gone, or the server did not
                # answer), never a per-title answer.
                self._set_load_error(*self._load_error_copy(None))
            return

        media_id = self.media_id

        # Out-of-library discovery entry: resolve to the owned title if it is
        # actually in the library, otherwise fall back to a watchlist-only
        # view (DetailResponse carries availability, not display metadata).
        if not media_id and self.discovery_id:
            try:
                disc = client.discovery_detail(self.discovery_media_type, int(self.discovery_id))
            except (http.ApiError, ValueError, TypeError) as exc:
                kodigui.ERROR("detail.py: discovery_detail failed: {0}".format(exc))
                disc = {}
            if disc.get("in_library") and disc.get("local_media_id"):
                media_id = disc["local_media_id"]
                # Record it: from here on this is an in-library title, and the
                # watchlist toggle keys off self.media_id to pick its endpoint.
                self.media_id = media_id
            else:
                # Kept: the request pill row is rebuilt from this payload after
                # a request or a cancellation, and tvdb_id comes off it.
                self.discovery_detail = disc
                self._render_out_of_library(disc)
                # PAGE 2 TOO. This used to return here, so a title the server
                # does not hold got Cast & Crew, About and More Like This as
                # three blank pages -- reported from the box against NCIS,
                # where the web UI fills all three.
                #
                # It was never missing data. discovery_detail already carries
                # `cast` and `crew` in the same shape media_detail uses (name,
                # role/job, profile_url), and every field _about_facts reads:
                # release_date, runtime_minutes, genres, studios,
                # content_rating, tagline, overview. This payload was already
                # being fetched and thrown away for these three tabs.
                #
                # More Like This is NOT rendered: _render_more_like_this needs
                # a library media id, which is exactly what an out-of-library
                # title does not have. It gets the empty state instead, which
                # is what the reference app shows for a title with no related
                # titles (internal-docs/atv-reference/detail-empty-more.png).
                self._render_page2(client, disc)
                return

        if not media_id:
            return

        try:
            self.media = client.media_detail(media_id) or {}
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: media_detail failed: {0}".format(exc))
            self.media = {}
            # Say so, rather than drawing the hero scaffold with nothing in
            # it. Reported from the cinema box 2026-08-21: a stale pooled
            # connection timed out here and the page came up with no
            # backdrop, no logo and an empty Play pill -- indistinguishable
            # from a title whose artwork simply had not arrived, and with
            # nothing on screen to try again with.
            #
            # An older comment here said "the failure is not a reason to
            # change what a failed page looks like" and packed the pill row
            # instead. That was the wrong conclusion from the right
            # observation: the row is packed because unpacked pills are
            # invisible, but a page with no data should not be showing that
            # row at all.
            self._wire_pill_navigation()
            self._set_load_error(*self._load_error_copy(exc))
            return

        # TIME TO PILLS is the number this screen is judged by: the hero draws
        # from a payload already in hand, so the viewer sees backdrop and logo
        # at once and then waits for the action row. Logged in the same shape
        # as Home and the episode grid, and split, because a slow fetch and a
        # slow build want opposite fixes.
        t_start = time.monotonic()
        try:
            self._render_hero(client, self.media)
            t_hero = time.monotonic()
            self._render_actions(client, self.media)
            t_actions = time.monotonic()
            # PACK THE ROW HERE, not only in the finally below.
            #
            # Everything the row is made of is known by now: _render_actions
            # has set show_watchlist, show_rewatch, the primary's label and,
            # through _render_version_pill, show_version. What follows is
            # PAGE 2 -- cast, crew, episodes -- and a separate request for
            # More Like This, none of which the viewer can see yet, and all
            # of which the action row used to wait behind.
            #
            # Measured on a fast Mac over the LAN: hero 28ms, actions 45ms,
            # page2 4ms, more-like-this 322ms -- so the row sat unpacked for
            # 327ms after it could have been drawn, on the one screen where
            # the viewer is deciding whether to press Play. Adrian reports
            # the slower boxes showing the primary pill alone and the rest
            # arriving visibly later, which is this.
            #
            # Still packed again in the finally, and deliberately: page 2 can
            # move the next-up episode, which changes which file the hero
            # offers and therefore the edition pill. Repacking is idempotent
            # -- positions, an enable, and nav links -- so the second call
            # costs nothing and corrects anything page 2 moved.
            self._wire_pill_navigation()
            t_pills = time.monotonic()
            log.info(
                "detail: pills in {0:.2f}s (hero {1:.2f}, actions {2:.2f}, "
                "pack {3:.2f})".format(
                    t_pills - t_start, t_hero - t_start,
                    t_actions - t_hero, t_pills - t_actions))
            # Everything from here on is behind the pack, so none of it can
            # hold the action row off the screen.
            if self.media.get("media_type") == "tv":
                self._render_episodes(
                    client, self.media, self.media.get("seasons") or [],
                    next_ep=self._nextup_episode,
                    progress_map=self._nextup_progress)
            self._render_page2(client, self.media)
            self._render_more_like_this(client, media_id)
            log.info("detail: page 2 done {0:.2f}s after the pills".format(
                time.monotonic() - t_pills))
        finally:
            # In a finally so a throwing render pass above still leaves the
            # tab bar navigable -- and, since pills_packed gates their
            # visibility, still leaves the action row on screen at all.
            #
            # Static XML wires the common Resume->Watchlist left/right; this
            # refines the horizontal order when the (conditional) Rewatch pill
            # is present. Vertical page-1<->page-2 movement is owned by
            # onAction, not nav links.
            self._wire_pill_navigation()
            self._wire_tab_navigation()


    # ------------------------------------------------------------------
    # page 1 -- hero
    # ------------------------------------------------------------------

    def _set_hero_title(self, title: str) -> None:
        """Publish the hero title as both a clean string and a wrapped label.

        `hero_title` stays the plain title -- other code reads it back (and
        hands it to dialogs and requests), so a [CR] must never get into it.
        `hero_title_display` is what the label draws, with the break already
        in it, and `hero_title_lines` is what the skin slides on: Kodi cannot
        bottom-align a label, so a one-line title has to be moved down a line
        for its baseline to meet the meta row. See
        textmetrics.hero_title_wrap for why the break is made here rather
        than left to <wrapmultiline>."""
        self.setProperty("hero_title", title)
        display, lines = textmetrics.hero_title_wrap(title, T.HERO_TITLE_COLUMN)
        self.setProperty("hero_title_display", display)
        self.setProperty("hero_title_lines", str(lines))

    def _render_hero(self, client: MediaServerClient, media: dict):
        # Same reason as MainWindow._home_update_hero_art: a hero resolved on
        # a miss hands Kodi a URL carrying the hourly image token, and that
        # row is orphaned as soon as the token rotates. Two images, once per
        # title opened, on the thread that is already loading this page.
        artcache.prefetch(client.stage_pairs([media], "backdrop_path", "logo_path"),
                          timeout_s=1.0)
        backdrop = client.resolve_image_url(media.get("backdrop_path")) or ""
        self.setProperty("hero_backdrop", backdrop)
        try:
            self.getControl(9000).setImage(backdrop)
        except Exception:
            pass

        logo = client.resolve_image_url(media.get("logo_path")) or ""
        self.setProperty("hero_logo", logo)

        title = media.get("title") or ""
        self._set_hero_title(title)
        self.setProperty("eyebrow_title", title.upper())

        genres = media.get("genres") or []
        meta = [_year_from(media), media.get("content_rating") or "", _runtime_str(media.get("runtime_minutes"))]
        meta.extend(genres[:2])
        self.setProperty("hero_meta_line", _dot_join(*meta))

        self.setProperty("hero_ratings_line", self._ratings_line(media))
        # Before _render_format_badges(): it ends by re-packing the stack, and
        # the synopsis is one of the blocks it packs.
        self.setProperty("hero_synopsis", media.get("overview") or "")
        files = media.get("files") or []
        chosen = next((f for f in files if f.get("available")), files[0] if files else None)
        self._render_format_badges(chosen)
        # The version pill is NOT rendered here. It describes the file the
        # primary button plays, and on a show that file is not known until
        # _render_actions has picked the next-up episode -- so it renders
        # there, for both media types.

    def _render_format_badges(self, chosen_file: dict | None):
        """Up to 3 capsule badges (e.g. "4K", "HDR10", "TrueHD Atmos 7.1")
        from the file's server-derived `format`. Filled into 3 FIXED POSITIONAL
        slots (badge_1/2/3) rather than semantic ones, so a missing badge
        kind never leaves a gap -- Kodi controls can't size themselves from
        label text length."""
        # The profile can switch the whole row off ("Format badges"), the same
        # way show_card_ratings switches the poster score chip off. Default
        # ON for a server that doesn't send the key, matching how
        # theme.card_rating_text() treats its own.
        show_badges = self._ensure_preferences().get("show_format_badges", True)
        badges = (self._format_badge_labels(chosen_file)
                  if (show_badges and chosen_file) else [])
        for i in range(4):
            self.setProperty("badge_{0}_label".format(i + 1), badges[i] if i < len(badges) else "")
        self._layout_format_badges(badges)
        # "Plays as X": the device-capability caveat, now that capabilities.py
        # can ask Kodi what this box will actually output. It is NOT a
        # restatement of the file -- an early attempt filled it from the
        # file's own channel layout, which showed it on every title and said
        # nothing. It appears only when the badge's promise won't survive
        # playback here, which on a box without passthrough is most of the
        # time and on the CoreELEC box is never.
        # Every axis on which this box will differ from the file, joined:
        # "1080p · SDR · 2.0". Silent when nothing differs, so a box that
        # delivers the file intact keeps a clean hero.
        # The caveat line follows the same switch. A user who doesn't want the
        # badges doesn't want their fallback either -- and with the badges
        # gone the line has no baseline to contrast against. (The Apple TV
        # app ignores this preference entirely and draws badges regardless;
        # that's a bug there, not a contract to match.)
        parts = capabilities.delivery(
            (chosen_file or {}).get("format") or {},
            file_height=(chosen_file or {}).get("height") or 0,
            fps=(chosen_file or {}).get("display_frame_rate"),
        )
        self.setProperty(
            "plays_as_line",
            "Plays as {0}".format(u" \u00b7 ".join(parts)) if (parts and show_badges) else "")
        self._layout_hero_stack()

    #: The hero's vertical stack, top to bottom: (name, the posy the template
    #: declares, the control ids that move together, and the PITCH from this
    #: block's own top to the next block's top). The pitches are just the
    #: template's own numbers subtracted, so a title carrying everything lays
    #: out exactly as it does today -- that arrangement was pixel-matched to
    #: the reference and this must not disturb it. The last pitch runs to the
    #: action row at 392, which never moves.
    #: 2026-08-04: every posy moved up 35 (one line of tofa_font_row_title)
    #: and the synopsis pitch grew by the same, to give the synopsis FOUR
    #: visible lines instead of three -- the Apple TV app shows four
    #: (atv-reference/detail-not-in-library.png). The action row at 392 did
    #: not move, so the growth is taken out of the empty space above the
    #: logo. An earlier note warned a 4th line would collide with "Plays as";
    #: it cannot now, because the whole stack shifted with it.
    HERO_STACK = (
        ("meta",     12,  (5102,),      52),
        ("ratings",  64,  (5103,),      59),
        ("badges",   123, (5106, 5109), 56),
        ("plays_as", 179, (5108, 5107), 52),
        ("synopsis", 231, (5104,),      161),
    )
    #: Title logo / text title. Rides the whole shift, being above all of it.
    #: 5101's y comes from the TOKEN, not a literal: this setPosition() runs on
    #: every render and overrides whatever the template said, so a literal here
    #: silently wins over the XML. It did -- moving the title in the template
    #: alone changed nothing until this line was found.
    HERO_TITLE_BLOCK = ((5105, -215), (5101, T.HERO_TITLE_POSY_DETAIL))

    def _layout_hero_stack(self):
        """Pack the hero's blocks down against the action row, closing the
        gap left by anything this title doesn't have.

        Every block sat at a fixed posy, so a sparse title (no synopsis, no
        ratings, no "plays as" line) left its format badges floating ~200px
        above the action row with
        nothing in between. The real Apple TV app keeps the action row at a
        FIXED y and packs the content upward against it -- measured on the
        same title in both states, its row sits at 890 whether the hero is
        full (detail-hero-hokum.png) or nearly empty (detail-empty-*, same
        capture session): only the stack above it changes length.

        So this walks bottom-up and pushes everything above an absent block
        down by that block's own pitch. A full hero shifts by nothing and is
        left exactly where it was.
        """
        present = {
            "meta": bool(self.getProperty("hero_meta_line")),
            "ratings": bool(self.getProperty("hero_ratings_line")),
            # One row, two possible occupants -- format badges for a title
            # with a file, the IN CINEMAS pill for one still only in cinemas.
            # They cannot both appear (a theatrical-only title has no file to
            # describe), so they share a slot rather than each taking one.
            "badges": bool(self.getProperty("badge_1_label")
                           or self.getProperty("cinema_label")),
            "plays_as": bool(self.getProperty("plays_as_line")),
            "synopsis": bool(self.getProperty("hero_synopsis")),
        }
        shift = 0
        for name, posy, ids, pitch in reversed(self.HERO_STACK):
            if not present[name]:
                shift += pitch
                continue
            self._move_y(ids, posy, shift)
        self._move_y([cid for cid, _ in self.HERO_TITLE_BLOCK],
                     None, shift, self.HERO_TITLE_BLOCK)

    def _move_y(self, ids, posy, shift, pairs=None):
        # setPosition needs an x too, and these controls don't share one, so
        # each keeps its own.
        for cid in ids:
            y = posy if pairs is None else dict(pairs)[cid]
            try:
                control = self.getControl(cid)
                control.setPosition(control.getX(), y + shift)
            except Exception:
                pass

    #: image/label control id per badge slot, and the row's geometry, both
    #: measured off the real Apple TV app (see the template's own comment).
    #: TWO rows draw the same badges from the same badge_N_label properties:
    #: the hero's, and About's. They used to differ in treatment (About kept
    #: fixed 150/200px slots in a smaller font), which made one set of
    #: strings look like two different things.
    #: Four slots, not three: a Dolby Vision disc shows its base layer too,
    #: so the longest row is resolution + DV + base + audio.
    BADGE_CONTROLS = ((5112, 5113), (5114, 5115), (5116, 5117), (5118, 5119))
    ABOUT_BADGE_CONTROLS = ((6610, 6611), (6612, 6613), (6614, 6615), (6616, 6617))
    BADGE_PAD = 13
    BADGE_GAP = 12

    def _layout_format_badges(self, badges: list):
        """Size each badge to its own text and pack the row left to right.

        Kodi can't do this from XML -- a control's width is static and the
        labels are runtime data -- so the widths in the template are
        placeholders and the real layout happens here via setWidth/
        setPosition. Silently gives up if the controls aren't up yet; the
        placeholder widths are harmless in that case."""
        self._pack_badge_row(self.BADGE_CONTROLS, badges)
        self._pack_badge_row(self.ABOUT_BADGE_CONTROLS, badges)

    def _pack_badge_row(self, controls, badges: list):
        x = 0
        for i, (image_id, label_id) in enumerate(controls):
            try:
                image = self.getControl(image_id)
                label = self.getControl(label_id)
            except Exception:
                return
            if i >= len(badges):
                continue
            width = textmetrics.text_width(badges[i]) + 2 * self.BADGE_PAD
            for control in (image, label):
                control.setPosition(x, 0)
                control.setWidth(width)
            x += width + self.BADGE_GAP

    @staticmethod
    def _format_badge_labels(f: dict) -> list:
        """The hero's badge row, taken from the server's own MediaFormatInfo.

        All of this used to be re-derived here from raw ffprobe fields, which
        the API contract explicitly tells clients not to do: the field was
        added so that a client would read it in preference to working the
        same answer out of raw codec and profile strings itself. Two real
        bugs came straight out of ignoring it:

        - The audio badge read `audio_tracks[0]`, the FIRST track, where the
          server picks the BEST one. Measured across the real library, the
          first track is not the best in 28 of 77 multi-track files: 10
          Cloverfield Lane badged "DD 5.1" on a TrueHD Atmos 7.1 file, and
          10 Rillington Place badged its FLAC Mono track over its DD 2.0.
        - It printed the raw ffprobe `profile`, so an AAC file read "LC 2.0".

        Labels are rendered verbatim, per VideoFormatInfo's own instruction,
        which also means the row is no longer force-uppercased: the app shows
        "1080p" and "DTS-HD MA 2.0", not "1080P".
        """
        fmt = f.get("format")
        if not fmt:
            # A server predating MediaFormatInfo. Resolution is safe to derive
            # (width/height mean exactly one thing); audio and dynamic range
            # are what got this wrong in the first place, so they stay absent
            # rather than guessed.
            return [lbl for lbl in (DetailWindow._resolution_fallback(f),) if lbl]

        badges = []
        if fmt.get("resolution_label"):
            badges.append(fmt["resolution_label"])

        # SDR is an explicit, real answer from the server, but it is not a
        # badge -- the app shows nothing there (Besenbinden renders "1080p"
        # alone on an SDR file). `null` means unprobed, likewise nothing.
        #
        # BOTH layers of a Dolby Vision disc, not one or the other. The API's
        # own base_layer field is documented for exactly this: a 4K disc
        # carries its DV encode on top of an HDR10+ base, and a detail
        # surface is meant to show that base ALONGSIDE the DV badge rather
        # than instead of it. An earlier pass here SUBSTITUTED the base layer on a box
        # that couldn't do DV; that conflated two jobs. These badges describe
        # the FILE, and what this box will actually deliver is the caveat
        # line's job -- each is then simply true, instead of one row trying to
        # be both and lying in whichever direction the hardware isn't.
        video = fmt.get("video") or {}
        # 3D, straight after the resolution and before dynamic range: it is a
        # fact about the PICTURE, like the resolution, where DV/HDR describe
        # its colour. Server 0.9.28 added it (`Stereo3dLayout`), and until
        # then this client had no way to know a file was 3D at all -- the gap
        # is recorded in project_player_native_settings_gap. Rendered
        # verbatim, exactly like the other labels: the server already computes
        # "3D Frame-Packed" / "3D Side-by-Side", and `null` is the 2D case.
        if video.get("stereo_3d_label"):
            badges.append(video["stereo_3d_label"])

        # Projection ratio, next to the resolution for the same reason: both
        # describe the rectangle. 16:9 IS shown here, unlike on a card --
        # the hero has room, and on a detail page "1.78:1" is a fact rather
        # than clutter. `picture_aspect_ratio` is the picture inside the
        # frame, so a 2.39 film in a full-frame remux reads 2.39, which is
        # the whole point of the field.
        aspect = fmt_badges.aspect_badge(fmt.get("picture_aspect_ratio"))
        if aspect:
            badges.append(aspect)

        if video.get("dynamic_range") not in (None, "sdr") and video.get("label"):
            badges.append(video["label"])
            base = video.get("base_layer_label")
            if base and base != video["label"]:
                badges.append(base)

        # `audio` comes back null once the best track is ordinary
        # stereo/AAC-grade material, i.e. the absence IS the badge -- the
        # server's own call on what is worth badging, made
        # by CODEC FAMILY rather than channel count. FLAC Mono gets nothing;
        # DTS-HD MA 2.0 still gets a badge, which is what the real Apple TV
        # app shows on The 'Burbs (captured 2026-08-01).
        audio = fmt.get("audio")
        if audio and audio.get("label"):
            # Bit depth on the badge too, and ONLY for lossless -- the same
            # rule tracks.bit_depth_label applies, but read off the server's
            # own `lossless` flag rather than re-derived.
            #
            # The depth lives on the raw AudioTrack, not on AudioFormatInfo,
            # so it is joined back through `track_index`, which the API
            # provides for exactly this -- it exists to let a client tie the
            # best-audio badge to the track it came from. Matched on AudioTrack.index, the
            # container stream index -- NOT on list position, which is a
            # different number.
            depth = ""
            index = audio.get("track_index")
            if audio.get("lossless") and index is not None:
                for track in (f.get("audio_tracks") or []):
                    if track.get("index") == index and track.get("bit_depth"):
                        depth = f"{int(track['bit_depth'])}-bit"
                        break
            badges.append(u" ".join(
                p for p in (audio["label"], audio.get("channels_label"), depth) if p))

        return badges

    @staticmethod
    def _resolution_fallback(f: dict) -> str:
        # Height-only, unlike the server's width-primary `resolution_label`
        # (a 3840x1600 scope master is 4K by width and 1080p by height). Both
        # agreed on all 168 library files compared, so this stays a plain
        # fallback rather than something to reconcile.
        height = f.get("height") or 0
        if height >= 2000:
            return "4K"
        if height >= 1000:
            return "1080p"
        if height >= 700:
            return "720p"
        return ""

    def _ratings_line(self, media: dict) -> str:
        """"Critics 82 • Audience 77", numerals on the §2 quality ramp.

        Inline [COLOR] here and in Search's Top Result was abandoned once
        because the color appeared to vary by score even after the code was
        changed to one fixed hex. See main.py's _search_ratings_line for why
        that was almost certainly a stale-module artefact of redeploying
        without restarting Kodi, not a Kodi color bug."""
        parts = []
        critics = media.get("tofa_critics_rating")
        if critics is not None:
            parts.append(u"Critics {0}".format(theme.rating_numeral(critics)))
        audience = media.get("tofa_audience_rating")
        if audience is not None:
            parts.append(u"Audience {0}".format(theme.rating_numeral(audience)))
        return _dot_join(*parts)

    def _render_actions(self, client: MediaServerClient, media: dict):
        media_type = media.get("media_type")
        self.tmdb_id = media.get("tmdb_id")
        self.content_media_type = media_type

        # --- Watchlist toggle ---
        # Gated on a tmdb id alone until now, which hid the pill on a library
        # title that has none -- including one already ON the watchlist, with
        # no way to take it off from the screen you'd go to for exactly that
        # (Besenbinden). A title we HOLD is keyed by its media id; only an
        # out-of-library one needs tmdb_id. Same two-endpoint split main.py's
        # card-options row already makes, and api.py's own docstring warns
        # about.
        if self.media_id or (self.tmdb_id and media_type in ("movie", "tv")):
            self.on_watchlist = self._is_on_watchlist(client)
            self.setProperty("show_watchlist", "1")
            self.setProperty("watchlist_glyph", chr(icon_glyphs.BOOKMARK_OFF if self.on_watchlist else icon_glyphs.BOOKMARK))
        else:
            self.setProperty("show_watchlist", "")

        # --- TV shows: Play/Resume the next-up episode; tab bar gains
        # Episodes (see _render_episodes()). ---
        if media_type == "tv":
            self.setProperty("is_tv", "1")
            self.setProperty("detail_tab", "episodes")
            self.setProperty("detail_tabs_hint", "EPISODES  ·  CAST  ·  ABOUT  ·  MORE")
            self.setProperty("show_rewatch", "")
            seasons = media.get("seasons") or []
            ep, f = self._next_up_episode(client, seasons)
            self._nextup_episode = ep
            if ep and f:
                self.play_file_id = f.get("id")
                self.is_playable = True
                # From the batch that just ran, NOT a second single-file GET.
                # _next_up_episode fetched progress for every candidate in one
                # request and the chosen file is by definition one of them, so
                # asking again was a whole round trip to re-learn what we were
                # already holding -- on the critical path, ahead of the pills.
                position_ms, completed = progress.position_of(
                    self._nextup_progress.get(self.play_file_id))
                self.play_duration_ms = f.get("duration_ms") or 0
                # Same rule as movies: Rewatch means "restart the episode the
                # primary button would resume", so it needs a resume point.
                self._apply_primary_progress(position_ms, completed)
                self._render_format_badges(f)
                # AFTER the badges: that call ends by packing the hero stack,
                # and this can change which blocks are in it.
                self._apply_episode_synopsis()
            else:
                self.is_playable = False
                self.setProperty("primary_label", "Unavailable")
                self.setProperty("primary_progress_fill", "")
            self._render_version_pill()
            # NOT _render_episodes here. The grid is page-2 content the viewer
            # cannot see yet, and rendering it from inside this call put the
            # whole season sidebar + episode grid AHEAD of the pack that makes
            # the action row visible -- defeating, on the TV path only, the
            # early pack _load does for exactly this reason. _load renders it
            # after the pack now, next to the other page-2 work.
            return

        # --- Movie: pick the first available file, read progress ---
        files = media.get("files") or []
        chosen = next((f for f in files if f.get("available")), files[0] if files else None)
        # Before the early return below: play_file_id is what the pill reads,
        # and "no file at all" still has to clear it.
        self.play_file_id = chosen.get("id") if chosen else None
        self._render_version_pill()
        if not chosen:
            self.is_playable = False
            self.setProperty("primary_label", "Unavailable")
            self.setProperty("primary_progress_fill", "")
            self.setProperty("show_rewatch", "")
            self.play_completed = False
            return

        self.is_playable = True

        position_ms, completed = self._progress(client, self.play_file_id, chosen)
        self.play_duration_ms = chosen.get("duration_ms") or 0

        # "Remove from Continue Watching" leaves the position on the server,
        # so a dismissed title would otherwise keep offering Resume here long
        # after the user asked for it to go away.
        if self._is_dismissed(client, media.get("id") or self.media_id, position_ms):
            position_ms, completed = 0, False

        self._apply_primary_progress(position_ms, completed)

    def _apply_primary_progress(self, position_ms: int, completed: bool):
        """Point the action row at a position: Resume vs Play, the pill's own
        progress sliver, and whether Rewatch is offered.

        One writer, called both when the page renders and when it comes back
        to the front (see refresh_watch_progress), so a refreshed page cannot
        drift from a freshly-loaded one.

        Rewatch is the "start from the beginning" action, so it is meaningful
        exactly while the primary button is NOT a plain Play -- that is,
        mid-watch, when Resume would drop the viewer somewhere else. Gating it
        on `completed` alone hid it for every partially-watched title --
        confirmed against the real Apple TV app, which shows Resume and
        Rewatch side by side on a title only ~2% in.

        A FINISHED title is the case that reads wrong. The primary falls back
        to Play, which already starts from the beginning, so a Rewatch beside
        it is the same action under a second name and the viewer has to work
        out which of two identical buttons they want. Offering both was
        reported from the box on a film watched to the end. Two pills, one
        behaviour: keep the one that says Play."""
        resuming = bool(position_ms and not completed)
        self.play_completed = bool(completed)
        if resuming:
            self.resume_ms = position_ms
            self._set_primary_label(self._primary_label("Resume"))
            step = progress.fill_step(position_ms, self.play_duration_ms)
            self.setProperty(
                "primary_progress_fill", "progress/{0}.png".format(step) if step else "")
        else:
            self.resume_ms = 0
            self._set_primary_label(self._primary_label("Play"))
            self.setProperty("primary_progress_fill", "")
        self.setProperty("show_rewatch", "1" if resuming else "")

    def _progress(self, client: MediaServerClient, file_id: str, file_obj: dict):
        try:
            prog = client.get_progress(file_id)
        except http.ApiError:
            prog = None
        if not prog:
            return 0, False
        return prog.get("position_ms") or 0, bool(prog.get("completed"))

    def _is_dismissed(self, client: MediaServerClient, media_id, position_ms: int) -> bool:
        """Whether this title was removed from Continue Watching while still
        holding a resume position.

        Dismissing does NOT clear the progress record -- probed against the
        live server: a dismissed title still reports position_ms 105949 /
        completed false, while /users/me/continue no longer lists it. So the
        raw record cannot answer "is this resumable"; Continue Watching
        membership is what the reference app follows, and it shows Play with
        no Rewatch pill and no progress underline for a dismissed title.

        Only consulted when there IS a position to suppress, so an unwatched
        title costs no extra request. Fails OPEN: if the call errors we treat
        the title as not dismissed, because wrongly hiding someone's resume
        point is far worse than wrongly offering it."""
        if not media_id or not position_ms:
            return False
        try:
            resp = client.continue_watching()
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: continue_watching failed, assuming not dismissed: {0}".format(exc))
            return False
        items = resp.get("items") if isinstance(resp, dict) else resp
        return not any(
            (it.get("id") or it.get("media_id")) == media_id for it in (items or [])
        )

    @staticmethod
    def _progress_pct(prog, file_obj) -> float:
        """0.0-1.0 watched fraction, or 0.0 when it can't be known.

        The progress record carries position_ms; the duration comes off the
        file, which is why both are needed. Returns 0.0 rather than raising
        on a missing/zero duration -- an episode we can't measure simply
        shows no capsule."""
        if not prog or not file_obj:
            return 0.0
        try:
            pos = float(prog.get("position_ms") or 0)
            dur = float(file_obj.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0.0
        if dur <= 0 or pos <= 0:
            return 0.0
        return max(0.0, min(1.0, pos / dur))

    def _ensure_preferences(self) -> dict:
        """The signed-in profile's preferences blob, fetched at most once per
        window -- same helper MainWindow keeps, for the same reason: card
        ratings honour show_card_ratings/preferred_card_rating, which are
        per-profile."""
        if self._preferences is None:
            client = self._get_client()
            if not client:
                return {}
            try:
                self._preferences = ((client.whoami() or {}).get("preferences")) or {}
                # Remembered for the PLAYER, which reads the same preferences
                # from inside onAVStarted and used to lose the audio language
                # entirely if that one request failed. Detail is on the way to
                # almost every play, so this is what gives the first play
                # after a Kodi start something to fall back to. See
                # playbackprefs.py.
                playbackprefs.remember(self._preferences.get("playback"))
            except http.ApiError as exc:
                kodigui.ERROR("detail.py: whoami failed: {0}".format(exc))
                self._preferences = {}
        return self._preferences

    def _is_on_watchlist(self, client: MediaServerClient) -> bool:
        """Match on media id first, tmdb id second.

        Entries carry both keys and a library title's `tmdb_id` is often
        null, so matching on tmdb_id alone reported "not on the watchlist"
        for something sitting right there in it -- which then drew the
        pill's ADD glyph on a title already saved."""
        try:
            entries = client.watchlist() or []
        except http.ApiError:
            return False
        for e in entries:
            if not isinstance(e, dict):
                continue
            if self.media_id and e.get("media_id") == self.media_id:
                return True
            if self.tmdb_id and e.get("tmdb_id") == self.tmdb_id:
                return True
        return False

    # ------------------------------------------------------------------
    # page 2 -- cast + about
    # ------------------------------------------------------------------

    def _size_person_panels(self, cast_count: int, crew_count: int) -> None:
        """Size each of the Cast/Crew panels to its own row count.

        Both panels live in one grouplist (id 6250) whose whole point is
        that the region scrolls as a unit. A panel with a *static* height
        defeats that: a section with fewer rows leaves a hole its
        neighbours never close, and one with more rows swallows the Down
        press to scroll inside its own box while everything above it stays
        pinned. Kodi cannot size a control from its content in XML, but
        Control.setHeight() exists at runtime -- the same escape hatch
        plex-for-kodi uses to fit its dropdown to its option count
        (lib/windows/dropdown.py). A grouplist stacks children by their
        declared heights, so resizing a panel here also moves the Crew
        label and panel below it by exactly the right amount, and an empty
        section collapses to nothing instead of leaving a hole.

        CAST_MAX_ROWS is not a nicety, it is the constraint that makes the
        whole thing work. Verified live against Hereditary (20 cast, 4
        rows): a grouplist scrolls to reveal the focused CHILD, and it does
        that well -- stepping from Cast into Crew slides the last cast row
        up above the "Crew" label, exactly the one-region scroll we want.
        But it has no way to scroll for a focus move *inside* a child, so a
        panel taller than the viewport left row 4 clipped at the bottom
        edge while focused. Capped to whole rows that fit, an oversized
        section scrolls internally again (Kodi's own behaviour, focus stays
        visible) and only the section labels stay pinned while it does.
        """
        for control_id, count in (
            (self.CAST_LIST, cast_count),
            (self.CREW_LIST, crew_count),
        ):
            rows = int(math.ceil(count / float(T.CAST_COLS)))
            try:
                self.getControl(control_id).setHeight(
                    min(rows, T.CAST_MAX_ROWS) * T.CAST_TILE
                )
            except Exception:
                pass

    def _wire_person_panels(self, has_crew: bool) -> None:
        """Re-assert Up/Down on the two person panels, because the grouplist
        they live in threw the XML's away.

        Both panels declare `<onup>` in the template and neither worked: Up
        on a crew member wrapped to the bottom of Crew, Up on the first cast
        row wrapped to the bottom of Cast, so the whole region was a focus
        trap with no way back to the tab bar. `CGUIControlGroupList` OVERRIDES
        its children's up/down navigation when it adds them, chaining them
        into a list and using the GROUPLIST's own onup/ondown for the two
        ends. Ours declares neither, so the end children were left with an
        empty action -- and an empty navigation action is precisely what makes
        a Kodi container wrap internally rather than navigate away
        (`wrapAround = !action.HasActionsMeetingCondition()`).

        Setting it here rather than adding onup/ondown to the grouplist in
        XML: the chain the grouplist builds runs over ALL its children, and
        two of the four are plain section labels with no id, so half of the
        generated links point at nothing. Naming the real targets from Python
        is both shorter and immune to a label being added later.

        Down is set for the same reason, and additionally because Crew hides
        itself when empty -- Cast must then aim at the tab bar rather than an
        invisible control.
        """
        try:
            cast_ctrl = self.getControl(self.CAST_LIST)
            crew_ctrl = self.getControl(self.CREW_LIST)
            tab = self.getControl(self.TAB_CAST)
        except Exception:
            return
        cast_ctrl.controlUp(tab)
        cast_ctrl.controlDown(crew_ctrl if has_crew else tab)
        crew_ctrl.controlUp(cast_ctrl)
        # Nothing sits below Crew, so Down is a no-op -- aimed at itself, the
        # same answer every other bottom row in the app gives.
        #
        # It used to aim back at the tab bar, on the reasoning that the region
        # should stay escapable from its last row. Measured, that made Cast &
        # Crew the one place in the app where Down travels UPWARD: tab -> Cast
        # -> Crew -> tab -> Cast -> ... a loop with no end, and no way to tell
        # you had reached the bottom. Up already leaves the region, which is
        # what "escapable" needed.
        crew_ctrl.controlDown(crew_ctrl)

    def _render_page2(self, client: MediaServerClient, media: dict):
        # Cast & Crew are two separate sections. CastMember uses "role",
        # CrewMember uses "job" -- normalized to one "role" property here
        # so person_card() doesn't need to know which list an item came from.
        #
        # A person keeps their own credit even if they appear in both lists
        # (e.g. voice actor + screenwriter) -- don't dedupe Crew against
        # Cast, that's real data, not a bug to work around.
        cast = media.get("cast") or []
        crew = media.get("crew") or []
        self.cast_list.reset()
        cast_managed = [
            self._person_card_item(m.get("name"), m.get("role"), m.get("profile_url"), client)
            for m in cast
        ]
        if cast_managed:
            self.cast_list.addItems(cast_managed)
        self.crew_list.reset()
        crew_managed = [
            self._person_card_item(m.get("name"), m.get("job"), m.get("profile_url"), client)
            for m in crew
        ]
        if crew_managed:
            self.crew_list.addItems(crew_managed)
        self.setProperty("has_crew", "1" if crew_managed else "")
        self.setProperty("has_cast_content", "1" if (cast_managed or crew_managed) else "")
        self._size_person_panels(len(cast_managed), len(crew_managed))
        self._wire_person_panels(bool(crew_managed))

        # About reuses the hero's ratings_line/format-badge properties as-is
        # (already set this render pass) -- just shown at a different position.
        self.setProperty("about_tagline", media.get("tagline") or "")
        self.setProperty("about_synopsis", media.get("overview") or "")
        facts = self._about_facts(media)
        for i in range(5):
            eyebrow, value = facts[i] if i < len(facts) else ("", "")
            self.setProperty("fact_{0}_eyebrow".format(i + 1), eyebrow)
            self.setProperty("fact_{0}_value".format(i + 1), value)
        self._layout_about_column()

    #: About's LEFT column, top to bottom: (name, declared posy, control ids,
    #: pitch to the next block's top). Same shape as HERO_STACK, opposite
    #: direction -- page 2 is a top-anchored content pane, so an absent block
    #: pulls what follows UP rather than pushing what precedes it down.
    ABOUT_COLUMN = (
        ("tagline",  168, (6600,), 36),
        ("synopsis", 204, (6601,), 290),
        ("ratings",  494, (6602,), 34),
        ("badges",   528, (6603,), 0),
    )

    def _layout_about_column(self):
        """Close the gaps in About's left column.

        Every block sat at a fixed posy, so a title with no tagline, no
        synopsis and no ratings still pushed its format badges 528px down and
        left an entirely empty column above them, with the facts panel
        stranded alone on the right. The real Apple TV app packs this column
        to the TOP: on that same title its one badge sits at y~180, right
        under the header rule
        (internal-docs/atv-reference/detail-about-sparse.png).
        """
        present = {
            "tagline": bool(self.getProperty("about_tagline")),
            "synopsis": bool(self.getProperty("about_synopsis")),
            "ratings": bool(self.getProperty("hero_ratings_line")),
            "badges": bool(self.getProperty("badge_1_label")),
        }
        shift = 0
        for name, posy, ids, pitch in self.ABOUT_COLUMN:
            if not present[name]:
                shift -= pitch
                continue
            self._move_y(ids, posy, shift)

    @staticmethod
    def _person_card_item(name, role, profile_url, client: MediaServerClient) -> "kodigui.ManagedListItem":
        # No URL disambiguation needed for a person appearing in both Cast
        # and Crew -- the same plain image URL renders correctly for both,
        # given fragments.py:person_card()'s scalediffuse="false".
        name = name or ""
        profile = client.resolve_image_url(profile_url) or ""
        # offscreen: cast rows are built detached and never written again once
        # the shelf is filled. See ManagedListItem.__init__ and issue #11.
        mli = kodigui.ManagedListItem(label=name, thumbnailImage=profile,
                                      offscreen=True)
        if profile:
            mli.setArt({"poster": profile})
            mli.setProperty("has_photo", "1")
        else:
            mli.setProperty("has_photo", "")
        mli.setProperty("initials", _initials(name))
        mli.setProperty("role", role or "")
        return mli

    @staticmethod
    def _about_facts(media: dict) -> list:
        # Fixed positional slots (fact_N_eyebrow/value, N=1..5), filled
        # left-to-right skipping absent fields -- same convention as
        # _render_format_badges(); Kodi controls can't size from text length.
        facts = []

        def add(eyebrow, value):
            if value:
                facts.append((eyebrow, value))

        add("RELEASED", _year_from(media))
        add("RUNTIME", _runtime_str(media.get("runtime_minutes")))
        genres = media.get("genres") or []
        add("GENRES", u", ".join(genres))
        studios = media.get("studios") or []
        add("STUDIO(S)", u", ".join(studios[:2]))
        add("RATED", media.get("content_rating"))
        return facts

    # ------------------------------------------------------------------
    # page 2 -- episodes (TV only)
    # ------------------------------------------------------------------

    def _next_up_episode(self, client: MediaServerClient, seasons: list, *,
                         required: bool = False) -> tuple:
        """The episode the hero should offer, in this order of preference:

          0. one the CALLER named (Continue Watching knows its own episode)
          1. one already STARTED and not finished
          2. the first not-yet-completed AFTER the highest completed episode
          3. the first not-yet-completed, when there is no usable frontier
          4. the first episode, when everything is completed

        (1) exists because the first-unfinished rule alone disagreed with
        Continue Watching: a viewer who jumped straight into S1 E3 without
        watching E1 gets a CW card reading S1 E3 and, before this, a hero
        offering "Resume S1 E1" -- two answers to the same question on two
        screens one keypress apart. The reference app resumes the episode
        with progress on it, which is also the only one the word "Resume"
        is true of.

        (2) is the same disagreement in its other form, and only shows up
        once nothing is part-watched: someone who finished S3 and left no
        episode mid-flight was offered S1 E1, because the earliest gap in a
        long show is almost never where the viewer is. The server promotes
        the episode after the last one FINISHED, so this matches it -- a gap
        behind that frontier was skipped deliberately.

        Specials (season_number 0) are excluded throughout. Progress is
        looked up in one batch call across every candidate's file id.

        The selection itself lives in progress.next_up() so the card context
        menu can reach the same answer -- "Mark as Watched" on a show has to
        name the SAME episode this pill plays, or the two disagree one
        keypress apart. The reasons above are why that rule is what it is.

        `required=True` re-raises a failed progress read instead of deciding
        from an empty map -- see refresh_watch_progress, which cannot afford
        the answer that failure produces.
        """
        candidates = progress.episode_candidates(seasons)
        if not candidates:
            self._nextup_progress = {}
            return None, None
        progress_map = progress.fetch_many(
            client, [c[3].get("id") for c in candidates], required=required)
        # Published for the load path to reuse -- see _load. Set by the call
        # that just fetched it, so it cannot go stale: a refresh path calls
        # this again and overwrites it before anyone reads it. It is NOT a
        # memo, and nothing may serve it without having called this first.
        self._nextup_progress = progress_map
        chosen = progress.next_up(candidates, progress_map, self.prefer_file_id)
        if chosen is None:
            return None, None
        season_number, episode_number, ep, f = chosen
        self._remember_next_up(season_number, episode_number, ep)
        return ep, f

    def _apply_episode_synopsis(self) -> None:
        """Describe the EPISODE the Play pill is pointing at, not the series.

        A DIVERGENCE, deliberately, and one to put to tofa. Android 0.1.11
        shows the SHOW's synopsis on a series hero even though the pill right
        under it reads "Play S1 E8" (internal-docs/androidtv-reference/
        tv-detail-hero.png), and its Episodes grid carries no synopsis at
        all -- so the episode's own `overview` is fetched by every client and
        displayed by none of them. Adrian's call, 2026-08-10: the hero
        describes what pressing Play would actually start.

        The series pitch is not lost -- the About tab still carries it in
        full, which is where the long synopsis is specified to live.

        Re-packs afterwards because the stack closes the gap left by an
        absent block, and "the show has a synopsis but this episode does
        not" is exactly the case that changes which blocks are present.
        Falls back to the SHOW's synopsis when the episode has none, so a
        sparse episode never blanks the hero -- and, on the refresh path,
        never leaves the PREVIOUS episode's text behind. On the load path
        _render_hero has already put the show synopsis there, so this writes
        the same value; on refresh it restores it.
        """
        self.setProperty(
            "hero_synopsis",
            self._next_up_overview or (self.media.get("overview") or ""))
        self._layout_hero_stack()

    def _remember_next_up(self, season_number, episode_number, ep: dict) -> None:
        """Which episode the primary action is pointing at.

        The reference app puts its number ON the button -- "Resume S1 E3" --
        so the viewer knows what is about to play without opening the
        Episodes tab, which is where its NAME already lives."""
        self._next_up_season = season_number
        self._next_up_episode_number = episode_number
        self._next_up_title = (ep.get("title") or "").strip()
        # The episode's OWN synopsis, for the hero. Free: it rides in on the
        # same media_detail payload the season list came from, so nothing is
        # fetched for it. See _apply_episode_synopsis.
        self._next_up_overview = (ep.get("overview") or "").strip()

    def _render_episodes(self, client: MediaServerClient, media: dict, seasons: list,
                         *, next_ep: dict | None = None,
                         progress_map: dict | None = None):
        """`next_ep` and `progress_map` let the caller hand over what it has
        already resolved. _load has both by the time it gets here, and
        recomputing them meant a second whole-show progress batch for an
        answer that had not changed. Omit them and this resolves its own, which
        is what the season-switch and refresh paths want -- they are repainting
        precisely because the answer MAY have changed."""
        if not seasons:
            if self.season_list is not None:
                self.season_list.reset()
            if self.episode_list is not None:
                self.episode_list.reset()
            self.setProperty("episodes_watched_count", "")
            return
        if next_ep is None:
            next_ep, _ = self._next_up_episode(client, seasons)
        default_season_number = None
        if next_ep:
            for s in seasons:
                if next_ep in (s.get("episodes") or []):
                    default_season_number = s.get("season_number")
                    break
        if default_season_number is None:
            non_special = [s for s in seasons if (s.get("season_number") or 0) != 0]
            default_season_number = (non_special[0] if non_special else seasons[0]).get("season_number")
        self.selected_season_number = default_season_number
        self._render_season_sidebar(seasons, default_season_number)
        self._render_episode_grid(client, seasons, default_season_number,
                                  progress_map=progress_map)

    def _render_season_sidebar(self, seasons: list, active_season_number):
        if self.season_list is None:
            return
        managed = []
        active_pos = 0
        active_season = None
        for i, s in enumerate(seasons):
            n = s.get("season_number") or 0
            label = s.get("title") or ("Specials" if n == 0 else "Season {0}".format(n))
            mli = kodigui.ManagedListItem(label=label, data_source=s)
            mli.setProperty("count", str(len(s.get("episodes") or [])))
            is_active = n == active_season_number
            mli.setProperty("active", "1" if is_active else "")
            if is_active:
                active_pos = i
                active_season = s
            managed.append(mli)
        self.season_list.reset()
        if managed:
            self.season_list.addItems(managed)
            # Focus lands on index 0 by default, which is Specials
            # whenever a show has them -- jump it to the active season so
            # keyboard focus and the visual "active" highlight agree.
            self.season_list.setSelectedItemByPos(active_pos)
        self._render_season_header(active_season)

    def _render_season_header(self, season: dict | None):
        if not season:
            self.setProperty("season_title", "")
            self.setProperty("season_subtitle", "")
            return
        n = season.get("season_number") or 0
        title = season.get("title") or ("Specials" if n == 0 else "Season {0}".format(n))
        self.setProperty("season_title", title)

        episodes = season.get("episodes") or []
        parts = ["{0} episode{1}".format(len(episodes), "" if len(episodes) == 1 else "s")]
        year = _year_from(season)
        if year:
            parts.append(year)
        self.setProperty("season_subtitle", _dot_join(*parts))

    def _render_episode_grid(self, client: MediaServerClient, seasons: list, season_number,
                             *, progress_map: dict | None = None):
        if self.episode_list is None:
            return
        # Timed in the same shape MainWindow logs Home in, and for the same
        # reason: card building and fetching fail slowly in different ways,
        # and one number cannot tell them apart. This is the grid PR #18
        # left out (issue #11), so the split is what says whether the
        # offscreen build actually landed on the box.
        started = time.monotonic()
        season = next((s for s in seasons if (s.get("season_number") or 0) == season_number), None)
        episodes = sorted((season.get("episodes") or []) if season else [], key=lambda e: e.get("episode_number") or 0)

        ep_file_map = {}
        file_ids = []
        for ep in episodes:
            avail = [f for f in (ep.get("files") or []) if f.get("available")]
            if avail:
                ep_file_map[ep.get("id")] = avail[0]
                file_ids.append(avail[0].get("id"))
        # A caller that already batched the whole show covers every ordinary
        # season, so the common case fetches nothing here. Specials are the
        # exception and genuinely are not covered: episode_candidates() drops
        # season 0, so opening one still costs its own batch -- which is why
        # this tops up the gap rather than trusting a handed-in map wholesale.
        if progress_map is None:
            progress_map = progress.fetch_many(client, file_ids)
        else:
            missing = [fid for fid in file_ids if fid not in progress_map]
            if missing:
                progress_map = dict(progress_map)
                progress_map.update(progress.fetch_many(client, missing))
        fetched_at = time.monotonic()

        # Spoiler protection (7.1): everything PAST the next-to-watch episode
        # hides its still behind a "Details hidden" plate, because a grid of
        # thumbnails spoils a show you're partway through -- a still from E9
        # gives away that a character is alive. The next-to-watch episode
        # itself is never hidden; you're about to watch it.
        #
        # It is the PROFILE'S call, not ours. `layout.spoilerBlurEpisodes` is
        # a real per-profile setting that the other tofa clients honour, and
        # this window used to blur unconditionally -- so a viewer who had
        # switched it off still lost every still here and nowhere else.
        # Default on when the key is absent: 7.1 calls the protection
        # canonical, and a profile that predates the setting has not opted
        # out of it.
        blur_spoilers = prefs.as_bool(
            self._ensure_preferences(), "layout.spoilerBlurEpisodes", True)
        first_unwatched = next(
            (e.get("episode_number") for e in episodes
             if not (progress_map.get((ep_file_map.get(e.get("id")) or {}).get("id"), {}) or {}).get("completed")),
            None,
        ) if blur_spoilers else None

        # Episodes that have not aired yet carry no still -- TMDB has nothing
        # to show for an episode nobody has seen -- and a grid of empty plates
        # is what a season still running looks like for most of its run.
        #
        # The fallback is THIS SEASON'S poster, not the show's backdrop. Both
        # were tried against a capture of the real Apple TV app on Lioness S3:
        # centre-cropping the season poster to 16:9 reproduces its unaired
        # cards essentially pixel for pixel, and the show backdrop is a
        # visibly different image. It is also the better answer on its own
        # terms -- a season's art belongs to the season, and a show that
        # re-shoots its key art each year would otherwise show last year's on
        # every unaired episode.
        #
        # A 2:3 poster in a 16:9 tile needs the image to FILL and crop rather
        # than fit; see episode_card()'s aspectratio.
        # Stage the stills AND the season poster before any of it resolves:
        # the poster is the fallback for every episode without a still, so on
        # an unaired season it is the one image the whole grid draws.
        artcache.prefetch(client.stage_pairs(episodes, "still_path")
                          + client.stage_pairs([season or {}], "poster_path"))
        season_art = client.resolve_image_url((season or {}).get("poster_path")) or ""

        watched = 0
        managed = []
        for ep in episodes:
            f = ep_file_map.get(ep.get("id"))
            still = client.resolve_image_url(ep.get("still_path")) or season_art
            title = episodes_fmt.title_or_number(ep) or "Episode ?"
            num = ep.get("episode_number")

            spoiler = (
                first_unwatched is not None and num is not None
                and num > first_unwatched
            )
            if spoiler:
                still = ""

            # offscreen: built detached here and handed to addItems below.
            # This was the ONE detached builder left paying Kodi's frame-move
            # guard (9bb54bf excluded it, because _apply_episode_progress
            # also serves the refresh, which writes to rows already in a live
            # container). That refresh now writes only what changed -- three
            # properties on one row instead of three on every row -- so the
            # residual here matches the one Home already accepted. See
            # issue #11.
            mli = kodigui.ManagedListItem(label=title, thumbnailImage=still,
                                          data_source={"episode": ep, "file": f},
                                          offscreen=True)
            if still:
                mli.setArt({"thumb": still})
                mli.setProperty("has_thumb", "1")
            else:
                mli.setProperty("has_thumb", "")
            mli.setProperty("spoiler", "1" if spoiler else "")

            prog = progress_map.get(f.get("id")) if f else None
            if prog and prog.get("completed"):
                watched += 1
            self._apply_episode_progress(mli, ep, f, prog)

            # Unaired / unavailable badge. An episode with a future air date
            # says when; one that has aired but has no playable file says so
            # plainly rather than looking like a broken card.
            mli.setProperty("unaired", "" if spoiler else _unaired_label(ep, f))
            managed.append(mli)

        self.episode_list.reset()
        if managed:
            self.episode_list.addItems(managed)
            # Land on the episode the hero's Resume pill is offering, so
            # moving down from "Resume S1 E3" arrives ON E3 rather than on
            # E1 with the viewer to find it. Only meaningful in the season
            # that episode is in -- switching season deliberately starts at
            # its first episode.
            target = next(
                (i for i, ep in enumerate(episodes)
                 if str((ep_file_map.get(ep.get("id")) or {}).get("id"))
                 == str(self.play_file_id)),
                None)
            # `is not None`, not a bare truth test: position 0 is a real
            # answer and a falsy one. It happened to be invisible here
            # because 0 is also where an unselected list already sits, but
            # _select_episode_by_file relies on the same lookup to MOVE the
            # selection, where landing back on the first episode is a
            # change that has to actually happen.
            if target is not None:
                self.episode_list.setSelectedItemByPos(target)
        self.setProperty("episodes_watched_count", "{0}/{1} watched".format(watched, len(episodes)))
        done = time.monotonic()
        # info, not debug, and for the reason Home's identical line is:
        # the box runs at the default log level, so a debug line is a
        # measurement nobody can read where it matters.
        log.info("detail: season {0} -- {1} episode(s) in {2:.2f}s "
                  "({3:.2f}s building cards, {4:.2f}s fetching)".format(
                      season_number, len(episodes), done - started,
                      done - fetched_at, fetched_at - started))

    def _season_clicked(self):
        item = self.season_list.getSelectedItem() if self.season_list is not None else None
        client = self._get_client()
        if not item or not item.dataSource or not client:
            return
        seasons = self.media.get("seasons") or []
        season_number = item.dataSource.get("season_number")
        self.selected_season_number = season_number
        self._render_season_sidebar(seasons, season_number)
        self._render_episode_grid(client, seasons, season_number)

    def _episode_clicked(self):
        item = self.episode_list.getSelectedItem() if self.episode_list is not None else None
        if not item or not item.dataSource:
            return
        f = item.dataSource.get("file")
        if not f:
            return
        client = self._get_client()
        position_ms, completed = self._progress(client, f.get("id"), f) if client else (0, False)
        ep = item.dataSource.get("episode") or {}
        from .player import PlayerWindow
        self._renew_profile_token_for((f.get("duration_ms") or 0) - (position_ms or 0))
        PlayerWindow.open(
            file_id=f.get("id"),
            media_id=self.media_id,
            resume_ms=(position_ms if position_ms and not completed else None),
            title=ep.get("title") or self.media.get("title"),
            # Hand over the art we already resolved, so 8.6's opening
            # card can show the backdrop from its FIRST frame. The player
            # resolves its own copy once metadata lands, but that is a round
            # trip later -- long enough that a fast open showed a black card
            # and nothing else.
            backdrop=self.getProperty("hero_backdrop"),
            logo=self.getProperty("hero_logo"),
        )

    # ------------------------------------------------------------------
    # page 2 -- more like this
    # ------------------------------------------------------------------

    def _render_more_like_this(self, client: MediaServerClient | None, media_id: str | None):
        if self.similar_list is None:
            return
        self.similar_list.reset()
        if self.discover_list is not None:
            self.discover_list.reset()
        # "Nothing similar" and "couldn't ask" are different answers, and 9.7
        # gives them different treatments, so one property carries all three
        # states: "" (results, show the grid), "empty", "error". They used to
        # share one flag and one sentence.
        self.setProperty("similar_state", "empty")
        if not client or not media_id:
            return
        try:
            resp = client.media_similar(media_id) or {}
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: media_similar failed: {0}".format(exc))
            self.setProperty("similar_state", "error")
            return
        # The owned/requestable split the API returns IS the app's own
        # category axis: it shows "More Like This" for what the library holds
        # and "More to Discover" for the rest (captured 2026-08-01). These
        # used to be concatenated into one flat grid. Clicking a requestable
        # card opens the same out-of-library Detail flow Home's Discover rows
        # already use; there's no separate "add to library" request UI here.
        owned = [self._similar_card(client, it) for it in (resp.get("owned") or [])]
        requestable = [
            self._similar_card(client, it) for it in (resp.get("requestable") or [])
        ]
        if owned:
            self.similar_list.addItems(owned)
        if requestable and self.discover_list is not None:
            self.discover_list.addItems(requestable)
        # Each shelf's header doubles as its visibility switch: poster_row()
        # hides a row whose title property is empty, and the grouplist skips
        # invisible children, so a title with only one kind of result shows
        # only that shelf, flush to the top.
        self.setProperty("similar_row_title", "More Like This" if owned else "")
        self.setProperty("discover_row_title", "More to Discover" if requestable else "")
        self.setProperty("similar_state", "" if (owned or requestable) else "empty")
        # Down from the tab bar is statically wired to the owned shelf; aim it
        # at whichever shelf actually exists.
        try:
            self.getControl(self.TAB_MORE).controlDown(
                self.getControl(self.SIMILAR_LIST if owned else self.DISCOVER_LIST))
        except Exception:
            pass

    def _similar_card(self, client: MediaServerClient, item: dict) -> "kodigui.ManagedListItem":
        title = item.get("title") or ""
        poster_path = item.get("poster_path") or item.get("poster_url")
        poster = client.resolve_image_url(poster_path) or "" if poster_path else ""
        # Score chip and format badges come with the card; their own gates
        # hide them when there is no score, or when the profile turned either
        # off. See windows/cards.py.
        # offscreen: built detached, handed to addItems. The one later write is
        # _card_options_picked's watched/watchlisted, the same accepted
        # residual Home carries -- see main.py's note and issue #11.
        mli = cards.poster_item(item, poster, label=title,
                                prefs=self._ensure_preferences(),
                                offscreen=True)
        mli.setProperty("caption_meta", _year_from(item))
        # "+" means NOT IN YOUR LIBRARY, which is exactly what puts a title on
        # the More to Discover shelf -- so it rides on the same test the shelf
        # itself does rather than on a separate field. A requested title wears
        # the clock instead; cards.apply_library_badge decides.
        cards.apply_library_badge(mli, item, in_library=bool(item.get("id")))
        return mli

    def _similar_clicked(self, control_id: int = 0):
        lst = (self.discover_list if control_id == self.DISCOVER_LIST
               else self.similar_list)
        item = lst.getSelectedItem() if lst is not None else None
        if not item or not item.dataSource:
            return
        data = item.dataSource
        media_id = data.get("id")
        if media_id:
            DetailWindow.open(media_id=media_id)
        elif data.get("tmdb_id") and data.get("media_type"):
            DetailWindow.open(discovery_id=data.get("tmdb_id"), media_type=data.get("media_type"))

    # ------------------------------------------------------------------
    # out-of-library (discovery, not owned)
    # ------------------------------------------------------------------

    def _render_out_of_library(self, disc: dict):
        # 7.9's Request action lives here (_render_request_state below, and
        # 7.6's dialog in requestseasons.py).
        #
        # The Apple TV capture this page was first matched against shows only
        # two pills -- but that title is IN CINEMAS, which the capture made
        # look like the reason it could not be requested. It is not: that
        # title merely happened to be tracked already. Do not re-derive the
        # pill row from it.
        #
        # DetailResponse has no title/overview/cast, so the hero is built
        # from the shelf item the caller forwarded (self.discovery_item).
        # Before that was forwarded this page drew NOTHING but its action
        # row -- no title, no artwork, no synopsis -- because it read back
        # properties that nobody had ever set.
        self._render_discovery_hero(self.discovery_item)
        title = self.getProperty("hero_title") or ""
        self.setProperty("eyebrow_title", title.upper())
        self.setProperty("hero_synopsis", self.getProperty("hero_synopsis") or "Not in your library yet.")
        self._render_request_state(disc)
        self.setProperty("primary_progress_fill", "")
        self.setProperty("show_rewatch", "")
        self.play_completed = False
        # Nothing to configure on a title the server does not hold.
        self.setProperty("hide_options", "1")
        self.is_playable = False
        if self.discovery_id and self.discovery_media_type:
            try:
                self.tmdb_id = int(self.discovery_id)
            except (ValueError, TypeError):
                self.tmdb_id = None
            self.content_media_type = self.discovery_media_type
            client = self._get_client()
            self.on_watchlist = (
                self._is_on_watchlist(client) if (client and self.tmdb_id) else False
            )
            self.setProperty("show_watchlist", "1")
            # PLUS/CHECK here, not the bookmark the in-library hero uses.
            # project_watchlist_glyph settled the OWNED page against the live
            # app while 18 was open; this page has since been captured
            # (atv-reference/detail-not-in-library.png) and shows a plus, and
            # "+" is already what this client means by "not in your library"
            # on Discover's own cards. The two pages are not in conflict --
            # they are different states.
            self.setProperty("watchlist_glyph", chr(
                icon_glyphs.CHECK if self.on_watchlist else icon_glyphs.PLUS))
        self._wire_pill_navigation()
        # Pack the stack for the blocks this page actually has. Without it
        # the synopsis kept the y it would have had under a ratings line, a
        # badge row and a "plays as" line that a discovery item never
        # carries, and overflowed its box -- the page opened showing the
        # synopsis from its second sentence.
        self._layout_hero_stack()
        # Via the BUILTIN, not setFocusId: the pill's own visibility was set
        # moments ago in this same pass and Kodi has not drawn a frame yet,
        # so the control is not focusable to a direct call. The builtin is
        # queued and lands after the layout settles. Same reason
        # <defaultcontrol always="true">5210</defaultcontrol> otherwise wins.
        # Whichever pill actually DOES something takes focus: Request when the
        # title can be requested, Cancel when it already has been, and
        # Watchlist otherwise (the two inert states leave nothing else). The
        # reference shows Watchlist focused beside an inert primary, which is
        # that last case.
        self._focus_request_row()

    #: request_status values that mean "the server is on it" -- the pill
    #: reports them and does nothing, but the request is still this viewer's
    #: to withdraw. Wording is the web/desktop client's, so the two agree.
    REQUEST_STATE_LABELS = {
        "pending_approval": "Pending approval",
        "requested": "Requested",
        "downloading": "Downloading",
        "retrying": "Retrying",
    }

    def _render_request_state(self, disc: dict):
        """The primary pill for a title the server does not hold.

        Driven by `request_status` (the whole RequestStatus enum, not just
        "is there a request"), then by what radarr/sonarr says. Measured
        against the live server and the macOS "tofa Desktop Player"
        2026-08-08; that client's own CTA is the reference for the wording
        and for which states do nothing:

          no integration for this TYPE  -> "Not in library", inert. The field
                                     is per media type, so a household with
                                     radarr but no sonarr can request films
                                     and not shows.
          pending_approval/requested/downloading/retrying
                                   -> the state, inert, plus a Cancel pill.
          failed                   -> "Retry request" where the server still
                                     allows one, else "Request failed".
          denied                   -> "Request again": denied is a decision
                                     about one ask, not a permanent bar.
          available                -> "Coming to library" (acquired, not yet
                                     imported).
          no request, arr has the FILE -> "Coming to library", inert. Nothing
                                     to withdraw: this is not our request.
          otherwise                -> "+ Request", the real action.

        **Merely being TRACKED is not "coming"** -- and reading it that way is
        what left a cancelled title stuck. Cancelling removes the title from
        radarr/sonarr, but `arr_status` only catches up on the server's next
        *arr refresh (~30s), so the payload we re-read a second later still
        says tracked; and a fast cancel, before the request resolved to an
        instance, leaves it tracked for good. A tracked title with no file is
        re-requestable anyway -- the server accepts it and searches again.

        Being IN CINEMAS is NOT what makes a title unrequestable -- Spider-Man
        BND is in cinemas and offers Request. The old capture's title merely
        happened to be tracked already.

        `disc` is the /discovery/detail payload; the shelf item's own
        `request_status` is NOT usable here -- it reads "requested" for titles
        already in the library and for anything merely tracked in the arr
        stack, so it would offer "Requested" on things nobody asked for.
        """
        disc = disc or {}
        self.request_id = disc.get("request_id") or ""
        self.request_status = (disc.get("request_status") or "").lower()
        self.is4k_capable = bool(disc.get("is4k_capable"))
        self.disc_seasons = list(disc.get("seasons") or [])
        arr = disc.get("arr_status") or {}
        # No integration configured for this media type means nothing can be
        # requested at all, and a pill that always fails is worse than one
        # that is honest about it.
        integrated = bool(disc.get("integration_available"))

        self.can_request = False
        self.can_retry_request = False
        self.setProperty("show_cancel_request", "")

        if not integrated:
            # No icon: this states a fact rather than offering an action, and
            # a glyph on a pill that does nothing reads as a broken button.
            self._set_primary_label("Not in library", glyph="")
            return

        status = self.request_status
        if status in self.REQUEST_STATE_LABELS:
            self._set_primary_label(
                self._downloading_label(disc) if status == "downloading"
                else self.REQUEST_STATE_LABELS[status], glyph="")
            # Withdrawing stays offered for every live state: it is the one
            # thing left to do about a request, and the server cancels a
            # download as readily as a queued ask (it pulls the transfer and
            # removes the title from *arr).
            self.setProperty("show_cancel_request", "1" if self.request_id else "")
        elif status == "failed":
            if self.request_id and disc.get("can_retry"):
                self.can_retry_request = True
                self._set_primary_label("Retry request",
                                        glyph=chr(icon_glyphs.REFRESH_CW))
            else:
                self._set_primary_label("Request failed", glyph="")
            self.setProperty("show_cancel_request", "1" if self.request_id else "")
        elif status == "denied":
            # A denial answers one ask; asking again is the only move left,
            # and it is what the desktop client offers ("Denied - Re-request").
            self.can_request = True
            self._set_primary_label("Request again", glyph=chr(icon_glyphs.PLUS))
        elif status == "available" or (arr.get("tracked") and arr.get("has_file")):
            # The file exists on the server's side but this library has not
            # picked it up yet.
            self._set_primary_label("Coming to library", glyph="")
        # A show needs its season list to be requestable at all -- 7.6 asks
        # which seasons, and there is nothing to ask with if the payload
        # carried none.
        elif self.discovery_media_type == "movie" or self.disc_seasons:
            self.can_request = True
            self._set_primary_label("Request", glyph=chr(icon_glyphs.PLUS))
        else:
            self._set_primary_label("Not in library", glyph="")

    @staticmethod
    def _downloading_label(disc: dict) -> str:
        """"Downloading 42%" while the server reports progress, plain
        "Downloading" before it does -- a percentage of nothing reads as a
        stalled transfer."""
        progress = (disc or {}).get("request_download") or {}
        try:
            percent = int(round(float(progress.get("progress") or 0) * 100))
        except (TypeError, ValueError):
            percent = 0
        return "Downloading {0}%".format(percent) if percent else "Downloading"

    @staticmethod
    def _today_iso() -> str:
        import datetime
        return datetime.date.today().isoformat()

    def _render_discovery_hero(self, item: dict):
        """The hero for a title the server does not hold, from the shelf
        item's own fields.

        Deliberately NOT _render_hero(): that reads a MediaDetail (files,
        runtime_minutes, content_rating, logo_path) and a discovery item has
        a different, thinner shape. Sharing it would mean teaching it two
        payloads; this stays a small separate pass over what actually exists.
        """
        if not item:
            return
        client = self._get_client()
        if client:
            backdrop = client.resolve_image_url(item.get("backdrop_path")) or ""
            self.setProperty("hero_backdrop", backdrop)
            try:
                self.getControl(9000).setImage(backdrop)
            except Exception:
                pass
            self.setProperty("hero_logo",
                             client.resolve_image_url(item.get("logo_path")) or "")

        title = item.get("title") or item.get("name") or ""
        self._set_hero_title(title)

        # Same grammar as an owned title's meta line, over the fields a
        # discovery item has: no runtime and no content rating come back
        # from these shelves, so the line is year + genres.
        year = str(item.get("year") or "")[:4]
        genres = [g for g in (item.get("genres") or []) if g][:2]
        self.setProperty("hero_meta_line", _dot_join(year, *genres))

        # Straight reuse: a discovery item carries tofa_critics_rating /
        # tofa_audience_rating under exactly the names _ratings_line reads,
        # so this is the same "Critics 78 - Audience 84" the owned hero
        # draws, on the same quality ramp. The reference shows it here too.
        self.setProperty("hero_ratings_line", self._ratings_line(item))

        # Still in cinemas, no home release yet: the reference badges exactly
        # this state under the scores. The rule is main.py's -- a theatrical
        # date already past and no digital date -- reproduced here rather
        # than imported, because main.py imports THIS module.
        theatrical = item.get("theatrical_release_date")
        in_cinemas = bool(theatrical and not item.get("digital_release_date")
                          and str(theatrical)[:10] <= self._today_iso())
        self.setProperty("cinema_label", "IN CINEMAS" if in_cinemas else "")
        self.setProperty("cinema_glyph",
                         chr(icon_glyphs.CLAPPERBOARD) if in_cinemas else "")

        self.setProperty("hero_synopsis", item.get("overview") or "")

    # ------------------------------------------------------------------
    # navigation wiring (depends on which pills are visible)
    # ------------------------------------------------------------------

    #: pill id -> (its wrapping group's id, width, the gap that precedes it).
    #:
    #: Every pill but the primary is one width now (fragments.ACTION_PILL_W),
    #: and every gap is one gap. The per-pill numbers this used to hold were
    #: the reference app's, and they only worked while every label was known
    #: at build time -- see that constant for why they stopped. This table is
    #: what packs the row at runtime, so it has to agree with the template or
    #: every pill after the first mismatch lands in the wrong place.
    PILL_LAYOUT = {
        5210: (5219, 360, 0),
        5225: (5226, fragments.ACTION_PILL_W, fragments.ACTION_PILL_GAP),
        5220: (5221, fragments.ACTION_PILL_W, fragments.ACTION_PILL_GAP),
        5230: (5231, fragments.ACTION_PILL_W, fragments.ACTION_PILL_GAP),
        5240: (5241, fragments.ACTION_PILL_W, fragments.ACTION_PILL_GAP),
        5250: (5251, fragments.ACTION_PILL_W, fragments.ACTION_PILL_GAP),
    }

    def _layout_action_row(self, pills: list):
        """Pack the visible pills left to right, closing the gap a hidden one
        leaves behind.

        Rewatch and Watchlist are both conditional but every pill sat at a
        fixed x, so a title without Rewatch drew Play and Options and then a
        ~300px hole before Watchlist. The real Apple TV app packs them: on a
        title with no Rewatch its Watchlist pill starts 668px into the row,
        and packing ours puts it at 664.

        Same trick the format badges use -- a group's position offsets its
        children, so one setPosition() per pill moves the whole thing.

        Nothing conditional is VISIBLE until this has run: each such pill's
        <visible> also tests `pills_packed`, which is set at the end here.
        Without it the pill drew at the static x its XML carries -- the
        position it would hold with every other pill present -- and then
        slid left the moment this ran, which is what the viewer saw.
        """
        x = 0
        for pid in pills:
            entry = self.PILL_LAYOUT.get(pid)
            if not entry:
                continue
            group_id, width, gap = entry
            x += gap
            try:
                self.getControl(group_id).setPosition(x, 0)
            except Exception:
                pass
            x += width
        # Last, and only after every position has landed.
        self.setProperty("pills_packed", "1")

    def _wire_pill_navigation(self):
        # Order: Resume, Edition, Options, Rewatch, Watchlist. Rewatch used
        # to sit second; it belongs after Options (real app, captured
        # 2026-07-31). Edition leads them all because it CHANGES WHAT THE
        # OTHERS MEAN -- Options lists the tracks of whichever file is
        # selected, and Play plays it -- so a viewer who wants the 4K cut
        # has to reach it before, not after, the panel describing the 1080p
        # one. It is also the rarest pill (only a multi-file title has it),
        # which keeps the common row unchanged.
        #
        # This list is the single source for both the visual order
        # (_layout_action_row packs them left to right) and the left/right
        # chain, so a hidden pill simply drops out instead of stranding
        # focus on an invisible control.
        pills = [self.PILL_PRIMARY]
        # Straight after the primary, because it belongs TO it: the primary has
        # become the inert "Requested" label and this is the only thing left to
        # do about that. The real app stacks it on a second line under
        # "Requested"; ours stays in the one row every other state uses, which
        # this packer already handles and which comfortably fits (Requested +
        # Cancel request + Watchlist is ~900px of a 1920 row).
        if self.getProperty("show_cancel_request"):
            pills.append(self.PILL_CANCEL_REQUEST)
        if self.getProperty("show_version"):
            pills.append(self.PILL_VERSION)
        # Options is shown for every title this server HOLDS -- there is no
        # data-driven reason to hide it there, unlike Rewatch/Watchlist. For
        # an out-of-library title there is nothing to set quality, audio or
        # subtitles for, and the Apple TV app drops it
        # (atv-reference/detail-not-in-library.png).
        if not self.getProperty("hide_options"):
            pills.append(self.PILL_OPTIONS)
        if self.getProperty("show_rewatch"):
            pills.append(self.PILL_REWATCH)
        if self.getProperty("show_watchlist"):
            pills.append(self.PILL_WATCHLIST)
        # The row is LAID OUT from every visible pill but NAVIGATED over only
        # the ones that do something. An inert primary ("Requested", "Coming
        # to library", "Not in library") still holds its place at the head of
        # the row -- it is the page's answer to "can I watch this?" -- but
        # taking focus there drew an accent ring around a pill that does
        # nothing when pressed, which reads as a broken button.
        self._layout_action_row(pills)
        focusable = [pid for pid in pills
                     if pid != self.PILL_PRIMARY or self._primary_is_actionable()]

        controls = {}
        for pid in pills:
            try:
                controls[pid] = self.getControl(pid)
            except Exception:
                return

        # Disabled, not merely unlinked: the chain is only one way in. Kodi's
        # own <defaultcontrol always="true">, a mouse click and SetFocus() all
        # reach a control that is simply missing from it, and a disabled one
        # they skip. The pill draws the same either way -- it is a transparent
        # hit area, and every visual around it keys off Control.HasFocus.
        try:
            controls[self.PILL_PRIMARY].setEnabled(
                self.PILL_PRIMARY in focusable)
        except Exception:
            pass

        try:
            tab = self.getControl(self.TAB_CAST)
        except Exception:
            tab = None

        for i, pid in enumerate(focusable):
            ctrl = controls[pid]
            left = controls[focusable[i - 1]] if i > 0 else ctrl
            right = controls[focusable[i + 1]] if i < len(focusable) - 1 else ctrl
            ctrl.controlLeft(left)
            ctrl.controlRight(right)
            if tab is not None:
                ctrl.controlDown(tab)
            ctrl.controlUp(ctrl)

    def _primary_is_actionable(self) -> bool:
        """Whether pressing the primary pill would DO anything: play an owned
        title, or open/retry a request on one the server does not hold."""
        return bool(self.is_playable or self.can_request or self.can_retry_request)

    def _wire_tab_navigation(self):
        # Same dynamic-list-of-visible-controls technique as
        # _wire_pill_navigation() -- avoids a static XML <onright> pointing
        # at an always-invisible-for-movies control. Episodes is leftmost
        # for TV, so it goes first here too.
        #
        # An EMPTY tab is still a tab. A pass that hid Cast & Crew and More
        # Like This when they had nothing behind them was checked against the
        # real Apple TV app (Besenbinden, which has neither) and is wrong
        # there: the app keeps both and answers them with 9.7's scaffold. The
        # spec agrees as far as it goes -- 7.1 makes exactly one tab
        # conditional, "(Episodes omitted for movies)", and says nothing
        # about the rest.
        self._tabs = ["cast", "about", "more"]
        if self.getProperty("is_tv"):
            self._tabs.insert(0, "episodes")
        self.setProperty(
            "detail_tabs_hint",
            "  ·  ".join(self.TAB_HINTS[n] for n in self._tabs),
        )
        tabs = [self.TAB_BY_NAME[n] for n in self._tabs]
        controls = {}
        for tid in tabs:
            try:
                controls[tid] = self.getControl(tid)
            except Exception:
                return
        for i, tid in enumerate(tabs):
            ctrl = controls[tid]
            left = controls[tabs[i - 1]] if i > 0 else ctrl
            right = controls[tabs[i + 1]] if i < len(tabs) - 1 else ctrl
            ctrl.controlLeft(left)
            ctrl.controlRight(right)

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------

    def onAction(self, action):
        # Both directions of the page1<->page2 pager need a manual override:
        # Kodi's native focus engine runs before onAction is called, but
        # silently fails to move focus onto a control positioned off-screen
        # by the pager slide (true for PILL_PRIMARY from the tab bar's
        # <onup>, and for the tabs from the pills' <ondown>). setFocusId()
        # works regardless of on-screen position, so both directions are
        # driven explicitly here.
        #
        # getFocusId() reflects focus AFTER Kodi's native nav attempt for
        # this keypress, which makes "just arrived at a tab via successful
        # native nav" and "was already on the tab, native nav to page 1
        # failed" indistinguishable by focus id alone -- both read as
        # focus == the tab. _tab_just_arrived (set in onFocus on a genuine
        # transition onto a tab, consumed by the first Up press after)
        # disambiguates: only a second, real "still here" Up press flips
        # to page 1.
        aid = action.getId()
        try:
            focus = self.getFocusId()
        except Exception:
            focus = 0

        # BACK on page 2 goes UP to page 1, not out of the screen. The pager
        # is one screen in two halves -- Down enters page 2 and Up leaves it
        # -- so Back closing the whole window from down there threw away the
        # hero as well, and the way back to it was a key Back is not.
        #
        # Deliberately NOT swallowed while Back is auto-repeating: holding it
        # is 10.1's "return to the top level", and stopping that dead on
        # page 1 would make a held key mean something different here than
        # everywhere else. A held key therefore still unwinds straight out;
        # only a deliberate press pages up. See kodigui.back_is_held_repeat.
        if (aid in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
                and self.getProperty("detailpage") == "page2"
                and not kodigui.back_is_held_repeat()):
            self.setProperty("detailpage", "page1")
            self.setFocusId(self._page1_focus_id())
            # Focus is off the grid now, so the season subtitle comes back.
            self._sync_episode_synopsis()
            return

        # 10.2 names the episode grid as required card-options coverage
        # ("Home, Discover, Search, episode grid"), and More Like This is an
        # ordinary poster shelf. Cast and Crew are deliberately absent: a
        # person is not a title and none of 7.2's actions apply to one.
        if aid == xbmcgui.ACTION_CONTEXT_MENU:
            if focus == self.SEASON_SIDEBAR_LIST and self._open_season_options():
                return
            if self._open_card_options(focus):
                return
            # The hero itself. 7.2 assigns this panel to the Options pill,
            # but the live app's Options opens the Quality/Audio pre-play
            # panel instead (7.7) -- captured 2026-07-31 -- and that is what
            # our pill already does, so the pill stays put. The context key
            # is free here and is the trigger 10.2 sanctions anyway.
            #
            # This is the only route to Mark as Watched/Unwatched and Remove
            # from Continue Watching on a detail screen; neither has a pill.
            if focus in (self.PILL_PRIMARY, self.PILL_REWATCH,
                         self.PILL_OPTIONS, self.PILL_WATCHLIST):
                if self._open_hero_options():
                    return

        if aid == xbmcgui.ACTION_MOVE_DOWN and focus in (
            self.PILL_PRIMARY, self.PILL_REWATCH, self.PILL_OPTIONS,
            self.PILL_WATCHLIST, self.PILL_VERSION, self.PILL_CANCEL_REQUEST,
        ):
            tab = self.TAB_BY_NAME.get(
                self.getProperty("detail_tab"), self.TAB_CAST)
            self.setProperty("detailpage", "page2")
            self.setFocusId(tab)
            return
        if aid == xbmcgui.ACTION_MOVE_UP and focus in (
            self.TAB_CAST, self.TAB_ABOUT, self.TAB_MORE, self.TAB_EPISODES
        ):
            if self._tab_just_arrived:
                # Native nav already landed focus correctly this press;
                # nothing more to do.
                self._tab_just_arrived = False
            else:
                self.setProperty("detailpage", "page1")
                # NOT always the primary: on an out-of-library page it is
                # frequently disabled ("Requested" and friends do nothing), and
                # setFocusId() onto a disabled control fails silently -- which
                # left focus on a tab that had just slid off screen.
                self.setFocusId(self._page1_focus_id())
            return
        kodigui.ControlledWindow.onAction(self, action)
        # AFTER the base class: Kodi's onFocus does not fire when the
        # selection moves WITHIN an already-focused container, so the only
        # way to see the cursor move from E4 to E5 is to let the move happen
        # and then read where it landed. Same technique as main.py's
        # _browse_maybe_load_more.
        self._sync_episode_synopsis()

    def _sync_episode_synopsis(self) -> None:
        """Describe the episode the cursor is ON, on the season heading's row.

        The reference shows an episode synopsis NOWHERE -- not on the hero,
        not in this grid (Android 0.1.11, internal-docs/androidtv-reference/
        tv-page2.png: still, "E1 - 21m", title, and nothing else). So this is
        a divergence to put to tofa alongside the hero one.

        It costs no layout. The grid is three rows of 284 starting at 230,
        which is exactly the screen, so a synopsis ABOVE it would clip the
        third row; instead this rides the line the season subtitle already
        occupies, and that subtitle steps aside while an episode is focused.
        The XML picks between them on episode_synopsis being empty.

        Cleared whenever focus is anywhere else, so the subtitle comes back
        rather than the line going stale on a screen the cursor has left.
        """
        try:
            focused = self.getFocusId()
        except Exception:                                   # noqa: BLE001
            focused = 0
        if focused != self.EPISODE_GRID_PANEL or self.episode_list is None:
            self.setProperty("episode_synopsis", "")
            return
        item = self.episode_list.getSelectedItem()
        data = (item.dataSource or {}) if item else {}
        episode = data.get("episode") or {}
        self.setProperty(
            "episode_synopsis", (episode.get("overview") or "").strip())

    def onFocus(self, controlID):
        tabs = (self.TAB_CAST, self.TAB_ABOUT, self.TAB_MORE, self.TAB_EPISODES)
        self._tab_just_arrived = controlID in tabs and self._prev_focus_id not in tabs
        self._prev_focus_id = controlID

        if controlID in (
            self.TAB_CAST, self.TAB_ABOUT, self.TAB_MORE, self.TAB_EPISODES,
            self.CAST_LIST, self.CREW_LIST, self.SIMILAR_LIST, self.DISCOVER_LIST,
            self.SEASON_SIDEBAR_LIST, self.EPISODE_GRID_PANEL,
        ):
            self.setProperty("detailpage", "page2")
        else:
            self.setProperty("detailpage", "page1")

        if controlID == self.TAB_CAST:
            self.setProperty("detail_tab", "cast")
        elif controlID == self.TAB_ABOUT:
            self.setProperty("detail_tab", "about")
        elif controlID == self.TAB_MORE:
            self.setProperty("detail_tab", "more")
        elif controlID == self.TAB_EPISODES:
            self.setProperty("detail_tab", "episodes")
        # Entering or LEAVING the grid is a real onFocus, unlike moving
        # inside it -- which is why onAction carries the other half.
        self._sync_episode_synopsis()

    def onClick(self, controlID):
        self.remember_focus(controlID)
        if controlID == self.PILL_PRIMARY:
            # On an out-of-library page the primary pill is Request (or Retry,
            # or Request again after a denial), not Play -- and in its inert
            # states it is deliberately nothing at all. Those states also
            # disable the control, so this is belt and braces.
            if self.can_request:
                self._request_clicked()
            elif self.can_retry_request:
                self._retry_request_clicked()
            elif self.is_playable:
                self._play(self._fresh_resume_ms())
        elif controlID == self.PILL_RETRY:
            self._load()
        elif controlID == self.PILL_CANCEL_REQUEST:
            self._cancel_request_clicked()
        elif controlID == self.PILL_REWATCH:
            self._play(0)
        elif controlID == self.PILL_OPTIONS:
            self._open_playback_options()
        elif controlID == self.PILL_WATCHLIST:
            self._toggle_watchlist()
        elif controlID == self.PILL_VERSION:
            self._version_clicked()
        elif controlID == self.TAB_CAST:
            self.setProperty("detail_tab", "cast")
        elif controlID == self.TAB_ABOUT:
            self.setProperty("detail_tab", "about")
        elif controlID == self.TAB_MORE:
            self.setProperty("detail_tab", "more")
        elif controlID == self.TAB_EPISODES:
            self.setProperty("detail_tab", "episodes")
        elif controlID in (self.SIMILAR_LIST, self.DISCOVER_LIST):
            self._similar_clicked(controlID)
        elif controlID == self.SEASON_SIDEBAR_LIST:
            self._season_clicked()
        elif controlID == self.EPISODE_GRID_PANEL:
            self._episode_clicked()
        elif controlID in (self.CAST_LIST, self.CREW_LIST):
            self._person_clicked(controlID)

    def _person_clicked(self, control_id: int):
        """7.4's filmography page. Both grids feed the same window; the
        lookup is on the name string because the API has no person id.

        The client is handed over so the new window doesn't re-run the
        profile gate on an already-signed-in session."""
        lst = self.cast_list if control_id == self.CAST_LIST else self.crew_list
        if lst is None:
            return
        item = lst.getSelectedItem()
        if item is None:
            return
        person.show(item.getLabel(), self._get_client())

    def _open_playback_options(self) -> bool:
        """7.7's pre-play options: Quality / Audio / Subtitles for the file
        Play is about to use.

        This is what the Options pill opens, matching the live Apple TV app
        (captured 2026-07-31), where the compact button beside Play leads
        here and not to 7.2's card menu. 7.2's menu is still reachable on
        the hero, on the remote's context key -- it is the only route to
        Mark as Watched and Remove from Continue Watching, neither of which
        has a pill.

        The track and tier lists come from a DRY RUN of the same negotiation
        Play will perform, so what the panel offers is what the server will
        actually honour for this file, this profile and this client's codec
        support -- not a guess assembled from the media record. dry_run is
        what keeps it free of side effects: no session is created, so
        opening Options never shows up as a play."""
        if not self.is_playable or not self.play_file_id:
            return False
        client = self._get_client()
        if not client:
            return False
        try:
            info = client.stream_info(
                self.play_file_id,
                CapabilityProfile.for_device(
                    max_bitrate=self.play_selection.max_bitrate,
                    quality_mode=self.play_selection.quality_mode),
                dry_run=True,
            )
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: stream info for options failed: {0}".format(exc))
            toast.show("Playback options are unavailable right now")
            return True

        # Name the file, not just the title: on a multi-edition title the
        # panel's contents change completely with the version pill, and two
        # identical-looking dialogs that mean different things is the exact
        # confusion the version pill was split out to end.
        current = next((f for f in self._available_files()
                        if f.get("id") == self.play_file_id), None)
        subtitle = self._version_row_label(current) if current else ""

        self.play_selection = playoptions.show(
            title="Options",
            subtitle=subtitle or (self.media.get("title") or ""),
            info=info,
            selection=self.play_selection,
            # So the Audio row names the track playback will choose, rather
            # than the file's first one -- see playoptions.build_sections().
            audio_languages=((self._ensure_preferences().get("playback") or {})
                             .get("preferred_audio_languages") or []),
        )
        return True

    def _open_hero_options(self) -> bool:
        """7.2's detail variant: the same panel, but carrying "Options" as
        its eyebrow and Cancel as a row of its own.

        "Go to Details" is dropped -- this IS the details. Watchlist stays
        even though a pill exists, because 7.2 lists it and a user who opened
        the menu should not have to close it again to reach an action the
        menu is plainly about."""
        client = self._get_client()
        if not client or not self.media:
            return False
        media_id = self.media.get("id") or self.media_id
        keys = [k for k in cardoptions.option_keys(
            in_library=bool(media_id) and self.is_playable,
            fully_watched=self.play_completed,
            has_progress=bool(self.resume_ms),
            on_watchlist=self.on_watchlist,
            in_continue_watching=bool(self.resume_ms),
            detail_variant=True,
        ) if k != cardoptions.DETAILS]

        picked = cardoptions.show(
            title=self.media.get("title") or "",
            subtitle=self.getProperty("hero_meta_line") or "",
            eyebrow="OPTIONS",
            keys=keys,
            resume=bool(self.resume_ms),
        )
        if picked == cardoptions.PLAY:
            self._play(self._fresh_resume_ms())
        elif picked in (cardoptions.WATCHLIST_ADD, cardoptions.WATCHLIST_REMOVE):
            self._toggle_watchlist()
        elif picked in (cardoptions.MARK_WATCHED, cardoptions.MARK_UNWATCHED):
            self._set_media_watched(client, picked == cardoptions.MARK_WATCHED)
        elif picked == cardoptions.REMOVE_FROM_CW and media_id:
            try:
                client.dismiss_media(media_id)
            except http.ApiError as exc:
                kodigui.ERROR("detail.py: dismiss failed: {0}".format(exc))
                return True
            # Re-render so the hero drops Resume/Rewatch immediately, the
            # same state _is_dismissed() would compute on a fresh open.
            self._render_actions(client, self.media)
        return True

    def _primary_label(self, verb: str) -> str:
        """"Resume S1 E3" on a show, plain "Resume" on a film.

        Measured off the reference app, which puts the number on the button
        itself. _set_primary_label() re-centres the pill for whatever word
        it is given, so the longer label needs nothing else."""
        if self._next_up_season is None or self._next_up_episode_number is None:
            return verb
        return "{0} S{1} E{2}".format(
            verb, self._next_up_season, self._next_up_episode_number)

    #: The play triangle the primary pill normally carries.
    PRIMARY_GLYPH = chr(icon_glyphs.PLAY)

    def _set_primary_label(self, label: str, glyph: str | None = None) -> None:
        """Set the primary pill's text AND re-centre its icon+label group.

        One call site for both so they can never disagree -- the pill's
        geometry depends on the word it is showing.

        `glyph=""` draws the label alone and centres it on its own, for the
        one pill that is not an action: "Not in library" states a fact and
        does nothing when pressed, and the Apple TV app gives it no icon
        (atv-reference/detail-not-in-library.png). A play triangle on an
        unplayable title reads as a broken button.
        """
        icon = self.PRIMARY_GLYPH if glyph is None else glyph
        self.setProperty("primary_glyph", icon)
        self.setProperty("primary_label", label)
        self._layout_primary_pill(label, bool(icon))

    def _layout_primary_pill(self, label: str, with_icon: bool = True) -> None:
        """Point the primary pill's label at the room its icon leaves.

        It used to RE-CENTRE the icon+label group for whatever label was
        showing, because Kodi cannot centre two siblings as a unit and this
        label changes at runtime (Play / Resume / Resume S2 E2 / Requested).
        That measured the label to place it.

        Nothing is measured now. The icon is anchored at the pill's inset
        like every other pill's (fragments.action_pill_layout), the label is
        centred in the span beside it by the XML, and the only thing left
        that varies is WHETHER there is an icon -- with none, the label takes
        the whole inner width instead of starting after one.

        `label` is kept in the signature: callers read better for it, and it
        is what the docstring above is about."""
        icon_x, label_x, label_w, _trailing = fragments.action_pill_layout(
            self.PILL_LAYOUT[self.PILL_PRIMARY][1])
        if not with_icon:
            label_x = fragments.ACTION_PILL_INSET
            label_w = self.PILL_LAYOUT[self.PILL_PRIMARY][1] - 2 * label_x
        try:
            self.getControl(self.PRIMARY_ICON).setPosition(icon_x, 0)
            lbl = self.getControl(self.PRIMARY_LABEL)
            lbl.setPosition(label_x, 0)
            lbl.setWidth(label_w)
        except Exception:
            pass

    def _set_media_watched(self, client: MediaServerClient, watched: bool) -> None:
        """Mark this title watched/unwatched, then re-render so Resume /
        Rewatch and the episode ticks reflect it without a reopen.

        ON A SHOW THIS IS ONE EPISODE -- the one the hero is offering, i.e.
        exactly what Play would start. It used to walk
        seasons[].episodes[].files[] and mark the lot: measured on Murder,
        She Wrote, one press marked all 264 episodes across 12 seasons, and
        the owner's read was that they had picked it expecting it to apply
        to the episode they had just watched. Nothing on this menu says
        "show", and 264 PUTs is not a thing to infer from "Mark as Watched".
        Whole-season marking still exists, on the season row's own menu,
        where the word "Season" is in the label.

        A MOVIE still marks every available file: those are versions of one
        thing, and leaving them disagreeing would make the card's watched
        badge depend on which version happened to be played."""
        if self.media.get("seasons"):
            ids = [self.play_file_id] if self.play_file_id else []
        else:
            ids = [f.get("id") for f in (self.media.get("files") or [])
                   if f.get("available") and f.get("id")]
        if not ids:
            kodigui.ERROR("detail.py: no available files to mark watched")
            return
        try:
            for fid in ids:
                client.update_watched(fid, watched)
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: watched toggle failed: {0}".format(exc))
            return
        # Not just the hero: on a show the grid's tick for this episode has
        # changed too, and finishing one moves next-up along.
        self.refresh_watch_progress()
        self._render_actions(client, self.media)

    def _open_season_options(self) -> bool:
        """7.2's panel for the focused SEASON, matching the real Apple TV
        app's: "Play Season" over "Mark Season as Watched", under an
        "Options" eyebrow with the season's name and its available-episode
        count. Its Cancel row is deliberately absent -- the context key that
        opens this also dismisses it, which is the same reason
        option_keys() only adds Cancel for the detail-pill variant.

        Returns whether the press was consumed."""
        if self.season_list is None:
            return False
        item = self.season_list.getSelectedItem()
        season = item.dataSource if item is not None else None
        if not season:
            return False
        client = self._get_client()
        if not client:
            return False

        episodes = season.get("episodes") or []
        playable = [(e, f) for e in episodes
                    for f in ([next((x for x in (e.get("files") or [])
                                     if x.get("available")), None)] or [])
                    if f]
        if not playable:
            return False

        progress_map = progress.fetch_many(client, [f.get("id") for _e, f in playable])
        watched = sum(1 for _e, f in playable
                      if (progress_map.get(f.get("id")) or {}).get("completed"))
        keys = [cardoptions.PLAY_SEASON]
        if watched < len(playable):
            keys.append(cardoptions.MARK_SEASON_WATCHED)
        if watched:
            keys.append(cardoptions.MARK_SEASON_UNWATCHED)

        picked = cardoptions.show(
            eyebrow="Options",
            title=season.get("title") or "Season {0}".format(season.get("season_number") or 0),
            subtitle="{0} available episode{1}".format(
                len(playable), "" if len(playable) == 1 else "s"),
            keys=keys,
        )
        if picked == cardoptions.PLAY_SEASON:
            self._play_season(playable, progress_map)
        elif picked in (cardoptions.MARK_SEASON_WATCHED,
                        cardoptions.MARK_SEASON_UNWATCHED):
            # season["id"] is the server's Season id, which is what the
            # season-scoped endpoint keys on. Absent on older payloads, and
            # _mark_season falls back to a request per episode then.
            self._mark_season(client, playable,
                              picked == cardoptions.MARK_SEASON_WATCHED,
                              season_id=season.get("id"))
        return True

    def _play_season(self, playable: list, progress_map: dict):
        """Start the season at its first unwatched episode, or its first if
        the whole season is done -- the same rule _next_up_episode applies to
        a show, scoped to this one season."""
        pick = next(((e, f) for e, f in playable
                     if not (progress_map.get(f.get("id")) or {}).get("completed")),
                    playable[0])
        episode, f = pick
        self.play_file_id = f.get("id")
        self.play_duration_ms = f.get("duration_ms") or 0
        position_ms, completed = progress.position_of(progress_map.get(f.get("id")))
        from .player import PlayerWindow
        self._renew_profile_token_for(self.play_duration_ms - (position_ms or 0))
        PlayerWindow.open(
            file_id=f.get("id"),
            media_id=self.media_id,
            resume_ms=(position_ms if position_ms and not completed else None),
            title=episode.get("title") or self.media.get("title"),
            # Hand over the art we already resolved, so 8.6's opening
            # card can show the backdrop from its FIRST frame. The player
            # resolves its own copy once metadata lands, but that is a round
            # trip later -- long enough that a fast open showed a black card
            # and nothing else.
            backdrop=self.getProperty("hero_backdrop"),
            logo=self.getProperty("hero_logo"),
        )

    def _mark_season(self, client: MediaServerClient, playable: list, watched: bool,
                     season_id=None):
        """Mark every available episode in the season watched/unwatched.

        ONE request when the server can take it. This used to be a PUT per
        file, because there was no season-scoped endpoint -- "a 39-episode
        season really is 39 requests". Server 0.9.28 added
        PUT /seasons/{id}/watched with the same semantics, so a season is now
        one write.

        The per-file loop stays as the fallback, for a season we have no id
        for and for a server too old to know the route (404). Both paths run
        on the GUI thread deliberately: the grid must not repaint from
        half-applied state, and this is a deliberate, infrequent action."""
        if season_id:
            try:
                answer = client.update_season_watched(season_id, watched) or {}
                # `updated` is rows written; zero is legitimate, not a
                # failure -- a season already in the requested state writes
                # nothing.
                log.info(f"detail: season {season_id} -> watched={watched}, "
                         f"{answer.get('updated')} row(s) in one request")
                self.refresh_watch_progress()
                return
            except http.ApiError as exc:
                log.warning(f"detail: season-scoped mark failed ({exc}); "
                            f"falling back to one request per episode")
        failed = 0
        for _episode, f in playable:
            try:
                client.update_watched(f.get("id"), watched)
            except http.ApiError as exc:
                failed += 1
                log.warning(f"detail: mark season {f.get('id')} failed: {exc}")
        if failed:
            cardoptions.alert(
                kodigui.ADDON.getAddonInfo("name"),
                "Could not update {0} of {1} episodes.".format(failed, len(playable)),
                error=True)
        self.refresh_watch_progress()

    def _open_card_options(self, focus_id) -> bool:
        """7.2's panel for the focused episode or More Like This card.
        Returns whether the press was consumed."""
        client = self._get_client()
        if not client:
            return False

        if focus_id == self.EPISODE_GRID_PANEL and self.episode_list is not None:
            item = self.episode_list.getSelectedItem()
            if item is None or not item.dataSource:
                return False
            episode = item.dataSource.get("episode") or {}
            f = item.dataSource.get("file")
            completed = bool(item.getProperty("watched"))
            # An episode gets a deliberately shorter set. "Go to Details" is
            # meaningless (this IS the show's detail), and Watchlist and
            # Continue Watching are title-level, not episode-level -- 7.2's
            # conditions are written for a title, so applying them whole to
            # an episode would offer three rows that do nothing.
            keys = []
            if f:
                keys.append(cardoptions.PLAY)
                keys.append(cardoptions.MARK_UNWATCHED if completed else cardoptions.MARK_WATCHED)
            picked = cardoptions.show(
                title=item.getLabel() or "",
                subtitle=item.getProperty("caption") or "",
                keys=keys,
                resume=bool(item.getProperty("progress_fill")) and not completed,
            )
            if picked == cardoptions.PLAY:
                self._episode_clicked()
            elif picked in (cardoptions.MARK_WATCHED, cardoptions.MARK_UNWATCHED):
                watched = picked == cardoptions.MARK_WATCHED
                fid = (f or {}).get("id")
                if fid:
                    try:
                        client.update_watched(fid, watched)
                    except http.ApiError as exc:
                        kodigui.ERROR("detail.py: episode watched toggle failed: {0}".format(exc))
                        return True
                    item.setProperty("watched", "1" if watched else "")
                    if watched:
                        item.setProperty("progress_fill", "")
            return True

        if focus_id in (self.SIMILAR_LIST, self.DISCOVER_LIST):
            lst = (self.discover_list if focus_id == self.DISCOVER_LIST
                   else self.similar_list)
            if lst is None:
                return False
            item = lst.getSelectedItem()
            if item is None or not item.dataSource:
                return False
            data = item.dataSource
            media_id = data.get("id") or data.get("media_id")
            keys = cardoptions.option_keys(
                in_library=bool(media_id),
                fully_watched=bool(item.getProperty("watched")),
                has_progress=False,
                on_watchlist=bool(item.getProperty("watchlisted")),
                in_continue_watching=False,
            )
            picked = cardoptions.show(
                title=item.getLabel() or "",
                subtitle=item.getProperty("caption_meta") or "",
                keys=keys,
            )
            # Every remaining action on a related title is really "go look at
            # it", so both routes land on its own detail screen rather than
            # reimplementing play/watchlist against a card we do not own.
            if picked in (cardoptions.PLAY, cardoptions.DETAILS):
                self._similar_clicked(focus_id)
            return True

        return False

    def _available_files(self) -> list:
        """Every file the Edition pill may offer -- which on a SHOW is not
        every file the show has.

        `/media/{id}` on a series answers with a FLAT `files` list covering
        every episode of every season, each entry tagged with its
        `episode_id` (100 entries for The 100). Read whole, it made the pill
        offer a scrolling list of "1080p" rows -- other episodes -- on an
        episode that has exactly one file, and picking one would have
        pointed Play at a different episode entirely.

        Editions are a property of ONE episode, so the list is scoped to the
        episode the primary button plays. Most shows then have <2 files here
        and the pill hides itself, which is the correct answer."""
        files = [f for f in (self.media.get("files") or []) if f.get("available")]
        if (self.media.get("media_type") or "") != "tv":
            return files
        episode_id = next((f.get("episode_id") for f in files
                           if f.get("id") == self.play_file_id), None)
        # No episode chosen yet (or a server that stopped tagging them): offer
        # nothing rather than the whole show. Hiding the pill is recoverable;
        # a pill that silently switches episodes is not.
        if not episode_id:
            return []
        return [f for f in files if f.get("episode_id") == episode_id]

    def _version_row_parts(self, f: dict, *, full: bool = False) -> tuple[str, str]:
        """(label, detail) for one edition, split across the two columns the
        options panel's rows draw.

        `full` adds 7.7's remaining two fields, video codec and size GB. Only
        the Edition picker passes it: that window is sized for the long
        string, and it is the one place where "which of these do I want" is
        the actual question. The same parts feed the options panel's own
        subtitle, which has one narrow line to name the file in hand and is
        better served by the short form.

        The EDITION leads, which neither the app nor the web UI does. Both
        render Hugo's two files as "4K ..." and "HD ...", with no hint that
        one is the 3D cut -- the only reason anyone would pick it. 7.7 asks
        for edition headers on a title with more than one, so it goes first,
        and a file with no edition name falls back to its resolution rather
        than leading with a blank.

        An earlier pass dropped codec and size entirely, because on the
        780-wide panel they truncated the fields that decide the choice
        ("3D . 1080p . H264 . DTS-HD ..."). Widening the Edition window
        rather than cutting the data is the better trade, and 7.7 asks for
        all of it."""
        fmt = f.get("format") or {}
        video = fmt.get("video") or {}
        audio = fmt.get("audio") or {}
        # MediaFormatInfo only -- NEVER the raw `audio_codec` beside it. That
        # field is the first-pass probe, and it is exactly what reported a
        # DTS-HD MA or Atmos track on a big remux as plain "DTS"; tofa fixed
        # that in 0.9.27 by taking a second look and correcting `format.audio`,
        # so falling back to the raw codec would reintroduce the wrong answer
        # on precisely the files the fix was written for. A null `format.audio`
        # means the server is saying it does not know -- which is a reason to
        # print nothing, not to guess.
        audio_label = " ".join(x for x in (
            audio.get("label") or "",
            audio.get("channels_label") or "",
        ) if x)
        # Never the raw `resolution` ("1920x1080"): the badge row, the pill
        # and this list all name the same file, and only this one was
        # spelling it in dimensions. `_resolution_fallback` is what the badge
        # uses.
        resolution = fmt.get("resolution_label") or self._resolution_fallback(f)
        dynamic_range = (video.get("label")
                         if video.get("dynamic_range") not in (None, "sdr") else "")
        # 7.7's order, which is also least-to-most disposable: a truncated
        # tail costs the size before it costs the resolution.
        codec = tracks.video_codec_label(f.get("video_codec")) if full else ""
        size = tracks.file_size_label(f.get("file_size")) if full else ""
        edition = f.get("edition") or ""
        if edition:
            return edition, _dot_join(resolution, dynamic_range, codec, audio_label, size)
        # A file with no edition name leads with its resolution instead of a
        # blank, so the detail must not repeat it.
        return (resolution or "Version"), _dot_join(dynamic_range, codec, audio_label, size)

    def _version_row_label(self, f: dict) -> str:
        """The two columns as one string, for the Options panel's subtitle --
        which names the file this dialog is about and has one line to do it
        in."""
        label, detail = self._version_row_parts(f)
        return _dot_join(label, detail)

    def _render_version_pill(self):
        """The pill only exists for a title with more than one file, which is
        the minority -- 7.7 gates its whole file-picker surface the same way,
        showing the edition eyebrow headers only where a second edition
        exists."""
        available = self._available_files()
        if len(available) < 2:
            self.setProperty("show_version", "")
            self.setProperty("version_label", "")
            return
        self.setProperty("show_version", "1")
        current = next((f for f in available if f.get("id") == self.play_file_id),
                       available[0])
        self.setProperty("version_label", self._version_pill_label(current))

    @classmethod
    def _version_pill_label(cls, f: dict) -> str:
        """What the edition pill says: a NAME, or the resolution said short.

        The pill is laid out around a label the width of "1080p" -- the
        action row packs four pills at fixed positions, and
        `action_pill_content` measures `label_text` to centre the group. A
        longer string is Kodi's to clip.

        So `resolution` must never reach it. It is raw dimensions
        ("1920x1080"), which clipped to "192..." -- a label that says less
        than nothing, on a title whose format badge said "1080p" two lines
        above. Seen on the demo server's Big Buck Bunny, which has two files
        and no edition names, while taking the add-on's screenshots.

        `_resolution_fallback` is the same derivation that badge uses, so the
        pill and the badge now agree by construction rather than by luck.
        A real edition NAME still leads: "Director's Cut" is what the viewer
        is choosing between, and 1080p vs 4K only becomes the distinguishing
        fact when nobody has named the files."""
        fmt = f.get("format") or {}
        return (f.get("edition") or fmt.get("resolution_label")
                or cls._resolution_fallback(f) or "Version")

    def _version_clicked(self):
        """Pick which of the title's own FILES plays.

        This used to live behind the Options pill under a "Quality" heading,
        which is wrong twice over: 7.7 reserves Options for pre-play
        Quality/Audio/Subtitles, and the thing being picked is the EDITION.

        Drawn by the options panel in its flat mode rather than by
        PickerDialog. The two sat one keypress apart on the same action row
        and looked like different products -- trailing check vs leading,
        accent-filled focus vs accent wash. PickerDialog keeps its own look
        because Browse's Sort/Filter buttons are pixel-matched to the real
        app; this pill is not.
        """
        available = self._available_files()
        if len(available) < 2:
            return
        rows = []
        for f in available:
            label, detail = self._version_row_parts(f, full=True)
            rows.append({"label": label, "detail": detail})
        selected = next((i for i, f in enumerate(available)
                         if f.get("id") == self.play_file_id), 0)
        picked = playoptions.show_editions(
            title="Edition",
            subtitle=self.media.get("title") or "",
            rows=rows,
            selected_idx=selected,
        )
        if picked is None:
            return
        self._select_file(available[picked])

    def _select_file(self, chosen: dict):
        """Adopt a file as the one Play will use, and re-render everything
        that describes it. The app does NOT do this -- its hero badges keep
        describing a different file than the one its own version pill says is
        selected -- but with a delivery caveat on screen the two disagreeing
        would be worse than useless."""
        self.play_file_id = chosen.get("id")
        self.play_selection = playoptions.Selection()
        self.play_duration_ms = chosen.get("duration_ms") or 0
        position_ms, completed = self._progress(self._get_client(), self.play_file_id, chosen)
        self._apply_primary_progress(position_ms, completed)
        self._render_format_badges(chosen)
        self._render_version_pill()

    def onReInit(self):
        """Kodi re-inits this window when the player above it closes, which
        is exactly when the position it is describing has moved."""
        self.refresh_watch_progress()
        self.restore_focus()

    #: The Play pill is where <defaultcontrol> already lands, so a click on
    #: it is not worth returning to -- and it opens the player, after which
    #: landing back on Play is exactly right.
    FOCUS_MEMORY_IGNORE = (5210,)

    def focus_memory_list(self, control_id):
        """This page's card rows. A Detail page can open ANOTHER Detail page
        (More Like This) or a Person page, and comes back to the same
        problem the sections have."""
        return {
            self.CAST_LIST: self.cast_list,
            self.CREW_LIST: self.crew_list,
            self.SIMILAR_LIST: self.similar_list,
            self.DISCOVER_LIST: self.discover_list,
            self.SEASON_SIDEBAR_LIST: self.season_list,
            self.EPISODE_GRID_PANEL: self.episode_list,
        }.get(control_id)

    def refresh_watch_progress(self):
        """Re-read this page's positions and repaint what shows them.

        See progress.py. Two surfaces here: the action row's Resume/Play pill
        and its progress sliver, and -- for a show -- the episode grid's
        per-episode bars and watched ticks.

        For a show the primary pill may now point at a DIFFERENT episode,
        since finishing one moves next-up along, so the episode that pill
        plays is re-derived rather than just re-measured."""
        if not self.is_playable or not self.play_file_id:
            return
        client = self._get_client()
        if not client:
            return

        # The caller's episode is an answer for ARRIVAL, not a permanent pin.
        # Continue Watching hands over the file its card stands for, and
        # _next_up_episode's rule (0) prefers it over everything it could
        # infer -- correct on the way in, wrong from here on, because by the
        # time we refresh the viewer has watched something and the inference
        # is now the fresher answer.
        #
        # Left set, it survives playback: arriving on E4's card, playing E3
        # from the grid and coming back offered "Play S1 E4" while E3 sat at
        # 20% and E4 was already completed -- the page pinned to an episode
        # the viewer had finished, ignoring the one they were in the middle
        # of. Reported from the box.
        #
        # Cleared HERE rather than in rule (0) itself because the initial
        # load derives twice (the hero and the episode grid), and consuming
        # it on first use would leave those two disagreeing.
        self.prefer_file_id = None

        # A refresh that cannot READ progress must change nothing. Every
        # read below fails to an empty answer, and an empty answer here is
        # not "we don't know" but a set of confident, wrong statements:
        # nothing is watched, so next-up is episode one, so the pill says
        # Play S1 E1 and the grid jumps back to it. Measured on the box
        # 2026-08-09 with an expired profile token -- see
        # MediaServerClient.profile_token_expired, which is the other half
        # of that fix (this half also covers the server merely being
        # unreachable for the second it took to come back from playback).
        try:
            if self.getProperty("is_tv"):
                seasons = self.media.get("seasons") or []
                ep, f = self._next_up_episode(client, seasons, required=True)
                if ep and f:
                    self.play_file_id = f.get("id")
                    self.play_duration_ms = f.get("duration_ms") or 0
                    # Next-up moved to another episode, and editions are scoped
                    # to one episode -- so the pill can appear, vanish or
                    # relabel.
                    self._render_version_pill()
                    # The hero's other per-episode blocks move with it: the
                    # A/V badges describe the file that WILL play, and the
                    # synopsis describes the episode it belongs to. _load
                    # paints both after picking next-up (badges then synopsis,
                    # the order _layout_hero_stack needs); the refresh path
                    # only ever repainted the pill, so after finishing an
                    # episode the badges and synopsis stayed on the one just
                    # watched -- reported from the box as the Details synopsis
                    # still describing the previous episode.
                    self._render_format_badges(f)
                    self._apply_episode_synopsis()
                self._refresh_episode_progress(client)
                # The grid's landing rule ("select what the pill offers") was
                # only ever applied on render, so after watching, coming back
                # and pressing down the viewer arrived on the episode that was
                # next up when the page FIRST loaded -- one they had since
                # finished. Reported from the box. Re-applied here so the two
                # agree again.
                self._select_episode_by_file(client, seasons, self.play_file_id)

            primary = progress.fetch_many(
                client, [self.play_file_id], required=True).get(self.play_file_id)
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: leaving the page as it was, progress "
                          "refresh failed: {0}".format(exc))
            return

        position_ms, completed = progress.position_of(primary)
        # Same suppression the first render applies: a dismissed title keeps
        # its position on the server but must stop offering Resume here.
        if self._is_dismissed(client, self.media.get("id") or self.media_id, position_ms):
            position_ms, completed = 0, False
        self._apply_primary_progress(position_ms, completed)

        # Re-pack the action row, because what just changed is WHICH pills are
        # visible, and the packer only ever positions the pills it was told
        # about. XML drives each pill's <visible> straight off these
        # properties, so a pill that appears now lands back on its TEMPLATE x
        # while its neighbours keep the packed x they were given on the first
        # render.
        #
        # That is not a cosmetic drift, it is a collision. Watching an unwatched
        # episode flips show_rewatch on: Rewatch reappears at its template 658
        # while Watchlist is still parked at the 664 it was packed to when
        # Rewatch was absent -- 244px of Watchlist inside Rewatch's 270, six
        # pixels apart. Reported from the box after returning from playback.
        #
        # _render_version_pill above can flip show_version the same way when
        # next-up moves to an episode with different editions, so this covers
        # both writers rather than just the Rewatch one.
        self._wire_pill_navigation()

    def _episode_progress_props(self, ep: dict, f, prog) -> dict:
        """One episode row's watched tick, progress capsule and meta line --
        the three things that describe where the viewer is in it.

        Computes, writes nothing. One producer, shared by the grid builder
        and the refresh below, so a repainted row cannot drift from a
        freshly-built one; splitting the write out is what lets the refresh
        skip the rows that have not changed.

        The capsule shows only while genuinely mid-episode. 7.1 gates it on
        "0 < progress < 100 and not watched", so a finished episode shows the
        checkmark alone rather than a full bar underneath saying the same
        thing."""
        completed = bool(prog and prog.get("completed"))
        runtime_minutes = _episode_runtime_minutes(ep, f)

        pct = 0.0 if completed else self._progress_pct(prog, f)
        left_label = ""
        fill = ""
        if pct:
            # episode-progress/, not the shared flat progress/ strips: the bar
            # sits flush with the still's corners now, so it needs the set cut
            # to this card's silhouette. See tools/gen_episode_assets.py.
            step = max(2, min(100, int(round(pct * 100 / 2.0)) * 2))
            fill = "episode-progress/{0}.png".format(step)
            if runtime_minutes:
                remaining = int(round(runtime_minutes * (1.0 - pct)))
                if remaining > 0:
                    left_label = "{0}m left".format(remaining)

        num = ep.get("episode_number")
        return {
            "watched": "1" if completed else "",
            "progress_fill": fill,
            # 7.1's meta line: "E5 - 42m - 4K - 12m left".
            "caption": _dot_join(
                u"E{0}".format(num) if num is not None else "",
                _runtime_str(runtime_minutes),
                *(self._format_badge_labels(f)[:3] if f else []),
                left_label,
            ),
        }

    def _apply_episode_progress(self, mli, ep: dict, f, prog) -> bool:
        """Write those three, skipping any that already say what they say.

        The skip is not a micro-optimisation. Every ListItem setter takes
        Kodi's frame-move guard, so on a busy screen a write can wait a whole
        frame -- and at 4K on the box a frame is ~66ms (see issue #11). The
        refresh below used to repaint EVERY row after one episode was
        watched; on a 22-episode season that is 66 locked writes to change
        three. Now it is three, which is what lets the builder hand these
        rows to Kodi offscreen.

        `ManagedListItem.getProperty` reads its own dict and takes no lock,
        so the comparison itself is free."""
        wrote = False
        for key, value in self._episode_progress_props(ep, f, prog).items():
            if mli.getProperty(key) != value:
                mli.setProperty(key, value)
                wrote = True
        return wrote

    def _refresh_episode_progress(self, client: MediaServerClient):
        """Repaint the episode grid's ticks and capsules in place.

        In place, not a re-render: rebuilding the grid would throw away the
        viewer's scroll position and selection, and the only things that can
        have changed are the ones _apply_episode_progress writes. Spoiler
        blurring is deliberately left alone for the same reason -- it is
        derived from which episode is first unwatched, and re-deciding that
        would un-blur stills under the viewer mid-page.

        Raises http.ApiError rather than repainting from a failed read: the
        per-row writes below are no-ops on an empty map, but the counter is
        not -- it would read "0/22 watched" off a request that never
        answered. refresh_watch_progress catches it."""
        if self.episode_list is None or not len(self.episode_list):
            return
        by_file = {}
        for mli in self.episode_list:
            f = (mli.dataSource or {}).get("file") or {}
            if f.get("id"):
                by_file.setdefault(f["id"], []).append(mli)
        if not by_file:
            return
        fresh = progress.fetch_many(client, list(by_file), required=True)
        watched = 0
        repainted = 0
        for mli in self.episode_list:
            source = mli.dataSource or {}
            f = source.get("file") or {}
            record = fresh.get(f.get("id"))
            if record and record.get("completed"):
                watched += 1
            if f.get("id") in fresh and self._apply_episode_progress(
                    mli, source.get("episode") or {}, f, record):
                repainted += 1
        # Logged because the whole point of the change-gate is that this
        # number is small: coming back from one episode should repaint one
        # row. A run that repaints the whole grid means something upstream
        # is producing a different value for rows that did not change.
        log.info(f"detail: episode progress repainted {repainted}/"
                  f"{len(self.episode_list)} rows")
        self.setProperty(
            "episodes_watched_count", "{0}/{1} watched".format(watched, len(self.episode_list)))

    def _select_episode_by_file(self, client: MediaServerClient, seasons: list, file_id) -> None:
        """Move the episode grid's selection onto `file_id`.

        Cheap when that episode is already on screen -- just a reselect. When
        it is not, the viewer finished a season while they were away and the
        next one lives on a different page of the grid, so the season rail
        and the grid are both re-rendered; _render_episode_grid then lands on
        it by its own rule.

        Never touches focus, only the selection, and only for a grid that is
        not currently focused: moving the cursor under someone who is already
        reading the list is the one case where the old position is the right
        one."""
        if self.episode_list is None or not file_id:
            return
        if self.getFocusId() == self.EPISODE_GRID_PANEL:
            return
        for pos, mli in enumerate(self.episode_list):
            f = (mli.dataSource or {}).get("file") or {}
            if str(f.get("id")) == str(file_id):
                self.episode_list.setSelectedItemByPos(pos)
                return

        season_number = next(
            (s.get("season_number") for s in seasons
             for e in (s.get("episodes") or [])
             for candidate in (e.get("files") or [])
             if str(candidate.get("id")) == str(file_id)),
            None)
        if season_number is None or season_number == self.selected_season_number:
            return
        self.selected_season_number = season_number
        self._render_season_sidebar(seasons, season_number)
        self._render_episode_grid(client, seasons, season_number)

    def _fresh_resume_ms(self) -> int:
        """The Resume pill's position, re-read at the moment it is pressed.

        self.resume_ms is as old as this page's last load, and the page does
        not reload when playback hands back -- so playing, backing out and
        playing again resumed from the first position twice. Only the Resume
        path asks; Rewatch means zero and must not be second-guessed."""
        client = self._get_client() if self.play_file_id else None
        if not client:
            return self.resume_ms
        return progress.resume_position_ms(
            client, self.play_file_id, fallback=self.resume_ms) or 0

    def _renew_profile_token_for(self, runtime_ms: int) -> None:
        """Pre-flight the profile token for something about to play.

        Thin wrapper over profile_select.renew_for_playback, which owns the
        reasoning -- this only drops the page's own client, since it is
        holding the token that was about to die."""
        if profile_select.renew_for_playback(runtime_ms):
            self.client = None

    def _play(self, resume_ms: int):
        if not self.is_playable or not self.play_file_id:
            return
        from .player import PlayerWindow

        self._renew_profile_token_for((self.play_duration_ms or 0) - (resume_ms or 0))

        PlayerWindow.open(
            file_id=self.play_file_id,
            media_id=self.media_id,
            resume_ms=resume_ms or None,
            title=self.media.get("title"),
            selection=self.play_selection,
            # 8.6's opening card wants backdrop art and the title LOGO from
            # its first frame. The player resolves both itself, but only
            # after /media/{id} comes back -- measured at ~3.5s on a
            # transcode, during which the card showed the plain-text title
            # fallback on black and then visibly swapped to the logo.
            # This page already has both resolved for its hero.
            backdrop=self.getProperty("hero_backdrop"),
            logo=self.getProperty("hero_logo"),
        )

    def _request_clicked(self):
        """Ask the server for this title (7.9).

        A SHOW always opens 7.6's dialog first, one season or twenty:
        "which seasons" is a question only the viewer can answer, and even a
        single-season show carries the quality decisions. That reverses the
        earlier skip-the-dialog rule, which was measured on the Apple TV app;
        the macOS "tofa Desktop Player" shows the dialog every time and is
        the newer client (Adrian's call, 2026-08-08).

        A MOVIE has no seasons, so it only gets the dialog when there IS a
        decision -- HD vs 4K, or which *arr quality profile. With neither it
        fires straight away, the way the app does.
        """
        client = self._get_client()
        if not client or not self.tmdb_id or not self.content_media_type:
            return
        from .requestseasons import RequestSeasonsDialog

        profiles, default_profile_id = self._profile_choices(client)
        chosen = RequestSeasonsDialog.ask(
            title=self.getProperty("hero_title") or "",
            media_type=self.content_media_type,
            seasons=self.disc_seasons,
            is4k_capable=self.is4k_capable,
            can_request_4k=self._can_request_4k(client),
            requested=self._already_requested_seasons(),
            profiles=profiles,
            default_profile_id=default_profile_id,
        )
        if not chosen:
            return              # cancelled, or nothing ticked
        try:
            client.create_request(
                self.content_media_type,
                self.getProperty("hero_title") or "",
                self.tmdb_id,
                seasons=chosen.get("seasons"),
                is4k=chosen.get("is4k"),
                tvdb_id=self._disc_tvdb_id(),
                quality_profile_id=chosen.get("quality_profile_id"),
            )
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: request failed: {0}".format(exc))
            self._notify("Could not request this title")
            return
        self._refresh_request_state()

    def _retry_request_clicked(self):
        client = self._get_client()
        if not client or not self.request_id:
            return
        try:
            client.retry_request(self.request_id)
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: retry request failed: {0}".format(exc))
            self._notify("Could not retry the request")
            return
        self._refresh_request_state()

    def _cancel_request_clicked(self):
        client = self._get_client()
        if not client or not self.request_id:
            return
        try:
            client.cancel_request(self.request_id)
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: cancel request failed: {0}".format(exc))
            self._notify("Could not cancel the request")
            return
        self._refresh_request_state()

    def _can_request_4k(self, client) -> bool:
        """Whether this viewer may ask for 4K at all.

        Server-side permission, not a preference: offering a choice the server
        will refuse is worse than not offering it. Cached for the life of the
        page -- it cannot change while a detail screen is open."""
        if getattr(self, "_can_4k", None) is None:
            try:
                self._can_4k = bool((client.me() or {}).get("can_request_4k"))
            except http.ApiError:
                self._can_4k = False
        return self._can_4k

    def _profile_choices(self, client) -> tuple:
        """(profiles, default_id) for the service this title routes to, or
        ([], None) when this viewer has no say.

        ADMINS ONLY, which is what the web and desktop clients do: a quality
        profile is an operator's setting, and the household's other viewers
        should get the instance default without being asked to pick between
        "Bluray Remux" and "Web 480p". Cached for the life of the page --
        profiles do not change while a detail screen is open.
        """
        if getattr(self, "_profiles_cache", None) is None:
            self._profiles_cache = ([], None)
            try:
                if (client.me() or {}).get("is_admin"):
                    payload = client.quality_profiles() or {}
                    service = ("radarr" if self.content_media_type == "movie"
                               else "sonarr")
                    self._profiles_cache = (
                        list(payload.get(service) or []),
                        payload.get("{0}_default_profile_id".format(service)),
                    )
            except http.ApiError as exc:
                kodigui.ERROR("detail.py: quality profiles failed: {0}".format(exc))
        return self._profiles_cache

    def _already_requested_seasons(self) -> set:
        """Season numbers this show already has on request, so 7.6 can show
        them checked and inert rather than offering them twice.

        Straight off the detail payload's `request_seasons`, which the server
        fills for exactly this. Scanning GET /requests for a matching tmdb_id
        answered the same question a whole request list later.

        A season whose own request was DENIED or FAILED is not "already
        requested" -- it is the one you would most want to ask for again --
        so it is left selectable, matching the web client."""
        numbers = set()
        for season in (self.discovery_detail or {}).get("request_seasons") or []:
            if (season.get("status") or "").lower() in ("denied", "failed"):
                continue
            try:
                numbers.add(int(season.get("season_number")))
            except (TypeError, ValueError):
                continue
        return numbers

    def _disc_tvdb_id(self):
        try:
            return int(self.discovery_detail.get("tvdb_id")) if self.discovery_detail else None
        except (TypeError, ValueError):
            return None

    def _refresh_request_state(self):
        """Re-read the title and redraw the pill row.

        Re-fetched rather than assumed: the server decides what the request
        actually became -- `requested` where this viewer is auto-approved,
        `pending_approval` where they are not -- and guessing would show the
        wrong pill to exactly the viewers whose requests need approving.
        """
        client = self._get_client()
        if not client or not self.tmdb_id or not self.content_media_type:
            return
        try:
            disc = client.discovery_detail(self.content_media_type, self.tmdb_id) or {}
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: request state refresh failed: {0}".format(exc))
            return
        self.discovery_detail = disc
        self._render_request_state(disc)
        self._wire_pill_navigation()
        self._layout_hero_stack()
        self._focus_request_row()

    def _page1_focus_id(self) -> int:
        """The pill focus should rest on: whichever one actually DOES
        something, left to right.

        Never the primary while it is inert -- "Requested", "Coming to
        library" and the rest are statements, and an accent ring around a pill
        that does nothing when pressed reads as a broken button. They are also
        disabled outright by _wire_pill_navigation(), so focus could not stay
        there anyway.
        """
        # The failed page has exactly one control on it, and every pill is
        # hidden -- so this has to answer before any of them.
        if self.getProperty("detail_state") == "error":
            return self.PILL_RETRY
        if self._primary_is_actionable():
            return self.PILL_PRIMARY
        if self.getProperty("show_cancel_request"):
            return self.PILL_CANCEL_REQUEST
        if self.getProperty("show_watchlist"):
            return self.PILL_WATCHLIST
        return self.PILL_PRIMARY

    def _focus_request_row(self):
        target = self._page1_focus_id()
        if target == self.PILL_PRIMARY and not self._primary_is_actionable():
            return              # nothing on this page takes focus
        xbmc.executebuiltin("SetFocus({0})".format(target))

    def _notify(self, message: str):
        """8.9's toast, in our own skin. This window carries the fragment
        (see skin/fragments.py:toast), so the message has somewhere to draw;
        it used to be Kodi's own notification, in the host skin."""
        toast.show(message)

    def _toggle_watchlist(self):
        """Which endpoint applies is decided by what the title carries, not
        by preference: a held title has a media id and frequently no tmdb id
        at all, so the content endpoint cannot serve it, and an out-of-library
        one is the reverse. Getting it wrong fails silently."""
        client = self._get_client()
        if not client:
            return
        adding = not self.on_watchlist
        try:
            if self.media_id:
                (client.watchlist_add if adding else client.watchlist_remove)(self.media_id)
            elif self.tmdb_id and self.content_media_type:
                if adding:
                    client.watchlist_add_content(self.content_media_type, self.tmdb_id)
                else:
                    client.watchlist_remove_content(self.content_media_type, self.tmdb_id)
            else:
                kodigui.ERROR("detail.py: watchlist toggle has neither media_id nor tmdb_id")
                return
        except http.ApiError as exc:
            kodigui.ERROR("detail.py: watchlist toggle failed: {0}".format(exc))
            return
        self.on_watchlist = adding
        self.setProperty("watchlist_glyph", chr(icon_glyphs.BOOKMARK_OFF if self.on_watchlist else icon_glyphs.BOOKMARK))
