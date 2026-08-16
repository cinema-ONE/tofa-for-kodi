"""8.3's rail opens at the outro marker, and 8.5 stops offering that moment.

The spec's lead is "~30s before content end ABSENT an outro marker, clamped
<=6min from true end" -- so 30s is the fallback, not the rule. player.py took
the fallback unconditionally because the marker was believed not to exist; it
arrives on the QuickView segments response, which 8.5 was already reading.

Taking the fallback anyway is what put two surfaces on one moment: an outro
detected 36s from the end raised "Skip Credits", and the rail replaced it 6s
later. This suite pins the reveal arithmetic and the suppression that go
together -- if either half regresses, the flicker comes back.

Run:  python3 test_nextup_outro_marker.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakePlayer:
    """Just the state the two functions under test read.

    `_outro_start_ms` is the REAL one, not a stand-in: the marker choice and
    the clamps around it are what this suite is about, so stubbing it would
    leave the interesting half untested."""

    _outro_start_ms = PlayerWindow._outro_start_ms

    def __init__(self, duration_ms, segments=(), next_up=("ep", "file"),
                 mode=player.AUTO_PLAY_NEXT_AUTO):
        self._duration_ms = duration_ms
        self._segments = list(segments)
        self._next_up = next_up
        self._mode = mode

    def _auto_play_next_mode(self):
        return self._mode


def reveal(fake):
    return PlayerWindow._next_up_reveal_ms(fake)


def owns(fake):
    return PlayerWindow.rail_owns_outro(fake)


HOUR = 3600_000

# ---- the fallback, unchanged where there is no marker --------------------
check("no marker at all -> 30s before the end",
      reveal(FakePlayer(HOUR)) == HOUR - 30_000,
      str(reveal(FakePlayer(HOUR))))

check("markers of other kinds do not move it",
      reveal(FakePlayer(HOUR, [("intro", 60_000, 90_000),
                               ("recap", 0, 30_000)])) == HOUR - 30_000)

# ---- the reported case ---------------------------------------------------
# Outro detected 36s from the end: the rail must open THERE, not 6s later.
observed = FakePlayer(HOUR, [("outro", HOUR - 36_000, HOUR)])
check("outro 36s out -> the rail opens at the marker, not at 30s",
      reveal(observed) == HOUR - 36_000, str(reveal(observed)))

# ---- the two clamps ------------------------------------------------------
check("an outro closer than 30s does not DELAY the rail",
      reveal(FakePlayer(HOUR, [("outro", HOUR - 10_000, HOUR)])) == HOUR - 30_000)

check("an outro more than 6 min out is clamped to 6 min",
      reveal(FakePlayer(HOUR, [("outro", HOUR - 900_000, HOUR)]))
      == HOUR - int(player.NEXT_UP_LEAD_MARKER_MAX_S * 1000))

check("the LAST outro is the one that counts",
      reveal(FakePlayer(HOUR, [("outro", 120_000, 150_000),
                               ("outro", HOUR - 40_000, HOUR)])) == HOUR - 40_000)

# ---- who owns the outro moment ------------------------------------------
check("with a next episode and auto-play on, the rail owns it",
      owns(FakePlayer(HOUR)))

check("a series finale (no next episode) leaves the pill in place",
      not owns(FakePlayer(HOUR, next_up=None)))

check("auto-play `none` leaves the pill in place",
      not owns(FakePlayer(HOUR, mode=player.AUTO_PLAY_NEXT_NONE)))

check("`ask` still opens a rail, so it still owns the moment",
      owns(FakePlayer(HOUR, mode=player.AUTO_PLAY_NEXT_ASK)))

print("\n" + "=" * 60)
FAILED = sum(1 for _, ok in RESULTS if not ok)
if FAILED:
    print(f"{FAILED} of {len(RESULTS)} checks FAILED")
    raise SystemExit(1)
print(f"the rail takes the outro marker ({len(RESULTS)} checks)")
