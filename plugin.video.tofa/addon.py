#!/usr/bin/env python3
"""Router: plugin://plugin.video.tofa/?action=... (brief §2).

Directory-provider only -- no custom window XML, no bundled skin (brief §2,
§10). Every screen is Kodi's own container drawing ListItems we hand it.
"""
from __future__ import annotations

import sys
import urllib.parse
from typing import Any, Optional

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib import api, auth, cloud, home_rows, http, listing, log, monitor, playback, signin
from resources.lib.api import MediaServerClient
from resources.lib.profile import CapabilityProfile
from resources.lib.windows import profile_select

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

_ = ADDON.getLocalizedString


def build_url(**params) -> str:
    clean = {k: str(v) for k, v in params.items() if v is not None}
    return f"{BASE_URL}?{urllib.parse.urlencode(clean)}"


def get_params() -> dict[str, str]:
    qs = sys.argv[2][1:] if len(sys.argv) > 2 else ""
    return dict(urllib.parse.parse_qsl(qs))


def get_client() -> MediaServerClient:
    session = http.new_session()
    tok = auth.ensure_fresh(session)
    tok = profile_select.ensure_profile_selected(session, tok)
    return api.client_for(session, tok)


def notify(message: str, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(ADDON_NAME, message, icon)


# --------------------------------------------------------------------------
# Window UI -- purely additive, doesn't touch the directory-provider routes
# above. Imported lazily (only when one of these actions is invoked) so the
# window/kodigui framework never loads for the default directory-listing
# path this add-on otherwise runs entirely through xbmcplugin.
# --------------------------------------------------------------------------

def _release_plugin_container() -> None:
    """Close the directory handle and get Kodi off this plugin's folder.

    Both halves matter, for different reasons.

    Closing the handle is required before any window activation: Kodi is
    holding a busy dialog open waiting for a listing, and while it is up
    activation is refused with "active modal dialogs".

    Navigating away is required so the window can be CLOSED again. These
    actions leave the Videos window sitting on
    `plugin://plugin.video.tofa/?action=...`; when our window closes, Kodi
    re-enters that folder, runs this file again, and reopens the window --
    an exit loop with no way out except Kodi's Home button. Seen live on the
    CoreELEC box, 2026-08-03: cardoptions (the exit dialog), then
    CPythonInvoker on addon.py, then script-tofa-main.xml, over and over.

    Kodi's own Home is the right place to land: it is where the plugin
    listing would have gone had the user backed out of it normally, and it
    holds no path that can relaunch anything. The exit dialog's Minimize
    branch already did exactly this, which is why Minimize escaped the loop
    and Exit did not.

    None of this affects the launch_home.py / RunScript entry point, which
    has no directory listing behind it at all -- see
    resources/lib/windows/main.py and the two-entry-points note. That is
    still the door the Program add-ons tile uses.
    """
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True, updateListing=True, cacheToDisc=False)
    xbmc.executebuiltin("ActivateWindow(10000)")


def action_home_window() -> None:
    _release_plugin_container()

    from resources.lib import prefetch
    from resources.lib.windows import splash

    # Splash BEFORE the heavy import, and dismissed by MainWindow.onFirstInit
    # rather than here -- same launch as launch_home.py, see the note there
    # for what each ordering was measured to cost.
    splash.ensure_up()

    from resources.lib.windows.main import MainWindow

    prefetch.warm()
    splash.wait_out()
    splash.hand_over()
    # Same two rules as launch_home.py: a backgrounded player first, then
    # the remembered section.
    from resources.lib.windows.player import PlayerWindow

    try:
        if PlayerWindow.reactivate_if_backgrounded():
            return
        target = MainWindow.remembered_target()
        MainWindow.open(start_target=target) if target else MainWindow.open()
        # Same restart contract as launch_home.py: a profile switch closes
        # the window and asks for a new one. Without this the other door
        # would drop the viewer out of the add-on mid-switch.
        while MainWindow.take_restart_request():
            prefetch.reset()
            prefetch.warm()
            MainWindow.open()
    finally:
        # A no-op on the normal path (hand_over cleared it); this only
        # fires if the open above threw before Kodi could replace the
        # splash, where an unclosable splash would be the worse failure.
        splash.dismiss()
        # ...and forget any splash this process owned. Kodi destroys the windows
        # an interpreter created when that interpreter is torn down, so once this
        # script ends there is no splash anywhere -- whatever the flag says. Not
        # doing this is what left every profile switch rebuilding the app over
        # Kodi's own Home; see splash.release().
        splash.release()


