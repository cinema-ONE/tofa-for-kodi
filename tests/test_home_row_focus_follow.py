"""Moving a home row keeps focus ON that row, including at the boundaries.

The row editor gives each row three focus targets, and the arrows are
DISABLED at the ends: the first row cannot move up, the last cannot move
down. So the arrow a viewer just pressed is sometimes disabled at the row's
NEW position -- move row 2 up and it becomes row 1, whose up arrow is
dimmed.

The first version focused the pressed column regardless. setFocusId on a
disabled control does nothing, so focus stayed on the row that had just
moved away and the next Up escaped to the nav bar. Reported from the box
2026-08-27: "when I move the 2nd row UP, the focus doesn't move with the
row, and pressing up lands on the main menu pill".

The rule these pin: follow the ROW to the nearest control that can hold
focus -- pressed column, then the other arrow, then the switch, which is
never disabled.

Run:  python3 test_home_row_focus_follow.py
"""
from __future__ import annotations
import sys

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def landing_column(action: str, landed: int, last: int) -> int:
    """The column main.py picks after a move. Mirrors the loop in
    _settings_home_row_pressed; kept here as the thing under test because
    the real one needs a live Kodi window to call."""
    wanted = 0 if action == "up" else 1
    for col in (wanted, 1 - wanted, 2):
        if col == 0 and landed == 0:
            continue
        if col == 1 and landed == last:
            continue
        return col
    return 2


UP, DOWN, SWITCH = 0, 1, 2

# --- the reported bug ---------------------------------------------------
check("row 2 moved UP lands on a control that can hold focus",
      landing_column("up", landed=0, last=7) != UP,
      "the top row's up arrow is disabled; focusing it strands the viewer")
check("...and prefers the DOWN arrow, staying on the arrows",
      landing_column("up", landed=0, last=7) == DOWN)

# --- its mirror ---------------------------------------------------------
check("second-to-last moved DOWN does not land on the dimmed down arrow",
      landing_column("down", landed=7, last=7) != DOWN)
check("...and prefers the UP arrow",
      landing_column("down", landed=7, last=7) == UP)

# --- the ordinary middle case is unchanged ------------------------------
check("a middle row keeps the column it was moved with (up)",
      landing_column("up", landed=3, last=7) == UP)
check("a middle row keeps the column it was moved with (down)",
      landing_column("down", landed=3, last=7) == DOWN)

# --- degenerate: a single row, both arrows disabled ----------------------
check("with one row only, focus falls to the switch",
      landing_column("up", landed=0, last=0) == SWITCH,
      "both arrows are disabled; the switch never is")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
