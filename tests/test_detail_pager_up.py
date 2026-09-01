"""One Up press leaves page 2, and moving up INSIDE page 2 does not.

Detail is one screen in two halves. Down off an action pill slides page 2
in; Up off the tab bar slides it away again. Kodi's own focus engine cannot
serve either direction -- it silently refuses to move focus onto a control
the pager has parked off-screen -- so detail.py drives both with
setFocusId() from onAction.

That leaves onAction unable to tell two situations apart, because
getFocusId() reflects focus AFTER Kodi's native attempt:

  * the cursor was in the cast grid and Up carried it to the tab bar,
    which is a move that WORKED and should be left alone; and
  * the cursor was already on the tab bar and Up did nothing, which is the
    viewer asking to go back up to the hero.

Both read as "focus is a tab". _tab_just_arrived is the tie-breaker, armed
in onFocus. It used to be armed on ANY arrival at a tab from a non-tab
control -- which includes the Down press that entered page 2 in the first
place. So the first Up after entering was swallowed as "you only just got
here" and the hero took TWO presses to reach. Reported from the box
2026-09-01.

The rule these pin: arm it only for an arrival from BELOW, i.e. from a
page-2 body control. An arrival from a page-1 pill was a DOWN press, and
the Up after it is a real one.

Run:  python3 test_detail_pager_up.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs

import xbmcgui

# The stub xbmcgui carries no ACTION_* ids; these are Kodi's own values.
xbmcgui.ACTION_MOVE_UP = 3
xbmcgui.ACTION_MOVE_DOWN = 4
xbmcgui.ACTION_PREVIOUS_MENU = 10
xbmcgui.ACTION_NAV_BACK = 92
xbmcgui.ACTION_CONTEXT_MENU = 117

from resources.lib.windows import kodigui                    # noqa: E402
from resources.lib.windows.detail import DetailWindow        # noqa: E402

# onAction hands anything it does not claim to its base class. Nothing in
# these scenarios wants that, and the real one needs a live Kodi window.
kodigui.ControlledWindow.onAction = lambda self, action: None

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Action:
    def __init__(self, aid): self._id = aid
    def getId(self): return self._id


class Pager:
    """Just enough of DetailWindow to run its REAL onFocus and onAction.

    Kodi's native nav runs BEFORE onAction, so press() models that first and
    then calls the real handler -- which is the only ordering under which
    the flag means anything.
    """

    # Every id and the two membership tuples come from the real class, so a
    # renumbered control cannot leave this passing against stale ids.
    for _name in ("PILL_PRIMARY", "PILL_RETRY", "PILL_CANCEL_REQUEST",
                  "PILL_WATCHLIST", "TAB_CAST", "TAB_ABOUT", "TAB_MORE",
                  "TAB_EPISODES", "TAB_BY_NAME", "TAB_IDS", "PAGE2_BODY_IDS",
                  "CAST_LIST", "EPISODE_GRID_PANEL", "SEASON_SIDEBAR_LIST",
                  "CREW_LIST", "SIMILAR_LIST", "DISCOVER_LIST",
                  "PILL_REWATCH", "PILL_OPTIONS", "PILL_VERSION"):
        locals()[_name] = getattr(DetailWindow, _name)
    del _name

    onFocus = DetailWindow.onFocus
    onAction = DetailWindow.onAction
    _page1_focus_id = DetailWindow._page1_focus_id
    _primary_is_actionable = lambda self: True

    def __init__(self, focus):
        self.props = {"detailpage": "page1", "detail_tab": "cast"}
        self._prev_focus_id = 0
        self._tab_just_arrived = False
        self._focus = 0
        self.setFocusId(focus)

    # -- the window surface the two handlers touch ----------------------
    def getProperty(self, key): return self.props.get(key, "")
    def setProperty(self, key, value): self.props[key] = value
    def getFocusId(self): return self._focus
    def setFocusId(self, control_id):
        self._focus = control_id
        self.onFocus(control_id)
    def _sync_episode_synopsis(self): pass
    def _open_card_options(self, _cid): return False
    def _open_season_options(self): return False
    def _open_hero_options(self): return False

    # -- the keypress ---------------------------------------------------
    def press(self, aid, native_lands_on=None):
        """One d-pad press. `native_lands_on` is where Kodi's own focus
        engine put the cursor before onAction saw it: a control id when the
        move succeeded, None when it silently failed (the pager case)."""
        if native_lands_on is not None:
            self.setFocusId(native_lands_on)
        self.onAction(Action(aid))

    @property
    def page(self): return self.props["detailpage"]


UP, DOWN = xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN

# --- the reported bug ---------------------------------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)                       # native cannot reach an off-screen tab
check("Down off the primary pill enters page 2", w.page == "page2")
check("...landing on the remembered tab", w._focus == DetailWindow.TAB_CAST)

w.press(UP)                         # native cannot reach an off-screen pill
check("ONE Up press comes back to page 1", w.page == "page1",
      "this took two presses: entering page 2 armed _tab_just_arrived")
check("...landing on the primary pill", w._focus == DetailWindow.PILL_PRIMARY)

# --- and again, so it is not a one-shot ---------------------------------
w.press(DOWN)
w.press(UP)
check("Down/Up is repeatable, still one press each way", w.page == "page1")

# --- what the flag is actually FOR --------------------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)                       # -> tab bar, page 2
w.press(DOWN, native_lands_on=DetailWindow.CAST_LIST)
check("Down again drops into the cast grid", w._focus == DetailWindow.CAST_LIST)
check("...and page 2 stays up", w.page == "page2")

w.press(UP, native_lands_on=DetailWindow.TAB_CAST)
check("Up out of the cast grid stops at the tab bar",
      w.page == "page2" and w._focus == DetailWindow.TAB_CAST,
      "native nav already served this press; page 1 would overshoot")

w.press(UP)
check("a SECOND Up, still on the tab bar, does leave for page 1",
      w.page == "page1")

# --- the same, through the TV route: the episode grid --------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.props["detail_tab"] = "episodes"
w.press(DOWN)
check("a show lands on the Episodes tab", w._focus == DetailWindow.TAB_EPISODES)
w.press(UP)
check("...and one Up leaves it", w.page == "page1")

w.press(DOWN)
w.press(DOWN, native_lands_on=DetailWindow.EPISODE_GRID_PANEL)
w.press(UP, native_lands_on=DetailWindow.TAB_EPISODES)
check("Up out of the episode grid stops at the tab bar", w.page == "page2")

# --- every body control counts as "from below" --------------------------
for body in DetailWindow.PAGE2_BODY_IDS:
    w = Pager(DetailWindow.PILL_PRIMARY)
    w.press(DOWN)
    w.press(DOWN, native_lands_on=body)
    w.press(UP, native_lands_on=DetailWindow.TAB_CAST)
    check(f"Up from page-2 body control {body} holds at the tab bar",
          w.page == "page2")

# --- moving ALONG the tab bar is not an arrival --------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)
w.setFocusId(DetailWindow.TAB_ABOUT)        # Right, native, tab -> tab
w.press(UP)
check("Up after moving sideways along the tabs still leaves in one press",
      w.page == "page1",
      "a tab-to-tab move is not an arrival from below")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
