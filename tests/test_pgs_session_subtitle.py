"""A picture (PGS) track on a converted stream is fetched in the background.

Kodi cannot wait out a track the server is still extracting (503, minutes
for a film). The player retries, shifts the .sup onto a cut session's clock,
loads it only if the viewer still wants it, and reuses the download after a
re-cut.

Run:  python3 test_pgs_session_subtitle.py
"""
import os
import struct
import threading
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http
from resources.lib.windows import player
from resources.lib.windows.player import PlayerWindow

RESULTS = []
SESSION, TOKEN = "22222222-3333-4444-5555-666666666666", "tok"
PGS_TRACK = {"index": 10, "codec": "hdmv_pgs_subtitle", "external": False, "render": "bitmap",
             "representations": [{"format": "pgs", "schema": "sup-v1", "state": "ready"}]}


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def sup(*seconds):
    out = b""
    for s in seconds:
        for kind in (0x16, 0x80):
            out += b"PG" + struct.pack(">IIBH", int(s * 90000), 0, kind, 11) + b"\x00" * 11
    return out


class Resp:
    headers = {"X-Tofa-Subtitle-Time-Basis": "content"}

    def __init__(self, body):
        self.content = body


class FakeClient:
    def __init__(self, not_ready=0):
        self.not_ready, self.calls = not_ready, 0

    def session_subtitle(self, sid, tok, index, name, timeout=None):
        self.calls += 1
        if self.calls <= self.not_ready:
            raise http.ApiError(503, "subtitle_extraction_pending", "still extracting")
        return Resp(sup(272.856, 621.371))


class FakePlayer:
    def __init__(self):
        self.loaded = []

    def getAvailableSubtitleStreams(self):
        return list(self.loaded)

    def setSubtitles(self, path):
        self.loaded.append(path)


class Fake:
    _select_subtitle = PlayerWindow._select_subtitle
    _load_picture_subtitle = PlayerWindow._load_picture_subtitle
    _load_subtitle_file = PlayerWindow._load_subtitle_file
    _session_subtitle_file = PlayerWindow._session_subtitle_file
    _stream_slot = staticmethod(PlayerWindow._stream_slot)

    def __init__(self, client, offset_ms=600000):
        self._subtitle_tracks = [PGS_TRACK]
        self._subtitle_order = [10]
        self._nego = {"session_id": SESSION, "session_token": TOKEN, "play_method": "Transcode"}
        self._time_offset_ms = offset_ms
        self._loaded_subtitle_slots, self._subtitle_bytes = {}, {}
        self._picture_subtitle_wanted = self._active_subtitle_index = None
        self._stop_tick = threading.Event()
        self.client, self.ui_player = client, FakePlayer()


def settle(win, want=1, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout and len(win.ui_player.loaded) < want:
        time.sleep(0.01)
    time.sleep(0.05)


def first_pts(path):
    with open(path, "rb") as f:
        return struct.unpack(">I", f.read(6)[2:6])[0] / 90000


def run():
    player.PICTURE_SUBTITLE_RETRY_S = 0.01

    win = Fake(FakeClient(not_ready=2))
    check("selecting a picture track returns at once", win._select_subtitle(10) is True)
    settle(win)
    check("it keeps asking while the server extracts, then loads",
          win.client.calls == 3 and len(win.ui_player.loaded) == 1, repr((win.client.calls, win.ui_player.loaded)))
    path = win.ui_player.loaded[0] if win.ui_player.loaded else ""
    check("Kodi gets a local .sup", path.endswith(".sup") and os.path.exists(path), path)
    check("the .sup is on the session clock", abs(first_pts(path) - 21.371) < 0.001, repr(first_pts(path) if path else None))
    check("the slot and the active track are recorded",
          win._loaded_subtitle_slots == {10: 0} and win._active_subtitle_index == 10,
          repr((win._loaded_subtitle_slots, win._active_subtitle_index)))

    win._time_offset_ms = 610000
    again = win._session_subtitle_file(SESSION, TOKEN, 10, "full.sup", player.pgstime.shift)
    check("a re-cut re-shifts the download instead of fetching it again",
          win.client.calls == 3 and abs(first_pts(again) - 11.371) < 0.001, repr(win.client.calls))

    off = Fake(FakeClient(not_ready=10**6))
    off._select_subtitle(10)
    time.sleep(0.05)
    off._picture_subtitle_wanted = None          # the viewer chose Off
    settle(off, timeout=0.3)
    check("turning subtitles off stops the wait, nothing loads", off.ui_player.loaded == [])

    twice = Fake(FakeClient(not_ready=3))
    twice._select_subtitle(10)
    twice._select_subtitle(10)                   # a re-cut asks again
    settle(twice, want=2, timeout=1.0)
    check("a newer request replaces the older one: one load", len(twice.ui_player.loaded) == 1,
          repr(twice.ui_player.loaded))

    closing = Fake(FakeClient(not_ready=10**6))
    player.PICTURE_SUBTITLE_RETRY_S = 5.0
    closing._select_subtitle(10)
    time.sleep(0.05)
    closing._stop_tick.set()                     # the window closes
    time.sleep(0.1)
    check("closing the window ends the wait", not any(t.name == "tofa-player-pgs" and t.is_alive()
                                                       for t in threading.enumerate()))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("picture subtitles load in the background on the session clock (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
