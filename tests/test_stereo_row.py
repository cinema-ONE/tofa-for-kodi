"""The Adjust panel's 3D row: a stepper through the modes this box can output.

It exists for one case -- the viewer answered the start-of-playback question
wrong and wants to change it. That is why it steps rather than picks: each
press applies live, so the screen is the feedback. A picker would make them
commit blind.

Run:  python3 test_stereo_row.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import stereoscopic
from resources.lib.windows.player import PlayerWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


MODES = [{"label": "Disabled", "mode": "off"},
         {"label": "Over / Under", "mode": "split_horizontal"},
         {"label": "Side by side", "mode": "split_vertical"},
         {"label": "Hardware based", "mode": "hardware_based"}]

state = {"mode": "off"}
stereoscopic.modes = lambda: MODES
stereoscopic.current_mode = lambda: next(
    (m for m in MODES if m["mode"] == state["mode"]), None)
def _set(mode):
    state["mode"] = mode
    return True
stereoscopic.set_mode = _set


class Fake:
    _cycle_stereo_mode = PlayerWindow._cycle_stereo_mode
    _stereo_mode_label = PlayerWindow._stereo_mode_label


win = Fake()
check("reads the mode it is on", win._stereo_mode_label() == "Disabled",
      win._stereo_mode_label())

win._cycle_stereo_mode(MODES, True)
check("forward steps to the next mode", state["mode"] == "split_horizontal", state["mode"])
check("...and the label follows", win._stereo_mode_label() == "Over / Under",
      win._stereo_mode_label())

win._cycle_stereo_mode(MODES, False)
check("back steps to the previous", state["mode"] == "off", state["mode"])

# Wrapping: a list you are cycling through to COMPARE has no natural end,
# unlike every navigable list in this app (project_wrap_stop_mechanism).
win._cycle_stereo_mode(MODES, False)
check("stepping back from the first wraps to the last",
      state["mode"] == "hardware_based", state["mode"])
win._cycle_stereo_mode(MODES, True)
check("and forward from the last wraps to the first", state["mode"] == "off",
      state["mode"])

# A mode Kodi reports that is not in the list must not crash the step.
state["mode"] = "anaglyph_cyan_red"
win._cycle_stereo_mode(MODES, True)
check("an unknown current mode falls back to the first",
      state["mode"] == "split_horizontal", state["mode"])

# Nothing to offer: no hardware modes at all.
state["mode"] = "off"
win._cycle_stereo_mode([], True)
check("an empty mode list is a no-op", state["mode"] == "off", state["mode"])

# The label when Kodi will not answer.
stereoscopic.current_mode = lambda: None
check("no answer shows an em dash", win._stereo_mode_label() == "—",
      win._stereo_mode_label())

failed = [n for n, ok in RESULTS if not ok]

# --- the self-raised panel must not strand focus -------------------------
# 2026-08-10: BACK/SELECT/ESC closed our 3D prompt and then nothing could be
# focused. close_panel re-raises the chrome and hands focus to the recorded
# opener -- and a panel nobody opened had recorded the bare SURFACE, which
# has no navigation targets.
import types
from resources.lib.windows.player import PlayerWindow

class FakePlayer(object):
    SURFACE_ID = PlayerWindow.SURFACE_ID
    PLAYPAUSE_ID = PlayerWindow.PLAYPAUSE_ID
    PANEL_LIST_ID = PlayerWindow.PANEL_LIST_ID
    def __init__(self, focused):
        self._focused = focused
        self._panel_opener = None
        self._chrome_deadline = 1.0
        self._props = {"player_panel": "1"}
        self._panel_apply = self._panel_steppers = None
        self._modal = True
    def getFocusId(self): return self._focused
    def setFocusId(self, cid): self._focused = cid
    def getProperty(self, k): return self._props.get(k, "")
    def setProperty(self, k, v): self._props[k] = v
    def anchor_chrome(self): self._chrome_deadline = 2.0

def opener_for(focused):
    p = FakePlayer(focused)
    # the one line of _open_panel under test
    o = p.getFocusId()
    p._panel_opener = o if o != p.SURFACE_ID else 0
    return p._panel_opener

check("a panel opened FROM a capsule remembers it",
      opener_for(PlayerWindow.AUDIO_ID) == PlayerWindow.AUDIO_ID)
check("a SELF-raised panel records no opener",
      opener_for(PlayerWindow.SURFACE_ID) == 0)

def close(opener):
    p = FakePlayer(PlayerWindow.PANEL_LIST_ID)
    p._panel_opener = opener
    PlayerWindow.close_panel(p)
    return p._focused

check("closing hands focus back to the capsule",
      close(PlayerWindow.AUDIO_ID) == PlayerWindow.AUDIO_ID)
check("closing with no opener lands on play/pause, never the surface",
      close(0) == PlayerWindow.PLAYPAUSE_ID)
check("even a SURFACE opener is refused while the chrome is up",
      close(PlayerWindow.SURFACE_ID) == PlayerWindow.PLAYPAUSE_ID)


# --- ...and it must not have focus taken away the moment it opens --------
# 2026-08-11, AM6B+ (Kodi 21.3, 4.9 kernel), Hugo: the panel came up with no
# row highlighted and the d-pad still on the chrome. Two ways that happens,
# both timing-dependent and both invisible on a fast machine:
#   1. reveal_chrome() lands AFTER the panel opened and, being the first
#      reveal of the playback, drags focus to play/pause.
#   2. Kodi drops the SETFOCUS outright, because the panel's group is gated
#      on a window property set microseconds earlier and the group is not
#      visible -- hence not focusable -- until the next render pass.
# The panel is only ever reachable by a programmatic focus (all its nav
# targets are NAV_STOP), so either one strands the viewer completely.
import time as _time
from resources.lib.windows import player as _player

class RevealFake(object):
    PLAYPAUSE_ID = PlayerWindow.PLAYPAUSE_ID
    PANEL_LIST_ID = PlayerWindow.PANEL_LIST_ID
    reveal_chrome = PlayerWindow.reveal_chrome
    _hold_panel_focus = PlayerWindow._hold_panel_focus
    def __init__(self, modal, focused, chrome_deadline=0.0):
        self._modal = modal
        self._focused = focused
        self._chrome_deadline = chrome_deadline
        self._pause_card_deadline = 0.0
        self._panel_focus_deadline = 0.0
        self._props = {}
    def getFocusId(self): return self._focused
    def setFocusId(self, cid): self._focused = cid
    def getProperty(self, k): return self._props.get(k, "")
    def setProperty(self, k, v): self._props[k] = v

# (1) the reveal that stole focus
p = RevealFake(modal=True, focused=PlayerWindow.PANEL_LIST_ID)
p.reveal_chrome()
check("revealing the chrome under an open panel leaves focus on the panel",
      p._focused == PlayerWindow.PANEL_LIST_ID, str(p._focused))
check("...and still reveals the chrome", p.getProperty("player_chrome") == "1")

# The ordinary reveal must be untouched -- this is the path every playback
# takes, and landing on play/pause is 10.4's documented behaviour.
p = RevealFake(modal=False, focused=PlayerWindow.SURFACE_ID)
p.reveal_chrome()
check("a reveal with no panel still lands on play/pause",
      p._focused == PlayerWindow.PLAYPAUSE_ID, str(p._focused))

# (2) the focus Kodi dropped on the floor
p = RevealFake(modal=True, focused=PlayerWindow.PLAYPAUSE_ID)
p._props["player_panel"] = "1"
p._panel_focus_deadline = _time.monotonic() + _player.PANEL_FOCUS_GRACE_S
p._hold_panel_focus(_time.monotonic())
check("the tick puts focus back on a panel that never got it",
      p._focused == PlayerWindow.PANEL_LIST_ID, str(p._focused))

# It is a grace period, not a permanent owner: past the deadline the tick
# stops touching focus, so a real focus bug still shows itself.
p = RevealFake(modal=True, focused=PlayerWindow.PLAYPAUSE_ID)
p._props["player_panel"] = "1"
p._panel_focus_deadline = _time.monotonic() - 0.01
p._hold_panel_focus(_time.monotonic())
check("past the grace period the tick lets focus alone",
      p._focused == PlayerWindow.PLAYPAUSE_ID, str(p._focused))
check("...and disarms itself", p._panel_focus_deadline == 0.0)

# A closed panel disarms it too, so close_panel's hand-back is not undone.
p = RevealFake(modal=False, focused=PlayerWindow.AUDIO_ID)
p._panel_focus_deadline = _time.monotonic() + _player.PANEL_FOCUS_GRACE_S
p._hold_panel_focus(_time.monotonic())
check("a closed panel does not drag focus back",
      p._focused == PlayerWindow.AUDIO_ID, str(p._focused))

# close_panel must clear the deadline itself, or the tick would fight the
# hand-back for the rest of the grace period.
p = FakePlayer(PlayerWindow.PANEL_LIST_ID)
p._panel_opener = PlayerWindow.AUDIO_ID
p._panel_focus_deadline = _time.monotonic() + _player.PANEL_FOCUS_GRACE_S
PlayerWindow.close_panel(p)
check("closing the panel disarms the focus hold",
      p._panel_focus_deadline == 0.0)


# --- the restore marker must outlive KODI, not just the add-on -----------
# A window property dies with the process, so it covered our add-on crashing
# and nothing else -- and Kodi going down IS the case where nobody is left to
# restore. Measured 2026-08-10 after a restart mid-playback: Kodi still on
# Preferred with no marker left to notice it.
import resources.lib.stereoscopic as st

st._clear_saved()
check("nothing saved reads as nothing", st._read_saved() is None)
check("was_suppressed is false with no marker", st.was_suppressed() is False)
st._write_saved(st.ASK)
check("the parked value comes back", st._read_saved() == st.ASK)
check("was_suppressed sees the marker", st.was_suppressed() is True)
# Zero is a REAL value here ("Ask me"), so the marker must not be tested for
# truthiness anywhere -- that bug would silently strand the one setting we
# ever park.
check("ASK is 0, and 0 must not read as absent", st.ASK == 0
      and st._read_saved() is not None)
st._clear_saved()
check("clearing really clears", st._read_saved() is None)
# A corrupt marker clears itself rather than being retried every launch.
handle = __import__("xbmcvfs").File(st._saved_path(), "w")
handle.write("not a number"); handle.close()
check("a corrupt marker is discarded", st._read_saved() is None)
check("...and does not linger", st._read_saved() is None)

print("\n" + "=" * 60)
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
