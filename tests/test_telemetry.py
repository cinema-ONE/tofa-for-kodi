"""What the telemetry reports say, and what they refuse to make up.

Server 0.9.35's Activity page shows "This client doesn't report live
metrics" beside the desktop app's network / buffer / dropped / stalls tiles.
The route is POST /stream/s/{id}/telemetry and telemetry.py builds the body.

The rule these pin is honesty over completeness: Kodi has no dropped-frame
count and no bandwidth estimate, VideoPlayer.VideoBitrate is empty on most
files, and Player.CacheLevel is a percentage where the schema wants
milliseconds -- so those fields are null, never 0 and never estimated. What
Kodi CAN see -- position, state, codecs, resolution, stalls, time to first
frame -- is reported, and the monitor sends it without ever letting a
telemetry failure touch the progress writes that decide where the viewer
resumes.

Run:  python3 test_telemetry.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc

from resources.lib import http, telemetry, monitor

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# --- the report shape ----------------------------------------------------
LABELS = {
    "System.BuildVersion": "21.3 (21.3.0) Git:20241213-e6b9a1b3b4",
    "Player.Process(videowidth)": "1,920",
    "Player.Process(videoheight)": "1,088",
    "VideoPlayer.VideoCodec": "h264",
    "VideoPlayer.AudioCodec": "aac",
    "VideoPlayer.VideoBitrate": "",
}
xbmc.getInfoLabel = lambda name, *a: LABELS.get(name, "")

q = telemetry.QoE()
r = telemetry.report(telemetry.HEARTBEAT, position_ms=1_234_567, state=telemetry.PLAYING,
                     qoe=q.as_dict(), base_url="http://10.0.0.5:33333", now=1_700_000_000.5)
check("type and timestamp", r["type"] == "heartbeat" and r["timestamp_ms"] == 1_700_000_000_500)
check("position is 100ns TICKS, like every /stream/s/ field",
      r["playback"]["position_ticks"] == 1_234_567 * 10_000, str(r["playback"]["position_ticks"]))
check("resolution is de-localised (1,920 -> 1920x1088)",
      r["playback"]["resolution"] == "1920x1088", str(r["playback"]["resolution"]))
check("codecs come from VideoPlayer.*", (r["playback"]["video_codec"], r["playback"]["audio_codec"]) == ("h264", "aac"))
for field in ("bitrate_kbps", "buffer_ahead_ms", "dropped_frames", "bandwidth_estimate_bps"):
    check(f"{field} is NULL when Kodi cannot measure it", r["playback"][field] is None,
          f"got {r['playback'][field]!r}; a made-up number is worse than none")
check("client identity names the engine that decodes the stream",
      r["client"]["player_engine"] == "Kodi 21.3", str(r["client"]["player_engine"]))
check("...and the same user agent the requests carry", r["client"]["user_agent"] == http.USER_AGENT)
check("every required top-level field is present",
      all(k in r for k in ("type", "timestamp_ms", "client", "playback", "qoe")), str(sorted(r)))
check("a LAN address reports lan", r["connection"] == "lan", str(r["connection"]))
check("a relay address reports relay",
      telemetry.connection_mode("https://api.tofa.tv/servers/abc/relay") == "relay")
check("a public host reports wan", telemetry.connection_mode("https://tofa.example.org:443") == "wan")

LABELS["VideoPlayer.VideoBitrate"] = "8,000"
r2 = telemetry.playback_state(0)
check("a bitrate IS sent once Kodi has one", r2["bitrate_kbps"] == 8000, str(r2["bitrate_kbps"]))

# --- QoE counters: counted on the way in, timed on the way out -----------
q = telemetry.QoE()
check("a stall is counted once when it begins", q.buffering_began(100.0) and q.rebuffer_count == 1)
check("...and not again while it continues", q.buffering_began(101.0) is False and q.rebuffer_count == 1)
check("its duration accrues while still stalled", q.as_dict(now=103.0)["rebuffer_duration_ms"] == 3000.0)
check("...and is banked when it ends", q.buffering_ended(104.5) and q.as_dict()["rebuffer_duration_ms"] == 4500.0)
check("ending twice is a no-op", q.buffering_ended(105.0) is False)
check("switch and recovery counts are zero, truthfully",
      q.as_dict()["quality_switch_count"] == 0 and q.as_dict()["recovery_attempts"] == 0)

# --- the monitor: transitions, cadence, back-off, and never-raises --------
class Client:
    base_url = "http://10.0.0.5:33333"
    def __init__(self): self.sent = []; self.fail = None
    def report_telemetry(self, sid, stok, payload, timeout=None):
        if self.fail: raise self.fail
        self.sent.append(payload)


class Player(monitor.TofaPlayer):
    def __init__(self):
        super().__init__()
        self.client = Client()
        self.pos = 0
    def _client(self): return self.client
    def _position_ms(self): return self.pos


p = Player()
p._session = {"file_id": "f", "media_id": "m", "session_id": "s", "session_token": "t"}
p._position_advanced_at = 1000.0
kinds = lambda: [x["type"] for x in p.client.sent]

# Three ticks with the position moving: exactly one heartbeat, no state changes.
for i, t in enumerate((1010.0, 1020.0, 1030.0)):
    p._position_advanced_at = t   # _check_stall would have reset this
    p._tick_telemetry(now=t)
check("a heartbeat every third tick while playing", kinds() == ["heartbeat"], str(kinds()))
check("...reporting playing", p.client.sent[0]["player_state"] == "playing")

# The position stops moving: one state_change in, one out.
p._position_advanced_at = 1030.0
p._tick_telemetry(now=1033.0)           # frozen 3s > TELEMETRY_STALL_AFTER_S
check("a frozen position becomes ONE buffering state_change",
      kinds()[-1] == "state_change" and p.client.sent[-1]["player_state"] == "buffering", str(kinds()))
p._tick_telemetry(now=1043.0)           # still frozen
check("...not repeated while it persists", kinds().count("state_change") == 1, str(kinds()))
p._position_advanced_at = 1050.0        # moved again
p._tick_telemetry(now=1050.0)
check("...and one state_change back to playing when it moves",
      kinds().count("state_change") == 2 and p.client.sent[-1]["player_state"] == "playing", str(kinds()))
check("the stall reached the QoE counters",
      p.client.sent[-1]["qoe"]["rebuffer_count"] == 1 and p.client.sent[-1]["qoe"]["rebuffer_duration_ms"] == 17000.0,
      str(p.client.sent[-1]["qoe"]))

# Paused positions are allowed to stand still.
p._is_paused = True
p._position_advanced_at = 1050.0
p._tick_telemetry(now=1080.0)
check("a paused position is not a stall", kinds().count("state_change") == 2)
p._is_paused = False

# 429: quiet for the back-off, then resume.
p.client.fail = http.ApiError(429, "too_many", "slow down")
n = len(p.client.sent)
p._telemetry(telemetry.HEARTBEAT, now=2000.0)
p.client.fail = None
p._telemetry(telemetry.HEARTBEAT, now=2001.0)
check("a 429 mutes the channel", len(p.client.sent) == n, "a report went out inside the back-off")
p._telemetry(telemetry.HEARTBEAT, now=2000.0 + monitor.TELEMETRY_BACKOFF_S + 1)
check("...and it comes back after TELEMETRY_BACKOFF_S", len(p.client.sent) == n + 1)

# Anything else telemetry does wrong must not reach the caller.
p.client.fail = RuntimeError("Kodi answered something odd")
try:
    p._telemetry(telemetry.SESSION_END, now=3000.0)
    raised = False
except Exception:                                           # noqa: BLE001
    raised = True
check("a telemetry failure never raises into the progress path", not raised)

# The session-end report names its error when there is one.
p.client.fail = None
p._telemetry(telemetry.FATAL_ERROR, error={"code": "stall_timeout", "fatal": True, "message": "30s"}, now=3001.0)
check("a fatal report carries its ErrorInfo",
      p.client.sent[-1]["type"] == "fatal_error" and p.client.sent[-1]["error"]["code"] == "stall_timeout")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
