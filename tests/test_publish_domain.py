# -*- coding: utf-8 -*-
"""The CNAME file is what binds the domain to this repository.

GitHub Pages resolves a custom hostname to a REPO by the `CNAME` file in the
served tree, not by DNS -- every custom subdomain points at the same
`<user>.github.io`, because DNS has no notion of a path. So publishing a tree
without that file unbinds the domain: `kodi.cinemaone.ch` stops answering and
every install's update channel goes down, with nothing failing locally to say
so. It is generated from BASE_URL for exactly that reason, and checked here
because the failure is invisible until it is a stranger's problem.

The other half is that a LAN test build must never claim the domain. Building
with `--base-url http://<ip>:8000` and copying that tree anywhere near docs/
would write a CNAME for an IP address.
"""
import hashlib
import os
import pathlib
import sys
import tempfile

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


EMPTY_INDEX = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<addons>\n\n</addons>\n').encode("utf-8")


def _tree(tmp, cname=None):
    """The smallest tree verify_repo will read past."""
    with open(os.path.join(tmp, "addons.xml"), "wb") as handle:
        handle.write(EMPTY_INDEX)
    digest = hashlib.new(release.HASH_ALGO, EMPTY_INDEX).hexdigest()
    with open(os.path.join(tmp, "addons.xml." + release.HASH_ALGO),
              "w", encoding="utf-8") as handle:
        handle.write(digest)
    if cname is not None:
        with open(os.path.join(tmp, "CNAME"), "w", encoding="utf-8") as handle:
            handle.write(cname + "\n")


def main():
    # --- which URLs want a CNAME at all
    check("a domain we own yields its host",
          release.custom_domain("https://kodi.cinemaone.ch")
          == "kodi.cinemaone.ch")
    check("...and a path on it does not confuse the host",
          release.custom_domain("https://kodi.cinemaone.ch/repo")
          == "kodi.cinemaone.ch")
    check("a github.io URL wants no CNAME",
          release.custom_domain("https://cinema-one.github.io/tofa-for-kodi")
          is None)
    check("a LAN test build wants no CNAME",
          release.custom_domain("http://192.168.1.50:8000") is None)
    check("...nor an IPv6 one",
          release.custom_domain("http://[::1]:8000") is None)
    check("localhost wants no CNAME",
          release.custom_domain("http://localhost:8000") is None)

    # --- and what the shipped configuration resolves to
    check("BASE_URL is https", release.BASE_URL.startswith("https://"),
          release.BASE_URL)
    check("BASE_URL is a domain we control, not github.io",
          release.custom_domain(release.BASE_URL) is not None,
          release.BASE_URL)
    check("BASE_URL has no trailing slash",
          not release.BASE_URL.endswith("/"), release.BASE_URL)

    # --- verify_repo refuses a tree that would unbind the domain
    with tempfile.TemporaryDirectory() as tmp:
        _tree(tmp)
        problems = release.verify_repo(tmp, "https://kodi.cinemaone.ch")
        check("a missing CNAME is a PROBLEM, not a shrug",
              any("CNAME" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        _tree(tmp, cname="kodi.example.org")
        problems = release.verify_repo(tmp, "https://kodi.cinemaone.ch")
        check("a CNAME for the wrong host is caught",
              any("CNAME" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        _tree(tmp, cname="kodi.cinemaone.ch")
        problems = release.verify_repo(tmp, "https://kodi.cinemaone.ch")
        check("a matching CNAME passes",
              not any("CNAME" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        _tree(tmp)
        problems = release.verify_repo(tmp, "http://192.168.1.50:8000")
        check("a LAN build is not asked for a CNAME",
              not any("CNAME" in p for p in problems), str(problems))

    # The early return for a missing index used to drop what was found first.
    with tempfile.TemporaryDirectory() as tmp:
        problems = release.verify_repo(tmp, "https://kodi.cinemaone.ch")
        check("a CNAME problem survives an unreadable tree",
              any("CNAME" in p for p in problems), str(problems))

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("publish domain: the CNAME binds and is checked (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
