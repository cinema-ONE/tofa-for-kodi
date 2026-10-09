"""An unreachable server at launch is logged and told, not left blank.

MainWindow._get_client swallowed the ApiError, so every section came up
empty with nothing in the log. It now logs each failure and toasts once.

Run:  python3 test_no_client_notice.py
"""
import re
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from kodi_stubs import NOTIFICATIONS, PLUGIN, PROPERTY_WRITES
import xbmc

from resources.lib import auth, household, http, toast
from resources.lib import profiles as profiles_api
from resources.lib.windows import main, profile_select
from resources.lib.windows.main import MainWindow

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


# The real wording, so the test also pins what the viewer reads.
PO = (PLUGIN / "resources/language/resource.language.en_gb/strings.po").read_text()
STRINGS = {int(i): s for i, s in re.findall(r'msgctxt "#(\d+)"\nmsgid "(.*)"', PO)}
profile_select._ = STRINGS.get
UNREACHABLE = STRINGS[31051]

LOGS = []
xbmc.log = lambda msg, level=0: LOGS.append((level, msg))

RELAY = "https://api.example/servers/srv-1/relay"
TOK = auth.Tokens(server=RELAY, server_id="srv-1", connect_url="https://cloud",
                  access_token="a", refresh_token="r", token_type="Bearer",
                  expires_in=3600, obtained_at=time.time(), device_id="dev",
                  profile_id="p1")
RELAY_DOWN = http.ApiError(503, "server_relay_not_connected", "")
CLIENT = object()

main.prefetch.client = lambda: None
main.http.new_session = lambda: None
main.auth.ensure_fresh = lambda session: TOK
main.api.client_for = lambda session, tok: CLIENT
GATE = {"answer": TOK}


def fake_gate(session, tok):
    if isinstance(GATE["answer"], Exception):
        raise GATE["answer"]
    return GATE["answer"]


main.profile_select.ensure_profile_selected = fake_gate


class FakeWindow:
    _get_client = MainWindow._get_client
    _report_no_client = MainWindow._report_no_client

    def __init__(self):
        self.client = None
        self._no_client_told = False

    def _household_start(self):
        pass


def toasts():
    return [v for k, v in PROPERTY_WRITES if k == toast.PROPERTY and v]


def warnings():
    return [m for level, m in LOGS if level == xbmc.LOGWARNING]


def reset(answer):
    GATE["answer"] = answer
    LOGS.clear()
    PROPERTY_WRITES.clear()
    NOTIFICATIONS.clear()


# -- the server is offline: logged every time, told once ---------------------
reset(RELAY_DOWN)
w = FakeWindow()
check("no client while the relay says the server is gone", w._get_client(), None)
check("the failure is logged with its address and code",
      [m for m in warnings() if RELAY in m and "server_relay_not_connected" in m] != [], True)
check("the viewer is told the server could not be reached", toasts(), [UNREACHABLE])
w._get_client()
w._get_client()
check("each section's failure is logged", len(warnings()), 3)
check("but the toast is said once per window", toasts(), [UNREACHABLE])

reset(RELAY_DOWN)
FakeWindow()._get_client()
check("a new window tells it again", toasts(), [UNREACHABLE])

# -- a failed token refresh has no address yet ------------------------------
reset(RELAY_DOWN)
main.auth.ensure_fresh = lambda session: (_ for _ in ()).throw(RELAY_DOWN)
FakeWindow()._get_client()
check("a refresh failure is logged too",
      [m for m in warnings() if "the token refresh" in m] != [], True)
main.auth.ensure_fresh = lambda session: TOK

# -- not failures: nothing logged, nothing shown -----------------------------
reset(profile_select.ProfileCanceled())
FakeWindow()._get_client()
check("a cancelled picker is not reported", (warnings(), toasts()), ([], []))

reset(TOK)
main.api.client_for = lambda session, tok: (_ for _ in ()).throw(household.ViewerEnded("ended"))
w = FakeWindow()
w._get_client()
check("an ended member session is logged", len(warnings()), 1)
check("but left to household viewing's own toast", toasts(), [])
check("so a later outage is still told", w._no_client_told, False)
main.api.client_for = lambda session, tok: CLIENT

reset(TOK)
w = FakeWindow()
check("a reachable server still gives a client", w._get_client(), CLIENT)
check("and says nothing", (warnings(), toasts()), ([], []))

# -- the wording, shared with Switch Profile --------------------------------
fm = profile_select.failure_message
check("no connection reads as unreachable",
      fm(http.ApiError(0, "connection_error", "HTTPConnectionPool(...)")), UNREACHABLE)
check("a gateway timeout reads as unreachable", fm(http.ApiError(504, "unknown_error", "<html>")),
      UNREACHABLE)
check("the server's own message is still quoted",
      fm(http.ApiError(403, "forbidden", "Profile is locked")),
      STRINGS[31050] % "Profile is locked")
check("a busy server answered, so it is quoted too",
      fm(http.ApiError(503, "not_ready", "Server is starting")),
      STRINGS[31050] % "Server is starting")

reset(None)
profile_select.auth.ensure_fresh = lambda session: TOK


def relay_down(*a, **k):
    raise RELAY_DOWN


profiles_api.list_profiles = relay_down
profile_select.switch_profile()
check("Switch Profile words the relay-down case the same way",
      [m for _h, m, _i in NOTIFICATIONS], [UNREACHABLE])

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
