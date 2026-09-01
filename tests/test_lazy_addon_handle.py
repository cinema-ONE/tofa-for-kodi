"""No module may take an xbmcaddon.Addon handle at IMPORT time.

Kodi deregisters an add-on before it registers the replacement. Inside that
window -- well under a second -- `xbmcaddon.Addon()` raises

    RuntimeError: Unknown addon id 'plugin.video.tofa'

Ten modules used to make that call at module scope, so an import landing in
the window took the whole script down and Kodi popped its own error
notification at the viewer. Seen on the cinema box updating 0.9.24 -> 0.9.25
(2026-09-01, 14:59:43.102): the outgoing service re-imported fontinstall 0.7s
before Kodi unpacked the new zip. It did NOT reproduce on the other two boxes
in the same sweep, which is what a one-frame race looks like -- and is exactly
why a test is worth more here than a re-run.

The rule this pins: every module must import cleanly while Addon() is
FAILING. Not "the ten known ones" -- every module, so a new one that reaches
for the handle at import fails here rather than on a television.

Run:  python3 test_lazy_addon_handle.py
"""
import importlib
import pathlib
import sys

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmcaddon

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


ROOT = pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"
_real_Addon = xbmcaddon.Addon
CALLS = []


class SwapWindow:
    """Kodi mid-update: our id is not registered, so every lookup raises.

    Verbatim message and type, because the point is to reproduce the failure
    the box actually hit, not a stand-in for it.
    """
    def __enter__(self):
        def boom(*a, **k):
            CALLS.append(a)
            raise RuntimeError("Unknown addon id 'plugin.video.tofa'")
        xbmcaddon.Addon = boom
        return self

    def __exit__(self, *exc):
        xbmcaddon.Addon = _real_Addon
        return False


def addon_modules():
    """Every importable module in the add-on, by dotted name.

    Discovered rather than listed: a list is a thing to forget to update,
    and the whole failure was one module nobody was thinking about.
    """
    names = []
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        name = ".".join(parts)
        # The three ENTRY POINTS are excluded, and only these three: they run
        # top-level work on import by design (addon.py reads sys.argv[1],
        # which is Kodi's plugin handle and is not present here).
        if name in ("addon", "launch_home", "service"):
            continue
        names.append(name)
    return names


MODULES = addon_modules()
check("the sweep actually found the add-on's modules", len(MODULES) > 50,
      f"found {len(MODULES)}")

# --- the rule ------------------------------------------------------------
failures = []
with SwapWindow():
    for name in MODULES:
        try:
            importlib.import_module(name)
        except RuntimeError as exc:
            if "Unknown addon id" in str(exc):
                failures.append(name)
            else:
                raise

check(f"all {len(MODULES)} modules import while Addon() is failing",
      not failures,
      "took the handle at import time: " + ", ".join(failures))
check("...and nothing even ASKED for it during the sweep", not CALLS,
      f"{len(CALLS)} call(s) -- an import is reaching for the handle")

# --- the proxy still behaves like an Addon once out of the window --------
from resources.lib import addonref, branding                     # noqa: E402

check("addonref.ADDON forwards attribute access to the real Addon",
      callable(addonref.ADDON.getAddonInfo))
check("...and localize() resolves a string id",
      addonref.localize(31042) is not None)

# --- a failure must not be REMEMBERED ------------------------------------
addonref._addon = None
raised = False
with SwapWindow():
    try:
        addonref.addon()
    except RuntimeError:
        raised = True
check("a call inside the window still raises", raised)
check("...but is not cached, so the next call retries and succeeds",
      addonref.addon() is not None,
      "caching the failure would turn one frame into a dead interpreter")

# --- what does not need Kodi at all --------------------------------------
with SwapWindow():
    ident, named = branding.app_id(), branding.app_name()
check("branding.app_id() answers without an Addon handle",
      ident == "plugin.video.tofa", f"got {ident!r}")
check("branding.app_name() likewise", bool(named), f"got {named!r}")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
