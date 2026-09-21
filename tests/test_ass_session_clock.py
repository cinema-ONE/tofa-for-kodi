"""An ASS track on a cut transcode reaches Kodi on the session's clock.

The server sends full.ass on the file's clock (time basis `content`); a
session resumed or seeked mid-file starts at the cut. The player shifts the
script into a local file, falls back to the (already shifted) full.vtt if
that fails, and forgets its loaded slots when a seek re-cuts the session.

Run:  python3 test_ass_session_clock.py
"""
import os

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, playback
from resources.lib.windows.player import PlayerWindow

RESULTS = []
SESSION = "11111111-2222-3333-4444-555555555555"
TOKEN = "tok"
ASS_TRACK = {"index": 3, "codec": "ass", "external": False,
             "representations": [{"format": "ass"}, {"format": "vtt"}]}
SCRIPT = ("[Events]\n"
          "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
          "Dialogue: 0,0:00:10.06,0:00:11.18,Default,,0,0,0,,SHAGGY\n"
          "Dialogue: 0,0:03:12.86,0:03:16.14,insert,,0,80,350,,{\\an8}UNSER\n")


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Resp:
    def __init__(self, basis):
        self.content = SCRIPT.encode("utf-8")
        self.headers = {"X-Tofa-Subtitle-Time-Basis": basis}


class FakeClient:
    def __init__(self, basis="content", fail=False):
        self.basis, self.fail, self.calls = basis, fail, []

    def resolve_url(self, path):
        return "http://box.local:33333" + path

    def session_subtitle(self, *args):
        self.calls.append(args)
        if self.fail:
            raise http.ApiError(503, "not_ready", "still extracting")
        return Resp(self.basis)


class Fake:
    _external_subtitle_url = PlayerWindow._external_subtitle_url
    _session_timed_ass = PlayerWindow._session_timed_ass
    _is_vobsub_sidecar = staticmethod(PlayerWindow._is_vobsub_sidecar)
    _install_session_fonts = PlayerWindow._install_session_fonts
    _fonts_session = None
    _seek_via_session = PlayerWindow._seek_via_session
    STATE_OPENING = PlayerWindow.STATE_OPENING

    def __init__(self, offset_ms, client):
        self._time_offset_ms = offset_ms
        self._subtitle_tracks = [ASS_TRACK]
        self._nego = {"session_id": SESSION, "session_token": TOKEN, "play_method": "Transcode"}
        self.client = client
        self._loaded_subtitle_slots = {3: 0}
        self.title, self.played = "", []
        self.ui_player = type("P", (), {"play": lambda _s, url, li: self.played.append(url)})()

    def _hls_session(self): return (SESSION, TOKEN)
    def _publish_time_offset(self): pass
    def _resolve_duration_ms(self): return 1217000
    def setProperty(self, *a): pass
    def refresh_progress(self): pass


def dialogue(path):
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.startswith("Dialogue:")]


def run():
    url = Fake(0, FakeClient())._external_subtitle_url(3)
    check("no cut: Kodi fetches full.ass itself",
          url.startswith("http://") and url.partition("?")[0].endswith("/subtitles/3/full.ass"), url)

    client = FakeClient("content")
    path = Fake(181998, client)._external_subtitle_url(3)
    check("a cut session gets a local .ass file", path.endswith(".ass") and os.path.exists(path), path)
    check("fetched with the session token", client.calls == [(SESSION, TOKEN, 3, "full.ass")],
          repr(client.calls))
    check("events moved onto the session clock",
          dialogue(path) == ["Dialogue: 0,0:00:10.86,0:00:14.14,insert,,0,80,350,,{\\an8}UNSER"],
          repr(dialogue(path)))

    path2 = Fake(5000, FakeClient("session-local"))._external_subtitle_url(3)
    check("an already session-local script is not shifted twice",
          dialogue(path2)[0].startswith("Dialogue: 0,0:00:10.06,"), repr(dialogue(path2)))
    check("the previous local file is cleaned up", not os.path.exists(path), path)

    url = Fake(181998, FakeClient(fail=True))._external_subtitle_url(3)
    check("a failed fetch falls back to the shifted full.vtt",
          url.partition("?")[0].endswith("/subtitles/3/full.vtt"), url)

    playback.build_list_item = lambda *a, **k: object()    # the stub ListItem has no info tag
    win = Fake(181998, FakeClient())
    win.client.seek_stream = lambda sid, tok, ms: {
        "stream_url": "/api/v1/stream/s/x/master.m3u8", "play_method": "Transcode",
        "start_position_ticks": 300000 * 10000}
    ok = win._seek_via_session(300000)
    check("a re-cut reopens on the new clock",
          ok and win._time_offset_ms == 300000 and len(win.played) == 1, repr((ok, win.played)))
    check("a re-cut forgets the loaded subtitle slots", win._loaded_subtitle_slots == {},
          repr(win._loaded_subtitle_slots))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("ASS on a cut session: shifted, cleaned up, re-fetched after a re-cut (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
