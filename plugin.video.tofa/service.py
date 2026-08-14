#!/usr/bin/env python3
"""Background service: font install + token refresh + playback monitoring
(brief §2, §3, §8).

Runs for Kodi's whole lifetime, unlike addon.py which is a one-shot script
invocation per directory listing / play request -- registered as
<extension point="xbmc.service" .../> with start="startup" in addon.xml, so
this is the one thing guaranteed to run once whenever Kodi (and this add-on)
starts, regardless of which screen or entry point the user reaches first.
That makes it a good place to catch a first-ever install before the user
has done anything at all -- checked once here, before anything else; if it
triggers a restart (a version bump, or a first-ever install), there is
nothing left to usefully do in this process, so return immediately rather
than starting the monitor loop.

Deliberately redundant with the SECOND check in windows/kodigui.py's
BaseFunctions.open()/create() (every window class's own choke point): this
service only checks once per actual Kodi process start, so an in-place
add-on update (a FONT_SET_VERSION bump) applied without a full Kodi
restart would otherwise go unnoticed until the next one. The window-open
check catches it the moment the user next opens ANY tofa screen instead.
See fontinstall.py's own docstring for the full reasoning -- both callers
share the same cheap, idempotent function, so this isn't wasted duplicate
work in the common (already-current) case.

Three jobs share one Monitor.waitForAbort loop:

- keep the access token fresh well before its 30-day expiry (auth.ensure_fresh's
  fast path is a cheap local expiry check, safe to call every tick),
- drive TofaPlayer.tick() for the ~10s session-progress heartbeat (brief §8) --
  xbmc.Player's callbacks fire on their own regardless of this loop, this is
  only for the periodic-while-playing part, and
- sweep the artwork staging area back inside its disk budget.

The sweep lives here because this is the only part of the add-on with a
lifetime rather than an invocation. It used to be triggered from
artcache._submit(), which meant it ran on the first cache MISS in a process
and never again -- so the better staging worked, the less likely it was to
run at all, and it had never once fired on the dev machine's 2261 files.
"""
from __future__ import annotations

import time

import xbmc

from resources.lib import artcache, auth, hostsetup, http, log
from resources.lib.monitor import TofaPlayer

TICK_SECONDS = 10

#: Long enough that a cold start is never competing with the first screen for
#: disk. Nothing here is urgent: the budget is a ceiling measured in months of
#: browsing, not a queue that backs up.
SWEEP_FIRST_DELAY_S = 120

#: And then twice a day. NOT once per Kodi start -- the boxes run for weeks at
#: a time, so a startup-only sweep would effectively never fire on the devices
#: that most need it.
SWEEP_EVERY_S = 12 * 3600


def main() -> None:
    if hostsetup.ensure_host_setup():
        return

    kodi_monitor = xbmc.Monitor()
    session = http.new_session()
    player = TofaPlayer()
    sweep_due = time.monotonic() + SWEEP_FIRST_DELAY_S

    while not kodi_monitor.abortRequested():
        if auth.is_signed_in():
            try:
                auth.ensure_fresh(session)
            except auth.NotSignedIn:
                pass
            except http.ApiError as exc:
                log.warning(f"service: refresh failed: {exc}")
        player.tick()
        if time.monotonic() >= sweep_due:
            # Inline, not on a thread: it is a few thousand stat calls (8ms
            # for 2261 files, measured) and this loop has 10s to spare. A
            # thread here would only be one more thing for Kodi to wait on
            # at shutdown, which artcache's workers already taught us to
            # avoid.
            _sweep()
            sweep_due = time.monotonic() + SWEEP_EVERY_S
        if kodi_monitor.waitForAbort(TICK_SECONDS):
            break


def _sweep() -> None:
    """Never let a maintenance failure take the service down with it.

    This loop is also the token refresh and the playback heartbeat; tidying
    up artwork is the least important thing it does and must behave that way
    if the disk is full, read-only, or the directory has gone missing.
    """
    try:
        removed, freed = artcache.sweep()
        if removed:
            log.info("service: artwork sweep freed %.1f MB across %d file(s)"
                     % (freed / 1e6, removed))
        # And the rows Kodi cached under a rotating image token. Separate from
        # the file sweep because it collects something else: not our disk, but
        # the residue of the misses that batching cannot reach.
        artcache.sweep_texture_rows()
    except Exception as exc:                                # noqa: BLE001
        log.warning(f"service: artwork sweep failed: {exc!r}")


if __name__ == "__main__":
    main()
