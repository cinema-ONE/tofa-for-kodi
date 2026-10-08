"""One Up press leaves page 2, and moving up INSIDE page 2 does not.

Detail is one screen in two halves. Down off an action pill brings page 2
in; Up off page 2's first control takes it away again. Kodi's own focus
engine cannot serve either direction, so detail.py drives both with
setFocusId() from onAction.

getFocusId() reflects focus AFTER Kodi's native attempt, so onAction cannot
tell "Up carried the cursor onto the first control" (leave it) from "Up on
the first control did nothing" (go back to the hero). _p2_just_arrived,
armed in onFocus only for an arrival from BELOW, is the tie-breaker. Armed
on any arrival, it swallowed the first Up after entering, and the hero took
TWO presses to reach (reported from the box 2026-09-01).

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

    # Every id and table comes from the real class, so a renumbered control
    # cannot leave this passing against stale ids.
    for _name in ("PILL_PRIMARY", "PILL_RETRY", "PILL_CANCEL_REQUEST",
                  "PILL_WATCHLIST", "PAGE2_BODY_IDS", "P2_SECTIONS",
                  "CAST_LIST", "EPISODE_GRID_PANEL", "SEASON_SIDEBAR_LIST",
                  "SIMILAR_LIST", "DISCOVER_LIST", "ABOUT_BUTTON",
                  "PILL_REWATCH", "PILL_OPTIONS", "PILL_VERSION"):
        locals()[_name] = getattr(DetailWindow, _name)
    del _name

    onFocus = DetailWindow.onFocus
    onAction = DetailWindow.onAction
    _page1_focus_id = DetailWindow._page1_focus_id
    _p2_shown = DetailWindow._p2_shown
    _p2_entry = DetailWindow._p2_entry
    _p2_sync_hints = DetailWindow._p2_sync_hints
    _primary_is_actionable = lambda self: True

    def __init__(self, focus, show=False):
        self.props = {"detailpage": "page1", "has_cast_content": "1",
                      "similar_row_title": "More Like This",
                      "p2_has_episodes": "1" if show else ""}
        self._prev_focus_id = 0
        self._p2_just_arrived = False
        self._focus = 0
        self.setFocusId(focus)

    # -- the window surface the two handlers touch ----------------------
    def getProperty(self, key): return self.props.get(key, "")
    def setProperty(self, key, value): self.props[key] = value
    def getFocusId(self): return self._focus
    def setFocusId(self, control_id):
        self._focus = control_id
        self.onFocus(control_id)
    def _sync_episode_block(self): pass
    def _open_card_options(self, _cid): return False
    def _open_season_options(self): return False
    def _open_hero_options(self): return False

    # -- the keypress ---------------------------------------------------
    def press(self, aid, native_lands_on=None):
        """One d-pad press. `native_lands_on` is where Kodi's own focus
        engine put the cursor before onAction saw it: a control id when the
        move succeeded, None when it did not."""
        if native_lands_on is not None:
            self.setFocusId(native_lands_on)
        self.onAction(Action(aid))

    @property
    def page(self): return self.props["detailpage"]


UP, DOWN = xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN

# --- the reported bug ---------------------------------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)
check("Down off the primary pill enters page 2", w.page == "page2")
check("...landing on the first section, Cast", w._focus == DetailWindow.CAST_LIST)

w.press(UP)
check("ONE Up press comes back to page 1", w.page == "page1",
      "entering page 2 must not arm _p2_just_arrived")
check("...landing on the primary pill", w._focus == DetailWindow.PILL_PRIMARY)

w.press(DOWN)
w.press(UP)
check("Down/Up is repeatable, still one press each way", w.page == "page1")

# --- what the flag is actually FOR --------------------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)
w.press(DOWN, native_lands_on=DetailWindow.SIMILAR_LIST)
check("Down again scrolls to More Like This", w._focus == DetailWindow.SIMILAR_LIST)
check("...and page 2 stays up", w.page == "page2")
check("...with no OVERVIEW hint off the top section", w.props.get("p2_at_top") == "")

w.press(UP, native_lands_on=DetailWindow.CAST_LIST)
check("Up back to Cast stops there",
      w.page == "page2" and w._focus == DetailWindow.CAST_LIST,
      "native nav already served this press; page 1 would overshoot")
check("...and the OVERVIEW hint returns", w.props.get("p2_at_top") == "1")

w.press(UP)
check("a SECOND Up, still on Cast, does leave for page 1", w.page == "page1")

# --- a show: the episode row, the pills above it -------------------------
w = Pager(DetailWindow.PILL_PRIMARY, show=True)
w.press(DOWN)
check("a show lands on the episode row", w._focus == DetailWindow.EPISODE_GRID_PANEL)
check("...naming the section below it", w.props.get("p2_next_hint") == "CAST & CREW",
      repr(w.props.get("p2_next_hint")))
w.press(UP, native_lands_on=DetailWindow.SEASON_SIDEBAR_LIST)
check("Up from the episodes stops on the season pills", w.page == "page2")
w.press(UP)
check("...and the next Up leaves for the hero", w.page == "page1")

# --- every body control counts as "from below" --------------------------
for body in DetailWindow.PAGE2_BODY_IDS:
    if body == DetailWindow.CAST_LIST:
        continue
    w = Pager(DetailWindow.PILL_PRIMARY)
    w.press(DOWN)
    w.press(DOWN, native_lands_on=body)
    w.press(UP, native_lands_on=DetailWindow.CAST_LIST)
    check(f"Up from page-2 control {body} holds at the first section",
          w.page == "page2")

# --- Back on page 2 goes to page 1 --------------------------------------
w = Pager(DetailWindow.PILL_PRIMARY)
w.press(DOWN)
w.press(xbmcgui.ACTION_NAV_BACK)
check("Back on page 2 returns to the hero", w.page == "page1"
      and w._focus == DetailWindow.PILL_PRIMARY)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
