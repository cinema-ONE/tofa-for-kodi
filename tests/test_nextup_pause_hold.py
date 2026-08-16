"""Pausing holds 8.3's countdown, and resuming gives back what was left.

The rail used to expire by wall clock whatever playback was doing, on the
reading that the 20,000ms is a "hard contract". It is a contract about how
LONG the countdown runs, not a licence to ignore the one key whose whole
meaning is "hold everything" -- pausing under an open rail still advanced the
episode, so you came back to the next one already playing.

The old worry, written into the code, was a timer frozen into a rail that
never resolves. These checks are what says that is not reachable: a hold only
exists while the stream is paused, and the next resume re-arms it with the
remainder rather than a fresh 20s.

Run:  python3 test_nextup_pause_hold.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakePlayer:
    """The rail's own state, and the real hold/release under test."""

    _hold_next_up = PlayerWindow._hold_next_up
    _release_next_up = PlayerWindow._release_next_up

    def __init__(self, open_=True, deadline=0.0, hold=0.0):
        self._next_up_open = open_
        self._next_up_deadline = deadline
        self._next_up_hold = hold


NOW = 1000.0


def at(monkey_now):
    """Pin time.monotonic for the duration of one call."""
    import time as _t
    real = _t.monotonic
    _t.monotonic = lambda: monkey_now
    return real


def restore(real):
    import time as _t
    _t.monotonic = real


# ---- holding ------------------------------------------------------------
p = FakePlayer(deadline=NOW + 12.0)
real = at(NOW)
p._hold_next_up()
restore(real)
check("a pause parks the remaining seconds", abs(p._next_up_hold - 12.0) < 0.001,
      str(p._next_up_hold))
check("...and clears the deadline, so the tick stops counting",
      p._next_up_deadline == 0.0)

# ---- resuming -----------------------------------------------------------
real = at(NOW + 300.0)          # five minutes later: the pause was long
p._release_next_up()
restore(real)
check("a resume gives back exactly what was left, not a fresh 20s",
      abs(p._next_up_deadline - (NOW + 300.0 + 12.0)) < 0.001,
      str(p._next_up_deadline))
check("...and the hold is spent", p._next_up_hold == 0.0)

# ---- the cases that must NOT hold ---------------------------------------
p = FakePlayer(open_=False, deadline=NOW + 5.0)
real = at(NOW)
p._hold_next_up()
restore(real)
check("no rail open -> nothing is parked", p._next_up_hold == 0.0)

# `ask` mode shows the rail with no timer at all: deadline 0 is that state,
# not a countdown at zero, and parking it would invent one.
p = FakePlayer(deadline=0.0)
real = at(NOW)
p._hold_next_up()
restore(real)
check("`ask` mode has no countdown, so there is nothing to park",
      p._next_up_hold == 0.0)

# ---- a second pause must not extend the hold ----------------------------
p = FakePlayer(deadline=NOW + 8.0)
real = at(NOW)
p._hold_next_up()
p._hold_next_up()               # a repeated pause event
restore(real)
check("a repeated pause does not re-park and lose time",
      abs(p._next_up_hold - 8.0) < 0.001, str(p._next_up_hold))

# ---- releasing when nothing is held -------------------------------------
p = FakePlayer(deadline=0.0)
real = at(NOW)
p._release_next_up()
restore(real)
check("a resume with nothing held does not start a countdown",
      p._next_up_deadline == 0.0)

print("\n" + "=" * 60)
FAILED = sum(1 for _, ok in RESULTS if not ok)
if FAILED:
    print(f"{FAILED} of {len(RESULTS)} checks FAILED")
    raise SystemExit(1)
print(f"pause holds the countdown ({len(RESULTS)} checks)")
