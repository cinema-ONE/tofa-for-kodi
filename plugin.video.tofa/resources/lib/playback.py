"""/stream/{id}/info negotiation -> resolved URL.

Guardrail: never silently hand Kodi a transcoded stream when
DirectPlay/DirectFile was the goal. Rejection is surfaced loudly and
playing the fallback anyway requires an explicit yes from the user, never
a default.
"""
from __future__ import annotations

from typing import Any, Optional

import xbmc
import xbmcgui

from . import http, log
from .api import MediaServerClient
from .profile import CapabilityProfile


class NegotiateTimeout(Exception):
    """The server didn't answer /stream/{id}/info in time -- distinct from
    "opening timeout" / "stall", matching the tofa Android app's states."""


def resolve_file_id(client: MediaServerClient, media_id: str, season: Optional[int] = None, episode: Optional[int] = None) -> str:
    """/media/{id} -> /media/{id}/versions, taking the server's recommended
    file for our declared capabilities."""
    versions = client.media_versions(media_id, season=season, episode=episode)
    version_list = versions.get("versions") or []
    if not version_list:
        raise LookupError(f"No playable versions for media {media_id}")
    recommended = versions.get("recommended_media_file_id")
    chosen = next((v for v in version_list if v["media_file_id"] == recommended), version_list[0])
    return chosen["media_file_id"]


#: The stream API's tick, in the milliseconds the rest of this client
#: counts in. `resume_ticks`, `start_position_ticks` and /seek's
#: `position_ticks` are ALL 100-nanosecond ticks -- the same unit QuickView
#: uses, and NOT the milliseconds the /progress endpoint takes.
#:
#: This was got wrong for a long time and the mistake was invisible, because
#: the server faithfully honours whatever you send: asking to resume at
#: `600000` gets you 60 milliseconds in, which looks exactly like a server
#: that ignores resume. Measured 2026-08-07 and written up on issue #7,
#: which had blamed the server for it.
TICKS_PER_MS = 10_000


#: One brief second-chance for a 503 from /stream/info -- "host is at
#: transcode capacity", which is also what a converter that cannot START
#: answers. The 0.9.33 notes say these failures usually clear within a
#: second or two, most often because a previous stream of the same title
#: has not finished releasing the graphics card, and that apps should
#: retry for a moment rather than erroring straight away. ONE retry, 503
#: only: a host genuinely out of capacity answers the same way, and
#: hammering it helps nobody -- while a 404 or 403 would answer the same
#: way forever.
_RETRY_503_AFTER_SECONDS = 2.0


def negotiate(
    client: MediaServerClient,
    file_id: str,
    profile: CapabilityProfile,
    resume_ms: Optional[int] = None,
) -> dict[str, Any]:
    """Negotiate a stream. `resume_ms` is MILLISECONDS, like every other
    position in this client; the conversion to the API's ticks happens here
    so no caller has to remember which unit this endpoint wants.

    Both play paths call this under their own spinner, so the one 503
    retry's two-second wait is spent looking like the load it is, not like
    a hang."""
    resume_ticks = (resume_ms * TICKS_PER_MS) if resume_ms else None
    for attempt in (1, 2):
        try:
            resp = client.stream_info(file_id, profile, dry_run=False, resume_ticks=resume_ticks)
            break
        except http.ApiError as exc:
            if exc.error == "timeout":
                raise NegotiateTimeout(str(exc)) from None
            if exc.status == 503 and attempt == 1:
                log.warning(f"playback: converter not ready (503), retrying once: {exc!r}")
                xbmc.sleep(int(_RETRY_503_AFTER_SECONDS * 1000))
                continue
            raise
    if resp.get("stream_url"):
        resp["stream_url"] = client.resolve_url(resp["stream_url"])
    return resp


def is_direct(resp: dict[str, Any]) -> bool:
    return resp.get("play_method") == "DirectPlay" and resp.get("decision_mode") == "DirectFile"


