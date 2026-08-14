"""An explicit pick in 7.7's panel must only override its OWN half.

A LATENT bug, found while chasing a different one and fixed on the way past.
It is NOT what was reported from the cinema box -- that viewer had touched
nothing (see playbackprefs.py) -- but it is real, and it produces the same
symptom, which is exactly why it needs pinning rather than leaving.

7.7's panel writes `subtitle_index` only when the Subtitles section is used
and `audio_index` only when Audio is, and `DetailWindow.play_selection`
outlives a play. So choosing a subtitle once on a title leaves a Selection
with a subtitle index and no audio index -- and apply_track_selection read

    if audio_index is None and subtitle_index is None:
        apply the language preferences; return

which that Selection fails. The language preferences were skipped, the
explicit branch set only subtitles, and the audio was never touched at all:
it stayed on whatever the file listed FIRST. On a German-first file with an
English-first profile that plays German, silently, with nothing in the log.

The file modelled below is the real one from the report: `ger` first, then
`eng`, exactly as the server reports it.

Run:  python3 test_track_selection_halves.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import playoptions
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


# ger FIRST, eng second -- the layout that makes the bug visible.
AUDIO = [{"index": 1, "language": "ger", "codec": "ac3", "channels": 2},
         {"index": 2, "language": "eng", "codec": "ac3", "channels": 2}]
SUBS = [{"index": 3, "language": "eng", "codec": "subrip"}]
PREFS = {"playback": {"preferred_audio_languages": ["eng", "deu"],
                      "preferred_subtitle_languages": ["eng", "deu"],
                      "always_enable_subtitles": True}}


class FakePlayer:
    def __init__(self):
        self.audio_slot = None
        self.subs_shown = None

    def getAvailableAudioStreams(self):
        return ["ger", "eng"]

    def setAudioStream(self, slot):
        self.audio_slot = slot

    def setSubtitleStream(self, slot):
        pass

    def showSubtitles(self, on):
        self.subs_shown = on


class Fake:
    """Only the machinery apply_track_selection actually reaches."""
    apply_track_selection = PlayerWindow.apply_track_selection
    _apply_language_preferences = PlayerWindow._apply_language_preferences
    # staticmethod() is load-bearing: bound as a plain function it would take
    # `self` as its first argument, raise TypeError, and be swallowed by the
    # very except-clause under test -- which looks exactly like the bug.
    _first_by_language = staticmethod(PlayerWindow._first_by_language)

    def __init__(self, selection):
        self.selection = selection
        self.ui_player = FakePlayer()
        self._audio_tracks = list(AUDIO)
        self._subtitle_tracks = list(SUBS)
        self._audio_order = [t["index"] for t in AUDIO]
        self._subtitle_order = [t["index"] for t in SUBS]
        self.client = object()

    # -- stubbed collaborators -----------------------------------------
    def _playback_prefs(self):
        return PREFS["playback"]

    def _stream_slot(self, order, index, available):
        return order.index(index) if index in order else None

    def _switch_audio(self, slot):
        self.ui_player.setAudioStream(slot)
        return True

    def _select_subtitle(self, index):
        return index in self._subtitle_order

    def _current_stream(self, subtitles=False):
        return (0, False)

    def _log_subtitle_inventory(self, _why):
        pass


def run():
    # 1. THE REGRESSION: a subtitle-only pick must not cost us the audio.
    sel = playoptions.Selection()
    sel.subtitle_index = 3
    win = Fake(sel)
    win.apply_track_selection()
    check("a subtitle-only pick still applies the AUDIO preference",
          win.ui_player.audio_slot == 1,
          "slot %r; 1 == eng, 0 == ger (the bug)" % win.ui_player.audio_slot)

    # 2. The mirror image: an audio-only pick must not cost us the subtitles.
    sel = playoptions.Selection()
    sel.audio_index = 1                       # the viewer chose German by hand
    win = Fake(sel)
    win.apply_track_selection()
    check("an audio-only pick still applies the SUBTITLE preference",
          win.ui_player.subs_shown is True,
          "showSubtitles(%r)" % win.ui_player.subs_shown)
    check("...and does not overrule the audio the viewer chose",
          win.ui_player.audio_slot == 0,
          "slot %r" % win.ui_player.audio_slot)

    # 3. Neither set: preferences drive both, which always worked.
    win = Fake(playoptions.Selection())
    win.apply_track_selection()
    check("no picks at all -> preferences choose the audio",
          win.ui_player.audio_slot == 1,
          "slot %r" % win.ui_player.audio_slot)

    # 4. Both set: the viewer decided everything, preferences stay out.
    sel = playoptions.Selection()
    sel.audio_index, sel.subtitle_index = 1, playoptions.OFF
    win = Fake(sel)
    win.apply_track_selection()
    check("both picked -> audio stays on the viewer's choice",
          win.ui_player.audio_slot == 0, "slot %r" % win.ui_player.audio_slot)
    check("both picked -> subtitles stay OFF as asked",
          win.ui_player.subs_shown is False,
          "showSubtitles(%r)" % win.ui_player.subs_shown)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("track selection: the two halves are independent (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
