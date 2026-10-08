"""The four Next Up styles: one device setting, one layout per style.

Run:  python3 test_nextup_styles.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmcaddon
from resources.lib import settings_options as so
from resources.lib.windows.player import PlayerWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


stored = {}
class Addon:
    def getSetting(self, key): return stored.get(key, "")
    def setSetting(self, key, value): stored[key] = value
xbmcaddon.Addon = Addon

check("unset reads as Compact, the app's default", so.next_up_style() == "compact")
so.set_next_up_style("lower")
check("a pick is kept on this device", so.next_up_style() == "lower")
stored["nextup_style"] = "huge"
check("an unknown value falls back to Compact", so.next_up_style() == "compact")
check("the styles are the app's four, in its order",
      [label for _v, label in so.NEXT_UP_STYLES] == ["Compact", "Minimal", "Lower third", "Full"])
check("every style has a layout",
      set(PlayerWindow._NEXTUP_GEOMETRY) == {v for v, _l in so.NEXT_UP_STYLES})
check("the Settings row has one segment per style",
      len(next(s for k, _g, s, _p in so.SEGMENTED_GROUPS if k == "nextupstyle"))
      == len(so.NEXT_UP_STYLES))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"next up styles: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
