# -*- coding: utf-8 -*-
"""fontinstall._is_writable must answer by TRYING, not by asking os.access.

It used to be `os.access(path, os.W_OK)`. That is correct on POSIX and a lie
on Windows, where it reports only the read-only file ATTRIBUTE and never
consults ACLs -- so `C:\\Program Files\\Kodi\\addons\\skin.estuary` answered
True. The copy-to-somewhere-writable fallback never ran, and both callers
died on the write itself:

    fontinstall: failed, continuing with default fonts:
      [Errno 13] Permission denied: '...\\skin.estuary\\fonts\\tofa_lucide-icons.ttf'
    seekbarpatch: failed, leaving the skin's seek bar in place:
      [Errno 13] Permission denied: '...\\skin.estuary\\xml\\DialogSeekBar.xml'

Found on a real Windows 11 install 2026-08-16. The user-visible half was that
the consent dialog re-asked on EVERY launch, because nothing it promised had
actually happened.

The behaviour test (a genuinely unwritable directory) only runs where the OS
can make one and where we are not root -- CI containers often run as root,
where nothing is unwritable. The rest runs everywhere.
"""
import os
import pathlib
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kodi_stubs  # noqa: F401,E402  (installs the xbmc* modules)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"))
from resources.lib import fontinstall  # noqa: E402

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def main():
    # --- it must not CALL os.access. That is the whole bug. Parsed rather
    #     than grepped, so this file's own prose about os.access -- and the
    #     docstring explaining why it is banned -- do not trip it.
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(fontinstall._is_writable))
    calls = {
        f"{n.func.value.id}.{n.func.attr}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
    }
    check("_is_writable does not CALL os.access", "os.access" not in calls,
          "os.access(W_OK) reports only the read-only attribute on Windows")
    check("...and probes by opening a file instead",
          any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "open" for n in ast.walk(tree)))

    # --- a writable directory answers True, and leaves nothing behind
    tmp = tempfile.mkdtemp()
    try:
        before = set(os.listdir(tmp))
        check("a writable dir answers True", fontinstall._is_writable(tmp))
        check("...and the probe file is cleaned up",
              set(os.listdir(tmp)) == before, str(set(os.listdir(tmp)) - before))

        # --- repeated calls must not collide with each other
        check("repeatable", all(fontinstall._is_writable(tmp) for _ in range(5)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- a path that does not exist is not writable (and must not raise)
    missing = os.path.join(tempfile.gettempdir(), "tofa-no-such-dir-abc123")
    check("a missing dir answers False, without raising",
          fontinstall._is_writable(missing) is False)

    # --- a genuinely unwritable directory. Root ignores mode bits, and
    #     Windows ignores chmod, so this one is conditional by necessity.
    can_test = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
    if can_test:
        locked = tempfile.mkdtemp()
        try:
            os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)  # r-x, no write
            check("an unwritable dir answers False", not fontinstall._is_writable(locked))
        finally:
            os.chmod(locked, stat.S_IRWXU)
            shutil.rmtree(locked, ignore_errors=True)
    else:
        print("SKIP  unwritable-dir check (needs POSIX and non-root)")

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("writable probe: answers by trying, not by asking (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
