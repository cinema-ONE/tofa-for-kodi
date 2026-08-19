"""Play Next must not inherit the previous episode's audio track.

Reported 2026-08-19 from the cinema box (add-on issue #67), and reported
AGAIN the same evening after the first fix shipped: pressing Play Next at the
end of Murder, She Wrote S2 E19 started S2 E20 in GERMAN. Both episodes list
German first, English second, and the profile asks for English.

The client resolved English correctly both times. What discarded it was
`_switch_audio`'s shortcut, which skips `setAudioStream()` when the wanted
slot is already active -- reading that slot from `currentaudiostream`:

    18:04:33.24  VideoPlayer::OpenFile  (the next episode)
    18:04:33.53  Opening stream: 1      <- ger, the container default
    18:04:33.84  audio[open] kodi_current=1 showing_current=True
                 audio already on slot 1; not switching

`kodi_current=1` is English's slot -- in a file Kodi had opened on German.
The index comes from `CApplicationPlayer::GetAudioStream()`, a ONE-SECOND
cache (`m_audioStreamUpdate.Set(1000ms)`) that `OpenFile` expires as the open
is queued, so any reader in the window before the new audio stream opens
re-fills it from the OUTGOING file. PR #68's `_showing_current_item()` cannot
see that: `Player.GetItem` is not behind the cache, so it answered "yes, the
new episode" while the index still described the old one.

Reproduced deliberately on local Kodi with two plain mkvs and a 40ms poller
in the role of the box's JSON-RPC clients -- no add-on involved:

    +0.30s  currentaudiostream index 1 ("eng")   AudioLanguage ger   epB.mkv
    +1.00s  currentaudiostream index 1 ("eng")   AudioLanguage ger   epB.mkv
    +1.08s  currentaudiostream index 0 ("ger")   AudioLanguage ger   epB.mkv

With no poller the same read is right from +0.30s, which is why local Kodi
and the AM6B+ never showed this. The stream INVENTORY and the InfoLabels were
right in every sample, so those are what the shortcut trusts now.

Exercises the REAL methods bound to a stand-in `self`, so the test cannot
drift from the implementation. Run:  python3 test_audio_changeover_guard.py
"""
import json

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeUIPlayer:
    def __init__(self):
        self.audio_switches = []
        self.subtitle_switches = []

    def setAudioStream(self, slot):
        self.audio_switches.append(slot)

    def setSubtitleStream(self, slot):
        self.subtitle_switches.append(slot)


class FakeKodi:
    """Kodi's two surfaces: the JSON-RPC inventory and the InfoLabels.

    `cached_index` is what `currentaudiostream` answers -- deliberately
    allowed to disagree with `labels`, because that disagreement IS the bug.
    """

    def __init__(self, streams, labels, cached_index=None, subtitle_enabled=True,
                 subtitles=()):
        self.streams = list(streams)
        self.subtitles = list(subtitles)
        self.labels = dict(labels)
        self.cached_index = cached_index
        self.subtitle_enabled = subtitle_enabled

    def executeJSONRPC(self, payload):
        req = json.loads(payload)
        method, params = req["method"], req.get("params") or {}
        if method == "Player.GetActivePlayers":
            result = [{"playerid": 1, "type": "video"}]
        elif method == "Player.GetProperties":
            wanted = params.get("properties") or []
            result = {}
            if "audiostreams" in wanted:
                result["audiostreams"] = self.streams
            if "subtitles" in wanted:
                result["subtitles"] = self.subtitles
            if "currentaudiostream" in wanted:
                result["currentaudiostream"] = {"index": self.cached_index}
            if "currentsubtitle" in wanted:
                result["currentsubtitle"] = {"index": self.cached_index}
            if "subtitleenabled" in wanted:
                result["subtitleenabled"] = self.subtitle_enabled
        else:
            result = {}
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})

    def getInfoLabel(self, name):
        return self.labels.get(name, "")


class FakePlayer:
    """Only what the guards and the confirmation touch."""

    def __init__(self, kodi):
        self.ui_player = FakeUIPlayer()
        self._kodi = kodi
        self._audio_confirm_at = 0.0
        self._audio_confirm_slot = None

    # bound straight off the real class, so the test follows the code
    _AUDIO_LABELS = PlayerWindow._AUDIO_LABELS
    _kodi_audio_streams = PlayerWindow._kodi_audio_streams
    _kodi_subtitle_streams = PlayerWindow._kodi_subtitle_streams
    _playing_audio_slot = PlayerWindow._playing_audio_slot
    _playing_subtitle_slot = PlayerWindow._playing_subtitle_slot
    _current_stream = PlayerWindow._current_stream
    _arm_audio_confirmation = PlayerWindow._arm_audio_confirmation
    _confirm_audio_slot = PlayerWindow._confirm_audio_slot


GER_ENG = [{"index": 0, "language": "ger", "codec": "ac3", "channels": 2},
           {"index": 1, "language": "eng", "codec": "ac3", "channels": 2}]


