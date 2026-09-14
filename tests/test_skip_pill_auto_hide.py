"""8.5's pill hides after the server's auto-hide, and the chrome brings it back.

Reported watching a long intro: "Skip Intro" stayed on screen for the whole
of it. The pill takes focus itself when it appears from the bare surface, and
the auto-hide was held off while the pill had focus -- so it never ran out.

The web and macOS players hide it after `prompt_auto_hide_secs` and raise it
again with their controls. This suite pins that: the countdown, the rest, the
return with the chrome, the hold while the chrome is up, and that declining
(back) or leaving the segment still behave as before.

Run:  python3 test_skip_pill_auto_hide.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


CHROME_FOCUS = 12345   # any control in the transport row


class FakePlayer:
    """The state _tick_skip and _hide_skip read, with the REAL methods bound.

    Everything the pill does on screen is a window property, so the fake keeps
    them in a dict and the checks read `player_skip` exactly as the skin does."""

    SURFACE_ID = PlayerWindow.SURFACE_ID
    SKIP_BUTTON_ID = PlayerWindow.SKIP_BUTTON_ID
    _SKIP_LABELS = PlayerWindow._SKIP_LABELS
    _tick_skip = PlayerWindow._tick_skip
    _hide_skip = PlayerWindow._hide_skip
    _policy = PlayerWindow._policy
    _skip_deadline = PlayerWindow._skip_deadline

    def __init__(self, segments):
        self._segments = list(segments)
        self._skip_policy = {"prompt_auto_hide_secs": 8,
                             "skip_min_remaining_secs": 1}
        self._skip_active = None
        self._skip_hide_at = 0.0
        self._skip_resting = None
        self._skip_done = set()
        self._next_up_open = False
        self.props = {}
        self.focus = self.SURFACE_ID
        self.deferred = []

    def getProperty(self, key):
        return self.props.get(key, "")

    def setProperty(self, key, value):
        self.props[key] = value

    def getFocusId(self):
        return self.focus

    def setFocusId(self, cid):
        self.focus = cid

    def _segment_action(self, _kind):
        return "ask"

    def rail_owns_outro(self):
        return False

    def _size_skip_pill(self, _label):
        pass

    def _auto_skip(self, _segment):
        raise AssertionError("ask must never auto-skip")

    def _defer_focus_restore(self, cid):
        self.deferred.append(cid)
        self.focus = self.SURFACE_ID

    # -- test helpers --
    def tick(self, now, position_ms):
        self._tick_skip(now, position_ms)
        return self.props.get("player_skip") == "1"

    def chrome(self, up):
        self.props["player_chrome"] = "1" if up else ""
        self.focus = CHROME_FOCUS if up else self.SURFACE_ID


INTRO = ("intro", 60_000, 180_000)   # a two-minute intro


def at(t):
    """Playback position for wall time t, starting 59s into the file."""
    return 59_000 + int(t * 1000)


# ---- the reported case ---------------------------------------------------
p = FakePlayer([INTRO])
check("no pill before the segment", not p.tick(0.0, at(0.0)))
check("pill raised at the segment's start", p.tick(1.0, at(1.0)))
check("...and it takes focus from the bare surface", p.focus == p.SKIP_BUTTON_ID)
check("still up just inside the auto-hide", p.tick(8.8, at(8.8)))
check("GONE after the auto-hide, although it has focus",
      not p.tick(9.2, at(9.2)), str(p.props))
check("focus handed back through the deferred restore",
      p.deferred == [p.SKIP_BUTTON_ID], str(p.deferred))
check("stays hidden while the chrome is down",
      not p.tick(30.0, at(30.0)) and not p.tick(60.0, at(60.0)))

# ---- the chrome brings it back, and holds it -----------------------------
p.chrome(True)
check("raising the chrome raises the pill again", p.tick(61.0, at(61.0)))
check("...without taking focus off the chrome", p.focus == CHROME_FOCUS)
check("held for as long as the chrome is up, well past 8s",
      p.tick(75.0, at(75.0)) and p.tick(90.0, at(90.0)))
p.chrome(False)
check("chrome gone: still up at first", p.tick(91.0, at(91.0)))
check("...and hidden again once the countdown runs out",
      not p.tick(98.5, at(98.5)))
check("comes back a second time with the chrome",
      (p.chrome(True), p.tick(100.0, at(100.0)))[1])

# ---- the segment's end and a rewind --------------------------------------
check("hidden when the segment ends", not p.tick(122.0, at(122.0)))
p.chrome(False)
check("a rewind to before the start offers it afresh",
      not p.tick(130.0, 50_000) and p.tick(131.0, 60_500))

# ---- declining is still final --------------------------------------------
p = FakePlayer([INTRO])
p.tick(1.0, at(1.0))
p._hide_skip(used=True)             # back on the pill
p.chrome(True)
check("back declines the segment: the chrome does not bring it back",
      not p.tick(20.0, at(20.0)))

p = FakePlayer([INTRO])
p.tick(1.0, at(1.0))
p.tick(10.0, at(10.0))              # timed out, resting
p._hide_skip(used=True)             # e.g. the Next Up rail took over
p.chrome(True)
check("a resting pill declined by a used hide stays gone",
      not p.tick(20.0, at(20.0)))

# ---- an operator who turned the auto-hide off ----------------------------
p = FakePlayer([INTRO])
p._skip_policy["prompt_auto_hide_secs"] = 0
p.tick(1.0, at(1.0))
check("auto-hide 0 means the pill stays for the whole segment",
      p.tick(100.0, at(100.0)))

print("\n" + "=" * 60)
FAILED = sum(1 for _, ok in RESULTS if not ok)
if FAILED:
    print(f"{FAILED} of {len(RESULTS)} checks FAILED")
    raise SystemExit(1)
print(f"the skip pill auto-hides and returns with the chrome ({len(RESULTS)} checks)")
