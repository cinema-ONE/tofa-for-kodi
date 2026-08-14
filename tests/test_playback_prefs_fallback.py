"""A failed preferences fetch must not silently change which audio plays.

THE BUG, reported from the cinema box 2026-08-12 (Murder, She Wrote S2 E1,
`ger` first / `eng` second, profile set to English-then-German):

    15:49:57  first play   -> Kodi opens the German stream, NO switch ever
    16:02:59  same episode -> opens German, switches to English 0.9s later
    16:19:40  next episode -> opens German, switches to English 0.7s later

Only the FIRST play after the Kodi start was wrong, and the viewer had
touched nothing -- no Options panel, no manual track pick. What makes the
first play special is that `_playback_prefs()` called `whoami()` live, from
inside onAVStarted, with no cache anywhere. One failed request there returned
`{}`, `_apply_language_preferences()` took its `if not playback_prefs: return`
and the audio was never switched at all -- so the file's FIRST track played,
which on this file is German.

`{}` does not mean "no preference". It means "we did not find out", and the
two must not be treated the same. The only record was a log.debug on a box
with debug logging off, which is why nothing appeared in the log either time.

Run:  python3 test_playback_prefs_fallback.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, playbackprefs
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


PLAYBACK = {"preferred_audio_languages": ["eng", "deu"],
            "preferred_subtitle_languages": ["eng", "deu"],
            "always_enable_subtitles": True}


class OkClient:
    def whoami(self):
        return {"preferences": {"playback": PLAYBACK}}


class DeadClient:
    """The cinema box's first play: the request simply did not come back."""

    def whoami(self):
        raise http.ApiError(0, "connection_error", "the request did not come back")


class Fake:
    _playback_prefs = PlayerWindow._playback_prefs

    def __init__(self, client):
        self.client = client


def run():
    remembered = {}
    playbackprefs.remember = lambda pb: remembered.update({"pb": pb} if pb else {})
    playbackprefs.last_known = lambda: remembered.get("pb") or {}

    # 1. A good read answers, and is remembered for later.
    got = Fake(OkClient())._playback_prefs()
    check("a successful read returns the preferences", got == PLAYBACK, repr(got))
    check("...and remembers them", remembered.get("pb") == PLAYBACK,
          repr(remembered))

    # 2. THE REGRESSION: the request fails, but we still know the languages.
    got = Fake(DeadClient())._playback_prefs()
    check("a FAILED read falls back to the remembered copy",
          got == PLAYBACK,
          "%r -- empty here is the bug: the audio never gets switched and "
          "the file's first track plays" % (got,))

    # 3. No client at all takes the same path rather than returning {}.
    got = Fake(None)._playback_prefs()
    check("no client also falls back", got == PLAYBACK, repr(got))

    # 4. Nothing remembered yet is the one case that must still be empty --
    #    honestly empty, so the caller skips rather than inventing a language.
    remembered.clear()
    got = Fake(DeadClient())._playback_prefs()
    check("a failure with nothing remembered is empty, not invented",
          got == {}, repr(got))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("playback prefs: a failed fetch no longer decides the audio "
          "(%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