def action_browse_window() -> None:
    _release_plugin_container()

    # Browse/Discover/Search are sections of the merged MainWindow, not
    # standalone xbmcgui windows.
    from resources.lib.windows.main import MainWindow

    MainWindow.open(start_target="browse_window")


def action_discover_window() -> None:
    _release_plugin_container()

    from resources.lib.windows.main import MainWindow

    MainWindow.open(start_target="discover_window")


def action_search_window() -> None:
    _release_plugin_container()

    from resources.lib.windows.main import MainWindow

    MainWindow.open(start_target="search_window")


def action_detail_window(params: dict[str, str]) -> None:
    _release_plugin_container()

    from resources.lib.windows.detail import DetailWindow

    DetailWindow.open(
        media_id=params.get("media_id"),
        discovery_id=params.get("discovery_id"),
        media_type=params.get("media_type"),
    )


# --------------------------------------------------------------------------
# sign-in / sign-out
# --------------------------------------------------------------------------

def action_sign_in() -> None:
    signin.interactive_sign_in()


def action_sign_out() -> None:
    auth.sign_out()
    notify(_(31020))


def action_install_fonts() -> None:
    """Settings > Appearance > Install tofa fonts."""
    from resources.lib import hostsetup

    hostsetup.setup_interactive()


def action_switch_profile() -> None:
    profile_select.switch_profile()


# --------------------------------------------------------------------------
# browsing
# --------------------------------------------------------------------------

# preferences.home_screen.rows (from GET /users/me) drives the row-based
# home screen; home_rows.py's maps mirror the id/type -> label scheme the
# web app hardcodes client-side (the server sends ids, not labels) and are
# shared with the windowed Home screen, which must resolve the same ids to
# the same labels. A row type/id/list_type not in these maps is skipped,
# not a crash -- feature-detect rather than assume a fixed surface.
_BUILTIN_ROW_LABELS = home_rows.BUILTIN_ROW_LABELS
_DISCOVERY_LIST_LABELS = home_rows.DISCOVERY_LIST_LABELS


def _builtin_row_url(row_id: str) -> Optional[str]:
    if row_id == "continue_watching":
        return build_url(action="continue")
    if row_id == "recent_movies":
        return build_url(action="browse", media_type="movie", page=1, sort="added_at", order="desc")
    if row_id == "recent_tv":
        return build_url(action="browse", media_type="tv", page=1, sort="added_at", order="desc")
    if row_id == "recently_released":
        # Films and shows together, by release date -- no media_type filter.
        return build_url(action="browse", page=1, sort="release_date", order="desc")
    if row_id == "top_rated_movies":
        return build_url(action="browse", media_type="movie", page=1, sort="rating", order="desc")
    if row_id == "top_rated_tv":
        return build_url(action="browse", media_type="tv", page=1, sort="rating", order="desc")
    if row_id == "suggested":
        return build_url(action="suggested")
    return None


