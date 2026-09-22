"""Subtitle contract 2 is asked for only where the file's own tracks need it.

On server 0.10.0 a contract-2 /stream/{id}/info takes over a second longer
than a contract-1 one on the same file. What 2 adds (`representations`)
matters only for styled (ASS/SSA) and picture (PGS, VobSub, DVB) tracks, and
the title's file record lists those before anything is negotiated. So Options,
Play, the quality picker and Up Next ask for 2 on those files only, and keep
asking for it whenever the tracks are unknown.

Run:  python3 test_subtitle_contract_per_file.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, playback, tracks
from resources.lib.profile import CapabilityProfile
from resources.lib.windows import detail as detail_mod, player as player_mod, playoptions
from resources.lib.windows.detail import DetailWindow
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def sub(codec, external=False):
    return {"index": 2, "language": "eng", "codec": codec, "external": external}


SRT_ONLY = [sub("subrip"), sub("subrip", external=True), sub("mov_text")]
WITH_PGS = [sub("subrip"), sub("hdmv_pgs_subtitle")]
WITH_ASS = [sub("ass")]


class Recorder:
    """A client whose stream_info records the query and then fails."""

    def __init__(self):
        self.params = None

    def stream_info(self, file_id, profile, **kw):
        self.params = profile.to_query_params()
        raise http.ApiError(503, "test", "stop here")


def contract_of(params):
    return (params or {}).get("subtitle_contract_version")


# --- the rule ------------------------------------------------------------
for tracks_, want, why in (
        (None, 2, "unknown tracks keep contract 2"),
        ([], None, "a file without subtitles asks for nothing"),
        (SRT_ONLY, None, "plain text tracks ask for nothing"),
        ([sub("webvtt")], None, "WebVTT asks for nothing"),
        (WITH_ASS, 2, "an ASS track asks for 2"),
        ([sub("ssa")], 2, "an SSA track asks for 2"),
        (WITH_PGS, 2, "one PGS track among text asks for 2"),
        ([sub("dvd_subtitle")], 2, "an embedded VobSub asks for 2"),
        ([sub("dvd_subtitle", external=True)], 2, "a VobSub sidecar asks for 2"),
        ([sub("dvb_subtitle")], 2, "a DVB track asks for 2"),
        ([sub("PGS")], 2, "the codec is read case-blind"),
        ([None, {}], None, "malformed entries are skipped")):
    got = tracks.subtitle_contract_for(tracks_)
    check(why, got == want, repr(got))

# --- the query -----------------------------------------------------------
check("contract 1 is sent as silence",
      "subtitle_contract_version" not in
      CapabilityProfile.for_device(subtitle_contract_version=None).to_query_params())
check("the default profile still asks for 2",
      contract_of(CapabilityProfile.for_device().to_query_params()) == 2)

# --- Detail: Options and Play --------------------------------------------
detail_mod.toast.show = lambda *a, **k: None


class FakeDetail:
    _open_playback_options = DetailWindow._open_playback_options
    _play = DetailWindow._play
    _play_file = DetailWindow._play_file
    _available_files = DetailWindow._available_files

    def __init__(self, file_tracks):
        f = {"id": "f1", "available": True}
        if file_tracks is not None:
            f["subtitle_tracks"] = file_tracks
        self.media = {"media_type": "movie", "files": [f], "title": "T"}
        self.is_playable = True
        self.media_id = "m1"
        self.play_file_id = "f1"
        self.play_duration_ms = 0
        self.play_selection = playoptions.Selection()
        self.client = Recorder()

    def _get_client(self):
        return self.client

    def _renew_profile_token_for(self, runtime_ms):
        pass

    def getProperty(self, key):
        return ""


for tracks_, want, what in ((SRT_ONLY, None, "a text-only file"),
                            (WITH_PGS, 2, "a PGS file"),
                            (None, 2, "a file record without tracks")):
    d = FakeDetail(tracks_)
    d._open_playback_options()
    check("Options on %s asks for %r" % (what, want),
          contract_of(d.client.params) == want, repr(d.client.params))

opened = {}
real_open = PlayerWindow.open
PlayerWindow.open = classmethod(lambda cls, **kw: opened.update(kw))
try:
    FakeDetail(WITH_ASS)._play(0)
finally:
    PlayerWindow.open = real_open
check("Play hands the file's tracks to the player",
      opened.get("subtitle_tracks") == WITH_ASS, repr(opened.get("subtitle_tracks")))

# --- the player: negotiation, the quality picker, Up Next -----------------
negotiated = []


def fake_negotiate(client, file_id, profile, **kw):
    negotiated.append((file_id, profile.to_query_params()))
    raise playback.NegotiateTimeout()


player_mod.playback.negotiate = fake_negotiate
player_mod.stereoscopic.suppress_ask = lambda: None
player_mod.stereoscopic.was_suppressed = lambda: False


class SubtitleOffset:
    def load(self, file_id):
        pass


class UiPlayer:
    def stop(self):
        pass


class FakePlayer:
    STATE_OPENING = PlayerWindow.STATE_OPENING
    _start_playback = PlayerWindow._start_playback
    _pick_quality = PlayerWindow._pick_quality
    _play_episode = PlayerWindow._play_episode

    def __init__(self, file_tracks):
        self.file_id = "f1"
        self._file_subtitle_tracks = file_tracks
        self.selection = playoptions.Selection()
        self.resume_ms = None
        self.title = "T"
        self._duration_ms = 0
        self._subtitle_offset = SubtitleOffset()
        self.ui_player = UiPlayer()
        self.client = Recorder()
        self.failed = None

    def _get_client(self):
        return self.client

    def fail(self, message):
        self.failed = message

    def _position_ms(self):
        return 0

    def setProperty(self, key, value):
        pass

    def _hide_skip(self, used):
        pass

    def _close_out_session(self, *a, **k):
        pass

    def getFocusId(self):
        return 0

    def _defer_focus_restore(self, control_id):
        pass


p = FakePlayer(SRT_ONLY)
p._start_playback()
check("Play on a text-only file negotiates contract 1",
      negotiated and contract_of(negotiated[-1][1]) is None, repr(negotiated[-1:]))
p = FakePlayer(None)
p._start_playback()
check("Play with unknown tracks negotiates contract 2",
      contract_of(negotiated[-1][1]) == 2, repr(negotiated[-1:]))
p = FakePlayer(WITH_PGS)
p._pick_quality()
check("the quality picker on a PGS file asks for 2",
      contract_of(p.client.params) == 2, repr(p.client.params))

p = FakePlayer(WITH_PGS)
p._play_episode(({"season_number": 1}, {"episode_number": 2, "title": "E2"},
                 {"id": "f2", "subtitle_tracks": SRT_ONLY}))
check("Up Next negotiates the NEXT file's contract",
      negotiated[-1][0] == "f2" and contract_of(negotiated[-1][1]) is None,
      repr(negotiated[-1:]))
p._play_episode(({"season_number": 1}, {"episode_number": 3},
                 {"id": "f3", "subtitle_tracks": WITH_ASS}))
check("...and back to 2 when that one has styled tracks",
      negotiated[-1][0] == "f3" and contract_of(negotiated[-1][1]) == 2,
      repr(negotiated[-1:]))


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("contract 2 only where the file's tracks need it (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
