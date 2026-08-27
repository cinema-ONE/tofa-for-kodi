# -*- coding: utf-8 -*-
"""Merged Home/Browse/Discover/Search/Settings window -- one persistent
window instead of five, avoiding the full-screen redraw a doModal()
open/close on every tab switch caused. Sections are added incrementally;
a target not yet in SECTION_TARGETS falls back to opening its own old
standalone window. Window.Property names are shared window-wide (unlike
control ids) -- a new section can't reuse another's property name."""
from __future__ import annotations

import datetime
import os
import random
import threading
import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui

from . import (cardoptions, cards, focusmemory, kodigui, navbar, profile_select,
               splash, theme)
from .. import (api, artcache, auth, cloud, episodes, home_rows, http, langcodes, log,
                textmetrics,
                playbackprefs, prefetch, progress, regional, search_history,
                serverversion, settings_options, settings_pages, signin)
from .. import avatar_presets
from ..api import MediaServerClient
from ..skin import icon_glyphs
from ..skin import tokens as T

ADDON = xbmcaddon.Addon()
_ = ADDON.getLocalizedString


def _dot_join(*parts) -> str:
    return u" • ".join(p for p in parts if p)


def _card_meta_left(item: dict) -> str:
    """A card caption's leading slot: the year, or `S1 E1` for an episode.

    Measured off the real Apple TV app's Continue Watching row, where a
    show's card reads "S1 E1" in accent where a film's reads "2011" in the
    caption's own tertiary. The year of a series is not what someone
    part-way through season 3 wants in that slot."""
    season, episode = item.get("season_number"), item.get("episode_number")
    if season is not None and episode is not None:
        return theme.accent_in_accent(episodes.number_label(
            season, episode, item.get("episode_number_end")))
    return _item_year(item)


def _item_year(item: dict) -> str:
    year = item.get("year")
    if year:
        return str(year)
    release_date = item.get("release_date") or item.get("air_date")
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        return release_date[:4]
    return ""


def _library_count(lib: dict) -> str:
    """The sidebar's per-library count, grouped the way this Kodi's region
    writes numbers: 10,738 on a US box, 10.738 on a German one. Kodi keeps
    that rule to itself, so regional.py digs it out (see its docstring)."""
    for key in ("item_count", "media_count", "count", "total", "title_count"):
        val = lib.get(key)
        if isinstance(val, int):
            return regional.number(val)
    return ""


def _history_latest_per_title(items: list) -> list:
    """One card per title, keeping its most recent watch.

    /watch/history is a SESSION log: every play is its own row, so watching
    the same film three times returns three entries with distinct ids and
    started_at. Rendering it raw fills the grid with one poster repeated --
    which is what shipped, and what Adrian caught.

    The real app collapses them: 5 Hokum sessions on the server, one card on
    screen (captured 2026-07-31, Browse > History sorted "Last Watched").

    Nothing is dropped that the screen was showing: every duplicate carries
    the same title, poster and media_id, and the entry kept is the newest,
    so the caption's watched-date stays the one a viewer would expect.
    Episodes key on their own id, so two episodes of one show stay two
    cards -- they are different things watched, not the same thing twice.

    Order is preserved rather than re-sorted: the server already returns
    newest-first, and re-sorting here would silently override whatever
    ordering it applied."""
    seen = set()
    out = []
    for it in items:
        key = it.get("episode_id") or it.get("media_id") or it.get("id")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _format_history_date(started_at: str) -> str:
    """"Jul 28" from an ISO-8601 UTC timestamp, or "28. Jul" where the region
    puts the day first.

    Still avoids strftime's `%-d` (a glibc extension Android's bionic libc
    does not have); regional.day_and_month builds the string itself, so the
    flag never comes up, and the month name comes from Kodi's own localized
    strings rather than the C library's."""
    return regional.day_and_month(started_at)


# Unrecognized ListType keys fall back to a title-cased version of the key
# (see _discover_list_title) so a new server-side list still renders.
_DISCOVER_LIST_TITLES = {
    "trending-movies": "Trending Movies",
    "trending-tv": "Trending Shows",
    "popular-movies": "Popular Movies",
    "popular-tv": "Popular Shows",
    "top-rated-movies": "Top Rated Movies",
    "top-rated-tv": "Top Rated Shows",
    "upcoming-movies": "Coming Soon",
}


def _discover_list_title(list_type: str) -> str:
    if list_type in _DISCOVER_LIST_TITLES:
        return _DISCOVER_LIST_TITLES[list_type]
    return list_type.replace("-", " ").replace("_", " ").title()


# preferred_card_rating keeps legacy Rotten Tomatoes naming even after the
# 0.9.24 ratings unification: "rt" is Critics, "rt_audience" is Audience
# (confirmed by toggling the web app's Settings > Rating badge and re-reading
# the value). Maps to (preferred field, fallback field) -- the changelog
# guarantees the critics->audience direction ("a title with no critic score
# shows the audience one"); the reverse is ours, and safe because the badge
# renders a bare number with no label, so a fallback is indistinguishable.
# Card rating fields/default moved to theme.card_rating_text() -- the
# person screen needs the same rule.



def _discover_in_cinemas(item: dict) -> bool:
    """True when a title is in cinemas and not yet available at home.

    The real app puts a clapperboard chip on exactly these. Derived, not
    guessed: the rule below reproduces the server's own `still-in-cinemas`
    shelf membership on live data -- a theatrical date that has already
    passed, and no digital release date yet."""
    theatrical = item.get("theatrical_release_date")
    if not theatrical or item.get("digital_release_date"):
        return False
    return str(theatrical)[:10] <= _today_iso()


def _today_iso() -> str:
    import datetime

    return datetime.date.today().isoformat()


def _discover_open_card_numeral(score) -> str:
    """The open card's score numeral, which does NOT use the quality ramp.

    A deliberate one-step rule: 70 and over takes the ramp's good green,
    anything under it stays plain white, with no amber or red at all.
    Discover is a wall of
    artwork, and scattering amber and red numerals across it reads as a page
    with problems. It is not the ramp arriving here by another door -- one
    step, one threshold, one surface. Threshold is shared with web's
    `discoverScoreClass`; change both or neither.

    Both branches are explicit rather than letting one inherit the control's
    color: that label sits at the tertiary tier so the CRITICS/AUDIENCE words
    recede, and a numeral must not recede with them."""
    try:
        value = int(round(float(score)))
    except (TypeError, ValueError):
        return ""
    color = "FF5FD38A" if value >= theme.DISCOVER_CARD_SCORE_THRESHOLD else "FFFFFFFF"
    return u"[COLOR {0}]{1}[/COLOR]".format(color, value)


def _discover_scores_line(item: dict) -> str:
    """"78 CRITICS 76 AUDIENCE" for the wide focused Discover card.

    Always BOTH scores when both exist, deliberately ignoring the profile's
    preferred_card_rating -- the real app's focused card shows the pair
    regardless. Falls back to whichever single score is present, matching the
    server's own documented "a title with no critic score shows the audience
    one" rule, and to an empty line when neither is."""
    parts = []
    critics = item.get("tofa_critics_rating")
    audience = item.get("tofa_audience_rating")
    if critics is not None:
        parts.append(u"{0}  CRITICS".format(_discover_open_card_numeral(critics)))
    if audience is not None:
        parts.append(u"{0}  AUDIENCE".format(_discover_open_card_numeral(audience)))
    return u"   ".join(parts)


def _discover_row_meta(item: dict) -> str:
    """Year only. The real app's Discover captions carry the title over a bare
    year -- no genre (captured 2026-07-31: "Big Brother" / "2000"). We used to
    append the first genre, which made the line longer than the reference's
    and pushed the title into an ellipsis more often."""
    year = item.get("year")
    return str(year) if year else ""


# Two separate grids (letters/digits), matching the real Apple TV app's
# Grid keyboard's "abc"/"123" tabs -- see MainWindow.keyboard_mode.
# Each entry is (label, action, value); action "append" adds `value`, the
# rest are edit commands.
_SEARCH_TAB_LABELS = ("abc", "123")


def _search_letter_defs():
    return [(ch, "append", ch) for ch in "abcdefghijklmnopqrstuvwxyz"]


def _search_digit_defs():
    # 42 keys, 7 rows x 6 cols, matching the real Apple TV app's own 123
    # tab layout exactly:
    #   1 2 3 4 5 6
    #   7 8 9 0 ` '
    #   " ; : ~ = *
    #   + - _ , . ?
    #   ! @ # $ % ^
    #   & | / \ ( )
    #   [ ] { } < >
    chars = "1234567890`'\";:~=*+-_,.?!@#$%^&|/\\()[]{}<>"
    return [(ch, "append", ch) for ch in chars]


# SPACE / backspace / CLEAR -- always visible under whichever grid
# (letters/digits) is showing, since these are query-editing actions, not
# characters of a specific keyboard mode. Each entry is (label_text,
# icon_codepoint_or_None, action, value).
def _search_spacerow_defs():
    return [
        ("SPACE", None, "append", " "),
        (None, icon_glyphs.DELETE, "del", None),
        ("CLEAR", None, "clear", None),
    ]


def _search_meta_line(item: dict) -> str:
    parts = [_item_year(item)]
    runtime_minutes = item.get("runtime_minutes")
    if runtime_minutes:
        hours, minutes = divmod(int(runtime_minutes), 60)
        parts.append("{0} h {1} min".format(hours, minutes) if hours else "{0} min".format(minutes))
    genres = item.get("genres") or []
    if genres:
        parts.append(genres[0])
    return _dot_join(*parts)


def _search_ratings_line(item: dict) -> str:
    """"Critics 82 • Audience 77", numerals on the quality ramp.

    This line spent a while deliberately plain-white: an inline [COLOR] tag
    was twice observed still varying by score after the code had been changed
    to one fixed hex, which looked like Kodi reinterpreting the color. The
    likelier explanation surfaced later -- this add-on runs as ONE persistent
    Python process, so redeploying without a full Kodi restart leaves the old
    module in sys.modules and the OLD threshold function still running. That
    reproduces the symptom exactly. Verify any change here with a full
    restart, never a bare redeploy."""
    critics = item.get("tofa_critics_rating")
    audience = item.get("tofa_audience_rating")
    parts = []
    if critics is not None:
        parts.append(u"Critics {0}".format(theme.rating_numeral(critics)))
    if audience is not None:
        parts.append(u"Audience {0}".format(theme.rating_numeral(audience)))
    return _dot_join(*parts)