def show_root_menu() -> None:
    xbmcplugin.setContent(HANDLE, "videos")
    client = get_client()

    rows: list[dict[str, Any]] = []
    try:
        rows = (((client.whoami().get("preferences") or {}).get("home_screen") or {}).get("rows")) or []
    except http.ApiError as exc:
        log.debug(f"could not load home_screen preference, falling back to defaults: {exc.message}")

    entries: list[tuple[str, str, Optional[str]]] = []  # (label, url, icon)
    if rows:
        for row in rows:
            if not row.get("enabled", True):
                continue
            row_type = row.get("type")
            if row_type == "builtin":
                row_id = row.get("id")
                label_id = _BUILTIN_ROW_LABELS.get(row_id)
                url = _builtin_row_url(row_id)
                if label_id and url:
                    icon = "DefaultInProgressShows.png" if row_id == "continue_watching" else None
                    entries.append((_(label_id), url, icon))
                else:
                    log.debug(f"skipping unknown home_screen builtin row id={row_id}")
            elif row_type == "discovery":
                list_type = row.get("discoveryList")
                label_id = _DISCOVERY_LIST_LABELS.get(list_type)
                if list_type and label_id:
                    entries.append((_(label_id), build_url(action="discover_list", list_type=list_type), None))
                else:
                    log.debug(f"skipping unknown home_screen discovery list_type={list_type}")
            else:
                log.debug(f"skipping unknown home_screen row type={row_type}")
    else:
        entries.append((_(31000), build_url(action="continue"), "DefaultInProgressShows.png"))

    # Fixed entries -- not part of home_screen (mirrors the web app's
    # separate Browse/Discover tabs, distinct from its row-based Home page).
    entries.append((_(31001), build_url(action="browse", media_type="movie", page=1), "DefaultMovies.png"))
    entries.append((_(31002), build_url(action="browse", media_type="tv", page=1), "DefaultTVShows.png"))
    entries.append((_(31085), build_url(action="libraries"), None))
    entries.append((_(31066), build_url(action="discover"), None))
    entries.append((_(31067), build_url(action="watchlist"), None))
    entries.append((_(31003), build_url(action="search"), "DefaultAddonsSearch.png"))

    for label, url, icon in entries:
        li = xbmcgui.ListItem(label=label)
        if icon:
            li.setArt({"icon": icon, "thumb": icon})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_continue_watching() -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    for item in client.continue_watching():
        listing.add_continue_item(HANDLE, client, build_url, item, xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


def show_browse(
    media_type: Optional[str],
    page: int,
    sort: str = "title",
    order: str = "asc",
    genre: Optional[str] = None,
    library_id: Optional[str] = None,
) -> None:
    """Serves default Browse, Recently Added (sort=added_at&order=desc),
    Top Rated (sort=rating&order=desc), genre-filtered, and library-filtered
    browsing alike -- one function, not near-duplicates per row type.
    `media_type` can be `other` here (a library's own type, e.g. a "Videos"
    catch-all library) -- treated like `movie`: flat, single-file playable
    items, no season hierarchy."""
    client = get_client()
    xbmcplugin.setContent(HANDLE, "tvshows" if media_type == "tv" else "movies" if media_type == "movie" else "videos")
    kwargs: dict[str, Any] = {"page": page, "per_page": 50, "sort": sort, "order": order}
    if genre:
        kwargs["genre"] = genre
    if library_id:
        kwargs["library_id"] = library_id
    result = client.media_list(media_type, **kwargs)
    # `media_type` is None for a deliberately MIXED listing -- Recently
    # Released puts films and shows in one row. Genres are asked for per
    # media type, so that shortcut has no meaning here and is left out.
    if page == 1 and not genre and media_type:
        li = xbmcgui.ListItem(label=_(31068))
        url = build_url(action="genres", media_type=media_type, library_id=library_id)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    for media in result.get("items", []):
        # Per ITEM, not per listing: in a mixed listing every show would
        # otherwise be built as a movie -- playable, no season hierarchy --
        # and its episodes would be unreachable.
        kind = media_type or media.get("media_type")
        if kind == "tv":
            listing.add_show_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
        else:
            listing.add_movie_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
    if page < result.get("total_pages", 1):
        more_label = _(31001) if media_type == "movie" else _(31002) if media_type == "tv" else _(31086)
        li = xbmcgui.ListItem(label=">> " + more_label)
        url = build_url(
            action="browse", media_type=media_type, page=page + 1, sort=sort, order=order, genre=genre, library_id=library_id
        )
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_genres(media_type: str, library_id: Optional[str] = None) -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    for name in client.genres(media_type=media_type, library_id=library_id) or []:
        li = xbmcgui.ListItem(label=name)
        url = build_url(action="browse", media_type=media_type, genre=name, library_id=library_id, page=1)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_libraries() -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    for library in client.libraries() or []:
        li = xbmcgui.ListItem(label=library.get("name") or "")
        url = build_url(action="browse", media_type=library.get("media_type"), library_id=library.get("id"), page=1)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_seasons(media_id: str) -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "seasons")
    media = client.media_detail(media_id)
    show_title = media.get("title") or ""
    for season in media.get("seasons") or []:
        listing.add_season_item(HANDLE, client, build_url, media_id, show_title, season, xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


def show_episodes(media_id: str, season_number: int) -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "episodes")
    media = client.media_detail(media_id)
    show_title = media.get("title") or ""
    season = next((s for s in media.get("seasons") or [] if s["season_number"] == season_number), None)
    for episode in (season or {}).get("episodes") or []:
        listing.add_episode_item(
            HANDLE, client, build_url, media_id, show_title, season_number, episode, xbmcplugin.addDirectoryItem
        )
    xbmcplugin.endOfDirectory(HANDLE)


