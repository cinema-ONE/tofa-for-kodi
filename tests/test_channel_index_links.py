# -*- coding: utf-8 -*-
"""The channel's index.html must link every file the repository add-on fetches.

Kodi has no directory listing for an HTTP host -- it PARSES the `<a href>`
list on the page. And `CFile::Open` consults `g_directoryCache` before it
opens a socket:

    if (!g_directoryCache.FileExists(url2, bPathInCache))
      if (bPathInCache)
        return false;                       // instant, no request, no log

`FileExists` reports `bPathInCache` when the DIRECTORY is cached, and returns
whether the file is among its items. So once anything has listed this host,
a file missing from the page is a file Kodi believes does not exist.

Our own published install steps make that happen every time: they tell the
user to add this host as a Kodi source and browse it ("Install from zip
file"). That caches a listing which -- while `addons.xml` and its sidecar
were unlinked -- contained only the repository zip. The repository then could
not read its own index:

    error: CRepository: failed read 'https://tofa.cinemaone.ch/addons.xml.sha256'

one millisecond after asking, with no `CurlFile::Open` line at all. A Kodi
restart cleared the cache and it worked, which is exactly why it looked
transient. It was the first bug an outside user ever reported (2026-08-16).

This test reads the URLs out of the REPOSITORY ADD-ON rather than hardcoding
them, so moving `<info>`/`<checksum>` without updating the page fails here.
"""
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import release  # noqa: E402

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def _repo_addon_xml() -> str:
    """The repository add-on's addon.xml.

    It has no source file -- release.py GENERATES it from a template, so ask
    the generator. That also means this test compares one generated artefact
    against the other, which is the pairing that has to stay in step: the
    page Kodi lists and the URLs the repo asks for.
    """
    return release._repository_addon_xml(release.BASE_URL).decode("utf-8")


def main():
    # --- what the repository actually fetches
    root = ET.fromstring(_repo_addon_xml())
    dir_el = root.find(".//extension[@point='xbmc.addon.repository']/dir")
    fetched = []
    for tag in ("info", "checksum"):
        el = dir_el.find(tag) if dir_el is not None else None
        if el is not None and (el.text or "").strip():
            fetched.append(el.text.strip())
    check("the repo add-on declares <info> and <checksum>", len(fetched) == 2, str(fetched))

    # --- what the generated page advertises
    html = release._INDEX.format(
        base_url=release.BASE_URL, repo_id=release.REPO_ID,
        repo_version=release.REPO_VERSION,
        repo_zip=f"{release.REPO_ID}-{release.REPO_VERSION}.zip",
        version="0.0.0", floor="0.0.0", project_url=release.PROJECT_URL,
        project_label="example")
    hrefs = set(re.findall(r'href="([^"]+)"', html))
    check("the page has links at all", bool(hrefs))

    for url in fetched:
        name = url.rsplit("/", 1)[-1]
        check(f"index.html links {name}", name in hrefs,
              f"Kodi will treat {name} as non-existent once this host is listed")

    # --- and the zip itself, which is how a human installs
    check("index.html links the repository zip",
          f"{release.REPO_ID}-{release.REPO_VERSION}.zip" in hrefs)

    # --- The LIVE channel is a separate, human-gated act: docs/ is the site,
    #     and it only changes when someone runs `release.py publish` and
    #     merges it. Report the drift loudly, but do not fail on it -- a code
    #     fix must be mergeable before the thing it fixes is deployed, and
    #     failing here would block the very PR that repairs the generator.
    published = ROOT / "docs" / "index.html"
    if published.exists():
        pub = set(re.findall(r'href="([^"]+)"', published.read_text(encoding="utf-8")))
        missing = [u.rsplit("/", 1)[-1] for u in fetched
                   if u.rsplit("/", 1)[-1] not in pub]
        if missing:
            print("WARN  the LIVE channel (docs/index.html) still omits %s"
                  % ", ".join(missing))
            print("      -- the fix is INERT until `release.py publish` is run "
                  "and merged.")
        else:
            print("PASS  the live docs/index.html links them too")
    else:
        print("SKIP  published docs/index.html not present")

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("channel index: every fetched file is linked (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
