# -*- coding: utf-8 -*-
"""Persisted state must survive being written twice -- on Windows too.

`auth.save()`, `auth.save_image_token()` and `search_history` all wrote
`<file>.tmp` and then `xbmcvfs.rename(tmp, path)`. That is an atomic replace
on POSIX and a **silent no-op on Windows**, where renaming onto an existing
name fails. `xbmcvfs.rename` returns a bool and every caller ignored it, so
after the first write the real file never changed again.

Measured on a Windows 11 install 2026-08-16, right after choosing a profile:

    tokens.json      1486 bytes  23:10   profile_id: (empty)
    tokens.json.tmp  1520 bytes  23:23   profile_id: 0768eb9d-...

Visible symptom: the profile picker reopened for ever. Unseen and worse:
`auth.save()` is also how a REFRESHED token pair is stored, and reusing a
retired refresh token revokes the whole session family.

The behaviour half of this file passes on the OLD code on POSIX, because
rename() overwrites there -- nothing that runs on a Mac or in CI could have
caught this. The STRUCTURAL check is the one that matters, so it is written
against the AST rather than grepped.
"""
import ast
import os
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kodi_stubs  # noqa: F401,E402

ADDON = HERE.parent / "plugin.video.tofa"
sys.path.insert(0, str(ADDON))
from resources.lib import atomicwrite  # noqa: E402

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def _calls(path: pathlib.Path):
    """Every `a.b(...)` call name in a module, from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and isinstance(n.func.value, ast.Name):
            out.add(f"{n.func.value.id}.{n.func.attr}")
    return out


def main():
    # --- structural: nothing may persist via xbmcvfs.rename any more
    for mod in ("auth.py", "search_history.py", "atomicwrite.py"):
        p = ADDON / "resources" / "lib" / mod
        check(f"{mod} never calls xbmcvfs.rename",
              "xbmcvfs.rename" not in _calls(p),
              "silently fails on Windows when the target exists")

    check("atomicwrite uses os.replace",
          "os.replace" in _calls(ADDON / "resources" / "lib" / "atomicwrite.py"),
          "os.replace is atomic AND overwrites on both POSIX and Windows")

    # --- behaviour: writing twice must actually change the file
    tmpdir = tempfile.mkdtemp()
    try:
        target = os.path.join(tmpdir, "tokens.json")
        atomicwrite.write_json(target, {"profile_id": None, "n": 1})
        first = pathlib.Path(target).read_text()
        check("first write lands", '"n": 1' in first)

        atomicwrite.write_json(target, {"profile_id": "abc-123", "n": 2})
        second = pathlib.Path(target).read_text()
        check("SECOND write replaces the first", '"n": 2' in second, second[:80])
        check("...and the new value is really there", "abc-123" in second)

        leftovers = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
        check("no .tmp is left stranded", not leftovers, str(leftovers))

        # ten writes in a row, the shape a token refresh actually has
        for i in range(10):
            atomicwrite.write_json(target, {"n": i})
        check("repeated writes all land",
              '"n": 9' in pathlib.Path(target).read_text())
        check("...still no .tmp left",
              not [f for f in os.listdir(tmpdir) if f.endswith(".tmp")])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("atomic replace: second write wins, on every platform (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
