# -*- coding: utf-8 -*-
"""Kodi's texture cache, restricted to the rows this add-on put there.

WHY THIS EXISTS
===============

Kodi caches every remote image it is asked to draw: a row in `Textures*.db`
plus a resized, re-encoded copy under `userdata/Thumbnails/`. It has no
eviction of its own before **Kodi 22**, which added `CImageCacheCleaner` --
a timer that drops cached images no library still references. Measured
2026-08-12, that split our devices:

    dev laptop          Kodi 21.3        Textures13   no cleaner
    4K CoreELEC box     Kodi 22.0-BETA1  schema 14    CLEANS ITSELF
    AM6B+ CoreELEC box  Kodi 21.3-p3i    Textures13   no cleaner
    Android TV box      Kodi 21.2        Textures13   no cleaner

Three of four will never collect anything. And they have something to
collect: before `artcache` existed every image was cached under a URL
carrying the hourly `?st=` token, so a rotation orphaned the lot. The cinema
box was still holding **1796 such rows for 555 distinct images** -- 3.2x
duplication, one poster stored 23 times.

THE ONE RULE
============

**Never remove a row this add-on did not create.** The database is shared
with the skin, every other add-on and Kodi's own library, and a texture id
carries nothing that says who asked for it. So ownership is decided from the
URL alone, by `classify()` below, and anything it cannot positively identify
as ours is left alone. `remove()` re-checks before deleting rather than
trusting a caller's list, because the only irreversible mistake available
here is deleting someone else's artwork.

`Textures.RemoveTexture` takes both halves with it -- verified 2026-08-12 on
Kodi 21.3 by removing one row and watching `Thumbnails/3/34364dc4.png`
(170 KB) disappear with it. So there is no separate file to tidy up, and no
reason to touch the sqlite file directly.

IN-PROCESS, NOT OVER HTTP
=========================

`xbmc.executeJSONRPC` builds a `CAddOnTransport` and calls
`CJSONRPC::MethodCall` directly (`ModuleXbmc.cpp`); it never reaches the web
server. So none of this depends on "Allow remote control via HTTP", which is
**off by default** in Kodi's shipped `settings.xml` and off on plenty of real
installs. The `tools/purge_texture_cache.py` companion speaks the same API
over HTTP because it runs from a dev machine, and that one does need the
setting.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Iterable, Optional

#: Our image API's shape, used to identify legacy rows cached under a
#: tokenised URL. Both halves are required and neither is generic: `st=` is
#: tofa's image-token parameter, and `/cache/images/` is the prefix
#: `resolve_image_url` builds. Matching on `st=` alone would be a substring
#: of any number of unrelated query strings.
_LEGACY_MARKERS = ("st=", "/cache/images/")

#: What `classify()` returns. Anything else is not ours.
STAGED = "staged"      # references a file in our staging directory
LEGACY = "legacy"      # a pre-artcache row keyed on a rotating token


def _log(level: str, msg: str) -> None:
    """Lazily, so this module stays importable without Kodi for the checks."""
    try:
        from . import log as _l
        getattr(_l, level)(msg)
    except Exception:                                       # noqa: BLE001
        pass


def _rpc(method: str, params: Optional[dict] = None):
    import xbmc

    raw = xbmc.executeJSONRPC(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}))
    answer = json.loads(raw)
    if "error" in answer:
        raise RuntimeError("%s: %s" % (method, answer["error"]))
    return answer.get("result")


def normalise(url: str) -> str:
    """A texture URL in a form the ownership tests can read.

    Kodi stores art two ways and both turn up in the same table: the plain
    reference it was given, and an `image://<percent-encoded>/` wrapper added
    by whichever loader ingested it. Sampled from the cinema box:

        image://%2fstorage%2f.kodi%2fuserdata%2faddon_data%2fplugin.video
                .tofa%2fartcache%2fimages_posters_4811731e7cc385af.jpg/
        image://http%3a%2f%2f192.168.1.50%3a33333%2fcache%2fimages%2f
                posters%2f4811731e7cc385af.jpg%3fst%3deyJ0eXAi...

    Encoded ONCE, so unquote once -- matching what the wrapper applies rather
    than decoding until nothing changes, which would happily turn a literal
    `%2f` inside a name into a path separator.
    """
    text = url or ""
    if text.startswith("image://"):
        text = text[len("image://"):].rstrip("/")
    return urllib.parse.unquote(text)


def classify(url: str, staging_dir: str,
             hosts: Optional[Iterable[str]] = None) -> Optional[str]:
    """`STAGED`, `LEGACY`, or None for a row that is not ours to touch.

    STAGED is unambiguous: the path contains our own staging directory, which
    is under `addon_data/plugin.video.tofa`. Nothing else on the system can
    produce it.

    LEGACY needs `hosts`, and needs ALL of: our media server's host, our
    image path prefix, and the image-token parameter. The host list is the
    part that does the real work -- without it a `/cache/images/...?st=`
    shape could in principle belong to another client talking to some other
    server, so when no hosts are known this returns None rather than
    guessing. Being wrong in that direction costs a row that stays; being
    wrong the other way deletes someone else's artwork.
    """
    if not url or not staging_dir:
        return None
    text = normalise(url)
    if staging_dir.rstrip("/") + "/" in text:
        return STAGED
    if not hosts:
        return None
    if not all(marker in text for marker in _LEGACY_MARKERS):
        return None
    host = urllib.parse.urlparse(text).netloc
    return LEGACY if host and host in set(hosts) else None


def rows(staging_dir: str, hosts: Optional[Iterable[str]] = None,
         kinds: Iterable[str] = (STAGED, LEGACY)) -> list[tuple[int, str, str]]:
    """Our texture rows as `(textureid, url, kind)`.

    Everything is fetched and filtered here rather than through the API's
    own `filter`, because the filter matches the STORED url and ours may be
    percent-encoded inside an `image://` wrapper -- a `contains` test against
    a decoded path would miss exactly the rows we want. The table is small
    enough that this is not worth being clever about: 2438 rows came back in
    22ms on the cinema box.
    """
    wanted = set(kinds)
    found = []
    try:
        result = _rpc("Textures.GetTextures", {"properties": ["url"]}) or {}
    except Exception as exc:                                # noqa: BLE001
        _log("warning", f"texturedb: could not read the texture cache ({exc!r})")
        return found
    for row in result.get("textures") or []:
        kind = classify(row.get("url", ""), staging_dir, hosts)
        if kind in wanted:
            found.append((row.get("textureid"), row.get("url", ""), kind))
    return found


def remove(textureid: int, url: str, staging_dir: str,
           hosts: Optional[Iterable[str]] = None) -> bool:
    """Delete one row, re-checking ownership first.

    The re-check is not redundant. A caller holds a list that was true when
    it was built, and ids are reused as rows come and go; this is the last
    point before something is irreversibly deleted, so it asks again rather
    than trusting the list.
    """
    if textureid is None or classify(url, staging_dir, hosts) is None:
        return False
    try:
        _rpc("Textures.RemoveTexture", {"textureid": int(textureid)})
        return True
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"texturedb: could not remove texture {textureid} ({exc!r})")
        return False


def forget(names: Iterable[str], staging_dir: str) -> int:
    """Drop the rows referencing these staging FILENAMES. Returns how many.

    This is what keeps the two halves in step. When the sweep deletes a
    staged file, any Kodi row still pointing at it describes something that
    is no longer there -- Kodi would go on drawing it from its own copy,
    which is a second copy of a picture we have just decided not to keep. So
    the file and the row go together.

    Filenames, not paths, because that is what the sweep has in hand and the
    stored URL may be wrapped and encoded around it.
    """
    targets = {n for n in names if n}
    if not targets:
        return 0
    gone = 0
    for textureid, url, _kind in rows(staging_dir, kinds=(STAGED,)):
        if normalise(url).rsplit("/", 1)[-1] in targets:
            gone += remove(textureid, url, staging_dir)
    return gone


def purge(staging_dir: str, hosts: Optional[Iterable[str]] = None) -> int:
    """Remove every row that is ours. Returns how many went.

    Behind the explicit Settings action, so it is allowed to be blunt: what
    it costs is re-downloading the artwork actually on screen next time, and
    what it buys is a way out when the cache is the suspect.
    """
    gone = 0
    for textureid, url, _kind in rows(staging_dir, hosts):
        gone += remove(textureid, url, staging_dir, hosts)
    if gone:
        _log("info", "texturedb: removed %d texture row(s)" % gone)
    return gone
