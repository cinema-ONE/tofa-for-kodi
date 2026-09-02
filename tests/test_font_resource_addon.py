"""The fonts ship in resource.font.tofa, and nothing copies them into a skin.

Kodi's `GUIFontManager` will not load an add-on's `Font.xml`, so a `<font>`
NAME still has to be appended to the active skin's own -- that is the 2013
workaround `fontinstall.py` implements and xbmc/xbmc#29028 removes for 22 RC1.

But the font FILE has never needed that. `LoadTTF()` resolves a bare filename
against every enabled `kodi.resource.font` add-on before giving up, and has
since 2017 (`1317f0f7ac`) -- present in the 21.3-Omega tag and in the CoreELEC
fork the boxes run. So the files moved out of the plugin and into a resource
add-on, and injection writes XML only.

What that is worth, and what these pin:

  * 1.9 MB stops being written into a skin the user installed. We have never
    had cleanup code, so every skin they pass through kept a copy forever.
  * a changed .ttf stops being a skin write at all -- it ships as a
    dependency update. Only a changed DECLARATION still needs a
    FONT_SET_VERSION bump and the consent-and-restart path.

THE PREFIX IS LOAD-BEARING, not namespacing. `LoadTTF()` searches the active
skin's own `fonts/` FIRST, so a bare `RobotoMono-Regular.ttf` would silently
render the skin's copy instead of ours -- and Roboto Mono is a font a skin
plausibly ships. That is the "Relative fonts use skin paths" finding on the
PR: pre-existing, not introduced by it, and it lands squarely here.

Run:  python3 test_font_resource_addon.py
"""
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import fontinstall

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin.video.tofa"
FONT_ADDON = ROOT / "resource.font.tofa"
PREFIX = "tofa_"

# --- the add-on exists and is the right KIND ----------------------------
manifest = ET.parse(FONT_ADDON / "addon.xml").getroot()
points = [e.get("point") for e in manifest.findall("extension")]
check("resource.font.tofa declares kodi.resource.font",
      "kodi.resource.font" in points, f"points={points}")
check("...and xbmc.addon.metadata, which release.py's index needs",
      "xbmc.addon.metadata" in points,
      "kodi.addon.metadata parses for Kodi but _index_entry() looks for the "
      "xbmc. spelling and raises")
check("...and imports kodi.resource, as every resource add-on does",
      any(i.get("addon") == "kodi.resource"
          for i in manifest.findall("./requires/import")))

# --- every file FONTS names is shipped, prefixed ------------------------
wanted = sorted({spec[0] for spec in fontinstall.FONTS.values()})
check("FONTS names at least the four faces", len(wanted) >= 4, f"{wanted}")
missing = [f for f in wanted if not (FONT_ADDON / "resources" / (PREFIX + f)).exists()]
check("every .ttf FONTS names ships in the font add-on, prefixed",
      not missing, f"absent: {missing}")

# --- and the plugin ships NO font at all --------------------------------
stray = [str(p.relative_to(PLUGIN)) for p in PLUGIN.rglob("*.ttf")]
check("the plugin ships no .ttf of its own", not stray, f"found {stray}")
check("...and its old fonts directory is gone",
      not (PLUGIN / "resources" / "skins" / "Main" / "fonts").exists())

# --- the declaration references the prefixed name -----------------------
entry = fontinstall._font_entry_xml("tofa_font_body", "inter_tight_regular.ttf", 24, "Regular")
check("the injected <filename> carries the prefix",
      f"<filename>{PREFIX}inter_tight_regular.ttf</filename>" in entry,
      entry)
check("...and the bare name never appears on its own",
      "<filename>inter_tight_regular.ttf</filename>" not in entry,
      "the active skin's fonts/ is searched before any font add-on")

# --- injection writes XML, and only XML ---------------------------------
src = (PLUGIN / "resources" / "lib" / "fontinstall.py").read_text(encoding="utf-8")
body = src.split("def _inject_fonts", 1)[1].split("\ndef ", 1)[0]
for forbidden in ("copyfile", "copytree", "mkdirs"):
    check(f"_inject_fonts no longer calls {forbidden}()",
          forbidden not in body,
          "the font files come from the resource add-on now")

# --- the plugin depends on it, at the version it actually is ------------
plugin_xml = ET.parse(PLUGIN / "addon.xml").getroot()
imports = {i.get("addon"): i.get("version")
           for i in plugin_xml.findall("./requires/import")}
check("the plugin imports resource.font.tofa",
      "resource.font.tofa" in imports, f"requires={sorted(imports)}")
check("...at the version the font add-on declares",
      imports.get("resource.font.tofa") == manifest.get("version"),
      f"plugin wants {imports.get('resource.font.tofa')}, "
      f"add-on is {manifest.get('version')}")

# --- the channel would carry it -----------------------------------------
sys.path.insert(0, str(ROOT / "tools"))
import release  # noqa: E402

shipped = {arc.split("/", 1)[1] for _p, arc in release.font_addon_files()}
check("the font add-on's zip carries addon.xml and the fonts",
      "addon.xml" in shipped
      and all(("resources/" + PREFIX + f) in shipped for f in wanted),
      f"{sorted(shipped)}")
check("...and the OFL text travels with the fonts it covers",
      "resources/OFL.txt" in shipped,
      "a licence that ships apart from its fonts is the one that goes stale")

publish_src = (ROOT / "tools" / "release.py").read_text(encoding="utf-8")
check("do_publish stages the font add-on into the index",
      "FONT_ADDON_ID" in publish_src.split("def do_publish", 1)[1],
      "Kodi refuses to install an add-on whose dependency its repository "
      "cannot supply, so omitting it breaks the plugin's install outright")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
