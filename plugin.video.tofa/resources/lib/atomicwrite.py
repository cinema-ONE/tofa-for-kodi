"""Write a small file so a reader never sees it half-written -- on Windows too.

Three places wrote `<file>.tmp` and then called `xbmcvfs.rename(tmp, path)`.
That is an atomic replace on POSIX and a **silent no-op on Windows**, where
renaming onto an existing name fails (`MoveFile` without
`MOVEFILE_REPLACE_EXISTING`). `xbmcvfs.rename` returns a bool and every
caller ignored it, so the new content stayed in the `.tmp` for ever and the
real file never changed.

Proved on a Windows 11 install 2026-08-16, after selecting a profile:

    tokens.json      1486 bytes  23:10   profile_id: (empty)
    tokens.json.tmp  1520 bytes  23:23   profile_id: 0768eb9d-...

The visible symptom was that the profile picker reopened for ever, because
nothing chosen was ever stored. The unseen half is worse: `auth.save()` is
also how a REFRESHED token pair is persisted, and reusing a retired refresh
token revokes the whole session family (see auth's module docstring). A
Windows install therefore could not hold on to any credential it rotated.

`os.replace` is the fix: atomic on POSIX, and on Windows it maps to
`MoveFileEx(..., MOVEFILE_REPLACE_EXISTING)`, which is also atomic. Both
paths here are already real filesystem paths -- the add-on's profile dir
comes back from `xbmcvfs.translatePath` -- so it never sees a `special://`
URL. Guard anyway rather than assume.
"""
from __future__ import annotations

import json
import os

import xbmcvfs

from . import log


def write_json(path: str, data) -> None:
    """Serialise `data` to `path`, replacing any existing file atomically."""
    write_text(path, json.dumps(data, indent=2))


def write_text(path: str, text: str) -> None:
    tmp = path + ".tmp"
    f = xbmcvfs.File(tmp, "w")
    try:
        f.write(text)
    finally:
        f.close()
    try:
        os.replace(tmp, path)
    except OSError as exc:
        # Never leave the .tmp behind to be mistaken for real state later,
        # and never fail silently the way xbmcvfs.rename did.
        log.error(f"atomicwrite: could not replace {path}: {exc!r}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
