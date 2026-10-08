"""The Playback panel's Speed row steps through Kodi's own tempo range.

Run:  python3 test_playback_speed.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import playbacksync as ps

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


sent = []
ps._video_player_id = lambda: 1
ps._rpc = lambda method, params=None: sent.append((method, params)) or "OK"

check("up from 1x is 1.1x", ps.nudge_speed(1.0, True) == 1.1)
check("...sent as Kodi's tempo", sent[-1] == ("Player.SetTempo", {"playerid": 1, "tempo": 1.1}),
      repr(sent[-1]))
check("down from 1x is 0.9x", ps.nudge_speed(1.0, False) == 0.9)
check("a reading off the grid steps to the next one", ps.nudge_speed(1.04, True) == 1.1)
sent.clear()
check("1.5x is the top, and nothing is sent past it",
      ps.nudge_speed(1.5, True) == 1.5 and not sent)
check("0.8x is the bottom", ps.nudge_speed(0.8, False) == 0.8 and not sent)
check("an unknown speed starts from 1x", ps.nudge_speed(None, True) == 1.1)
ps._rpc = lambda method, params=None: None
check("Kodi refusing (paused) reads as unknown", ps.nudge_speed(1.0, True) is None)

check("1x reads 1×", ps.format_speed(1.0) == "1×")
check("1.2x reads 1.2×", ps.format_speed(1.2) == "1.2×")
check("unknown reads as a dash", ps.format_speed(None) == "—")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"playback speed: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
