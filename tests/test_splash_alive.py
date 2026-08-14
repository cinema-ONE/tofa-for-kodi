"""is_alive() must observe, not just believe.

The flag on Kodi's home window is a CLAIM. It was wrong twice, and the second
one is what the owner saw after the first fix: within ONE launch, a profile
switch found the flag still "1" while no splash was on screen, so ensure_up()
declined to raise one and the app rebuilt over Kodi's own menu. The log said
"splash: one is already up, not raising another" -- twice, with nothing up.

Run:  python3 test_splash_alive.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
import xbmcgui
from resources.lib.windows import splash

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def set_flag(on):
    splash._mark_alive(on)

def with_window(name):
    xbmc.getInfoLabel = lambda label: name if "tofa_window" in label else ""


# No flag: answered at once, without asking Kodi anything.
set_flag(False); with_window("")
check("no flag means no splash", splash.is_alive() is False)

# Flag set AND a splash really on screen.
set_flag(True); with_window("SplashWindow")
check("flag plus a real splash means alive", splash.is_alive() is True)

# Flag set but the splash is gone -- the profile-switch case.
set_flag(True); with_window("MainWindow")
check("a stale flag is not believed", splash.is_alive() is False)
check("...and the stale flag is cleared, so the next call is instant",
      xbmcgui.Window(splash._SESSION_WINDOW).getProperty(
          splash._ALIVE_PROPERTY) != "1")

# The window we are actually walked back onto during a switch is the splash,
# so the case the original code protected still works.
set_flag(True); with_window("SplashWindow")
check("a genuine re-activation still suppresses a second splash",
      splash.is_alive() is True)

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
