"""A converted stream's ASS track gets the file's attached fonts.

Kodi's libass reads special://temp/fonts/ when a subtitle opens. From a
whole file Kodi extracts the attachments there itself; a transcoded stream
carries none, so the player fetches them from the session instead.

Run:  python3 test_ass_session_fonts.py
"""
import os
import shutil

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmcvfs
from resources.lib import http
from resources.lib.windows import player
from resources.lib.windows.player import PlayerWindow, font_file_name

RESULTS = []
TOKEN = "tok"
ASS_TRACK = {"index": 3, "codec": "ass", "external": False,
             "representations": [{"format": "ass"}, {"format": "vtt"}]}
SRT_TRACK = {"index": 4, "codec": "subrip", "external": False,
             "representations": [{"format": "vtt"}]}
FONTS = [{"index": 8, "filename": "arial_0.ttf"},
         {"index": 9, "filename": "../../escape.ttf"},
         {"index": 10, "filename": "missing.otf"},
         {"index": 11, "filename": "Avenir Heavy_0"}]
FOLDER = xbmcvfs.translatePath("special://temp/fonts/")


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Resp:
    def __init__(self, body):
        self.content = body
        self.headers = {"X-Tofa-Subtitle-Time-Basis": "session-local"}


class FakeClient:
    def __init__(self):
        self.fonts = []

    def resolve_url(self, path):
        return "http://box.local:33333" + path

    def session_font(self, sid, tok, index):
        self.fonts.append((sid, tok, index))
        if index == 10:
            raise http.ApiError(404, "not_found", "No such font attachment")
        return Resp(b"FONT%d" % index)

    def session_subtitle(self, *args, **kwargs):
        return Resp(b"[Events]\n")


class Fake:
    _external_subtitle_url = PlayerWindow._external_subtitle_url
    _session_subtitle_file = PlayerWindow._session_subtitle_file
    _install_session_fonts = PlayerWindow._install_session_fonts
    _is_vobsub_sidecar = staticmethod(PlayerWindow._is_vobsub_sidecar)

    def __init__(self, session, play_method="Transcode", fonts=FONTS, offset_ms=0):
        self._subtitle_tracks = [ASS_TRACK, SRT_TRACK]
        self._nego = {"session_id": session, "session_token": TOKEN,
                      "play_method": play_method, "font_attachments": fonts}
        self._time_offset_ms = offset_ms
        self._fonts_session = None
        self._subtitle_bytes = {}
        self.client = FakeClient()


def listing():
    return sorted(os.listdir(FOLDER)) if os.path.isdir(FOLDER) else []


def run():
    shutil.rmtree(FOLDER, ignore_errors=True)
    win = Fake("s1")
    win._external_subtitle_url(3)
    check("every attached font is asked for with the session token",
          win.client.fonts == [("s1", TOKEN, i) for i in (8, 9, 10, 11)], repr(win.client.fonts))
    check("fonts land in Kodi's temp font folder under safe names",
          listing() == ["Avenir Heavy_0.ttf", "arial_0.ttf", "escape.ttf"], repr(listing()))
    with open(os.path.join(FOLDER, "arial_0.ttf"), "rb") as f:
        check("the bytes are the attachment's", f.read() == b"FONT8")
    check("nothing escapes the folder", not os.path.exists(os.path.join(FOLDER, "..", "..", "escape.ttf")))

    win.client.fonts.clear()
    win._external_subtitle_url(3)
    check("a second load in the same session fetches nothing", win.client.fonts == [],
          repr(win.client.fonts))
    win._nego["session_id"] = "s2"
    win._external_subtitle_url(3)
    check("a new session fetches again", len(win.client.fonts) == 4, repr(win.client.fonts))

    other = Fake("s3")
    other._external_subtitle_url(4)
    check("a plain-text track fetches no fonts", other.client.fonts == [])
    whole = Fake("s4", play_method="DirectPlay")
    whole._external_subtitle_url(3)
    check("direct play leaves fonts to Kodi", whole.client.fonts == [])
    bare = Fake("s5", fonts=[])
    bare._external_subtitle_url(3)
    check("a file without attachments costs nothing", bare.client.fonts == [])

    saved = player.FONT_BUDGET_BYTES
    player.FONT_BUDGET_BYTES = 5
    capped = Fake("s6")
    capped._external_subtitle_url(3)
    player.FONT_BUDGET_BYTES = saved
    check("the size budget stops further downloads", len(capped.client.fonts) == 1,
          repr(capped.client.fonts))

    check("names get an extension Kodi loads",
          [font_file_name(n, 7) for n in ("x.TTF", "font.bin", "", None, "a:b?.otf")]
          == ["x.ttf", "font.bin.ttf", "font-7.ttf", "font-7.ttf", "a_b_.otf"])

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("attached fonts reach libass on a converted stream (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
