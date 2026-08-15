# -*- coding: utf-8 -*-
"""What lands in the published zip, and what must never.

The add-on zip is built by WALKING THE WORKING TREE, not by asking git. So
every untracked file in the tree is a candidate for a stranger's download,
and the ones that matter most are exactly the ones git stays quiet about:
`.DS_Store` is gitignored, so `git status` is clean while three of them sit
in the tree waiting to be packaged. Two were inside the 0.9.2 zip when this
was written.

Checks the REAL add-on tree, not a fixture, because the failure being
guarded against is a file appearing in that tree between releases.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import release  # noqa: E402  (tools/, not the add-on -- no Kodi stubs needed)

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
    j = os.path.join

    # --- the rule itself, at root and nested; a suffix match cannot do this
    check("a .DS_Store at the add-on root is skipped",
          release._should_skip(".DS_Store"))
    check("...and one buried in the skin is skipped",
          release._should_skip(j("resources", "skins", "Main", ".DS_Store")))
    check("Thumbs.db is skipped", release._should_skip("Thumbs.db"))
    check("bytecode is still skipped", release._should_skip("service.pyc"))
    check("__pycache__ is still skipped",
          release._should_skip(j("resources", "__pycache__", "x.py")))
    check("a merge leftover is still skipped",
          release._should_skip(j("resources", "lib", "api.py.orig")))
    check("an ordinary module is NOT skipped",
          not release._should_skip(j("resources", "lib", "api.py")))
    check("a file merely CONTAINING the name is not skipped",
          not release._should_skip(j("resources", "DS_Store_notes.txt")))

    # --- and what the real tree would ship right now
    shipped = release.package_files()
    arcnames = [arc for _path, arc in shipped]

    junk = [a for a in arcnames if os.path.basename(a) in release.EXCLUDE_NAMES]
    check("the real add-on tree ships no desktop-database junk", not junk,
          str(junk))

    stray = [a for a in arcnames if not a.startswith("plugin.video.tofa" + os.sep)]
    check("everything sits under the add-on id, not the zip root", not stray,
          str(stray[:3]))

    check("addon.xml itself ships",
          j("plugin.video.tofa", "addon.xml") in arcnames)
    check("the zip is not empty", len(shipped) > 500, str(len(shipped)))

    missing = [p for p, _a in shipped if not os.path.exists(p)]
    check("every listed source path exists", not missing, str(missing[:3]))

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("package contents: no junk, correct layout (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
