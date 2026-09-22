"""Subtitle contract 2 is asked for only where the server delivers what it describes.

On server 0.10.0 a contract-2 /stream/{id}/info takes over a second longer
than a contract-1 one on the same file. What 2 adds (`representations`) is
read only for a styled (ASS/SSA) or picture (PGS, VobSub, DVB) track the
server itself delivers: a sidecar always, an embedded track only when the
stream is converted, since Kodi reads a whole file's own tracks. Unknown
tracks still ask for 2.

A converted answer given without 2 is completed from a contract-2 dry run,
which opens no session and lists the same tracks by index (measured).

Run:  python3 test_subtitle_contract_per_file.py
"""
import copy

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


def sub(codec, index=2, external=False):
    return {"index": index, "language": "eng", "codec": codec, "external": external}


SRT_ONLY = [sub("subrip"), sub("subrip", 1000, external=True), sub("mov_text", 3)]
WITH_PGS = [sub("subrip"), sub("hdmv_pgs_subtitle", 3)]
WITH_ASS = [sub("ass")]
PGS_SIDECAR = [sub("subrip"), sub("pgs", 1000, external=True)]
REPS = {"representations": [{"format": "pgs", "schema": "sup-v1", "state": "ready"}],
        "track_id": "t3"}


def contract_of(params):
    return (params or {}).get("subtitle_contract_version")


# --- the rule ------------------------------------------------------------
for tracks_, whole, want, why in (
        (None, True, 2, "unknown tracks keep contract 2"),
        ([], True, None, "a file without subtitles asks for nothing"),
        (SRT_ONLY, False, None, "plain text asks for nothing, even converted"),
        (WITH_PGS, True, None, "an embedded PGS track on a whole file asks for nothing"),
        (WITH_ASS, True, None, "an embedded ASS track on a whole file asks for nothing"),
        (WITH_PGS, False, 2, "an embedded PGS track on a converted stream asks for 2"),
        (WITH_ASS, False, 2, "an embedded ASS track on a converted stream asks for 2"),
        ([sub("ssa")], False, 2, "so does SSA"),
        (PGS_SIDECAR, True, 2, "a PGS sidecar asks for 2 on a whole file"),
        ([sub("ass", 1000, external=True)], True, 2, "so does an ASS sidecar"),
        ([sub("dvd_subtitle", 1000, external=True)], True, 2, "so does a VobSub sidecar"),
        ([sub("PGS", external=True)], True, 2, "the codec is read case-blind"),
        ([None, {}], False, None, "malformed entries are skipped")):
    got = tracks.subtitle_contract_for(tracks_, whole_file=whole)
    check(why, got == want, repr(got))

# --- completing contract-1 tracks ------------------------------------------
session = [sub("subrip"), sub("hdmv_pgs_subtitle", 3)]
tracks.add_contract_fields(session, [dict(sub("hdmv_pgs_subtitle", 3), **REPS),
                                     dict(sub("subrip", 9), representations=[])])
check("contract 2's fields join the track with the same index",
      session[1].get("representations") == REPS["representations"]
      and session[1].get("track_id") == "t3", repr(session[1]))
check("...and nothing joins a track the dry run did not list",
      "representations" not in session[0], repr(session[0]))
check("tracks.picture_unready reads the completed track",
      tracks.picture_unready(session[1]) is False)

# --- the query -----------------------------------------------------------
check("contract 1 is sent as silence",
      "subtitle_contract_version" not in
      CapabilityProfile.for_device(subtitle_contract_version=None).to_query_params())
check("the default profile still asks for 2",
      contract_of(CapabilityProfile.for_device().to_query_params()) == 2)


class Client:
    """stream_info answers with `method` and records every query."""

    def __init__(self, method="DirectPlay", fail=False):
        self.method, self.fail, self.calls = method, fail, []

    def stream_info(self, file_id, profile, **kw):
        self.calls.append((profile.to_query_params(), kw.get("dry_run")))
        if self.fail:
            raise http.ApiError(503, "test", "stop here")
        return {"play_method": self.method, "subtitle_tracks": [dict(sub("hdmv_pgs_subtitle", 3), **REPS)]}


# --- Detail: Options and Play --------------------------------------------
detail_mod.toast.show = lambda *a, **k: None
detail_mod.playoptions.show = lambda **kw: kw.get("selection")


class FakeDetail:
    _open_playback_options = DetailWindow._open_playback_options
    _options_info = DetailWindow._options_info
    _play = DetailWindow._play
    _play_file = DetailWindow._play_file
    _available_files = DetailWindow._available_files

    def __init__(self, file_tracks, client):
        f = {"id": "f1", "available": True}
        if file_tracks is not None:
            f["subtitle_tracks"] = file_tracks
        self.media = {"media_type": "movie", "files": [f], "title": "T"}
        self.is_playable = True
        self.media_id = "m1"
        self.play_file_id = "f1"
        self.play_duration_ms = 0
        self.play_selection = playoptions.Selection()
        self.client = client

    def _get_client(self):
        return self.client

    def _version_row_label(self, f):
        return ""

    def _ensure_preferences(self):
        return {}

    def _renew_profile_token_for(self, runtime_ms):
        pass

    def getProperty(self, key):
        return ""


