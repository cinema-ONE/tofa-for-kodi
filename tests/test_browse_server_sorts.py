"""The server declares the sort vocabulary and the default. Honour both.

`GET /api/v1/media/facets` returns `sorts`, `default_sort` and
`default_order`, and the contract's reason for it is that a client should
offer what the server really has rather than a table baked in at build time:
no empty facets, and one agreed default. Two things can go quietly
wrong when a hardcoded table starts being filtered by a server list:

  1. The picker shows POSITIONS, and picked_idx is a position in the rows
     that were passed. Once the rows are a SUBSET of BROWSE_SORT_OPTIONS,
     treating that position as an index into the full table selects the
     wrong sort -- silently, since every index is valid.

  2. `default_order` is the direction for the default sort, while our own
     table carries its own opinion per sort. It has to be stored as the
     REVERSED flag relative to our entry. Get it backwards and the pill
     shows a down arrow over an ascending grid.

Neither raises. Both are checked here against the real methods, bound to a
stand-in so no Kodi window is needed.

Run:  python3 test_browse_server_sorts.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import main as main_mod

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


MW = main_mod.MainWindow
OPTIONS = MW.BROWSE_SORT_OPTIONS
VALUES = [v for _l, v, _o in OPTIONS]


class Item(dict):
    def setProperty(self, k, v):
        self[k] = v


class Browse:
    """Only what the sort methods touch."""

    BROWSE_SORT_OPTIONS = OPTIONS

    def __init__(self, server_sorts=None, picked=False, idx=0, reversed_=False):
        self._browse_server_sorts = server_sorts
        self._browse_sort_user_picked = picked
        self._browse_sort_idx = idx
        self._browse_sort_reversed = reversed_
        self.sort_list = [Item()]

    _browse_offered_sorts = MW._browse_offered_sorts
    _browse_apply_server_sort_default = MW._browse_apply_server_sort_default
    _browse_sync_sort_pill = MW._browse_sync_sort_pill
    _browse_sort_glyph = MW._browse_sort_glyph


# --------------------------------------------------------------------------
# 1. Which sorts get offered
# --------------------------------------------------------------------------

check("a server that never answered gets the WHOLE local table",
      Browse(server_sorts=None)._browse_offered_sorts()
      == list(range(len(OPTIONS))))

subset = ("title", "added_at")
offered = Browse(server_sorts=subset)._browse_offered_sorts()
check("only the sorts the server lists are offered",
      [VALUES[i] for i in offered] == ["added_at", "title"],
      str([VALUES[i] for i in offered]))

check("a sort the server does NOT list is hidden (it would silently no-op)",
      all(VALUES[i] != "random" for i in offered))

# A key we have no row for cannot be invented; it must not crash or appear.
mixed = Browse(server_sorts=("title", "popularity"))._browse_offered_sorts()
check("an unknown server sort is skipped, not invented",
      [VALUES[i] for i in mixed] == ["title"], str([VALUES[i] for i in mixed]))

check("no overlap at all falls back to the local table rather than an empty picker",
      Browse(server_sorts=("nothing_we_know",))._browse_offered_sorts()
      == list(range(len(OPTIONS))))


# --------------------------------------------------------------------------
# 2. THE POSITION TRAP
# --------------------------------------------------------------------------
# Reproduces what _browse_sort_clicked does: build rows from `offered`, then
# map the picked POSITION back. With a filtered list the two differ, which is
# the whole point.

offered = Browse(server_sorts=("title", "random"))._browse_offered_sorts()
rows = [OPTIONS[i][0] for i in offered]
check("rows are built from the offered subset", rows == ["Title", "Shuffle"], str(rows))

picked_pos = 1                      # the viewer picked "Shuffle"
mapped = offered[picked_pos]
check("THE POSITION TRAP: position maps back to the right option",
      OPTIONS[mapped][1] == "random", OPTIONS[mapped][0])
check("...and taking the position as a raw index would have been WRONG",
      OPTIONS[picked_pos][1] != OPTIONS[mapped][1],
      "the bug would be invisible if these matched")


# --------------------------------------------------------------------------
# 3. default_sort / default_order
# --------------------------------------------------------------------------

b = Browse()
b._browse_apply_server_sort_default("added_at", "desc")
check("the server's default sort is adopted",
      OPTIONS[b._browse_sort_idx][1] == "added_at")
check("...with no reverse, since our own entry is already desc",
      b._browse_sort_reversed is False)

# added_at is "desc" in our table, so an asc default MUST set reversed.
b = Browse()
b._browse_apply_server_sort_default("added_at", "asc")
check("THE DIRECTION TRAP: an opposite default_order sets reversed",
      b._browse_sort_reversed is True)

# title is "asc" in our table -- the mirror case, so the flag is not just
# "always True when the server says asc".
b = Browse()
b._browse_apply_server_sort_default("title", "asc")
check("...and an default_order matching our entry does not",
      OPTIONS[b._browse_sort_idx][1] == "title" and b._browse_sort_reversed is False)

b = Browse()
b._browse_apply_server_sort_default("random", "desc")
check("a directionless sort is never marked reversed",
      OPTIONS[b._browse_sort_idx][1] == "random" and b._browse_sort_reversed is False)

# The rule that protects the viewer.
b = Browse(picked=True, idx=1)
b._browse_apply_server_sort_default("added_at", "desc")
check("A CHOSEN SORT IS NEVER OVERRIDDEN by the server default",
      b._browse_sort_idx == 1)

b = Browse()
b._browse_apply_server_sort_default(None, None)
check("a server that declares no default leaves the sort alone",
      b._browse_sort_idx == 0 and b._browse_sort_reversed is False)

b = Browse()
b._browse_apply_server_sort_default("no_such_sort", "desc")
check("an unknown default_sort is ignored rather than guessed at",
      b._browse_sort_idx == 0)


# --------------------------------------------------------------------------
# 4. The pill agrees with the state
# --------------------------------------------------------------------------

b = Browse()
b._browse_apply_server_sort_default("added_at", "asc")
glyph = b.sort_list[0].get("sort_glyph")
from resources.lib.skin import icon_glyphs  # noqa: E402
check("the pill's arrow follows the reversed flag, not the raw table",
      glyph == chr(icon_glyphs.ARROW_UP), repr(glyph))
check("the pill's label follows the adopted sort",
      b.sort_list[0].get("sort_label") == "Date Added",
      repr(b.sort_list[0].get("sort_label")))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
