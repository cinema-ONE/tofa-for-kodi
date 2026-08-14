"""Media JSON -> xbmcgui.ListItem + InfoTagVideo.

Only Kodi-native containers are used -- no custom window XML, no bundled
skin. The skin draws every screen from what we hand it here.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import xbmcgui

from . import episodes
from .api import MediaServerClient


def _set_art(li: xbmcgui.ListItem, client: MediaServerClient, media: dict[str, Any]) -> None:
    art = {}
    poster = client.resolve_image_url(media.get("poster_path"))
    backdrop = client.resolve_image_url(media.get("backdrop_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if backdrop:
        art["fanart"] = backdrop
    if art:
        li.setArt(art)


def _set_common_info(li: xbmcgui.ListItem, media: dict[str, Any], *, mediatype: str) -> None:
    info = li.getVideoInfoTag()
    info.setMediaType(mediatype)
    info.setTitle(media.get("title") or "")
    if media.get("overview"):
        info.setPlot(media["overview"])
    if media.get("release_date"):
        info.setPremiered(media["release_date"])
        year = media["release_date"][:4]
        if year.isdigit():
            info.setYear(int(year))
    if media.get("genres"):
        info.setGenres(media["genres"])
    if media.get("runtime_minutes"):
        info.setDuration(media["runtime_minutes"] * 60)
    rating = media.get("imdb_rating") or media.get("rating")
    if rating:
        info.setRating(float(rating))


def add_movie_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    media: dict[str, Any],
    add_directory_item,
) -> None:
    li = xbmcgui.ListItem(label=media.get("title") or "")
    li.setProperty("IsPlayable", "true")
    _set_common_info(li, media, mediatype="movie")
    _set_art(li, client, media)
    url = build_url(action="play", media_id=media["id"])
    add_directory_item(handle, url, li, isFolder=False)


def add_show_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    media: dict[str, Any],
    add_directory_item,
) -> None:
    li = xbmcgui.ListItem(label=media.get("title") or "")
    _set_common_info(li, media, mediatype="tvshow")
    _set_art(li, client, media)
    url = build_url(action="show", media_id=media["id"])
    add_directory_item(handle, url, li, isFolder=True)


def add_season_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    show_media_id: str,
    show_title: str,
    season: dict[str, Any],
    add_directory_item,
) -> None:
    label = season.get("title") or f"Season {season['season_number']}"
    li = xbmcgui.ListItem(label=label)
    info = li.getVideoInfoTag()
    info.setMediaType("season")
    info.setTitle(label)
    info.setTvShowTitle(show_title)
    info.setSeason(season["season_number"])
    art = {}
    poster = client.resolve_image_url(season.get("poster_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if art:
        li.setArt(art)
    url = build_url(action="season", media_id=show_media_id, season_number=season["season_number"])
    add_directory_item(handle, url, li, isFolder=True)


def add_episode_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    show_media_id: str,
    show_title: str,
    season_number: int,
    episode: dict[str, Any],
    add_directory_item,
) -> None:
    """`season_number` is passed in explicitly by the caller (from the
    enclosing Season object) -- Episode itself carries `season_id`, not a
    denormalised `season_number`; reading `episode.get("season_number")`
    silently produces `season=0` in every play URL."""
    label = episodes.title_or_number(episode)
    li = xbmcgui.ListItem(label=label)
    li.setProperty("IsPlayable", "true")
    info = li.getVideoInfoTag()
    info.setMediaType("episode")
    info.setTitle(label)
    info.setTvShowTitle(show_title)
    info.setSeason(season_number)
    info.setEpisode(episode["episode_number"])
    if episode.get("overview"):
        info.setPlot(episode["overview"])
    if episode.get("air_date"):
        info.setFirstAired(episode["air_date"])
    if episode.get("runtime_minutes"):
        info.setDuration(episode["runtime_minutes"] * 60)
    art = {}
    still = client.resolve_image_url(episode.get("still_path"))
    if still:
        art["thumb"] = still
    if art:
        li.setArt(art)
    url = build_url(
        action="play",
        media_id=show_media_id,
        season=season_number,
        episode=episode["episode_number"],
    )
    add_directory_item(handle, url, li, isFolder=False)


def _add_owned_or_discover_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    *,
    title: str,
    media_kind: str,
    tmdb_id: Optional[int],
    owned: bool,
    local_media_id: Optional[str],
    art: dict[str, Any],
    set_info,
    add_directory_item,
    context_menu: Optional[list[tuple[str, str]]] = None,
) -> None:
    """Shared routing for any item that might be owned (route to the same
    play/show URLs as a normal library browse) or not (route to the
    discover-detail screen, keyed by tmdb_id, for a Watchlist action) --
    used by both Discover and Watchlist listings, which carry the same
    owned/unowned distinction under different field names."""
    li = xbmcgui.ListItem(label=title)
    set_info(li)
    if art:
        li.setArt(art)
    if context_menu:
        li.addContextMenuItems(context_menu)
    if owned and local_media_id:
        if media_kind == "tv":
            url = build_url(action="show", media_id=local_media_id)
            add_directory_item(handle, url, li, isFolder=True)
        else:
            li.setProperty("IsPlayable", "true")
            url = build_url(action="play", media_id=local_media_id)
            add_directory_item(handle, url, li, isFolder=False)
    else:
        url = build_url(action="discover_detail", media_type=media_kind, tmdb_id=tmdb_id)
        add_directory_item(handle, url, li, isFolder=True)


def add_discovery_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    item: dict[str, Any],
    add_directory_item,
) -> None:
    """`AnnotatedDiscoveryItem` -- field names differ from `MediaSummary`
    (`year` not `release_date`, `vote_average` not `rating`, `tmdb_id` not
    `id`), so this doesn't reuse add_movie_item/add_show_item's field
    mapping, only the owned-routing logic (`_add_owned_or_discover_item`)."""
    mediatype = "tvshow" if item.get("type") == "tv" else "movie"

    def set_info(li: xbmcgui.ListItem) -> None:
        info = li.getVideoInfoTag()
        info.setMediaType(mediatype)
        info.setTitle(item.get("title") or "")
        if item.get("overview"):
            info.setPlot(item["overview"])
        if item.get("year"):
            info.setYear(item["year"])
        if item.get("genres"):
            info.setGenres(item["genres"])
        if item.get("vote_average"):
            info.setRating(float(item["vote_average"]))

    art = {}
    poster = client.resolve_image_url(item.get("poster_path"))
    backdrop = client.resolve_image_url(item.get("backdrop_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if backdrop:
        art["fanart"] = backdrop

    _add_owned_or_discover_item(
        handle,
        client,
        build_url,
        title=item.get("title") or "",
        media_kind=item.get("type") or "movie",
        tmdb_id=item.get("tmdb_id"),
        owned=bool(item.get("in_library")),
        local_media_id=item.get("local_media_id"),
        art=art,
        set_info=set_info,
        add_directory_item=add_directory_item,
    )


def add_watchlist_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    item: dict[str, Any],
    remove_label: str,
    add_directory_item,
) -> None:
    """`WatchlistItem` row -- `owned` + `media_id` for library titles,
    `media_kind`/`tmdb_id` always present for routing either way. Unowned
    rows get a "Remove from Watchlist" context-menu action -- the natural Kodi idiom for a one-off action on a
    list item that isn't itself a navigation target, rather than a fake
    intermediate folder. Owned rows don't need it: they're not on the
    content-watchlist path (they route straight to play/show), and removing
    an *owned* title's watchlist flag isn't exposed by this add-on."""
    mediatype = "tvshow" if item.get("media_kind") == "tv" else "movie"
    owned = bool(item.get("owned"))
    context_menu = None
    if not owned:
        remove_url = build_url(
            action="watchlist_toggle",
            add=0,
            media_type=item.get("media_kind") or "movie",
            tmdb_id=item.get("tmdb_id"),
        )
        context_menu = [(remove_label, f"RunPlugin({remove_url})")]

    def set_info(li: xbmcgui.ListItem) -> None:
        info = li.getVideoInfoTag()
        info.setMediaType(mediatype)
        info.setTitle(item.get("title") or "")
        if item.get("overview"):
            info.setPlot(item["overview"])
        if item.get("year"):
            info.setYear(item["year"])
        if item.get("genres"):
            info.setGenres(item["genres"])
        if item.get("imdb_rating"):
            info.setRating(float(item["imdb_rating"]))

    art = {}
    poster = client.resolve_image_url(item.get("poster_path"))
    backdrop = client.resolve_image_url(item.get("backdrop_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if backdrop:
        art["fanart"] = backdrop

    _add_owned_or_discover_item(
        handle,
        client,
        build_url,
        title=item.get("title") or "",
        media_kind=item.get("media_kind") or "movie",
        tmdb_id=item.get("tmdb_id"),
        owned=owned,
        local_media_id=item.get("media_id"),
        art=art,
        set_info=set_info,
        add_directory_item=add_directory_item,
        context_menu=context_menu,
    )


def add_continue_item(
    handle: int,
    client: MediaServerClient,
    build_url: Callable[..., str],
    item: dict[str, Any],
    add_directory_item,
) -> None:
    is_episode = item.get("kind") == "episode" or item.get("episode_id")
    label = item.get("title") or ""
    if is_episode and item.get("episode_title"):
        label = f"{label} - {item['episode_title']}"
    li = xbmcgui.ListItem(label=label)
    li.setProperty("IsPlayable", "true")
    info = li.getVideoInfoTag()
    info.setMediaType("episode" if is_episode else "movie")
    info.setTitle(label)
    if is_episode:
        info.setTvShowTitle(item.get("title") or "")
        if item.get("season_number") is not None:
            info.setSeason(item["season_number"])
        if item.get("episode_number") is not None:
            info.setEpisode(item["episode_number"])
    if item.get("overview"):
        info.setPlot(item["overview"])
    if item.get("genres"):
        info.setGenres(item["genres"])
    if item.get("duration_ms"):
        info.setDuration(item["duration_ms"] // 1000)
    # position_ms comes free on every ContinueWatchingItem -- no extra API
    # call needed, unlike resuming from Movies/TV/Search. Sets the poster's
    # partial-progress badge; the actual auto-seek happens in action_play
    # via resume_ms on the play URL below.
    if item.get("position_ms"):
        total_s = (item["duration_ms"] / 1000) if item.get("duration_ms") else 0.0
        info.setResumePoint(item["position_ms"] / 1000, total_s)
    art = {}
    poster = client.resolve_image_url(item.get("poster_path"))
    backdrop = client.resolve_image_url(item.get("backdrop_path"))
    if poster:
        art["poster"] = poster
        art["thumb"] = poster
    if backdrop:
        art["fanart"] = backdrop
    if art:
        li.setArt(art)
    # ContinueWatchingItem already carries the resolved media_file_id -- no
    # versions lookup needed, unlike browse/search results. Clicking an item
    # from Continue Watching already implies "resume" -- no prompt needed,
    # just pass the known position straight through.
    url = build_url(
        action="play",
        file_id=item["media_file_id"],
        media_id=item["media_id"],
        resume_ms=item.get("position_ms"),
    )
    add_directory_item(handle, url, li, isFolder=False)