def action_search() -> None:
    query = xbmcgui.Dialog().input(_(31040), type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    result = client.search(query)
    movies = result.get("movies") or []
    if not movies:
        notify(_(31041))
    for media in movies:
        if media.get("media_type") == "tv":
            listing.add_show_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
        else:
            listing.add_movie_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


def show_suggested() -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    result = client.suggested()
    items = result.get("items") or []
    if not items:
        # A thin watch history is expected, not an error -- notify and
        # still end the directory successfully.
        notify(_(31065))
    for media in items:
        if media.get("media_type") == "tv":
            listing.add_show_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
        else:
            listing.add_movie_item(HANDLE, client, build_url, media, xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


# All 7 ListType values (api-1.yaml) -- fixed, not fetched, since the enum
# is closed and this avoids pulling every list's full item payload just to
# render a category menu.
_DISCOVERY_LIST_TYPES = [
    ("trending-movies", 31080),
    ("trending-tv", 31081),
    ("popular-movies", 31082),
    ("popular-tv", 31083),
    ("top-rated-movies", 31062),
    ("top-rated-tv", 31063),
    ("upcoming-movies", 31084),
]


def show_discover_categories() -> None:
    xbmcplugin.setContent(HANDLE, "videos")
    for list_type, label_id in _DISCOVERY_LIST_TYPES:
        li = xbmcgui.ListItem(label=_(label_id))
        url = build_url(action="discover_list", list_type=list_type)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_discover_list(list_type: str) -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    result = client.discovery_list(list_type)
    for item in result.get("items") or []:
        listing.add_discovery_item(HANDLE, client, build_url, item, xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


def action_discover_detail(media_type: str, tmdb_id: str) -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    detail = client.discovery_detail(media_type, int(tmdb_id))
    title = detail.get("title") or ""

    if detail.get("in_library") and detail.get("local_media_id"):
        # Became available since the discover list was fetched -- route
        # straight to the real owned item instead of the Watchlist-only
        # screen below.
        li = xbmcgui.ListItem(label=title)
        if media_type == "tv":
            url = build_url(action="show", media_id=detail["local_media_id"])
            xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
        else:
            li.setProperty("IsPlayable", "true")
            url = build_url(action="play", media_id=detail["local_media_id"])
            xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # Not owned: a single info-rich folder item whose only action is to
    # add it to the watchlist -- there is no request-submission endpoint
    # in the documented API, only watchlist save/unsave.
    li = xbmcgui.ListItem(label=f"{_(31069)} — {title}")
    info = li.getVideoInfoTag()
    info.setMediaType("tvshow" if media_type == "tv" else "movie")
    info.setTitle(title)
    if detail.get("overview"):
        info.setPlot(detail["overview"])
    if detail.get("year"):
        info.setYear(detail["year"])
    if detail.get("genres"):
        info.setGenres(detail["genres"])
    art = {}
    poster = client.resolve_image_url(detail.get("poster_path"))
    backdrop = client.resolve_image_url(detail.get("backdrop_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if backdrop:
        art["fanart"] = backdrop
    if art:
        li.setArt(art)
    url = build_url(
        action="watchlist_toggle",
        add=1,
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        poster_path=detail.get("poster_path"),
        backdrop_path=detail.get("backdrop_path"),
        year=detail.get("year"),
    )
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def action_watchlist_toggle(params: dict[str, str]) -> None:
    client = get_client()
    media_type = params["media_type"]
    tmdb_id = int(params["tmdb_id"])
    if params.get("add", "1") != "0":
        snapshot = {
            "title": params.get("title"),
            "poster_path": params.get("poster_path"),
            "backdrop_path": params.get("backdrop_path"),
            "year": int(params["year"]) if params.get("year") else None,
        }
        client.watchlist_add_content(media_type, tmdb_id, snapshot)
        notify(_(31071))
    else:
        client.watchlist_remove_content(media_type, tmdb_id)
        notify(_(31072))
    # succeeded=True (default): the toggle itself worked; there's just
    # nothing to browse into. succeeded=False would surface Kodi's own
    # "content unavailable" indicator, which would misread as a failure.
    xbmcplugin.endOfDirectory(HANDLE)


def show_watchlist() -> None:
    client = get_client()
    xbmcplugin.setContent(HANDLE, "videos")
    for item in client.watchlist() or []:
        listing.add_watchlist_item(HANDLE, client, build_url, item, _(31070), xbmcplugin.addDirectoryItem)
    xbmcplugin.endOfDirectory(HANDLE)


# --------------------------------------------------------------------------
# playback
# --------------------------------------------------------------------------

def action_play(params: dict[str, str]) -> None:
    client = get_client()
    # for_device(), not the bare constructor: this path NEGOTIATES (see
    # playback.negotiate below), and profile.py commits every caller that
    # asks the server for a playback decision to the derived profile. It was
    # the one negotiating call site still using the plain one, so the AV1
    # ceiling would have reached windows/player.py and stopped here. Fixing
    # that also starts deriving audio_fidelity on this path, which is the
    # documented intent -- the bare constructor's own fallback is what
    # profile.py calls "the old stereo-AAC behaviour".
    profile = CapabilityProfile.for_device()

    file_id = params.get("file_id")
    if not file_id:
        media_id = params["media_id"]
        season = int(params["season"]) if "season" in params else None
        episode = int(params["episode"]) if "episode" in params else None
        try:
            file_id = playback.resolve_file_id(client, media_id, season, episode)
        except LookupError as exc:
            # Deliberately Kodi's stock dialog, not the skinned alert the
            # rest of the UI now uses. This is the plain directory-provider
            # path, which player.py's own docstring commits to keeping free
            # of any dependency on resources/lib/windows/ -- and a viewer
            # who reached it is browsing Kodi's own file list, where a
            # system dialog is the native thing anyway.
            xbmcgui.Dialog().ok(ADDON_NAME, str(exc))
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return

    # Only Continue Watching resumes automatically (position comes free on
    # the listing item, and clicking it already implies resume intent);
    # resume from Movies/TV/Search browsing isn't wired up here.
    #
    # Milliseconds here; playback.negotiate converts to the API's 100ns
    # ticks. The comment that used to sit here said "resume_ticks/
    # start_position_ticks are milliseconds despite the name" -- they are
    # not, and believing that made every transcoded resume start at zero.
    # See playback.TICKS_PER_MS.
    resume_ms = int(params["resume_ms"]) if "resume_ms" in params else None
    try:
        resp = playback.negotiate(client, file_id, profile, resume_ms=resume_ms)
    except playback.NegotiateTimeout:
        notify(_(31033), xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    except http.ApiError as exc:
        # Same hole as windows/player.py, different surface. This one is a
        # Kodi toast, gone in a few seconds, so it gets the SHORT sentence:
        # the window's card can stay up and explain, a toast cannot. The
        # useful half here is "not this one", not why.
        log.warning(f"negotiate failed: {exc!r}")
        notify(_(31121), xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    if not playback.is_direct(resp):
        # No longer a prompt. This used to ask before playing anything other
        # than DirectPlay and default to No, which meant a single Enter on a
        # listing item could end in a modal asking a question the viewer had
        # no way to act on from here -- there is no quality picker on the
        # plugin-directory surface. It is logged instead, and the window UI
        # carries the same posture; see windows/player.py for the full
        # reasoning and where this information is going to live.
        log.warning(
            f"non-DirectPlay: "
            f"play_method={resp.get('play_method')} decision_mode={resp.get('decision_mode')} "
            f"reasons={resp.get('transcode_reasons')} trace_id={resp.get('decision_trace_id')}"
        )

    # addon.py's process exits right after setResolvedUrl and can't itself
    # watch for onPlayBackStopped/Ended, so hand session info to service.py's
    # TofaPlayer via a one-shot Window property instead of staying resident.
    monitor.stash_pending_session(file_id, params.get("media_id"), resp["session_id"], resp["session_token"])

    li = playback.build_list_item(resp)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


# --------------------------------------------------------------------------
# router
# --------------------------------------------------------------------------

def run() -> None:
    params = get_params()
    action = params.get("action")

    if action == "sign_in":
        action_sign_in()
        return
    if action == "sign_out":
        action_sign_out()
        return
    if action == "switch_profile":
        action_switch_profile()
        return
    # Ahead of the signed-in gate below: installing fonts is a display
    # concern and has nothing to do with having an account.
    if action == "install_fonts":
        action_install_fonts()
        return
    if action == "home_window":
        action_home_window()
        return
    if action == "browse_window":
        action_browse_window()
        return
    if action == "discover_window":
        action_discover_window()
        return
    if action == "search_window":
        action_search_window()
        return
    if action == "detail_window":
        action_detail_window(params)
        return

    if not auth.is_signed_in():
        # Drive the device-code flow right here rather than just telling
        # the user to go find it in Add-on settings.
        signin.interactive_sign_in()
        if not auth.is_signed_in():
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return

    try:
        if action is None:
            show_root_menu()
        elif action == "continue":
            show_continue_watching()
        elif action == "browse":
            show_browse(
                params.get("media_type"),
                int(params.get("page", 1)),
                sort=params.get("sort", "title"),
                order=params.get("order", "asc"),
                genre=params.get("genre"),
                library_id=params.get("library_id"),
            )
        elif action == "genres":
            show_genres(params["media_type"], library_id=params.get("library_id"))
        elif action == "libraries":
            show_libraries()
        elif action == "suggested":
            show_suggested()
        elif action == "discover":
            show_discover_categories()
        elif action == "discover_list":
            show_discover_list(params["list_type"])
        elif action == "discover_detail":
            action_discover_detail(params["media_type"], params["tmdb_id"])
        elif action == "watchlist":
            show_watchlist()
        elif action == "watchlist_toggle":
            action_watchlist_toggle(params)
        elif action == "show":
            show_seasons(params["media_id"])
        elif action == "season":
            show_episodes(params["media_id"], int(params["season_number"]))
        elif action == "search":
            action_search()
        elif action == "play":
            action_play(params)
        else:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except auth.NotSignedIn:
        notify(_(31021))
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except profile_select.ProfileCanceled:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except http.ApiError as exc:
        notify(_(31050) % exc.message, xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


if __name__ == "__main__":
    run()
