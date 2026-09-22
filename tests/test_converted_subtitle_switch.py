"""On a converted stream, picking a subtitle fetches it from the server.

A transcode carries no subtitles, so the only streams Kodi lists there are
the ones the player loaded itself. Mapping a server track onto them by
position picked the wrong one: after the English SRT (loaded as Kodi's
stream 0), choosing the German forced ASS -- the server's FIRST track --
switched back to stream 0. Found on the AM9 Pro, 2026-09-22.

Run:  python3 test_converted_subtitle_switch.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def sub(index, codec, fmt):
    return {"index": index, "codec": codec, "language": "ger", "external": False,
            "representations": [{"format": fmt, "schema": "x", "state": "ready"}]}


class UiPlayer:
    def __init__(self, streams):
        self.streams = streams

    def getAvailableSubtitleStreams(self):
        return list(self.streams)


class Fake:
    _select_subtitle = PlayerWindow._select_subtitle
    _stream_slot = staticmethod(PlayerWindow._stream_slot)

    def __init__(self, play_method, streams, loaded):
        self._nego = {"play_method": play_method, "session_id": "s", "session_token": "t"}
        self._subtitle_tracks = [sub(3, "ass", "ass"), sub(4, "subrip", "vtt"),
                                 sub(5, "subrip", "vtt"), sub(6, "subrip", "vtt")]
        self._subtitle_order = [3, 4, 5, 6]
        self._loaded_subtitle_slots = dict(loaded)
        self._active_subtitle_index = None
        self._picture_subtitle_wanted = None
        self.ui_player = UiPlayer(streams)
        self.switched, self.fetched = [], []

    def _switch_subtitle(self, slot):
        self.switched.append(slot)
        return True

    def _external_subtitle_url(self, index):
        return "url-%d" % index

    def _load_subtitle_file(self, index, url):
        self.fetched.append((index, url))
        self._active_subtitle_index = index


# Converted: Kodi lists only what was loaded (English SRT as 0, forced SRT as 1).
p = Fake("Transcode", ["full", "full"], {6: 0, 4: 1})
p._select_subtitle(3)
check("converted: the forced ASS is fetched from the server",
      p.fetched == [(3, "url-3")] and p.switched == [], repr((p.fetched, p.switched)))
check("...and becomes the active track", p._active_subtitle_index == 3)

p = Fake("Transcode", ["full", "full"], {6: 0, 4: 1})
p._select_subtitle(6)
check("converted: a track already loaded switches to its own stream",
      p.switched == [0] and p.fetched == [], repr((p.fetched, p.switched)))

# Whole file: Kodi's own streams mirror the server's, so position is the map.
p = Fake("DirectPlay", ["ger", "ger", "ger", "eng"], {})
p._select_subtitle(3)
check("whole file: an embedded track is Kodi's own stream, by position",
      p.switched == [0] and p.fetched == [], repr((p.fetched, p.switched)))


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("converted streams fetch their subtitles (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
