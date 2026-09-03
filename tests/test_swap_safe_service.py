"""The service stops quietly when Kodi is replacing the add-on.

Kodi deregisters an add-on before it registers the replacement, and every
xbmcaddon.Addon() call in that window raises `Unknown addon id`. #143 moved
the module-level lookups so an IMPORT could no longer land there. The
0.9.26 -> 0.9.27 update on the cinema box (2026-09-03 11:19:42) showed the
RUN-TIME half: the outgoing service's tick loop called auth.is_signed_in(),
which resolved the profile directory, which called xbmcaddon.Addon(), which
raised out of main() -- and Kodi put its error notification on the
television. Two rules, both pinned here:

  * the profile directory is resolved once per process, so the tick path no
    longer calls Addon() at all;
  * a swap RuntimeError ends the service loop quietly; any OTHER RuntimeError
    still propagates, because that one is a bug and must stay visible.

Run:  python3 test_swap_safe_service.py
"""
import importlib
import sys

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
import xbmcaddon

from resources.lib import addonref, auth

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


SWAP = RuntimeError("Unknown addon id 'plugin.video.tofa'.")

# --- the signature ----------------------------------------------------------
check("the swap error is recognised", addonref.is_swap_error(SWAP))
check("...and only that one", not addonref.is_swap_error(RuntimeError("something else"))
      and not addonref.is_swap_error(ValueError("Unknown addon id 'x'")))

# --- the profile directory is resolved once -----------------------------------
calls = []
_real = xbmcaddon.Addon          # a factory in the stubs, so wrap rather than subclass
def Counting(*a, **k):
    calls.append(1); return _real(*a, **k)
xbmcaddon.Addon = Counting
auth._PROFILE_DIR = None
first, second = auth._profile_dir(), auth._profile_dir()
check("the profile dir is resolved once per process", len(calls) == 1 and first == second,
      f"Addon() called {len(calls)} times")
# ...and a failure is not cached.
auth._PROFILE_DIR = None
def boom(*a, **k): raise SWAP
xbmcaddon.Addon = boom
raised = False
try: auth._profile_dir()
except RuntimeError: raised = True
xbmcaddon.Addon = Counting
check("a lookup inside the window still raises", raised)
check("...and is not remembered, so the next call resolves", auth._profile_dir() == first)
xbmcaddon.Addon = _real

# --- the loop -----------------------------------------------------------------
sys.path.insert(0, str(kodi_stubs.PLUGIN))
service = importlib.import_module("service")


class OneTickMonitor:
    """abortRequested() False once, then the wait says abort: one tick."""
    def __init__(self): self.ticks = 0
    def abortRequested(self): return False
    def waitForAbort(self, t=0): return True


def run_main(is_signed_in):
    service.hostsetup.ensure_host_setup = lambda: False
    service.xbmc.Monitor = OneTickMonitor
    service.http.new_session = lambda: object()
    service.TofaPlayer = lambda: type("P", (), {"tick": lambda self: None})()
    service.auth.is_signed_in = is_signed_in
    return service.main()

def swap(): raise SWAP
try:
    run_main(swap); quiet = True
except Exception:                                           # noqa: BLE001
    quiet = False
check("a swap error ends the loop quietly", quiet, "it raised out of main(), which is the toast")

def bug(): raise RuntimeError("a real bug")
try:
    run_main(bug); propagated = False
except RuntimeError:
    propagated = True
check("any other RuntimeError still propagates", propagated, "a bug must not hide behind the swap guard")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
