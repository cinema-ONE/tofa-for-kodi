"""A burst of chrome-hidden seeks is ONE seek, 400ms after the last press.

10.4 gained an accumulation rule: each press or hold-repeat extends a pending
ABSOLUTE target, and the client commits once after 400ms of stillness. Before
this, every press seeked -- five taps were five seeks, and on a transcoded
session each one re-cuts the stream server-side.

The scrubber has always worked this way (scrub/commit_scrub). This pins the
same contract for the chrome-hidden path, plus the three things 10.4 asks for
around it: reversing walks back from the PENDING target rather than from the
live position, the target is clamped to the title, and Back drops the burst
without seeking.

Pure state logic -- no Kodi window.  Run:  python3 test_quick_seek_accumulate.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player as P

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Fake:
    """Only what quick_seek / commit / cancel touch."""
    def __init__(self, position=60_000, duration=600_000, step=10_000):
        self._pos, self._duration_ms, self._step = position, duration, step
        self._quick_seek_ms = None
        self._quick_seek_commit_at = 0.0
        self._toast_deadline = 0.0
        self.props, self.seeks, self.ladder_resets = {}, [], 0
    # the bits of PlayerWindow it calls
    def _position_ms(self): return self._pos
    def _seek_step_ms(self, forward): return self._step
    def _seek_to(self, ms): self.seeks.append(ms)
    def _reset_seek_ladder(self): self.ladder_resets += 1
    def setProperty(self, k, v): self.props[k] = v
    def getProperty(self, k): return self.props.get(k, "")
    # the methods under test, bound unchanged
    quick_seek = P.PlayerWindow.quick_seek
    commit_quick_seek = P.PlayerWindow.commit_quick_seek
    cancel_quick_seek = P.PlayerWindow.cancel_quick_seek


# 1. THE POINT: five presses are one seek, not five.
f = Fake()
for _ in range(5):
    f.quick_seek(True)
check("five presses seek nothing yet", f.seeks == [], repr(f.seeks))
check("...and accumulate one target", f._quick_seek_ms == 60_000 + 5 * 10_000,
      repr(f._quick_seek_ms))
f.commit_quick_seek()
check("...committing seeks ONCE", f.seeks == [110_000], repr(f.seeks))
check("...and the burst is over", f._quick_seek_ms is None)
check("...and the ladder reset with it", f.ladder_resets == 1, repr(f.ladder_resets))

# 2. Reversing walks back from the PENDING target, not the live position.
#    Three forward then one back is +20s from where playback actually is.
f = Fake()
for _ in range(3): f.quick_seek(True)
f.quick_seek(False)
check("reversing works from the pending target",
      f._quick_seek_ms == 60_000 + 2 * 10_000, repr(f._quick_seek_ms))

# 3. Clamped at the title's bounds, both ends.
f = Fake(position=595_000)
for _ in range(5): f.quick_seek(True)
check("never past the end", f._quick_seek_ms == 600_000, repr(f._quick_seek_ms))
f = Fake(position=5_000)
for _ in range(5): f.quick_seek(False)
check("never before the start", f._quick_seek_ms == 0, repr(f._quick_seek_ms))

# 4. The toast announces the ACCUMULATED movement (8.9: 10s, 20s, 30s), not
#    the last step.
f = Fake()
f.quick_seek(True)
first = f.getProperty("player_seek_amount")
f.quick_seek(True); f.quick_seek(True)
third = f.getProperty("player_seek_amount")
check("the caption grows with the burst", first != third, f"{first!r} then {third!r}")
check("...and names the whole movement", third == P._seek_amount_label(30_000),
      repr(third))
check("direction is captioned", f.getProperty("player_seek_toast") == "forward")
f.quick_seek(False); f.quick_seek(False); f.quick_seek(False)
check("...and flips on reversal", f.getProperty("player_seek_toast") == "back")

# 5. Back drops the burst: no seek, no toast left captioning it.
f = Fake()
for _ in range(3): f.quick_seek(True)
check("cancel reports it had one", f.cancel_quick_seek() is True)
check("...and never seeked", f.seeks == [], repr(f.seeks))
check("...and cleared the caption", f.getProperty("player_seek_toast") == "")
check("...and the deadline", f._quick_seek_commit_at == 0.0)

# 6. Both are no-ops with nothing pending -- so Back still falls through to
#    the next rung, and teardown can call cancel unconditionally.
f = Fake()
check("commit with nothing pending is False", f.commit_quick_seek() is False)
check("cancel with nothing pending is False", f.cancel_quick_seek() is False)
check("...and neither seeked", f.seeks == [], repr(f.seeks))

# 7. A commit deadline is set by every press, and 400ms out.
f = Fake()
import time as _t
before = _t.monotonic()
f.quick_seek(True)
gap = f._quick_seek_commit_at - before
check("the deadline is ~400ms out", 0.35 <= gap <= 0.45, repr(gap))

# 8. 8.9: the toast stays up through the burst and leaves within 300ms of
#    the commit. The commit runs on a 5Hz tick, so a deadline inside one tick
#    is met by the very next one, 200ms later.
f = Fake()
f.quick_seek(True); f.quick_seek(True)
check("no toast deadline while the burst is pending", f._toast_deadline == 0.0,
      repr(f._toast_deadline))
before = _t.monotonic()
f.commit_quick_seek()
left = f._toast_deadline - before
check("the toast is due before the next tick after the commit", 0 < left <= 0.2,
      repr(left))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
