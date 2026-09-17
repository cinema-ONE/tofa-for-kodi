"""Settings > Appearance > Media cards writes layout.spoilerBlurEpisodes.

Until now the add-on READ that key (Detail's episode grid hides the stills of
episodes past the one you are on) and offered no way to change it. Android TV
read it without a switch too, so on a Kodi-only household the value was
whatever some old build last wrote -- and tofa confirmed on vault #159 that
this key IS cross-client, unlike the rest of `layout.*`.

Two things this pins, both of which would be invisible on screen:

  * The value is written as the STRING "true"/"false". The dotted keys are
    strings in the blob (project_preferences_blob_types), and `prefs.as_bool`
    exists precisely because `'false'` is truthy. Writing a real bool here
    would leave this account's value a different type from every other
    client's, and the next client to read it with the same care would get it
    right by accident rather than by contract.
  * An ABSENT key means ON, matching the reader in detail.py -- so the first
    press on a profile that has never held the key must write "false", not
    "true".

Run:  python3 test_settings_spoiler_toggle.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import prefs
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


KEY = "layout.spoilerBlurEpisodes"


class Fake:
    _settings_spoilers_clicked = MainWindow._settings_spoilers_clicked

    def __init__(self, stored):
        self._prefs = {} if stored is None else {KEY: stored}
        self.written = None

    def _ensure_preferences(self):
        return self._prefs

    def _settings_write(self, patch):
        self.written = patch


def press(stored):
    f = Fake(stored)
    f._settings_spoilers_clicked()
    return f.written


# ---- the reader's default, which the writer has to agree with ------------
check("an absent key reads as ON (the reader's default)",
      prefs.as_bool({}, KEY, True) is True)
check("the string 'false' reads as OFF, where a bare .get would not",
      prefs.as_bool({KEY: "false"}, KEY, True) is False
      and bool("false") is True)

# ---- what a press writes -------------------------------------------------
check("never set: first press turns it OFF",
      press(None) == {KEY: "false"}, repr(press(None)))
check("stored 'false': press turns it ON",
      press("false") == {KEY: "true"}, repr(press("false")))
check("stored 'true': press turns it OFF",
      press("true") == {KEY: "false"}, repr(press("true")))

# ---- the type, which is the part that cannot be seen on screen -----------
written = press("false")[KEY]
check("the value is a STRING, like every other dotted key",
      isinstance(written, str), f"{written!r} is {type(written).__name__}")

# ---- one key per write: the server shallow-merges everything but playback
check("the patch carries that key alone", list(press("true")) == [KEY])

print("\n" + "=" * 60)
FAILED = sum(1 for _, ok in RESULTS if not ok)
if FAILED:
    print(f"{FAILED} of {len(RESULTS)} checks FAILED")
    raise SystemExit(1)
print(f"the spoiler toggle writes what the other clients read ({len(RESULTS)} checks)")
