"""Offline verification of monitor.TofaPlayer._check_stall timing.

No Kodi, no network, no sleeping -- the wall clock is injected. Run:
    python3 test_stall.py
"""
import sys                                                       # noqa: E402
from kodi_stubs import NOTIFICATIONS, PROPERTY_WRITES             # noqa: E402
from resources.lib import monitor  # noqa: E402

# ---- a player whose clock and position we control --------------------------
class FakePlayer(monitor.TofaPlayer):
    def __init__(self):
        self.position_ms = 0
        self.stopped = False
        super().__init__()
    def getTime(self):
        return self.position_ms / 1000.0
    def stop(self):
        self.stopped = True
    def isPlayingVideo(self):
        return True

def new_player():
    NOTIFICATIONS.clear()
    PROPERTY_WRITES.clear()
    return FakePlayer()

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")

T = monitor.STALL_TIMEOUT_SECONDS

# 1. Healthy playback never trips the detector.
p = new_player()
for i in range(40):
    p.position_ms = i * 10_000          # 10s of video per 10s of wall clock
    p._check_stall(now=1000.0 + i * 10)
check("healthy playback never stalls", not p.stopped and not PROPERTY_WRITES)

# 2. A frozen position trips it after STALL_TIMEOUT_SECONDS, not before.
p = new_player()
p.position_ms = 688_868                  # the real incident's position
p._check_stall(now=1000.0)               # seeds the window
p._check_stall(now=1000.0 + T - 1)
before = p.stopped
p._check_stall(now=1000.0 + T)
check("frozen position does NOT trip early", not before)
check("frozen position trips at the timeout", p.stopped)
# Our own toast now, not Kodi's notification: 8.9 wants a surface we can
# style and fade, and the host skin's popup is neither. Asserted against the
# WRITE HISTORY rather than the live property, because toast.show clears
# itself from a timer thread and the stub's sleep is a no-op.
check("viewer is told (#31035, through our own toast)",
      any(k == "tofa_toast" and "31035" in str(v) for k, v in PROPERTY_WRITES),
      str(PROPERTY_WRITES))

# 3. THE REGRESSION THAT CAUSED THE INCIDENT.
#    During the outage ticks were 40s apart, not 10s. The old code needed
#    3 consecutive stalled ticks, so it needed 3 * 40s = 120s of real time.
#    Wall-clock detection must fire on the FIRST tick past the timeout.
p = new_player()
p.position_ms = 688_868
p._check_stall(now=1000.0)               # tick 1 -- seeds
p._check_stall(now=1000.0 + 40)          # tick 2 -- 40s later
check("fires on 2nd tick when ticks are 40s apart (old code needed 4)", p.stopped)

# 4. Pause must not be mistaken for a stall, however long it lasts.
p = new_player()
p.position_ms = 500_000
p._is_paused = True
for i in range(20):
    p._check_stall(now=1000.0 + i * 30)  # 10 minutes paused
check("a long pause never trips the detector", not p.stopped and not PROPERTY_WRITES)

# 5. Resuming from a pause restarts the window rather than firing instantly.
p._is_paused = False
p._check_stall(now=2000.0)               # first unpaused tick
check("resume does not fire immediately", not p.stopped)
p._check_stall(now=2000.0 + T - 1)
check("resume window is measured from the resume", not p.stopped)
p._check_stall(now=2000.0 + T)
check("resume window still fires once elapsed", p.stopped)

# 6. A seek clears the window (a backward seek looks like negative progress).
p = new_player()
p.position_ms = 900_000
p._check_stall(now=1000.0)
p._check_stall(now=1000.0 + T - 1)
p.position_ms = 100_000                  # user seeks back
p.onPlayBackSeek(100_000, -800_000)
p._check_stall(now=1000.0 + T + 1)
check("a backward seek is not a stall", not p.stopped)

# 7. Sub-epsilon drift still counts as stalled (clock jitter, not progress).
p = new_player()
p.position_ms = 400_000
p._check_stall(now=1000.0)
p.position_ms = 400_000 + monitor.STALL_EPSILON_MS - 1
p._check_stall(now=1000.0 + T)
check("jitter under STALL_EPSILON_MS counts as stalled", p.stopped)

# 8. The property that actually matters: with the server completely dead,
#    a stall is still detected within a bounded time. Worst tick period is
#    the heartbeat's whole I/O budget plus service.py's wait; worst detection
#    is the stall timeout plus one whole tick period.
TICK_SECONDS = 10          # service.py:41
HEARTBEAT_CALLS = 2        # report_progress + update_progress
worst_tick = monitor.PROGRESS_TIMEOUT_SECONDS * HEARTBEAT_CALLS + TICK_SECONDS
worst_detect = monitor.STALL_TIMEOUT_SECONDS + worst_tick
check("dead server: stall detected within 60s", worst_detect <= 60,
      f"worst case {worst_detect}s")
# For contrast, the code as it shipped: 15s default timeout, plus a fallback
# attempt per call, times 3 consecutive ticks.
old_worst_tick = 15.0 * 2 * HEARTBEAT_CALLS + TICK_SECONDS
old_worst_detect = old_worst_tick * 3
print(f"      (was up to {old_worst_detect:.0f}s; now {worst_detect:.0f}s)")

# 9. The heartbeat must NOT retry against the fallback base_url -- that is
#    what doubled the cost per call during the incident.
import resources.lib.http as http_mod                                # noqa: E402
from resources.lib.api import MediaServerClient                      # noqa: E402

attempts = []
def fake_request_json(session, method, url, **kw):
    attempts.append((url, kw.get("timeout")))
    raise http_mod.ApiError(0, "connection_error", "refused")
http_mod.request_json = fake_request_json
import resources.lib.auth as auth_mod                                # noqa: E402
auth_mod.update_server = lambda *a, **k: None

client = MediaServerClient(None, "http://lan:33333", "tok", "dev",
                           fallback_base_url="https://tunnel:33333")
attempts.clear()
try:
    client.report_progress("sid", "stok", 688_868, False, timeout=monitor.PROGRESS_TIMEOUT_SECONDS)
except http_mod.ApiError:
    pass
check("heartbeat tries the primary only (no fallback doubling)", len(attempts) == 1,
      f"{len(attempts)} attempts: {[u for u, _ in attempts]}")
check("heartbeat carries the short timeout",
      attempts and attempts[0][1] == monitor.PROGRESS_TIMEOUT_SECONDS,
      f"timeout was {attempts[0][1] if attempts else None}")

# ...but the FINAL write still gets the fallback and the full budget.
attempts.clear()
try:
    client.update_progress("fid", 688_868, True)
except http_mod.ApiError:
    pass
check("final write still tries the fallback", len(attempts) == 2,
      f"{len(attempts)} attempts")
check("final write uses http.py's default budget", attempts and attempts[0][1] is None,
      f"timeout was {attempts[0][1] if attempts else None}")

print()
failed = [n for n, ok, _ in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
