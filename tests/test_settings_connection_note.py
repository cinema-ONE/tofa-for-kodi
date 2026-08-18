"""The CONNECTION note reports how THIS box is reaching the server.

Settings > Account has always had the "Direct connections only" toggle, but
nothing told the viewer their CURRENT route -- so a box quietly on tofa's
relay (every byte, video included, through tofa's cloud) read as "everything
is slow" with no cause on screen. The note reads the client's LIVE base_url,
which _request has already swapped to the fallback if the LAN address failed.

Run:  python3 test_settings_connection_note.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import MainWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeClient:
    def __init__(self, base_url):
        self.base_url = base_url


class FakeMain:
    _settings_fill_connection = MainWindow._settings_fill_connection
    def __init__(self):
        self._props = {}
    def setProperty(self, key, value):
        self._props[key] = value
    def getProperty(self, key):
        return self._props.get(key, "")


def body_for(base_url):
    win = FakeMain()
    win._settings_fill_connection(FakeClient(base_url) if base_url is not None else None)
    return win.getProperty("settings_connection_body")


LAN = "http://192.168.0.60:33333"
RELAY_HOST = "https://abc123.connect.tofa.tv"
PROXY = "https://api.tofa.tv/servers/abc-123/relay"

check("a LAN address reads as direct",
      body_for(LAN).lower().startswith("connected directly"), body_for(LAN))
check("the relay host reads as relay",
      "relay" in body_for(RELAY_HOST).lower(), body_for(RELAY_HOST))
check("the cloud PROXY path reads as relay too",
      "relay" in body_for(PROXY).lower(), body_for(PROXY))
check("no client leaves the note empty (never a false 'direct')",
      body_for(None) == "", repr(body_for(None)))
# The relay copy has to earn its two rendered lines without a third: the card
# is sized for two (SETTINGS_ACCOUNT_RELAY_NOTE_H). A crude proxy for "fits":
# it must be materially shorter than three metadata lines at this width.
check("the relay copy stays short enough for a two-line card",
      len(body_for(RELAY_HOST)) <= 130, str(len(body_for(RELAY_HOST))))

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