class MainWindow(focusmemory.FocusMemory, kodigui.ControlledWindow):
    dismissOnClose = True

    xmlFile = "script-tofa-main.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    NAV_LIST_ID = 3000

    # nav target string (matches navbar.NAV_TABS' own target values) ->
    # short section name, used for Window.Property(active_section), which
    # each section's root group's <visible> gates on.
    SECTION_TARGETS = {
        "home_window": "home",
        "browse_window": "browse",
        "discover_window": "discover",
        "search_window": "search",
        "settings_window": "settings",
    }

    ROW_LIST_IDS = home_rows.HOME_ROW_LIST_IDS

    # Browse section control ids -- 6000-6299 block, kept collision-free
    # from Home's 4000-5899/9000 block.
    SIDEBAR_ID = 6000
    # Fixed sources (Watchlist/History/Collections/Surprise Me) and
    # per-library rows are two separate list controls, not one -- Kodi's
    # <list> can't vary itemheight per item, and the real app has a
    # genuine ~29px empty gap between the two groups, not just a thin rule
    # crammed into the same ~6px gap every other row pair gets.
    SIDEBAR_LIBRARY_ID = 6010
    # A single-item list, same as SORT_ID/FILTER_ID -- clicking
    # it opens a PickerDialog rather than acting as a real multi-item pill
    # row (variable-width genre names made a fixed-itemwidth pill row
    # truncate). See _browse_genre_clicked().
    GENRE_ID = 6100
    GRID_ID = 6200
    ALPHA_RAIL_ID = 6220
    SORT_ID = 6110
    FILTER_ID = 6120
    # 6130 was Quality, now an axis of the Filter dialog; the slot it left
    # is where the collections back pill sits.
    TOOLBAR_IDS = (6110, 6120, 6100)

    ALL_GENRES = "All"

    # self._sources always starts with exactly these 3 fixed rows (in this
    # order), before any per-library rows -- see _browse_build_sidebar().
    BROWSE_FIXED_SOURCE_COUNT = 3
    # Position of the "Surprise Me" action row within the FIXED sidebar
    # list (id 6000) -- the last of its 4 items, right after the 3 fixed
    # sources. Not itself a source (no data to load, never "active"), so
    # it needs its own position<->index mapping -- see
    # _browse_fixed_pos_to_source_idx() / _browse_library_pos_to_source_idx().
    BROWSE_SURPRISE_ME_LIST_POS = BROWSE_FIXED_SOURCE_COUNT

    # (label, api sort value, api order value), offered by the Sort pill's
    # picker dialog. "Shuffle" (api value "random") is a persistent random
    # ORDER for the whole grid, paginated stably via a seed (see
    # _browse_sort_clicked()) -- distinct from Surprise Me's one-shot
    # "open a random title's Detail page". order=None since "random" has
    # no ascending/descending sense.
    BROWSE_SORT_OPTIONS = (
        ("Date Added", "added_at", "desc"),
        ("Title", "title", "asc"),
        ("Release Date", "release_date", "desc"),
        ("Rating", "rating", "desc"),
        ("Runtime", "runtime", "asc"),
        ("Last Watched", "last_watched", "desc"),
        ("Play Count", "play_count", "desc"),
        ("Shuffle", "random", None),
    )
    # (label, year_from, year_to) for the Filter dialog's Year axis --
    # None/None means no year filter.
    BROWSE_YEAR_OPTIONS = (
        ("All Years", None, None),
        ("2020s", 2020, 2029),
        ("2010s", 2010, 2019),
        ("2000s", 2000, 2009),
        ("1990s", 1990, 1999),
        ("1980s", 1980, 1989),
        ("Before 1980", None, 1979),
    )
    # (label, api `watched` value) for the Filter dialog's Watch Status
    # axis -- None means no filter (omit the param; the API has no literal
    # "all" value). BASE = always offered; a 5th "Played" option is
    # appended at runtime when the server advertises the
    # `media.watched_played` capability -- see
    # _browse_watched_options()/_ensure_capabilities().
    BROWSE_WATCHED_OPTIONS_BASE = (
        ("All", None),
        ("Unwatched", "unwatched"),
        ("In Progress", "in_progress"),
        ("Watched", "watched"),
    )
    # (label, api `quality` value) for the Quality pill's picker -- its
    # own pill, not folded into the Filter dialog's axes.
    BROWSE_QUALITY_OPTIONS = (
        ("Any", None),
        ("4K", "uhd4k"),
        ("4K HDR", "uhd4k_hdr"),
        ("Dolby Vision", "dolby_vision"),
        ("HDR", "hdr"),
        ("1080p+", "hd1080"),
        ("Atmos", "atmos"),
    )

    # Discover section control ids -- 6300-6699 block.
    DISCOVER_ROW_LIST_IDS = home_rows.DISCOVER_ROW_LIST_IDS
    MAX_DISCOVER_ROWS = home_rows.MAX_DISCOVER_ROWS

    #: How many of a Discover tab's shelves are staged EAGERLY -- i.e. how
    #: many the render pass will wait on the internet for. Two, because two
    #: is what fits on a 4K screen: the first shelf and the top of the
    #: second. Everything below the fold is queued in the background instead,
    #: so the wait is bounded by what the viewer can actually see rather than
    #: by how many shelves the server sent (up to MAX_DISCOVER_ROWS).
    DISCOVER_EAGER_SHELVES = 2

    #: ...and how many cards of each. A shelf carries about 40 and shows
    #: about five; eight is that plus a card of headroom for the first
    #: sideways press. Staging whole shelves instead was measured at 2.40s on
    #: the render call -- 75 images fetched to draw ten.
    DISCOVER_EAGER_ITEMS = 8

    #: The whole eager batch's budget, not each shelf's. Shorter than
    #: artcache's own 3s default because this runs on the action thread, so
    #: it is time the screen is not repainting. What misses the deadline
    #: draws from the CDN exactly as it did before -- a slow network makes
    #: this a no-op, never a stall.
    DISCOVER_EAGER_TIMEOUT_S = 1.5

    # The card's cinema chip, drawn in the Lucide icon font. Its two
    # siblings (the not-in-library plus and the requested clock) live in
    # windows/cards.py, which owns that badge for every screen.
    CINEMA_GLYPH = chr(icon_glyphs.CLAPPERBOARD)

    # Search section control ids -- 6700-6899 block.
    # Sentinel data_source for the Recent Searches list's trailing "Clear"
    # row. An object(), not a string: a real query can never be it.
    HISTORY_CLEAR = object()
    QUERY_EDIT_ID = 6701        # real Kodi edit control -- native OSK on Select, live physical-keyboard typing
    TAB_LIST_ID = 6702          # 2-item "abc" / "123" switcher (globe icon beside it is non-functional -- no language switching)
    KEYBOARD_ID = 6700          # 26-letter 6x5 grid
    NUMPAD_ID = 6703            # digit 3x4 grid (1-9, 0)
    SPACEROW_ID = 6704          # SPACE / backspace / CLEAR, always visible regardless of keyboard_mode
    TOP_RESULT_LIST_ID = 6805   # single-item list, same pattern as Browse's Sort/Filter/Quality/Genre; focusable/clickable
    MOVIES_LIST_ID = 6820
    SHOWS_LIST_ID = 6830
    ACTORS_LIST_ID = 6840
    SEARCH_DISCOVER_LIST_ID = 6850
    HISTORY_LIST_ID = 6860      # idle-state "Recent Searches" list -- local-only, no server endpoint exists (see search_history.py)
    #: Search's result rows, top to bottom as the page stacks them. A query
    #: routinely fills some and not others, so this is also the order
    #: focusmemory walks when the row a result was opened from is no longer
    #: on the page (see focus_memory_neighbours).
    SEARCH_RESULT_LIST_IDS = (TOP_RESULT_LIST_ID, MOVIES_LIST_ID, SHOWS_LIST_ID,
                              ACTORS_LIST_ID, SEARCH_DISCOVER_LIST_ID)

    # Settings section control ids -- 8000-8299, clear of Discover's 7000-7310
    # and Home's stray 9000. Each focusable detail row is its own one-item
    # list; see fragments.settings_action_row() for why.
    SETTINGS_NAV_ID = 8000
    SETTINGS_SWITCH_PROFILE_ID = 8110
    #: Its own grouplist child, one row, so Down leaves it (see the tokens).
    SETTINGS_SWITCH_SERVER_ID = 8115
    # Between its two neighbours on the page, and numbered between them so
    # the ids read in the order the rows are focused.
    #: Settings > Playback & Video > QUALITY. 8470, NOT 8450: that one is
    #: already SETTINGS_SEGMENT_IDS' fifth row (Commercial), and a duplicate
    #: id does not error -- Kodi silently resolves to whichever comes first
    #: in the XML, so the segment row simply stops working. check_xml caught
    #: it; the screen did not.
    #: `playback.default_quality`, in the app's order. Both values verified
    #: against the live server by writing each and reading it back -- the
    #: lesson of segment_actions' "play", which wrote cleanly and was
    #: silently dropped.
    SETTINGS_QUALITY_SEGMENTS = (("Auto", "auto"), ("Original", "original"))

    #: The CONNECTION toggle ("Direct connections only"), Settings > Account.
    SETTINGS_DIRECT_ONLY_ID = 8130
    SETTINGS_SIGN_OUT_ID = 8120
    SETTINGS_FOX_ID = 8200
    SETTINGS_APPEARANCE_LIST_ID = 8290   # the scrolling grouplist
    SETTINGS_RATING_ID = 8300
    SETTINGS_EPISODES_ID = 8310
    SETTINGS_SPOTLIGHT_ID = 8320
    SETTINGS_HOMEROWS_ID = 8330
    # ONE "Add a row" tile, holding three groups. 8350 was a second tile
    # ("Add a genre row") until the reference apps settled on a single
    # grouped picker; the id is retired rather than reused so a stale
    # rendered XML cannot resolve it to something else.
    SETTINGS_ADD_ROW_ID = 8340
    SETTINGS_REGION_ID = 8360
    # Playback & Video (8400s) and Audio & Subtitles (8500s) each own a
    # scrolling grouplist of their own, 8490 / 8590.
    # One list per segment type, in settings_options.SEGMENT_ROWS order.
    SETTINGS_SEGMENT_IDS = (8410, 8420, 8430, 8440, 8450)
    # NEXT EPISODE sits in its own group above SEGMENTS; see
    # tokens.SETTINGS_NEXTUP_GROUP_H for why it is not a sixth row.
    # Audio & Subtitles: primary + secondary per axis, mirroring the web and
    # desktop apps. preferred_*_languages is an ordered list and those clients
    # write TWO entries for a non-English locale, so a one-row page could
    # neither show nor set what they had already stored.
    SETTINGS_AUDIOLANG_ID = 8510
    SETTINGS_AUDIOLANG2_ID = 8540
    SETTINGS_SUBLANG_ID = 8520
    SETTINGS_SUBLANG2_ID = 8550
    SETTINGS_ALWAYSSUBS_ID = 8530
    #: control id -> (preferences key, slot in the ordered list)
    SETTINGS_LANGUAGE_ROWS = {
        8510: ("preferred_audio_languages", 0),
        8540: ("preferred_audio_languages", 1),
        8520: ("preferred_subtitle_languages", 0),
        8550: ("preferred_subtitle_languages", 1),
    }
    SETTINGS_LICENCES_ID = 8620
    #: How long the hero may block its own settle thread staging its art.
    #: Short: the fallback is today's behaviour (one tokenised row), so a slow
    #: link should give up quickly rather than hold the hero back.
    HERO_STAGE_TIMEOUT_S = 1.0

    SETTINGS_FONTS_ID = 8710
    SETTINGS_ARTBUDGET_ID = 8720
    SETTINGS_ARTCLEAR_ID = 8730

    def __init__(self, *args, **kwargs):
        start_target = kwargs.pop("start_target", "home_window")
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.client: MediaServerClient | None = None
        self._current_target = start_target
        self._loaded_sections: set[str] = set()

        # Down-navigation target from the nav bar, per active section name.
        # nav_bar()'s <ondown> is baked into the rendered XML as a single
        # static default -- only correct for one section. Every section's
        # real entry control is wired here at runtime instead, by
        # _activate_section() (same controlDown()-rewiring technique
        # _home_wire_row_nav() uses for the row chain).
        self._section_down_targets: dict[str, int] = {}

        # Focus-driven work that is too expensive to do per keypress waits
        # for the cursor to settle. 7.9.6 sets the delay at ~180ms and the
        # account carries `layout.focusedBackdropDelayMs` for it; the
        # preference is read once, when the first settle is scheduled,
        # since _ensure_preferences() is a network call the constructor
        # must not make.
        self._settle = kodigui.SettleTimer(T.FOCUS_SETTLE_MS, "tofa-focus-settle")
        # A SECOND timer, deliberately not the one above. SettleTimer.schedule()
        # REPLACES whatever is pending, and `_settle` is re-scheduled by every
        # hero-art update -- so a deferred section load parked on it was
        # cancelled by the viewer's first Down onto a row. Measured: Home
        # silently never reloaded after a profile switch and kept showing the
        # previous profile's rows.
        self._section_settle = kodigui.SettleTimer(T.FOCUS_SETTLE_MS, "tofa-section-settle")
        # A THIRD, for the same reason again: the half-clock delay between
        # dipping the hero's foreground out and swapping what it draws. Not
        # a plain sleep on the settle thread, which would hold that worker
        # and delay the NEXT focus change by the length of the dip.
        self._hero_swap = kodigui.SettleTimer(T.HERO_TEXT_DISSOLVE_MS, "tofa-hero-swap")
        self._settle_ms_from_prefs = False

        # ---- home section state ----
        # One ManagedControlList per row slot, keyed by control id -- built
        # once in onFirstInit, refilled each time _home_load() re-reads the
        # server's row list.
        self.row_lists: dict[int, kodigui.ManagedControlList] = {}
        # Which populated slot (if any) is Continue Watching this load --
        # _home_cw_clicked()/the ACTION_SHOW_INFO handler key off this
        # instead of a fixed control id, since CW's slot varies by
        # account/order.
        self._cw_list_id: int | None = None
        #: Row slots that came back non-empty on the last Home load, in slot
        #: order. Kept because Continue Watching can appear or empty out on
        #: a refresh, and the vertical nav chain has to be re-pointed around
        #: it without re-running the whole load (refresh_watch_progress).
        self._home_active_list_ids: list[int] = []
        # controlID -> "cw" | "library" | "discovery", for slots actually
        # populated this load.
        self._row_kinds: dict[int, str] = {}

        # ---- browse section state ----
        self.sidebar_list: kodigui.ManagedControlList | None = None
        self.sidebar_library_list: kodigui.ManagedControlList | None = None
        self.sort_list: kodigui.ManagedControlList | None = None
        self.filter_list: kodigui.ManagedControlList | None = None
        self.genre_list: kodigui.ManagedControlList | None = None
        self.grid_list: kodigui.ManagedControlList | None = None
        # each: {"kind": "watchlist"|"history"|"collections"|"library", ...}
        # -- always exactly BROWSE_FIXED_SOURCE_COUNT fixed entries first,
        # in that order, then one per real library. "Surprise Me" is
        # deliberately NOT in this list -- see BROWSE_SURPRISE_ME_LIST_POS.
        self._sources: list[dict] = []
        self._genres: list[str] = []        # includes ALL_GENRES at index 0
        # genre name -> how many titles carry it in the CURRENT scope. Keyed
        # by name so it survives _genres' synthetic "All" row.
        self._genre_counts: dict[str, int] = {}
        self._active_source_idx = 0
        # The collection drilled into, or None while the Collections grid
        # itself is showing.
        self._browse_collection: dict | None = None
        # Index position to restore when Back leaves a collection.
        self._collection_return_pos = 0
        # The collections index as DATA, plus which slots have been turned
        # into cards -- the same shape the poster grid uses, for the same
        # reason. See _browse_fill_collection_window.
        self._collection_items: list = []
        self._collection_filled: set = set()
        self._active_genre = self.ALL_GENRES
        self._browse_sort_idx = 0           # index into BROWSE_SORT_OPTIONS
        # The sort keys THIS server accepts, straight off the facets response
        # ("clients render real options instead of hardcoded tables"). None
        # until a facets response has been seen -- which is not the same as
        # empty, and is why this is not just a set: an older server that says
        # nothing must keep getting the full local table rather than none of
        # it. See _browse_offered_sorts.
        self._browse_server_sorts: tuple[str, ...] | None = None
        # Whether the VIEWER chose the current sort. The server's default_sort
        # only applies while this is False, so learning a new default (a
        # second library, a server upgrade) can never move a sort somebody
        # deliberately picked.
        self._browse_sort_user_picked = False
        self._browse_watched_idx = 0        # index into _browse_watched_options()
        self._browse_year_idx = 0           # index into BROWSE_YEAR_OPTIONS
        self._browse_quality_idx = 0        # index into BROWSE_QUALITY_OPTIONS
        # The A-Z rail's selection. "" is All; otherwise a single letter or
        # "#", passed to /api/v1/media?letter= verbatim.
        self._browse_letter = ""
        # {letter: count} for the ACTIVE source, from the same /media/facets
        # response the genre list is built from. The rail's cells come only
        # from here, so it can never offer a letter that lands on an empty
        # grid; empty means no rail at all.
        self._browse_letter_counts: dict[str, int] = {}
        self._server_capabilities: set = set()  # from GET /api/v1/system/info, see _ensure_capabilities()
        self._capabilities_loaded = False
        self._preferences: dict | None = None  # whoami's preferences, see _ensure_preferences()
        self._settings_languages: list | None = None  # /media/facets languages, see _settings_language_facet()
        self._settings_identity: dict | None = None  # cloud GET /v1/me, see _settings_account_identity()
        self._browse_shuffle_seed: int | None = None  # for Sort="random"'s stable pagination, see _browse_sort_clicked()
        # Browse grid paging. The server caps per_page at 200 however much is
        # asked for, so the rest of a 10,000-title library is only reachable
        # by asking for page 2, 3... See _browse_maybe_load_more().
        self._browse_total: int | None = None
        self._browse_page_params: dict | None = None
        self._browse_loading_more = False
        #: Page numbers already fetched. The grid is allocated to its full
        #: length up front, so "how much is loaded" can no longer be read off
        #: the item count -- this is the only record of what is real.
        self._browse_pages_loaded: set[int] = set()
        #: page -> its raw items, kept so slots can become cards lazily.
        self._browse_page_data: dict[int, list] = {}
        #: grid positions already turned into real cards.
        self._browse_filled: set[int] = set()
        self._browse_sort_reversed = False  # re-picking the active Sort row flips its order, see _browse_sort_clicked()

        # ---- discover section state ----
        # one ManagedControlList per rendered row, keyed by control id
        self.discover_rows: dict[int, kodigui.ManagedControlList] = {}

        # ---- search section state ----
        self.search_query: str = ""
        self.keyboard_mode: str = "abc"
        self.tabs: kodigui.ManagedControlList | None = None
        self.keyboard: kodigui.ManagedControlList | None = None
        self.numpad: kodigui.ManagedControlList | None = None
        self.spacerow: kodigui.ManagedControlList | None = None
        self.top_result_list: kodigui.ManagedControlList | None = None
        self.movies_list: kodigui.ManagedControlList | None = None
        self.shows_list: kodigui.ManagedControlList | None = None
        self.actors_list: kodigui.ManagedControlList | None = None
        self.history_list: kodigui.ManagedControlList | None = None
        # Query already recorded into history since it was last typed --
        # avoids re-writing the same entry to the front of the file on
        # every focus round-trip through the results while it's unchanged.
        self._search_history_committed_for: str | None = None
        self._search_query_field_focused = False

    @classmethod
    def open(cls, **kwargs):
        return kodigui.ControlledWindow.open.__func__(cls, **kwargs)

    def onReInit(self):
        """Kodi re-inits this window whenever the one above it closes -- the
        player, a Detail page, anything. That is exactly when the positions
        on screen may have moved, so it is where they get re-read."""
        self.refresh_watch_progress()
        self.restore_focus()

    #: Kodi's own default already lands on the nav bar, so returning to it
    #: is what happens anyway.
    FOCUS_MEMORY_IGNORE = (NAV_LIST_ID,)

    def open_detail(self, **kwargs):
        """Open a Detail page over this window, remembering where from.

        EVERY DetailWindow.open() in this file goes through here. Recording
        the origin in onClick alone was not enough: the Info key and the
        card-options panel both open Detail from onAction, which never
        reaches onClick, so backing out of those landed on the nav bar
        instead of the card. Centralised so a new entry point cannot forget
        (windows/focusmemory.py).
        """
        self.remember_focus(self.getFocusId())
        from .detail import DetailWindow
        DetailWindow.open(**kwargs)

    #: Nothing else would take focus. Kodi's own default lands here anyway --
    #: the difference is that this happens on the re-init, instead of costing
    #: the viewer the keypress that discovers the window is focusing nothing.
    FOCUS_MEMORY_LAST_RESORT = NAV_LIST_ID

    def focus_memory_neighbours(self, control_id) -> tuple:
        """Which controls a given one sits among, top to bottom on screen.

        Only consulted when the remembered control has gone unfocusable, so
        these are the "where else could they stand" answers, not navigation:
        the d-pad chains are wired separately per section.

        Slots, not live rows: _home_load walks its slots in order and simply
        leaves the empty ones' titles blank, so ROW_LIST_IDS is the visual
        order whether or not every slot is filled, and the mixin skips the
        empty ones itself. Same for Discover's shelves.
        """
        if control_id in self.ROW_LIST_IDS:
            return tuple(self.ROW_LIST_IDS)
        if control_id in self.DISCOVER_ROW_LIST_IDS:
            # The tab pills sit above the shelves and are always there, so a
            # tab whose every shelf came back empty still has somewhere to
            # land -- on the pill that chose it.
            return home_rows.DISCOVER_TAB_LIST_IDS + tuple(self.DISCOVER_ROW_LIST_IDS)
        if control_id in (self.GRID_ID, self.COLLECTION_GRID_ID):
            # A grid that filtered down to nothing sends them back to the
            # sidebar, which is where the source and filters live -- i.e.
            # where the emptiness gets undone.
            return (self.SIDEBAR_ID, self.ALPHA_RAIL_ID, control_id)
        if control_id in self.SEARCH_RESULT_LIST_IDS:
            return self.SEARCH_RESULT_LIST_IDS
        return ()

    def focus_memory_list(self, control_id):
        """Every card container in this window, across all five sections."""
        for lists in (self.row_lists, self.discover_rows,
                      self._discover_tab_lists):
            mcl = (lists or {}).get(control_id)
            if mcl is not None:
                return mcl
        return {
            self.GRID_ID: self.grid_list,
            self.COLLECTION_GRID_ID: self.collection_list,
            self.ALPHA_RAIL_ID: self.alpha_list,
            self.SIDEBAR_ID: self.sidebar_list,
            self.SIDEBAR_LIBRARY_ID: self.sidebar_library_list,
            self.TOP_RESULT_LIST_ID: self.top_result_list,
            self.MOVIES_LIST_ID: self.movies_list,
            self.SHOWS_LIST_ID: self.shows_list,
            self.ACTORS_LIST_ID: self.actors_list,
            self.HISTORY_LIST_ID: self.history_list,
        }.get(control_id)

    def onFirstInit(self):
        # A window id comes from a pool and is reused, so the switch cover
        # must be cleared rather than assumed unset -- a stuck one would
        # paint the whole window SPLASH_BG.
        self.setProperty("switching_profile", "")
        # This window is also reachable straight from Kodi's Program add-ons
        # (launch_home.py), bypassing addon.py's plugin:// router -- so
        # nothing upstream has necessarily checked sign-in yet. Drive the
        # device-code flow here too, or an unauthenticated launch renders
        # full chrome with every row silently empty.
        if not auth.is_signed_in() and not signin.interactive_sign_in():
            self.closeNow()
            return
        # Multi-profile household gate (brief §3, §8) -- same reasoning as
        # the sign-in check above: a locked profile 403s every
        # account-scoped call, which would otherwise render full chrome
        # with every section silently empty.
        self._search_profile_id: str | None = None
        try:
            session = http.new_session()
            tok = auth.ensure_fresh(session)
            tok = profile_select.ensure_profile_selected(session, tok)
            self._search_profile_id = tok.profile_id
            self._render_nav_avatar()
        except (auth.NotSignedIn, profile_select.ProfileCanceled):
            self.closeNow()
            return
        except http.ApiError:
            pass  # let the section's own data load surface this
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("accent_pill_fill", theme.accent_with_alpha("3D"))
        # Settings' focused detail row is accent-tinted glass, not the solid
        # accent fill its sidebar uses -- see tokens.SETTINGS_ROW_FOCUS_ALPHA.
        self.setProperty("settings_row_wash",
                         theme.accent_with_alpha(T.SETTINGS_ROW_FOCUS_ALPHA))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("logo_file", theme.default_logo())
        # Kodi can reuse a window ID slot across different window
        # instances, and an unset property can read back whatever the
        # previous occupant last set -- explicitly clear nav_closing rather
        # than assume a fresh window starts blank.
        self.setProperty("nav_closing", "")
        navbar.build_nav(self, self.NAV_LIST_ID, self._current_target)

        # Built regardless of starting section (cheap, no HTTP): the row
        # lists' Down/Up focus chain ids are referenced by the static XML
        # even before Home is first shown.
        for list_id in self.ROW_LIST_IDS:
            self.row_lists[list_id] = kodigui.ManagedControlList(self, list_id, 6)

        # Same reasoning as the Home row lists above: built regardless of
        # starting section, since a fixed control id can be a
        # Down-navigation target (see _section_down_targets) even before
        # Browse is first shown.
        self.sidebar_list = kodigui.ManagedControlList(self, self.SIDEBAR_ID, 4)
        self.sidebar_library_list = kodigui.ManagedControlList(self, self.SIDEBAR_LIBRARY_ID, 12)
        self.sort_list = kodigui.ManagedControlList(self, self.SORT_ID, 1)
        self.filter_list = kodigui.ManagedControlList(self, self.FILTER_ID, 1)
        self.genre_list = kodigui.ManagedControlList(self, self.GENRE_ID, 1)
        self.alpha_list = kodigui.ManagedControlList(
            self, self.ALPHA_RAIL_ID, len(T.ALPHA_KEYS))
        # Settings, same reasoning again: its sidebar is a Down target from
        # the nav bar before the section has ever been shown. The three
        # action rows are one-item lists (see fragments.settings_action_row).
        self.settings_nav_list = kodigui.ManagedControlList(
            self, self.SETTINGS_NAV_ID, len(settings_pages.PAGES))
        self.settings_switch_profile_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SWITCH_PROFILE_ID, 1)
        self.settings_switch_server_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SWITCH_SERVER_ID, 1)
        self.settings_direct_list = kodigui.ManagedControlList(
            self, self.SETTINGS_DIRECT_ONLY_ID, 1)
        self.settings_sign_out_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SIGN_OUT_ID, 1)
        self.settings_fox_list = kodigui.ManagedControlList(
            self, self.SETTINGS_FOX_ID, len(theme.PRESETS))
        self.settings_episodes_list = kodigui.ManagedControlList(
            self, self.SETTINGS_EPISODES_ID, 1)
        self.settings_spotlight_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SPOTLIGHT_ID, 1)
        # NOTE: no settings_homerows_list any more. The home-row editor is
        # nine groups of real buttons (home_rows.HOME_ROW_EDIT_IDS), because
        # a list item cannot hold three focus targets. See
        # fragments.settings_home_row_editor.
        self.settings_add_row_list = kodigui.ManagedControlList(
            self, self.SETTINGS_ADD_ROW_ID, 1)
        self.settings_region_list = kodigui.ManagedControlList(
            self, self.SETTINGS_REGION_ID, 1)
        self.settings_audiolang_list = kodigui.ManagedControlList(
            self, self.SETTINGS_AUDIOLANG_ID, 1)
        self.settings_audiolang2_list = kodigui.ManagedControlList(
            self, self.SETTINGS_AUDIOLANG2_ID, 1)
        self.settings_sublang_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SUBLANG_ID, 1)
        self.settings_sublang2_list = kodigui.ManagedControlList(
            self, self.SETTINGS_SUBLANG2_ID, 1)
        self.settings_alwayssubs_list = kodigui.ManagedControlList(
            self, self.SETTINGS_ALWAYSSUBS_ID, 1)
        self.settings_licences_list = kodigui.ManagedControlList(
            self, self.SETTINGS_LICENCES_ID, 1)
        self.settings_fonts_list = kodigui.ManagedControlList(
            self, self.SETTINGS_FONTS_ID, 1)
        self.settings_artbudget_list = kodigui.ManagedControlList(
            self, self.SETTINGS_ARTBUDGET_ID, 1)
        self.settings_artclear_list = kodigui.ManagedControlList(
            self, self.SETTINGS_ARTCLEAR_ID, 1)
        self.grid_list = kodigui.ManagedControlList(self, self.GRID_ID, 25)
        # 7.5's index is landscape, so it needs its own panel: a Kodi panel
        # has a single itemwidth/itemheight and cannot switch shape.
        self.collection_list = kodigui.ManagedControlList(self, self.COLLECTION_GRID_ID, 12)
        # Sort/Filter/Quality/Genre are single always-present rows (not a
        # real choice list -- clicking any of them opens a picker dialog),
        # so they're built with one static item each, right here, rather
        # than in _browse_load() like the sidebar/grid are. Current value
        # is shown via a *_label ListItem property, not a Window property
        # -- a Window property doesn't reliably re-render inside a list
        # item that's never rebuilt (Kodi caches the item's rendered
        # layout), while a ListItem property does invalidate it. See
        # _browse_sort_clicked().
        sort_item = kodigui.ManagedListItem(label="Sort")
        sort_item.setProperty("sort_label", self.BROWSE_SORT_OPTIONS[self._browse_sort_idx][0])
        sort_item.setProperty("sort_glyph", self._browse_sort_glyph())
        self.sort_list.addItems([sort_item])
        filter_item = kodigui.ManagedListItem(label="Filter")
        filter_item.setProperty("filter_label", self._browse_filter_label())
        self.filter_list.addItems([filter_item])
        genre_item = kodigui.ManagedListItem(label="Genre")
        genre_item.setProperty("genre_label", self._browse_genre_label())
        self.genre_list.addItems([genre_item])
        self._section_down_targets["browse"] = self.SIDEBAR_ID

        # Down target is fixed at row-0's list regardless of how many rows
        # end up populated, unlike Home's per-load rewire -- if row0 is
        # empty/hidden, Down silently fails (known rough edge, not fixed
        # here).
        for list_id in self.DISCOVER_ROW_LIST_IDS:
            self.discover_rows[list_id] = kodigui.ManagedControlList(self, list_id, 12)

        # Tab pills. Each is a 1-item list holding its own static label; the
        # selected pill is the one Kodi draws through focusedlayout, so
        # "which tab is active" is just which pill list is selected -- no
        # extra property needed for the visual state. Down from the pills
        # lands on the rows; Down from nav lands on the pills, so the pills
        # are the section's real entry point.
        self._discover_tab_lists: dict[int, kodigui.ManagedControlList] = {}
        for idx, (key, label, _w) in enumerate(home_rows.DISCOVER_TABS):
            list_id = home_rows.DISCOVER_TAB_LIST_IDS[idx]
            mcl = kodigui.ManagedControlList(self, list_id, 1)
            mcl.reset()
            mcl.addItems([kodigui.ManagedListItem(label=label, data_source=key)])
            self._discover_tab_lists[list_id] = mcl
        self._discover_tab = home_rows.DISCOVER_DEFAULT_TAB
        self._discover_shelves_by_tab: dict[str, list[dict]] = {}
        # Drives every pill's active/inactive look; see
        # fragments.discover_tab_pill() for why it can't be layout-based.
        self.setProperty("discover_tab", self._discover_tab)
        self._section_down_targets["discover"] = home_rows.DISCOVER_TAB_LIST_IDS[0]

        # Search section's own control construction (cheap, no HTTP --
        # unlike every other section, Search has no initial data load at
        # all; nothing fetches until the user types a key, so there's no
        # per-section lazy-load branch for it in _activate_section()).
        self.setProperty("query", "")
        self.setProperty("results_caption", "")
        self.setProperty("no_results_caption", "")
        self.setProperty("movies_count", "0")
        self.setProperty("shows_count", "0")
        self.setProperty("actors_count", "0")
        self.setProperty("search_discover_count", "0")
        self.setProperty("has_results", "0")
        self.setProperty("keyboard_mode", self.keyboard_mode)

        self.tabs = kodigui.ManagedControlList(self, self.TAB_LIST_ID, 2)
        self.tabs.reset()
        tab_items = []
        for label in _SEARCH_TAB_LABELS:
            mli = kodigui.ManagedListItem(label=label)
            mli.setProperty("is_active", "1" if label == self.keyboard_mode else "")
            tab_items.append(mli)
        self.tabs.addItems(tab_items)

        self.keyboard = kodigui.ManagedControlList(self, self.KEYBOARD_ID, 6)
        self.keyboard.reset()
        self.keyboard.addItems([
            kodigui.ManagedListItem(label=label, data_source={"action": action, "value": value})
            for label, action, value in _search_letter_defs()
        ])
        self.numpad = kodigui.ManagedControlList(self, self.NUMPAD_ID, 3)
        self.numpad.reset()
        self.numpad.addItems([
            kodigui.ManagedListItem(label=label, data_source={"action": action, "value": value})
            for label, action, value in _search_digit_defs()
        ])
        self.spacerow = kodigui.ManagedControlList(self, self.SPACEROW_ID, 3)
        spacerow_items = []
        for label_text, icon, action, value in _search_spacerow_defs():
            mli = kodigui.ManagedListItem(label=label_text or "", data_source={"action": action, "value": value})
            # A real unicode char, not the `&#xHHHH;` numeric-entity form --
            # that form is only needed for a glyph written directly into
            # XML source text, not one arriving through a runtime
            # property. $INFO[ListItem.Property(...)] passes it straight
            # through to a label using the tofa_font_icons_<size> font.
            mli.setProperty("icon", chr(icon) if icon else "")
            spacerow_items.append(mli)
        self.spacerow.reset()
        self.spacerow.addItems(spacerow_items)

        self.top_result_list = kodigui.ManagedControlList(self, self.TOP_RESULT_LIST_ID, 1)
        self.movies_list = kodigui.ManagedControlList(self, self.MOVIES_LIST_ID, 6)
        self.shows_list = kodigui.ManagedControlList(self, self.SHOWS_LIST_ID, 6)
        self.actors_list = kodigui.ManagedControlList(self, self.ACTORS_LIST_ID, 6)
        # Search's Discover shelf reuses the SAME watchlist +/check toggle
        # as the Discover section's own rows -- registering it into
        # self.discover_rows means onClick's/onAction's existing
        # `controlID in self.discover_rows` branches (see
        # _discover_card_clicked()) already handles it, since search's
        # discover items share the same shape
        # (tmdb_id/type/poster_path/vote_average/genres/year) as
        # Discover's own.
        self.discover_rows[self.SEARCH_DISCOVER_LIST_ID] = kodigui.ManagedControlList(
            self, self.SEARCH_DISCOVER_LIST_ID, 6
        )
        self.history_list = kodigui.ManagedControlList(self, self.HISTORY_LIST_ID, search_history.MAX_ENTRIES)
        self._search_fill_history()
        self._search_wire_keyboard_nav()
        self._section_down_targets["search"] = self.QUERY_EDIT_ID

        # Settings' sidebar has a fixed page list with no server data in it,
        # so it is filled here once rather than in a load branch; only the
        # per-page values it shows as subtitles need the network, and those
        # arrive later via _settings_load().
        self._settings_fill_nav()
        self._settings_fill_foxes()
        self._section_down_targets["settings"] = self.SETTINGS_NAV_ID

        # Focus the nav bar BEFORE any section's slow HTTP-bound load: the
        # nav's active-tab pill only renders full-size while the nav list
        # has literal Kodi focus (see fragments.py:nav_bar()'s
        # Control.HasFocus split).
        self.setFocusId(self.NAV_LIST_ID)
        self._activate_section(self._current_target, first_init=True)


    # ------------------------------------------------------------------
    # section switching
    # ------------------------------------------------------------------

    def _get_client(self) -> MediaServerClient | None:
        # Shared across every section -- one client for the whole merged
        # window's lifetime, unlike the old per-screen windows, which each
        # built (and threw away, on every tab switch) their own.
        #
        # "The whole window's lifetime" is longer than a locked profile's ~4h
        # token lives, and this window is the one that is never closed -- so
        # it is the likeliest of all of them to be holding a dead token. Past
        # the expiry, rebuild (which re-verifies the PIN) rather than let
        # every section read its 401s back as empty.
        if self.client and not self.client.profile_token_expired():
            return self.client
        # Built during the splash when it could be (see prefetch.py). Its
        # absence is normal -- a locked profile, a signed-out account, or any
        # failure -- and just means doing it here as before.
        warmed = prefetch.client()
        if warmed is not None and not warmed.profile_token_expired():
            self.client = warmed
            return self.client
        try:
            session = http.new_session()
            tok = auth.ensure_fresh(session)
            tok = profile_select.ensure_profile_selected(session, tok)
            self.client = api.client_for(session, tok)
        except (auth.NotSignedIn, profile_select.ProfileCanceled, http.ApiError):
            self.client = None
        return self.client

    #: section name -> the function that loads it, for _activate_section.
    #: Unbound so the table can live on the class; called as loader(self).
    SECTION_LOADERS = {
        "home": lambda self: self._home_load(),
        "browse": lambda self: self._browse_load(),
        "discover": lambda self: self._discover_load(),
        "settings": lambda self: self._settings_load(),
    }

    def _deferred_section_load(self, section: str, loader):
        """Load one section, from the settle thread.

        Re-checked here rather than at schedule time: several activations can
        be scheduled during one walk across the nav bar, and only the last
        survives -- but a section the viewer left and came back to may have
        been loaded in between.

        Also re-checked against the CURRENT section: the timer fires ~180ms
        after focus stops, and a viewer who moved on again in that window
        would otherwise pay for a screen they are no longer looking at.
        """
        if section in self._loaded_sections:
            return
        if self.SECTION_TARGETS.get(self._current_target) != section:
            return
        self._loaded_sections.add(section)
        loader(self)

    def _activate_section(self, target: str, first_init: bool = False):
        section = self.SECTION_TARGETS.get(target)
        if not section:
            return
        self._current_target = target
        # Written on every switch, not only on close: Kodi's Home button
        # does not always give the window a clean shutdown, and a section
        # recorded a moment early is better than one never recorded.
        self._remember_section()
        self.setProperty("active_section", section)
        if not first_init:
            # is_current was already set correctly by build_nav() for the
            # window's starting section; every switch after that needs to
            # move it explicitly, since build_nav() only ever runs once.
            navbar.set_current(self, self.NAV_LIST_ID, target)

        # A section's first load is DEFERRED behind the settle timer, and so
        # runs off the action thread. Two separate problems, one mechanism:
        #
        # 1. The nav bar activates on FOCUS, not on Select (see onAction), so
        #    walking Left from Settings to Home passes over Search, Discover
        #    and Browse and used to load every one of them. Measured on the
        #    box: browse 2.65s + discover 3.87s + home 14.53s, all on the
        #    action thread, for a walk the viewer meant as "go Home". After a
        #    profile switch (_loaded_sections reset to {"settings"}) that is
        #    the whole of "it takes more than ten seconds and my Down does
        #    nothing". schedule() replaces whatever was pending, so only the
        #    section focus COMES TO REST on is loaded now.
        #
        # 2. Even the one section you do want was loading on the action
        #    thread, where Kodi drops keypresses rather than queueing them.
        #    Off-thread, Down is accepted while the rows are still filling.
        #
        # Same treatment Browse's source list already got for the same reason
        # (_browse_switch_source), and the same timer that carries
        # _browse_load_grid, so building cards from it is established here.
        #
        # `_loaded_sections` is marked INSIDE the callback, never at schedule
        # time: a section passed over has its callback replaced and never
        # runs, and marking it early would leave it permanently "loaded" and
        # permanently empty.
        loader = self.SECTION_LOADERS.get(section)
        if loader and section not in self._loaded_sections:
            if first_init:
                # Cold start: the splash is up, nothing is drawn yet, and
                # this is the fast path anyway (measured 0.6s of card
                # building against 12s on a reload). Deferring it would only
                # put an empty Home on screen behind the splash.
                self._loaded_sections.add(section)
                loader(self)
            else:
                self._section_settle.schedule(lambda s=section, f=loader: self._deferred_section_load(s, f))
        # "search" has no lazy-load branch -- unlike every other section it
        # has no initial HTTP-bound data to fetch; nothing loads until the
        # user types a key (see _search_apply_key()).

        # Re-point the nav bar's Down key at this section's real entry
        # control now that it's active -- see _section_down_targets'
        # docstring in __init__ for why this can't just be static XML.
        down_id = self._section_down_targets.get(section)
        if down_id:
            try:
                self.getControl(self.NAV_LIST_ID).controlDown(self.getControl(down_id))
            except Exception:
                pass

    def _nav_clicked(self):
        target = navbar.resolve_nav_click(self, self.NAV_LIST_ID, self._current_target)
        if target:
            self._open_nav_target(target)

    def _open_nav_target(self, target: str):
        # Every target switches in place -- no window open()/doModal() at
        # all. Settings used to be the exception, handled inside
        # navbar.resolve_nav_click by popping ADDON.openSettings(); it is an
        # ordinary section now and reaches here like the rest.
        self._activate_section(target)

    # ------------------------------------------------------------------
    # input (shared across every section)
    # ------------------------------------------------------------------

    def onClick(self, controlID):
        # Where to put the viewer back if this click opens a window over us.
        self.remember_focus(controlID)
        if controlID == self.NAV_LIST_ID:
            self._nav_clicked()
        elif controlID == self._cw_list_id:
            self._home_cw_clicked()
        elif controlID in self._row_kinds:
            self._home_detail_clicked(self.row_lists[controlID], self._row_kinds[controlID])
        elif controlID == self.SETTINGS_NAV_ID:
            self._settings_page_clicked()
        elif controlID == self.SETTINGS_SWITCH_PROFILE_ID:
            self._settings_switch_profile()
        elif controlID == self.SETTINGS_SWITCH_SERVER_ID:
            self._settings_switch_server()
        elif controlID == self.SETTINGS_DIRECT_ONLY_ID:
            self._settings_direct_only_clicked()
        elif controlID == self.SETTINGS_SIGN_OUT_ID:
            self._settings_sign_out()
        elif controlID == self.SETTINGS_FOX_ID:
            self._settings_fox_clicked()
        elif controlID == self.SETTINGS_EPISODES_ID:
            self._settings_episodes_clicked()
        elif controlID == self.SETTINGS_SPOTLIGHT_ID:
            self._settings_spotlight_clicked()
        elif controlID in settings_options.SEGMENTED_BY_ID:
            self._settings_segmented_pressed(controlID)
        elif (home_rows.HOME_ROW_EDIT_GROUP_IDS[0]
              <= controlID <= home_rows.HOME_ROW_EDIT_IDS[-1][-1]):
            self._settings_home_row_pressed(controlID)
        elif controlID == self.SETTINGS_ADD_ROW_ID:
            self._settings_add_row()
        elif controlID == self.SETTINGS_REGION_ID:
            self._settings_region_clicked()
        elif controlID in self.SETTINGS_LANGUAGE_ROWS:
            key, slot = self.SETTINGS_LANGUAGE_ROWS[controlID]
            self._settings_language_clicked(key, slot)
        elif controlID == self.SETTINGS_ALWAYSSUBS_ID:
            self._settings_alwayssubs_clicked()
        elif controlID == self.SETTINGS_LICENCES_ID:
            self._settings_licences_clicked()
        elif controlID == self.SETTINGS_FONTS_ID:
            self._settings_fonts_clicked()
        elif controlID == self.SETTINGS_ARTBUDGET_ID:
            self._settings_artbudget_clicked()
        elif controlID == self.SETTINGS_ARTCLEAR_ID:
            self._settings_artclear_clicked()
        elif controlID in (self.SIDEBAR_ID, self.SIDEBAR_LIBRARY_ID):
            self._browse_sidebar_clicked(controlID)
        elif controlID == self.ALPHA_RAIL_ID:
            self._browse_alpha_clicked()
        elif controlID == self.SORT_ID:
            self._browse_sort_clicked()
        elif controlID == self.FILTER_ID:
            self._browse_filter_clicked()
        elif controlID == self.GENRE_ID:
            self._browse_genre_clicked()
        elif controlID == self.COLLECTION_GRID_ID:
            item = self.collection_list.getSelectedItem()
            if item:
                self._browse_open_collection(item)
        elif controlID == self.COLLECTION_BACK_ID:
            self._browse_close_collection()
        elif controlID == self.GRID_ID:
            self._browse_grid_clicked()
        elif controlID in self.discover_rows:
            self._discover_card_clicked(controlID)
        elif controlID in home_rows.DISCOVER_TAB_LIST_IDS:
            self._discover_tab_clicked(controlID)
        elif controlID == self.TAB_LIST_ID:
            self._search_tab_clicked()
        elif controlID in (self.KEYBOARD_ID, self.NUMPAD_ID):
            self._search_key_clicked(controlID)
        elif controlID == self.SPACEROW_ID:
            self._search_spacerow_clicked()
        elif controlID == self.TOP_RESULT_LIST_ID:
            self._search_top_result_clicked()
        elif controlID in (self.MOVIES_LIST_ID, self.SHOWS_LIST_ID):
            self._search_result_clicked(controlID)
        elif controlID == self.ACTORS_LIST_ID:
            self._search_actor_clicked()
        elif controlID == self.HISTORY_LIST_ID:
            self._search_history_clicked()

    # 7.9.5's open/close (the 450ms WIDTH swap) was built here and is gone
    # again, removed 2026-08-13 after Adrian watched it on the 4K panel:
    # "especially the shrinking of the artwork in the left card feels weird".
    #
    # It was never the effect the spec asks for. Kodi's zoom is a render
    # transform, so the departing card's ARTWORK is squashed horizontally
    # rather than the frame narrowing over a still image -- a 2.5x horizontal
    # compression on the first frames, which is what reads as wrong. Kodi
    # cannot crop-on-resize, so that divergence had no fix; it was accepted
    # when shipped and rejected once seen at size. See internal-docs/
    # ANIMATION.md for the whole route, and git history (5bc3af9) for the
    # three findings it cost -- Conditional-not-Focus, direction decides
    # which edge holds still, per-ITEM not per-window -- which are all still
    # true and are the reason that commit is worth reading before anyone
    # tries per-item motion in a Kodi list again.
    #
    # 7.9.5's DISSOLVE stays: it is the arriving card's fade in
    # skin/fragments.py:discover_card, measured on the cinema box before it
    # shipped, and it is the half that looks right.

    def onFocus(self, controlID):
        # Track the whole input pane, not just the query edit control:
        # typing via the on-screen keyboard sets the edit control's text
        # directly without ever focusing it, so "left 6701" alone would
        # never fire as a "done typing" signal.
        if controlID in (self.QUERY_EDIT_ID, self.TAB_LIST_ID, self.KEYBOARD_ID, self.NUMPAD_ID, self.SPACEROW_ID):
            self._search_query_field_focused = True
        elif getattr(self, "_search_query_field_focused", False):
            # Focus just left the input pane -- commit the current query
            # to history now, rather than on every debounced keystroke.
            # See _search_maybe_commit_history()'s own docstring.
            self._search_query_field_focused = False
            self._search_maybe_commit_history()

        # Browse: coming back UP out of the grid should return to the pill
        # you left FROM, not always to Sort. The template can carry only one
        # static onup so it named the first pill; walking right to Genre,
        # down into the grid and back up then teleported focus across the
        # whole filter row. Same remembered-entry idea as Discover's group
        # pills and 7.9.7's deterministic entry -- re-pointed here because
        # "which pill" is only known at runtime.
        if controlID in self.TOOLBAR_IDS:
            try:
                self.getControl(self.GRID_ID).controlUp(self.getControl(controlID))
            except Exception:
                pass

        # Browse's sidebar is two lists that read as one; keep the fixed
        # one's cursor where the crossing needs it. See
        # _browse_park_fixed_cursor for why this is done BEFORE the press
        # rather than in onAction.
        if controlID == self.SIDEBAR_LIBRARY_ID:
            # Up from the library list must land on the row directly above
            # it, which is the LAST fixed row ("Surprise Me").
            #
            # ONLY this crossing. An earlier cut also parked the cursor at 0
            # whenever the nav bar took focus in Browse, on the theory that
            # coming back down should land on the first row -- but measured
            # live, Down off the nav bar goes to the GRID, not the sidebar,
            # so that branch never fired; and it would have overwritten the
            # cursor that _browse_rewire_grid_left relies on to return Left
            # from the grid to the ACTIVE source.
            self._browse_park_fixed_cursor(len(self.sidebar_list or []) - 1)

        mlist = self.row_lists.get(controlID)
        if mlist:
            item = mlist.getSelectedItem()
            if item and item.dataSource:
                self._home_update_hero(item.dataSource)

    #: Where the viewer was, remembered for the LIFE OF THIS KODI RUN.
    #: Pressing Home mid-browse and coming back should land where you left,
    #: not on Home. Same storage and lifetime as the splash's once-per-run
    #: flag: a property on Kodi's home window, which outlives our processes
    #: (every launch is a fresh interpreter) and dies with Kodi.
    LAST_SECTION_PROPERTY = "tofa.last_section"
    #: Set when the window wants launch_home.py to build a NEW one, rather
    #: than the script simply ending. See request_restart().
    RESTART_PROPERTY = "tofa.restart_requested"

    @classmethod
    def request_restart(cls):
        """Ask the launcher for a fresh window once this one closes.

        A profile change makes every list in this window wrong at once, and
        clearing them one by one is a list that has to stay correct for ever
        -- Home, the Browse grid and its collection grid, every Discover row,
        the four Search lists, the sidebar's libraries and genres. Miss one
        and a Kids profile is shown the previous viewer's library, which is
        the failure this cannot afford.

        A new window cannot carry any of it: new controls, empty lists,
        nothing inherited. Correct by construction rather than by
        enumeration."""
        xbmcgui.Window(10000).setProperty(cls.RESTART_PROPERTY, "1")

    @classmethod
    def take_restart_request(cls) -> bool:
        """One-shot: consumed by the launcher, so a restart cannot loop."""
        win = xbmcgui.Window(10000)
        if not win.getProperty(cls.RESTART_PROPERTY):
            return False
        win.clearProperty(cls.RESTART_PROPERTY)
        return True

    @classmethod
    def remembered_target(cls) -> str | None:
        value = xbmcgui.Window(10000).getProperty(cls.LAST_SECTION_PROPERTY)
        return value or None

    def _remember_section(self):
        xbmcgui.Window(10000).setProperty(
            self.LAST_SECTION_PROPERTY, self._current_target or "")

    def onClosed(self):
        # The settle worker outlives the window otherwise, and its next
        # callback would setImage() on a control that no longer exists.
        self._settle.stop()
        self._section_settle.stop()
        self._hero_swap.stop()
        self._remember_section()
        kodigui.ControlledWindow.onClosed(self)

    def onAction(self, action):
        action_id = action.getId()

        if self.getFocusId() == self.QUERY_EDIT_ID:
            # Kodi's edit control already accepts physical-keyboard typing
            # and opens the native OSK on Select -- built in, nothing to
            # wire up. This just mirrors the control's real text back into
            # our own state after any action.
            self._search_sync_from_edit()

        if action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK) and kodigui.back_is_held_repeat():
            # The user is still holding Back after unwinding the pushed
            # windows above us. This IS the top level, so swallow the rest of
            # the repeat stream rather than letting it walk focus to the nav
            # bar and then exit the add-on -- "hold Back to get out of where
            # I am" must not mean "hold Back to quit".
            #
            # Re-stamp on every swallowed repeat, so a key held down for any
            # length of time keeps extending the guard instead of expiring
            # mid-stream and letting the next repeat through to the exit.
            kodigui.note_back_close()
            self.setFocusId(self.NAV_LIST_ID)
            return

        if (action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK)
                and self._browse_collection is not None):
            # Inside a collection, Back is the drill-down's own step out --
            # above the nav-bar rung, because leaving the collection is
            # what the viewer means before leaving Browse.
            self._browse_close_collection()
            return

        if action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK) and self.getFocusId() != self.NAV_LIST_ID:
            # Back returns to the nav bar first (tvOS/Android TV's "Back
            # goes to the top level before it exits"), instead of
            # immediately closing the screen. A second Back, now with nav
            # itself focused, falls through to ControlledWindow's own Back
            # handling below and actually exits.
            self.setFocusId(self.NAV_LIST_ID)
            return

        if action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            # Nav bar is focused, so this Back is the one that leaves the
            # add-on. Confirm instead of dropping straight out to Kodi's
            # menu -- modelled on plex-for-kodi's own exit dialog
            # (lib/windows/home.py:confirmExit).
            #
            # This is also the real backstop for a held Back. The
            # auto-repeat timing guard above is a nicety that stops the
            # dialog flashing; it is NOT load-bearing, because a repeat that
            # slips past it now opens a dialog whose own Back cancels it,
            # rather than quitting.
            choice = cardoptions.confirm_exit()
            if choice == cardoptions.MINIMIZE:
                # Kodi's home window. The add-on keeps running, so coming
                # back is instant and nothing is re-fetched.
                xbmc.executebuiltin("ActivateWindow(10000)")
            elif choice == cardoptions.EXIT:
                self.closeNow()
            return

        if (
            action_id == xbmcgui.ACTION_SHOW_INFO
            and self._cw_list_id is not None
            and self.getFocusId() == self._cw_list_id
        ):
            item = self.row_lists[self._cw_list_id].getSelectedItem()
            src = item.dataSource if item else None
            media_id = (src.get("media_id") or src.get("id")) if src else None
            if media_id:
                # Directly, not RunPlugin: that route opens Detail from a
                # SEPARATE script invocation, and backing out of it leaves
                # the add-on entirely rather than returning here. Same file
                # id the Select path hands over, so Info and Select land on
                # the same episode.
                self.open_detail(media_id=media_id,
                                  play_file_id=src.get("media_file_id"))
                return

        if action_id == xbmcgui.ACTION_CONTEXT_MENU:
            # 7.2's card options, on the context/menu key. 10.2 asks for a
            # long-press of Select and sanctions the dedicated key where the
            # remote has one free; Kodi's focus engine exposes no press
            # phase for Select at all, so the key IS the trigger here.
            #
            # This used to be Discover's watchlist toggle, bound here because
            # the "+" badge can't be an independently focusable child of a
            # Kodi list item. Watchlist is now a row in the panel, where 7.2
            # puts it, so the toggle no longer needs the key to itself.
            if self._open_card_options(self.getFocusId()):
                return

        if (action_id in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN)
                and self.getFocusId() == self.SETTINGS_NAV_ID):
            # Same tvOS "load as soon as the row is highlighted" rule the nav
            # bar uses for Left/Right, and the same reason for reading the
            # list's position as-is: Kodi has already applied the cursor move
            # by the time onAction sees it, so adding an offset would skip a
            # page. Base class first, THEN read -- unlike the nav bar, whose
            # own handler is reached after Kodi's list widget has moved.
            kodigui.ControlledWindow.onAction(self, action)
            self._settings_show_page()
            return

        if action_id in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
            if self.getFocusId() == self.NAV_LIST_ID:
                # Load the newly-highlighted screen immediately (tvOS-style)
                # instead of waiting for Select. Kodi already applies the
                # cursor move before onAction is invoked, so this reads the
                # list's current position as-is -- no +/-1, or it double-
                # applies the step and skips a tab.
                target = navbar.resolve_nav_focus(self, self.NAV_LIST_ID, self._current_target)
                if target:
                    self._open_nav_target(target)
                    return
                kodigui.ControlledWindow.onAction(self, action)
                return
            mlist = self.row_lists.get(self.getFocusId())
            if mlist:
                # Kodi's onFocus only fires when a *control* gains focus,
                # not when Left/Right moves the selection within an
                # already-focused horizontal list -- let the base class
                # actually move the selection first, then refresh the hero
                # from wherever it landed.
                kodigui.ControlledWindow.onAction(self, action)
                item = mlist.getSelectedItem()
                if item and item.dataSource:
                    self._home_update_hero(item.dataSource)
                return

        if (action_id in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN,
                          xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT)
                and self.getFocusId() == self.COLLECTION_GRID_ID):
            # The collections index is windowed like the poster grid, so it
            # tops up the same way: move first, then fill where it landed.
            # It never pages -- the whole index arrives in one response --
            # so there is no _browse_maybe_load_more equivalent here.
            kodigui.ControlledWindow.onAction(self, action)
            client = self._get_client()
            if client:
                self._browse_fill_collection_window(client)
            return

        if (action_id in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN,
                          xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT)
                and self.getFocusId() == self.GRID_ID):
            # All FOUR directions, not just Down: the grid is multi-column, so
            # Right walks along a row and reaches the end of the loaded set
            # just as readily. Kodi's onFocus does not fire when the selection
            # moves inside an already-focused list, so the base class moves
            # first and the check reads where it landed.
            kodigui.ControlledWindow.onAction(self, action)
            self._browse_maybe_load_more()
            return

        kodigui.ControlledWindow.onAction(self, action)

    # ==================================================================
    # HOME SECTION
    # ==================================================================

    def _home_load(self):
        # Timed because this runs on the ACTION thread: for however long it
        # takes, the window is frozen and keypresses are dropped, not
        # queued. Measured on the box after a profile switch (nothing
        # warmed) it was 3.6s and the viewer's Down never arrived. The split
        # between fetching and card-building is what says whether the
        # prefetch re-warm in _settings_switch_profile is enough, so both
        # halves are reported. Mirrors prefetch.warm's own line.
        started = time.monotonic()
        client = self._get_client()
        if not client:
            return

        rows_pref = ((self._ensure_preferences().get("home_screen") or {}).get("rows")) or []

        # Same fallback as addon.py's show_root_menu(): an account with no
        # home_screen preference at all still gets Continue Watching, not a
        # blank Home.
        if not rows_pref:
            rows_pref = [{"enabled": True, "type": "builtin", "id": "continue_watching"}]

        # HIDE EVERY ROW BEFORE REBUILDING IT. Each row group is gated on
        # `row{N}_title` (see the XML), so clearing them takes the rows off
        # the render thread for the duration of the build.
        #
        # Not cosmetic -- it halves the build. Every card is ~8 writes across
        # into Kodi's C++ side, and a write to a list Kodi is actively
        # drawing at 4K waits on it. Measured on the box, same 253 cards:
        #
        #   cold launch (nothing drawn yet)  0.59s   2.6ms/card
        #   reload, rows left visible       10.41s  47.0ms/card
        #   reload, rows hidden first        4.93s  21.4ms/card
        # ...except the row focus is actually ON. The load runs off the action
        # thread now, so the viewer can be standing in a row when it starts,
        # and hiding that row would leave focus on a control Kodi no longer
        # draws -- which is how the d-pad stops responding entirely.
        _focused = self.getFocusId()
        for _idx, _lid in enumerate(self.ROW_LIST_IDS):
            if _lid != _focused:
                self.setProperty("row{0}_title".format(_idx), "")

        discovery_payload: dict[str, dict] | None = None  # fetched lazily, once, only if a discovery row is present
        self._cw_list_id = None
        self._row_kinds = {}
        active_list_ids: list[int] = []
        slot = 0
        build_s = 0.0

        for row in rows_pref:
            if slot >= len(self.ROW_LIST_IDS):
                break
            if not row.get("enabled", True):
                continue

            row_type = row.get("type")
            if row_type == "builtin":
                row_id = row.get("id")
                label_id = home_rows.BUILTIN_ROW_LABELS.get(row_id)
                if not label_id:
                    log.debug(f"main.py: skipping unknown home_screen builtin row id={row_id}")
                    continue
                row_kind = "cw" if row_id == "continue_watching" else "library"
                row_title = _(label_id)
                items = self._home_fetch_builtin_row(client, row_id)
            elif row_type == "discovery":
                list_type = row.get("discoveryList")
                if not list_type:
                    log.debug("main.py: skipping home_screen discovery row with no discoveryList")
                    continue
                row_kind = "discovery"
                if discovery_payload is None:
                    discovery_payload = self._home_discovery_shelves(client)
                shelf = discovery_payload.get(list_type)
                if shelf is None:
                    log.debug(f"main.py: home_screen discovery row {list_type} not offered by this server")
                    continue
                items = shelf["items"]
                # Server-supplied title first: since 0.9.25 the Settings
                # home-screen editor can add any of the 32 shelves, so the
                # local label map only covers the original 7.
                label_id = home_rows.DISCOVERY_LIST_LABELS.get(list_type)
                row_title = _(label_id) if label_id else shelf["title"]
            elif row_type == "genre":
                # Added from the Settings home-screen editor as
                # {type: "genre", genre: <name>}; the genre's own name is
                # the row title, matching the web app.
                genre = row.get("genre")
                if not genre:
                    log.debug("main.py: skipping home_screen genre row with no genre")
                    continue
                row_kind = "library"
                row_title = genre
                items = self._home_genre_row_items(client, genre)
            else:
                log.debug(f"main.py: skipping unknown home_screen row type={row_type}")
                continue

            list_id = self.ROW_LIST_IDS[slot]
            mlist = self.row_lists[list_id]
            # Stage this row's artwork BEFORE building its cards, so every
            # card gets a stable local path rather than a tokenised URL that
            # will rotate. Batched on purpose -- a whole row costs ~0.13s at
            # four workers, against ~1s one image at a time. A no-op unless
            # artcache is enabled, and anything that misses the deadline just
            # falls back to the remote URL. See artcache.prefetch.
            artcache.prefetch(self._row_art(client, items))
            build_started = time.monotonic()
            managed = [self._home_build_row_managed_item(client, it, row_kind) for it in items]
            build_s += time.monotonic() - build_started
            mlist.reset()
            if managed:
                mlist.addItems(managed)
                mlist.selectItem(0)
                active_list_ids.append(list_id)
                self._row_kinds[list_id] = row_kind
                if row_kind == "cw":
                    self._cw_list_id = list_id

            # Empty rows clear their title property so the header + row
            # group hide (visible=!String.IsEmpty in the XML) -- applied
            # uniformly to every slot now, including Continue Watching.
            self.setProperty("row{0}_title".format(slot), row_title if managed else "")
            slot += 1

            # THE FIRST ROW IS THE SCREEN. Show it, and dress the hero from
            # it, before building the other eight.
            #
            # Building all nine rows takes 10-26s on the box and the hero
            # used to be set after the last of them, so for that whole time
            # Home was a blank page with no title, no backdrop and nothing to
            # look at -- even though the row the viewer actually wanted was
            # ready in the first second. Nothing here is faster; it simply
            # stops holding back what is already finished.
            if len(active_list_ids) == 1 and managed:
                first = mlist.getSelectedItem()
                if first and first.dataSource:
                    self._home_update_hero(first.dataSource)

        # Clear any slots beyond what this load populated (fewer server rows
        # than a previous load, or than MAX_HOME_ROWS) so a stale row/header
        # doesn't linger from before.
        for idx in range(slot, len(self.ROW_LIST_IDS)):
            self.setProperty("row{0}_title".format(idx), "")
            self.row_lists[self.ROW_LIST_IDS[idx]].reset()

        # The hero was already dressed from the first row above, as soon as
        # that row existed. Re-read here only because a later row can become
        # the first one when an earlier row turns out empty.
        if active_list_ids:
            first_item = self.row_lists[active_list_ids[0]].getSelectedItem()
            if first_item and first_item.dataSource:
                self._home_update_hero(first_item.dataSource)

        self._home_active_list_ids = list(active_list_ids)
        self._home_wire_row_nav(active_list_ids)
        total_s = time.monotonic() - started
        log.info("home: %d row(s) in %.2fs (%.2fs building cards, %.2fs fetching)"
                 % (len(active_list_ids), total_s, build_s, total_s - build_s))
        # AFTER the rows are on screen, deliberately. This is one small
        # request, but Home's load is the number we watch
        # (project_home_load_performance), and a version warning is worth
        # nothing to someone still looking at an empty screen. Browse and
        # Discover call the same thing lazily; whichever gets there first
        # pays for it once.
        self._ensure_capabilities()

    #: The ONE art field a Home card draws -- see
    #: _home_build_row_managed_item, which resolves `poster_path` and nothing
    #: else. `backdrop_path` and `logo_path` are HERO art, shown one item at
    #: a time as focus settles, so prefetching a row of them is work for
    #: images that will mostly never be displayed.
    #:
    #: Getting this wrong is expensive rather than broken: the first version
    #: staged all four fields, which turned rows of ~25 into batches of 50-81
    #: and took a cold Home load from 2.2s to 10.1s, with two rows timing out
    #: half-done. Measured, then narrowed to this.
    _CARD_ART_FIELD = "poster_path"

    def _row_art(self, client: MediaServerClient, items: list[dict]) -> list[tuple]:
        """(remote_url, server_path) for the art this row's cards will draw.

        stage_pairs, not resolve_image_url: the latter would re-enter artcache
        and queue the same downloads asynchronously behind the synchronous
        ones, and it is also what knows which images are ours to stage at
        all -- a discovery row's posters live on the tofa cloud CDN, need no
        token, and are already stable."""
        return client.stage_pairs(items, self._CARD_ART_FIELD)

    def _home_refresh_cw_row(self, client) -> None:
        """Rebuild the Continue Watching row alone, in place.

        NOT _home_load(). That rebuilds every row and is timed at 4.93s with
        the rows hidden first -- on the ACTION thread, so the window is
        frozen and keypresses are dropped rather than queued for the whole
        of it. Paying that to restate one card would be worse than the
        problem. Remove-from-Continue-Watching still takes the full reload;
        it changes the row's LENGTH, which is the case below.

        Falls back to the full load when the row comes back EMPTY, because
        an empty row has to hide its header and hand its Down target to the
        row beneath -- nav rewiring that _home_load already owns and that is
        not worth a second implementation for the last-episode case.
        """
        list_id = getattr(self, "_cw_list_id", None)
        mlist = self.row_lists.get(list_id) if list_id else None
        if mlist is None:
            return

        items = self._home_fetch_builtin_row(client, "continue_watching")
        if not items:
            self._home_load()
            return

        # Hold the viewer's place. The row is server-ordered and a promoted
        # episode keeps its slot, so the index is the right thing to keep,
        # not the item -- the card at this position is deliberately a
        # DIFFERENT one now. Clamped, since the row can also get shorter.
        keep = 0
        selected = mlist.getSelectedPos()
        if selected is not None and selected >= 0:
            keep = min(selected, len(items) - 1)

        artcache.prefetch(self._row_art(client, items))
        managed = [self._home_build_row_managed_item(client, it, "cw") for it in items]
        mlist.reset()
        mlist.addItems(managed)
        mlist.selectItem(keep)

        # The hero mirrors the focused card, so it is now describing an
        # episode that is no longer there.
        current = mlist.getSelectedItem()
        if current is not None and self.getFocusId() == list_id:
            self._home_update_hero(current.dataSource)

    def _home_fetch_builtin_row(self, client: MediaServerClient, row_id: str) -> list[dict]:
        # Taken once, if the launch already fetched it while the splash was
        # up. A later reload falls through and asks the server, which is what
        # someone returning to Home wants.
        warmed = prefetch.take_row(row_id)
        if warmed is not None:
            return warmed
        return prefetch.fetch_builtin_row(client, row_id)

    def _home_genre_row_items(self, client: MediaServerClient, genre: str) -> list[dict]:
        """Items for a Settings-added genre row. Same call the web app makes:
        the plain media list narrowed to one genre, newest first. `genre`
        takes the genre NAME, not a slug (see api.py:genres())."""
        try:
            resp = client.media_list(
                media_type=None, genre=genre, sort="added_at", order="desc",
                page=1, per_page=20,
            )
        except http.ApiError as exc:
            kodigui.ERROR("main.py: genre row {0} failed: {1}".format(genre, exc))
            return []
        return (resp or {}).get("items") or []

    def _home_discovery_shelves(self, client: MediaServerClient) -> dict[str, dict]:
        """Discovery shelves a home row can reference, keyed by every id the
        server might have written into preferences.home_screen.rows: the new
        shelf `key`, plus the old `list_type` alias where one exists.

        Sourced from the 32-shelf page when the server offers it -- the old
        endpoint only knows 7, so a row added from the 0.9.25 Settings
        editor would otherwise resolve to nothing and be dropped."""
        shelves: dict[str, dict] = {}
        if self._has_capability("discovery.page"):
            try:
                page = client.discovery_page() or {}
            except http.ApiError as exc:
                kodigui.ERROR("main.py: discovery/page failed: {0}".format(exc))
                page = {}
            for s in (page.get("shelves") or []):
                entry = {"title": s.get("title") or "", "items": s.get("items") or []}
                for key in (s.get("key"), s.get("list_type")):
                    if key:
                        shelves.setdefault(key, entry)
            if shelves:
                return shelves
        try:
            payload = client.discovery_lists() or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: discovery_lists failed: {0}".format(exc))
            return shelves
        for named in (payload.get("lists") or []):
            lt = named.get("list_type")
            if lt:
                shelves[lt] = {"title": _discover_list_title(lt),
                               "items": named.get("items") or []}
        return shelves

    def _home_build_row_managed_item(self, client: MediaServerClient, item: dict, row_kind: str) -> kodigui.ManagedListItem:
        """Unified poster-card builder for every row kind. row_kind gates
        the things that actually differ: episode-aware label + progress bar
        for Continue Watching; a has_detail marker for library-owned rows
        (recent/top-rated/suggested); nothing extra for
        discovery rows (their tmdb_id/local_media_id/type live on
        data_source instead, resolved at click time -- see
        _home_detail_clicked)."""
        title = item.get("title") or ""
        label = title
        if row_kind == "cw" and (item.get("kind") == "episode" or item.get("episode_id")) and item.get("episode_title"):
            label = u"{0} - {1}".format(title, item["episode_title"])

        poster = client.resolve_image_url(item.get("poster_path")) or ""
        # offscreen=True is the fix for issue #11. These cards are built
        # detached and handed to addItems() below, so there is nothing on
        # screen for Kodi's frame-move guard to protect while we write them --
        # and taking it anyway is what made this loop cost 26s. Measured on
        # the box under a sustained 4K poster load, the same eight writes:
        #
        #   offscreen=False   0.859 ms/card   (0.048 idle -- 18x worse under load)
        #   offscreen=True    0.035 ms/card   (0.035 idle -- unchanged)
        #
        # The lock is g_application.LockFrameMoveGuard(), held for the whole
        # of FrameMove+Render, so an unlucky write waits a WHOLE FRAME: a
        # single 254-card batch was measured blocking 1237ms at 1fps. That is
        # why the cost looked "environmental to the box" and why it split
        # evenly across label/setArt/rating/badges -- every setter takes the
        # same lock, and a label has nothing to do with artwork.
        #
        # The residual: _card_options_picked writes `watched`/`watchlisted`
        # onto a LIVE card, and those two writes are now unlocked. Kodi's own
        # docs say an item you modify later should keep the default. Judged
        # worth it at 2 writes per menu action against 2032 per load -- but it
        # is the one place this trade is visible, so it is named here.
        mli = cards.poster_item(item, poster, label=label,
                                prefs=self._ensure_preferences(), offscreen=True)

        if row_kind == "cw":
            self._apply_card_progress(mli, item)

        # "YEAR" left; the trailing "NN MIN LEFT" is set by
        # _apply_card_progress above, and left alone outside Continue
        # Watching. Two properties, not one joined string, because 6
        # justifies the Continue Watching meta line to the card edges with no
        # separator (see fragments.py's caption block).
        mli.setProperty("caption_meta", _card_meta_left(item))

        if row_kind == "library":
            # Owned titles carry a local media id (MediaSummary `id`) --
            # route those to the detail window.
            media_id = item.get("id") or item.get("media_id")
            if media_id:
                # Marks the card as one that HAS a detail screen;
                # _home_detail_clicked reads the id off the data source
                # itself rather than routing through this URL.
                mli.setProperty("has_detail", "1")

        return mli

    @staticmethod
    def _apply_card_bar(mli: kodigui.ManagedListItem, item: dict):
        """Write a poster card's progress bar from its own data_source.

        The fill is one of 51 pre-rendered rounded-left-cap strips
        (media/poster-progress/<even-pct>.png, see tools/gen_poster_assets.py)
        -- not the shared media/progress/ folder, which is a plain rectangle
        that can't do the cap or the poster's corner clipping."""
        duration_ms = item.get("duration_ms") or 0
        position_ms = item.get("position_ms") or 0
        step = progress.fill_step(position_ms, duration_ms)
        if step:
            mli.setProperty("progress_pct", str(progress.fraction(position_ms, duration_ms)))
            mli.setProperty("progress_fill", "poster-progress/{0}.png".format(step))
        else:
            # Cleared rather than left alone: on a refresh this card may have
            # just been rewound to the start, and a stale bar under it would
            # be the exact lie the refresh exists to prevent.
            mli.setProperty("progress_pct", "")
            mli.setProperty("progress_fill", "")

    @classmethod
    def _apply_card_progress(cls, mli: kodigui.ManagedListItem, item: dict):
        """A Continue Watching card's bar AND its "NN MIN LEFT" caption.

        One writer, called when the card is built AND whenever Home comes
        back to the front, so a refreshed card cannot drift from a fresh one.
        Everything it needs comes out of `item`, which is the card's own
        data_source -- so refreshing is "update the dict, call this again".

        Browse's watch history calls _apply_card_bar directly instead: those
        cards spend their caption on the date they were watched, which is the
        one thing a session log adds over the plain title."""
        cls._apply_card_bar(mli, item)
        mli.setProperty("caption_trailing", progress.minutes_left_label(
            item.get("position_ms") or 0, item.get("duration_ms") or 0))

    def refresh_watch_progress(self):
        """Re-read Continue Watching and repaint the row -- MEMBERSHIP AND
        ALL, not just the positions of the cards that happen to be on it.

        See progress.py: a screen's copy of position_ms is only as fresh as
        its last load, and Home does not reload when playback hands back.

        This used to refresh positions ONLY, on the reasoning that
        re-ordering a row under the viewer's focus was worse than a card
        that was merely stale. That trade does not survive contact with what
        actually changes the row:

          - Marking an episode watched (or unwatched) in Detail is the
            viewer ASKING for the row to change. It kept the card.
          - Finishing an episode moves the show's Continue Watching entry to
            the NEXT one -- a different media_file_id. The old card stayed,
            still captioned with the episode just finished, and the fresh
            position for it was fetched and painted, which made the wrong
            answer look deliberate.
          - Anything started on another device never appeared at all.

        Membership is the whole point of the row, so it is what gets
        re-read. The cost is unchanged: one request either way, /users/me/
        continue instead of a bulk progress lookup, and it carries the
        positions too.

        Focus is protected explicitly instead: whatever card the viewer was
        on is looked up again by media_id and reselected, so a row that
        merely reordered leaves them where they were.
        """
        if self._cw_list_id is None:
            return
        mcl = self.row_lists.get(self._cw_list_id)
        if mcl is None:
            return
        client = self._get_client()
        if not client:
            return
        items = self._home_fetch_builtin_row(client, "continue_watching")

        selected = mcl.getSelectedItem() if len(mcl) else None
        was_on = (selected.dataSource or {}).get("media_id") if selected else None
        had_focus = self.getFocusId() == self._cw_list_id
        previous_len = len(mcl)

        managed = [self._home_build_row_managed_item(client, it, "cw")
                   for it in items]
        mcl.reset()
        if managed:
            mcl.addItems(managed)
            index = next(
                (i for i, mli in enumerate(managed)
                 if (mli.dataSource or {}).get("media_id") == was_on), 0)
            mcl.selectItem(index)
        self.setProperty(
            "row{0}_title".format(self.ROW_LIST_IDS.index(self._cw_list_id)),
            _(home_rows.BUILTIN_ROW_LABELS["continue_watching"]) if managed else "")

        # A row that has just emptied (the last part-watched title finished)
        # hides itself, and Kodi will not leave focus on a hidden list --
        # the d-pad dies there. Hand focus to the nav bar, which is where
        # Down from the top goes anyway.
        if had_focus and not managed:
            try:
                self.setFocusId(self.NAV_LIST_ID)
            except RuntimeError:
                pass
        # Appearing or disappearing changes which slots are populated, so
        # the vertical chain has to be re-pointed -- see _home_wire_row_nav.
        if bool(previous_len) != bool(managed):
            active = [cid for cid in self._home_active_list_ids
                      if cid != self._cw_list_id]
            if managed:
                active.append(self._cw_list_id)
                # Back into slot order: the chain is positional, not
                # arrival-ordered.
                active.sort(key=self.ROW_LIST_IDS.index)
            self._home_active_list_ids = active
            self._home_wire_row_nav(active)

    def _home_wire_row_nav(self, active_list_ids: list[int]):
        """Vertical Down/Up between nav + whichever row slots actually came
        back non-empty this load. XML wires the full static chain
        (nav -> slot0 -> slot1 -> ... -> slot8, each self-looping at the
        end); this re-points around any slot that's empty (hidden) this
        load, and around the tail past however many slots are actually
        populated."""
        # Keep the nav bar's own Down target (see _section_down_targets)
        # current too -- which slot ends up first varies per account/order,
        # and Home's own _load() can rerun later with a different set of
        # populated rows.
        self._section_down_targets["home"] = active_list_ids[0] if active_list_ids else self.NAV_LIST_ID

        chain = [self.getControl(self.NAV_LIST_ID)] + [self.getControl(cid) for cid in active_list_ids]
        for i, ctrl in enumerate(chain):
            down = chain[i + 1] if i + 1 < len(chain) else ctrl
            up = chain[i - 1] if i > 0 else ctrl
            try:
                ctrl.controlDown(down)
                if i > 0:
                    ctrl.controlUp(up)
            except Exception:
                pass

    def _settle_delay_ms(self) -> int:
        """7.9.6's settle delay, preferring the account's own value."""
        if not self._settle_ms_from_prefs:
            self._settle_ms_from_prefs = True
            try:
                raw = (self._ensure_preferences() or {}).get("layout.focusedBackdropDelayMs")
                if raw is not None:
                    self._settle.set_delay(int(str(raw).strip()))
            except (TypeError, ValueError):
                pass
        return self._settle.delay_ms

    def _home_update_hero(self, item: dict):
        """The WHOLE hero waits for focus to settle, then changes as one.

        The backdrop is a full-screen texture and the logo another, so doing
        either per keypress means a viewer holding Right pays two texture
        loads per card crossed -- measured on the CoreELEC box as the 1-4fps
        troughs that make a row scrub feel like it is catching. 7.9.6 asks
        for exactly that ("crossfading as focus settles").

        The text used to be exempt, on the grounds that property writes are
        cheap and would "read as lag if they trailed the cursor". True about
        the cost, wrong about the look: it made the hero change in two
        instalments, the words on the keypress and the picture ~200ms later,
        which is what Adrian reported on 2026-08-13 as the title and synopsis
        changing abruptly under a backdrop that dissolves. 7.10.2 asks for
        one crossfading hero, not a hero whose halves disagree about when
        the focus moved. So the text settles too, and the price is that a
        fast scrub leaves the hero behind until the cursor stops -- which is
        what a settle delay is FOR.
        """
        self._settle_delay_ms()
        self._settle.schedule(lambda: self._home_update_hero_art(item))

    def _home_update_hero_art(self, item: dict):
        client = self._get_client()
        if client:
            # Stage the hero's two images BEFORE resolving them. This is the
            # last place a tokenised URL still reached Kodi's texture cache:
            # measured 2026-08-12, every focus change on a title not seen
            # before filed exactly two rows, one backdrop and one logo, which
            # are dead the moment the token rotates an hour later.
            #
            # Blocking is safe here and nowhere else on this path -- the hero
            # runs on SettleTimer's own thread, already debounced by
            # FOCUS_SETTLE_MS, so the UI thread is not waiting on it. Two
            # images on the LAN is ~100ms, and only on a miss.
            #
            # Not batched across the row: prefetching every card's hero was
            # measured at 10.09s on a cold Home (rows of 50-81 images, two
            # timing out half-staged) and is not worth revisiting. Only the
            # focused item's hero is ever drawn.
            artcache.prefetch(
                client.stage_pairs([item], "backdrop_path", "logo_path"),
                timeout_s=self.HERO_STAGE_TIMEOUT_S)
        # Start the foreground's dip NOW, in the same breath as handing the
        # backdrop its new texture: <fadetime> begins the moment the texture
        # changes, so both halves of the hero start their 300ms here and land
        # together. Dipping first and swapping the backdrop afterwards would
        # cost the backdrop the dip's length in added latency, on top of the
        # settle delay it already waits out.
        self.setProperty("hero_swapping", "1")

        backdrop = client.resolve_image_url(item.get("backdrop_path")) if client else None
        self.setProperty("hero_backdrop", backdrop or "")
        self.getControl(9000).setImage(backdrop or "")

        # tofa serves logo_path as SVG, which Kodi's texture loader can't
        # render -- treat it as unavailable, or the image control shows
        # nothing AND the text fallback stays hidden (its <visible> only
        # checks for an empty property, not a renderable one), leaving no
        # title at all.
        logo = client.resolve_image_url(item.get("logo_path")) if client else None
        if logo and logo.split("?", 1)[0].lower().endswith(".svg"):
            logo = None

        # Everything the dipping group draws is written by the commit below,
        # once the group is invisible. A SettleTimer rather than a sleep on
        # this thread: it carries the same drop-it-if-the-window-closed
        # guarantee, and its replace-the-pending behaviour means a second
        # focus change during the dip lands one swap, not two.
        self._hero_swap.schedule(lambda: self._home_commit_hero_foreground(item, logo))

    def _home_commit_hero_foreground(self, item: dict, logo: str | None):
        """Swap the hero's foreground while nobody can see it, then bring it
        back. Clearing `hero_swapping` IS the fade-in: it turns the group's
        <visible> back on, which is what plays its Visible animation."""
        self.setProperty("hero_logo", logo or "")
        self._home_update_hero_text(item)
        self.setProperty("hero_swapping", "")

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

    def _home_update_hero_text(self, item: dict):
        title = item.get("title") or ""
        if item.get("episode_title"):
            title = u"{0} - {1}".format(title, item["episode_title"])
        self._set_hero_title(title)

        genres = item.get("genres") or []
        runtime_minutes = None
        if item.get("duration_ms"):
            runtime_minutes = int(item["duration_ms"] // 60000)
        elif item.get("runtime_minutes"):
            runtime_minutes = int(item["runtime_minutes"])
        meta_parts = [_item_year(item)]
        if runtime_minutes:
            hours, minutes = divmod(runtime_minutes, 60)
            meta_parts.append("{0} h {1} min".format(hours, minutes) if hours else "{0} min".format(minutes))
        meta_parts.extend(genres[:2])
        self.setProperty("hero_meta_line", _dot_join(*meta_parts))

        self.setProperty("hero_ratings_line", self._hero_rating_line(item))

        synopsis = item.get("overview") or ""
        self.setProperty("hero_synopsis", synopsis)

    def _home_cw_clicked(self):
        """Select on a Continue Watching card opens DETAIL, not the player.

        It used to play immediately, which made this the only Home row that
        did not open its title, and left Detail reachable from a CW card
        only through a 500ms hold -- while 7.2's own card-options panel
        offers Play and Details as two separate things, so Select and
        long-press-Play were doing the same job and Details had nowhere of
        its own.

        TV-DESIGN does not settle this: it says a great deal about Continue
        Watching (privileged first section, its own caption grammar, its
        exclusive Remove item) but never what a bare Select does there. The
        one play-on-select rule it states, 7.9's "in-library items open to
        play", is scoped to Discover. The reference app opens Detail.

        Nothing is lost by the extra press: Detail re-reads the position at
        the moment its pill is pressed (_fresh_resume_ms), so it opens
        already reading Resume with this title's real progress under it."""
        if self._cw_list_id is None:
            return
        item = self.row_lists[self._cw_list_id].getSelectedItem()
        if not item:
            return
        src = item.dataSource or {}
        media_id = src.get("media_id")
        if media_id:
            # Opened directly, not via RunPlugin, so Detail layers over this
            # window rather than replacing it. The card names its own
            # episode, so hand the file id over rather than making Detail
            # infer which episode this row meant.
            self.open_detail(media_id=media_id,
                              play_file_id=src.get("media_file_id"))
            return

        # No media id on the row: there is no detail screen to open, so
        # rather than make the card a dead press it still plays. Resume is
        # re-read here for the same reason Detail re-reads it -- Home does
        # not rebuild when playback hands back, so src["position_ms"] is as
        # old as the card.
        file_id = src.get("media_file_id")
        if not file_id:
            return
        client = self._get_client()
        resume_ms = src.get("position_ms")
        if client:
            resume_ms = progress.resume_position_ms(client, file_id, fallback=resume_ms)
        from .player import PlayerWindow

        # Same pre-flight Detail runs -- ask for the PIN here, if this is
        # long enough to outlive the token, rather than partway through.
        if profile_select.renew_for_playback(
                (src.get("duration_ms") or 0) - (resume_ms or 0)):
            self.client = None

        PlayerWindow.open(
            file_id=file_id,
            media_id=None,
            resume_ms=resume_ms,
            title=item.getLabel(),
        )

    def _home_detail_clicked(self, mlist, row_kind: str):
        item = mlist.getSelectedItem()
        if not item or not item.dataSource:
            return
        if row_kind == "discovery":
            # Opened directly (not RunPlugin) so Detail layers over this
            # window instead of replacing it.
            data = item.dataSource
            self.open_detail(
                media_id=data.get("local_media_id"),
                discovery_id=data.get("tmdb_id"),
                media_type=data.get("type"),
            )
            return
        # Opened DIRECTLY, like every other card in this add-on.
        #
        # This used to be RunPlugin(plugin://...detail_window), which reached
        # the right screen but through addon.py's router in a SEPARATE script
        # invocation. Backing out of that Detail page did not return here --
        # it dropped the viewer onto Kodi's own home screen, out of the
        # add-on entirely, because the window this one is modal in is not the
        # window that opened it. Reproduced from a Home row every time, while
        # the same title opened from Browse came back correctly.
        #
        # Continue Watching next door already did it this way, which is why
        # that row never had the bug.
        src = item.dataSource or {}
        media_id = src.get("id") or src.get("media_id")
        if media_id:
            self.open_detail(media_id=media_id)

    # ==================================================================
    # BROWSE SECTION -- Watchlist/History/Collections/Surprise Me fixed
    # rows + per-library rows below a divider. Poster captions are
    # year-only here; "year · genre" is Discover's own caption grammar.
    # ==================================================================

    def _browse_load(self):
        self._ensure_capabilities()
        self._browse_build_sidebar()
        # The rail is filled from the facets, so it is built at the END of
        # _browse_apply_facets() rather than here -- it has nothing to show
        # until that response is in. Same overlapped load a source switch
        # uses; entering Browse pays the same two requests.
        self._browse_load_source_content()

    def _ensure_capabilities(self):
        """Server-wide feature flags, fetched at most once per window.
        Feature-detect rather than version-match: gates the Filter dialog's
        "Played" watch-status option on `media.watched_played`, and the
        32-shelf Discover surface on `discovery.page`.

        Shared by Browse and Discover, either of which may be the first
        section the user opens, so it can't live in one section's load."""
        if self._capabilities_loaded:
            return
        client = self._get_client()
        if not client:
            return
        try:
            info = client.system_info() or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: system_info failed: {0}".format(exc))
            return
        self._server_capabilities = set(info.get("capabilities") or [])
        self._capabilities_loaded = True
        # Same response, so the version check is free here. It warns at most
        # once per Kodi session and only when the server is genuinely older
        # -- see serverversion, which treats an unreadable version as fine
        # rather than guessing.
        try:
            serverversion.warn_if_old(
                info.get("version"), alert=cardoptions.alert,
                localize=_)
        except Exception as exc:                       # never block the load
            log.warning(f"main.py: server version check failed: {exc!r}")

    def _has_capability(self, name: str) -> bool:
        self._ensure_capabilities()
        return name in self._server_capabilities

    def _ensure_preferences(self) -> dict:
        """The signed-in profile's preferences blob, fetched at most once per
        window. Per-profile, not per-account: the same request under a
        different X-Profile-Id returns different values."""
        # TAKEN, not peeked: _settings_write() drops this cache to force a
        # re-read after saving, and a prefetch that kept answering would make
        # every settings change look like it had not saved.
        if self._preferences is None:
            self._preferences = prefetch.take_preferences()
        if self._preferences is None:
            client = self._get_client()
            if not client:
                return {}
            try:
                self._preferences = ((client.whoami() or {}).get("preferences")) or {}
            except http.ApiError as exc:
                kodigui.ERROR("main.py: whoami failed: {0}".format(exc))
                self._preferences = {}
        # Remembered for the player wherever the blob came from -- the
        # prefetch above answers most of the time, and it is just as good a
        # source. See playbackprefs.py for what the player does without it.
        playbackprefs.remember((self._preferences or {}).get("playback"))
        return self._preferences

    def _hero_rating_line(self, item: dict) -> str:
        """Hero rating line: "Critics 82 • Audience 66" -- labelled, unlike the
        bare number on a poster badge, because the hero has room and the label
        is what tells the two scores apart.

        BOTH scores, deliberately ignoring the profile's
        preferred_card_rating. That preference governs the one number a poster
        BADGE has room for; the hero is a full line and the spec and the real
        app both show the pair there (captured 2026-07-31: "Critics 82 •
        Audience 66"). Same reasoning as Discover's open card, which has
        always shown the pair.

        Falls back to whichever single score exists, and to nothing at all
        when neither does -- 11 forbids rating-source marks outright ("no
        IMDb/RT/star iconography", founder decision 2026-07-26), so a title
        with no tofa score shows no rating rather than borrowing one. The
        numerals ride the quality ramp; labels stay at the control's muted
        color."""
        parts = []
        for field, label in (("tofa_critics_rating", "Critics"),
                             ("tofa_audience_rating", "Audience")):
            numeral = theme.rating_numeral(item.get(field))
            if numeral:
                parts.append(u"{0} {1}".format(label, numeral))
        return _dot_join(*parts)

    def _browse_watched_options(self) -> tuple:
        """(label, api `watched` value) tuples for the Filter dialog's
        Watch Status axis. "Played" (the finished-or-partway union, per
        the API's own param description) only appears when the server
        advertises `media.watched_played` -- see _ensure_capabilities()."""
        options = list(self.BROWSE_WATCHED_OPTIONS_BASE)
        if "media.watched_played" in self._server_capabilities:
            options.append(("Played", "played"))
        return tuple(options)

    def _browse_filter_label(self) -> str:
        """The whole line on the Filter pill -- every axis that is set, in
        the order the dialog asks about them: "Unwatched", "4K, 2020s",
        "In Progress, Dolby Vision, Before 1980".

        THE DEFAULTS ARE LEFT OUT. "All", "All Years" and "Any" are three
        different ways of saying "I did not filter on this", which is what
        the pill says by not mentioning the axis at all. Naming them would
        also cost the room the real answers need.

        Format was missing entirely until 2026-08-09, which was the visible
        half of the bug: its pill went when the axis moved into this dialog,
        so a Browse filtered to 4K said "Filter: All".

        UNFILTERED READS "Filter", not "Filter: All". The pill is the only
        one on the row that has no value to show when it is off, so it falls
        back to naming itself -- which is exactly what the real app puts
        there permanently (Android 0.1.11, and the Apple TV capture agrees).
        "All" alone would be a value that says nothing, and next to a Sort
        pill now reading a bare "Date Added" it would read as a fourth
        filter rather than as "off".

        Three axes cannot fit however they are spelled (the narrowest such
        line measures 254px against a 248px column), so Kodi ellipsizes the
        tail. That is the right thing to lose: the axes are listed in the
        order the panel asks about them, so what survives is what the viewer
        chose first, and the "..." says the rest is there.
        """
        # Watch Status, Format, Year -- the panel's own order. Keep the two in
        # step: the promise above is that a truncated line drops the axes the
        # viewer reached last, and that only holds if this matches _browse_
        # open_filter's `sections`.
        parts = []
        if self._browse_watched_idx != 0:
            parts.append(self._browse_watched_options()[self._browse_watched_idx][0])
        if self._browse_quality_idx != 0:
            parts.append(self.BROWSE_QUALITY_OPTIONS[self._browse_quality_idx][0])
        if self._browse_year_idx != 0:
            parts.append(self.BROWSE_YEAR_OPTIONS[self._browse_year_idx][0])
        return ", ".join(parts) if parts else "Filter"

    def _browse_offered_sorts(self) -> list[int]:
        """Indices into BROWSE_SORT_OPTIONS this server will actually honour.

        The facets response carries a `sorts` vocabulary, and offering a sort
        outside it is offering something that silently does nothing -- /media
        ignores an unrecognised parameter rather than rejecting it, the same
        trap `letter=` set (see _browse_load_grid). So an option the server
        does not list is not shown at all.

        A server that says nothing gets the whole table: `None` means "never
        asked", which is not "answered with an empty list". Unknown keys the
        server offers and we have no row for are skipped rather than
        invented -- a client cannot make up a good label for `popularity` --
        but they are logged, so a new one is discoverable rather than silently
        missing.
        """
        if self._browse_server_sorts is None:
            return list(range(len(self.BROWSE_SORT_OPTIONS)))
        offered = [i for i, (_label, value, _order)
                   in enumerate(self.BROWSE_SORT_OPTIONS)
                   if value in self._browse_server_sorts]
        unknown = (set(self._browse_server_sorts)
                   - {v for _l, v, _o in self.BROWSE_SORT_OPTIONS})
        if unknown:
            log.debug("main.py: server offers sorts we have no row for: %s"
                      % sorted(unknown))
        # Never leave the viewer with nothing to sort by. A server whose
        # vocabulary overlaps ours in nothing at all is a wrong answer
        # somewhere; showing the local table beats an empty picker.
        return offered or list(range(len(self.BROWSE_SORT_OPTIONS)))

    def _browse_apply_server_sort_default(self, default_sort, default_order):
        """Adopt the server's declared default sort, if the viewer has not
        chosen one.

        `default_order` is the direction for that sort, which our own table
        also carries an opinion about -- so it is stored as the REVERSED flag
        relative to our entry, which is the form the pill, the glyph and the
        query all already read. Getting that wrong would show a down arrow
        over an ascending grid.
        """
        if self._browse_sort_user_picked or not default_sort:
            return
        for i, (_label, value, order) in enumerate(self.BROWSE_SORT_OPTIONS):
            if value != default_sort:
                continue
            self._browse_sort_idx = i
            # Shuffle has no direction, so nothing to reverse.
            self._browse_sort_reversed = bool(
                order and default_order and default_order != order)
            self._browse_sync_sort_pill()
            return
        log.debug("main.py: server default_sort %r has no row here" % default_sort)

    def _browse_sync_sort_pill(self):
        """Write the Sort pill from whatever _browse_sort_idx now is."""
        if self.sort_list is None:
            return
        self.sort_list[0].setProperty(
            "sort_label", self.BROWSE_SORT_OPTIONS[self._browse_sort_idx][0])
        self.sort_list[0].setProperty("sort_glyph", self._browse_sort_glyph())

    def _browse_sort_glyph(self) -> str:
        """The Sort pill's leading mark: which way this sort actually runs.

        The generic up-AND-down pair says "this control sorts", which the
        word next to it already said. A single arrow says something the pill
        could not otherwise tell you without being read: whether Date Added
        is newest-first or oldest-first, which is exactly what the reverse
        toggle changes and what nothing on screen used to reflect.

        Shuffle gets the SHUFFLE mark rather than an arrow, because it has no
        direction at all -- an arrow there would be a lie, and the generic
        up-and-down pair only said "this sorts". The same mark already means
        "randomised" on the sidebar's Surprise Me row; that is a shared
        vocabulary, not a collision, because both mean the same thing.

        Same vocabulary as the Sort picker's own rows (see picker.py's
        direction_glyph): down = descending, up = ascending. `reversed` is
        applied here rather than stored, mirroring _browse_load_grid, so the
        two can't disagree about which way the grid is actually running.
        """
        _label, value, order = self.BROWSE_SORT_OPTIONS[self._browse_sort_idx]
        # "random" is the ONLY directionless option (see BROWSE_SORT_OPTIONS,
        # where it is the one carrying order=None). Should another ever join
        # it, give it its own mark here rather than letting it fall through
        # to an arrow that would claim a direction it does not have.
        if value == "random":
            return chr(icon_glyphs.SHUFFLE)
        if self._browse_sort_reversed:
            order = "asc" if order == "desc" else "desc"
        return chr(icon_glyphs.ARROW_DOWN if order == "desc"
                   else icon_glyphs.ARROW_UP)

    def _browse_genre_label(self) -> str:
        """The Genre pill's whole line: the genre, or the bare word "Genre".

        Same rule as _browse_filter_label, for the same reason. The pill used
        to read "Genre: Action", and dropping the prefix everywhere else made
        the unset value the problem rather than the width: a lone "All" next
        to a Sort pill reading "Date Added" says nothing about what it is all
        OF. Naming itself is what the row's other value-less control already
        does.
        """
        genre = self._active_genre
        return genre if genre and genre != self.ALL_GENRES else "Genre"

    def _browse_build_sidebar(self):
        client = self._get_client()
        self._sources = [
            {"kind": "watchlist", "name": "Watchlist", "glyph": icon_glyphs.BOOKMARK},
            {"kind": "history", "name": "History", "glyph": icon_glyphs.ROTATE_CCW_CLOCK},
            {"kind": "collections", "name": "Collections", "glyph": icon_glyphs.LAYERS},
        ]
        if client:
            try:
                libs = client.libraries() or []
            except http.ApiError as exc:
                kodigui.ERROR("main.py: browse libraries failed: {0}".format(exc))
                libs = []
            for lib in libs:
                media_type = lib.get("media_type")
                if media_type == "movie":
                    glyph = icon_glyphs.CLAPPERBOARD
                elif media_type == "tv":
                    glyph = icon_glyphs.TV
                else:
                    glyph = icon_glyphs.VIDEO
                self._sources.append({
                    "kind": "library",
                    "id": lib.get("id"),
                    "name": lib.get("name") or "Library",
                    "media_type": media_type,
                    "glyph": glyph,
                    # /api/v1/libraries carries no item count; a per_page=1
                    # /media call returns the `total` cheaply.
                    "count": _library_count(lib) or self._browse_fetch_library_count(client, lib),
                })

            # Collections' own sidebar count badge (matches the real app
            # showing e.g. "522" next to Collections) -- cheap, one small
            # call, no per-item cost.
            try:
                collections_resp = client.collections() or {}
                count = len(collections_resp.get("collections") or [])
                # User-made collections (0.9.33) count too -- the grid
                # shows both, so the badge must agree with it.
                try:
                    count += len((client.custom_collections() or {}).get("collections") or [])
                except http.ApiError as exc:
                    kodigui.ERROR("main.py: browse custom collections count failed: {0}".format(exc))
                self._sources[2]["count"] = str(count)
            except http.ApiError as exc:
                kodigui.ERROR("main.py: browse collections count failed: {0}".format(exc))

        # default active = first real library if one exists, else Watchlist.
        self._active_source_idx = self.BROWSE_FIXED_SOURCE_COUNT if len(self._sources) > self.BROWSE_FIXED_SOURCE_COUNT else 0

        fixed_managed = []
        for idx in range(self.BROWSE_FIXED_SOURCE_COUNT):
            src = self._sources[idx]
            mli = kodigui.ManagedListItem(label=src["name"], data_source=src)
            mli.setProperty("icon_glyph", chr(src["glyph"]))
            mli.setProperty("count", src.get("count", ""))
            mli.setProperty("active", "1" if idx == self._active_source_idx else "0")
            fixed_managed.append(mli)
        # "Surprise Me" action row, wedged in right after the fixed sources
        # -- deliberately NOT part of self._sources, see
        # BROWSE_SURPRISE_ME_LIST_POS's docstring.
        surprise_mli = kodigui.ManagedListItem(label="Surprise Me", data_source={"kind": "surprise_me"})
        surprise_mli.setProperty("icon_glyph", chr(icon_glyphs.SHUFFLE))
        fixed_managed.append(surprise_mli)
        self.sidebar_list.reset()
        self.sidebar_list.addItems(fixed_managed)

        library_managed = []
        for idx in range(self.BROWSE_FIXED_SOURCE_COUNT, len(self._sources)):
            src = self._sources[idx]
            mli = kodigui.ManagedListItem(label=src["name"], data_source=src)
            mli.setProperty("icon_glyph", chr(src["glyph"]))
            mli.setProperty("count", src.get("count", ""))
            mli.setProperty("active", "1" if idx == self._active_source_idx else "0")
            library_managed.append(mli)
        self.sidebar_library_list.reset()
        self.sidebar_library_list.addItems(library_managed)

        if self._active_source_idx < self.BROWSE_FIXED_SOURCE_COUNT:
            self.sidebar_list.selectItem(self._active_source_idx)
        else:
            self.sidebar_library_list.selectItem(self._active_source_idx - self.BROWSE_FIXED_SOURCE_COUNT)
        self._browse_rewire_grid_left(self._active_source_idx)

    def _browse_fixed_pos_to_source_idx(self, pos: int) -> int | None:
        """Position in the fixed-sources list (6000) -> self._sources
        index. None means this position IS the Surprise Me row, not a
        real source."""
        if pos == self.BROWSE_SURPRISE_ME_LIST_POS:
            return None
        return pos

    def _browse_library_pos_to_source_idx(self, pos: int) -> int:
        """Position in the per-library list (6010) -> self._sources index."""
        return self.BROWSE_FIXED_SOURCE_COUNT + pos

    def _browse_set_source_active(self, idx: int, active: bool):
        """Sets the "active" ListItem property on whichever single row
        (fixed list or library list) corresponds to source index `idx` --
        see _browse_switch_source()'s own comment for why this touches
        exactly one row instead of relisting either list."""
        value = "1" if active else "0"
        if idx < self.BROWSE_FIXED_SOURCE_COUNT:
            li = self.sidebar_list[idx]
        else:
            li = self.sidebar_library_list[idx - self.BROWSE_FIXED_SOURCE_COUNT]
        if li:
            li.setProperty("active", value)

    def _browse_rewire_grid_left(self, idx: int):
        """The grid's Left target has to follow whichever sidebar list
        currently holds the active source -- Kodi's onleft is a static
        per-control target, and the sidebar is split into two list
        controls (see SIDEBAR_LIBRARY_ID), so a fixed XML target would be
        wrong half the time."""
        target_id = self.SIDEBAR_ID if idx < self.BROWSE_FIXED_SOURCE_COUNT else self.SIDEBAR_LIBRARY_ID
        self.getControl(self.GRID_ID).controlLeft(self.getControl(target_id))

    def _browse_fetch_library_count(self, client: MediaServerClient, lib: dict) -> str:
        params = {"library_id": lib.get("id"), "per_page": 1}
        if lib.get("media_type"):
            params["media_type"] = lib["media_type"]
        try:
            resp = client._get("/api/v1/media", params=params)
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse library count failed: {0}".format(exc))
            return ""
        if isinstance(resp, dict):
            total = resp.get("total")
            if isinstance(total, int):
                # Grouped the same way _library_count does. This is the path
                # that actually runs: /api/v1/libraries carries no count, so
                # every sidebar row lands here.
                return regional.number(total)
        return ""

    # The collection currently drilled into, or None while the Collections
    # grid itself is showing. The real app keeps this INSIDE Browse rather
    # than opening a separate screen, so it is a state of this section and
    # not a window of its own.
    COLLECTION_BACK_ID = 6260
    COLLECTION_GRID_ID = 6210

    def _browse_active_source(self) -> dict:
        return self._sources[self._active_source_idx]

    def _browse_filterbar_visible(self, src: dict) -> bool:
        """Sort/Filter/Quality/genre pills only make sense for a real
        title list -- hidden for Collections (its cards have no genre/
        quality/watch-status to filter by). Kept visible for Watchlist/
        History even though not every pill is fully wired to those
        endpoints yet (see _browse_load_grid()/_browse_load_history_grid());
        showing a not-yet-wired control beats hiding it."""
        return src["kind"] in ("watchlist", "history", "library")

    def _browse_start_facets(self):
        """Send the facets request, WITHOUT waiting for it. Returns a handle
        for _browse_finish_facets(), or None when there is nothing to wait for.

        The facets and the grid's own first page are independent requests to
        the same server, and used to be made one after the other -- the grid
        did not start until the facets came back, measured at 267-898ms on the
        CoreELEC box. Overlapping them takes that off every source switch.

        What CANNOT wait is the genre RESET: the grid's own query reads
        `_active_genre`, so leaving the previous source's genre in place until
        the response lands would filter the new library by it. That part is
        done here, synchronously; only the fetched names/letters are awaited.
        """
        client = self._get_client()
        src = self._browse_active_source()
        wanted = self._browse_filterbar_visible(src)
        self.setProperty("browse_filterbar", "1" if wanted else "")
        self._active_genre = self.ALL_GENRES
        self.genre_list[0].setProperty("genre_label", self._browse_genre_label())
        self.genre_list[0].setProperty("active", "")
        if not wanted or not client:
            self._browse_apply_facets([], {})
            return None

        pending: dict = {"names": [], "letters": {}}

        def run():
            try:
                if src["kind"] == "library":
                    facets = client.facets(media_type=src.get("media_type"), library_id=src.get("id")) or {}
                else:
                    facets = client.facets() or {}
                # facets()'s counts are real (unlike genres(), a flat name
                # list with no count) -- a genre with 0 matches in this
                # library/media_type scope just isn't returned at all, so
                # the Genre dialog never offers one that would show nothing.
                # The count comes back with the name and is worth keeping, not
                # just testing: it is what the Genre picker's right-hand
                # column shows, and it is the same number the real app puts
                # on its genre pills ("Action - 1988"). One request already
                # answers it, so showing it costs nothing.
                pending["names"] = [(g.get("value"), g.get("count"))
                                    for g in (facets.get("genres") or []) if g.get("count")]
                # Same response, second facet: the A-Z rail's cells. Read
                # here rather than in a call of its own because it is the
                # SAME scope (library + media type) and the endpoint has
                # already answered it -- a second round trip would only add
                # a way for the two to disagree. A server older than API 22
                # has no `letters` field at all: no field, no rail.
                pending["letters"] = {f.get("value"): (f.get("count") or 0)
                                      for f in (facets.get("letters") or [])
                                      if f.get("value") and f.get("count")}
                # Third and fourth facets from the same response: the sort
                # vocabulary this server accepts, and the sort it wants used
                # when nobody has chosen. `sorts` stays None when the field
                # is absent, which an older server is entitled to do -- see
                # _browse_offered_sorts on why None is not an empty list.
                srt = facets.get("sorts")
                pending["sorts"] = tuple(s for s in srt if s) if srt else None
                pending["default_sort"] = facets.get("default_sort")
                pending["default_order"] = facets.get("default_order")
            except http.ApiError as exc:
                kodigui.ERROR("main.py: browse facets failed: {0}".format(exc))

        # Nothing in run() touches Kodi -- it is one HTTP call writing into
        # `pending`. Every UI write happens in _browse_apply_facets, back on
        # the caller's thread.
        pending["thread"] = threading.Thread(target=run, name="tofa-browse-facets")
        pending["thread"].daemon = True
        pending["thread"].start()
        return pending

    def _browse_finish_facets(self, pending):
        """Wait for _browse_start_facets()'s request and apply it."""
        if pending is None:
            return
        # http.py's own 15s timeout is the real bound; this only stops a
        # wedged request from holding the switch open forever.
        pending["thread"].join(20)
        self._browse_apply_facets(pending["names"], pending["letters"],
                                  sorts=pending.get("sorts"),
                                  default_sort=pending.get("default_sort"),
                                  default_order=pending.get("default_order"))

    def _browse_apply_facets(self, names, letters, *, sorts=None,
                             default_sort=None, default_order=None):
        """`names` is [(genre, count), ...] -- see _browse_start_facets."""
        pairs = [(n, c) for n, c in names if n]
        self._genres = [self.ALL_GENRES] + [n for n, _c in pairs]
        # Parallel to _genres by NAME, not by index: _genres carries the
        # synthetic ALL_GENRES at 0 and the collection drill-down builds its
        # own list, so an index-parallel list would be one off in one place
        # and right in the other.
        self._genre_counts = {n: c for n, c in pairs}
        self._browse_letter_counts = letters
        # Only overwrite what the server actually said. The no-facets caller
        # below passes nothing, and a source with no facet request must not
        # wipe a vocabulary a previous one established.
        if sorts is not None:
            # Logged when it CHANGES, not every source switch: it is the one
            # signal that this server's vocabulary was actually read, and
            # without it a server whose list happens to match ours looks
            # exactly like one that answered nothing at all.
            if sorts != self._browse_server_sorts:
                log.info("browse: server sorts=%s default=%s/%s"
                         % (",".join(sorts), default_sort, default_order))
            self._browse_server_sorts = sorts
            # A sort this server does not offer cannot stay selected -- it
            # would silently do nothing on every query.
            offered = self._browse_offered_sorts()
            if self._browse_sort_idx not in offered:
                self._browse_sort_user_picked = False
        self._browse_apply_server_sort_default(default_sort, default_order)
        self._browse_fill_alpha_rail()

    def _browse_load_grid(self):
        """Load whichever source the sidebar has selected, then re-aim the
        nav bar's Down at whatever actually ended up on screen."""
        try:
            self._browse_load_grid_content()
        finally:
            self._browse_wire_nav_down()

    def _browse_wire_nav_down(self):
        """Down out of the top nav enters the GRID, not the left menu.

        The left menu is still one Left away from the grid, and landing on
        the content is what the section is for -- a viewer who wanted to
        change source would have gone there deliberately.

        Falls back to the left menu when the grid came back EMPTY (a genre
        with no matches, an empty Watchlist). Kodi will not focus an empty
        list, so pointing Down at one strands the viewer on the nav bar with
        no way into the section at all -- worse than landing on the menu.
        """
        collections = bool(self.getProperty("browse_collections"))
        grid = self.collection_list if collections else self.grid_list
        target_id = self.COLLECTION_GRID_ID if collections else self.GRID_ID
        # `not len(grid)` rather than `not grid`: a ManagedControlList is
        # falsy when EMPTY, which is exactly the case being tested, but the
        # None check has to stay separate to say so.
        if grid is None or not len(grid):
            target_id = self.SIDEBAR_ID
        self._section_down_targets["browse"] = target_id
        if self._current_target == "browse_window":
            try:
                self.getControl(self.NAV_LIST_ID).controlDown(
                    self.getControl(target_id))
            except RuntimeError:
                pass

    def _browse_load_grid_content(self):
        # A genre or sort change inside a collection re-renders THAT, rather
        # than dropping back to the index: both handlers end here, and
        # clearing the drill-down would eject the viewer on every pill.
        if self._browse_collection is not None:
            self._browse_render_collection_members()
            return
        self.setProperty("browse_heading", "")
        self.setProperty("browse_collections", "")
        self._browse_point_sidebar_at(self.GRID_ID)
        self._browse_grid_geometry(in_collection=False)
        # Undo the drill-down's own wiring: with the pill gone, Genre is
        # the end of the row again.
        try:
            genre = self.getControl(self.GENRE_ID)
            genre.controlRight(genre)
        except RuntimeError:
            pass
        client = self._get_client()
        self.grid_list.reset()
        # Disarm paging on EVERY refill, so only the branch that actually
        # paged re-arms it below. Without this the params survived into the
        # next source: with Watchlist showing, scrolling to its end appended
        # 200 MOVIES onto it, because the previous library's query was still
        # sitting in _browse_page_params. Caught live -- the item count grew
        # by exactly 200 on a list that has 208.
        self._browse_reset_paging()
        if not client:
            return
        src = self._browse_active_source()

        if src["kind"] == "history":
            self._browse_load_history_grid(client)
            return
        if src["kind"] == "collections":
            self._browse_load_collections_grid(client)
            return

        items: list[dict] = []
        try:
            if src["kind"] == "watchlist":
                # No sort/filter support on this endpoint (plain bare-array
                # response, see MediaServerClient.watchlist()) -- Sort/Filter
                # stay visible+clickable to match the real app, but only
                # take effect once the user switches to a real library.
                items = client.watchlist() or []
            else:
                _sort_label, sort_value, order = self.BROWSE_SORT_OPTIONS[self._browse_sort_idx]
                if order and self._browse_sort_reversed:
                    order = "asc" if order == "desc" else "desc"
                _watched_label, watched_value = self._browse_watched_options()[self._browse_watched_idx]
                _year_label, year_from, year_to = self.BROWSE_YEAR_OPTIONS[self._browse_year_idx]
                _quality_label, quality_value = self.BROWSE_QUALITY_OPTIONS[self._browse_quality_idx]
                params = {
                    "library_id": src.get("id"),
                    "sort": sort_value,
                    "order": order,
                    "per_page": self.BROWSE_PAGE_SIZE,
                }
                if src.get("media_type"):
                    params["media_type"] = src["media_type"]
                if self._active_genre and self._active_genre != self.ALL_GENRES:
                    params["genre"] = self._active_genre
                if watched_value:
                    params["watched"] = watched_value
                if year_from:
                    params["year_from"] = year_from
                if year_to:
                    params["year_to"] = year_to
                if quality_value:
                    params["quality"] = quality_value
                # The A-Z rail. The server buckets by first letter itself,
                # articles already stripped ("The BFG" answers letter=B),
                # and `#` IS its name for the non-alphabetic bucket, so the
                # rail's own labels go straight through untranslated.
                #
                # Only ever sent for a letter the rail offers. An
                # unrecognised value is IGNORED rather than rejected --
                # letter=0-9 and letter=Ä both came back with the full
                # 11,493 -- so a bad one would look exactly like "All"
                # instead of failing where it could be seen.
                if self._browse_letter:
                    params["letter"] = self._browse_letter
                if sort_value == "random":
                    # Stable pagination for a persistent shuffle -- same
                    # seed for the lifetime of this Shuffle selection, set
                    # in _browse_sort_clicked() when the user picks it.
                    if self._browse_shuffle_seed is None:
                        self._browse_shuffle_seed = random.randint(0, 2 ** 31 - 1)
                    params["seed"] = self._browse_shuffle_seed
                resp = client._get("/api/v1/media", params=params)
                items = (resp or {}).get("items", []) if isinstance(resp, dict) else (resp or [])
                # Remember exactly what produced this page, so page 2 asks the
                # same question. Rebuilding the params from current state would
                # silently change the query if a filter moved while a fetch was
                # in flight, and the two pages would then interleave.
                self._browse_page_params = dict(params)
                self._browse_total = ((resp or {}).get("total")
                                      if isinstance(resp, dict) else None)
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse media list failed: {0}".format(exc))
            items = []

        if not items:
            return
        # The first page arrives as DATA and becomes cards only where the
        # viewer is actually looking -- the same rule pages 2+ have followed
        # since eb5f153. Page 1 used to be the exception and built all 200 of
        # its cards on EVERY source switch: measured on the CoreELEC box at
        # 0.8-2.2s, and 22s when the switch landed while the box was still
        # busy with the previous one. Only ~15 cards are ever on screen.
        #
        # Chunked by BROWSE_PAGE_SIZE even for the sources that never page
        # (Watchlist), so _browse_fill_window's position->page arithmetic
        # finds their data too rather than leaving everything past the first
        # 200 permanently blank.
        for start in range(0, len(items), self.BROWSE_PAGE_SIZE):
            self._browse_page_data[start // self.BROWSE_PAGE_SIZE + 1] = \
                items[start:start + self.BROWSE_PAGE_SIZE]
        if self._browse_page_params:
            self._browse_pages_loaded = {1}
        # EVERY addItems for this grid happens HERE, while the selection is
        # still at 0 -- see _browse_blanks() for why that matters.
        # Blanks only. Building the first screenful as real cards up front
        # instead was tried and MEASURED WORSE on the box (TV Shows 1317ms vs
        # 386ms, Movies Deutsch 6780ms vs 3008ms): a detached
        # ManagedListItem has to construct its own xbmcgui.ListItem, whereas
        # filling one already in the container reuses the blank's. Fill it
        # after the insert, not before -- do not "optimise" this back.
        self.grid_list.addItems(
            self._browse_blanks(max(self._browse_total or 0, len(items))))
        self.grid_list.selectItem(0)
        # Paint the first screenful before returning, so the grid is never
        # handed to the viewer as a wall of blanks.
        self._browse_fill_window(client)

    def _browse_blanks(self, count: int) -> list:
        """`count` empty items, so the grid is its FULL length from the start.

        This is the whole fix for the grid jumping back to row 1 mid-scroll.
        Kodi's `control.addItems()` resets a focused container's position, and
        no amount of restoring the position afterwards is safe: onAction runs
        on the Python thread while Kodi's GUI thread keeps moving the
        selection, so between reading the position and putting it back the
        viewer has already moved somewhere else. Restoring it was tried, and
        it held on this desktop and still lost the race on the box -- fast
        enough to hide the bug is not the same as fixed.

        So: allocate all of it up front, while the viewer is still at position
        0 and a reset to 0 is a no-op, and from then on only ever fill items
        in PLACE (_browse_fill_page). An in-place fill cannot move the
        selection because it never touches the container's length.

        This is what plex-for-kodi does with the same problem on the same
        hardware (library.py: fillShows/_chunkCallback allocate totalSize
        default items and then mutate showPanelControl[pos]).

        The cost is that unfetched cards are visibly blank until their page
        lands, rather than the grid simply ending. That is the honest picture:
        the scrollbar and item count now describe the real library instead of
        whatever happened to be downloaded.

        NOT free, whatever an earlier note here claimed ("10,741 measured at
        17ms"): re-measured on the box 2026-08-08 it is 1.5-2.8s for a
        10,741-title library, because each one is a real xbmcgui.ListItem. That
        is why ManagedListItem no longer calls setArt for an item with no art
        -- the wasted C++ call was a per-blank cost paid 10,741 times.
        """
        return [kodigui.ManagedListItem() for _ in range(count)]

    def _browse_reset_paging(self):
        """Forget any paged query. Called whenever the grid is refilled; the
        library branch re-arms it, and every other source (Watchlist,
        History, Collections) is then correctly un-pageable."""
        self._browse_total = None
        self._browse_page_params = None
        self._browse_pages_loaded = set()
        self._browse_page_data = {}
        self._browse_filled = set()

    #: How close to the end of the loaded set the selection has to get before
    #: the next page is fetched. One full row ahead of the last card, so the
    #: fetch overlaps the scroll rather than starting when the viewer has
    #: already hit the bottom.
    BROWSE_PREFETCH_WITHIN = 12

    #: What the server actually returns per page -- it caps per_page at 200
    #: however much is asked for, so this is a server fact, not a preference.
    #: Page N holds indices (N-1)*200 .. N*200-1, which is what lets a
    #: position be turned straight into the page that owns it.
    BROWSE_PAGE_SIZE = 200

    def _browse_maybe_load_more(self):
        """Fill the page the selection is heading into, in place.

        The server pages cleanly (page=2 returns the next 200 with zero
        overlap, verified against the real library) and caps per_page at 200
        whatever is asked for, so paging is the only way past the first 200 of
        10,741 movies.

        The grid is already its full length (_browse_blanks), so this
        never appends -- it swaps blanks for real cards where they sit. Which
        page to fetch comes from the SELECTION, not from a running counter:
        a viewer holding Down on a slow box outruns the fetch and lands three
        pages further on, and asking for "the next one" would then fill a page
        nowhere near them and be asked again immediately.

        Guarded three ways: only for a real paged list (page params recorded),
        only for a page not already filled, and never while a fetch is already
        running -- a held-down Down key fires this on every repeat.

        It LOOPS rather than fetching once, because the selection keeps moving
        during the fetch: Kodi's GUI thread scrolls the grid while this runs on
        the Python thread. A viewer who lets go while a page is in flight would
        otherwise be left sitting on blanks with no keypress left to trigger
        the page they actually landed on -- the one trigger that mattered was
        dropped by the in-flight guard. Re-reading the position after each
        fetch is also what makes a fast scroll converge instead of filling a
        trail of pages behind the viewer.
        """
        if self.grid_list is None or not len(self.grid_list):
            return
        client = self._get_client()
        if not client:
            return
        # Cheap: only fills slots not already done, so once the window is
        # covered this is a no-op scan. This is what lets a page arrive as
        # data and become cards as the viewer walks into it.
        #
        # Runs for EVERY source, before the paging guards below: since page 1
        # is allocated as blanks too, a source that never pages (Watchlist)
        # depends on this for everything past the first window. Gating it on
        # _browse_page_params -- as this did while only pages 2+ were
        # windowed -- would leave those permanently blank.
        self._browse_fill_window(client)
        if self._browse_loading_more or not self._browse_page_params:
            return

        self._browse_loading_more = True
        try:
            # Bounded: a grid that somehow never settles must not spin here,
            # and four pages is already 800 cards past where the viewer was.
            for _ in range(4):
                # One row further on than the selection, so the fetch overlaps
                # the scroll instead of starting once they are on blanks.
                target = min(self.grid_list.getSelectedPosition() + self.BROWSE_PREFETCH_WITHIN,
                             len(self.grid_list) - 1)
                page = target // self.BROWSE_PAGE_SIZE + 1
                if page in self._browse_pages_loaded:
                    return
                params = dict(self._browse_page_params)
                params["page"] = page
                try:
                    resp = client._get("/api/v1/media", params=params)
                except http.ApiError as exc:
                    kodigui.ERROR("main.py: browse page {0} failed: {1}".format(page, exc))
                    return
                items = (resp or {}).get("items", []) if isinstance(resp, dict) else (resp or [])
                # Marked loaded even when empty: a server whose `total`
                # overstates would otherwise be re-queried on every keypress
                # over that page.
                self._browse_pages_loaded.add(page)
                self._browse_fill_page(client, page, items)
        finally:
            self._browse_loading_more = False

    def _browse_fill_page(self, client: MediaServerClient, page: int, items: list):
        """Turn the blanks already holding this page's slots into real cards.

        Mutates the ListItems Kodi is already showing, so the container's
        length never changes and the selection cannot move -- which is the
        entire point (see _browse_blanks)."""
        # Keep the page's raw data; _browse_fill_window() turns it into cards
        # a windowful at a time, as the viewer reaches them.
        self._browse_page_data[page] = items
        self._browse_fill_window(client)

    #: How many slots around the selection are turned into real cards. Two
    #: screens' worth: enough that a normal scroll never outruns it, small
    #: enough that the work is a fifth of a second rather than seconds.
    BROWSE_FILL_WINDOW = 40

    def _browse_fill_window(self, client: MediaServerClient):
        """Fill the slots near the selection from whatever pages we hold.

        Filling one card costs ~10 writes into Kodi's C++ side. A page is
        200 of them, and on the CoreELEC box that measured 0.8s at best,
        4.2s cold, and 11s while the viewer kept scrolling -- against a
        220-290ms fetch for the same page. The fill, not the network, was
        what made a page boundary feel slow, and it ran on the action thread
        so it stalled input while it went.

        Only ~15 cards are ever on screen, so filling 200 was doing an order
        of magnitude more work than the viewer could see. This fills a window
        around the selection and leaves the rest as data until they are
        approached, which is the same rule Kodi already applies to its own
        texture cache: cache where you land, not everything you passed.
        """
        if self.grid_list is None or not len(self.grid_list):
            return
        here = self.grid_list.getSelectedPosition()
        lo = max(0, here - self.BROWSE_FILL_WINDOW // 2)
        hi = min(len(self.grid_list), here + self.BROWSE_FILL_WINDOW + 1)
        pending = []
        for pos in range(lo, hi):
            if pos in self._browse_filled:
                continue
            page = pos // self.BROWSE_PAGE_SIZE + 1
            data = self._browse_page_data.get(page)
            if data is None:
                continue
            offset = pos - (page - 1) * self.BROWSE_PAGE_SIZE
            if offset >= len(data):
                continue
            pending.append((pos, data[offset]))

        # Stage this window's posters before any card is built, so each one
        # gets a stable local path. Left to fall through card by card they
        # would each be a miss, and a miss hands Kodi the tokenised URL --
        # exactly what the staging area exists to keep out of its cache.
        artcache.prefetch(client.stage_pairs([it for _p, it in pending],
                                             self._CARD_ART_FIELD))
        for pos, item in pending:
            self._browse_apply_grid_item(client, self.grid_list[pos], item)
            self._browse_filled.add(pos)

    def _browse_build_grid_item(self, client: MediaServerClient, item: dict) -> kodigui.ManagedListItem:
        return self._browse_apply_grid_item(
            client, kodigui.ManagedListItem(), item)

    def _browse_apply_grid_item(self, client: MediaServerClient, mli, item: dict):
        """Everything a Browse grid card shows, applied to `mli`.

        Split from the constructor so a page fetched later can turn the blank
        already sitting in that slot into a real card without rebuilding it
        (see _browse_blanks). One definition either way, so a card
        cannot look different depending on whether it arrived with page 1.
        """
        title = item.get("title") or ""
        poster = client.resolve_image_url(item.get("poster_path")) or ""
        cards.apply_poster(mli, item, poster, label=title,
                           prefs=self._ensure_preferences())

        mli.setProperty("caption_meta", _item_year(item))

        media_id = item.get("id") or item.get("media_id")
        mli.setProperty("media_id", str(media_id) if media_id else "")
        return mli

    def _browse_load_history_grid(self, client: MediaServerClient):
        try:
            resp = client.watch_history(limit=100) or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse watch_history failed: {0}".format(exc))
            resp = {}
        history = _history_latest_per_title(resp.get("items") or [])
        artcache.prefetch(client.stage_pairs(history, "poster_path"))
        managed = [self._browse_build_history_item(client, it) for it in history]
        if managed:
            self.grid_list.addItems(managed)
            self.grid_list.selectItem(0)

    def _browse_build_history_item(self, client: MediaServerClient, item: dict) -> kodigui.ManagedListItem:
        title = item.get("title") or ""
        if item.get("episode_title"):
            title = u"{0} - {1}".format(title, item["episode_title"])
        poster = client.resolve_image_url(item.get("poster_path")) or ""
        mli = kodigui.ManagedListItem(label=title, thumbnailImage=poster, data_source=item)
        mli.setArt({"poster": poster})

        self._apply_card_bar(mli, item)

        # A history entry has no year/genre -- caption is when it was
        # watched instead (e.g. "Jul 28"), the one piece of context a
        # session log actually adds over the plain title.
        mli.setProperty("caption_meta", _format_history_date(item.get("started_at") or ""))

        media_id = item.get("media_id")
        mli.setProperty("media_id", str(media_id) if media_id else "")
        return mli

    def _browse_load_collections_grid(self, client: MediaServerClient):
        """7.5's landscape index. Renders into its OWN panel, not the poster
        grid, and flips browse_collections so the two swap places."""
        try:
            resp = client.collections() or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse collections failed: {0}".format(exc))
            resp = {}
        collections = resp.get("collections") or []
        # User-made collections (server 0.9.33) live on their own route and
        # come FIRST: someone on this server made each of them on purpose,
        # there will only ever be a handful, and behind five hundred
        # franchise tiles nobody would learn they exist. Marked so the card
        # builder and the drill-in know which field family and which fetch
        # applies. Read-only here by decision (2026-08-24): the server's
        # own apps have create/edit; we show.
        try:
            custom = (client.custom_collections() or {}).get("collections") or []
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse custom collections failed: {0}".format(exc))
            custom = []
        for it in custom:
            it["_custom"] = True
        # Curated collections carry absolute poster_url/backdrop_url on our
        # own server rather than the usual relative *_path, and both are
        # drawn on the card -- stage_pair knows the difference, this only
        # has to name the right fields. Custom ones carry the ordinary
        # relative pair, so they stage as a second small batch.
        started = time.monotonic()
        # ALLOCATE, DON'T BUILD. This screen used to stage every tile's art
        # and build every card before showing anything, on the assumption
        # (written here) of "~15 tiles". The real library answers **529**,
        # so it staged ~1058 images across two blocking prefetches and then
        # made 529 cards at ~10 C++ writes each, on the action thread,
        # before the first tile appeared: measured on the cinema box at
        # 1.62s warm and 10.6-33.3s cold, EVERY time the section was opened.
        #
        # Same fix the poster grid already carries (_browse_blanks +
        # _browse_fill_window): allocate the full length up front while the
        # selection is still at 0, then fill a window around it and stage
        # only that window's art. ~15 tiles are ever on screen, which is
        # what the old comment assumed the whole index was.
        self._collection_items = custom + collections
        self._collection_filled = set()
        self.setProperty("browse_collections", "1")
        # The sidebar's <onright> is baked at the poster grid, which is
        # hidden in this state, so right out of the sidebar went nowhere.
        self._browse_point_sidebar_at(self.COLLECTION_GRID_ID)
        self.collection_list.reset()
        if self._collection_items:
            self.collection_list.addItems(
                self._browse_blanks(len(self._collection_items)))
            self.collection_list.selectItem(0)
            self._browse_fill_collection_window(client)
        log.info("browse: %d collection(s) (%d custom) in %.2fs"
                 % (len(collections) + len(custom), len(custom),
                    time.monotonic() - started))

    def _browse_fill_collection_window(self, client: MediaServerClient):
        """Turn the blanks near the selection into real collection tiles.

        The poster grid's _browse_fill_window in miniature, and the same
        reasoning: only the slots a viewer can see are worth ~10 C++ writes
        each. The one difference is the art, which comes in two field
        families -- curated collections carry absolute *_url on our own
        server, user-made ones the ordinary relative *_path -- so the window
        stages as two small batches rather than one.

        include_cdn stays set for the curated batch: some of that art is
        served by the cloud, and this is a screen the viewer has navigated
        to and is waiting on. It is affordable now because the batch is a
        window rather than all 529.
        """
        if self.collection_list is None or not len(self.collection_list):
            return
        here = self.collection_list.getSelectedPosition()
        lo = max(0, here - self.BROWSE_FILL_WINDOW // 2)
        hi = min(len(self.collection_list), here + self.BROWSE_FILL_WINDOW + 1)
        pending = [(pos, self._collection_items[pos])
                   for pos in range(lo, hi)
                   if pos not in self._collection_filled
                   and pos < len(self._collection_items)]
        if not pending:
            return

        items = [it for _pos, it in pending]
        curated = [it for it in items if not it.get("_custom")]
        made = [it for it in items if it.get("_custom")]
        if curated:
            artcache.prefetch(client.stage_pairs(curated, "poster_url",
                                                 "backdrop_url", include_cdn=True))
        if made:
            artcache.prefetch(client.stage_pairs(made, "poster_path",
                                                 "backdrop_path"))
        for pos, item in pending:
            self._browse_apply_collection_item(
                client, self.collection_list[pos], item)
            self._collection_filled.add(pos)

    def _browse_build_collection_item(self, client: MediaServerClient, item: dict) -> kodigui.ManagedListItem:
        return self._browse_apply_collection_item(
            client, kodigui.ManagedListItem(), item)

    def _browse_apply_collection_item(self, client: MediaServerClient, mli, item: dict):
        """Everything a collection tile shows, applied to `mli`.

        Split from the constructor for the same reason the poster grid's
        was: a blank already sitting in the grid becomes a real tile in
        place, without changing the container's length and so without
        moving the selection."""
        title = item.get("name") or ""
        # 7.5's artwork ladder wants BOTH: the backdrop is the tile's normal
        # art, and the poster is the fallback that must be fitted rather
        # than cropped. They go in different slots so the layout can tell
        # them apart and pick its own treatment for each.
        if item.get("_custom"):
            # The relative *_path family, like media. A collection nobody
            # has given a poster still answers `poster_paths` -- up to four
            # member posters -- and the first of those beats an empty slot;
            # a composite tile would need layout work this read-only pass
            # doesn't buy.
            poster_path = item.get("poster_path")
            if not poster_path:
                paths = item.get("poster_paths") or []
                poster_path = paths[0] if paths else None
            backdrop = client.resolve_image_url(item.get("backdrop_path")) or ""
            poster = client.resolve_image_url(poster_path) or ""
        else:
            backdrop = client.resolve_image_url(item.get("backdrop_url")) or ""
            poster = client.resolve_image_url(item.get("poster_url")) or ""
        # Same idiom as cards.apply_poster: assign thumbnailImage rather
        # than calling the setter, so a blank standing in the grid becomes
        # the tile in place.
        mli.dataSource = item
        mli.setLabel(title)
        mli.thumbnailImage = backdrop
        mli.setArt({"thumb": backdrop, "poster": poster})
        mli.setProperty("poster", poster)

        count = item.get("item_count")
        if isinstance(count, int):
            mli.setProperty("caption_meta", "{0} title{1}".format(count, "" if count == 1 else "s"))

        # Collection tiles live in their own list (COLLECTION_GRID_ID), so a
        # click routes through onClick's COLLECTION_GRID_ID branch to
        # _browse_open_collection (the drill-in) -- NOT the poster grid's
        # _browse_grid_clicked. The tile carries the collection's own id in its
        # data_source, not a media_id.
        return mli

    def _browse_open_collection(self, item: kodigui.ManagedListItem):
        """Drill into a collection, staying inside Browse."""
        # Where to put focus back when Back returns to the index. Captured
        # before anything is fetched, because the index list is rebuilt on
        # the way back and its selection would otherwise reset to the first
        # tile -- leaving the viewer to hunt for the collection they had
        # just been in.
        try:
            self._collection_return_pos = self.collection_list.getSelectedPosition()
        except (RuntimeError, AttributeError):
            self._collection_return_pos = 0
        data = item.dataSource or {}
        collection_id = data.get("id")
        if not collection_id:
            return
        client = self._get_client()
        if not client:
            return
        try:
            if data.get("_custom"):
                resp = client.custom_collection(str(collection_id)) or {}
                # Members are MediaSummary -- library shapes carrying
                # `release_date`, not the `year` the shared card, caption
                # and sort all read. Derive it once here rather than
                # branching three consumers.
                for m in resp.get("items") or []:
                    if m.get("year") is None:
                        date = str(m.get("release_date") or "")
                        if date[:4].isdigit():
                            m["year"] = int(date[:4])
            else:
                resp = client.collection(str(collection_id)) or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: collection {0} failed: {1}".format(collection_id, exc))
            return
        self._browse_collection = resp
        self.setProperty("browse_heading", resp.get("name") or item.getLabel() or "")
        # Members are titles again, so the poster grid comes back and the
        # toolbar returns with it: both apps show Sort/Quality/Filter and
        # the collection's own genres here (verified on Android TV, whose
        # pills carry no counts inside a collection).
        self.setProperty("browse_collections", "")
        # Members are AnnotatedDiscoveryItem, the same shape Discover's
        # shelves carry, so its card builder renders owned and requestable
        # alike without a second one.
        # Genres come from the members themselves, so the pills offer only
        # what this collection actually contains. Android shows them without
        # counts here, unlike the library grid's "Action - 1979".
        # Counted here rather than fetched: the members are already in hand,
        # so the same tally the facets endpoint would do is a loop. A title
        # carrying two genres counts under both, which is what the facets
        # endpoint reports too.
        counts: dict[str, int] = {}
        for m in (resp.get("items") or []):
            for g in (m.get("genres") or []):
                if g:
                    counts[g] = counts.get(g, 0) + 1
        genres = sorted(counts)
        self._genre_counts = counts
        self._genres = [self.ALL_GENRES] + genres
        self._active_genre = self.ALL_GENRES
        self.genre_list[0].setProperty("genre_label", self._browse_genre_label())
        self.genre_list[0].setProperty("active", "")
        self.setProperty("browse_filterbar", "1")
        self._browse_point_sidebar_at(self.GRID_ID)
        self._browse_grid_geometry(in_collection=True)
        self._browse_render_collection_members()
        # The drill-down inserts a back pill the static XML knows nothing
        # about, so its links are wired here.
        #
        # The pill IS the fourth toolbar slot, sitting beside Sort/Filter/
        # Quality/Genre rather than under them -- so it joins the row
        # horizontally (Genre's Right), and the grid's Up goes to the
        # toolbar exactly as it does outside a collection.
        try:
            pill = self.getControl(self.COLLECTION_BACK_ID)
            self.getControl(self.GENRE_ID).controlRight(pill)
            pill.controlDown(self.getControl(self.GRID_ID))
            self.getControl(self.GRID_ID).controlUp(self.getControl(self.SORT_ID))
        except RuntimeError:
            pass
        if resp.get("items"):
            self.setFocusId(self.GRID_ID)

    # The poster grid sits at 299 normally. Inside a collection the heading
    # and the back pill need the space above it, so it drops; our toolbar is
    # four full-width buttons and cannot take the pill inline the way both
    # reference apps do.
    # Vertical rhythm inside a collection, measured off the real app's own
    # collection screen: heading ink at 197, toolbar 34 below it, grid 59
    # below that at 381. Ours matches, with the back pill beside the title
    # rather than inline with Sort, which our four full-width buttons leave
    # no room for.
    _GRID_Y = 299
    _GRID_H = 781
    _GRID_Y_COLLECTION = 381
    _GRID_H_COLLECTION = 699
    _TOOLBAR_Y = 190
    _TOOLBAR_Y_COLLECTION = 262

    def _browse_grid_geometry(self, *, in_collection: bool):
        # The toolbar moves too: with a heading above it, its library
        # position would sit on top of the title.
        toolbar_y = (self._TOOLBAR_Y_COLLECTION if in_collection
                     else self._TOOLBAR_Y)
        for toolbar_id in self.TOOLBAR_IDS:
            try:
                control = self.getControl(toolbar_id)
                control.setPosition(control.getX(), toolbar_y)
            except (RuntimeError, AttributeError):
                pass
        try:
            grid = self.getControl(self.GRID_ID)
        except RuntimeError:
            return
        grid.setPosition(
            T.BROWSE_GRID_X,
            self._GRID_Y_COLLECTION if in_collection else self._GRID_Y)
        grid.setHeight(
            self._GRID_H_COLLECTION if in_collection else self._GRID_H)

    def _browse_point_sidebar_at(self, target_id: int):
        """Aim both sidebar lists' right at whichever grid is on screen."""
        try:
            target = self.getControl(target_id)
        except RuntimeError:
            return
        for list_id in (self.SIDEBAR_ID, self.SIDEBAR_LIBRARY_ID):
            try:
                self.getControl(list_id).controlRight(target)
            except RuntimeError:
                pass

    def _browse_render_collection_members(self):
        """Apply the genre pill and the sort to the members, client-side.

        The endpoint hands back every member in one payload with no sort or
        filter parameters, so both are done here. Only the axes the data
        actually carries are wired: AnnotatedDiscoveryItem has `genres` and
        `year` but no quality or watch state, so Quality/Filter stay visible
        and inert exactly as they already are on Watchlist and History --
        the same call this section made there, that showing a not-yet-wired
        control beats hiding it."""
        client = self._get_client()
        if not client or self._browse_collection is None:
            return
        items = list(self._browse_collection.get("items") or [])
        if self._active_genre and self._active_genre != self.ALL_GENRES:
            items = [i for i in items
                     if self._active_genre in (i.get("genres") or [])]
        label, value, order = self.BROWSE_SORT_OPTIONS[self._browse_sort_idx]
        reverse = (order == "desc") != bool(self._browse_sort_reversed)
        if value == "title":
            items.sort(key=lambda i: (i.get("title") or "").lower(), reverse=reverse)
        elif value in ("release_date", "added_at"):
            # `year` is the only date a member carries; Date Added has no
            # equivalent at all here, so it falls back to it rather than
            # silently doing nothing.
            items.sort(key=lambda i: i.get("year") or 0, reverse=reverse)
        elif value == "rating":
            items.sort(key=lambda i: i.get("vote_average") or 0, reverse=reverse)
        elif value == "random":
            import random
            random.shuffle(items)
        self.grid_list.reset()
        artcache.prefetch(client.stage_pairs(items, "poster_path"))
        self.grid_list.addItems([self._discover_build_card(client, m) for m in items])

    def _browse_close_collection(self) -> bool:
        """Back out to the Collections grid. True when there was one open."""
        if self._browse_collection is None:
            return False
        self._browse_collection = None
        self.setProperty("browse_heading", "")
        self._browse_load_grid()
        # Focus goes to the COLLECTIONS grid, not the poster one -- that is
        # what is on screen now -- and onto the tile we came from.
        try:
            self.setFocusId(self.COLLECTION_GRID_ID)
            if self._collection_return_pos:
                self.collection_list.setSelectedItemByPos(self._collection_return_pos)
                # The rebuilt index fills a window around position 0, and
                # this jump can land well outside it -- on a blank, with no
                # keypress coming to fill it. Fill where we actually landed.
                client = self._get_client()
                if client:
                    self._browse_fill_collection_window(client)
        except (RuntimeError, AttributeError):
            pass
        return True

    def _browse_sidebar_idx_from(self, control_id: int) -> int | None:
        """Reads the currently-selected position out of whichever sidebar
        list `control_id` refers to and maps it to a self._sources index
        (None for the Surprise Me action row)."""
        if control_id == self.SIDEBAR_ID:
            return self._browse_fixed_pos_to_source_idx(self.sidebar_list.getSelectedPosition())
        return self._browse_library_pos_to_source_idx(self.sidebar_library_list.getSelectedPosition())

    def _browse_park_fixed_cursor(self, pos: int):
        """Move the FIXED sidebar list's cursor while it is not focused.

        Browse's sidebar reads as one list and is two controls (see
        SIDEBAR_LIBRARY_ID). Crossing between them is where that shows: Kodi
        moves focus to the other LIST, which lands on whatever cursor that
        list was left with -- so Up from "Movies" jumped over Collections and
        Surprise Me to "Watchlist" at the top. Reported 2026-08-11.

        Done from onFocus, and PRE-emptively, for a measured reason: Kodi's
        focus engine runs BEFORE onAction, so by the time an Up press reaches
        us the jump has already happened and correcting it there would move
        the highlight a second time, visibly, on a box that paints slowly.
        Parking the cursor while the list is off-focus is invisible: the
        crossing then lands where the viewer already expects.

        Same reason detail.py cannot undo a panel wrap in onAction either --
        see reference_kodi_layout_traps.
        """
        fixed = self.sidebar_list
        # `is None`, never truthiness: an empty ManagedControlList is falsy
        # (feedback_managedcontrollist_truthiness).
        if fixed is None or not len(fixed):
            return
        try:
            fixed.setSelectedItemByPos(max(0, min(pos, len(fixed) - 1)))
        except (RuntimeError, AttributeError):
            pass

    def _browse_sidebar_clicked(self, control_id: int):
        idx = self._browse_sidebar_idx_from(control_id)
        if idx is None:
            self._browse_surprise_me_clicked()
            return
        self._browse_switch_source(idx)

    def _browse_switch_source(self, idx: int):
        """SELECT only. This used to fire on focus too, tvOS-style, the way
        the nav bar's Left/Right still does -- moving onto a source loaded
        it. Adrian had it changed (2026-08-06) because of what it costs on
        the 4K CoreELEC box: the settle timer stops a fast flurry of Up/Down
        from loading every row, but it cannot help someone who moves down
        two rows and pauses, and every such pause bought a genres+grid fetch
        on the UI thread for a library they were only passing through.
        Deliberate divergence from the app, made for a device it does not
        have to run on -- do not "restore" it as a regression."""
        # A drill-down belongs to the source it was opened from.
        self._browse_collection = None
        if idx < 0 or idx >= len(self._sources) or idx == self._active_source_idx:
            return
        # Touch only the (at most) two rows that actually change state --
        # clear the old active row, set the new one -- rather than
        # relisting both lists on every switch. Kodi's render thread polls
        # ListItem state independently of this Python thread; a full
        # relist left a window where a fast Up/Down flurry could render a
        # stray "active" highlight in the wrong list before the next
        # re-render caught up.
        self._browse_set_source_active(self._active_source_idx, False)
        self._browse_set_source_active(idx, True)
        self._active_source_idx = idx
        self._browse_rewire_grid_left(idx)
        # Filter/Quality are per-source in the real app -- reset both to
        # their defaults on every source switch rather than carrying a
        # selection over into a library it wasn't chosen for. Sort is
        # deliberately left alone.
        self._browse_watched_idx = 0
        self._browse_year_idx = 0
        self._browse_quality_idx = 0
        self._browse_reset_letter()
        self.filter_list[0].setProperty("active", "")
        self.filter_list[0].setProperty("filter_label", self._browse_filter_label())
        # Everything above is local state and repaints instantly, so the
        # highlight lands on the pressed row at once. These two are HTTP.
        # They stay on the settle timer even though a click cannot burst
        # the way focus could, because that timer is also what keeps them
        # OFF the action thread -- calling them straight from onClick would
        # freeze the window for the length of the fetch, which is the whole
        # complaint. Mashing Select down the sidebar still loads only the
        # last row, for free.
        self._settle_delay_ms()
        self._settle.schedule(self._browse_load_source_content)

    # ---------------------------------------------------------- A-Z rail --

    def _browse_alpha_wanted(self) -> bool:
        """Whether the rail belongs on screen for the active source.

        Three gates besides having any cells to draw:

          * the server has to advertise `media.letter_index`. Without it
            `letter=` is an IGNORED query param, not a rejected one, so
            every pill would come back with the unfiltered library and look
            exactly like All -- a rail of 28 lies.
          * the source has to be a real LIBRARY. Watchlist and History are
            bounded, deliberately-ordered sets where an alphabet is noise,
            the collections index is not a title list at all, and a
            collection's members are a set the author chose.
          * the library has to be big enough to be worth one. Below
            ALPHA_MIN_TITLES the whole thing is a short scroll, and 28 pills
            beside it read as a second navigation column for nothing.
        """
        if "media.letter_index" not in self._server_capabilities:
            return False
        if self._browse_collection is not None:
            return False
        if self._browse_active_source().get("kind") != "library":
            return False
        return sum(self._browse_letter_counts.values()) >= T.ALPHA_MIN_TITLES

    def _browse_fill_alpha_rail(self):
        """Rebuild the rail for the active source, or hide it.

        Per-source, not once: the counts are library-scoped, so a different
        library is a different alphabet. A letter with no titles in THIS
        library is not offered at all -- the server says which buckets are
        non-empty, and a cell that lands on an empty grid is the one failure
        an index cannot afford.

        T.ALPHA_KEYS still fixes the ORDER (All, A..Z, then "#") rather than
        the facet response's, so the rail reads the same whatever order the
        server happens to answer in.

        Also re-aims the GRID's Right. Kodi's onright is baked into the XML
        as one static target and cannot vary by source, so on a library with
        no rail it would point Right at a hidden control."""
        if self.alpha_list is None:
            return
        wanted = self._browse_alpha_wanted()
        self.setProperty("browse_alpha", "1" if wanted else "")
        if wanted:
            try:
                self.getControl(self.GRID_ID).controlRight(
                    self.getControl(self.ALPHA_RAIL_ID))
            except RuntimeError:
                pass
        self.alpha_list.reset()
        if not wanted:
            self._browse_letter = ""
            return
        # A letter that survived into a library which has no titles under it
        # would be an active pill with no cell, and a grid filtered by
        # something the viewer cannot see or clear.
        if self._browse_letter and not self._browse_letter_counts.get(self._browse_letter):
            self._browse_letter = ""
        total = sum(self._browse_letter_counts.values())
        items = []
        for key in T.ALPHA_KEYS:
            count = total if key == T.ALPHA_KEYS[0] else self._browse_letter_counts.get(key)
            if not count:
                continue
            mli = kodigui.ManagedListItem(
                label=self._browse_alpha_speech(key, count),
                data_source=self._alpha_value(key))
            # The DRAWN glyph, separate from the label, because the label is
            # now what a screen reader says. See _browse_alpha_speech.
            mli.setProperty("glyph", key)
            items.append(mli)
        self.alpha_list.addItems(items)
        self._browse_mark_alpha_active()

    @staticmethod
    def _browse_alpha_speech(key: str, count: int) -> str:
        """What a screen reader says for a pill. The count is SPOKEN, never
        drawn: a number beside a 64px glyph is unreadable at ten feet, but
        "F, 15 titles" is exactly what a listener needs to judge the jump.

        Kodi reads ListItem.Label, so the label carries this and the pill
        draws ListItem.Property(glyph) instead.

        "#" is spelled OTHER rather than read as "hash", which is the
        server's bucket name, not a word for the non-alphabetic titles."""
        titles = "{0} title{1}".format(count, "" if count == 1 else "s")
        if key == T.ALPHA_KEYS[0]:
            return "All, {0}".format(titles)
        if key == "#":
            return "Other, {0}".format(titles)
        return "{0}, {1}".format(key, titles)

    @staticmethod
    def _alpha_value(key: str) -> str:
        """The rail label as the server wants it. "All" means "no filter",
        which is the absence of the param; every other label -- including
        "#" -- is already the server's own bucket name."""
        return "" if key == T.ALPHA_KEYS[0] else key

    def _browse_mark_alpha_active(self):
        if self.alpha_list is None:
            return
        for item in self.alpha_list:
            if item is None:
                continue
            item.setProperty(
                "active", "1" if item.dataSource == self._browse_letter else "")

    def _browse_alpha_clicked(self):
        """Select only, like the sidebar: a letter costs a round trip, and
        scrolling 28 of them on the way to Z should not cost 28."""
        item = self.alpha_list.getSelectedItem() if self.alpha_list else None
        if item is None or item.dataSource == self._browse_letter:
            return
        self._browse_letter = item.dataSource
        self._browse_mark_alpha_active()
        self._settle_delay_ms()
        self._settle.schedule(self._browse_load_grid)

    def _browse_reset_letter(self):
        """Back to All. The rail is per-source in the same way Filter and
        Quality are: a letter chosen in Movies means nothing in TV Shows,
        and silently carrying it over would look like an empty library."""
        self._browse_letter = ""
        self._browse_mark_alpha_active()

    def _browse_load_source_content(self):
        # Facets in flight while the grid fetches and paints, joined after.
        pending = self._browse_start_facets()
        self._browse_load_grid()
        self._browse_finish_facets(pending)

    def _browse_surprise_me_clicked(self):
        """Instant action, not a navigable source -- picks one random title
        from the whole library (no media_type/library scoping) and opens
        its Detail directly."""
        client = self._get_client()
        if not client:
            return
        try:
            resp = client._get("/api/v1/media", params={
                "sort": "random", "seed": random.randint(0, 2 ** 31 - 1), "per_page": 1,
            })
        except http.ApiError as exc:
            kodigui.ERROR("main.py: browse surprise me failed: {0}".format(exc))
            return
        items = (resp or {}).get("items") or []
        if not items:
            return
        media_id = items[0].get("id") or items[0].get("media_id")
        if not media_id:
            return
        self.open_detail(media_id=media_id)

    def _browse_sort_clicked(self):
        from .picker import PickerDialog
        # Only what this server honours, so the picker cannot offer a sort
        # that would quietly do nothing. `offered` maps ROW POSITION back to
        # the BROWSE_SORT_OPTIONS index -- picked_idx is a position in the
        # rows we passed, and treating it as an index into the full table is
        # exactly how a filtered list picks the wrong sort.
        offered = self._browse_offered_sorts()
        rows = []
        for i in offered:
            label, _value, order = self.BROWSE_SORT_OPTIONS[i]
            active = i == self._browse_sort_idx
            if active and order and self._browse_sort_reversed:
                order = "asc" if order == "desc" else "desc"
            rows.append((label, active, order))
        current_pos = (offered.index(self._browse_sort_idx)
                       if self._browse_sort_idx in offered else 0)
        dialog = PickerDialog.open(
            heading="Sort",
            hint="Select the current sort again to reverse it.",
            rows=rows,
            selected_idx=current_pos,
        )
        if not dialog or dialog.canceled:
            return
        if dialog.reselected:
            # Shuffle has no meaningful direction -- nothing to flip.
            if self.BROWSE_SORT_OPTIONS[self._browse_sort_idx][2] is None:
                return
            self._browse_sort_reversed = not self._browse_sort_reversed
            self._browse_sort_user_picked = True
            # The label is unchanged here -- same sort, other way round -- so
            # the arrow is the ONLY thing that can report a reverse toggle.
            self.sort_list[0].setProperty("sort_glyph", self._browse_sort_glyph())
        elif dialog.picked_idx is not None:
            # Back through `offered`: picked_idx is a position in the rows
            # shown, not an index into BROWSE_SORT_OPTIONS.
            if dialog.picked_idx < 0 or dialog.picked_idx >= len(offered):
                return
            choice = offered[dialog.picked_idx]
            self._browse_sort_idx = choice
            self._browse_sort_reversed = False
            # From here the server's default_sort must never move it again.
            self._browse_sort_user_picked = True
            # Fresh seed only on a transition INTO "random" -- reselecting
            # Shuffle while already on it takes the `reselected` branch
            # above instead. _browse_load_grid() reuses this seed for
            # stable pagination for as long as Shuffle stays selected.
            if self.BROWSE_SORT_OPTIONS[choice][1] == "random":
                self._browse_shuffle_seed = None
            # ListItem properties, not Window ones -- see onFirstInit's
            # comment on the Sort item's construction. One writer, shared
            # with the server-default path, so the two cannot drift.
            self._browse_sync_sort_pill()
        else:
            return
        self._browse_load_grid()

    def _browse_filter_clicked(self):
        """Watch Status, Year and Quality behind ONE collapsed panel.

        Quality used to be a fourth toolbar button. It is an axis of the
        same question the Filter dialog already asked, and folding it in
        frees the slot the collections back pill now sits in -- which was
        the point: the real app puts every control on one row, and ours had
        run out of room.

        Uses 7.7's collapsible panel rather than the flat picker Sort still
        uses. Flat, three axes would be a 15-row scroll whose eyebrow
        scrolls off while you are still inside its section; collapsed, it
        opens as three rows that each state their current value, which is
        what the viewer came to check most of the time."""
        from . import playoptions
        watched_options = self._browse_watched_options()
        # ORDER: most-used first, longest list last -- and here those agree.
        #
        # Watch Status leads because it is the only axis about YOU rather than
        # about the film, and because the TV apps put it first (Android
        # 0.1.11's dialog is Watch Status then Year, and holds nothing else).
        # Worth noting the desktop/web app orders the same axes the other way
        # up -- Genre, Year, Rating, Format, Status -- i.e. attributes first,
        # personal state last. The TV apps deliberately invert that, and we
        # are a TV client.
        #
        # Format second: 7 short options, and on a 4K/DV library it is the
        # axis people actually reach for. Year LAST because it is 12 decades,
        # by far the longest list -- last is the one place its length costs
        # nothing, since everything above it stays reachable without
        # scrolling. (Desktop puts Year before Format; it can afford to, with
        # five dropdowns side by side instead of one stacked panel.)
        sections = [
            {"key": "watched", "title": "Watch Status",
             "options": [{"label": label, "detail": ""}
                         for label, _value in watched_options],
             "selected": self._browse_watched_idx},
            # "Format", not "Quality" -- deliberately NOT what the real app
            # calls it (Android 0.1.11 still says Quality here). On this
            # client the word is already taken: the player's own stream
            # picker is Quality (player.py _open_panel), and that one means
            # transcode ladder -- how hard the server is working. This one
            # means what the FILE is: 4K, Dolby Vision, Atmos. Two unrelated
            # questions under one word, two presses apart, is the confusion
            # this rename removes. The API field stays `quality`, so the
            # constants below keep the server's name.
            {"key": "quality", "title": "Format",
             "options": [{"label": label, "detail": ""}
                         for label, _value in self.BROWSE_QUALITY_OPTIONS],
             "selected": self._browse_quality_idx},
            {"key": "year", "title": "Year",
             "options": [{"label": label, "detail": ""}
                         for label, _f, _to in self.BROWSE_YEAR_OPTIONS],
             "selected": self._browse_year_idx},
        ]
        picked = playoptions.show_sections(title="Filter", sections=sections)
        if picked is None:
            return
        # Positional, in SECTION order -- so this unpacking moves whenever the
        # list above is reordered. It is quality-then-year now, not
        # year-then-quality.
        watched_choice, quality_choice, year_choice = picked
        if (watched_choice == self._browse_watched_idx
                and year_choice == self._browse_year_idx
                and quality_choice == self._browse_quality_idx):
            return
        self._browse_watched_idx = watched_choice
        self._browse_year_idx = year_choice
        self._browse_quality_idx = quality_choice
        # "active" (accent-filled pill, like Sort) when any axis is off its
        # default -- ListItem property, same reasoning as sort_label: a
        # Window property doesn't reliably re-render inside a static list
        # item.
        is_active = bool(watched_choice or year_choice or quality_choice)
        self.filter_list[0].setProperty("active", "1" if is_active else "")
        self.filter_list[0].setProperty("filter_label", self._browse_filter_label())
        self._browse_load_grid()
    def _browse_genre_clicked(self):
        from .picker import PickerDialog
        current_idx = self._genres.index(self._active_genre) if self._active_genre in self._genres else 0
        # 4th element: the count, right-aligned and small. Deliberately absent
        # on "All" -- genres overlap (a title can be Action AND Adventure), so
        # there is no honest total to sum here, and the library's own count
        # already sits in the sidebar.
        rows = [(name, i == current_idx, None,
                 regional.number(self._genre_counts[name])
                 if name in self._genre_counts else "")
                for i, name in enumerate(self._genres)]
        dialog = PickerDialog.open(
            heading="Genre",
            rows=rows,
            selected_idx=current_idx,
        )
        if not dialog or dialog.canceled or dialog.picked_idx is None:
            return
        idx = dialog.picked_idx
        if idx < 0 or idx >= len(self._genres):
            return
        self._active_genre = self._genres[idx]
        self.genre_list[0].setProperty("genre_label", self._browse_genre_label())
        self.genre_list[0].setProperty("active", "1" if idx != 0 else "")
        self._browse_load_grid()

    def _browse_grid_clicked(self):
        item = self.grid_list.getSelectedItem()
        if not item:
            return
        data = item.dataSource or {}
        media_id = item.getProperty("media_id") or data.get("id") or data.get("media_id")
        if not media_id:
            # A member this server does not own yet: Detail still opens on
            # the tmdb id, which is what Discover does with the same shape.
            discovery_id = data.get("tmdb_id") or data.get("discovery_id")
            if discovery_id:
                self.open_detail(discovery_id=discovery_id)
            return
        # Opened directly, not via RunPlugin -- Detail layers over this
        # window instead of replacing it. Do not close this window here.
        self.open_detail(media_id=media_id)

    # ==================================================================
    # DISCOVER SECTION
    # ==================================================================

    def _discover_shelves(self, client) -> list[dict]:
        """Shelves to render, newest server surface first.

        `discovery.page` is the 32-shelf surface added in 0.9.24; servers
        without it keep the original 7-list endpoint, which is frozen for
        exactly this reason. Both are normalized to the same
        {title, items} shape so the render loop doesn't branch.

        Titles come from the shelf's own `title` -- the server names all 32,
        and since 0.9.25 the Settings home-screen editor can surface any of
        them, so a client-side label map would silently drop the ones it
        hadn't been taught."""
        if self._has_capability("discovery.page"):
            try:
                page = client.discovery_page() or {}
                return [
                    {"title": s.get("title") or _discover_list_title(s.get("key", "")),
                     "kind": s.get("kind"),
                     "items": s.get("items") or []}
                    for s in (page.get("shelves") or [])
                ]
            except http.ApiError as exc:
                kodigui.ERROR("main.py: discovery/page failed: {0}".format(exc))

        try:
            payload = client.discovery_lists() or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: discover discovery/lists failed: {0}".format(exc))
            return []
        # The frozen 7-list endpoint has no `kind`, so these all fall through
        # _discover_group_by_tab()'s unknown-kind path into the default tab --
        # which is right: an old server has no tab axis to group by, and one
        # populated "Now" tab is the closest thing to its flat list.
        return [
            {"title": _discover_list_title(l.get("list_type", "")),
             "kind": None,
             "items": l.get("items") or []}
            for l in (payload.get("lists") or [])
        ]

    def _discover_group_by_tab(self, shelves: list[dict]) -> dict[str, list[dict]]:
        """Bucket the flat shelf list into the four tabs by each shelf's `kind`.

        Shelves group by `kind` alone. Within a tab they run in the order
        DISCOVER_TAB_KINDS lists the kinds, and within a kind they keep the
        server's own order -- no per-shelf exceptions. An unrecognized kind
        goes to DISCOVER_UNKNOWN_KIND_TAB rather than disappearing; the spec's
        rule is "never drop a shelf"."""
        known = {k for kinds in home_rows.DISCOVER_TAB_KINDS.values() for k in kinds}
        grouped: dict[str, list[dict]] = {}
        for tab, kinds in home_rows.DISCOVER_TAB_KINDS.items():
            ordered: list[dict] = []
            for kind in kinds:
                ordered.extend([s for s in shelves if s.get("kind") == kind])
            grouped[tab] = ordered
        strays = [s for s in shelves if s.get("kind") not in known]
        if strays:
            kodigui.LOG("main.py: discover: {0} shelf(s) with unknown kind {1} -> {2} tab".format(
                len(strays), sorted({s.get("kind") for s in strays}),
                home_rows.DISCOVER_UNKNOWN_KIND_TAB))
            grouped[home_rows.DISCOVER_UNKNOWN_KIND_TAB].extend(strays)
        return grouped

    def _discover_load(self):
        client = self._get_client()
        if not client:
            return

        shelves = [s for s in self._discover_shelves(client) if s["items"]]
        self._discover_shelves_by_tab = self._discover_group_by_tab(shelves)
        self._discover_render_tab(self._discover_tab)

    def _discover_render_tab(self, tab: str):
        """Fill the fixed row slots from one tab's shelves.

        Slots are reused across tabs rather than rebuilt: MAX_DISCOVER_ROWS is
        sized for the largest tab, so switching is just a repopulate. Titles of
        unused slots are cleared, which is what hides their groups."""
        client = self._get_client()
        if not client:
            return
        self._discover_tab = tab
        self.setProperty("discover_tab", tab)
        shelves = self._discover_shelves_by_tab.get(tab, [])[: self.MAX_DISCOVER_ROWS]

        for idx in range(self.MAX_DISCOVER_ROWS):
            self.setProperty("discover_row{0}_title".format(idx), "")

        started = time.monotonic()
        self._discover_stage_first_screenful(client, shelves)
        for idx, shelf in enumerate(shelves):
            list_id = self.DISCOVER_ROW_LIST_IDS[idx]
            self.setProperty("discover_row{0}_title".format(idx), shelf["title"])
            mcl = self.discover_rows[list_id]
            ranked = shelf.get("kind") == "now"
            artcache.prefetch(client.stage_pairs(shelf["items"], "poster_path"))
            managed = [
                self._discover_build_card(client, it, rank=(i + 1) if ranked else None)
                for i, it in enumerate(shelf["items"])
            ]
            mcl.reset()
            if managed:
                mcl.addItems(managed)

        log.info("discover: %s -- %d shelf/shelves in %.2fs"
                 % (tab, len(shelves), time.monotonic() - started))

        # Every tab pill's Down must land on a row that actually exists; with
        # no shelves at all it stays on the pills rather than dropping focus
        # into a hidden control.
        target = self.DISCOVER_ROW_LIST_IDS[0] if shelves else None
        for idx, list_id in enumerate(home_rows.DISCOVER_TAB_LIST_IDS):
            try:
                ctl = self.getControl(list_id)
            except Exception:
                continue
            if target is not None:
                ctl.controlDown(self.getControl(target))

        # ...and the first row's Up must come back to the pill you're ON.
        # The template can only carry ONE static onup, so it named the nav bar
        # -- which meant Down from the pills into the row and then Up again
        # skipped the pill row entirely and jumped to the nav bar, losing the
        # group you were in. 7.9.2's focus gate is explicit that arriving
        # from outside "lands on the group you're ON", and the tab row can't
        # be a single control (four text-hugging pill widths, one <itemwidth>
        # per Kodi list), so the target changes with the tab and has to be
        # wired here rather than in XML.
        if target is not None:
            try:
                tab_idx = [t[0] for t in home_rows.DISCOVER_TABS].index(tab)
            except ValueError:
                tab_idx = 0
            try:
                self.getControl(target).controlUp(
                    self.getControl(home_rows.DISCOVER_TAB_LIST_IDS[tab_idx])
                )
            except Exception:
                pass

    def _discover_tab_clicked(self, control_id):
        try:
            idx = home_rows.DISCOVER_TAB_LIST_IDS.index(control_id)
        except ValueError:
            return
        tab = home_rows.DISCOVER_TABS[idx][0]
        if tab == self._discover_tab:
            return
        self._discover_render_tab(tab)

    def _discover_stage_first_screenful(self, client: MediaServerClient,
                                        shelves: list) -> None:
        """Fetch the art the viewer is about to look at, and only that.

        A discovery poster lives on the tofa cloud's CDN, so waiting for one
        is waiting on the internet. Everything else on this screen goes on
        doing what it did before -- queued in the background by ref(), drawn
        from the CDN until it lands -- because a shelf below the fold is not
        worth a stall and a tab can carry up to MAX_DISCOVER_ROWS of them.

        WHY IT IS WORTH WAITING FOR AT ALL. Anything Kodi has to cache itself
        costs download -> decode -> resize -> re-encode -> write to eMMC ->
        INSERT into Textures14.db, four jobs at a time, and the commit is
        what costs. Timed cold on the cinema box: fifteen images took **20.6
        seconds** to appear.

        THREE CAPS, and each one is load-bearing:

        - the first DISCOVER_EAGER_SHELVES shelves, because that is what
          fits on screen;
        - their first DISCOVER_EAGER_ITEMS cards, for the same reason -- a
          shelf carries 40 and shows about five. Staging whole shelves was
          measured at 2.40s on this call, against 75 images fetched to draw
          about ten;
        - backdrop and logo for the FIRST card of each, and no other, since
          those two fields belong to the wide focused card and item 0 is
          what focus lands on. Staging them for every card is the mistake
          that took a cold Home from 2.2s to 10.1s (see _CARD_ART_FIELD).

        One batch and one deadline rather than one per shelf, so the cap is
        on the wait the viewer feels rather than on each piece of it.
        """
        pairs, seen = [], set()
        for shelf in shelves[: self.DISCOVER_EAGER_SHELVES]:
            items = shelf.get("items") or []
            for pair in (client.stage_pairs(items[: self.DISCOVER_EAGER_ITEMS],
                                            "poster_path", include_cdn=True)
                         + client.stage_pairs(items[:1], "backdrop_path",
                                              "logo_path", include_cdn=True)):
                # Shelves overlap -- a title can be Trending AND Popular --
                # and stage_pairs only deduplicates within one call.
                if pair[1] not in seen:
                    seen.add(pair[1])
                    pairs.append(pair)
        if pairs:
            artcache.prefetch(pairs, timeout_s=self.DISCOVER_EAGER_TIMEOUT_S)

    def _discover_build_card(
        self, client: MediaServerClient, item: dict, rank: int | None = None
    ) -> kodigui.ManagedListItem:
        title = item.get("title") or ""
        poster = client.resolve_image_url(item.get("poster_path")) or ""
        # offscreen: built detached, handed to addItems, never written again.
        # See ManagedListItem.__init__ and issue #11.
        mli = kodigui.ManagedListItem(label=title, thumbnailImage=poster,
                                      data_source=item, offscreen=True)
        mli.setArt({"poster": poster})

        # The top-left chip is a RANK on Discover, not a rating. Captured from
        # the real app 2026-07-31: its `now` shelves (Trending/Popular/New and
        # Noteworthy) number their cards 1..N, and every other Discover shelf
        # -- acclaimed, decades, genres, availability, house -- shows no chip
        # at all. A rating chip there is a library-shelf thing (Home still
        # uses one, which matches). `rank` is None for the shelves that get
        # nothing, so the badge's own visible= gate hides it.
        mli.setProperty("rating", str(rank) if rank is not None else "")

        mli.setProperty("caption_meta", _discover_row_meta(item))

        # Art + scores for the wide focused card (fragments.discover_card).
        # Only the focused card shows these, but ListItem properties are set
        # once per item regardless of which layout is drawing it.
        mli.setProperty("backdrop", client.resolve_image_url(item.get("backdrop_path")) or "")
        mli.setProperty("logo", client.resolve_image_url(item.get("logo_path")) or "")
        mli.setProperty("scores_line", _discover_scores_line(item))

        # The top-right chip: plus (not in your library), clock (the server is
        # already getting it), or nothing at all for a title we hold -- the
        # app shows no checkmark. Watchlist is a separate concept with its own
        # glyph (bookmark/bookmark.slash). See cards.apply_library_badge.
        cards.apply_library_badge(mli, item, in_library=bool(item.get("in_library")))
        mli.setProperty(
            "cinema_glyph", self.CINEMA_GLYPH if _discover_in_cinemas(item) else ""
        )
        return mli

    def _discover_card_clicked(self, control_id):
        mcl = self.discover_rows.get(control_id)
        item = mcl.getSelectedItem() if mcl else None
        if not item or not item.dataSource:
            return
        data = item.dataSource
        # discovery_id is the tmdb_id; media_id is passed only when the
        # payload says the title is already owned. The detail window
        # handles both, opened directly so it layers over this window.
        self.open_detail(
            media_id=data.get("local_media_id"),
            discovery_id=data.get("tmdb_id"),
            media_type=data.get("type"),
            # The card's OWN payload, forwarded. /discovery/detail answers
            # availability and nothing else -- no title, no artwork, no
            # synopsis -- so a title this server does not hold had no hero at
            # all: an empty page with three buttons on it. The shelf item
            # already carries everything the hero needs, and it is the only
            # place that data exists client-side.
            discovery_item=data,
        )

    def _focused_card(self, control_id):
        """(ManagedControlList, item, row_kind) for whichever card list has
        focus, or (None, None, None) when focus isn't on a card at all.

        One lookup across all four sections rather than a per-section branch
        at every call site: Home's row slots, Discover's row slots, Browse's
        grid and Search's three shelves are held in four different shapes but
        answer the same question.

        Search's Actors shelf is deliberately absent -- a person is not a
        title and none of 7.2's options apply to one."""
        for lists, kind in ((self.row_lists, "home"), (self.discover_rows, "discover")):
            mcl = (lists or {}).get(control_id)
            if mcl is not None:
                item = mcl.getSelectedItem()
                if item is not None and item.dataSource:
                    if kind == "home" and control_id == self._cw_list_id:
                        kind = "cw"
                    return mcl, item, kind
        for mcl, cid, kind in (
            (self.grid_list, self.GRID_ID, "browse"),
            (self.movies_list, self.MOVIES_LIST_ID, "search"),
            (self.shows_list, self.SHOWS_LIST_ID, "search"),
        ):
            if control_id == cid and mcl is not None:
                item = mcl.getSelectedItem()
                if item is not None and item.dataSource:
                    return mcl, item, kind
        return None, None, None

    def _open_card_options(self, control_id) -> bool:
        """7.2's card options for the focused card. Returns True when the
        press was consumed, so onAction can fall through for anything that
        isn't a card (nav bar, pills, sidebar)."""
        mcl, item, kind = self._focused_card(control_id)
        if item is None:
            return False
        data = item.dataSource
        client = self._get_client()
        if not client:
            return False

        media_id = data.get("id") or data.get("media_id")
        in_library = bool(media_id)
        # An out-of-library card carries no progress at all, so both watched
        # flags stay false rather than being looked up and always missing.
        completed = bool(item.getProperty("watched"))
        has_progress = bool(item.getProperty("progress_pct")) or bool(item.getProperty("progress_fill"))
        on_watchlist = self._card_on_watchlist(client, data, kind)

        keys = cardoptions.option_keys(
            in_library=in_library,
            fully_watched=completed,
            has_progress=has_progress,
            on_watchlist=on_watchlist,
            in_continue_watching=(kind == "cw"),
        )
        picked = cardoptions.show(
            title=item.getLabel() or "",
            subtitle=item.getProperty("caption_meta") or "",
            keys=keys,
            # Same title, same action, same word as the detail hero.
            resume=has_progress and not completed,
        )
        if picked:
            self._apply_card_option(picked, client, data, item, kind)
        return True

    def _apply_card_option(self, picked, client, data, item, kind):
        """Carry out one card-options choice.

        Kept out of cardoptions.py deliberately: the dialog reports a key and
        this screen decides what it means, because "Play" on a Home card and
        on a Discover card are different journeys."""
        media_id = data.get("id") or data.get("media_id")
        media_type = data.get("type") or data.get("media_type")
        tmdb_id = data.get("tmdb_id")

        if picked in (cardoptions.PLAY, cardoptions.DETAILS):
            # Both route through the detail window: it already owns version
            # selection, resume-vs-restart and the out-of-library request
            # flow, none of which a context menu should reimplement.
            # Directly, not RunPlugin -- see _home_detail_clicked for what
            # that route costs. The options dialog is modal and has already
            # closed by the time this runs, so Detail opens over this window
            # rather than under the panel.
            if media_id:
                self.open_detail(media_id=media_id)
            elif tmdb_id is not None and media_type:
                self.open_detail(discovery_id=str(tmdb_id),
                                 media_type=media_type)
            return

        try:
            if picked in (cardoptions.MARK_WATCHED, cardoptions.MARK_UNWATCHED):
                watched = picked == cardoptions.MARK_WATCHED
                if self._set_watched(client, data, watched):
                    # On CONTINUE WATCHING the card must not merely gain a
                    # tick: the row is "what to watch next", and the episode
                    # just marked is no longer that. The server already does
                    # the thinking -- verified against a live server, marking
                    # The Rookie S1E5 watched turned the row's first card
                    # into S1E6 in the same slot, same show -- so this is a
                    # refetch, not client-side surgery.
                    if kind == "cw":
                        self._home_refresh_cw_row(client)
                        return
                    # Reflect it on the CARD as well. The panel derives its
                    # option set from the item's own properties, so without
                    # this the menu keeps offering "Mark as Watched" on a
                    # title it just marked -- and the poster's watched badge
                    # stays wrong until the row reloads.
                    item.setProperty("watched", "1" if watched else "")
                    if watched:
                        item.setProperty("progress_fill", "")
            elif picked in (cardoptions.WATCHLIST_ADD, cardoptions.WATCHLIST_REMOVE):
                adding = picked == cardoptions.WATCHLIST_ADD
                # Two endpoints, and which one applies is decided by what the
                # card actually carries. A library card has a media_id and
                # frequently NO tmdb_id, so the content endpoint can't serve
                # it; a Discover card is the reverse. Getting this wrong is
                # silent, which is how this row first shipped doing nothing.
                if media_id:
                    (client.watchlist_add if adding else client.watchlist_remove)(media_id)
                elif media_type and tmdb_id is not None:
                    if adding:
                        client.watchlist_add_content(media_type, tmdb_id, {})
                    else:
                        client.watchlist_remove_content(media_type, tmdb_id)
                else:
                    kodigui.ERROR(
                        "main.py: watchlist row has neither media_id nor tmdb_id: {0}".format(
                            sorted(data.keys())))
                    return
                item.setProperty("watchlisted", "1" if adding else "")
                # On the Watchlist itself the card has to LEAVE, not merely
                # lose its badge -- the list IS the watchlist, so a card that
                # stays is showing something that is no longer true. Everywhere
                # else (Home, Discover, a library grid, Search) the badge is
                # the whole story, because none of those lists are defined by
                # it, and dropping a card there would be losing the viewer's
                # place for nothing.
                if (not adding and kind == "browse"
                        and self._browse_active_source().get("kind") == "watchlist"):
                    self._browse_reload_keeping_position()
            elif picked == cardoptions.REMOVE_FROM_CW and media_id:
                client.dismiss_media(media_id)
                # Reload rather than hiding the item locally: the row is
                # server-ordered and dropping one card client-side would
                # leave the rest stale on the next arrival anyway.
                self._home_load()
        except http.ApiError as exc:
            kodigui.ERROR("main.py: card option {0} failed: {1}".format(picked, exc))

    def _card_on_watchlist(self, client, data, kind) -> bool:
        """Whether this card's title is on the watchlist.

        The server carries no per-title flag -- `/media` list items and
        `/media/{id}` both answer only `watched` -- so this is settled the same
        way DetailWindow._is_on_watchlist settles it: ask for the watchlist and
        look for the title in it. Matching media id FIRST and tmdb id second,
        because a library title's tmdb_id is often null and matching on that
        alone reports "not on the watchlist" for something sitting in it.

        One small request, and only when the menu is actually opened. It is NOT
        read from the card's own `watchlisted` property: Discover sets that from
        `in_library`, which is a different fact, and Browse/Home/Search never
        set it at all -- which is how the menu came to offer "Add to Watchlist"
        for a title you were looking at IN your watchlist.
        """
        # Browse's Watchlist needs no lookup at all: every card in that grid is
        # on the watchlist by construction.
        if kind == "browse" and self._browse_active_source().get("kind") == "watchlist":
            return True
        media_id = data.get("id") or data.get("media_id")
        tmdb_id = data.get("tmdb_id")
        try:
            entries = client.watchlist() or []
        except http.ApiError as exc:
            # Offer Add on a failed lookup. Wrongly offering Remove is the
            # worse miss: it presents an action that will then do nothing.
            kodigui.ERROR("main.py: watchlist lookup failed: {0}".format(exc))
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if media_id and entry.get("media_id") == media_id:
                return True
            if tmdb_id is not None and entry.get("tmdb_id") == tmdb_id:
                return True
        return False

    def _browse_reload_keeping_position(self):
        """Rebuild the Browse grid, leaving the selection where it was.

        For an action that REMOVES the focused card from the list it is in.
        Reloading rather than deleting the one item locally: the grid is a
        blank-allocated, page-chunked structure (_browse_blanks,
        _browse_page_data, _browse_filled, and the container itself), and
        unpicking one row out of the middle of all four is a way for them to
        disagree about which position holds what.

        The position is kept rather than reset to 0 because the viewer is
        standing in a list they are editing: sending them back to the top on
        every removal would make clearing several items a fight. It is clamped,
        since the list is now one shorter -- removing the last card lands on
        the new last one.
        """
        try:
            pos = self.grid_list.getSelectedPosition()
        except (RuntimeError, AttributeError):
            pos = 0
        self._browse_load_grid()
        try:
            remaining = len(self.grid_list)
        except (RuntimeError, AttributeError):
            return
        if not remaining:
            # Kodi will not focus an empty list, and _browse_wire_nav_down has
            # already re-aimed the nav bar at the sidebar for exactly this.
            self.setFocusId(self.SIDEBAR_ID)
            return
        try:
            self.grid_list.setSelectedItemByPos(min(pos, remaining - 1))
            # The reload filled its window around position 0; the selection
            # has just moved off it.
            client = self._get_client()
            if client:
                self._browse_fill_window(client)
            self.setFocusId(self.GRID_ID)
        except (RuntimeError, AttributeError):
            pass

    def _set_watched(self, client, data, watched: bool) -> bool:
        """Mark a card's title watched/unwatched. Returns whether anything
        was actually marked.

        Per-FILE because that's what the endpoint takes. A MOVIE marks every
        available file: those are versions of one thing, and the card's
        watched badge must not depend on which version happened to be played.

        A SHOW marks ONE EPISODE -- the one this card stands for. Continue
        Watching and Next Up name their own (`media_file_id` on the row), and
        anything else falls back to the episode the detail hero would offer,
        via the same progress.next_up() rule, so the menu and the page cannot
        disagree. This used to mark every episode of every season; see
        DetailWindow._set_media_watched for what that cost and why the
        whole-show action now lives only on the season menu.

        Returning False rather than failing silently matters: a no-op here is
        invisible on screen, which is how this shipped doing nothing at all."""
        media_id = data.get("id") or data.get("media_id")
        if not media_id:
            return False
        # The row already knows its episode -- an exact answer, and no
        # detail fetch at all.
        card_file_id = data.get("media_file_id")
        try:
            detail = client.media_detail(media_id) or {}
        except http.ApiError as exc:
            kodigui.ERROR("main.py: media_detail for watched-toggle failed: {0}".format(exc))
            return False

        if detail.get("seasons"):
            candidates = progress.episode_candidates(detail.get("seasons"))
            if not candidates:
                kodigui.ERROR("main.py: no playable episodes for media {0}".format(media_id))
                return False
            # required: this read chooses which episode gets WRITTEN. An
            # empty map on failure means "nothing watched", i.e. episode one
            # -- so a card menu pressed on a show mid-season would silently
            # mark S1 E1 instead of the episode the card stands for. A card
            # that carries its own media_file_id is immune (next_up prefers
            # it), which is exactly why the ones that don't must not guess.
            progress_map = progress.fetch_many(
                client, [c[3].get("id") for c in candidates], required=True)
            chosen = progress.next_up(candidates, progress_map, card_file_id)
            file_ids = [chosen[3].get("id")] if chosen else []
        else:
            file_ids = [f.get("id") for f in (detail.get("files") or [])
                        if f.get("available") and f.get("id")]

        file_ids = [f for f in file_ids if f]
        if not file_ids:
            kodigui.ERROR("main.py: no available files to mark for media {0}".format(media_id))
            return False
        for fid in file_ids:
            client.update_watched(fid, watched)
        return True

    def _search_key_clicked(self, control_id):
        grid = self.keyboard if control_id == self.KEYBOARD_ID else self.numpad
        item = grid.getSelectedItem() if grid else None
        if item and item.dataSource:
            self._search_apply_key(item.dataSource)

    def _search_spacerow_clicked(self):
        item = self.spacerow.getSelectedItem() if self.spacerow is not None else None
        if item and item.dataSource:
            self._search_apply_key(item.dataSource)

    def _search_apply_key(self, data: dict):
        action = data.get("action")
        if action == "append":
            self.search_query += data.get("value") or ""
        elif action == "del":
            self.search_query = self.search_query[:-1]
        elif action == "clear":
            self.search_query = ""
        # Keep the real edit control's text in sync with grid-driven edits
        # too -- it's the source of truth _search_sync_from_edit() reads
        # back from for physical-keyboard/native-OSK input.
        self.getControl(self.QUERY_EDIT_ID).setText(self.search_query)
        self._search_on_query_changed()

    def _search_sync_from_edit(self):
        text = self.getControl(self.QUERY_EDIT_ID).getText()
        if text != self.search_query:
            self.search_query = text
            self._search_on_query_changed()

    def _search_tab_clicked(self):
        # Whichever tab was actually clicked -- NOT a blind abc<->123
        # toggle, which would flip the mode even when re-clicking the
        # already-active tab.
        idx = self.tabs.getSelectedPosition() if self.tabs is not None else -1
        if not (0 <= idx < len(_SEARCH_TAB_LABELS)):
            return
        self.keyboard_mode = _SEARCH_TAB_LABELS[idx]
        self.setProperty("keyboard_mode", self.keyboard_mode)
        # Update is_active in place (not reset()+addItems()) so the tab
        # list's cursor position doesn't jump back to item 0 -- same
        # technique navbar.py:set_current() uses for is_current.
        tab_control = self.getControl(self.TAB_LIST_ID)
        for idx, label in enumerate(_SEARCH_TAB_LABELS):
            tab_control.getListItem(idx).setProperty("is_active", "1" if label == self.keyboard_mode else "")
        self._search_wire_keyboard_nav()

    def _search_wire_keyboard_nav(self):
        # TAB_LIST_ID's/SPACEROW_ID's Down/Up can't statically target
        # "whichever grid is currently visible" in XML -- letters and
        # digits are two separate controls (KEYBOARD_ID/NUMPAD_ID), only
        # one visible at a time, and Kodi's own "landed on a hidden
        # control -> follow ITS static XML tag" fallback would cascade to
        # the wrong one.
        active_grid_id = self.KEYBOARD_ID if self.keyboard_mode == "abc" else self.NUMPAD_ID
        try:
            self.getControl(self.TAB_LIST_ID).controlDown(self.getControl(active_grid_id))
            self.getControl(self.SPACEROW_ID).controlUp(self.getControl(active_grid_id))
        except Exception:
            pass

    def _search_on_query_changed(self):
        self.setProperty("query", self.search_query)
        q = self.search_query.strip()
        if not q:
            # Clearing is itself a change of query, so it takes a generation
            # too. Without this, a reply still in flight for the text that
            # was just deleted would land on the emptied screen.
            self._search_generation = getattr(self, "_search_generation", 0) + 1
            self.setProperty("results_caption", "")
            self.setProperty("no_results_caption", "")
            self.setProperty("movies_count", "0")
            self.setProperty("shows_count", "0")
            self.setProperty("actors_count", "0")
            self.setProperty("search_discover_count", "0")
            self.setProperty("has_results", "0")
            # `is not None`, NOT plain truthiness -- ManagedControlList
            # defines __len__, so a real-but-empty list (right after
            # construction or reset()) is falsy and `if self.x:` would
            # skip it.
            if self.top_result_list is not None:
                self.top_result_list.reset()
            if self.movies_list is not None:
                self.movies_list.reset()
            if self.shows_list is not None:
                self.shows_list.reset()
            if self.actors_list is not None:
                self.actors_list.reset()
            search_discover = self.discover_rows.get(self.SEARCH_DISCOVER_LIST_ID)
            if search_discover is not None:
                search_discover.reset()
            # Re-read from disk, not just re-show the stale in-memory list
            # -- a query typed and cleared in this same visit may have
            # just been committed to history (see
            # _search_maybe_commit_history()) and should appear right away.
            self._search_fill_history()
            return

        self.setProperty("results_caption", u'Results for "{0}"'.format(q))
        # Built here rather than concatenated in the XML so both captions
        # quote the query the same way.
        self.setProperty("no_results_caption", u'No results for "{0}"'.format(q))
        self._search_schedule(q)

    #: How long the query must stand still before it is worth asking the
    #: server. Long enough that a run of keypresses is ONE search, short
    #: enough that a viewer who has stopped typing does not notice waiting.
    SEARCH_DEBOUNCE_S = 0.35

    def _search_schedule(self, q: str):
        """Search after the typing stops, off the action thread.

        Every keystroke used to run the search INLINE, on the thread Kodi
        dispatches the click on. Two costs, and the viewer feels both as one:
        the query round trip (measured against the live server at 100ms to
        1.1s per keystroke) and then building up to ~57 result cards. While
        that thread is busy Kodi DROPS keypresses rather than queueing them
        -- the same behaviour _home_load documents -- so characters typed on
        the grid keyboard simply vanished. Reported from the box, and true
        here too, just faster.

        So the keypress now only records the query and returns. A worker
        waits for the typing to stop and does the work; if another key
        arrives first, its own generation number makes the older worker drop
        its result rather than race it onto the screen."""
        self._search_generation = getattr(self, "_search_generation", 0) + 1
        generation = self._search_generation

        def run():
            if xbmc.Monitor().waitForAbort(self.SEARCH_DEBOUNCE_S):
                return
            # Superseded while we waited: a later keystroke owns the screen.
            if generation != self._search_generation:
                return
            try:
                self._search_run(q, generation)
            except Exception as exc:  # noqa: BLE001 - a search must not kill the window
                kodigui.ERROR("main.py: search worker failed: {0!r}".format(exc))

        threading.Thread(target=run, name="tofa-search", daemon=True).start()

    def _search_run(self, q: str, generation: int | None = None):
        client = self._get_client()
        raw_movies, actors, discover = [], [], []
        if client:
            try:
                resp = client.search(q, movie_limit=40, actor_limit=12, discover_limit=12) or {}
                raw_movies = resp.get("movies") or []
                actors = resp.get("actors") or []
                discover = resp.get("discover") or []
            except http.ApiError as exc:
                kodigui.ERROR("main.py: search failed: {0}".format(exc))

        # The #1 match becomes Top Result, so it is held OUT of the shelves
        # rather than listed a second time a few hundred pixels below itself.
        # The real Apple TV app shows it once; ours showed "Hugo" as both the
        # Top Result and the first Movies card.
        top_item = raw_movies[0] if raw_movies else None
        top_id = (top_item or {}).get("id")
        movies, shows = [], []
        for item in raw_movies:
            if top_id and item.get("id") == top_id:
                continue
            if (item.get("media_type") or "").lower() == "tv":
                shows.append(item)
            else:
                movies.append(item)

        # The answer arrived; is it still the answer to the CURRENT query?
        # Checked after the fetch and before the first UI write, so a slow
        # reply to "be" cannot repaint over the results for "besen".
        if generation is not None and generation != self._search_generation:
            return

        # "Top Result" is the server's own #1-ranked match, taken from
        # raw_movies[0] BEFORE the movies/shows split above -- not
        # necessarily the first item of either resulting bucket.
        self._search_fill_top_result(top_item)
        self._search_fill_shelf(self.movies_list, movies)
        self._search_fill_shelf(self.shows_list, shows)
        self._search_fill_actors(actors)
        search_discover = self.discover_rows.get(self.SEARCH_DISCOVER_LIST_ID)
        if search_discover is not None and client:
            artcache.prefetch(client.stage_pairs(discover, "poster_path"))
            managed = [self._discover_build_card(client, it) for it in discover]
            search_discover.reset()
            if managed:
                search_discover.addItems(managed)

        self.setProperty("movies_count", str(len(movies)))
        self.setProperty("shows_count", str(len(shows)))
        self.setProperty("actors_count", str(len(actors)))
        self.setProperty("search_discover_count", str(len(discover)))
        # top_item COUNTS. It is held out of the movies/shows split above, so
        # a query matching exactly one title puts that title in the Top Result
        # and leaves every bucket empty -- which read as has_results=0 and drew
        # the "No results for ..." empty state straight over the Top Result
        # card that was sitting right there ("besenbinden", 2026-08-06).
        # _search_fill_top_result() already learned this lesson for its own
        # has_top_result flag; this line was the other half of it.
        self.setProperty(
            "has_results",
            "1" if (top_item or movies or shows or actors or discover) else "0")
        self._search_wire_right_target()

    def _search_fill_top_result(self, item: dict | None):
        if self.top_result_list is None:
            return
        self.top_result_list.reset()
        # Its own flag, not movies_count: the Top Result is held out of the
        # Movies shelf now, so a query whose only movie IS the top result
        # leaves that count at 0 and would otherwise hide the block showing
        # it.
        self.setProperty("has_top_result", "1" if item else "")
        # The TEXT is Window properties, not ListItem ones: it renders from a
        # static block beside the list rather than inside its item layout,
        # because Kodi ignores <wrapmultiline> on a label in a list item and
        # the synopsis has to wrap to three lines. See
        # skin/fragments.py:top_result_card(). Cleared alongside the flag so a
        # query with no top result cannot leave the previous one's text behind
        # -- the group is hidden either way, but a stale property outliving
        # its card is exactly how a later "why is this showing?" starts.
        for key, value in (
            ("top_result_title", item.get("title") or "" if item else ""),
            ("top_result_meta", _search_meta_line(item) if item else ""),
            ("top_result_ratings", _search_ratings_line(item) if item else ""),
            ("top_result_overview", (item.get("overview") or "") if item else ""),
        ):
            self.setProperty(key, value)
        if not item:
            return
        client = self._get_client()
        poster = client.resolve_image_url(item.get("poster_path")) if client else ""
        mli = kodigui.ManagedListItem(label=item.get("title") or "", thumbnailImage=poster or "", data_source=item)
        mli.setArt({"poster": poster or ""})
        self.top_result_list.addItems([mli])

    def _search_fill_shelf(self, shelf: kodigui.ManagedControlList | None, items: list[dict]):
        if shelf is None:
            return
        client = self._get_client()
        if client:
            artcache.prefetch(client.stage_pairs(items, "poster_path"))
        managed = []
        for item in items:
            poster = ""
            if client:
                poster = client.resolve_image_url(item.get("poster_path")) or ""
            # offscreen: built detached, handed to addItems below. See #11.
            mli = cards.poster_item(item, poster,
                                    prefs=self._ensure_preferences(),
                                    offscreen=True)

            mli.setProperty("caption_meta", _item_year(item))
            managed.append(mli)

        shelf.reset()
        if managed:
            shelf.addItems(managed)

    def _search_fill_actors(self, items: list[dict]):
        if self.actors_list is None:
            return
        client = self._get_client()
        if client:
            # Same reason as Detail's Cast & Crew: an unstaged headshot makes
            # Kodi cache it itself, and the SQLite commit that ends that is
            # what fills a people shelf in visible steps. A SHORTER deadline
            # than Detail's, though -- this shelf is what the viewer is
            # waiting for, not something built behind a hero, so a slow
            # network must not hold the results back. What misses the
            # deadline draws from the CDN, as it always did.
            artcache.prefetch(
                client.stage_pairs(items, "profile_url", include_cdn=True),
                timeout_s=1.0)
        managed = []
        for item in items:
            name = item.get("name") or ""
            photo = item.get("profile_url") or ""
            if photo and client:
                photo = client.resolve_image_url(photo) or photo
            # offscreen: built detached, handed to addItems below. See #11.
            mli = kodigui.ManagedListItem(label=name, thumbnailImage=photo,
                                          data_source=item, offscreen=True)
            # person_card()'s vocabulary, shared with Detail's Cast & Crew:
            # the photo rides on Art(poster) and its presence is announced by
            # has_photo, which is what gates the placeholder glyph.
            mli.setArt({"poster": photo})
            mli.setProperty("has_photo", "1" if photo else "")
            count = item.get("media_count") or 0
            mli.setProperty("titles_label", "{0} title{1}".format(count, "" if count == 1 else "s"))
            managed.append(mli)
        self.actors_list.reset()
        if managed:
            self.actors_list.addItems(managed)

    def _search_result_clicked(self, controlID):
        shelf = self.movies_list if controlID == self.MOVIES_LIST_ID else self.shows_list
        item = shelf.getSelectedItem()
        if not item or not item.dataSource:
            return
        media_id = item.dataSource.get("id")
        if not media_id:
            return
        # Opened directly -- Detail layers over this window, do not close it.
        self.open_detail(media_id=media_id)

    def _search_top_result_clicked(self):
        item = self.top_result_list.getSelectedItem() if self.top_result_list is not None else None
        if not item or not item.dataSource:
            return
        media_id = item.dataSource.get("id")
        if not media_id:
            return
        self.open_detail(media_id=media_id)

    def _search_actor_clicked(self):
        item = self.actors_list.getSelectedItem() if self.actors_list is not None else None
        if not item or not item.dataSource:
            return
        name = item.dataSource.get("name") or ""
        if not name:
            return
        # Interim: re-run /search with the person's exact name, which ranks
        # their titles highly.
        #
        # NOT because the server lacks a filmography endpoint -- it has one,
        # GET /api/v1/discovery/person?name=&limit=, which this comment
        # previously claimed did not exist (found 2026-07-31 by diffing the
        # OpenAPI spec against our call sites). What's missing is the SCREEN:
        # 7.4's person page (name header, library-count subtitle, and one
        # 5-column grid split into "In your library" / "Not in your library").
        # Until that exists, search is the honest substitute; when it does,
        # this should call the real endpoint instead.
        self.search_query = name
        self.getControl(self.QUERY_EDIT_ID).setText(name)
        self._search_on_query_changed()

    def _search_fill_history(self):
        """Populates the idle-state "Recent Searches" list from local
        storage (no server endpoint exists for this, see
        search_history.py). `has_history` stays "0" if this profile has
        never searched, or profile_id couldn't be resolved."""
        if self.history_list is None:
            return
        entries = search_history.get(self._search_profile_id) if self._search_profile_id else []
        managed = [
            kodigui.ManagedListItem(
                label=q, data_source=q,
                properties={"icon": chr(icon_glyphs.ROTATE_CCW_CLOCK)})
            for q in entries
        ]
        # A trailing "Clear" row, the way the real Apple TV ends its own
        # Recent Searches. Its own glyph (circle-x, not the clock every query
        # above it carries) so it does not read as another past search --
        # which is the whole reason it needs a different icon rather than just
        # a different label. data_source is the sentinel the click handler
        # matches on; a query can never collide with it because add() strips
        # and rejects empty ones.
        if managed:
            managed.append(kodigui.ManagedListItem(
                label="Clear", data_source=self.HISTORY_CLEAR,
                properties={"icon": chr(icon_glyphs.CIRCLE_X)}))
        self.history_list.reset()
        if managed:
            self.history_list.addItems(managed)
        self.setProperty("has_history", "1" if managed else "0")
        self._search_wire_right_target()

    def _search_wire_right_target(self):
        """Every left-column control's <onright> is baked into the static XML
        as a single fixed target (6805, Top Result) -- wrong while idle with
        history showing instead, since Kodi can't focus a hidden control.

        TAB_LIST_ID is in the source list even though it is a HORIZONTAL
        list: Right steps "abc" -> "123" INSIDE the list first and only fires
        controlRight off the last item, so wiring it costs nothing on the
        first tab and is the only way off the second. It was the one control
        in this column left out, and its XML pointed <onright> back at itself,
        so Right on "123" wrapped to "abc" and the switcher was a trap you
        could only leave vertically."""
        target_id = (
            self.HISTORY_LIST_ID
            if not self.search_query.strip() and self.getProperty("has_history") == "1"
            else self.TOP_RESULT_LIST_ID
        )
        try:
            target = self.getControl(target_id)
            for source_id in (self.QUERY_EDIT_ID, self.TAB_LIST_ID, self.KEYBOARD_ID,
                              self.NUMPAD_ID, self.SPACEROW_ID):
                self.getControl(source_id).controlRight(target)
        except Exception:
            pass

    def _search_maybe_commit_history(self):
        """Called when focus leaves the query edit control (see onFocus)
        -- records the current query as a completed search once the user
        has actually moved on to look at its results, rather than on
        every debounced keystroke (which would otherwise fill history
        with typo-in-progress partial queries like "a", "av", "ava...")."""
        q = self.search_query.strip()
        if not q or not self._search_profile_id:
            return
        if self.getProperty("has_results") != "1":
            return
        if self._search_history_committed_for == q.lower():
            return
        search_history.add(self._search_profile_id, q)
        self._search_history_committed_for = q.lower()

    def _search_history_clicked(self):
        item = self.history_list.getSelectedItem() if self.history_list is not None else None
        if not item:
            return
        if item.dataSource is self.HISTORY_CLEAR:
            # Forget the lot and re-fill in place. _search_fill_history() also
            # resets has_history, which is what hides the whole block and
            # swaps in the first-run empty state -- and it calls
            # _search_wire_right_target(), so the keyboard column's Right stops
            # pointing at a list that no longer has anything to focus.
            search_history.clear(self._search_profile_id)
            self._search_history_committed_for = None
            self._search_fill_history()
            self.setFocusId(self.QUERY_EDIT_ID)
            return
        query = item.getLabel()
        self.search_query = query
        self.getControl(self.QUERY_EDIT_ID).setText(query)
        self._search_on_query_changed()
        self.setFocusId(self.QUERY_EDIT_ID)

    # ------------------------------------------------------------------
    # SETTINGS SECTION (9) -- replaces Kodi's own ADDON.openSettings()
    # dialog. Six pages down a sidebar; only Account is built so far, the
    # rest render 9.7's empty scaffold (see resources/lib/settings_pages.py,
    # which both this and skin/screens.py read so the two halves of the
    # screen cannot drift apart).
    # ------------------------------------------------------------------

    def _settings_fill_nav(self):
        """The sidebar's six rows. Static -- no server data is needed to
        know which pages exist, only to fill in their value subtitles, which
        _settings_load() does later."""
        items = []
        for page in settings_pages.PAGES:
            li = kodigui.ManagedListItem(label=page.label, data_source=page)
            li.setProperty("icon_glyph", chr(page.glyph))
            items.append(li)
        self.settings_nav_list.reset()
        self.settings_nav_list.addItems(items)
        self.settings_nav_list.selectItem(0)
        self._settings_show_page()

        # The three Account action rows. All are one-item lists whose single
        # item never changes, so they are built once here rather than per
        # load; only their subtitles are data, and those are set on the item
        # by _settings_load().
        switch = kodigui.ManagedListItem(label="Switch Profile")
        switch.setProperty("icon_glyph", chr(icon_glyphs.USERS))
        switch.setProperty("summary", "")
        # Not destructive: switching servers keeps the pairing and is one
        # keypress to undo by switching back, which is the whole point of it
        # existing rather than making people sign out.
        server = kodigui.ManagedListItem(label="Switch Server")
        server.setProperty("icon_glyph", chr(icon_glyphs.SERVER))
        server.setProperty("summary", "")
        self.settings_switch_profile_list.reset()
        self.settings_switch_profile_list.addItems([switch])
        self.settings_switch_server_list.reset()
        self.settings_switch_server_list.addItems([server])

        direct = kodigui.ManagedListItem(label="Direct connections only")
        # Kept to ONE rendered line: the row's summary is a fixed-width label
        # that ellipsises, not a textbox, so "...even if it is the only way"
        # lost its tail off the right edge. The fuller "what the relay is"
        # explanation now lives in the CONNECTION note below, so this can be
        # terse -- it only has to say what the toggle DOES.
        direct.setProperty(
            "summary",
            "Never use the tofa relay, even if it's the only way")
        self.settings_direct_list.reset()
        self.settings_direct_list.addItems([direct])

        out = kodigui.ManagedListItem(label="Sign Out")
        out.setProperty("icon_glyph", chr(icon_glyphs.LOG_OUT))
        out.setProperty("summary", "Disconnect this device from your server")
        # 2: destructive reads as red TEXT over glass, not a filled red row.
        out.setProperty("destructive", "1")
        self.settings_sign_out_list.reset()
        self.settings_sign_out_list.addItems([out])

    def _settings_current_page(self) -> settings_pages.Page | None:
        item = self.settings_nav_list.getSelectedItem()
        return item.dataSource if item else None

    def _settings_show_page(self):
        """Swap the detail pane to whichever sidebar row is selected.

        Also re-points the sidebar's Right key at that page's first
        focusable control, for the same reason every section re-points the
        nav bar's Down: the target is baked once into the rendered XML and
        cannot vary by which page is showing. A page with nothing focusable
        keeps Right pointing back at the sidebar, so the key is a no-op
        instead of dropping focus into a dead pane."""
        page = self._settings_current_page()
        if page is None:
            return
        self.setProperty("settings_page", page.key)
        self.setProperty("settings_title", page.title)
        self.setProperty("settings_subtitle", page.subtitle)
        target = settings_pages.RIGHT_TARGETS.get(page.key, self.SETTINGS_NAV_ID)
        try:
            self.getControl(self.SETTINGS_NAV_ID).controlRight(self.getControl(target))
        except Exception:
            pass

    def _settings_page_clicked(self):
        """Select on a sidebar row moves INTO the page rather than being a
        second way to switch to it -- the page already changed on focus (see
        onAction). Nothing to move into on an unbuilt page, so Select there
        is deliberately a no-op rather than a focus dead-end.

        Nothing routes to Kodi's own settings dialog any more: This Device
        was the last bridge to it, and every setting that lived there now has
        a home on one of these six pages."""
        page = self._settings_current_page()
        if page is None:
            return
        # Sync the pane to the highlighted row first. On the remote this is a
        # no-op -- the Up/Down handler above has already switched the page --
        # but any path that moves the sidebar's selection WITHOUT an Up/Down
        # leaves the two disagreeing: the row highlights and the pane keeps
        # showing the previous page. SetFocus(8000,n) from a script does
        # exactly that, and it produced two screenshots during the 2026-08-27
        # session that looked like a real bug and were not. Idempotent, so
        # making the honest path bulletproof costs nothing.
        self._settings_show_page()
        target = settings_pages.RIGHT_TARGETS.get(page.key)
        if target:
            self.setFocusId(target)

    def _settings_load(self):
        """Fill in everything on the Account page that comes from the server.

        Best-effort throughout: this screen is also the way BACK from a
        broken connection (it holds Sign Out and the manage-account QR), so
        a server that cannot be reached has to leave it usable rather than
        blank it. Anything unresolved reads as an em dash."""
        self.setProperty("settings_qr_caption",
                         "Scan to manage your account, or visit "
                         "app.tofa.tv/account in a browser.")
        self.setProperty("settings_email", "—")

        self._settings_fill_home_screen()
        self._settings_fill_add_rows()
        self._settings_fill_media_cards()
        self._settings_fill_playback()
        self._settings_fill_quality()
        self._settings_fill_audio()
        self._settings_fill_region()
        self._settings_fill_direct_only()
        self._settings_fill_privacy()
        self._settings_fill_device()
        self._settings_wire_account_nav()
        self._settings_wire_appearance_nav()
        self._settings_wire_segmented()

        _t0 = time.monotonic()
        client = self._get_client()
        me: dict = {}
        if client is not None:
            try:
                me = client.whoami() or {}
            except http.ApiError as exc:
                log.warning("settings: whoami failed: {0}".format(exc))
        # AFTER whoami: a call that started on the LAN address and fell back to
        # the relay has already swapped base_url by now, so the note reports
        # the route actually carrying traffic rather than what pairing stored.
        self._settings_fill_connection(client)

        # ORDER MATTERS on this page. Every fill below the email is LAN-fast --
        # system_info, the profile list, avatars off it -- while the email
        # alone is a CLOUD lookup: two internet round trips (mint a 15-minute
        # token, then GET /v1/me). It used to run FIRST, so the whole Account
        # view sat blank behind it -- measured locally at 0.16s of a 0.22s
        # load, and much worse from a box across the internet, which is what
        # "it takes a while for the values to appear" was. So the LAN data is
        # painted first and the email is fetched LAST; the page fills at once
        # and the address drops in a beat later.
        server_name, library_count = self._settings_server_summary(client)
        # The sidebar card's second line, e.g. "MEDIA-NAS - 4 libraries" -- or
        # "1 library", singular, on a server with one. A fresh server has
        # exactly one library for as long as it takes to add the second, so
        # "1 libraries" is what a new viewer sees first.
        libraries = ("" if library_count is None else
                     "{0} {1}".format(library_count,
                                      "library" if library_count == 1 else "libraries"))
        summary = " · ".join(part for part in (server_name, libraries) if part)
        self.setProperty("settings_server_line", summary)
        # The ROW says only the server's NAME, as the app's does. The library
        # count is not dropped -- the sidebar card above already carries it,
        # on both clients -- and a row that answers "which server am I on"
        # should answer exactly that.
        self.settings_switch_server_list.getListItem(0).setProperty(
            "summary", server_name or "—")
        # The SERVER card's two value rows, back now that the pane scrolls.
        self.setProperty("settings_server", server_name or "—")
        self.setProperty("settings_libraries",
                         "" if library_count is None else str(library_count))

        profile = self._settings_active_profile()
        self.settings_switch_profile_list.getListItem(0).setProperty(
            "summary", (profile.name if profile else "") or "")
        self.setProperty("settings_avatar_photo",
                         self._settings_account_avatar()
                         or self._settings_avatar_photo(profile))
        self.setProperty("settings_avatar", self._settings_avatar_texture(profile))
        self.setProperty("settings_avatar_initial",
                         self._settings_avatar_initials(profile))

        # LAST, because it is the slow one -- see the ORDER MATTERS note above.
        # The app's row here is "Email", showing the tofa account address. The
        # media server has no email field at all -- its User record is id /
        # username / avatar_path / preferences / is_admin -- and the address
        # lives only on the cloud account, which this client stops holding a
        # token for once pairing finishes. So the row names what we can
        # actually answer. Falls back to the media server's username, all this
        # page could show before pairing started keeping a cloud refresh token.
        username = me.get("username") or ""
        identity = self._settings_account_identity()
        account_line = (identity.get("email") or username)
        if account_line:
            # The ACCOUNT row's value column is wide; the identity card is
            # 310px and the sidebar row 284, and a real address overruns
            # both. Cut the MIDDLE rather than let Kodi cut the end, which
            # would drop the domain -- see textmetrics.middle_ellipsis.
            # The value column is `width // 2 - 40` = 290px, narrower than
            # the card's 310, so this one truncates hardest of the three.
            self.setProperty("settings_email", textmetrics.middle_ellipsis(
                account_line, 290, font_size=24))
            # FULL, not truncated: the card's font is tofa_font_account
            # (semibold 20) rather than metadata 23, and the address fits at
            # that size -- which is exactly why the app shows it whole here
            # and we could not.
            self.setProperty("settings_account_line", account_line)
            self._settings_nav_account_line = textmetrics.middle_ellipsis(
                account_line, 284)
        log.info("settings: Account page filled in {0:.2f}s".format(
            time.monotonic() - _t0))

        # Sidebar subtitles. Account's is the signed-in name and Appearance's
        # names the chosen fox; the rest DESCRIBE the page rather than
        # reporting a value from inside it.
        #
        # Playback and Audio used to report values ("Asks to skip intros",
        # "English . Subtitles off") and were dropped, because they did not
        # work and looked as though they should. THIS BLOCK ONLY RUNS FROM
        # _settings_load(), i.e. on first entry to Settings, on a profile
        # switch and after sign-out -- never after _settings_write(), which
        # also leaves "settings" in _loaded_sections so re-entering the
        # section does not re-run it either. A viewer changed their subtitle
        # language and watched the line sit there.
        #
        # SO: any summary added here that reports a VALUE must also be
        # refreshed where that value is written, the way Appearance does via
        # _settings_refresh_appearance_summary(). A one-off read in this
        # dictionary is a summary that will be wrong by the next keypress.
        #
        # Widths are measured against the 284px this column gives:
        # "How playback starts and behaves" is 334px and would have been cut.
        subtitles = {
            "account": getattr(self, "_settings_nav_account_line", "") or username,
            "playback": "How playback behaves",
            # Not "Languages and subtitles", which repeats the row's own
            # label; "defaults" is also the honest word for all five rows,
            # including the always-show toggle, which is not a language.
            "audio": "Language defaults",
            "appearance": self._settings_appearance_summary(),
            "privacy": "Diagnostics and version",
            "device": "Fonts and device id",
        }
        for idx, page in enumerate(settings_pages.PAGES):
            self.settings_nav_list.getListItem(idx).setProperty(
                "summary", subtitles.get(page.key, ""))

    def _settings_server_summary(self, client) -> tuple[str, int | None]:
        """(server name, library count), either of which may be unavailable.

        The NAME does not come from the media server at all: /system/info
        carries a version, capabilities and a `library_count`, but no
        human-readable name for itself. The only source is the tofa cloud's
        GET /servers, which needs the cloud token that exists solely during
        pairing -- so signin.py captures it into the token store and this
        reads it back. An install paired before that landed has no name
        stored, and falls back to the host, which is at least the thing the
        user typed."""
        name, count = "", None
        try:
            tok = auth.load()
            name = tok.server_name or urllib.parse.urlparse(tok.server).hostname or ""
        except auth.NotSignedIn:
            pass
        if client is None:
            return name, count
        try:
            info = client.system_info() or {}
            if isinstance(info.get("library_count"), int):
                count = info["library_count"]
        except http.ApiError as exc:
            log.warning("settings: system_info failed: {0}".format(exc))
        if count is None:
            try:
                libraries = client.libraries() or []
                count = len(libraries)
            except http.ApiError as exc:
                log.warning("settings: libraries failed: {0}".format(exc))
        return name, count

    def _render_nav_avatar(self):
        """The top-right profile marker. Visual only -- there is no control
        to focus, so this just names a texture.

        Shares _settings_active_profile()'s cache, which is why that lookup
        is cached at all now: the avatar wants it on every launch, where
        before only the Settings page did, and it costs a profile-list round
        trip. Silent on failure: an unknown profile simply shows no avatar
        rather than a wrong one."""
        try:
            # The profile may have CHANGED since anything cached it -- the
            # picker runs immediately before this on every launch. Reported
            # as the marker still showing the previous profile's initials
            # after a PIN was entered.
            self._invalidate_profile_cache()
            profile = self._settings_active_profile()
            self.setProperty("nav_avatar_photo",
                             self._settings_avatar_photo(profile))
            self.setProperty("nav_avatar",
                             self._settings_avatar_texture(profile))
            self.setProperty("nav_avatar_initial",
                             self._settings_avatar_initials(profile))
        except Exception as exc:
            log.warning("main.py: nav avatar unavailable: {0!r}".format(exc))
            self.setProperty("nav_avatar", "")
            self.setProperty("nav_avatar_photo", "")
            self.setProperty("nav_avatar_initial", "")

    def _settings_active_profile(self):
        """The signed-in profile's record, or None.

        One call for both the Switch Profile row's name and the sidebar
        card's avatar. It used to be two, and the second round trip was
        enough to make the whole page visibly finish drawing in stages.

        The name is not in the token store -- only the id is -- so this
        needs the profile list either way. Failure is silent: an unnamed row
        still opens the picker, which is the whole point of it."""
        if getattr(self, "_active_profile_cached", False):
            return self._active_profile
        self._active_profile_cached = True
        self._active_profile = None
        try:
            from .. import profiles as profiles_api
            tok = auth.load()
            session = http.new_session()
            everyone = list(profiles_api.list_profiles(
                session, tok.server, tok.access_token, tok.device_id,
                fallback=tok.server_fallback))
            # The ACCOUNT's avatar rides on the primary profile, which is
            # where the cloud applies an uploaded account picture (issue #7).
            # Picked up on this same pass rather than a second one, for the
            # staged-drawing reason above.
            for profile in everyone:
                if getattr(profile, "is_primary", False):
                    self._account_profile = profile
                    break
            if not tok.profile_id:
                return None
            for profile in everyone:
                if profile.id == tok.profile_id:
                    self._active_profile = profile
                    return profile
        except Exception:
            pass
        return None

    def _settings_account_avatar(self) -> str:
        """The ACCOUNT's picture for the identity card, which is a different
        thing from the profile's and is why the app shows two.

        The app's card carries the account avatar while its nav bar carries
        the signed-in PROFILE's, so on this household the card is the
        uploaded photo and the nav is Claude Code's robot preset. Ours had
        the profile's in both places.

        The cloud has no avatar of its own to give: GET /v1/me answers
        email / email_verified / identity_id / is_staff / name / tier /
        username and nothing pictorial. It arrives instead on the PRIMARY
        profile, as `custom:<uuid>` with a tokenless
        `https://api.tofa.tv/v1/avatars/<uuid>` beside it -- measured on this
        account, where the primary carries one and the other three carry
        presets or nothing.

        Empty when the account has no uploaded picture, which leaves the card
        on the profile's own avatar exactly as before."""
        self._settings_active_profile()          # fills _account_profile too
        return self._settings_avatar_photo(getattr(self, "_account_profile", None))

    def _settings_avatar_texture(self, profile) -> str:
        """A URL for the profile's `preset:` avatar, or "" for the monogram.

        This used to name BUNDLED art, and fell back to a generic fox when
        the profile had a photo or nothing -- a stand-in face, i.e. the wrong
        person's avatar, chosen so the card was never empty. Both are gone:
        the art now comes from the server (see avatar_presets, and the reason
        it is not bundled) and the fallback is this profile's own initials,
        which are always right and need no network.

        Costs nothing when the server is unreachable -- url_for answers ""
        rather than raising -- which is what keeps the old guarantee."""
        if profile is None:
            return ""
        client = self._get_client()
        if client is None:
            return ""
        return avatar_presets.url_for(
            client.session, client.base_url, profile.avatar_ref,
            client.access_token)

    def _settings_avatar_photo(self, profile) -> str:
        """An uploaded profile picture's URL, straight through.

        This card used to refuse photos, on the grounds that one "needs an
        image-token round trip" and this screen must stay usable with the
        server unreachable. That was true of SERVER art and is not true of
        these: an uploaded avatar lives on the tofa cloud
        (`https://api.tofa.tv/v1/avatars/<id>`) and is served with no token
        and no auth, so there is nothing to fetch first and nothing to spend.

        Measured, because it looked otherwise at first: the URL 403s for
        `Python-urllib`, which is a USER-AGENT block and not authentication
        -- any ordinary agent, Kodi's included, gets a 200 and a WebP. Do not
        re-derive "photos need a token" from a bare 403."""
        if profile is None:
            return ""
        return getattr(profile, "avatar_image_url", "") or ""

    def _settings_avatar_initials(self, profile) -> str:
        """The monogram behind the avatar, shown when there is no art."""
        if profile is None:
            return ""
        return profile_select._initials(getattr(profile, "name", "") or "")

    def _invalidate_profile_cache(self):
        """Drop the cached profile record. Switching profiles changes the
        face in the nav bar, and the cache would otherwise keep the old one
        for the life of the window."""
        self._active_profile_cached = False
        self._active_profile = None

    def _settings_switch_profile(self):
        """Open the profile picker, then rebuild the whole window.

        Everything this used to do by hand -- dropping _loaded_sections,
        the client, the preferences, the warmed prefetch, the profile cache,
        the Home rows -- was an attempt to make ONE window stop believing it
        belonged to the previous viewer. It never covered Browse, Discover or
        Search, whose lists kept the old profile's items until each section
        happened to reload; verified 2026-08-08, where the Browse grid still
        held the previous profile's titles after the switch.

        For a Kids profile that is not untidiness, it is showing a child the
        library they were moved away from. So the window goes instead. The
        launcher builds a new one, on Home, which is where a switch should
        land anyway: you have just said who is watching.

        Only the module-level caches need clearing here, since they outlive
        the window: the theme (accent is per-profile server data) and the
        prefetch (its client still carries the old profile's token). The
        launcher re-warms for the new identity behind the splash."""
        if not profile_select.switch_profile():
            return
        # Cover this window before anything else. The picker has just closed,
        # so the Settings page it was pressed from is back on screen, and it
        # stays there until closeNow() unwinds and the launcher raises the
        # splash. Reported from the box as a split-second flash back to
        # Settings. The cover is SPLASH_BG, so what follows it is the same
        # colour and the join is invisible.
        self.setProperty("switching_profile", "1")
        theme.reset_cache()
        # ...and immediately resolve it again, for the NEW viewer, because the
        # very next thing on screen is the splash and it cannot do this for
        # itself: it is raised with no network and no window to wait on. Drop
        # this and the switch plays the OUTGOING profile's fox at the incoming
        # one, which is the frame everybody would notice.
        #
        # A round-trip on this path is affordable in a way it is nowhere else:
        # the window is already being torn down and rebuilt, and the splash
        # covers the whole of it.
        theme.remember_accent()
        prefetch.reset()
        # Home, not wherever the switch was pressed from.
        xbmcgui.Window(10000).clearProperty(self.LAST_SECTION_PROPERTY)
        self.request_restart()
        # Keep the splash beneath us UP as this window goes, instead of
        # letting it step aside and show Kodi's own Home through the gap.
        splash.arm_for_restart()
        # Raising a splash HERE, before the close, does not work and is worth
        # writing down: it becomes the current window and pushes this one into
        # the history, but closeNow() then closes a window UNDERNEATH the
        # splash, and Kodi collapses the stack past both of them to its own
        # Home. Measured: 2.47s of Kodi's menu, worse than doing nothing,
        # because the wait for the animation then runs with Kodi on screen.
        # The launcher's restart loop raises it after this returns instead.
        self.closeNow()

    def _settings_switch_server(self):
        """Move this device to another server on the account, keeping the
        pairing (see signin.interactive_switch_server).

        The teardown is the sign-out one, not the profile-switch one, and
        for a stronger reason than either: nothing cached here belongs to
        the new server. Every id in a cached row, the accent, the
        preferences and the warmed client are all the old server's, and the
        stored profile is gone entirely because profiles are per-server --
        so the next _client() call runs the "Who's watching?" gate against
        the new server, exactly as a fresh launch would."""
        if not signin.interactive_switch_server():
            return
        # reset(), not discard_client(): a server change is a change of
        # IDENTITY in every sense the prefetch cares about, and any row it
        # warmed at launch and nothing has consumed yet belongs to the old
        # server. Same call the sign-out path makes, for the same reason.
        prefetch.reset()
        theme.reset_cache()
        self._settings_apply_theme()
        self._loaded_sections = {"settings"}
        self.client = None
        self._preferences = None
        # Both of these were missing, and both showed up the first time this
        # path was walked on a real second server (2026-08-13). A DIFFERENT
        # SERVER is a different library, so its language facet is a different
        # list; and this path can fall THROUGH to a full re-pair, when the
        # install has no cloud refresh token, after which the cloud identity
        # is a different answer -- the account email had stayed at the
        # username fallback cached before the pairing.
        self._settings_languages = None
        self._settings_identity = None
        self._invalidate_profile_cache()
        # ORDER MATTERS, and the old order was wrong. _render_nav_avatar
        # REPOPULATES the profile cache, and at this point no profile is
        # selected: profiles are per-server, so the switch cleared it, and
        # the gate that picks the new one does not run until _settings_load
        # asks for a client. Running the avatar first therefore cached "no
        # profile" and the Switch Profile row stayed blank for the life of
        # the window, with the profile picker having just been answered.
        # Loading first means the gate has run and both reads see it.
        self._settings_load()
        self._render_nav_avatar()

    def _settings_sign_out(self):
        """Sign out, then offer to pair again rather than dropping the viewer
        out of the add-on entirely.

        This window IS the add-on's top level -- launch_home.py is just
        `MainWindow.open()` -- so closing it ends the script and lands the
        viewer back in Kodi's own menu. That is a fine LAST step but a bad
        first one: signing out of one account to sign into another is the
        normal reason to press this, and quitting to the Kodi menu in between
        makes it look like a crash. So drive the same device-code flow
        onFirstInit uses, and only close if the viewer declines it.

        Everything cached belongs to the old account, so a successful re-pair
        drops it all and lets each section re-fetch when next shown."""
        if not cardoptions.confirm_sign_out():
            return
        auth.sign_out()
        if not signin.interactive_sign_in():
            self.closeNow()
            return
        # The warmed client was built at launch with the OLD account's token
        # and is not consumed on read, so _client() would hand it back for
        # the life of the window and every call would 401.
        prefetch.discard_client()
        theme.reset_cache()
        self._settings_apply_theme()
        self._loaded_sections = {"settings"}
        self.client = None
        self._preferences = None
        # A different account is a different library, so its languages are a
        # different list. This path re-pairs WITHOUT rebuilding the window
        # (the profile switch restarts it instead), so these have to be
        # dropped by hand -- as they do on the switch-server path above,
        # which reaches the very same pairing when there is no cloud token.
        self._settings_languages = None
        self._settings_identity = None
        self._invalidate_profile_cache()
        # Same reason as the profile switch above: the warmed client belongs
        # to the account that just signed out.
        prefetch.reset()
        # Load THEN draw the avatar, the order the switch-server path spells
        # out: the profile gate runs inside _settings_load, and a marker
        # drawn before it caches "no profile" for the window's life.
        self._settings_load()
        self._render_nav_avatar()

    # --- 9.4's fox / accent picker (Appearance page) -------------------

    SETTINGS_FOX_BLURB = (
        "Pick a fox. It sets your accent and matching logo across all your "
        "tofa apps. Buttons, highlights, and progress all follow it. "
        "Tofa Fox is the original look and the recommended experience."
    )

    def _settings_fill_foxes(self):
        """The 14 preset tiles, in 2's own order.

        Static, like the sidebar: which foxes exist is not server data. Only
        WHICH ONE is selected is, and that is re-marked by
        _settings_mark_selected_fox() whenever the accent changes."""
        self.setProperty("settings_fox_blurb", self.SETTINGS_FOX_BLURB)
        items = []
        for name, hex_value, logo in theme.PRESETS:
            li = kodigui.ManagedListItem(
                label="{0} Fox".format(name), data_source=hex_value)
            li.setProperty("tile_color", "0xFF" + hex_value)
            # The artwork cannot be tinted at runtime, so each tile carries
            # its own raster -- see theme.PRESETS.
            li.setArt({"thumb": logo})
            if hex_value == theme.DEFAULT_ACCENT:
                li.setProperty("is_default", "1")
            items.append(li)
        self.settings_fox_list.reset()
        self.settings_fox_list.addItems(items)
        self._settings_mark_selected_fox()

    def _settings_mark_selected_fox(self):
        """Flag whichever tile matches the live accent, and park the grid's
        cursor on it so opening the page lands on the current choice rather
        than on Tofa Fox.

        Matches on the resolved accent hex, which may be a custom colour that
        is not any preset -- in that case nothing is flagged, which is honest:
        none of these 14 IS the current accent. (The LOGO still snaps to the
        nearest, because there are only 14 rasters; that is theme.default_logo
        's problem, not this grid's.)"""
        current = theme.current_accent_hex()
        selected_index = None
        for idx, (_name, hex_value, _logo) in enumerate(theme.PRESETS):
            li = self.settings_fox_list.getListItem(idx)
            match = hex_value.upper() == current
            li.setProperty("selected", "1" if match else "")
            if match:
                selected_index = idx
        if selected_index is not None:
            self.settings_fox_list.selectItem(selected_index)

    def _settings_fox_clicked(self):
        """Apply the picked accent: write it, then re-theme this window.

        Written to the server rather than to the local Kodi setting, because
        the account's own `accent_color` preference is the source of truth and
        every other tofa client reads the same key (see windows/theme.py). The
        local setting stays what it always was -- the fallback for when the
        server cannot be reached.

        Re-theming is a property refresh, not a reload: every accented control
        in the window reads $INFO[Window.Property(accent_color)] at draw time,
        so setting the properties repaints the whole UI, nav bar included."""
        item = self.settings_fox_list.getSelectedItem()
        if item is None:
            return
        hex_value = item.dataSource
        client = self._get_client()
        if client is None:
            cardoptions.alert("Appearance",
                              "Can't reach your server, so the accent was not saved.",
                              error=True)
            return
        try:
            client.update_preferences({"accent_color": "#" + hex_value.lower()})
        except http.ApiError as exc:
            log.warning("settings: accent write failed: {0}".format(exc))
            cardoptions.alert("Appearance", exc.message, error=True)
            return
        # Mirror it into the LOCAL setting too. That setting is the fallback
        # for when the server cannot be reached (see windows/theme.py), and it
        # used to be edited by hand in Kodi's own settings dialog. Keeping it
        # in step with the account here means it is always the right fallback
        # and never needs its own row -- which is what let the native dialog
        # go entirely.
        try:
            kodigui.ADDON.setSettingString("accent_color", hex_value)
        except Exception:
            pass
        theme.reset_cache()
        self._preferences = None
        self._settings_apply_theme()
        self._settings_mark_selected_fox()
        # The sidebar's Appearance summary names the current fox.
        self._settings_refresh_appearance_summary()

    def _settings_apply_theme(self):
        """Re-read every accent-derived Window property. Shared by the fox
        picker, the profile switch and the re-pair after sign-out, all three
        of which can change which accent is live."""
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("accent_pill_fill", theme.accent_with_alpha("3D"))
        self.setProperty("settings_row_wash",
                         theme.accent_with_alpha(T.SETTINGS_ROW_FOCUS_ALPHA))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("logo_file", theme.default_logo())

    def _settings_fox_name(self) -> str:
        """"Indigo Fox" for the live accent, or "" when it is not one of the
        14 presets. Read from the resolved accent rather than from whatever
        was last clicked, so a value the server normalised still reads true."""
        current = theme.current_accent_hex()
        name = next((n for n, h, _l in theme.PRESETS if h.upper() == current), "")
        return "{0} Fox".format(name) if name else ""

    def _settings_appearance_summary(self) -> str:
        """The chosen fox, plus a reminder that this page also holds the
        Home Screen editor -- which is otherwise unfindable from the sidebar,
        the row names neither."""
        return "{0} & Home Screen".format(self._settings_fox_name() or "Custom")

    def _settings_refresh_appearance_summary(self):
        """Re-label the Appearance sidebar row after the accent changes.
        _settings_load() sets the same string on first load."""
        summary = self._settings_appearance_summary()
        for idx, page in enumerate(settings_pages.PAGES):
            if page.key == "appearance":
                self.settings_nav_list.getListItem(idx).setProperty("summary", summary)
                return

    # --- Appearance: MEDIA CARDS ---------------------------------------
    #
    # Which tofa score a poster shows, and whether a show poster carries its
    # remaining-episode count. Both are real preferences the add-on ALREADY
    # honours when drawing cards (theme.card_rating_text reads the first two);
    # until now there was no way to change them from the TV.
    #
    # "Off" is not a third value of preferred_card_rating -- it is
    # show_card_ratings=False. So the segmented control spans two keys, which
    # is why it is written as one dict rather than two calls.
    SETTINGS_RATING_SEGMENTS = (
        ("Audience", {"show_card_ratings": True, "preferred_card_rating": "rt_audience"}),
        ("Critics", {"show_card_ratings": True, "preferred_card_rating": "rt"}),
        ("Off", {"show_card_ratings": False}),
    )

    #: Title and one-line summary per segmented row, in the app's wording.
    SEGMENTED_TEXT = {
        "rating":  ("Rating badge", "Which score appears on posters"),
        "quality": ("Streaming quality", "Auto adapts to your connection"),
        "nextup":  ("Play the next episode", "What happens as an episode ends"),
    }

    def _settings_segmented_options(self, key: str):
        """(label, value) for one segmented row, in display order.

        Normalises three different source shapes: the rating segments carry
        a preference PATCH rather than a scalar, and SEGMENT_ACTIONS /
        AUTO_PLAY_NEXT_ACTIONS are (value, label) where the other two are
        (label, value). Getting that pair backwards writes the label to the
        server, which it rejects with a 400 -- so it is normalised once here
        rather than at four call sites.
        """
        if key == "rating":
            return list(self.SETTINGS_RATING_SEGMENTS)
        if key == "quality":
            return list(self.SETTINGS_QUALITY_SEGMENTS)
        if key == "nextup":
            return [(l, v) for v, l in settings_options.AUTO_PLAY_NEXT_ACTIONS]
        return [(l, v) for v, l in settings_options.SEGMENT_ACTIONS]

    def _settings_segmented_active(self, key: str) -> int:
        """Which option is currently selected, as an index."""
        if key == "rating":
            return self._settings_rating_index(self._ensure_preferences())
        playback = self._settings_playback()
        if key == "quality":
            return self._settings_quality_index(playback)
        values = [v for _l, v in self._settings_segmented_options(key)]
        if key == "nextup":
            current = str(playback.get("auto_play_next") or "").lower()
        else:
            current = (playback.get("segment_actions") or {}).get(key, "ask")
        try:
            return values.index(current)
        except ValueError:
            # An unset or unknown value reads as the documented default:
            # "auto" for next-up, "ask" for a skip segment.
            return 0 if key == "nextup" else values.index("ask")

    def _settings_fill_segmented(self):
        """Window properties for all eight segmented rows.

        Window rather than ListItem properties because these rows are groups
        of real buttons now, not one-item lists -- see
        fragments.settings_segmented_group.
        """
        hints = dict(self.SEGMENTED_TEXT)
        for key, label, hint in settings_options.SEGMENT_ROWS:
            hints[key] = (label, hint)
        for key, _gid, _sids, prop in settings_options.SEGMENTED_GROUPS:
            title, summary = hints.get(key, (key.title(), ""))
            self.setProperty(prop + "_title", title)
            self.setProperty(prop + "_summary", summary)
            active = self._settings_segmented_active(key)
            for idx, (seg_label, _value) in enumerate(
                    self._settings_segmented_options(key)):
                self.setProperty("{0}_seg{1}".format(prop, idx), seg_label)
                self.setProperty("{0}_seg{1}_on".format(prop, idx),
                                 "1" if idx == active else "")

    def _settings_segmented_pressed(self, control_id: int):
        """Pick the option that was pressed. No cycling: each option is its
        own control now, so the viewer chooses directly, which is what the
        reference app does and what makes a three-option row usable."""
        found = settings_options.SEGMENTED_BY_ID.get(control_id)
        if not found:
            return
        key, index = found
        options = self._settings_segmented_options(key)
        if not (0 <= index < len(options)):
            return
        _label, value = options[index]
        if key == "rating":
            self._settings_write(value)          # a preference patch
        elif key == "quality":
            self._settings_write({"playback": {"default_quality": value}})
        elif key == "nextup":
            self._settings_write({"playback": {"auto_play_next": value}})
        else:
            actions = dict(self._settings_playback().get("segment_actions") or {})
            actions[key] = value
            self._settings_write({"playback": {"segment_actions": actions}})
        self._settings_fill_segmented()

    def _settings_wire_segmented(self):
        """Left/Right between a row's options, Left off the first one back to
        the sidebar. Python, not XML: these buttons are grandchildren of a
        grouplist, whose AddControl overrides its children's up/down and
        leaves grandchildren resolving to nothing."""
        try:
            nav = self.getControl(self.SETTINGS_NAV_ID)
        except Exception:                                       # noqa: BLE001
            return
        rows: dict = {}
        for _key, _gid, sids, _prop in settings_options.SEGMENTED_GROUPS:
            try:
                btns = [self.getControl(i) for i in sids]
            except Exception:                                   # noqa: BLE001
                continue
            for i, btn in enumerate(btns):
                btn.controlLeft(btns[i - 1] if i else nav)
                if i < len(btns) - 1:
                    btn.controlRight(btns[i + 1])
            rows[_key] = btns

        # UP/DOWN as well as left/right. The pills are grandchildren of the
        # appearance/playback grouplist, so their vertical navigation
        # resolves to nothing and Kodi wraps them internally -- Down simply
        # did nothing. Same trap the home-row editor hit.
        #
        # Keep the column where the next row is wide enough, clamped
        # otherwise, so moving down a page of pills does not always dump
        # focus on the first one.
        def _join(above, below):
            if not (above and below):
                return
            for i, btn in enumerate(above):
                btn.controlDown(below[min(i, len(below) - 1)])
            for i, btn in enumerate(below):
                btn.controlUp(above[min(i, len(above) - 1)])

        order = [k for k, _g, _s, _p in settings_options.SEGMENTED_GROUPS]
        playback_chain = [k for k in order if k not in ("rating",)]
        for a, b in zip(playback_chain, playback_chain[1:]):
            _join(rows.get(a), rows.get(b))

        # The rating row sits between "Add a row" and "Episodes remaining"
        # on Appearance, not in the playback chain.
        try:
            add_row = self.getControl(self.SETTINGS_ADD_ROW_ID)
            episodes = self.getControl(self.SETTINGS_EPISODES_ID)
        except Exception:                                       # noqa: BLE001
            return
        for btn in rows.get("rating", []):
            btn.controlUp(add_row)
            btn.controlDown(episodes)
        if rows.get("rating"):
            add_row.controlDown(rows["rating"][0])
            episodes.controlUp(rows["rating"][0])

    def _settings_rating_index(self, prefs: dict) -> int:
        if not prefs.get("show_card_ratings", True):
            return 2
        return 1 if prefs.get("preferred_card_rating") == "rt" else 0

    def _settings_fill_media_cards(self):
        """Build both MEDIA CARDS rows from the profile's live preferences."""
        prefs = self._ensure_preferences()

        self._settings_fill_segmented()

        episodes = kodigui.ManagedListItem(label="Episodes remaining")
        episodes.setProperty("summary", "Show how many episodes you have left on show posters")
        episodes.setProperty(
            "checked", "1" if prefs.get("show_unwatched_count", True) else "")
        self.settings_episodes_list.reset()
        self.settings_episodes_list.addItems([episodes])

    def _settings_episodes_clicked(self):
        prefs = self._ensure_preferences()
        now = bool(prefs.get("show_unwatched_count", True))
        self._settings_write({"show_unwatched_count": not now})

    def _settings_write(self, patch: dict):
        """Send a preference patch, then re-read and re-render.

        Re-reads rather than assuming the write landed as sent: the server
        merges, and may normalise. Every screen that caches preferences is
        dropped too, so Home and Browse pick the change up next time they are
        shown rather than keeping the old cards."""
        client = self._get_client()
        if client is None:
            cardoptions.alert("Settings", "Can't reach your server, so that was not saved.",
                              error=True)
            return
        try:
            client.update_preferences(patch)
        except http.ApiError as exc:
            log.warning("settings: write failed: {0}".format(exc))
            cardoptions.alert("Settings", exc.message, error=True)
            return
        self._preferences = None
        self._settings_fill_media_cards()
        # Home and Browse drew their cards with the old values.
        self._loaded_sections = {"settings"}

    def _settings_account_identity(self) -> dict:
        """The tofa ACCOUNT behind this pairing (email, avatar), or {}.

        Cached for the window's life: it is a cloud round trip through a
        freshly minted 15-minute token, and nothing on this page changes it.

        {} is an ORDINARY answer, not a failure to report: an install paired
        before the cloud refresh token was persisted cannot mint a cloud
        token at all, and every caller here falls back to what the media
        server does know (the username). Only a genuine transport failure is
        logged."""
        if self._settings_identity is not None:
            return self._settings_identity
        self._settings_identity = {}
        try:
            from .. import signin
            tok = auth.load()
            session = http.new_session()
            cloud_token = signin._cloud_access_token(session, tok)
            if cloud_token:
                me = cloud.get_account(session, tok.connect_url, cloud_token) or {}
                if isinstance(me, dict):
                    self._settings_identity = me
                    log.debug("settings: cloud account keys: {0}".format(
                        sorted(me.keys())))
        except (auth.NotSignedIn, auth.TokenLoadError):
            pass
        except http.ApiError as exc:
            log.warning("settings: cloud account lookup failed: {0}".format(exc))
        except Exception as exc:                             # noqa: BLE001
            log.warning("settings: cloud account lookup error: {0}".format(exc))
        return self._settings_identity

    def _settings_wire_account_nav(self):
        """The Account pane's rows are GRANDCHILDREN of its grouplist too, so
        they need the same Python wiring as Appearance's -- see
        _settings_wire_appearance_nav for the mechanism and the measurement.

        Symptom without it, measured 2026-08-13: Down on Switch Profile does
        nothing at all. The list is not in the grouplist's chain, its ondown
        resolves to nothing, and Kodi wraps it internally onto its own single
        item rather than navigating away."""
        try:
            profile = self.getControl(self.SETTINGS_SWITCH_PROFILE_ID)
            server = self.getControl(self.SETTINGS_SWITCH_SERVER_ID)
            out = self.getControl(self.SETTINGS_SIGN_OUT_ID)
            direct = self.getControl(self.SETTINGS_DIRECT_ONLY_ID)
        except Exception:                                    # noqa: BLE001
            log.warning("settings: could not wire the Account pane's nav")
            return
        profile.controlDown(server)
        server.controlUp(profile)
        server.controlDown(out)
        out.controlUp(server)
        out.controlDown(direct)
        direct.controlUp(out)

    def _settings_wire_appearance_nav(self):
        """Re-assert the two MEDIA CARDS rows' up/down from Python.

        The grouplist chains its DIRECT children and uses its own onup/ondown
        at the two ends. Everything focusable on this page is a GRANDCHILD --
        the fox panel and these two lists all sit inside a group -- so none of
        them are in that chain, and Kodi's own rule bites instead: a container
        whose ondown resolves to nothing wraps internally rather than
        navigating away (`wrapAround = !action.HasActionsMeetingCondition()`).

        Measured, not assumed: before this, Down on the last fox row jumped
        back to Tofa Fox instead of leaving the grid, and MEDIA CARDS was
        unreachable. See project_kodi_grouplist_scroll_limit, which documents
        the same surprise on Detail's Cast & Crew.

        Wiring it from Python survives the override that XML does not."""
        try:
            foxes = self.getControl(self.SETTINGS_FOX_ID)
            # NOT SETTINGS_RATING_ID: the rating row is a group of pills now,
            # and getControl on the deleted list RAISED -- aborting this whole
            # try block, so even foxes->spotlight never got wired and Down
            # from the fox grid did nothing. Reported 2026-08-27.
            episodes = self.getControl(self.SETTINGS_EPISODES_ID)
            spotlight = self.getControl(self.SETTINGS_SPOTLIGHT_ID)
            foxes.controlDown(spotlight)
            spotlight.controlUp(foxes)
            # spotlight <-> first editor row and last editor row <-> the
            # add tile are joined by _settings_wire_home_rows, which is the
            # only place that knows how many rows the account actually has.
            # add row <-> rating pills <-> episodes is joined by
            # _settings_wire_segmented, which is the only place that knows
            # which pills a segmented row has.
            region = self.getControl(self.SETTINGS_REGION_ID)
            episodes.controlDown(region)
            region.controlUp(episodes)
        except Exception:
            pass
        # Privacy & About needs no cross-group hop: its PRIVACY group is a
        # read-only note card with nothing focusable in it, so Open Source
        # Notices is the only focusable row on that page. It DID need one
        # while the group held a telemetry switch -- 8610 and 8620 are
        # grandchildren of different children, and Down on the switch reached
        # nothing until the hop was wired from Python.
        #
        # Playback & Video, Audio & Subtitles and This Device are each ONE
        # group, so their rows are siblings and the XML onup/ondown stands.

    # --- Appearance: HOME SCREEN ---------------------------------------
    #
    # The row editor. `home_screen` is SHALLOW-merged by the server (only
    # `playback` is deep), so every write here has to send the whole object --
    # sending {"home_screen": {"rows": [...]}} alone would drop show_hero.
    # See api.update_preferences().

    def _settings_home_screen(self) -> dict:
        return dict(self._ensure_preferences().get("home_screen") or {})

    def _settings_fill_home_screen(self):
        home = self._settings_home_screen()

        # The note under the editor. From Python because $LOCALIZE in a
        # window XML reads the ACTIVE SKIN's strings, not ours -- see the
        # comment on the label in main.xml.tpl.
        self.setProperty("home_rows_note", _(31122))

        spotlight = kodigui.ManagedListItem(label="Featured spotlight")
        spotlight.setProperty("summary", "Show the featured banner above your home rows")
        spotlight.setProperty("checked", "1" if home.get("show_hero", True) else "")
        self.settings_spotlight_list.reset()
        self.settings_spotlight_list.addItems([spotlight])

        # Window properties, one set per SLOT: these rows are real controls
        # now, not list items, so there is no ListItem to read from. A slot
        # with an empty title hides itself, which also removes it from the
        # grouplist's navigation chain.
        shown = []
        for index, row in enumerate(home.get("rows") or []):
            title = home_rows.row_title(row, _)
            if not title:
                # Same rule _home_load() follows: a row type this add-on does
                # not understand is skipped, never guessed at. Editing a list
                # we cannot fully name would reorder rows blind.
                log.debug("settings: skipping unnameable home row {0}".format(row))
                continue
            shown.append((index, title, row.get("enabled", True),
                          row.get("type"), home_rows.row_removable(row)))

        self._settings_home_slots = [i for i, _t, _e, _k, _r in shown]
        # Say so LOUDLY rather than editing a list the viewer cannot see all
        # of. MAX_HOME_ROWS sat at 9 while tofa's own default grew to 10, and
        # the tenth row simply was not there -- no error, no gap, just a
        # shorter list than the account holds.
        if len(shown) > home_rows.MAX_HOME_ROWS:
            log.warning(
                "settings: account has {0} home rows but only {1} slots exist "
                "-- raise home_rows.MAX_HOME_ROWS".format(
                    len(shown), home_rows.MAX_HOME_ROWS))
        for slot in range(home_rows.MAX_HOME_ROWS):
            prefix = "homerow_{0}".format(slot)
            if slot >= len(shown):
                self.setProperty(prefix + "_title", "")
                self.setProperty(prefix + "_can_up", "")
                self.setProperty(prefix + "_can_down", "")
                self.setProperty(prefix + "_checked", "")
                self.setProperty(prefix + "_can_remove", "")
                self.setProperty(prefix + "_sub", "")
                continue
            _index, title, enabled, kind, removable = shown[slot]
            self.setProperty(prefix + "_title", title)
            # The TEN rows an account starts with can only be switched off,
            # never taken off the list -- every tofa app enforces that, and
            # nothing in the row data marks them, so home_rows carries the
            # list. Everything else the viewer put there can go.
            #
            # This is NOT "is it a builtin": two of the ten are typed
            # `discovery`, indistinguishable in the payload from a Discover
            # row added by hand.
            self.setProperty(prefix + "_can_remove", "1" if removable else "")
            # The subtitle rides with the remove button, not with the row
            # TYPE. Checked on a 2x crop of the reference: its two default
            # trending rows are typed `discovery` and carry no subtitle,
            # while the trending row the viewer added carries "Discover".
            # So the line is not "what kind of row is this" -- it is why
            # this one can be taken off the list, which is only worth
            # saying about a row that can.
            self.setProperty(prefix + "_sub", {
                "discovery": "Discover", "genre": "Genre",
            }.get(kind, "") if removable else "")
            self.setProperty(prefix + "_checked", "1" if enabled else "")
            # The app dims the first row's up arrow and the last row's down.
            # <enable> is bound to these, and Kodi SKIPS a disabled control
            # when navigating, so the ends behave as well as look right.
            self.setProperty(prefix + "_can_up", "" if slot == 0 else "1")
            self.setProperty(prefix + "_can_down",
                             "" if slot == len(shown) - 1 else "1")
        self._settings_wire_home_rows(
            len(shown), [r for _i, _t, _e, _k, r in shown])

    def _settings_spotlight_clicked(self):
        home = self._settings_home_screen()
        home["show_hero"] = not home.get("show_hero", True)
        self._settings_write_home(home)

    def _settings_wire_home_rows(self, count: int, removable=None):
        """Chain the editor's buttons by hand, in both axes.

        Two reasons XML cannot do this. CGUIControlGroupList::AddControl
        OVERRIDES its direct children's up/down, and these buttons are
        GRANDCHILDREN of the appearance grouplist, which is precisely the
        case that resolves to nothing and makes Kodi wrap internally instead
        of navigating away (reference_kodi_grouplist_children). And the last
        VISIBLE row is only known at runtime, since the account decides how
        many rows there are.

        Vertical moves keep the COLUMN, the way the app does: up from the
        middle button lands on the middle button above, not back at the
        first control of the row.
        """
        try:
            spotlight = self.getControl(self.SETTINGS_SPOTLIGHT_ID)
            add_row = self.getControl(self.SETTINGS_ADD_ROW_ID)
            cols = [[self.getControl(cid)
                     for cid in home_rows.HOME_ROW_EDIT_IDS[slot]]
                    for slot in range(count)]
        except Exception as exc:                                # noqa: BLE001
            # Before onInit has built the controls, or a slot id that does
            # not exist: nothing to wire, and this must never break the pane.
            log.debug("settings: home row wiring skipped ({0!r})".format(exc))
            return

        removable = list(removable or [False] * count)

        def usable(slot):
            """Columns that can actually take focus on this row, LEFT TO
            RIGHT as they are drawn.

            Two separate things are being respected here. A disabled control
            cannot take focus, so wiring INTO one is the same bug as aiming
            focus at it -- the move silently does nothing. And the order is
            the SCREEN order, not the order the ids happen to run in: remove
            sits between the down arrow and the switch on screen, while its
            id is the last of the four. Walking the id order instead sent
            Left from the switch back to the UP ARROW, two columns away and
            past the button it was meant to reach -- and since a press there
            moves the row, that mis-wire did not just misfocus, it acted."""
            out = []
            if slot > 0:
                out.append(home_rows.EDIT_UP)
            if slot < count - 1:
                out.append(home_rows.EDIT_DOWN)
            if slot < len(removable) and removable[slot]:
                out.append(home_rows.EDIT_REMOVE)
            out.append(home_rows.EDIT_TOGGLE)
            return out

        for slot, row in enumerate(cols):
            live = usable(slot)
            for n, col in enumerate(live):
                btn = row[col]
                if n:
                    btn.controlLeft(row[live[n - 1]])
                else:
                    # Leftmost column keeps the pane's rule: Left is "back
                    # to the sidebar".
                    btn.controlLeft(self.getControl(self.SETTINGS_NAV_ID))
                if n < len(live) - 1:
                    btn.controlRight(row[live[n + 1]])
                # Vertically, keep the column when the neighbouring row also
                # has it; otherwise fall to its toggle, which every row has.
                for delta, fallback in ((-1, spotlight), (1, add_row)):
                    near = slot + delta
                    if 0 <= near < len(cols):
                        target = row_at = cols[near]
                        pick = (col if col in usable(near)
                                else home_rows.EDIT_TOGGLE)
                        target = row_at[pick]
                    else:
                        target = fallback
                    (btn.controlUp if delta < 0 else btn.controlDown)(target)
        if cols:
            # The block's own ends, so the pane above and below still joins
            # up -- landing on a control that can actually take focus. The
            # FIRST row's up arrow is disabled by design, so aiming Down
            # from the spotlight at cols[0][0] pointed at a dead control and
            # Down did nothing. Same mistake as the focus-follow bug, one
            # layer up. Mirrored for the last row's down arrow.
            first = (cols[0][home_rows.EDIT_DOWN] if len(cols) > 1
                     else cols[0][home_rows.EDIT_TOGGLE])
            last = (cols[-1][home_rows.EDIT_UP] if len(cols) > 1
                    else cols[-1][home_rows.EDIT_TOGGLE])
            spotlight.controlDown(first)
            add_row.controlUp(last)

    #: control id -> (slot, what pressing it does)
    def _settings_home_row_button(self, control_id: int):
        for slot, ids in enumerate(home_rows.HOME_ROW_EDIT_IDS):
            for action, cid in zip(("up", "down", "toggle", "remove"), ids):
                if cid == control_id:
                    return slot, action
        return None, None

    def _settings_home_row_pressed(self, control_id: int):
        """Move a row, or turn it off, straight from the row itself.

        No action panel any more: the three choices are three real buttons,
        which is what the reference app shows and what a viewer expects to
        find on the row rather than one Select deeper.
        """
        slot, action = self._settings_home_row_button(control_id)
        if slot is None:
            return
        slots = getattr(self, "_settings_home_slots", [])
        if not (0 <= slot < len(slots)):
            return
        index = slots[slot]
        home = self._settings_home_screen()
        rows = list(home.get("rows") or [])
        if not (0 <= index < len(rows)):
            return

        if action == "up" and slot > 0:
            other = slots[slot - 1]
            rows[other], rows[index] = rows[index], rows[other]
        elif action == "down" and slot < len(slots) - 1:
            other = slots[slot + 1]
            rows[other], rows[index] = rows[index], rows[other]
        elif action == "remove":
            del rows[index]
        elif action == "toggle":
            rows[index] = dict(rows[index], enabled=not rows[index].get("enabled", True))
        else:
            return
        home["rows"] = rows
        self._settings_write_home(home)
        # Follow the row, not the position: after a move the viewer is still
        # thinking about the row they just moved, and leaving focus behind
        # means the next press moves a DIFFERENT row.
        if action == "remove":
            # The row is gone. Land on whatever now occupies its slot, or the
            # one above if it was the last -- never on the vanished row.
            landed = min(slot, len(slots) - 2)
            if landed < 0:
                return
            try:
                self.setFocusId(
                    home_rows.HOME_ROW_EDIT_IDS[landed][home_rows.EDIT_TOGGLE])
            except Exception:                                   # noqa: BLE001
                pass
        elif action in ("up", "down"):
            landed = slot - 1 if action == "up" else slot + 1
            landed = max(0, min(landed, len(slots) - 1))
            # The arrow the viewer just pressed may be DISABLED at the row's
            # new position -- moving row 2 up makes it row 1, whose up arrow
            # is dimmed by design, and the mirror case for the last row's
            # down arrow. setFocusId on a disabled control does nothing, so
            # focus was left stranded on the row that had moved away and the
            # next Up escaped to the nav bar. Reported 2026-08-27.
            #
            # Follow the ROW to the nearest control that can actually hold
            # focus: the pressed column first, then the other arrow, then the
            # switch, which is never disabled.
            last = len(slots) - 1
            wanted = 0 if action == "up" else 1
            order = [wanted, 1 - wanted, 2]
            for col in order:
                if col == 0 and landed == 0:
                    continue        # up arrow is dimmed at the top
                if col == 1 and landed == last:
                    continue        # down arrow is dimmed at the bottom
                try:
                    self.setFocusId(home_rows.HOME_ROW_EDIT_IDS[landed][col])
                except Exception:                               # noqa: BLE001
                    continue
                break

    def _settings_write_home(self, home: dict):
        """Send the WHOLE home_screen object, for the shallow-merge reason in
        this section's header, then re-fill from what came back."""
        self._settings_write({"home_screen": home})
        self._settings_fill_home_screen()
        self._settings_fill_add_rows()

    # --- Appearance: adding a row --------------------------------------

    def _settings_fill_add_rows(self):
        """The one "add a row" action. A static label; what it can offer is
        only known once the picker is opened, which is deliberate -- the
        shelf and genre lists are both a network call and this page must
        draw without one."""
        add = kodigui.ManagedListItem(label="Add a row")
        # Not "a row you removed": the Home rows group offers Recently
        # Released to anyone who does not have it, including a profile that
        # predates the row and removed nothing. "not already here" is true
        # of all three groups and says why the list is shorter than the
        # Discover screen.
        add.setProperty("summary",
                        "Any Discover list, genre, or Home row not already here")
        self.settings_add_row_list.reset()
        self.settings_add_row_list.addItems([add])

    def _settings_add_row(self):
        """ONE picker over three groups -- Home rows, Discover, Genres --
        rather than a button per kind.

        That is the reference apps' shape: the web app renders a single
        select whose options are grouped under exactly these three labels,
        and the tvOS app the same. What we had instead was two buttons, and
        a Discover list annotated with the raw `kind` the server tags a
        shelf with ("Now", "Availability"), which appears in no tofa app --
        those are our Discover TAB names, not a category anyone else shows.

        Genres come from the library, Discover shelves from the server, and
        the builtin group from what this add-on knows how to draw. Anything
        already on Home is left out of all three.
        """
        # Lazy, same as every other playoptions caller here: it pulls in a
        # second WindowXML and nothing on this page needs it until a picker
        # is actually opened.
        from . import playoptions
        client = self._get_client()
        if client is None:
            cardoptions.alert("Home Screen", "Can't reach your server.", error=True)
            return

        home = self._settings_home_screen()
        rows = list(home.get("rows") or [])
        present = {r.get("id") for r in rows}
        taken_lists = {r.get("discoveryList") for r in rows if r.get("type") == "discovery"}
        taken_genres = {r.get("genre") for r in rows if r.get("type") == "genre"}

        # Builtins first: no network, and it is the group the reference puts
        # at the top.
        builtins = [rid for rid in home_rows.ADDABLE_BUILTIN_IDS
                    if rid not in present]

        # A shelf list or a genre list that fails is not fatal -- the other
        # groups are still worth offering, so each is fetched on its own and
        # an error simply empties that group.
        try:
            shelves = (client.discovery_page() or {}).get("shelves") or []
        except http.ApiError as exc:
            log.warning("settings: discover shelves unavailable ({0})".format(exc.message))
            shelves = []
        # Keyed off `key`, never `list_type`: the latter is null on every
        # shelf added after the original seven (see api.discovery_page). The
        # row entry mirrors what the web app writes -- id "discover-<key>" --
        # so a row added here and one added on the web are the same object.
        offered_shelves = [s for s in shelves
                           if s.get("key") and s["key"] not in taken_lists]

        try:
            genres = client.genres() or []
        except http.ApiError as exc:
            log.warning("settings: genres unavailable ({0})".format(exc.message))
            genres = []
        offered_genres = [g for g in genres
                          if isinstance(g, str) and g and g not in taken_genres]

        groups = [
            {"key": "builtin", "title": "Home rows",
             "options": [{"label": _(home_rows.BUILTIN_ROW_LABELS[rid]),
                          "detail": ""} for rid in builtins]},
            {"key": "discovery", "title": "Discover",
             "options": [{"label": s.get("title") or s["key"], "detail": ""}
                         for s in offered_shelves]},
            {"key": "genre", "title": "Genres",
             "options": [{"label": g, "detail": ""} for g in offered_genres]},
        ]
        if not any(g["options"] for g in groups):
            cardoptions.alert("Home Screen",
                              "Every row your server offers is already on Home.")
            return

        picked = playoptions.show_grouped_choice(
            title="Add a row", subtitle="", groups=groups)
        if picked is None:
            return
        kind, index = picked

        if kind == "builtin":
            row_id = builtins[index]
            rows.append({"type": "builtin", "id": row_id, "enabled": True})
        elif kind == "discovery":
            key = offered_shelves[index]["key"]
            rows.append({"type": "discovery", "discoveryList": key,
                         "id": "discover-{0}".format(key), "enabled": True})
        else:
            # /media/genres returns NAMES, and `/media`'s genre filter takes
            # the name string directly, so the name is the whole key -- there
            # is no id to look up. The row's own `id` is a slug of it, purely
            # so the entry has a stable handle for the web app's list
            # rendering; nothing on this client reads it (see
            # home_rows.row_title, which names a genre row from `genre`).
            genre = offered_genres[index]
            rows.append({"type": "genre", "genre": genre,
                         "id": "genre-{0}".format(genre.lower().replace(" ", "-")),
                         "enabled": True})
        home["rows"] = rows
        self._settings_write_home(home)

    def _settings_playback(self) -> dict:
        return dict(self._ensure_preferences().get("playback") or {})

    def _settings_fill_playback(self):
        playback = self._settings_playback()

        # The API's contract: "A missing key means `auto` ... every client
        # must apply that default", so an untouched profile shows Auto
        self._settings_fill_segmented()

    def _settings_fill_audio(self):
        """Two sections, worded as the web and desktop apps word them --
        scraped from the running server's own bundle rather than paraphrased,
        so the same setting reads the same sentence on every screen."""
        playback = self._settings_playback()
        for mlist, prop, label, summary, pref_key, slot in (
            (self.settings_audiolang_list, "settings_audio_lang",
             "Primary language", "First audio track preference",
             "preferred_audio_languages", 0),
            (self.settings_audiolang2_list, "settings_audio_lang2",
             "Secondary language", "Primary is tried first, then secondary.",
             "preferred_audio_languages", 1),
            (self.settings_sublang_list, "settings_sub_lang",
             "Primary language", "Set to None if you don't want subtitles pre-selected.",
             "preferred_subtitle_languages", 0),
            (self.settings_sublang2_list, "settings_sub_lang2",
             "Secondary language", "Used when subtitles are enabled by default.",
             "preferred_subtitle_languages", 1),
        ):
            li = kodigui.ManagedListItem(label=label)
            li.setProperty("summary", summary)
            mlist.reset()
            mlist.addItems([li])
            self.setProperty(prop, self._settings_language_label(
                playback.get(pref_key), slot))

        always = kodigui.ManagedListItem(label="Always show subtitles")
        always.setProperty(
            "summary", "Turn subtitles on automatically when playback starts")
        always.setProperty(
            "checked", "1" if playback.get("always_enable_subtitles") else "")
        self.settings_alwayssubs_list.reset()
        self.settings_alwayssubs_list.addItems([always])

    @staticmethod
    def _settings_language_label(codes, slot: int = 0) -> str:
        """One slot of the ordered preference list, named.

        "None" rather than "Off": it is the word the other clients' pickers
        use for the same empty choice, and this row now represents one entry
        of a chain instead of the whole setting."""
        if not isinstance(codes, list) or len(codes) <= slot:
            return "None"
        return settings_options.language_label(str(codes[slot]))

    def _settings_language_facet(self):
        """`[{value, count}]` of the languages this library holds audio in.

        Unscoped on purpose -- no `media_type`, no `library_id` -- because
        this is one household-wide preference, not a filter on the grid a
        viewer happens to be looking at.

        Fetched at most once per window and cached even when it FAILS (as
        `[]`), so a server that cannot answer costs one request rather than
        one per picker opening. The cost of being wrong is small in both
        directions: a stale list only misses a language added since Settings
        was opened, and an empty one falls back to the static list."""
        if self._settings_languages is None:
            self._settings_languages = []
            client = self._get_client()
            if client is not None:
                try:
                    facets = client.facets() or {}
                    self._settings_languages = list(facets.get("languages") or [])
                except http.ApiError as exc:
                    log.warning("settings: languages facet failed: {0}".format(exc))
        return self._settings_languages

    def _settings_language_clicked(self, pref_key: str, slot: int = 0):
        """Edit one slot, then rebuild the list from both.

        Empties are dropped rather than stored, so clearing the primary
        promotes the secondary instead of leaving a hole the matcher would
        have to skip -- the list is consumed strictly in order (see
        langcodes.first_by_language).

        The AUDIO primary offers no None, matching the other clients: there
        is always a first audio preference, and an empty list would mean the
        file's own track order decides, which is the behaviour this whole
        setting exists to override."""
        from . import playoptions
        current = list(self._settings_playback().get(pref_key) or [])
        audio = pref_key.startswith("preferred_audio")
        audio_primary = audio and slot == 0
        options = settings_options.language_options(
            self._settings_language_facet(), subtitles=not audio)

        rows = [] if audio_primary else [{"label": "None", "detail": ""}]
        offset = len(rows)
        rows += [{"label": name, "detail": code.upper()}
                 for code, name in options]
        selected = 0
        if len(current) > slot:
            # langcodes.same, not ==: a preference written by the web app can
            # be the other spelling of the language this row offers, and an
            # exact compare would show nothing selected on a setting that IS
            # set. See langcodes.terminological.
            for idx, (code, _n) in enumerate(options):
                if langcodes.same(code, current[slot]):
                    selected = idx + offset
                    break
        index = playoptions.show_choice(
            title=("Audio" if audio else "Subtitles"),
            subtitle=("Primary language" if slot == 0 else "Secondary language"),
            rows=rows, selected_idx=selected)
        if index is None:
            return
        chosen = None if index < offset else options[index - offset][0]
        slots = [current[i] if len(current) > i else None for i in range(2)]
        slots[slot] = chosen
        # A language cannot usefully appear twice; picking the primary again
        # for the secondary would make the fallback a no-op.
        value = []
        for code in slots:
            if code and code not in value:
                value.append(code)
        self._settings_write({"playback": {pref_key: value}})
        self._settings_fill_audio()

    def _settings_alwayssubs_clicked(self):
        now = bool(self._settings_playback().get("always_enable_subtitles"))
        self._settings_write({"playback": {"always_enable_subtitles": not now}})
        self._settings_fill_audio()

    def _settings_quality_index(self, playback: dict) -> int:
        """Which segment is lit. An unset value reads as Auto, which is what
        the server itself defaults to."""
        current = (playback.get("default_quality") or "auto")
        for idx, (_label, value) in enumerate(self.SETTINGS_QUALITY_SEGMENTS):
            if value == current:
                return idx
        return 0

    def _settings_fill_quality(self):
        self._settings_fill_segmented()

    def _settings_direct_only_clicked(self):
        """Flip CONNECTION's toggle. Device-local, so no server round trip --
        and no _settings_write, which would report a failure the server was
        never asked about."""
        auth.set_direct_only(not auth.direct_only())
        self._settings_fill_direct_only()

    def _settings_fill_direct_only(self):
        item = self.settings_direct_list.getListItem(0)
        if item is not None:
            item.setProperty("checked", "1" if auth.direct_only() else "")

    def _settings_fill_connection(self, client):
        """CONNECTION's read-only note: how THIS box is reaching the server.

        Read off the client's LIVE base_url rather than the stored pairing:
        _request swaps base_url to the fallback on a successful retry, so by
        the time Settings loads this reflects the address actually in use.
        auth.is_relay_url answers for both the `<uuid>.connect.tofa.tv` relay
        host and the cloud proxy path. The web app shows the same warning as a
        banner; a 10-foot UI puts it here, next to the toggle that governs it,
        rather than over Home."""
        base = getattr(client, "base_url", "") if client else ""
        if base and auth.is_relay_url(base):
            body = ("Routed through tofa's relay, which can be slower. Forward "
                    "your server's port to connect directly.")
        elif base:
            body = "Connected directly to your server."
        else:
            body = ""
        self.setProperty("settings_connection_body", body)

    def _settings_fill_region(self):
        code = self._ensure_preferences().get("region") or ""
        li = kodigui.ManagedListItem(label="Availability region")
        li.setProperty("summary", "Used for release dates of titles not in your library yet")
        self.settings_region_list.reset()
        self.settings_region_list.addItems([li])
        self.setProperty("settings_region", settings_options.region_name(code) or "—")

    def _settings_region_clicked(self):
        from . import playoptions
        code = self._ensure_preferences().get("region") or ""
        selected = next((i for i, (c, _n) in enumerate(settings_options.REGIONS)
                         if c == code), 0)
        index = playoptions.show_choice(
            title="Availability region", subtitle="",
            rows=[{"label": name, "detail": c} for c, name in settings_options.REGIONS],
            selected_idx=selected)
        if index is None:
            return
        self._settings_write({"region": settings_options.REGIONS[index][0]})
        self._settings_fill_region()

    # --- Privacy & About, This Device -----------------------------------

    def _settings_fill_privacy(self):
        # Playback diagnostics is a NOTE, not a switch. It was a toggle on
        # `telemetry_enabled`, which was misleading twice over: this add-on
        # sends no quality metrics at all (audited -- every outbound call is
        # either the user's own media server carrying playback POSITION, or
        # cloud.py's five pairing/refresh calls), and the data the row was
        # named after is the SERVER's own diagnostics, which belong to
        # whoever runs it rather than to this client. Offering a switch for
        # something we neither send nor control was a promise we could not
        # keep, so the page explains it instead.
        self.setProperty(
            "settings_diagnostics_body",
            "This server records playback quality data (buffering, bitrate, "
            "and errors) so its owner can troubleshoot streaming issues. "
            "It stays on this server and is never sent to tofa.")

        licences = kodigui.ManagedListItem(label="Open Source Notices")
        licences.setProperty("summary", "Licences for the fonts and icons we bundle")
        licences.setProperty("icon_glyph", chr(icon_glyphs.INFO))
        self.settings_licences_list.reset()
        self.settings_licences_list.addItems([licences])

        self.setProperty("settings_version", kodigui.ADDON.getAddonInfo("version"))
        # Routed to THIS add-on's issue tracker, not tofa's support desk: a
        # bug in the Kodi client is not something they can act on, and it is
        # the kind of problem this screen gets reached for.
        #
        # It used to carry a second sentence sending account and server
        # trouble to accounts.tofa.tv/support. That ran past the rail's
        # three-line caption box and was CLIPPED, so it was not doing the
        # job it was there for. The routing is not lost: the issue form this
        # QR lands on carries the same hand-off as its own contact link
        # (.github/ISSUE_TEMPLATE/config.yml), where it is one tap on the
        # phone already in the viewer's hand rather than an address to copy
        # off a television.
        self.setProperty("settings_support_caption",
                         "Scan to report a problem with this add-on.")

    def _settings_licences_clicked(self):
        """The attribution the bundled licences require, not their full text.

        The full texts DO ship -- resources/skins/Main/fonts/OFL.txt and
        media/LUCIDE_LICENSE.txt -- which is what the SIL OFL and ISC actually
        oblige. What they also oblige is reproducing the copyright notices,
        and those are what this shows.

        Not the whole files: the alert's textbox does not scroll, so ninety
        lines of licence arrive clipped mid-sentence, which is worse than a
        clear pointer -- it looks like the notice itself is broken. Tried it;
        the OFL was cut inside its second copyright line.

        Copyright lines are READ FROM the files rather than restated here, so
        a font swap that updates OFL.txt updates this too."""
        notices = []
        for label, relative, keep in (
            ("SIL Open Font License 1.1", "skins/Main/fonts/OFL.txt", 5),
            ("ISC License", "skins/Main/media/LUCIDE_LICENSE.txt", 3),
        ):
            path = os.path.join(kodigui.ADDON.getAddonInfo("path"), "resources", relative)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    head = [line.strip() for line in handle.readlines()[:keep]]
            except OSError as exc:
                log.warning("settings: licence file missing: {0} ({1})".format(path, exc))
                continue
            holders = ", ".join(
                l.replace("Copyright (c) ", "\u00a9 ").replace("Copyright ", "\u00a9 ")
                for l in head if l.lower().startswith("copyright"))
            notices.append("{0} \u2014 {1}".format(label, holders) if holders else label)
        if not notices:
            cardoptions.alert("Open Source Notices",
                              "The bundled licence files could not be read.", error=True)
            return
        notices.append("Full licence texts ship with the add-on.")
        cardoptions.alert("Open Source Notices", "\n".join(notices))

    def _settings_fill_device(self):
        fonts = kodigui.ManagedListItem(label="Set up this device for tofa")
        fonts.setProperty(
            "summary", "Adds tofa's fonts to the active skin and raises Kodi's image quality limit")
        fonts.setProperty("icon_glyph", chr(icon_glyphs.REFRESH_CW))
        self.settings_fonts_list.reset()
        self.settings_fonts_list.addItems([fonts])
        try:
            self.setProperty("settings_device_id", auth.get_or_create_device_id())
        except Exception:
            self.setProperty("settings_device_id", "—")

        budget = kodigui.ManagedListItem(label="Artwork storage limit")
        # Short on purpose: a choice row gives its value label 400px on the
        # right, so a summary written to the full width truncates mid-word.
        budget.setProperty("summary", "Space artwork may use here")
        self.settings_artbudget_list.reset()
        self.settings_artbudget_list.addItems([budget])
        self.setProperty("settings_art_budget", self._settings_art_budget_label())

        clear = kodigui.ManagedListItem(label="Clear artwork cache")
        clear.setProperty(
            "summary", "Frees the space now. Artwork downloads again as you browse.")
        # CIRCLE_X, not DELETE: Lucide's `delete` is the BACKSPACE key glyph
        # (a tag with an x), which reads as "undo typing" next to a sentence
        # about removing files. No trash glyph is in the bundled subset and
        # adding one means regenerating the font and bumping FONT_SET_VERSION,
        # which would re-prompt every device for one icon.
        clear.setProperty("icon_glyph", chr(icon_glyphs.CIRCLE_X))
        self.settings_artclear_list.reset()
        self.settings_artclear_list.addItems([clear])

    def _settings_art_budget_label(self, mb: int | None = None) -> str:
        """The value shown on the row, named for `mb` or for what is stored.

        Callers that have JUST written the setting pass the value they wrote.
        Re-reading it there showed the OLD number on screen until the page was
        re-entered -- the write reaches settings.xml (verified) but a read
        taken immediately afterwards does not see it, so the row lied about a
        change the user had just made."""
        current = artcache.budget_bytes() // (1024 * 1024) if mb is None else mb
        return next((name for value, name in settings_options.ARTCACHE_BUDGETS
                     if value == current), "%d MB" % current)

    def _settings_artbudget_clicked(self):
        from . import playoptions
        current = artcache.budget_bytes() // (1024 * 1024)
        selected = next((i for i, (mb, _n) in enumerate(settings_options.ARTCACHE_BUDGETS)
                         if mb == current), 0)
        index = playoptions.show_choice(
            title="Artwork storage limit",
            subtitle="Artwork over this is removed oldest first, and downloads "
                     "again when you next see it.",
            rows=[{"label": name, "detail": ""}
                  for _mb, name in settings_options.ARTCACHE_BUDGETS],
            selected_idx=selected)
        if index is None:
            return
        # A Kodi setting, not a server preference: it describes THIS device's
        # disk, so it has no business on the account.
        chosen = settings_options.ARTCACHE_BUDGETS[index][0]
        kodigui.ADDON.setSettingInt("artcache_budget_mb", chosen)
        self.setProperty("settings_art_budget",
                         self._settings_art_budget_label(chosen))

    def _settings_artclear_clicked(self):
        """Empty the staging area and drop our rows from Kodi's texture cache.

        Asks first. Nothing here is destructive in the sense that matters --
        every byte is re-downloadable and the artwork comes back as the user
        browses -- but it can mean a few hundred megabytes fetched again over
        the next few screens, which is worth a sentence before it happens.

        Both halves go together, and neither is optional. Clearing the files
        while leaving the rows would leave Kodi drawing from its own copies of
        pictures we have just decided not to keep, under source paths that no
        longer exist; clearing the rows alone would leave the disk full.
        """
        if not cardoptions.confirm_clear_artwork():
            return
        client = self._get_client()
        # Without a client we can still empty our own directory and drop the
        # rows that point into it -- only the legacy tokenised rows need to
        # know the server's address, and texturedb refuses to guess at those.
        hosts = client.own_hosts() if client else None
        removed, freed = artcache.purge(hosts)
        cardoptions.alert(
            "Clear artwork cache",
            "Freed %.0f MB across %d file%s." % (freed / 1e6, removed,
                                                 "" if removed == 1 else "s")
            if removed else "There was nothing to clear.")
        self.setProperty("settings_art_budget", self._settings_art_budget_label())

    def _settings_fonts_clicked(self):
        """Re-run the host setup, asking first.

        This is the way back in after declining the prompt, which is
        otherwise remembered until the font set or the host-config
        expectation changes -- and the way to install into a skin switched to
        later, since fonts are injected per-skin. It was the one genuinely
        useful thing left in Kodi's own settings dialog."""
        from .. import hostsetup
        applied = hostsetup.ensure_host_setup(forced=True)
        cardoptions.alert(
            "Device setup",
            "Done. Restart Kodi for it to take effect."
            if applied else
            "Nothing was changed. tofa's own screens keep working either way.")
