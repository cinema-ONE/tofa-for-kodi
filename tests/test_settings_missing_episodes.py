"""Settings > Appearance > Missing episodes (app 2.1.0) writes what show pages read.

Run:  python3 test_settings_missing_episodes.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import episodes, settings_info
from resources.lib.skin import screens
from resources.lib.windows import main

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


W = main.MainWindow
check("the app's three choices, in its order",
      [label for _k, label in W.MISSING_EPISODES_CHOICES]
      == ["Automatic", "Always show", "Never show"])
check("each value is one show pages understand",
      {k for k, _l in W.MISSING_EPISODES_CHOICES} == {"auto", "show", "hide"})
check("Always show and Never show decide outright",
      episodes.show_missing({episodes.MISSING_EPISODES_KEY: "show"},
                            {"show_missing_episodes": False})
      and not episodes.show_missing({episodes.MISSING_EPISODES_KEY: "hide"},
                                    {"show_missing_episodes": True}))


class Fake:
    MISSING_EPISODES_CHOICES = W.MISSING_EPISODES_CHOICES

    def __init__(self, prefs):
        self.prefs = prefs

    def _ensure_preferences(self):
        return self.prefs

for prefs, want in (({}, "auto"), ({"layout.missingEpisodes": "hide"}, "hide"),
                    ({"layout.missingEpisodes": "nonsense"}, "auto")):
    got = W._settings_missing_value(Fake(prefs))
    check(f"{prefs or 'no preference'} reads as {want}", got == want, got)

check("the left column has the app's sentence",
      "daily shows like talk shows and soaps" in settings_info.ROWS["missing_episodes"].body)
check("the row is in the Appearance page, after the media cards",
      W.SETTINGS_INFO_KEYS[W.SETTINGS_MISSING_ID] == "missing_episodes")
xml = screens.render_main()
check("the skin has the row", 'id="8366"' in xml)
check("under an EPISODES eyebrow, above MOTION",
      0 < xml.find("EPISODES</label>") < xml.find('id="8366"') < xml.find("MOTION</label>"))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
