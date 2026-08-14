"""Per-profile local search history.

The tofa server has no search-history endpoint (`/api/v1/search` is the
only search-related route) -- history is managed entirely client-side: one
JSON file in the add-on's own profile dir, keyed by profile_id so each
household profile (see windows/profile_select.py) gets its own list, same
storage convention as auth.py's tokens.json.
"""
from __future__ import annotations

import json
import os

import xbmcaddon
import xbmcvfs

MAX_ENTRIES = 10


def _addon() -> xbmcaddon.Addon:
    return xbmcaddon.Addon()


def _profile_dir() -> str:
    path = xbmcvfs.translatePath(_addon().getAddonInfo("profile"))
    xbmcvfs.mkdirs(path)
    return path


def _history_file_path() -> str:
    return os.path.join(_profile_dir(), "search_history.json")


def _load_all() -> dict:
    path = _history_file_path()
    if not xbmcvfs.exists(path):
        return {}
    f = xbmcvfs.File(path)
    try:
        raw = f.read()
    finally:
        f.close()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: dict) -> None:
    path = _history_file_path()
    tmp = path + ".tmp"
    f = xbmcvfs.File(tmp, "w")
    try:
        f.write(json.dumps(data, indent=2))
    finally:
        f.close()
    # Same atomic-replace convention as auth.save() -- xbmcvfs.rename maps
    # to a native rename() on local paths, so there's never a window where
    # the file is half-written or missing.
    xbmcvfs.rename(tmp, path)


def get(profile_id: str) -> list:
    """Most-recent-first list of past search queries for this profile, capped
    at MAX_ENTRIES.

    add() already caps on write, so the slice only matters for a file written
    by an older build with a higher cap -- but the Search screen sizes its
    list for exactly MAX_ENTRIES rows and clips whatever will not fit, so a
    long file would silently lose its tail rather than scroll."""
    return list(_load_all().get(profile_id, []))[:MAX_ENTRIES]


def clear(profile_id: str) -> None:
    """Forget every query for this profile. Other profiles are untouched --
    the file is shared, so this drops one key rather than the whole file."""
    if not profile_id:
        return
    data = _load_all()
    if data.pop(profile_id, None) is None:
        return
    _save_all(data)


def add(profile_id: str, query: str) -> None:
    """Record `query` as the newest entry for this profile. An existing
    case-insensitive duplicate moves to the front instead of adding a
    second copy; the list is capped at MAX_ENTRIES (oldest dropped)."""
    query = query.strip()
    if not profile_id or not query:
        return
    data = _load_all()
    entries = data.get(profile_id, [])
    entries = [e for e in entries if e.lower() != query.lower()]
    entries.insert(0, query)
    data[profile_id] = entries[:MAX_ENTRIES]
    _save_all(data)
