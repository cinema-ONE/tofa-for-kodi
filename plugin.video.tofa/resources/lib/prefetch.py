# -*- coding: utf-8 -*-
"""Do the launch's HTTP work while the splash is still on screen.

WHY. A cold start used to run end to end: ~2.3s of splash animation in which
nothing happened, and only then MainWindow opening and making about ten
serial HTTP calls -- a token refresh, whoami, and one per Home row -- which
took another second with an empty nav bar on screen. Measured on the
development box: splash at 0.77s, window at 3.19s, rows at 4.01s.

The two do not depend on each other, so they run at the same time now. The
launch shows the splash, calls warm() while the animation plays, waits out
whatever is left of it, and only then opens MainWindow -- which finds the
answers already here and paints populated. The splash stops being dead time
and starts being the cover for the work.

WHY IT IS NOT A THREAD. The splash's animation is declarative (Kodi renders
it from the XML on its own thread), so the launch script is simply idle
during it. Doing the fetching on that idle thread needs no concurrency at
all, and nothing here touches the GUI.

WHY IT NEVER PROMPTS. This runs behind a splash, where a profile picker or a
PIN pad would be at best confusing and at worst invisible. warm() therefore
bails out of anything that could put a dialog on screen and leaves it to
MainWindow, which is set up to ask properly. A launch that cannot be
prefetched is exactly as fast as it was before -- never slower.

EVERYTHING HERE IS BEST-EFFORT. A prefetch that fails is a slower start, not
a broken one: every consumer falls back to fetching for itself.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from . import api, auth, home_rows, http, log
from .api import MediaServerClient

#: Filled by warm(), drained by the window as it builds.
_client: Optional[MediaServerClient] = None
_preferences: Optional[dict] = None
_rows: dict[str, list] = {}
_warmed = False


class SuggestedItems(list):
    """The Suggested row's items, carrying the server's `personalized` flag
    (False on the cold-start fallback) so the row can be titled from it."""
    personalized: bool = True


def fetch_builtin_row(client: MediaServerClient, row_id: str) -> list:
    """The items for one builtin Home row.

    Lives here rather than on MainWindow so the prefetch and the window make
    the SAME call -- a second copy would be a way for the two to drift, and
    a prefetch that fetched something subtly different from what the row
    renders would be worse than no prefetch at all.
    """
    try:
        if row_id == "continue_watching":
            return client.continue_watching() or []
        if row_id == "suggested":
            resp = client.suggested() or {}
            if isinstance(resp, dict):
                # The flag rides with the items so the row can be titled
                # from it: the web app calls a non-personalised Suggested row
                # "Popular on Your Server", and so do we.
                items = SuggestedItems(resp.get("items") or [])
                items.personalized = resp.get("personalized") is not False
                return items
            return resp or []
        if row_id == "leaving_soon":
            # LeavingSoonItem is not a MediaSummary: its id is `media_id`,
            # and `delete_after` is what the card's caption shows. Mapped to
            # the card shape here so the row builder needs no special case.
            return [{"id": it.get("media_id"), "title": it.get("title") or "",
                     "media_type": it.get("media_type"),
                     "poster_path": it.get("poster_path"),
                     "delete_after": it.get("delete_after"), "available": True}
                    for it in (client.leaving_soon() or []) if isinstance(it, dict)]
        if row_id == "recent_movies":
            resp = client.media_list(media_type="movie", sort="added_at", order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "recent_tv":
            resp = client.media_list(media_type="tv", sort="added_at", order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "recently_released":
            # No media_type: the row deliberately mixes films and shows,
            # which is what distinguishes it from Recently Added.
            resp = client.media_list(media_type=None, sort="release_date",
                                     order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "recently_released_movies":
            resp = client.media_list(media_type="movie", sort="release_date",
                                     order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "recently_released_tv":
            resp = client.media_list(media_type="tv", sort="release_date",
                                     order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "top_rated_movies":
            resp = client.media_list(media_type="movie", sort="rating", order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
        if row_id == "top_rated_tv":
            resp = client.media_list(media_type="tv", sort="rating", order="desc", page=1, per_page=25)
            return (resp or {}).get("items") or []
    except http.ApiError as exc:
        log.warning(f"builtin row {row_id} failed: {exc}")
        return []
    return []


def warm() -> None:
    """Fetch what the first screen will ask for. Never prompts, never raises.

    Call it once, straight after the splash goes up and before the real
    window is opened.
    """
    global _client, _preferences, _warmed
    if _warmed:
        return
    _warmed = True
    started = time.monotonic()
    try:
        if not auth.is_signed_in():
            return
        session = http.new_session()
        tok = auth.ensure_fresh(session)

        # Mirrors profile_select.ensure_profile_selected()'s no-network fast
        # path, deliberately rather than calling it: every other branch of
        # that function can raise a profile picker or a PIN pad, and putting
        # one of those up behind a splash is not a trade worth a second of
        # start-up. When this bails, MainWindow does the whole thing
        # properly, exactly as it did before this module existed.
        if not tok.profile_id:
            log.debug("prefetch: no profile chosen yet; leaving it to the window")
            return
        if tok.profile_token and (tok.profile_token_expires_at or 0) <= time.time() + 30:
            log.debug("prefetch: profile token needs a PIN; leaving it to the window")
            return

        client = api.client_for(session, tok)
        preferences = ((client.whoami() or {}).get("preferences")) or {}
        # Published only once BOTH are in hand: a window that took the client
        # but had to fetch preferences itself would have gained nothing and
        # made the failure harder to see. The client is kept (it is reusable);
        # the preferences are consumed on first read -- see take_preferences.
        _client, _preferences = client, preferences

        # The same list Home will build -- the stored rows plus every default
        # the profile lacks -- so what gets warmed is what gets drawn.
        rows = home_rows.normalize_home_screen(preferences.get("home_screen"))["rows"]
        slots = 0
        for row in rows:
            if slots >= home_rows.MAX_HOME_ROWS:
                break
            if not row.get("enabled", True):
                continue
            slots += 1
            # Builtin rows only. Discovery rows share ONE call that is made
            # through the window's own capability check, and genre rows need
            # settings this module has no business reading -- both are left
            # to the window, which still benefits from the warm client.
            if row.get("type") != "builtin":
                continue
            row_id = row.get("id")
            if row_id and row_id in home_rows.BUILTIN_ROW_LABELS:
                _rows[row_id] = fetch_builtin_row(client, row_id)
        log.info("prefetch: %d row(s) in %.2fs"
                 % (len(_rows), time.monotonic() - started))
    except Exception as exc:                            # noqa: BLE001
        # Including auth.NotSignedIn and anything the network throws. A
        # prefetch is an optimisation; the window re-does all of it.
        log.debug(f"prefetch: skipped ({exc!r})")


def client() -> Optional[MediaServerClient]:
    """The warmed client, or None. Not consumed -- the window keeps it."""
    return _client


def discard_client() -> None:
    """Throw the warmed client away, for when the thing it is bound to has
    changed underneath it.

    Because client() is NOT consumed, a caller that drops its own reference
    (`self.client = None`, the standard way to force a rebuild) gets this
    one handed straight back instead -- still carrying the token, server
    address and profile headers it was built with at launch. That is
    harmless while those stay true and wrong the moment they don't: after a
    sign-out it 401s, and after a server switch it talks to the old
    server."""
    global _client
    _client = None


def take_preferences() -> Optional[dict]:
    """The warmed preferences blob, ONCE, or None.

    CONSUMED, like take_row, and for a sharper reason. A window re-reads its
    preferences after writing one, by dropping its cached copy and asking
    again; if this kept handing back the blob captured at launch, that
    re-read would return the OLD values for the life of the window and every
    settings change would appear not to save. It did exactly that between
    fc59a6e and this fix.

    So the prefetch answers the first question and then gets out of the way:
    anything after that is a real fetch, which is what a caller re-reading
    has asked for.
    """
    global _preferences
    value, _preferences = _preferences, None
    return value


def take_row(row_id: str) -> Optional[list]:
    """The prefetched items for a row, ONCE, or None.

    Consumed rather than cached: this exists to make the first paint quick,
    and a later reload of Home means the viewer wants current data, not what
    the launch happened to see.
    """
    return _rows.pop(row_id, None)


def reset() -> None:
    """Drop everything warmed at launch.

    Two callers. Tests, where a real launch would be one process; and any
    change of IDENTITY -- switching profile, or signing out and back in --
    after which nothing captured at launch describes the viewer any more.

    That second one matters because `client()` is deliberately NOT consumed,
    so a window that drops its own client to force a re-fetch gets the warmed
    one straight back. On a profile switch that client still carries the
    PREVIOUS profile's token, so every section faithfully re-fetched and got
    the old profile's rows -- Continue Watching most visibly, since it is the
    row a viewer checks first after switching.
    """
    global _client, _preferences, _warmed
    _client = None
    _preferences = None
    _rows.clear()
    _warmed = False
