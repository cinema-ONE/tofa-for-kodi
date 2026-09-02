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
src = (ROOT / "plugin.video.tofa" / "resources" / "lib"
       / "fontinstall.py").read_text(encoding="utf-8")

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
body = src.split("def _inject_fonts", 1)[1].split("\ndef ", 1)[0]
for forbidden in ("copyfile", "copytree", "mkdirs"):
    check(f"_inject_fonts no longer calls {forbidden}()",
          forbidden not in body,
          "the font files come from the resource add-on now")

# --- the plugin depends on it, with a floor that actually binds ---------
#
# MINVERSION, not version. Kodi keeps an already-installed dependency unless
# it fails CAddonInfo::MeetsVersion(versionMin, version):
#     !(versionMin > installed.version || version < installed.minversion)
# so `version` says something about the dependency's ABI and `minversion` is
# the only floor on which version will do. Read out of AddonInstaller.cpp's
# resolve loop and AddonInfo.cpp:221-224, not assumed -- the first cut of
# this add-on shipped `version` alone, which would have left anyone on an
# older font resource there indefinitely: a newly added .ttf would arrive
# only when the repo's update timer happened to notice, and until then the
# plugin names a file that is not present, which draws as tofu.
plugin_xml = ET.parse(PLUGIN / "addon.xml").getroot()
fonts_import = next((i for i in plugin_xml.findall("./requires/import")
                     if i.get("addon") == "resource.font.tofa"), None)
check("the plugin imports resource.font.tofa", fonts_import is not None)
check("...with a minversion, which is the attribute that binds",
      fonts_import is not None and fonts_import.get("minversion"),
      "version= alone never forces an installed dependency to update")
check("...and that floor is the version the add-on actually is",
      fonts_import is not None
      and fonts_import.get("minversion") == manifest.get("version"),
      f"floor {fonts_import.get('minversion') if fonts_import is not None else None}, "
      f"add-on is {manifest.get('version')}")

# --- the upgrade path: stale copies must be swept ------------------------
#
# Before the fonts moved, _inject_fonts() copied them into the active skin's
# fonts/ -- which LoadTTF() searches BEFORE any font resource, taking the
# first path that exists (CheckFont() short-circuits). So an existing
# install renders from its stale copies and never reaches the add-on's.
# Invisible while the bytes match; permanent the first time a font is fixed.
# Confirmed on local Kodi: a deliberately wrong file at an earlier-searched
# path won, and Kodi's fontcache.xml recorded the family it had loaded.
check("fontinstall exposes a sweep for the old copies",
      hasattr(fontinstall, "prune_stale_skin_fonts"))
prune_src = src.split("def prune_stale_skin_fonts", 1)[1].split("\ndef ", 1)[0]
check("...that only ever removes our own prefix",
      'startswith("tofa_")' in prune_src and 'endswith(".ttf")' in prune_src,
      "it runs without consent, so its blast radius has to be exact")
check("...and refuses to run when the font add-on cannot supply the files",
      "FONT_ADDON_ID" in prune_src and "RuntimeError" in prune_src,
      "deleting the skin's copies while the dependency is absent strands "
      "every screen")

host_src = (PLUGIN / "resources" / "lib" / "hostsetup.py").read_text(encoding="utf-8")
setup_body = host_src.split("def ensure_host_setup", 1)[1]
check("ensure_host_setup sweeps BEFORE the consent check",
      setup_body.index("prune_stale_skin_fonts") < setup_body.index("_ask_consent"),
      "removing files we put there is permission being released, not taken")

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

# --- and the sweep actually sweeps, against a real directory ------------
#
# Driven rather than read: the guards are the whole safety argument for
# running it without asking. A temp skin stands in for the active one --
# on this Mac the real skin lives inside Kodi.app, which macOS App
# Management stops a shell writing to (Kodi itself has the entitlement,
# which is how the files got there).
import shutil
import tempfile
import xbmc
import xbmcaddon

tmp = tempfile.mkdtemp()
skin_fonts = os.path.join(tmp, "fonts")
os.makedirs(skin_fonts)
planted = ["tofa_inter_tight_regular.ttf", "tofa_lucide-icons.ttf"]
bystanders = ["NotoSans-Regular.ttf", "noto_license.txt", "tofa_notes.txt"]
for name in planted + bystanders:
    open(os.path.join(skin_fonts, name), "w").close()


class _SkinAddon:
    def getAddonInfo(self, key):
        return tmp if key == "path" else "skin.test"


_real_addon = xbmcaddon.Addon
xbmcaddon.Addon = lambda *a, **k: _SkinAddon()
xbmc.getSkinDir = lambda: "skin.test"
fontinstall._pruned_this_session = False
removed = fontinstall.prune_stale_skin_fonts()
left = sorted(os.listdir(skin_fonts))

check("the sweep removes the stale tofa_*.ttf", removed == len(planted),
      f"removed {removed}, expected {len(planted)}")
check("...and nothing else in the directory",
      left == sorted(bystanders),
      f"left {left}, expected {sorted(bystanders)}")
check("...including a tofa_ file that is not a .ttf",
      "tofa_notes.txt" in left)

fontinstall._pruned_this_session = False
second = fontinstall.prune_stale_skin_fonts()
check("a second run is a no-op", second == 0, f"removed {second}")

# The guard: with the font add-on missing, the skin's copies are the only
# ones there are and must be left alone.
for name in planted:
    open(os.path.join(skin_fonts, name), "w").close()


def _no_font_addon(addon_id=None, *a, **k):
    if addon_id == fontinstall.FONT_ADDON_ID:
        raise RuntimeError("Unknown addon id '%s'" % addon_id)
    return _SkinAddon()


xbmcaddon.Addon = _no_font_addon
fontinstall._pruned_this_session = False
guarded = fontinstall.prune_stale_skin_fonts()
check("with the font add-on absent it removes nothing", guarded == 0)
check("...and the files are still there",
      all(os.path.exists(os.path.join(skin_fonts, n)) for n in planted),
      "deleting them with no replacement would strand every screen")

xbmcaddon.Addon = _real_addon
shutil.rmtree(tmp, ignore_errors=True)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
