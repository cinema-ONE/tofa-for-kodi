"""Declining tofa's skin edits on one skin must not silence them on another.

Two of the three host-setup concerns edit the ACTIVE SKIN: the font
injection and the seek-bar patch. The decline was remembered as one bare
integer per concern, with no skin attached, so:

    decline the fonts on skin.estuary  ->  fonts_declined_version = 25
    switch to skin.confluence          ->  fonts_needed() is True, because
                                            the marker is not in that skin
    ...but the prompt never came back, because 25 is not < 25.

tofa then drew its own screens in the host skin's fallback font, silently,
with no way back short of a FONT_SET_VERSION bump or the Settings row. The
fix remembers a decline against the skin id it was given on.

The migration is the other half: an existing user's bare int cannot be
attributed to a skin by inspection, so it is credited to the skin active
when it is first read -- and to no other, which is what makes switching ask
again.

Run:  python3 test_per_skin_decline.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
import xbmc  # noqa: E402
from lib import hostsetup  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeAddon:
    """A settings store with types, because the real one has them: the
    per-skin value is a STRING and the legacy one an INT, and a stub that
    blurs that would hide a real mismatch."""

    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def getSetting(self, key):
        return str(self.values.get(key, ""))

    def getSettingInt(self, key):
        raw = self.values.get(key, 0)
        return int(raw) if str(raw).lstrip("-").isdigit() else 0

    def setSetting(self, key, value):
        self.values[key] = str(value)

    def setSettingInt(self, key, value):
        self.values[key] = int(value)


def use(addon, skin):
    hostsetup.ADDON = addon
    xbmc.getSkinDir = lambda: skin


FONTS = hostsetup._CONCERNS[0]
HOSTCONFIG = hostsetup._CONCERNS[1]

# --- the bug this fixes -------------------------------------------------
addon = FakeAddon()
use(addon, "skin.estuary")
hostsetup._remember_declined(FONTS)
check("decline is remembered on the skin it was given on",
      hostsetup._declined_version(FONTS) == FONTS.version,
      f"got {hostsetup._declined_version(FONTS)}")

use(addon, "skin.confluence")
check("...and NOT on a different skin",
      hostsetup._declined_version(FONTS) == 0,
      f"got {hostsetup._declined_version(FONTS)} for skin.confluence")

use(addon, "skin.estuary")
check("...and still holds on the original skin",
      hostsetup._declined_version(FONTS) == FONTS.version)

# --- both skins can hold their own decline ------------------------------
use(addon, "skin.confluence")
hostsetup._remember_declined(FONTS)
use(addon, "skin.estuary")
check("two skins keep separate declines",
      hostsetup._declined_version(FONTS) == FONTS.version
      and hostsetup._parse_skin_map(addon.getSetting(FONTS.skin_setting)) ==
      {"skin.estuary": FONTS.version, "skin.confluence": FONTS.version})

# --- applying clears only this skin's decline ---------------------------
hostsetup._clear_declined(FONTS)
check("applying clears the decline here",
      hostsetup._declined_version(FONTS) == 0)
use(addon, "skin.confluence")
check("...and leaves the other skin's alone",
      hostsetup._declined_version(FONTS) == FONTS.version)

# --- a non-skin concern stays global ------------------------------------
addon = FakeAddon()
use(addon, "skin.estuary")
hostsetup._remember_declined(HOSTCONFIG)
use(addon, "skin.confluence")
check("advancedsettings.xml decline is global, not per skin",
      hostsetup._declined_version(HOSTCONFIG) == HOSTCONFIG.version,
      "a profile-wide concern must not be re-asked per skin")

# --- migration of the pre-0.9.15 bare int -------------------------------
addon = FakeAddon({FONTS.declined_setting: FONTS.version})
use(addon, "skin.estuary")
check("legacy decline still counts on the skin in use at upgrade",
      hostsetup._declined_version(FONTS) == FONTS.version)
check("...and the legacy int is spent, so it cannot migrate twice",
      addon.getSettingInt(FONTS.declined_setting) == 0,
      f"legacy still {addon.getSettingInt(FONTS.declined_setting)}")
use(addon, "skin.confluence")
check("...but does NOT follow the user to another skin",
      hostsetup._declined_version(FONTS) == 0,
      f"got {hostsetup._declined_version(FONTS)}")

addon = FakeAddon({FONTS.declined_setting: 0})
use(addon, "skin.estuary")
check("no legacy decline migrates nothing",
      hostsetup._declined_version(FONTS) == 0
      and addon.getSetting(FONTS.skin_setting) == "")

# --- format round-trip and tolerance ------------------------------------
check("skin map round-trips",
      hostsetup._parse_skin_map(
          hostsetup._format_skin_map({"skin.a": 1, "skin.b": 22})) ==
      {"skin.a": 1, "skin.b": 22})
check("a corrupt chunk is dropped, not raised",
      hostsetup._parse_skin_map("skin.a=1|rubbish|skin.b=x|=4|skin.c=3") ==
      {"skin.a": 1, "skin.c": 3})

# --- no active skin never writes ----------------------------------------
addon = FakeAddon()
use(addon, "")
hostsetup._remember_declined(FONTS)
check("no active skin: nothing is written and nothing is declined",
      addon.values == {} and hostsetup._declined_version(FONTS) == 0,
      f"values={addon.values}")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