def apply_now_playing(li: xbmcgui.ListItem, media: dict[str, Any] | None,
                      *, title: str = "", season: Any = None, episode: Any = None,
                      art: dict[str, str] | None = None) -> None:
    """Describe what is playing, for everything OUTSIDE this add-on.

    Kodi republishes a playing item's info tag to remotes, phone apps, CEC
    displays and its own OSD. We were setting none of it, so a remote showed
    the last path segment of the stream URL -- literally "direct" -- and no
    artwork. Reported from the box.

    Kept here rather than in the player window because addon.py's plain
    directory-provider path plays through the same builder and deserves the
    same metadata.

    Follows plex-for-kodi (lib/player.py): set mediatype/title/tvshowtitle/
    season/episode/year/plot on the info tag and poster/fanart/thumb as art.
    The modern InfoTagVideo setters are Kodi 20+; setInfo() is the fallback,
    which is also how they gate it.
    """
    media = media or {}
    is_episode = season is not None and episode is not None
    show = media.get("title") or ""
    year = media.get("year") or ""
    if not year:
        date = media.get("release_date") or media.get("air_date") or ""
        if len(str(date)) >= 4 and str(date)[:4].isdigit():
            year = str(date)[:4]

    if art:
        li.setArt({k: v for k, v in art.items() if v})

    values = {
        "mediatype": "episode" if is_episode else "movie",
        "title": title or show,
        "plot": media.get("overview") or "",
    }
    if is_episode:
        values["tvshowtitle"] = show
    # The LABEL, not just the info tag. Remotes and phone apps read
    # Player.GetItem, whose `label` is a different field from the tag's
    # title -- an item built from a URL labels itself with the last path
    # segment, so a remote showed "direct" while the add-on's own OSD
    # (which reads VideoPlayer.Title, fed by the tag) read correctly. That
    # split is why this looked like the title being LOST later: it was
    # never set for the remote in the first place.
    if values["title"]:
        li.setLabel(values["title"])
    try:
        info = li.getVideoInfoTag()
        info.setMediaType(values["mediatype"])
        info.setTitle(values["title"])
        info.setPlot(values["plot"])
        if year:
            info.setYear(int(year))
        if is_episode:
            info.setTvShowTitle(show)
            info.setSeason(int(season))
            info.setEpisode(int(episode))
    except (AttributeError, TypeError, ValueError):
        # Kodi 19 and older have no InfoTagVideo setters.
        if year:
            values["year"] = year
        if is_episode:
            values["season"] = season
            values["episode"] = episode
        li.setInfo("video", values)


def build_list_item(resp: dict[str, Any], *, title: str = "",
                    media: dict[str, Any] | None = None,
                    season: Any = None, episode: Any = None,
                    art: dict[str, str] | None = None) -> xbmcgui.ListItem:
    li = xbmcgui.ListItem(path=resp["stream_url"])
    li.setProperty("IsPlayable", "true")
    # Before the duration/resume block: a caller that knows nothing still
    # gets a sane title instead of the URL's last path segment.
    apply_now_playing(li, media, title=title, season=season, episode=episode, art=art)
    info = li.getVideoInfoTag()
    duration_ms = resp.get("duration_ms")
    if duration_ms:
        info.setDuration(duration_ms // 1000)
    # Where the server says this stream begins. 100-NANOSECOND TICKS (see
    # TICKS_PER_MS) -- this used to divide by 1000, treating them as
    # milliseconds, which put the resume point 10,000x too early.
    #
    # Only meaningful for DirectPlay, where the whole file arrives and the
    # offset is advice about where to start. On an HLS session the stream
    # ALREADY begins here, so a resume point would seek a second time; see
    # start_offset_ms(), which is what the player uses instead.
    start_ms = start_offset_ms(resp)
    if start_ms and is_direct(resp):
        total_s = (duration_ms / 1000) if duration_ms else 0.0
        info.setResumePoint(start_ms / 1000.0, total_s)
    return li


def is_whole_file(resp: dict[str, Any]) -> bool:
    """Whether the player is being handed the ENTIRE file, so that its own
    clock is already the file's clock.

    Deliberately looser than is_direct(), which also requires
    decision_mode=DirectFile: what matters here is only whether the bytes
    arriving are the whole title or a server-cut HLS session. Same test the
    web client makes for this exact decision (`play_method === 'DirectPlay'`).
    """
    return resp.get("play_method") == "DirectPlay"


def start_offset_ms(resp: dict[str, Any]) -> int:
    """Where this stream's first frame sits in the FILE, in milliseconds.

    ZERO FOR DIRECTPLAY, even though the server still reports a
    start_position_ticks there -- on DirectPlay that number is advice about
    where to seek to, not a statement that the stream was cut. Treating it
    as an offset double-counts: the player would add 10 minutes to a clock
    that was already going to reach 10 minutes on its own. Measured doing
    exactly that before this guard existed.

    Non-zero only for an HLS session the server cut at an offset, where the
    clock genuinely restarts at zero and everything the viewer is shown --
    scrubber, OSD time, progress reports, skip segments -- has to add it
    back.
    """
    if is_whole_file(resp):
        return 0
    try:
        return int(resp.get("start_position_ticks") or 0) // TICKS_PER_MS
    except (TypeError, ValueError):
        return 0
