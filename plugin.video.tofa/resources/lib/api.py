"""tofa media-server REST client.

`stream_url` is server-relative (see resolve_url); session teardown needs
session_token as `?st=`, not just Bearer auth (see end_session).
"""
from __future__ import annotations

import datetime
import time
import urllib.parse
from typing import Any, Optional

import requests

from . import artcache, auth, http, log
from .profile import CapabilityProfile

#: The cloud proxy's own way of saying "the server is not on the other end
#: of me": HTTP 503, `server_relay_not_connected`. It is an ANSWER, not a
#: transport failure, so a retry rule written around requests' exceptions
#: alone never fired on it -- and the whole point of holding a second
#: address is to survive exactly this. 502/504 are the same shape from a
#: gateway that phrases it differently.
_RELAY_DOWN = ("server_relay_not_connected", "server_offline")


def _rfc3339_epoch(value: Optional[str]) -> Optional[float]:
    """`"2026-08-15T12:34:56Z"` -> a POSIX timestamp, or None.

    `fromisoformat` accepts the `Z` suffix only from Python 3.11, and the
    boxes this runs on are not all on the same one -- so the suffix is
    rewritten rather than relied upon. None for anything unparseable: the
    caller stores an expiry it cannot read as "unknown", which its own
    expiry check already treats as "ask again", and a wrong timestamp would
    be worse than no timestamp.
    """
    if not value:
        return None
    try:
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(text).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _worth_retrying(exc: http.ApiError) -> bool:
    """Should this failure be re-tried against the other address?

    Not a 4xx: the server answered and would answer the same way twice.
    Not a 500 from the server itself, which is a bug and not an address
    problem."""
    if exc.error in ("connection_error", "timeout"):
        return True
    return exc.status in (502, 503, 504) or exc.error in _RELAY_DOWN


