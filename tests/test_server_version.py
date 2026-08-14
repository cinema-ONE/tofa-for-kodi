# -*- coding: utf-8 -*-
"""The minimum-server-version gate.

We carry no backward-compatibility paths, so an old server does not fail --
it just returns less, and every gap looks like a client bug. This is the
thing that says so out loud.
"""
import kodi_stubs  # noqa: F401  (installs the Kodi stand-ins)

from resources.lib import serverversion as sv

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))


check("the current server parses", sv.parse("0.9.29") == (0, 9, 29))
check("a short version parses", sv.parse("0.9") == (0, 9))
check("a pre-release suffix is ignored", sv.parse("0.9.29-beta.2") == (0, 9, 29))
check("a build suffix is ignored", sv.parse("0.9.30+build7") == (0, 9, 30))

# An unreadable version must NOT read as old. A spurious "update your
# server" against a server that is fine is worse than saying nothing.
for junk in (None, "", "unknown", "v-next", "  "):
    check(f"unparseable {junk!r} is not treated as old", sv.is_supported(junk))

check("the exact minimum is supported", sv.is_supported("0.9.29"))
check("newer is supported", sv.is_supported("0.9.30"))
check("older is NOT supported", not sv.is_supported("0.9.28"))
check("much older is NOT supported", not sv.is_supported("0.9.21"))

# Tuple comparison, not string. "0.10.0" > "0.9.29" numerically but sorts
# BEFORE it as text, which is the classic way this check gets written wrong.
check("0.10.0 is newer than 0.9.29", sv.is_supported("0.10.0"))
check("1.0.0 is newer", sv.is_supported("1.0.0"))
check("...and a string compare would have got that wrong",
      "0.10.0" < "0.9.29")


class Dialogs:
    def __init__(self):
        self.shown = []

    def alert(self, title, message, *, error=False):
        self.shown.append((title, message, error))


def localize(sid):
    return {31114: "This server is version {0}. Needs {1} or newer.",
            31115: "Server needs updating"}[sid]


import xbmcgui
xbmcgui.Window(10000).clearProperty("tofa.server_version_warned")

d = Dialogs()
check("a current server warns about nothing",
      sv.warn_if_old("0.9.29", alert=d.alert, localize=localize) is False
      and not d.shown)

d = Dialogs()
shown = sv.warn_if_old("0.9.28", alert=d.alert, localize=localize)
check("an old server warns", shown is True and len(d.shown) == 1)
check("...as an error, with both versions named",
      d.shown[0][2] is True and "0.9.28" in d.shown[0][1]
      and "0.9.29" in d.shown[0][1], str(d.shown))

# Once per Kodi session. The add-on relaunches constantly -- Programs tile,
# profile switch, Back at the top level -- and a dialog on each would nag.
again = sv.warn_if_old("0.9.28", alert=d.alert, localize=localize)
check("it does NOT warn a second time", again is False and len(d.shown) == 1)

print("\n" + "=" * 60)
if FAILED:
    print(f"{FAILED} of {CHECKS} checks FAILED")
    raise SystemExit(1)
print(f"all {CHECKS} checks passed")
