"""The ten rows an account starts with can be switched off, never removed.

Adrian checked all four reference apps on 2026-08-27 -- macOS, the web app,
iOS and tvOS -- and they agree: the default rows offer a switch and the two
arrows, and no remove. We offered remove on any row not typed `builtin`,
which meant the two default DISCOVERY rows could be taken off the list here
and nowhere else.

Nothing in the payload marks them. The two trending rows are typed
`discovery` with the same fields as a row a viewer added by hand -- checked
against the live server, and confirmed against the web app's own bundle,
which carries the list client-side:

    Gn = new Set([...Bn, ...Hn.map(e => e.id)])
    Kn = e => Gn.has(e.id)
    Jn = e => Kn(e) ? false : (genre || discovery || known builtin)

So this pins the LIST as much as the logic: get an id wrong and a row
silently becomes removable in this app alone.

Run:  python3 test_home_row_protected.py
"""
from __future__ import annotations
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "plugin.video.tofa" / "resources" / "lib"))
import home_rows                                            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


# --- the list itself -----------------------------------------------------
EXPECTED = {
    "continue_watching", "recent_movies", "recent_tv",
    "recently_released_movies", "recently_released_tv",
    "top_rated_movies", "top_rated_tv", "suggested",
    "discover-trending-movies", "discover-trending-tv",
}
check("exactly ten rows are protected",
      len(home_rows.HOME_ROW_PROTECTED_IDS) == 10,
      str(sorted(home_rows.HOME_ROW_PROTECTED_IDS)))
check("...and they are the ids the reference apps protect",
      set(home_rows.HOME_ROW_PROTECTED_IDS) == EXPECTED,
      str(EXPECTED ^ set(home_rows.HOME_ROW_PROTECTED_IDS)))
check("two of the ten are DISCOVERY rows, not builtins",
      len(home_rows.HOME_ROW_DEFAULT_DISCOVERY) == 2)
check("every protected builtin has a label to draw",
      all(rid in home_rows.BUILTIN_ROW_LABELS
          for rid in home_rows.HOME_ROW_DEFAULT_BUILTINS))


# --- the predicate -------------------------------------------------------
def removable(**row):
    return home_rows.row_removable(row)


for rid in sorted(EXPECTED):
    kind = "discovery" if rid.startswith("discover-") else "builtin"
    row = {"id": rid, "type": kind, "enabled": True}
    if kind == "discovery":
        row["discoveryList"] = rid[len("discover-"):]
    check("default row %s cannot be removed" % rid,
          home_rows.row_removable(row) is False)

check("a trending row the viewer ADDED can be removed",
      removable(id="discover-trending-anime", type="discovery",
                discoveryList="trending-anime") is True,
      "same shape as the two protected ones -- only the id differs")
check("a genre row can be removed",
      removable(id="genre-anime", type="genre", genre="Anime") is True)
check("the superseded `recently_released` builtin can be removed",
      removable(id="recently_released", type="builtin") is True,
      "it is a builtin, but not one of the ten")
check("a row we cannot name is left alone",
      removable(id="something_tofa_added_later", type="builtin") is False,
      "removing what we cannot name would delete another app's row")

# --- what the editor may offer to ADD ------------------------------------
check("no protected builtin is offered as an addition",
      not (set(home_rows.ADDABLE_BUILTIN_IDS)
           & set(home_rows.HOME_ROW_DEFAULT_BUILTINS)),
      "they can never be absent, so offering them would be a dead option")
check("`recently_released` IS offered",
      "recently_released" in home_rows.ADDABLE_BUILTIN_IDS,
      "the mixed row the 0.9.29 split superseded but did not retire")
check("every offered builtin has a label",
      all(rid in home_rows.BUILTIN_ROW_LABELS
          for rid in home_rows.ADDABLE_BUILTIN_IDS))



# --- the editor's columns must be wired in the order they are DRAWN -------
# Left/Right walk a list of column indices. Getting that list in id order
# rather than screen order sent Left from the switch to the up arrow, two
# columns past the remove button -- and a press there MOVES the row, so the
# mis-wire acted rather than merely misfocused.
#
# Checked against the rendered XML, not against a copy of the wiring logic:
# the question is where the buttons actually are.
import xml.etree.ElementTree as ET                              # noqa: E402

XML = (pathlib.Path(__file__).resolve().parents[1] / "plugin.video.tofa"
       / "resources" / "skins" / "Main" / "1080i" / "script-tofa-main.xml")
tree = ET.parse(XML)
posx = {}
for control in tree.iter("control"):
    cid = control.get("id")
    x = control.find("posx")
    if cid and x is not None and x.text and x.text.strip().lstrip("-").isdigit():
        posx[int(cid)] = int(x.text.strip())

SLOT = 0
ids = home_rows.HOME_ROW_EDIT_IDS[SLOT]
check("every column of a row exists in the rendered XML",
      all(i in posx for i in ids),
      str([i for i in ids if i not in posx]))
if all(i in posx for i in ids):
    by_x = sorted(range(4), key=lambda c: posx[ids[c]])
    expected = [home_rows.EDIT_UP, home_rows.EDIT_DOWN,
                home_rows.EDIT_REMOVE, home_rows.EDIT_TOGGLE]
    check("the columns are drawn up, down, remove, switch -- left to right",
          by_x == expected,
          "drawn %s, wiring assumes %s" % (by_x, expected))
    check("...which is NOT the order their ids run in",
          by_x != [0, 1, 2, 3],
          "if these ever agree, delete this test rather than the ordering")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
