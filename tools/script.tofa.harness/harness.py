"""Executes Kodi builtins on behalf of tools/kodictl.py. Development only.

Why this add-on exists at all: `Addons.ExecuteAddon` over JSON-RPC resolves
`plugin.video.tofa` to its **pluginsource** entry point (addon.py, the plain
directory listing), never to the `xbmc.python.script` one (launch_home.py, the
real window UI) -- Kodi's RunAddon builtin looks for AddonType::PLUGIN first
and stops there. Driving the window UI through the plugin route is what made
every automated check in the 2026-08-01 player session unreliable: Kodi's
Videos window finishes navigating into plugin:// a moment later and takes focus
back, so tests silently ran against Kodi's own window.

JSON-RPC has no ExecuteBuiltin method (removed for security), so the only way
to reach `RunScript(plugin.video.tofa)` from a shell is a second add-on that is
*only* a script -- this one. It resolves unambiguously, and its whole job is to
forward a builtin string:

    Addons.ExecuteAddon script.tofa.harness  builtin=<percent-encoded builtin>

Arguments arrive as `key=value` because that is the shape RunAddon gives a
script, and percent-encoded (see kodictl.py) so the commas and brackets in a
builtin survive Kodi's own argument splitting.
"""

import sys
import urllib.parse

import xbmc


def main() -> None:
    xbmc.log("TOFAHARNESS argv=%r" % (sys.argv,), xbmc.LOGINFO)
    for arg in sys.argv[1:]:
        key, _, raw = arg.partition("=")
        if key != "builtin":
            continue
        command = urllib.parse.unquote(raw)
        xbmc.log("TOFAHARNESS builtin=%s" % command, xbmc.LOGINFO)
        xbmc.executebuiltin(command)
    xbmc.log("TOFAHARNESS done", xbmc.LOGINFO)


main()
