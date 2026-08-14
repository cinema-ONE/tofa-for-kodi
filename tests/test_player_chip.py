"""8.6's chip must also cover a stream that has simply stopped answering.

Kodi's Player.Caching only reports a buffer refill, not a dead source, so the
chip is additionally driven by a position that will not advance. Timing is
injected -- no Kodi, no sleeping.  Run:  python3 test_player_chip.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player
from resources.lib.windows.player import PlayerWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


T = player.STALL_CHIP_AFTER_S


class FakeWindow:
    """Only what _position_frozen touches."""
    STATE_PAUSED = PlayerWindow.STATE_PAUSED
    def __init__(self, paused=False):
        self._frozen_at_ms = -1
        self._frozen_since = 0.0
        self._pos = 0
        self._paused = paused
    def getProperty(self, key):
        return self.STATE_PAUSED if (key == "player_state" and self._paused) else ""
    def _position_ms(self):
        return self._pos
    def frozen(self, now):
        return PlayerWindow._position_frozen(self, now)


# 1. Normal playback never shows the chip.
w = FakeWindow()
tripped = False
for i in range(40):
    w._pos = i * 200                       # 200ms of video per 0.2s tick
    tripped = tripped or w.frozen(1000.0 + i * 0.2)
check("advancing playback never shows the chip", not tripped)

# 2. A frozen position waits out STALL_CHIP_AFTER_S first.
w = FakeWindow()
w._pos = 688_868
check("first frozen tick does not show it", not w.frozen(1000.0))
check("still not shown just under the threshold", not w.frozen(1000.0 + T - 0.1))
check("shown once the threshold passes", w.frozen(1000.0 + T))

# 3. Recovery clears it.
w._pos = 689_200
check("a resumed position clears the chip", not w.frozen(1000.0 + T + 0.2))

# 4. Pause is not a stall, however long it lasts.
w = FakeWindow(paused=True)
w._pos = 500_000
tripped = False
for i in range(60):
    tripped = tripped or w.frozen(1000.0 + i * 5)   # five minutes paused
check("a long pause never shows the chip", not tripped)

# 5. Unpausing restarts the window rather than showing it instantly.
w._paused = False
check("unpausing does not show it immediately", not w.frozen(2000.0))
check("...but a stall after the resume still does", w.frozen(2000.0 + T))

# 6. The chip must lead 8.7's card, never trail it -- the viewer should see
#    "it stopped, it may come back" well before "it is not coming back".
from resources.lib import monitor  # noqa: E402
chip_at = T + player.REBUFFER_DELAY_S
check("the chip appears long before the give-up card",
      chip_at < monitor.STALL_TIMEOUT_SECONDS,
      f"chip at {chip_at}s vs card at {monitor.STALL_TIMEOUT_SECONDS}s")
print(f"      (chip ~{chip_at:.1f}s, 8.7 card at {monitor.STALL_TIMEOUT_SECONDS:.0f}s)")

# 6b. Which VARIANT the chip uses. 8.6's determinate ring is for
#     engine-reported rebuffer progress; a dead source has none, and a ring
#     pinned at whatever CacheLevel last read looks frozen rather than busy.
#     Reported from the box: "spinner is up, but it's not spinning".
class ChipWindow:
    STATE_PAUSED = PlayerWindow.STATE_PAUSED
    STATE_OPENING = PlayerWindow.STATE_OPENING
    def __init__(self):
        self.props = {}
        self._rebuffer_at = 0.0
        self._frozen_at_ms = -1
        self._frozen_since = 0.0
        self._pos = 500_000
    def getProperty(self, k): return self.props.get(k, "")
    def setProperty(self, k, v): self.props[k] = v
    def _position_ms(self): return self._pos
    def _clear_rebuffer(self): return PlayerWindow._clear_rebuffer(self)
    def _position_frozen(self, now): return PlayerWindow._position_frozen(self, now)
    @staticmethod
    def _rebuffer_ring(): return "rebuffer-ring/12.png"     # a real cache reading
    def tick(self, now): return PlayerWindow._tick_rebuffer(self, now)

def run_chip(caching):
    player.xbmc.getCondVisibility = lambda label: caching and label == "Player.Caching"
    w = ChipWindow()
    reb = player.REBUFFER_DELAY_S
    for step in (0.0, T, T + reb, T + reb + 1.0):
        w.tick(1000.0 + step)
    return w

_real_cond = player.xbmc.getCondVisibility
try:
    w = run_chip(caching=False)          # dead source: position frozen
    check("a stalled stream shows the chip", w.props.get("player_rebuffer") == "1")
    check("a stalled stream uses the SPINNER, not the ring",
          w.props.get("player_rebuffer_ring") == "",
          repr(w.props.get("player_rebuffer_ring")))

    w = run_chip(caching=True)           # genuine engine rebuffer
    check("a real rebuffer still uses the determinate ring",
          w.props.get("player_rebuffer_ring") == "rebuffer-ring/12.png",
          repr(w.props.get("player_rebuffer_ring")))
finally:
    player.xbmc.getCondVisibility = _real_cond


# 7. 8.7's card must not be raised over a spinner. The stall that brings us
#    there is what raised the chip, and the ticker that would normally clear
#    it has just stopped for want of a player -- so fail() has to do it.
#    Seen live 2026-08-08: the card came up with the chip still turning
#    behind it, promising a recovery the card exists to rule out.
class FailWindow:
    """Absorbs everything fail() touches; keeps the real property store."""
    ERROR_CLOSE_ID = 9950
    def __init__(self):
        self.props = {}
        self.ui_player = None
        self._rebuffer_at = 12.0
        self.props["player_rebuffer"] = "1"
        self.props["player_rebuffer_ring"] = "rebuffer-ring/12.png"
    def getProperty(self, k): return self.props.get(k, "")
    def setProperty(self, k, v): self.props[k] = v
    def _clear_rebuffer(self): return PlayerWindow._clear_rebuffer(self)
    def __getattr__(self, name):        # close_panel, hide_chrome, _hide_skip...
        return lambda *a, **k: None

fw = FailWindow()
PlayerWindow.fail(fw, "Playback stopped unexpectedly.")
check("the failure card raises with the chip cleared",
      fw.props.get("player_rebuffer") == "", repr(fw.props.get("player_rebuffer")))
check("...and its spinner ring too",
      fw.props.get("player_rebuffer_ring") == "", repr(fw.props.get("player_rebuffer_ring")))
check("the card itself is up", fw.props.get("player_error") == "1")
check("the chip's delay is disarmed so it cannot re-arm", fw._rebuffer_at == 0.0)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
