# -*- coding: utf-8 -*-
"""Repository artwork is staged at the path addon.xml declares, not its name.

Kodi resolves a repository's artwork as `<datadir>/<addon-id>/<the path
written in addon.xml>`. Publishing flattened every asset to its basename,
which was invisible for as long as the only assets were `icon.png` and
`fanart.png` -- both at the add-on root, where the basename IS the relative
path. The first screenshot under `resources/screenshots/` would have been
published to a path Kodi never asks for: an entry whose screenshots silently
do not load, discovered by a stranger's add-on browser rather than by us.

Also checks that every asset travels, not a hardcoded pair. The fanart moved
from .jpg to .png once already.
"""
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


XML = """<?xml version="1.0"?>
<addon id="plugin.video.tofa" version="0.9.2">
  <extension point="xbmc.addon.metadata">
    <assets>
      <icon>icon.png</icon>
      <fanart>fanart.png</fanart>
      <screenshot>resources/screenshots/01-home.jpg</screenshot>
      <screenshot>resources/screenshots/02-browse.jpg</screenshot>
    </assets>
  </extension>
</addon>
"""


def main():
    assets = release.declared_assets(XML)
    targets = [target for _source, target in assets]

    check("every declared asset travels", len(assets) == 4, str(targets))
    check("a nested asset keeps its RELATIVE path, not its basename",
          "resources/screenshots/01-home.jpg" in targets, str(targets))
    check("...for every one of them",
          "resources/screenshots/02-browse.jpg" in targets, str(targets))
    check("a root asset is unchanged", "icon.png" in targets, str(targets))
    check("the source path is under the add-on directory",
          all(s.startswith(release.ADDON_DIR) for s, _t in assets))

    check("no <assets> block is empty, not an error",
          release.declared_assets("<addon><extension/></addon>") == [])

    # What the add-on really declares today has to resolve on disk, or the
    # published entry points at files that are not there.
    import os
    real = release.declared_assets(release.read_addon_xml())
    missing = [t for s, t in real if not os.path.exists(s)]
    check("every asset addon.xml declares exists on disk", not missing,
          str(missing))
    check("the add-on declares screenshots at all",
          any("screenshot" in t or "screenshots/" in t for _s, t in real),
          str([t for _s, t in real]))

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("declared assets: staged where Kodi looks for them (%d checks)"
          % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
