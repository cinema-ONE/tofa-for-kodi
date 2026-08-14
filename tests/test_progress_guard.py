"""A bad position reading must not cost a resume point -- and the guard that
ensures it must never be able to pin one either.

The server stores position_ms unguarded, so one bogus heartbeat can send a
viewer back to the start. The guard holds a big unexplained jump for exactly
one heartbeat. "Exactly one" is the property worth testing: a guard that can
latch is worse than the bug it prevents.

Run:  python3 test_progress_guard.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import monitor

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


R = monitor.POSITION_REGRESSION_MS


class RecordingClient:
    def __init__(self):
        self.resume_writes = []      # update_progress -> the resume point
        self.session_writes = []
    def report_progress(self, sid, stok, pos, paused, ended=False, timeout=None):
        self.session_writes.append(pos)
    def update_progress(self, fid, pos, ended=False, timeout=None):
        self.resume_writes.append((pos, ended))


class FakePlayer(monitor.TofaPlayer):
    def __init__(self):
        self.position_ms = 0
        self.client = RecordingClient()
        super().__init__()
        self._session = {"session_id": "s", "session_token": "t", "file_id": "f"}
    def getTime(self): return self.position_ms / 1000.0
    def isPlayingVideo(self): return True
    def _client(self): return self.client


def beat(p, position_ms, ended=False):
    p.position_ms = position_ms
    p._report(ended=ended)


# 1. Ordinary forward progress is never held.
p = FakePlayer()
for ms in (10_000, 20_000, 30_000, 40_000):
    beat(p, ms)
check("forward progress is never held",
      [w[0] for w in p.client.resume_writes] == [10_000, 20_000, 30_000, 40_000],
      str(p.client.resume_writes))

# 2. THE INCIDENT: 11:28 in, then a heartbeat claiming 50ms.
p = FakePlayer()
beat(p, 688_868)
beat(p, 50)
check("a jump to ~zero does not reach the resume point",
      [w[0] for w in p.client.resume_writes] == [688_868], str(p.client.resume_writes))

# 3. ...but the very next heartbeat writes, whatever it says. THE ANTI-LATCH
#    TEST: the held value and the next value deliberately differ, which is
#    what a stream playing on from a bad reading would do.
beat(p, 250)
check("the hold lasts exactly one heartbeat",
      [w[0] for w in p.client.resume_writes] == [688_868, 250], str(p.client.resume_writes))

# 4. And it keeps writing afterwards -- no lingering suppression.
beat(p, 450)
beat(p, 650)
check("writes continue after the hold",
      [w[0] for w in p.client.resume_writes] == [688_868, 250, 450, 650],
      str(p.client.resume_writes))

# 5. Drift smaller than the threshold is not held at all.
p = FakePlayer()
beat(p, 600_000)
beat(p, 600_000 - (R - 1_000))
check("a small backwards drift is written straight through",
      len(p.client.resume_writes) == 2, str(p.client.resume_writes))

# 6. A seek clears the baseline, so a real rewind is never even delayed.
p = FakePlayer()
beat(p, 900_000)
p.position_ms = 100_000                  # Kodi has already moved the clock
p.onPlayBackSeek(100_000, -800_000)
beat(p, 100_200)
check("a rewind after a seek is written immediately",
      [w[0] for w in p.client.resume_writes] == [900_000, 100_000, 100_200],
      str(p.client.resume_writes))

# 6b. ...and the same holds when getTime() LAGS the seek callback, which is
#     what made the baseline re-arm at the old position before it was
#     cleared after the report rather than only before it.
p = FakePlayer()
beat(p, 900_000)
p.onPlayBackSeek(100_000, -800_000)      # clock still reads 900_000 here
beat(p, 100_000)
check("a rewind is immediate even when getTime() lags the seek",
      [w[0] for w in p.client.resume_writes] == [900_000, 900_000, 100_000],
      str(p.client.resume_writes))

# 7. The final write is never held -- it is the one that saves the place.
p = FakePlayer()
beat(p, 688_868)
beat(p, 50, ended=True)
check("the final (ended) write is never held",
      p.client.resume_writes[-1] == (50, True), str(p.client.resume_writes))

# 8. The session endpoint is bookkeeping and stays unfiltered, so a held
#    heartbeat is still visible server-side rather than silently vanishing.
p = FakePlayer()
beat(p, 688_868)
beat(p, 50)
check("the session endpoint still sees every heartbeat",
      p.client.session_writes == [688_868, 50], str(p.client.session_writes))

# 9. A NEGATIVE position never leaves the client. Kodi's clock reads slightly
#    negative between play() and the first frame; measured -99ms on
#    2026-08-11 during a start that stalled in the audio renderer and never
#    produced one. The server answers `HTTP 422: position_ticks must be
#    greater than or equal to zero` and throws the whole heartbeat away, so
#    the stall window reported nothing at all.
p = FakePlayer()
beat(p, -99)
check("a negative reading is clamped, not sent",
      p.client.session_writes == [0] and [w[0] for w in p.client.resume_writes] == [0],
      f"session={p.client.session_writes} resume={p.client.resume_writes}")

# ...and it must not poison the cache either, or the fallback used once Kodi
# has torn the player down would hand back a negative long after the fact.
p = FakePlayer()
beat(p, -250)
check("the cached fallback is clamped too", p._last_position_ms == 0,
      str(p._last_position_ms))

# Zero is a REAL position (the very start), so the clamp must not treat it as
# missing -- same class of bug as ASK being 0 in the stereo marker.
p = FakePlayer()
beat(p, 0)
check("zero still reports as zero", p.client.session_writes == [0],
      str(p.client.session_writes))
# 10. The final heartbeat must go out BEFORE the session is retired. The
#     server reaps a session on /stopped, so a /progress sent afterwards is
#     addressed to something that no longer exists: it answers
#     `stream_session.validate_fail` / `not_in_registry` and drops the write.
#     Measured against the server's own log on 2026-08-11, where the two
#     requests arrived 9-11ms apart in the wrong order on every single stop.
class OrderingClient(RecordingClient):
    def __init__(self):
        super().__init__()
        self.calls = []
    def report_progress(self, sid, stok, pos, paused, ended=False, timeout=None):
        self.calls.append("progress")
        super().report_progress(sid, stok, pos, paused, ended, timeout)
    def report_stopped(self, sid, stok):
        self.calls.append("stopped")
    def end_session(self, sid, stok):
        self.calls.append("end_session")

p = FakePlayer()
p.client = OrderingClient()
p.position_ms = 123_000
p.onPlayBackStopped()
check("the last heartbeat is sent before the session is retired",
      p.client.calls[:2] == ["progress", "stopped"], str(p.client.calls))
check("...and it still carries the real position",
      p.client.session_writes == [123_000], str(p.client.session_writes))


print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
