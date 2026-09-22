"""8.7's failure card: titled "Playback stopped", Try again only where it can help.

The body carries the reason; the title stays the same for every failure. A
retry is offered only for a refusal that can clear on its own -- a busy
converter (`transcode_at_capacity`) or a network that did not answer. A
realtime refusal, a gone session or a missing file never offer one. While
the card is up it owns every key: arrows move between its buttons and must
not seek behind it.

Run:  python3 test_playback_stopped_card.py
"""
import os
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, playback
from resources.lib.windows import player as player_mod, playoptions
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class Card:
    """Absorbs what fail() touches beyond the property store."""
    ERROR_CLOSE_ID = PlayerWindow.ERROR_CLOSE_ID
    ERROR_RETRY_ID = PlayerWindow.ERROR_RETRY_ID
    SURFACE_ID = PlayerWindow.SURFACE_ID
    STATE_OPENING = PlayerWindow.STATE_OPENING
    fail = PlayerWindow.fail
    _retry_playback = PlayerWindow._retry_playback

    def __init__(self):
        self.props, self.focus, self.ui_player, self.started = {}, None, None, 0

    def getProperty(self, k): return self.props.get(k, "")
    def setProperty(self, k, v): self.props[k] = v
    def setFocusId(self, cid): self.focus = cid
    def _start_playback(self): self.started += 1

    def __getattr__(self, name):                 # close_panel, hide_chrome, ...
        return lambda *a, **k: None


# --- the card ---------------------------------------------------------------
c = Card()
c.fail("The server couldn't start this file.")
check("the title is Playback stopped (#31131)",
      c.props.get("player_error_title") == "<string 31131>", c.props.get("player_error_title"))
check("the reason is the body line", c.props.get("player_error_body") == "The server couldn't start this file.")
check("no retry unless asked", c.props.get("player_error_retry") == "")
check("focus lands on Close", c.focus == PlayerWindow.ERROR_CLOSE_ID, repr(c.focus))

c = Card()
c.fail("busy", retry=True)
check("a retryable failure shows Try again", c.props.get("player_error_retry") == "1")
check("...labelled from #31132", c.props.get("player_error_retry_label") == "<string 31132>")
check("...and takes focus first", c.focus == PlayerWindow.ERROR_RETRY_ID, repr(c.focus))

c._retry_playback()
check("Try again takes the card down",
      all(c.props.get(k) == "" for k in ("player_error", "player_error_retry",
                                          "player_error_title", "player_error_body")))
check("...shows the opening card", c.props.get("player_state") == PlayerWindow.STATE_OPENING)
check("...and asks again", c.started == 1)
c.fail("again", retry=True)
check("a second failure raises the card again", c.props.get("player_error") == "1")

# --- which failures retry ---------------------------------------------------
player_mod.stereoscopic.suppress_ask = lambda: None
player_mod.stereoscopic.was_suppressed = lambda: False
raised = {}


def negotiate(client, file_id, profile, **kw):
    raise raised["exc"]


player_mod.playback.negotiate = negotiate


class Offset:
    def load(self, file_id):
        pass


class Starter:
    _start_playback = PlayerWindow._start_playback

    def __init__(self):
        self.file_id, self.media_id = "f1", "m1"
        self._file_subtitle_tracks = []
        self.selection = playoptions.Selection()
        self.resume_ms = None
        self._subtitle_offset = Offset()
        self.failed = None

    def _get_client(self):
        return object()

    def fail(self, body, *, title="", retry=False):
        self.failed = (body, retry)


for exc, want, what in (
        (playback.NegotiateTimeout("slow"), True, "a timed-out negotiation"),
        (http.ApiError(503, "transcode_at_capacity", "This server is busy."), True,
         "a busy converter"),
        (http.ApiError(0, "connection_error", "refused"), True, "an unreachable server"),
        (http.ApiError(422, "transcode_realtime_unsupported", "Too slow."), False,
         "a realtime refusal"),
        (http.ApiError(410, "session_gone", "Gone."), False, "a gone session"),
        (http.ApiError(404, "not_found", "Missing."), False, "a missing file"),
        (http.ApiError(500, "internal", "Oops."), False, "any other error")):
    s = Starter()
    raised["exc"] = exc
    s._start_playback()
    got = s.failed and s.failed[1]
    check("%s %s Try again" % (what, "offers" if want else "does not offer"),
          got is want, repr(s.failed))

# --- the card owns the keys ------------------------------------------------
class Action:
    def __init__(self, aid): self.aid = aid
    def getId(self): return self.aid


class Keys:
    onAction = PlayerWindow.onAction
    # Kodi's ids for previous-menu, back and stop; the stubs carry none.
    _BACK_ACTIONS = (10, 92)
    _STOP_ACTIONS = (13,)

    def __init__(self):
        self.props = {"player_error": "1"}
        self._chrome_deadline = 0.0
        self.calls = []

    def getProperty(self, k): return self.props.get(k, "")
    def _exit(self): self.calls.append("exit")

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


base = []
real_base = player_mod.kodigui.ControlledDialog.onAction
player_mod.kodigui.ControlledDialog.onAction = lambda self, action: base.append(action.getId())
try:
    # Kodi's own ids: 1 left, 2 right, 7 select (the stubs carry no constants).
    for aid, name in ((2, "right"), (1, "left"), (7, "select")):
        k = Keys()
        k.onAction(Action(aid))
        check("%s on the card goes to its buttons, not a seek" % name,
              k.calls == [] and base[-1] == aid, repr((k.calls, base[-1:])))
    k = Keys()
    k.onAction(Action(92))
    check("Back on the card leaves", k.calls == ["exit"], repr(k.calls))
finally:
    player_mod.kodigui.ControlledDialog.onAction = real_base

# --- the skin ---------------------------------------------------------------
xml = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin.video.tofa",
                        "resources", "skins", "Main", "1080i", "script-tofa-player.xml"),
           encoding="utf-8").read()
retry_btn = re.search(r'<control type="button" id="9952">(.*?)</control>', xml, re.S)
close_btn = re.search(r'<control type="button" id="9951">(.*?)</control>', xml, re.S)
check("Try again is a button that moves right to Close",
      bool(retry_btn) and "<onright>9951</onright>" in retry_btn.group(1))
check("Close moves left to Try again",
      bool(close_btn) and "<onleft>9952</onleft>" in close_btn.group(1))
check("Close slides into the pair's right-hand slot when Try again shows",
      'end="112,0"' in xml and "Window.Property(player_error_retry)" in xml)


def run() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("8.7's card: one title, Try again only where it helps (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