def player(streams=GER_ENG, playing="eng", cached_index=None, **kw):
    kodi = FakeKodi(streams, {"VideoPlayer.AudioLanguage": playing,
                              "VideoPlayer.SubtitlesLanguage": playing},
                    cached_index=cached_index, **kw)
    xbmc.executeJSONRPC = kodi.executeJSONRPC
    xbmc.getInfoLabel = kodi.getInfoLabel
    return FakePlayer(kodi)


def switch_audio(wanted, playing, streams=GER_ENG, cached_index=None):
    p = player(streams, playing, cached_index)
    changed = PlayerWindow._switch_audio(p, wanted)
    return changed, p.ui_player.audio_switches


# --- the incident ---------------------------------------------------------
# The cache says slot 1 (English -- that was E19). German is what is playing.
changed, switches = switch_audio(wanted=1, playing="ger", cached_index=1)
check("mid-changeover: the cached index cannot skip the switch",
      changed and switches == [1], "switches=%r" % switches)

# --- the shortcut still works when the audio really is there --------------
changed, switches = switch_audio(wanted=1, playing="eng", cached_index=1)
check("settled: the shortcut still skips a pointless renderer change",
      (not changed) and switches == [], "switches=%r" % switches)

# --- a genuine change is never blocked ------------------------------------
changed, switches = switch_audio(wanted=1, playing="ger", cached_index=0)
check("a real switch happens", changed and switches == [1],
      "switches=%r" % switches)

# --- ambiguity answers None, which switches -------------------------------
TWO_ENG = [{"index": 0, "language": "eng", "codec": "ac3", "channels": 2},
           {"index": 1, "language": "eng", "codec": "ac3", "channels": 2}]
changed, switches = switch_audio(wanted=1, playing="eng", streams=TWO_ENG)
check("two identical English tracks: no false skip",
      changed and switches == [1], "switches=%r" % switches)

# ...but a commentary track IS told apart, so the shortcut survives it
COMMENTARY = [{"index": 0, "language": "eng", "codec": "dts", "channels": 6},
              {"index": 1, "language": "eng", "codec": "ac3", "channels": 2}]
p = player(COMMENTARY, "eng")
p._kodi.labels.update({"VideoPlayer.AudioCodec": "ac3",
                       "VideoPlayer.AudioChannels": "2"})
check("codec and channels break a same-language tie",
      PlayerWindow._playing_audio_slot(p) == 1)

# --- nothing to read answers None, and None switches ----------------------
p = player(GER_ENG, playing="")
check("no InfoLabel: the slot cannot be told, so it is not trusted",
      PlayerWindow._playing_audio_slot(p) is None)

# --- subtitles carry the identical defect, so the identical fix -----------
SUBS = [{"index": 0, "language": "eng"}, {"index": 1, "language": "ger"}]
# English is on screen; the cached index claims the German slot we want.
p = player(GER_ENG, playing="eng", cached_index=1, subtitles=SUBS)
changed = PlayerWindow._switch_subtitle(p, 1)
check("subtitles: a stale index does not skip the switch",
      changed and p.ui_player.subtitle_switches == [1],
      "switches=%r" % p.ui_player.subtitle_switches)
p = player(GER_ENG, playing="ger", cached_index=0, subtitles=SUBS)
changed = PlayerWindow._switch_subtitle(p, 1)
check("subtitles: the shortcut still skips when that track is on screen",
      (not changed) and p.ui_player.subtitle_switches == [],
      "switches=%r" % p.ui_player.subtitle_switches)
p = player(GER_ENG, playing="ger", subtitles=SUBS, subtitle_enabled=False)
changed = PlayerWindow._switch_subtitle(p, 1)
check("subtitles: a disabled track is switched on even on the right slot",
      changed and p.ui_player.subtitle_switches == [1])

# --- the confirmation pass ------------------------------------------------
p = player(GER_ENG, playing="ger")            # we asked for English (slot 1)
p._arm_audio_confirmation(1)
p._audio_confirm_at = 1.0
PlayerWindow._confirm_audio_slot(p, 2.0)
check("confirmation corrects a track that landed in the wrong language",
      p.ui_player.audio_switches == [1],
      "switches=%r" % p.ui_player.audio_switches)
check("confirmation fires once", p._audio_confirm_at == 0.0)

p = player(TWO_ENG, playing="eng")            # same language, other track
p._arm_audio_confirmation(1)
p._audio_confirm_at = 1.0
PlayerWindow._confirm_audio_slot(p, 2.0)
check("confirmation does not fight over a same-language track",
      p.ui_player.audio_switches == [],
      "switches=%r" % p.ui_player.audio_switches)

p = player(GER_ENG, playing="ger")
p._arm_audio_confirmation(1)
PlayerWindow._confirm_audio_slot(p, 0.0)      # not due yet
check("confirmation waits for its deadline", p.ui_player.audio_switches == [])

p = player(GER_ENG, playing="eng")
p._arm_audio_confirmation(1)
p._audio_confirm_at = 1.0
PlayerWindow._confirm_audio_slot(p, 2.0)
check("confirmation is silent when the track landed",
      p.ui_player.audio_switches == [])

print("")
failed = [n for n, ok in RESULTS if not ok]
print("audio changeover guard: a cached index cannot cost the chosen track "
      "(%d checks)" % len(RESULTS))
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
