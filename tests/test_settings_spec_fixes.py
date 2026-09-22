"""Settings follows 6's rules for languages and Sign Out.

Clearing the primary language clears the secondary behind it, clearing the
secondary promotes nothing, and the Sign Out confirmation opens on Cancel.

Run:  python3 test_settings_spec_fixes.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import cardoptions, playoptions
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Fake:
    _settings_language_clicked = MainWindow._settings_language_clicked

    def __init__(self, current):
        self.current, self.writes = list(current), []

    def _settings_playback(self):
        return {"preferred_subtitle_languages": list(self.current)}

    def _settings_language_facet(self):
        return []

    def _settings_metadata(self):
        return {}

    def _settings_write(self, patch):
        self.writes.append(patch)

    def _settings_fill_audio(self):
        pass


def pick(slot, index, current=("eng", "ger")):
    playoptions.show_choice = lambda **_k: index        # row 0 is "None"
    win = Fake(current)
    win._settings_language_clicked("preferred_subtitle_languages", slot)
    return win.writes[-1]["playback"]["preferred_subtitle_languages"]


def run():
    check("clearing the primary clears the secondary too", pick(0, 0) == [], repr(pick(0, 0)))
    check("clearing the secondary keeps the primary alone", pick(1, 0) == ["eng"],
          repr(pick(1, 0)))
    check("a primary with no secondary clears to nothing", pick(0, 0, ("eng",)) == [])

    seen = {}

    def show(**kwargs):
        seen.update(kwargs)
        return cardoptions.CANCEL
    cardoptions.show = show
    cardoptions.confirm_sign_out()
    check("the Sign Out confirmation opens on Cancel", seen.get("focus") == cardoptions.CANCEL,
          repr(seen.get("focus")))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("Settings follows 6's language and Sign Out rules (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
