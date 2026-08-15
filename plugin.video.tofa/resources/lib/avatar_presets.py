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

The add-on ships no avatar artwork at all, so it redistributes none. The 44
current avatars are first-party pixel art generated in-house with no
third-party licence (tofa, issue #5, 2026-08-12); a profile still holding a
retired id falls back to initials, which is what this module answers for any
id the server does not know.

THE CATALOGUE IS AN API NOW (0.9.30), which is why this module no longer
scrapes the web app's JS bundle for it. `GET /api/v1/profiles/avatars`
answers `{"ids": [...]}` and `GET /api/v1/profiles/avatars/<id>.png` serves
one. This is the endpoint we were told to wait for rather than build a third
workaround around, and it removes the app.tofa.tv dependency entirely: the
catalogue now comes from the same server as everything else, so it works on
a connection that never reaches tofa's web app.

The old module's docstring said "if a stable URL ever exists, this whole
module collapses into one f-string". It nearly does. What stops it is auth.

WHY THIS STAGES THE FILE INSTEAD OF HANDING KODI THE URL. Measured against
0.9.30 on 2026-08-15, the same asset:

    direct LAN     GET .../avatars/fox.png  with no headers  -> 200 image/png
    cloud relay    GET .../avatars/fox.png  with no headers  -> 401
    cloud relay    GET .../avatars/fox.png  with Bearer      -> 200

So the asset is only tokenless on a DIRECT connection. Kodi's texture loader
sends none of our headers, so handing it the URL works at home and answers
401 on the relay -- every profile silently back to initials, which is exactly
the failure the previous version's app.tofa.tv fallback existed to fix. We
fetch it ourselves with the session's token and hand Kodi a LOCAL PATH, which
is correct on both routes and, as a bonus, is a reference that never changes
-- the same reason artcache exists. (artcache itself is not the vehicle: its
session deliberately carries no bearer, because art URLs self-authenticate
with `?st=`, and these do not.)

REVALIDATION. A local copy that never expires would break the one promise
this module makes -- "an avatar changed server-side appears on the next
launch". The endpoint serves an ETag, so a staged file is revalidated with
`If-None-Match` at most every `_RECHECK_SECONDS`; a 304 costs a few hundred
bytes and keeps the file. Only ids actually being drawn are ever checked,
which for this household is two or three.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import xbmcaddon
import xbmcvfs

from . import log

_CACHE_FILE = "avatar_presets.json"
_ASSET_DIR = "avatars"

#: Don't re-check the catalogue, or revalidate a staged PNG, more often than
#: this. The profile picker and the nav avatar both ask, and a switch between
#: them should not cost a request each time.
_RECHECK_SECONDS = 300

_memory: Optional[dict] = None


def _profile_dir() -> str:
    profile = xbmcvfs.translatePath(
        xbmcaddon.Addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(profile)
    return profile


def _cache_path() -> str:
    return os.path.join(_profile_dir(), _CACHE_FILE)


def _asset_dir() -> str:
    path = os.path.join(_profile_dir(), _ASSET_DIR)
    xbmcvfs.mkdirs(path)
    return path


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


def _auth(access_token: Optional[str]) -> dict:
    return {"Authorization": "Bearer %s" % access_token} if access_token else {}


def _catalogue(session, server: str, access_token: Optional[str],
               cache: dict) -> list:
    """The ids this server can serve, re-read at most every recheck window.

    An id absent from it draws initials without a request, which is what the
    spec asks for and what a retired preset needs.
    """
    fresh = (time.time() - float(cache.get("checked_at") or 0)
             <= _RECHECK_SECONDS)
    if fresh and cache.get("server") == server and cache.get("ids") is not None:
        return cache.get("ids") or []
    try:
        response = session.get(server + "/api/v1/profiles/avatars",
                               headers=_auth(access_token), timeout=15)
        if response.status_code != 200:
            # Logged, because a SILENT failure here is what made the proxy
            # case take an afternoon to find last time: no catalogue, no
            # avatars, and not one line anywhere saying why.
            log.debug("avatar_presets: catalogue answered %d"
                      % response.status_code)
            return cache.get("ids") or []
        ids = (response.json() or {}).get("ids")
        if not isinstance(ids, list) or not ids:
            # Do NOT clear a working catalogue: tofa has changed this shape
            # once already (inline SVG -> PNG), and yesterday's ids beat none.
            log.warning("avatar_presets: catalogue had no ids; keeping the "
                        "previous one")
            return cache.get("ids") or []
    except Exception as exc:                       # network, DNS, TLS, JSON
        log.debug(f"avatar_presets: catalogue fetch failed: {exc!r}")
        return cache.get("ids") or []

    log.info("avatar_presets: %d presets from %s" % (len(ids), server))
    cache.update({"server": server, "ids": ids, "checked_at": time.time()})
    _write_cache(cache)
    return ids


def _stage(session, server: str, access_token: Optional[str], name: str,
           cache: dict) -> str:
    """Fetch `<id>.png` into the add-on profile and answer its local path.

    Returns "" on any failure, so the caller draws initials rather than a
    broken image.
    """
    path = os.path.join(_asset_dir(), "%s.png" % name)
    etags = cache.setdefault("etags", {})
    seen = cache.setdefault("validated_at", {})
    have = os.path.exists(path)
    if have and (time.time() - float(seen.get(name) or 0) <= _RECHECK_SECONDS):
        return path

    headers = _auth(access_token)
    if have and etags.get(name):
        headers["If-None-Match"] = etags[name]
    try:
        response = session.get(
            "%s/api/v1/profiles/avatars/%s.png" % (server, name),
            headers=headers, timeout=15)
        if response.status_code == 304 and have:
            seen[name] = time.time()
            _write_cache(cache)
            return path
        if response.status_code != 200 or not response.content:
            log.debug("avatar_presets: %s.png answered %d"
                      % (name, response.status_code))
            return path if have else ""
        # Atomic, for the same reason artcache is: a half-written file under
        # the real name is a blank avatar that nothing would ever correct,
        # because the next visit would see the path exist and use it.
        tmp = "%s.%d.part" % (path, os.getpid())
        with open(tmp, "wb") as handle:
            handle.write(response.content)
        os.replace(tmp, path)
        if response.headers.get("ETag"):
            etags[name] = response.headers["ETag"]
        seen[name] = time.time()
        _write_cache(cache)
        return path
    except Exception as exc:                       # network, disk, ...
        log.debug(f"avatar_presets: staging {name} failed: {exc!r}")
        return path if have else ""


def url_for(session, server: Optional[str], avatar_ref: Optional[str],
            access_token: Optional[str] = None) -> str:
    """`"preset:knight"` -> something Kodi can draw, or `""`.

    `""` means "draw the monogram", which is what every caller does, and is
    the right answer for an unknown id as well as an unreachable server -- a
    retired preset must fall through exactly the way tofa's own clients show
    it.

    `access_token` is not optional in practice, only in signature: without it
    this works on a direct LAN connection and answers "" on the cloud relay,
    which is a difference no caller wants to discover in the field. It
    defaults to None so a caller that genuinely has no token still gets the
    LAN behaviour rather than a TypeError.
    """
    if not server or not avatar_ref or not avatar_ref.startswith("preset:"):
        return ""
    name = avatar_ref[len("preset:"):]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return ""                       # never let a ref name a path
    server = server.rstrip("/")
    cache = _read_cache()
    ids = _catalogue(session, server, access_token, cache)
    if ids and name not in ids:
        return ""
    return _stage(session, server, access_token, name, cache)


def clear() -> None:
    """Drop the cache and the staged art. For tests and for a server change."""
    global _memory
    _memory = None
    path = _cache_path()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
    directory = os.path.join(_profile_dir(), _ASSET_DIR)
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        try:
            os.remove(os.path.join(directory, name))
        except OSError:                             # in use, gone already
            pass
