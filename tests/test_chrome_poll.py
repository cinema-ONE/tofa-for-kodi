"""The per-tick chrome close reads ONE window id, not four conditions.

Adrian, 2026-08-31: "we have a function that runs every tick and disables any
chrome from the base skin ... I suspect this loop might degrade performance."
He was right, and the cause was not the four dialogs.

MEASURED ON THE AM6B+ during DirectPlay of an 87 Mbps 4K Dolby Vision remux
(am-h265, hardware, 3840x2160), each call 200ms apart as the ticker runs them:

    getCondVisibility(Window.IsActive(videoosd))   wall 8380us   CPU 2135us
    getCondVisibility("true")                      wall 8406us   CPU 2432us
    getInfoLabel(Player.Time)                      wall  127us   CPU  125us
    xbmcgui.getCurrentWindowDialogId()             wall   54us   CPU   52us
    the old four-dialog loop                       wall 8419us   CPU 1498us

`getCondVisibility("true")` costing the same as a real condition is the whole
finding: the expense is the ENTRY POINT, not what you ask, so four calls cost
what one does and trimming the list would have bought nothing. At the 200ms
tick the old form spent ~1% of a core and blocked the ticker for 4% of every
tick on a question whose answer is almost always no.

TWO TRAPS THIS COST, both worth keeping:

  * A TIGHT LOOP READS 15.7us for the same call, 600x cheaper than the real
    cadence -- benchmarking it back-to-back would have "proved" it free.
  * Transcode and DirectPlay measured IDENTICALLY. The first run used a
    transcode, which hands the box an easier stream; Adrian caught it. Redone
    on the real remux the numbers did not move, which says the cost is fixed
    synchronisation rather than contention with the decoder.

SKIN INDEPENDENCE is unchanged by the swap. Ids come from Kodi's
`xbmc/guilib/WindowIDs.h`; the names are the same core table
`xbmc/input/WindowTranslator.cpp` uses to resolve `Dialog.Close(<name>)`.
Neither is skin-provided. Both forms are equally blind to a skin's own custom
windows -- Estuary hangs Custom_1109_TopBarOverlay off the seek bar, and no
form of this has ever seen it.

Run:  python3 test_chrome_poll.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
import xbmcgui
from resources.lib.windows.player import PlayerWindow, _KODI_CHROME_IDS

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Fake:
    """Stand-in `self`, so the test exercises the REAL method."""
    def __init__(self):
        self._closing = False


def run(top_id, closing=False):
    """Call the real _close_kodi_osd with a given topmost dialog id."""
    calls = []
    orig_id, orig_exec, orig_cond = (
        xbmcgui.getCurrentWindowDialogId, xbmc.executebuiltin, xbmc.getCondVisibility)
    conds = []
    xbmcgui.getCurrentWindowDialogId = lambda: top_id
    xbmc.executebuiltin = lambda cmd: calls.append(cmd)
    xbmc.getCondVisibility = lambda c: conds.append(c) or False
    try:
        f = Fake(); f._closing = closing
        PlayerWindow._close_kodi_osd(f)
    finally:
        xbmcgui.getCurrentWindowDialogId, xbmc.executebuiltin, xbmc.getCondVisibility = (
            orig_id, orig_exec, orig_cond)
    return calls, conds


# --- the ids are Kodi's, and the right ones ---------------------------
check("videoosd is 12901", _KODI_CHROME_IDS.get(12901) == "videoosd")
check("busydialog is 10138", _KODI_CHROME_IDS.get(10138) == "busydialog")
check("busydialognocancel is 10160", _KODI_CHROME_IDS.get(10160) == "busydialognocancel")
check("sliderdialog is 10145, NOT 10100",
      _KODI_CHROME_IDS.get(10145) == "sliderdialog" and 10100 not in _KODI_CHROME_IDS)
check("the seek bar (10115) is NOT in the map",
      10115 not in _KODI_CHROME_IDS,
      "closing it makes it strobe -- see the block under _close_kodi_osd")

# --- it closes what it should -----------------------------------------
for wid, name in sorted(_KODI_CHROME_IDS.items()):
    calls, _ = run(wid)
    check(f"{name} on top is closed", calls == [f"Dialog.Close({name},true)"], str(calls))

# --- and nothing else --------------------------------------------------
calls, _ = run(9999)                      # WINDOW_INVALID, no dialog at all
check("no dialog up -> no builtin", calls == [], str(calls))
calls, _ = run(13002)                     # our own player, dynamically allocated
check("OUR OWN window on top -> no builtin", calls == [], str(calls))
calls, _ = run(10115)                     # seekbar
check("the seek bar is left alone", calls == [], str(calls))
calls, _ = run(12005)                     # FullScreenVideo, the normal state
check("FullScreenVideo is left alone", calls == [], str(calls))

# --- the expensive call is gone ---------------------------------------
for wid in (9999, 13002, 12901, 10138):
    _, conds = run(wid)
    check(f"no getCondVisibility for top={wid}", conds == [], str(conds))

# --- the closing guard still short-circuits ---------------------------
calls, _ = run(12901, closing=True)
check("a closing window does nothing", calls == [], str(calls))

# --- it never raises ---------------------------------------------------
def boom():
    raise RuntimeError("Kodi said no")
orig = xbmcgui.getCurrentWindowDialogId
xbmcgui.getCurrentWindowDialogId = boom
try:
    f = Fake()
    PlayerWindow._close_kodi_osd(f)
    check("a raising id call is swallowed", True)
except Exception as exc:                                    # noqa: BLE001
    check("a raising id call is swallowed", False, repr(exc))
finally:
    xbmcgui.getCurrentWindowDialogId = orig

failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"all {len(RESULTS)} checks passed" if not failed
      else f"{len(failed)} of {len(RESULTS)} checks FAILED")
raise SystemExit(1 if failed else 0)