for tracks_, method, want, what in (
        (SRT_ONLY, "Transcode", [None], "a text-only file"),
        (WITH_PGS, "DirectPlay", [None], "an embedded PGS file that plays directly"),
        (WITH_PGS, "Transcode", [None, 2], "an embedded PGS file that is converted"),
        (PGS_SIDECAR, "DirectPlay", [2], "a PGS sidecar"),
        (None, "DirectPlay", [2], "a file record without tracks")):
    d = FakeDetail(tracks_, Client(method))
    d._open_playback_options()
    got = [contract_of(q) for q, _ in d.client.calls]
    check("Options on %s asks %r" % (what, want), got == want, repr(got))

opened = {}
real_open = PlayerWindow.open
PlayerWindow.open = classmethod(lambda cls, **kw: opened.update(kw))
try:
    FakeDetail(WITH_ASS, Client())._play(0)
finally:
    PlayerWindow.open = real_open
check("Play hands the file's tracks to the player",
      opened.get("subtitle_tracks") == WITH_ASS, repr(opened.get("subtitle_tracks")))

# --- the player: negotiation, the quality picker, Up Next -----------------
class Stop(Exception):
    pass


negotiated = []
answer = {}


def fake_negotiate(client, file_id, profile, **kw):
    negotiated.append((file_id, profile.to_query_params()))
    return copy.deepcopy(answer)


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
    _add_contract_fields = PlayerWindow._add_contract_fields
    _pick_quality = PlayerWindow._pick_quality
    _play_episode = PlayerWindow._play_episode

    def __init__(self, file_tracks, client=None):
        self.file_id = "f1"
        self.media_id = "m1"
        self._file_subtitle_tracks = file_tracks
        self.selection = playoptions.Selection()
        self.resume_ms = None
        self.title = "T"
        self._duration_ms = 0
        self._subtitle_offset = SubtitleOffset()
        self.ui_player = UiPlayer()
        self.client = client or Client()
        self.resp = None

    def _get_client(self):
        return self.client

    def fail(self, message):
        raise AssertionError("negotiation failed: %s" % message)

    def _publish_time_offset(self):
        raise Stop()          # everything worth checking has happened by now

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


def start(p, method):
    answer.clear()
    answer.update(play_method=method, subtitle_tracks=copy.deepcopy(p._file_subtitle_tracks or []))
    before = len(negotiated)
    try:
        p._start_playback()
    except Stop:
        pass
    return negotiated[before:]


p = FakePlayer(WITH_PGS)
sent = start(p, "DirectPlay")
check("a direct PGS play negotiates contract 1 and asks nothing more",
      [contract_of(q) for _, q in sent] == [None] and not p.client.calls, repr((sent, p.client.calls)))

p = FakePlayer(PGS_SIDECAR)
sent = start(p, "DirectPlay")
check("a PGS sidecar negotiates contract 2",
      [contract_of(q) for _, q in sent] == [2] and not p.client.calls, repr(sent))

p = FakePlayer(None)
sent = start(p, "DirectPlay")
check("unknown tracks negotiate contract 2", [contract_of(q) for _, q in sent] == [2], repr(sent))

p = FakePlayer(WITH_PGS)
completed = {}
orig_add = tracks.add_contract_fields


def spy(session_tracks, contract2_tracks):
    orig_add(session_tracks, contract2_tracks)
    completed["tracks"] = session_tracks


player_mod.tracks.add_contract_fields = spy
try:
    sent = start(p, "Transcode")
finally:
    player_mod.tracks.add_contract_fields = orig_add
dry = p.client.calls
check("a converted PGS play negotiates contract 1, then dry-runs contract 2",
      [contract_of(q) for _, q in sent] == [None]
      and [(contract_of(q), d) for q, d in dry] == [(2, True)], repr((sent, dry)))
pgs = next((t for t in completed.get("tracks") or [] if t.get("index") == 3), {})
check("...and the session's PGS track carries the dry run's state",
      pgs.get("representations") == REPS["representations"], repr(pgs))

p = FakePlayer(WITH_PGS, Client(fail=True))
try:
    start(p, "Transcode")
    ok = True
except Exception as exc:                                  # noqa: BLE001
    ok = False
    print("   ", repr(exc))
check("a failed dry run does not stop playback", ok)

p = FakePlayer(PGS_SIDECAR)
p._pick_quality()
check("the quality picker never asks for 2",
      [contract_of(q) for q, _ in p.client.calls] == [None], repr(p.client.calls))

p = FakePlayer(SRT_ONLY)
answer.clear()
answer.update(play_method="Transcode", subtitle_tracks=[])
before = len(negotiated)
try:
    p._play_episode(({"season_number": 1}, {"episode_number": 2, "title": "E2"},
                     {"id": "f2", "subtitle_tracks": PGS_SIDECAR}))
except Stop:
    pass
check("Up Next negotiates the NEXT file's contract",
      [(f, contract_of(q)) for f, q in negotiated[before:]] == [("f2", 2)],
      repr(negotiated[before:]))


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("contract 2 only where the server delivers what it describes (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
