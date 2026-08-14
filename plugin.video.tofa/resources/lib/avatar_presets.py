# -*- coding: utf-8 -*-
"""Resolve `preset:<id>` to the server's own avatar artwork, at display time.

WHY NOT BUNDLE IT, which is what this add-on did until 0.9.29: because the
set changes and we do not. tofa replaced twelve avatars with forty-four,
retired six ids, and swapped the delivery mechanism (inline SVG data URIs
became PNG files) in a single release. Bundled art was 2.4MB of which this
household draws four, it was stale the day the server updated, and every
future change needed a client release to catch up. Adrian's requirement,
2026-08-11: "I want to avoid the add-on getting out-of-date again when the
server-side avatars change."

We also never offer an avatar PICKER -- nothing here writes `avatar_ref`,
you choose on the web or on Apple TV -- so the only artwork we ever need is
for the handful of profiles that exist.

Two useful consequences:

* The add-on ships no avatar artwork at all, so it redistributes none. The
  set this replaces was Microsoft's Fluent Emoji path for path, and the
  provenance of the new one is undocumented; not shipping it makes the
  question moot for the public release (issue #5).
* An avatar changed server-side appears on the next launch.

THE URL IS NOT DISCOVERABLE FROM THE API. There is no catalogue endpoint --
`/profiles/avatars` answers 405 to a GET -- and no stable per-id path;
`/api/v1/profiles/avatars/knight.png` and every variant of it 404. The only
published list is the web app's own JS bundle, which is also where the
language lists came from (see settings_options). Filed as a gap on issue #7;
if a stable URL ever exists, this whole module collapses into one f-string.

The assets themselves are PUBLIC -- no Authorization header, served
`immutable` with a year-long max-age -- so Kodi can be handed the URL
directly and will cache the texture itself. That is why this returns a URL
rather than bytes.

CACHING. The bundle is ~230KB and the filenames carry a content hash, so
re-reading it on every profile screen would be silly and hard-coding the
hashes would be wrong. The cache is keyed on the ENTRY CHUNK's name, which
is itself content-hashed: fetching the 5KB index page tells us whether the
web app has been rebuilt, and only then do we re-read the bundle. A server
update therefore costs one small request, not one large one.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, Optional

import xbmcaddon
import xbmcvfs

from . import log

#: {id:`knight`,label:`Knight`,src:`/assets/knight-B8YibGO5.png`,pixel:!0}
_ENTRY = re.compile(
    r'\{id:`([a-z0-9_-]+)`,label:`[^`]*`,src:`(/assets/[^`]+)`,pixel:!0\}')
_ENTRY_CHUNK = re.compile(r'src="(/assets/index-[^"]+\.js)"')

_CACHE_FILE = "avatar_presets.json"

#: Don't re-check the index page more than this often. The profile picker
#: and the nav avatar both ask, and a switch between them should not cost a
#: request each time.
_RECHECK_SECONDS = 300

_memory: Optional[dict] = None


def _cache_path() -> str:
    profile = xbmcvfs.translatePath(
        xbmcaddon.Addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(profile)
    return os.path.join(profile, _CACHE_FILE)


def _read_cache() -> dict:
    global _memory
    if _memory is not None:
        return _memory
    path = _cache_path()
    if xbmcvfs.exists(path):
        handle = xbmcvfs.File(path)
        try:
            raw = handle.read()
        finally:
            handle.close()
        try:
            loaded = json.loads(raw or "{}")
            if isinstance(loaded, dict):
                _memory = loaded
                return _memory
        except ValueError:
            log.debug("avatar_presets: cache unreadable, rebuilding")
    _memory = {}
    return _memory


def _write_cache(data: dict) -> None:
    global _memory
    _memory = data
    handle = xbmcvfs.File(_cache_path(), "w")
    try:
        handle.write(json.dumps(data))
    finally:
        handle.close()


def _fetch(session, url: str) -> Optional[str]:
    try:
        response = session.get(url, timeout=15)
        if response.status_code != 200:
            return None
        return response.text
    except Exception as exc:                       # network, DNS, TLS, ...
        log.debug(f"avatar_presets: fetch {url} failed: {exc!r}")
        return None


def _refresh(session, server: str, cache: dict) -> dict:
    """Re-read the catalogue if the web app has been rebuilt.

    Cheap in the common case: one 5KB page, and the ~230KB bundle only when
    its hash has actually moved."""
    index = _fetch(session, server + "/")
    if not index:
        return cache
    found = _ENTRY_CHUNK.search(index)
    if not found:
        log.warning("avatar_presets: no entry chunk in the web app index")
        return cache
    chunk = found.group(1)
    cache["checked_at"] = time.time()
    if cache.get("chunk") == chunk and cache.get("presets"):
        _write_cache(cache)
        return cache
    bundle = _fetch(session, server + chunk)
    if not bundle:
        return cache
    presets = {name: src for name, src in _ENTRY.findall(bundle)}
    if not presets:
        # Do NOT clear a working cache: tofa has changed this shape once
        # already (inline SVG -> PNG), and yesterday's URLs beat none.
        log.warning("avatar_presets: no entries found -- tofa changed the "
                    "bundle shape again; keeping the previous catalogue")
        _write_cache(cache)
        return cache
    log.info(f"avatar_presets: {len(presets)} presets from {chunk}")
    cache = {"chunk": chunk, "presets": presets, "checked_at": time.time()}
    _write_cache(cache)
    return cache


def url_for(session, server: Optional[str], avatar_ref: Optional[str]) -> str:
    """`"preset:knight"` -> a directly loadable URL, or `""`.

    `""` means "draw the monogram", which is what every caller does, and is
    the right answer for an unknown id as well as an unreachable server --
    a retired preset (0.9.29 dropped six) must fall through exactly the way
    tofa's own clients show it."""
    if not server or not avatar_ref or not avatar_ref.startswith("preset:"):
        return ""
    name = avatar_ref[len("preset:"):]
    server = server.rstrip("/")
    cache = _read_cache()
    presets = cache.get("presets") or {}
    stale = (time.time() - float(cache.get("checked_at") or 0)
             > _RECHECK_SECONDS)
    # Re-read when we have never read, when the id is one we do not know
    # (a NEW preset -- the case this module exists for), or periodically.
    #
    # "Re-read" means the 5KB index, NOT the 230KB bundle: _refresh goes on
    # to the bundle only when the entry chunk's hash has actually moved. A
    # new preset always arrives with a rebuilt web app, so that is the real
    # signal; an unknown id under an unchanged build is a retired or bogus
    # one and must not cost a bundle download every time it is drawn.
    if not presets or name not in presets or stale:
        cache = _refresh(session, server, cache)
        presets = cache.get("presets") or {}
    src = presets.get(name)
    return server + src if src else ""


def clear() -> None:
    """Drop the cache. For tests and for a server change."""
    global _memory
    _memory = None
    path = _cache_path()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