class MediaServerClient:
    def __init__(
        self,
        session,
        base_url: str,
        access_token: str,
        device_id: str,
        fallback_base_url: str | None = None,
        profile_id: str | None = None,
        profile_token: str | None = None,
        profile_token_expires_at: float | None = None,
    ):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.device_id = device_id
        # profile_token (locked, PIN-verified) takes precedence over
        # profile_id when both are set. Sending neither is fine only for
        # single-profile/no-PIN households (server falls back to primary).
        self.profile_id = profile_id
        self.profile_token = profile_token
        self.profile_token_expires_at = profile_token_expires_at
        # Other reachable address (LAN vs. WAN). On connection error, retry
        # once against this, then swap the two so subsequent calls (and the
        # next process launch, via auth.update_server) use whichever worked.
        self.fallback_base_url = fallback_base_url.rstrip("/") if fallback_base_url else None
        self._image_token: Optional[str] = None
        self._image_token_expires_at: float = 0.0

    def profile_token_expired(self, margin: float = 30.0) -> bool:
        """True once this client's PIN-verified profile token is past (or
        within `margin` of) its ~4h TTL, so it must be rebuilt rather than
        used.

        A client is built once and kept for a window's whole lifetime, but
        the token inside it is not valid for that long -- and the server's
        answer to an expired one is a 401 on EVERY account-scoped call, which
        every caller here treats as "no data". Measured on the box
        2026-08-09: the token expired 43 minutes into an episode, and the
        Detail page underneath then said "Play S1 E1" on a show whose S1 E14
        had just been watched, with no tick on it and the grid landing back
        on E1 -- three separate lies, all of them a 401 read as an empty
        progress map.

        There is no refresh endpoint (only POST /profiles/{id}/verify-pin),
        so the recovery is necessarily the PIN pad -- see
        profile_select.ensure_profile_selected, which every _get_client()
        runs through once this returns True.
        """
        if not self.profile_token:
            return False
        return (self.profile_token_expires_at or 0) <= time.time() + margin

    def resolve_url(self, url: str) -> str:
        """stream_url is server-relative (e.g.
        `/api/v1/stream/{id}/direct?st=...`), despite the API spec calling
        it a "ready-to-use URL".

        NOT urljoin, which is wrong the moment a base URL has a path of its
        own: RFC 3986 says an absolute-path reference REPLACES the base's
        path, so joining `/cache/images/x.jpg` onto the cloud proxy's
        `https://api.tofa.tv/servers/<uuid>/relay` produced
        `https://api.tofa.tv/cache/images/x.jpg` -- the proxy prefix gone,
        and a 404 for every poster on screen. It went unnoticed for as long
        as every base was a bare scheme+host, where join and concatenate
        agree. Measured against the demo server 2026-08-14: text and ratings
        loaded, not one image did.

        An ABSOLUTE url is still returned untouched -- discovery items point
        at tofa's public metadata CDN, and prefixing those would be
        nonsense."""
        if not url:
            return url
        if urllib.parse.urlparse(url).scheme:
            return url
        return "{0}/{1}".format(self.base_url.rstrip("/"), url.lstrip("/"))

    def _headers(self, *, include_bearer: bool = True) -> dict[str, str]:
        headers = {"X-Tofa-Device-Id": self.device_id}
        if include_bearer:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.profile_token:
            headers["X-Profile-Token"] = self.profile_token
        elif self.profile_id:
            headers["X-Profile-Id"] = self.profile_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
        try_fallback: bool = True,
        want_response: bool = False,
    ) -> Any:
        """`timeout` overrides http.py's default for callers that cannot
        afford to wait for it -- see monitor.PROGRESS_TIMEOUT_SECONDS.

        `try_fallback=False` additionally skips the second attempt against
        fallback_base_url. Worth knowing that the fallback DOUBLES a caller's
        worst case, which matters most to callers on a timer: it is the
        difference between one timeout and two.

        `want_response=True` answers the raw Response instead of its body,
        for the one caller that needs a RESPONSE HEADER (the heartbeat's
        rotated profile token). It goes through the same fallback and the
        same error handling; only the last line differs.
        """
        if auth.direct_only() and auth.is_relay_url(self.base_url):
            # Nothing direct to fall back TO -- see direct_only_addresses.
            # Refusing loudly beats quietly using the relay the viewer
            # switched off, and the message names the setting so the way out
            # is obvious.
            raise http.ApiError(
                0, "direct_only",
                "Direct connections only is on, and this server is only "
                "reachable through tofa's relay right now.")
        kwargs: dict[str, Any] = {"params": params, "json_body": json_body, "headers": self._headers()}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            resp = http.request_response(self.session, method, f"{self.base_url}{path}", **kwargs)
            return resp if want_response else http.body_of(resp)
        except http.ApiError as exc:
            # "Direct connections only" (Settings > Account > CONNECTION) is
            # exactly a refusal to take this fallback: the fallback IS the
            # relay when pairing handed us one. Read per call rather than
            # cached at construction, since each plugin action is a fresh
            # process anyway and a viewer who just flipped it means now.
            if not _worth_retrying(exc) or not self.fallback_base_url \
                    or not try_fallback or auth.direct_only():
                raise
            # SAY WHICH ADDRESS FAILED, before the second attempt can bury it.
            #
            # Only the fallback's exception propagates, so a failure of the
            # PRIMARY left no trace at all: the one line in kodi.log named
            # the fallback's host and nothing else. On 2026-08-21 that read
            # as "the relay refused us" when the actual event was the LAN
            # server timing out, and sent the investigation at the profile
            # PIN instead. The primary is the address that was supposed to
            # work; when both fail, its error is the one worth having.
            log.warning("api: {0} {1} failed on {2} ({3}), trying {4}".format(
                method, path, self.base_url, exc,
                self.fallback_base_url))
            resp = http.request_response(self.session, method, f"{self.fallback_base_url}{path}", **kwargs)
            self.base_url, self.fallback_base_url = self.fallback_base_url, self.base_url
            auth.update_server(self.base_url, self.fallback_base_url)
            return resp if want_response else http.body_of(resp)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _put(self, path: str, json_body: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._request("PUT", path, json_body=json_body, **kwargs)

    def _post(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._request("POST", path, params=params, json_body=json_body, **kwargs)

    def _delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", path, params=params)

    def whoami(self) -> Any:
        return self._get("/api/v1/users/me")

    def update_preferences(self, preferences: dict[str, Any]) -> Any:
        """Patch the profile's `preferences` blob, returning the whole updated
        user record (same shape as whoami()).

        A PATCH, not a replace: the server merges what it is sent, deeply for
        the `playback` section and shallowly for everything else. So send only
        the keys being changed -- reading whoami(), editing, and sending the
        whole blob back would clobber any key a newer client wrote that this
        one does not know about.

        The shallow half of that rule has teeth for nested sections other than
        `playback`: sending `{"home_screen": {"rows": [...]}}` replaces the
        entire `home_screen` object, so a caller changing rows has to send the
        section's other keys alongside them.

        403 means the primary profile is locked and the request needed an
        `X-Profile-Token` -- _headers() already sends one whenever a profile
        is resolved, so this surfaces as "no profile selected yet" in practice.
        Values are typed as the server stores them, which is not uniform: see
        prefs.as_bool() for the dotted keys it writes back as strings."""
        return self._put("/api/v1/users/me/preferences", {"preferences": preferences})

    def image_token(self) -> str:
        """1h-lived, image-scoped token for poster/backdrop `?st=` auth
        (separate from stream/session tokens). The server keeps it stable
        for an hour so art URLs stay byte-identical and Kodi's texture cache
        can hit -- but addon.py is a fresh process per listing, so an
        in-memory-only cache never survives to the next one. Checked in
        order: in-memory -> on-disk -> server (only once an hour), otherwise
        every browse mints a new token and duplicates art in Textures13.db."""
        if self._image_token and time.time() < self._image_token_expires_at - 60:
            return self._image_token

        cached = auth.load_cached_image_token()
        if cached:
            token, expires_at = cached
            if time.time() < expires_at - 60:
                self._image_token, self._image_token_expires_at = token, expires_at
                return token

        granted = self._get("/api/v1/auth/image-token")
        self._image_token = granted["token"]
        self._image_token_expires_at = time.time() + granted["expires_in"]
        auth.save_image_token(self._image_token, self._image_token_expires_at)
        return self._image_token

    def resolve_image_url(self, path: Optional[str]) -> Optional[str]:
        """poster_path/backdrop_path/still_path are NOT server-relative like
        stream_url -- they need a `/cache/` prefix (reverse-engineered from
        the web app's own resolveImageUrl()). Without it the server returns
        the web app's SPA shell, HTTP 200, not an image.

        Absolute URLs arrive from two different places and must be treated
        differently: our own server (collections' poster_url/backdrop_url)
        still needs the `?st=` token, but discovery items point at the tofa
        cloud's public metadata CDN, which needs no token -- and appending
        ours would hand a credential to a host that never asked for it."""
        remote = self.image_url_uncached(path)
        if not remote or not self._stageable(path):
            return remote
        # artcache hands back a STABLE LOCAL PATH once it holds the file, and
        # `remote` until then -- so the worst case is today's behaviour. It is
        # keyed on `path`, never on the URL: the token must not reach the
        # filename or every rotation would stage the picture again and rebuild
        # the very churn this removes. See artcache.py.
        return artcache.ref(remote, self._stage_key(path))

    def image_url_uncached(self, path: Optional[str]) -> Optional[str]:
        """The remote URL, with no staging-area lookup.

        Split out so artcache.prefetch() can be handed something to download
        without re-entering ref() and queueing the same work twice.

        The URL is FULLY TOKENISED. It has to be: it is both what the fetcher
        uses and what is returned on a miss, so a tokenless URL here 401s the
        fetch AND blanks every image on screen. Which is exactly what the
        first live run of this did.
        """
        if not path:
            return None
        if path.startswith("http"):
            if self._is_own_host(path):
                return f"{path}?st={self.image_token()}"
            return path
        cache_path = path if path.startswith("/cache/") else f"/cache/{path.lstrip('/')}"
        return f"{self.resolve_url(cache_path)}?st={self.image_token()}"

    def stage_pair(self, path: Optional[str]):
        """`(remote_url, staging key)` for an image worth staging, else None.

        The one place that decides what belongs in the staging area, so a
        batch caller cannot disagree with resolve_image_url about it. It said
        yes to everything once, and the tofa cloud's CDN images -- which need
        no staging, being tokenless and already stable -- were then dragged
        over the internet on every cold Home build. Two rows timed out mid
        batch because of it.
        """
        if not path or not self._stageable(path):
            return None
        url = self.image_url_uncached(path)
        return (url, self._stage_key(path)) if url else None

    def stage_pairs(self, items, *fields) -> list:
        """Every `(remote_url, staging key)` a batch of cards is about to draw.

        The batch form of stage_pair, so a caller building a row or a grid can
        stage the whole thing in one pass instead of letting each card miss on
        its own. A miss is not free: `artcache.ref` falls back to today's
        TOKENISED url, Kodi caches the picture under it, and an hour later that
        row is orphaned -- which is the churn the staging area exists to stop.

        Measured 2026-08-12, this was still happening everywhere except Home,
        the only screen that had a staging pass: the cinema box was filing
        13-67 new tokenised rows a day, and the AM6B box collected 107 in its
        first day with staging already switched on.

        Deduplicated, because the same picture legitimately repeats -- a season
        poster standing in for episodes that have no still, the same title in
        two search shelves -- and fetching it twice would be work for nothing.
        """
        pairs, seen = [], set()
        for item in items or []:
            for field in fields:
                pair = self.stage_pair((item or {}).get(field))
                if pair and pair[1] not in seen:
                    seen.add(pair[1])
                    pairs.append(pair)
        return pairs

    #: The one part of the tofa cloud's metadata CDN we DO stage. See
    #: _stageable for why this is a carve-out rather than the whole CDN.
    _CDN_PEOPLE = "/metadata/assets/tmdb/people/"

    def _stageable(self, path: str) -> bool:
        """Whether this image is ours to stage.

        Most of the tofa cloud's metadata CDN is not: its URLs carry no token,
        so they are already stable and Kodi caches them exactly once. Staging
        them was tried and reverted -- discovery posters were dragged over the
        internet on every cold Home build and two rows timed out mid batch.

        HEADSHOTS ARE THE EXCEPTION, measured on the cinema box 2026-08-22.
        "Cached exactly once" is true and still expensive, because Kodi's
        once is not free: a URL it has to cache goes download -> decode ->
        resize -> re-encode -> write to eMMC -> INSERT into Textures14.db,
        four jobs at a time, and the commit is what costs. Timed on a cold
        Cast & Crew, eleven headshots: the downloads finished in 20-280ms
        each, and then the panel sat still for 1.8s while the first four
        wrote themselves into the cache. Staged art skips all of it -- 3821
        staged files had produced 13 texture rows in total, against 323 rows
        for headshots alone.

        And unlike a discovery poster, a headshot is never already there:
        every one of seven shows sampled at random added 6-11 NEW rows, so
        the cast set is effectively unbounded and the cost is paid on every
        title opened rather than once per library.

        The carve-out is by PATH, not by caller, because resolve_image_url
        and stage_pair must agree about it -- a card that staged the file and
        then drew the remote URL would pay both costs.
        """
        if not path.startswith("http"):
            return True
        return self._is_own_host(path) or self._CDN_PEOPLE in path

    @staticmethod
    def _stage_key(path: str) -> str:
        """The identity artcache files this image under -- a path, never a
        URL, so no token can reach the filename."""
        return urllib.parse.urlparse(path).path if path.startswith("http") else path

    def own_hosts(self) -> set:
        """Every host that IS this media server.

        Both addresses, since base/fallback swap on connection error and
        artwork can genuinely have been cached under either. Public because
        texturedb needs it to decide which tokenised texture rows are ours to
        remove -- and getting that set wrong in the generous direction would
        mean deleting somebody else's artwork.
        """
        own = {urllib.parse.urlparse(self.base_url).netloc}
        if self.fallback_base_url:
            own.add(urllib.parse.urlparse(self.fallback_base_url).netloc)
        return {host for host in own if host}

    def own_url_prefixes(self) -> set:
        """Every address that IS this media server, host AND path.

        The host alone stopped being enough when the cloud proxy became an
        address: there, the host is `api.tofa.tv`, which serves the whole
        cloud -- every account, every server, and the public metadata CDN.
        Treating all of it as "ours" would append this profile's image token
        to URLs that never asked for one, which is the precise thing
        image_url_uncached refuses to do."""
        bases = [self.base_url] + ([self.fallback_base_url]
                                   if self.fallback_base_url else [])
        return {b.rstrip("/") for b in bases if b}

    def _is_own_host(self, url: str) -> bool:
        """Whether an absolute URL points at the media server we're talking
        to (either address, since base/fallback swap on connection error).

        Prefix, not hostname -- see own_url_prefixes. The trailing boundary
        matters: `.../relay` must not match `.../relay-something-else`."""
        for prefix in self.own_url_prefixes():
            if url == prefix or url.startswith(prefix + "/") \
                    or url.startswith(prefix + "?"):
                return True
        return False

    def search(self, q: str, **kwargs: Any) -> Any:
        return self._get("/api/v1/search", params={"q": q, **kwargs})

    def continue_watching(self) -> Any:
        return self._get("/api/v1/users/me/continue")

    def suggested(self) -> Any:
        """`items` (owned, playable) plus `personalized` (false on
        cold-start fallback; caller decides whether to hide a mostly-empty
        row)."""
        return self._get("/api/v1/users/me/suggested")

    def genres(self, media_type: Optional[str] = None, library_id: Optional[str] = None) -> Any:
        """List of genre *names* (not ids) -- `/media`'s `genre` param takes
        the name string directly."""
        params = {"media_type": media_type, "library_id": library_id}
        return self._get("/api/v1/media/genres", params=params)

    def facets(self, media_type: Optional[str] = None, library_id: Optional[str] = None) -> Any:
        """`{genres: [{value, count}], years: {min, max}, quality:
        [{value, count}], watched: {watched, in_progress, unwatched},
        sorts: [...]}` -- unlike genres() this carries real per-genre counts
        for the scope, so a genre with 0 matches isn't in the list."""
        params = {"media_type": media_type, "library_id": library_id}
        return self._get("/api/v1/media/facets", params=params)

    def system_info(self) -> Any:
        """`{version, api_version, capabilities: [...], library_count,
        user_count, connection_type, ...}` -- server-wide, not per-user or
        per-profile. Feature-detect via `capabilities` rather than gating on
        `api_version` (e.g. the Filter dialog's "Played" option is gated on
        `"media.watched_played"` being present here)."""
        return self._get("/api/v1/system/info")

    def libraries(self) -> Any:
        """Each entry has `id`/`name`/`media_type` (`movie`/`tv`/`other`,
        same enum as `/media`'s filter) -- a library's own type says which
        listing function to route it to. Needs only a normal user bearer
        token, no admin scope."""
        return self._get("/api/v1/libraries")

    def discovery_list(self, list_type: str) -> Any:
        """One of the 7 fixed `ListType` values (trending-movies, trending-tv,
        popular-movies, popular-tv, top-rated-movies, top-rated-tv,
        upcoming-movies). Items are annotated with `in_library`/
        `local_media_id` so already-owned titles route straight to existing
        play/show, not a dead-end detail screen."""
        return self._get(f"/api/v1/discovery/list/{list_type}")

    def discovery_lists(self) -> Any:
        """All configured discovery lists in one call (each entry carries its
        own `list_type`) -- used where several discoveryList types are
        needed at once (MainWindow's discover section; Home's server-driven
        rows), so one request covers them instead of one per row.

        Frozen at the original 7 ListType values for already-shipped
        clients; the 32-shelf surface is discovery_page() instead."""
        return self._get("/api/v1/discovery/lists")

    # -- 0.9.24+ discovery surface (capability "discovery.page") ----------
    # Verified live against 0.9.25 / api_version 17. Not described by the
    # published API docs, which still ship the 0.9.21 endpoint list.

    def discovery_page(self) -> Any:
        """`{heroes: [...], shelves: [...]}` -- the whole Discover shell in
        one call. 32 shelves, each `{key, kind, title, subtitle, list_type,
        items, missing_count, generated_at}`.

        `kind` (`now`/`availability`/`standard`/`decade`/`genre`/`house`) is
        the only grouping signal; there is no group field, the client
        derives its tabs from it. Key off `key`, not `list_type` -- the
        latter is null on every shelf added after the original 7.

        `heroes` is legacy: the apps dropped the spotlight in 0.9.25 and
        open straight onto the rows."""
        return self._get("/api/v1/discovery/page")

    # Shelves that accept the `genre` axis. NOT derivable from `kind`:
    # new-noteworthy-* is kind=now yet rejects genre, while upcoming-movies
    # is kind=availability and accepts it. Everything else returns HTTP 400
    # genre_not_supported_for_this_shelf, so callers must gate on this set
    # (or treat that 400 as "axis absent" rather than an error).
    GENRE_CAPABLE_SHELVES = frozenset({
        "trending-movies", "trending-tv",
        "popular-movies", "popular-tv",
        "top-rated-movies", "top-rated-tv",
        "upcoming-movies",
    })

    def discovery_shelf(
        self,
        key: str,
        sort: Optional[str] = None,
        decade: Optional[int] = None,
        genre: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> Any:
        """One shelf, drilled into. `sort` is `curated` (default),
        `trending`, `popular`, `top-rated` or `newest`.

        `curated` is a fixed 40 items with no `total` and no `next_cursor`;
        every other sort browses the whole catalog behind the shelf
        (`total` in the thousands) and pages 40 at a time via `next_cursor`.

        `decade` (4-digit start year) intersects with the shelf's own rule
        rather than replacing it -- decade=1990 on top-2010s-movies is 0
        items, not the 1990s. `genre` takes a slug from discovery_genres()
        and only works on GENRE_CAPABLE_SHELVES.

        A cursor is scoped to the exact sort/decade/genre combo that minted
        it; replaying one after changing an axis is a 400."""
        params = {"sort": sort, "decade": decade, "genre": genre, "cursor": cursor}
        return self._get(f"/api/v1/discovery/shelf/{key}", params=params)

    def discovery_genres(self) -> Any:
        """`{genres: [{slug, name, media_types}]}` -- the option set for
        discovery_shelf()'s `genre` param, each entry scoped to movie, tv or
        both. Empty until the server has synced with the cloud at least
        once; treat empty as "axis doesn't exist", not an error."""
        return self._get("/api/v1/discovery/genres")

    def person_filmography(self, name: str) -> Any:
        """A person's filmography from the cloud -- the NOT-in-your-library
        half only, for 7.4's second section.

        Matched on the exact name string (there is no person id anywhere in
        the API), best-known titles first, rating-gated to the profile, and
        with titles you already own removed server-side. That last part is
        why the two halves of 7.4 can simply be concatenated: the in-library
        half comes from `media_list(cast=name)` and the server guarantees
        they don't overlap."""
        return self._get("/api/v1/discovery/person", params={"name": name})

    def discovery_board(
        self,
        media_type: Optional[str] = None,
        sort: Optional[str] = None,
        min_critics: Optional[int] = None,
        min_audience: Optional[int] = None,
        agree: Optional[bool] = None,
        digital_now: Optional[bool] = None,
        not_in_library: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Any:
        """`{items, total, generated_at}` -- every cached title as one
        filterable board. `sort` is `consensus` (default), `critics`,
        `audience` or `newest`; `agree` means both scores clear 70.

        Items carry a `consensus` int alongside the normal fields. The spec
        is explicit that it ranks and nothing else -- what a surface shows is
        the critics and audience numbers themselves, never this one."""
        params = {
            "media_type": media_type, "sort": sort,
            "min_critics": min_critics, "min_audience": min_audience,
            "agree": agree, "digital_now": digital_now,
            "not_in_library": not_in_library,
            "limit": limit, "offset": offset,
        }
        return self._get("/api/v1/discovery/board", params=params)

    def watch_history(self, media_type: Optional[str] = None, limit: Optional[int] = None) -> Any:
        """`{items: [...]}` -- one entry per PLAY SESSION, not per title
        (the same title watched 3 times is 3 entries, newest first, each
        carrying its own started_at/ended_at/progress_percent) -- unlike
        every other listing here, this is not deduplicated by media id."""
        params = {"media_type": media_type, "limit": limit}
        return self._get("/api/v1/watch/history", params=params)

    def collection(self, collection_id: str) -> Any:
        """One collection and its members.

        Takes either a TMDB franchise id (digits throughout) or the slug of
        a curated one. Members come back as AnnotatedDiscoveryItem -- the
        same shape Discover's shelves use, so the same card builder renders
        them, owned and requestable alike."""
        return self._get(f"/api/v1/collections/{collection_id}")

    def collections(self, curated: Optional[bool] = None) -> Any:
        """`{collections: [...]}` -- franchise/collection groupings, each
        with `poster_url`/`backdrop_url` (already absolute `https://`,
        unlike media's `poster_path`) and `item_count`. Still route through
        resolve_image_url() for the `?st=` token -- it has a branch for
        already-absolute paths that skips the `/cache/` rewrite."""
        params = {"curated": curated}
        return self._get("/api/v1/collections", params=params)

    def discovery_detail(self, media_type: str, tmdb_id: int) -> Any:
        return self._get(f"/api/v1/discovery/detail/{media_type}/{tmdb_id}")

    def create_request(
        self,
        media_type: str,
        title: str,
        tmdb_id: int,
        *,
        seasons: list[int] | None = None,
        is4k: bool | None = None,
        tvdb_id: int | None = None,
        quality_profile_id: int | None = None,
    ) -> Any:
        """Ask the server to acquire a title it does not hold (7.9).

        `media_type`, `title` and `tmdb_id` are the server's required trio --
        it wants the title as well as the id, so a request stays readable in
        its own queue without a second lookup. `seasons` is season NUMBERS for
        a show (omit for a movie), `is4k` picks the 4K profile where the title
        and the viewer both allow it, `quality_profile_id` one of
        quality_profiles()' ids for the matching service (omit for the
        instance's own default -- the 4K tier always uses its own).
        """
        body: dict[str, Any] = {
            "media_type": media_type,
            "title": title,
            "tmdb_id": int(tmdb_id),
        }
        # Sent only when they have a value: the schema types every optional as
        # `T | null`, and an explicit null is not the same as "use the
        # server's default" for quality_profile_id.
        if seasons:
            body["seasons"] = list(seasons)
        if is4k is not None:
            body["is4k"] = bool(is4k)
        if tvdb_id is not None:
            body["tvdb_id"] = int(tvdb_id)
        if quality_profile_id is not None:
            body["quality_profile_id"] = int(quality_profile_id)
        return self._post("/api/v1/requests", json_body=body)

    def requests(self) -> Any:
        """Every request this viewer can see: `{requests: [...]}`, each one a
        summary plus its `seasons` and `download` progress."""
        return self._get("/api/v1/requests")

    def cancel_request(self, request_id: str) -> Any:
        """Withdraw a request. The real Apple TV app offers this as a second
        pill under "Requested", so it is not an admin-only action.

        The server does more than drop its own row: where the request reached
        radarr/sonarr it pulls the download from the queue and deletes the
        movie/series there too, keeping any file already fetched and adding no
        import exclusion (the title stays re-requestable). That removal is
        best-effort and its result reaches `arr_status` only on the next
        refresh of the server's *arr view -- measured at up to ~30s, which is
        why detail.py must not read a lingering `arr_status.tracked` as "still
        coming"."""
        return self._delete(f"/api/v1/requests/{request_id}")

    def retry_request(self, request_id: str) -> Any:
        """Ask the server to have another go at a request that failed.

        Only meaningful while the detail payload says `can_retry` -- the
        server counts attempts (`retry_count`/`max_retries`) and refuses once
        they are spent."""
        return self._post(f"/api/v1/requests/{request_id}/retry")

    def quality_profiles(self) -> Any:
        """`{sonarr: [{id, name}], radarr: [...], sonarr_default_profile_id,
        radarr_default_profile_id}` -- the profiles of the default HD instance
        of each service, for the request dialog's picker.

        Keyed by SERVICE, so a movie reads `radarr` and a show `sonarr`. The
        4K tier is deliberately absent: it always uses its own instance's
        default, so a 4K request takes no profile id at all."""
        return self._get("/api/v1/integrations/quality-profiles")

    def me(self) -> Any:
        """The USER record -- `can_request_4k`, `auto_approve_requests`,
        `is_admin`. Distinct from whoami(), which answers with the profile and
        its preferences; there is no `/whoami` on this server (404)."""
        return self._get("/api/v1/users/me")

    def watchlist(self) -> Any:
        """No page/per_page -- opts into the plain bare-array response shape
        rather than the paginated envelope."""
        return self._get("/api/v1/users/me/watchlist")

    def watchlist_add(self, media_id: str) -> Any:
        """For a title we HOLD, keyed by its local media id. The out-of-library
        counterpart is watchlist_add_content(), keyed by tmdb_id.

        Both are needed: a library card carries a media_id and often no
        tmdb_id at all, so the content endpoint silently cannot serve it --
        which is exactly how the card-options watchlist row first shipped as
        a no-op."""
        return self._post(f"/api/v1/users/me/watchlist/{media_id}")

    def watchlist_remove(self, media_id: str) -> Any:
        return self._delete(f"/api/v1/users/me/watchlist/{media_id}")

    def watchlist_add_content(self, media_type: str, tmdb_id: int, snapshot: dict[str, Any] | None = None) -> Any:
        """For a title not yet in the library (out-of-library, keyed by
        tmdb_id) -- distinct from watchlist_add() above, which takes the
        local media_id of a title we hold."""
        return self._post(f"/api/v1/users/me/watchlist/content/{media_type}/{tmdb_id}", json_body=snapshot or {})

    def watchlist_remove_content(self, media_type: str, tmdb_id: int) -> Any:
        return self._delete(f"/api/v1/users/me/watchlist/content/{media_type}/{tmdb_id}")

    def media_list(self, media_type: str, **kwargs: Any) -> Any:
        return self._get("/api/v1/media", params={"media_type": media_type, **kwargs})

    def media_detail(self, media_id: str) -> Any:
        return self._get(f"/api/v1/media/{media_id}")

    def quickview(self, file_id: str) -> Any:
        """The whole QuickView bundle: chapters, thumbnail tile tracks,
        detected segments and the operator's skip policy, in one request.

        Preferred over the per-part endpoints because the player wants two
        of them (8.5's segments and 8.2's tiles) at the same moment."""
        return self._get(f"/api/v1/media/{file_id}/quickview")

    def quickview_tile_bytes(self, file_id: str, width: int, index: int) -> bytes:
        """One QuickView sprite sheet, as raw bytes.

        Fetched HERE rather than handed to Kodi as a URL because Kodi loads
        a <texture> itself and cannot send the X-Profile-Token header this
        endpoint requires -- it answers 403 to an unheadered request. The
        caller writes the bytes somewhere Kodi can read as a file."""
        url = f"{self.base_url}/api/v1/media/{file_id}/quickview/tiles/{width}/{index}"
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=20.0)
        except requests.RequestException as exc:
            raise http.ApiError(0, "network", str(exc)) from None
        if resp.status_code != 200:
            raise http.ApiError(resp.status_code, "tile", resp.text[:200])
        return resp.content

    def quickview_segments(self, file_id: str) -> Any:
        """8.5's detected intro/outro segments, plus the operator's own skip
        timings.

        `start_ticks`/`end_ticks` here are 100-NANOSECOND ticks, NOT the
        milliseconds `position_ticks` uses on the progress endpoint. Proved
        against three files whose outro end_ticks land exactly on their
        duration; getting it wrong puts every segment ~10,000x too far in."""
        return self._get(f"/api/v1/media/{file_id}/quickview/segments")

    def media_versions(self, media_id: str, **kwargs: Any) -> Any:
        return self._get(f"/api/v1/media/{media_id}/versions", params=kwargs)

    def media_similar(self, media_id: str) -> Any:
        """Returns `{owned: MediaSummary[], requestable: RequestableRelated[]}`
        -- titles you own (playable now, keyed by `id`) and un-owned related
        candidates (keyed only by `tmdb_id`+`media_type`, no local `id`)."""
        return self._get(f"/api/v1/media/{media_id}/similar")

    def media_progress_batch(self, file_ids: list[str]) -> Any:
        """Returns `{items: WatchProgressResponse[]}` -- missing ids simply
        aren't present in `items`, not a null placeholder."""
        return self._post("/api/v1/media/progress/batch", json_body={"media_file_ids": file_ids})

    def get_progress(self, file_id: str) -> Any:
        """`None` if never watched, else WatchProgressResponse (`position_ms`, `completed`, ...)."""
        return self._get(f"/api/v1/media/{file_id}/progress")

    def update_progress(
        self, file_id: str, position_ms: int, ended: bool = False, timeout: float | None = None
    ) -> Any:
        """`id` here is the media_file_id, not the title/media id."""
        return self._put(
            f"/api/v1/media/{file_id}/progress",
            json_body={"position_ms": position_ms, "ended": ended},
            timeout=timeout,
            try_fallback=timeout is None,
        )

    def update_watched(self, file_id: str, watched: bool) -> Any:
        return self._put(f"/api/v1/media/{file_id}/watched", json_body={"watched": watched})

    def update_season_watched(self, season_id: str, watched: bool) -> Any:
        """Mark a whole season in ONE write (server 0.9.28+).

        Replaces a PUT per episode. The old comment in detail.py said it
        plainly -- "a 39-episode season really is 39 requests" -- because the
        server had no season-scoped endpoint. It has one now, with the same
        semantics as the per-episode call: `completed` takes the value asked
        for, and the resume point is cleared along with it.

        Answers `updated`, the number of watch_progress rows written. Zero is
        legitimate, not a failure: a season already entirely in the requested
        state writes nothing."""
        return self._put(f"/api/v1/seasons/{season_id}/watched",
                         json_body={"watched": watched})

    def dismiss_media(self, media_id: str) -> Any:
        """Hide a title from Continue Watching without touching its progress.

        7.2's "Remove from Continue Watching", which is deliberately NOT
        "mark watched": the point is to get a title you've abandoned off the
        row while keeping your position, in case you come back. Keyed by
        media_id (the title), not a file id."""
        return self._post(f"/api/v1/users/me/dismiss/{media_id}")

    def undismiss_media(self, media_id: str) -> Any:
        return self._delete(f"/api/v1/users/me/dismiss/{media_id}")

    def stream_info(
        self,
        file_id: str,
        profile: CapabilityProfile,
        *,
        dry_run: bool = False,
        resume_ticks: Optional[int] = None,
    ) -> Any:
        params = profile.to_query_params()
        params["dry_run"] = "true" if dry_run else "false"
        if resume_ticks is not None:
            params["resume_ticks"] = resume_ticks
        return self._get(f"/api/v1/stream/{file_id}/info", params=params)

    def seek_stream(self, session_id: str, session_token: str, position_ms: int) -> Any:
        """Re-cut an active HLS session at `position_ms`, returning a fresh
        `stream_url` and the `start_position_ticks` it actually landed on
        (keyframe-aligned, so slightly off what was asked).

        `position_ticks` here is 100-NANOSECOND TICKS, like `resume_ticks`
        and unlike the milliseconds /progress takes -- see
        playback.TICKS_PER_MS. Sending milliseconds asks for a position
        10,000x too early and the server obligingly gives you it, which is
        what made this endpoint look broken (issue #7).
        """
        return self._post(
            f"/api/v1/stream/s/{session_id}/seek",
            json_body={"position_ticks": position_ms * 10_000},
            params={"st": session_token},
        )

    def report_progress(
        self,
        session_id: str,
        session_token: str,
        position_ms: int,
        is_paused: bool,
        ended: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Every /stream/s/{session_id}/* endpoint is secured by
        `session_token` alone (not Bearer) and requires it as `?st=` --
        omitting it 400s with `missing field st` even with a valid Bearer
        token.

        TAKES MILLISECONDS and converts, exactly like seek_stream above and
        for the same reason: the wire field is `position_ticks`, 100-ns ticks,
        and this endpoint is on the STREAM side. Only /media/{id}/progress
        takes real milliseconds -- the two are one word apart in the API and
        were confused here for months.

        The symptom was not an error. The server accepts whatever arrives, so
        every heartbeat wrote a position 10,000x too small onto the PLAY
        SESSION record and the server's percentage of it floored at 0.
        Measured 2026-08-13 against the live server: Kodi's clock at 23m35s,
        the watch-history row reading `position_ms: 140` -- i.e. our 1,400,000
        milliseconds taken as 1,400,000 ticks. Every tofa client that gets
        this right showed a real percentage on the same page (mpv 35%, Apple
        TV 26%); every one of ours read 0%.

        Resume was never affected, which is why this hid: that is the OTHER
        endpoint, it really does take milliseconds, and it was always correct.
        """
        response = self._post(
            f"/api/v1/stream/s/{session_id}/progress",
            # The literal, not playback.TICKS_PER_MS: playback imports THIS
            # module, so naming it here would be a cycle. seek_stream above
            # spells it out for the same reason.
            json_body={"position_ticks": position_ms * 10_000,
                       "is_paused": is_paused, "ended": ended},
            params={"st": session_token},
            timeout=timeout,
            try_fallback=timeout is None,
            want_response=True,
        )
        self._absorb_rotated_profile_token(response)
        return http.body_of(response)

    def _absorb_rotated_profile_token(self, response: Any) -> None:
        """Take the slid profile token out of a heartbeat's response headers.

        Server 0.9.30: when a request to this endpoint carries an
        `X-Profile-Token` that is nearing expiry, the 204 answers with a
        replacement in `X-Profile-Token` plus its RFC 3339 expiry in
        `X-Profile-Token-Expires-At`. The sliding is not unlimited -- a day
        after the PIN was first typed it stops, and the pad comes back.
        Headers are absent otherwise, which is the common case: this costs a
        dict lookup on every heartbeat and does nothing.

        Why it matters: a profile token lasts ~4h with no refresh endpoint,
        and the failure when it lapses is not an error the viewer can read.
        The server answers 401 and the screens that ask "what has this
        profile watched" render as though the answer were "nothing". Sliding
        it while someone is demonstrably still watching is exactly the fix.

        Never raises. A heartbeat that fails to bank a rotation must still
        count as a heartbeat -- the position matters more than the token, and
        the token gets another chance in fifteen seconds.
        """
        try:
            headers = getattr(response, "headers", None) or {}
            rotated = headers.get("X-Profile-Token")
            if not rotated:
                return
            expires_at = _rfc3339_epoch(headers.get("X-Profile-Token-Expires-At"))
            self.profile_token = rotated
            auth.save_rotated_profile_token(rotated, expires_at)
            log.info("api: profile token rotated by the server, unlock slid")
        except Exception as exc:                                # noqa: BLE001
            log.debug(f"api: could not bank a rotated profile token: {exc!r}")

    def report_stopped(self, session_id: str, session_token: str) -> Any:
        return self._post(f"/api/v1/stream/s/{session_id}/stopped", params={"st": session_token})

    def end_session(self, session_id: str, session_token: str) -> Any:
        return self._delete(f"/api/v1/stream/s/{session_id}", params={"st": session_token})


def direct_only_addresses(server: str, fallback: str | None) -> tuple[str, str | None]:
    """(base, fallback) with the relay taken out, when the viewer asked for
    direct connections only.

    Refusing the FALLBACK is not enough on its own. Pairing probes the LAN
    address and stores `(local, remote)` when it answers -- but when it does
    not, the order flips and the RELAY becomes the primary
    (signin._pick_server_address). A gate that only guards the fallback then
    guards nothing, because the relay is the address every call already uses.

    So: prefer a direct address if either slot holds one, and drop the relay
    entirely rather than leave it as a fallback to fall into. If BOTH are the
    relay there is nothing direct to offer and both come back unchanged --
    _request refuses the call itself, which is what "even if it is the only
    way" has to mean.
    """
    if not auth.direct_only():
        return server, fallback
    if auth.is_relay_url(server) and fallback and not auth.is_relay_url(fallback):
        return fallback, None
    if auth.is_relay_url(fallback):
        return server, None
    return server, fallback


def client_for(session, tok) -> MediaServerClient:
    """A client carrying everything auth.Tokens knows about how to reach the
    server as this profile.

    One constructor call, because there were seven copies of it -- addon.py,
    prefetch.py, monitor.py, theme.py and three windows -- and adding
    `profile_token_expires_at` to the client meant every one of them had to
    learn the new field or silently keep a client that believes its token
    never expires. That is precisely the bug this field exists to fix, so the
    copies had to go with it.
    """
    base, fallback = direct_only_addresses(tok.server, tok.server_fallback)
    return MediaServerClient(
        session,
        base,
        tok.access_token,
        tok.device_id,
        fallback_base_url=fallback,
        profile_id=tok.profile_id,
        profile_token=tok.profile_token,
        profile_token_expires_at=tok.profile_token_expires_at,
    )
