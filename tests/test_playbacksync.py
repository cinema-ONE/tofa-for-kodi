"""Audio and subtitle sync: quantisation, clamping, labels, and the shadow.

The quantisation cases are the point of this suite. `Player.SetAudioDelay`
rejects an offset that is not an exact multiple of 0.025, and 0.025 has no
exact binary form -- so naive accumulation produces 0.30000000000000004 after
twelve presses and the RPC starts silently refusing. Every step here is
walked by actually pressing, not by asserting one value in isolation.

Run:  python3 test_playbacksync.py
"""
import json

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
from resources.lib import playbacksync as ps

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# ---- a fake Kodi that behaves like the real RPC ---------------------------

class FakeKodi:
    """Answers the three methods playbacksync uses, and -- crucially --
    REJECTS an offset that is not a multiple of 0.025, the way Kodi does."""

    def __init__(self, playing=True):
        self.playing = playing
        self.offset = 0.0
        self.rejected = []
        self.actions = []

    def rpc(self, payload):
        req = json.loads(payload)
        method, params = req.get("method"), req.get("params") or {}
        if method == "Player.GetActivePlayers":
            return json.dumps({"result": [{"playerid": 1, "type": "video"}]
                               if self.playing else []})
        if method == "Player.GetAudioDelay":
            if not self.playing:
                return json.dumps({"error": {"message": "no player"}})
            return json.dumps({"result": {"offset": self.offset}})
        if method == "Player.SetAudioDelay":
            value = params.get("offset")
            if abs(round(value / 0.025) * 0.025 - value) > 1e-9:
                self.rejected.append(value)
                return json.dumps({"error": {"message": "not a multiple"}})
            self.offset = value
            return json.dumps({"result": "OK"})
        return json.dumps({"result": {}})

    def builtin(self, command):
        self.actions.append(command)


def install(fake):
    xbmc.executeJSONRPC = fake.rpc
    xbmc.executebuiltin = fake.builtin
    return fake


# ---- quantise: exact multiples, always -----------------------------------

check("quantise snaps to the step", ps.quantise(0.037, 0.025) == 0.025,
      str(ps.quantise(0.037, 0.025)))
check("quantise keeps an exact value", ps.quantise(0.05, 0.025) == 0.05)
check("quantise clamps high", ps.quantise(99.0, 0.025) == 10.0,
      str(ps.quantise(99.0, 0.025)))
check("quantise clamps low", ps.quantise(-99.0, 0.1) == -10.0,
      str(ps.quantise(-99.0, 0.1)))

# The float-drift case, walked the way a viewer walks it.
value = 0.0
for _ in range(40):
    value = ps.quantise(value + 0.025, 0.025)
check("40 presses land exactly on 1.0", value == 1.0, repr(value))
check("...and it is an exact multiple",
      abs(round(value / 0.025) * 0.025 - value) < 1e-12)


# ---- labels ---------------------------------------------------------------

# Zero is a NUMBER, not a claim. "In sync" would assert something nothing
# measures -- and these controls exist precisely because it might be false.
check("zero reads as a number", ps.format_offset(0.0, ps.AUDIO_STEP) == "0.000 s",
      ps.format_offset(0.0, ps.AUDIO_STEP))
# THREE decimals for audio, because the step is 0.025 and two decimals
# rendered it "0.03" -- a row that appears to round its own step badly.
check("audio label carries 3 decimals",
      ps.format_offset(0.05, ps.AUDIO_STEP) == "+0.050 s",
      ps.format_offset(0.05, ps.AUDIO_STEP))
check("one audio step shows exactly",
      ps.format_offset(0.025, ps.AUDIO_STEP) == "+0.025 s",
      ps.format_offset(0.025, ps.AUDIO_STEP))
check("negative audio label",
      ps.format_offset(-0.3, ps.AUDIO_STEP) == "-0.300 s",
      ps.format_offset(-0.3, ps.AUDIO_STEP))
check("subtitle label carries 1 decimal",
      ps.format_offset(-0.3, ps.SUBTITLE_STEP) == "-0.3 s",
      ps.format_offset(-0.3, ps.SUBTITLE_STEP))


# ---- audio: absolute, with read-back --------------------------------------

