"""A picture (PGS) track the server has not finished is neither offered nor asked for.

Asking starts a preparation that a stopped session cuts short, and the short
file is then served as complete. So on a converted stream an unready picture
track gets no row, no automatic pick and no fetch. A whole file is unaffected:
Kodi reads the track from the container.

Run:  python3 test_pgs_offered_when_ready.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import tracks
from resources.lib.windows import playoptions
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def pgs(index, state, language="eng", external=False):
    return {"index": index, "language": language, "codec": "hdmv_pgs_subtitle",
            "external": external, "render": "bitmap",
            "representations": [{"format": "pgs", "schema": "sup-v1", "state": state}]}


TEXT = {"index": 3, "language": "eng", "codec": "subrip", "external": False, "render": "text",
        "representations": [{"format": "vtt", "schema": "content-v1", "state": "pending"}]}
READY, PENDING, GONE = pgs(10, "ready"), pgs(11, "pending"), pgs(12, "unavailable")
CONVERTED = {"session_id": "s", "session_token": "t", "play_method": "Transcode"}
WHOLE = {"session_id": "s", "session_token": "t", "play_method": "DirectPlay"}


class Client:
    def __init__(self):
        self.calls = 0

    def session_subtitle(self, *a, **k):
        self.calls += 1
        raise AssertionError("an unready picture track must never be asked for")


class Player:
    def __init__(self):
        self.shown = None

    def getAvailableSubtitleStreams(self):
        return []

    def showSubtitles(self, on):
        self.shown = on


class Fake:
    _select_subtitle = PlayerWindow._select_subtitle
    _offered_subtitle_tracks = PlayerWindow._offered_subtitle_tracks
    _apply_language_preferences = PlayerWindow._apply_language_preferences
    _first_by_language = staticmethod(PlayerWindow._first_by_language)
    _stream_slot = staticmethod(PlayerWindow._stream_slot)
    _pick_stream = PlayerWindow._pick_stream
    _join_key = staticmethod(PlayerWindow._join_key)

    def __init__(self, subs, nego=CONVERTED, prefs=None):
        self._subtitle_tracks = list(subs)
        self._subtitle_order = [t["index"] for t in subs]
        self._audio_tracks = [{"index": 1, "language": "eng", "codec": "ac3"}]
        self._nego, self._prefs = dict(nego), prefs or {}
        self._loaded_subtitle_slots = {}
        self._picture_subtitle_wanted = self._active_subtitle_index = None
        self.client, self.ui_player = Client(), Player()
        self.picked = []

    def _playback_prefs(self):
        return self._prefs

    def _load_picture_subtitle(self, index):
        self.picked.append(index)
        return True

    def _log_subtitle_inventory(self, _when):
        pass

    def _current_stream(self, subtitles=False):
        return (-1, False)

    def _kodi_subtitle_streams(self):
        return []

    def _open_panel(self, **panel):
        self.panel = panel


def run():
    check("a ready picture track is ready", not tracks.picture_unready(READY))
    check("pending and unavailable are not",
          tracks.picture_unready(PENDING) and tracks.picture_unready(GONE))
    check("a picture without a state is not ready",
          tracks.picture_unready({"representations": [{"format": "pgs"}]}))
    check("a text track's state is not read", not tracks.picture_unready(TEXT))
    check("a track from an older server (no representations) is offered",
          not tracks.picture_unready({"codec": "hdmv_pgs_subtitle"}))
    check("on a whole file an embedded unready picture is still offered",
          tracks.subtitle_offered(PENDING, whole_file=True))
    check("...but not as a sidecar the server sends",
          not tracks.subtitle_offered(pgs(1000, "pending", external=True), whole_file=True))

    win = Fake([TEXT, READY, PENDING, GONE])
    check("a converted stream offers only the ready picture",
          [t["index"] for t in win._offered_subtitle_tracks()] == [3, 10],
          repr([t["index"] for t in win._offered_subtitle_tracks()]))
    check("selecting an unready picture asks for nothing",
          win._select_subtitle(11) is False and win.client.calls == 0 and win.picked == [])
    check("selecting a ready one still fetches it", win._select_subtitle(10) and win.picked == [10])

    win._pick_stream(subtitles=True)
    check("the in-player panel has Off, the text track and the ready picture",
          len(win.panel["rows"]) == 3, repr([r[0] for r in win.panel["rows"]]))

    whole = Fake([TEXT, PENDING], nego=WHOLE)
    check("a whole file offers the embedded picture",
          [t["index"] for t in whole._offered_subtitle_tracks()] == [3, 11])

    prefs = {"preferred_subtitle_languages": ["eng"], "always_enable_subtitles": True}
    auto = Fake([PENDING], prefs=prefs)
    auto._apply_language_preferences(apply_audio=False)
    check("the automatic pick skips an unready picture and leaves subtitles off",
          auto.picked == [] and auto.ui_player.shown is False, repr((auto.picked, auto.ui_player.shown)))

    info = {"play_method": "Transcode", "subtitle_tracks": [TEXT, PENDING, READY]}
    sections = playoptions.build_sections(info, playoptions.Selection())
    subs = next(s for s in sections if s["key"] == playoptions.SUBTITLES)
    check("the options panel lists no unready picture before a converted play",
          [o["index"] for o in subs["options"][2:]] == [3, 10],
          repr([o["index"] for o in subs["options"]]))
    info["play_method"] = "DirectPlay"
    sections = playoptions.build_sections(info, playoptions.Selection())
    subs = next(s for s in sections if s["key"] == playoptions.SUBTITLES)
    check("...and lists it before a whole-file play",
          [o["index"] for o in subs["options"][2:]] == [3, 11, 10])

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("unready picture tracks are neither offered nor asked for (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
