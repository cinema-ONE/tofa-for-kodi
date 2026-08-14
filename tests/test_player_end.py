"""A stream that dies must reach 8.7's card, not a silent close.

Exercises the REAL methods (bound to a stand-in `self`) so the test cannot
drift from the implementation. Run:  python3 test_player_end.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow, _PlayerUIPlayer

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeWindow:
    """Carries only what ended_prematurely reads."""
    PREMATURE_END_MS = PlayerWindow.PREMATURE_END_MS
    def __init__(self, position_ms, duration_ms):
        self._duration_ms = duration_ms
        self._pos = position_ms
    def _position_ms(self): return self._pos
    def _resolve_duration_ms(self): return self._duration_ms


def ended_prematurely(position_ms, duration_ms):
    return PlayerWindow.ended_prematurely(FakeWindow(position_ms, duration_ms))


# ---- ended_prematurely -----------------------------------------------------
# The incident itself: froze 11:28 into a 46:21 episode.
check("the real incident reads as premature", ended_prematurely(688_868, 2_780_832))

# An episode watched to the credits must NOT be accused.
check("a finished episode is not premature", not ended_prematurely(2_780_832, 2_780_832))
check("ending 5s early is not premature", not ended_prematurely(2_775_832, 2_780_832))
check("ending 59s early is not premature", not ended_prematurely(2_721_832, 2_780_832))
check("ending 61s early IS premature", ended_prematurely(2_719_832, 2_780_832))

# Kodi sometimes overshoots the declared duration by a hair at EOF.
check("overshooting the duration is not premature", not ended_prematurely(2_781_500, 2_780_832))

# No duration to compare against -> say nothing rather than accuse.
check("unknown duration is not premature", not ended_prematurely(688_868, 0))

# A stream that died in the first seconds.
check("dying at the very start is premature", ended_prematurely(0, 2_780_832))


# ---- onPlayBackEnded routing ----------------------------------------------
class RecordingWindow:
    def __init__(self, *, premature, restarting=False):
        self._premature, self._restarting = premature, restarting
        self.failed_with = None
        self.closed = False
    def is_restarting(self): return self._restarting
    def ended_prematurely(self): return self._premature
    def fail(self, body, **k): self.failed_with = body
    def closeNow(self): self.closed = True


class FakeEvents:
    def __init__(self, window): self.window = window


def route(**kw):
    win = RecordingWindow(**kw)
    _PlayerUIPlayer.onPlayBackEnded(FakeEvents(win))
    return win

w = route(premature=True)
check("a dead stream shows the card", w.failed_with is not None)
check("a dead stream does NOT silently close", not w.closed)
check("the card uses #31101", "31101" in str(w.failed_with), str(w.failed_with))

w = route(premature=False)
check("a finished episode closes as before", w.closed and w.failed_with is None)

# The Next Up advance and the quality change both end the outgoing stream
# deliberately, mid-title -- exactly what ended_prematurely() notices.
w = route(premature=True, restarting=True)
check("an episode changeover shows no card", w.failed_with is None)
check("an episode changeover still closes", w.closed)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