fake = install(FakeKodi())
check("reads the offset back", ps.audio_offset() == 0.0)

current = ps.audio_offset()
for _ in range(12):
    current = ps.nudge_audio(current, True)
check("12 presses reach 0.30", current == 0.3, repr(current))
check("Kodi accepted every one", not fake.rejected, str(fake.rejected))
check("and Kodi agrees with us", ps.audio_offset() == 0.3, repr(ps.audio_offset()))

for _ in range(24):
    current = ps.nudge_audio(current, False)
check("24 back reaches -0.30", current == -0.3, repr(current))
check("still no rejections", not fake.rejected, str(fake.rejected))

check("set clamps rather than sending out of range",
      ps.set_audio_offset(50.0) == 10.0, repr(ps.set_audio_offset(50.0)))

# Nothing playing: a missing answer must not read as "in sync".
fake = install(FakeKodi(playing=False))
check("no player reads as None, not 0", ps.audio_offset() is None,
      repr(ps.audio_offset()))
check("no player cannot be nudged", ps.nudge_audio(None, True) is None)


# ---- subtitles: the shadow ------------------------------------------------

fake = install(FakeKodi())
sub = ps.SubtitleOffset()
check("shadow starts neutral", sub.label() == "0.0 s", sub.label())

sub.nudge(True)
sub.nudge(True)
sub.nudge(True)
check("three presses reach +0.3", sub.label() == "+0.3 s", sub.label())
delays = [a for a in fake.actions if a.startswith("Action(subtitledelay")]
check("three delay actions were sent", len(delays) == 3, str(fake.actions))
check("and they were the plus action",
      all(a == "Action(subtitledelayplus)" for a in delays), str(delays))
# Every press must also take Kodi's own slider back down -- it raises one per
# press, and that is the "default Estuary bar" reported from the box.
check("each press closes Kodi's slider",
      fake.actions.count("Dialog.Close(sliderdialog,true)") == 3,
      str(fake.actions))

sub.nudge(False)
check("back one reaches +0.2", sub.label() == "+0.2 s", sub.label())
check("the minus action was sent",
      "Action(subtitledelayminus)" in fake.actions[-2:], str(fake.actions[-2:]))

# The clamp must not send an action, or the shadow desynchronises from Kodi.
sub.value = 10.0
sent = len(fake.actions)
sub.nudge(True)
check("clamped nudge sends nothing", len(fake.actions) == sent,
      str(fake.actions[sent:]))
check("clamped value is unchanged", sub.value == 10.0, repr(sub.value))

sub.reset()
check("reset returns to neutral", sub.label() == "0.0 s", sub.label())

# The offset is READ BACK FROM KODI, not remembered by us. Kodi stores it in
# its own video database and re-applies it on the next play; that database is
# the only place the value exists, so a shadow that reset to zero was simply
# lying about an episode that had been adjusted before.
DB = {}
ps.kodi_subtitle_delay = lambda fid: DB.get(str(fid))

a = ps.SubtitleOffset()
a.load("file-A")
check("a file Kodi knows nothing about starts at zero", a.value == 0.0, repr(a.value))

DB["file-B"] = 5.0
b = ps.SubtitleOffset()
b.load("file-B")
check("a stored offset is read back", b.value == 5.0, repr(b.value))
check("...and shown, not claimed to be zero", b.label() == "+5.0 s", b.label())

b.nudge(False)
check("stepping from it works", b.value == 4.9, repr(b.value))

DB["file-C"] = -2.5
c = ps.SubtitleOffset()
c.load("file-C")
check("a negative stored offset reads back", c.label() == "-2.5 s", c.label())

ps.kodi_subtitle_delay = lambda fid: None
d = ps.SubtitleOffset()
d.load("file-D")
check("an unreadable database falls back to zero", d.value == 0.0, repr(d.value))

sub2 = ps.SubtitleOffset()
for _ in range(4):
    sub2.nudge(True)
fake.actions.clear()
sub2.walk_to_zero()
check("walk_to_zero reaches zero", sub2.value == 0.0, repr(sub2.value))
check("...by sending every step back",
      len([a for a in fake.actions if a == "Action(subtitledelayminus)"]) == 4,
      str(fake.actions))


print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
