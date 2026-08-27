# -*- coding: utf-8 -*-
"""Shared home_screen row-id / list_type -> localized-label maps, plus the
windowed Home screen's fixed row-slot control-id scheme.

Single source of truth for GET /api/v1/users/me's preferences.home_screen.
rows, consumed by both the legacy plugin:// directory UI (addon.py's
show_root_menu) and the windowed Home section (windows/main.py:MainWindow's
_home_* methods) -- both must resolve the same row ids/list_types to the
same labels.

Anything not in these maps (a row type/id/list_type this add-on doesn't
know about yet) must be skipped by the caller via log.debug, never a
crash -- feature-detect rather than assume a fixed surface.

Deliberately plain data, no xbmc*/api imports -- safe to import from
plugin:// context (addon.py), windowed context (windows/main.py), and the
skin's stdlib-only render_all() CLI (skin/screens.py).
"""
from __future__ import annotations

BUILTIN_ROW_LABELS: dict[str, int] = {
    "continue_watching": 31000,
    "recent_movies": 31060,
    "recent_tv": 31061,
    # Server 0.9.27. The web app orders it right after Recently Added TV and
    # calls it "Recently Released": what you OWN, by release date, movies and
    # shows in one row, so a title added last year but only just released is
    # not buried behind the newest imports.
    "recently_released": 31107,
    # Server 0.9.29 SPLIT that row in two. The mixed one above is still
    # offered in the web editor, so all three ids are live and a profile can
    # carry any of them -- this is an addition, not a replacement.
    #
    # These ids are not guessed: they were read out of the web app's own
    # HomePage chunk, which is also where the language lists came from. An
    # id we do not know is dropped in silence by main.py, so a fresh profile
    # would simply have shown two fewer rows.
    "recently_released_movies": 31112,
    "recently_released_tv": 31113,
    "top_rated_movies": 31062,
    "top_rated_tv": 31063,
    "suggested": 31064,
}

# ------------------------------------------------- the account's DEFAULTS --
# The ten rows a tofa account starts with. Every tofa app REFUSES to remove
# one of these -- you can only switch it off -- and Adrian confirmed the rule
# holds on macOS, the web app, iOS and tvOS alike (2026-08-27).
#
# Read out of the web app's own bundle rather than inferred from a screenshot,
# because nothing in the row data marks them: the two trending rows are typed
# `discovery` exactly like a row a viewer added, and the API has no field
# telling them apart. The web app carries the list client-side and so must we.
#
#     Bn = the eight builtin ids below
#     Hn = the two discovery rows below
#     Gn = new Set([...Bn, ...Hn.map(e => e.id)])
#     Kn = e => Gn.has(e.id)          // "is a default row"
#
# A profile made before a row existed simply lacks it -- "The Kid" has eight
# rows, not ten, because it predates the recently_released split. That is why
# this is a PROTECTED set and not an expected one: never assume all ten are
# present.
HOME_ROW_DEFAULT_BUILTINS: tuple[str, ...] = (
    "continue_watching",
    "recent_movies",
    "recent_tv",
    "recently_released_movies",
    "recently_released_tv",
    "top_rated_movies",
    "top_rated_tv",
    "suggested",
)
HOME_ROW_DEFAULT_DISCOVERY: tuple[str, ...] = (
    "discover-trending-movies",
    "discover-trending-tv",
)
HOME_ROW_PROTECTED_IDS: frozenset = frozenset(
    HOME_ROW_DEFAULT_BUILTINS + HOME_ROW_DEFAULT_DISCOVERY)

# The builtin rows the editor may OFFER: every one it knows minus the eight
# it can never remove. Today that is `recently_released` alone -- the mixed
# movies-and-shows row the 0.9.29 split superseded but did not retire.
#
# Mirrors the web app's `Vn = zn.filter(e => !Bn.includes(e.id))`, quirk
# included: a profile that never had `recently_released_tv` cannot gain it
# here, because that id is protected and therefore never offered. Widening
# this to "any builtin not currently present" would fix that and is
# deliberately NOT done -- the preference blob is shared with four other
# apps, and inventing an option none of them offers is how the row lists
# drift apart.
ADDABLE_BUILTIN_IDS: tuple[str, ...] = tuple(
    row_id for row_id in BUILTIN_ROW_LABELS
    if row_id not in HOME_ROW_DEFAULT_BUILTINS
)


def row_is_default(row: dict) -> bool:
    """Is this one of the ten rows every account starts with?"""
    return row.get("id") in HOME_ROW_PROTECTED_IDS


def row_removable(row: dict) -> bool:
    """May the viewer take this row OFF the list, as opposed to switching it
    off? Mirrors the web app's `Jn`.

    A default row never can. Anything else can, provided we recognise it:
    a discovery row, a genre row, or a builtin from BUILTIN_ROW_LABELS.

    A row matching none of those is one this add-on does not understand, and
    it is left alone deliberately -- removing what we cannot name would
    delete another app's row on the viewer's behalf.
    """
    if row_is_default(row):
        return False
    row_type = row.get("type")
    if row_type in ("genre", "discovery"):
        return True
    if row.get("genre") or row.get("discoveryList"):
        return True
    return row_type == "builtin" and row.get("id") in BUILTIN_ROW_LABELS


DISCOVERY_LIST_LABELS: dict[str, int] = {
    "trending-movies": 31080,
    "trending-tv": 31081,
    "popular-movies": 31082,
    "popular-tv": 31083,
    "top-rated-movies": 31062,
    "top-rated-tv": 31063,
    "upcoming-movies": 31084,
}

# Fixed number of row slots main.xml.tpl (Home section) pre-declares.
#
# WAS 9, on a note reading "the real account currently sends 8 rows, leaving
# one spare slot". That went stale: tofa's DEFAULT home screen is now TEN
# rows (eight builtins plus the two trending ones -- see
# HOME_ROW_PROTECTED_IDS), so a profile created today overflowed by one
# before it was touched at all. Caught 2026-08-27 by adding a tenth row and
# watching it not appear -- not on Home, and not in the Settings editor
# either, where its controls did not exist to focus.
#
# 16 now, matching MAX_DISCOVER_ROWS and for the same reason: a slot nobody
# uses renders nothing, while running out drops a row in silence. Ten of the
# sixteen are spoken for before the viewer adds a single genre row.
MAX_HOME_ROWS = 16

#: The home-screen EDITOR in Settings > Appearance: three focusable
#: controls per row slot, laid out like the reference app -- move up, move
#: down, and the on/off switch.
#:
#: They have to be real controls rather than parts of a list item: Kodi
#: builds a list item's layout with `insideContainer=true`
#: (CGUIListItemLayout::LoadControl), so those controls are drawn but never
#: join the focus tree -- the list itself is the single focus target. A
#: grouplist of real buttons is the shape Kodi's own Estuary uses for
#: SettingsCategory, and it is what makes three targets per row reachable.
#:
#: 9101/9102/9103/9104 for slot 0, then +10 per slot.
#:
#: The block moved from 88xx when the slot count went to 16: 8800 + 10*15
#: reaches 8950, and Playback & Video's segmented rows own 8900-8973. 84xx
#: was never available either -- that pane's segments are 8410-8450 with its
#: grouplist at 8490, and check_xml.py caught that collision the first time
#: this was written. Above 9000 (the hero backdrop, the highest id in the
#: window) there is nothing to collide with at all.
HOME_ROW_EDIT_IDS: tuple[tuple[int, int, int, int], ...] = tuple(
    (9101 + 10 * i, 9102 + 10 * i, 9103 + 10 * i, 9104 + 10 * i)
    for i in range(MAX_HOME_ROWS)
)

#: Column meaning, so a caller never indexes these by a bare number.
EDIT_UP, EDIT_DOWN, EDIT_TOGGLE, EDIT_REMOVE = 0, 1, 2, 3

#: Slot i's wrapping group, so the whole row can be hidden when the account
#: has fewer rows than slots.
HOME_ROW_EDIT_GROUP_IDS: tuple[int, ...] = tuple(
    9100 + 10 * i for i in range(MAX_HOME_ROWS)
)

# HOME_ROW_GROUP_IDS[i]/HOME_ROW_LIST_IDS[i] is slot i's (group, list)
# control-id pair in the Home section of main.xml.tpl (rendered to
# script-tofa-main.xml).
#
# The stride was 200 per slot, inherited from the three original hardcoded
# rows (4100/4200, 4300/4400, 4500/4600). Nine slots reached 5800 and a
# tenth would have landed on 6000, which is Browse. Nothing needed those
# ninety spare ids, so the stride is now 20 -- the same shape the Discover
# rows use -- and sixteen slots fit in 4100-4410 with room over.
#
# No collisions with the hero block (4000-4005), the row region's own
# grouplist (4090), the nav bar (2000/3000), the hero backdrop (9000), or
# the kodigui sentinel (666). check_xml.py proves it per render.
HOME_ROW_GROUP_IDS: tuple[int, ...] = tuple(4100 + 20 * i for i in range(MAX_HOME_ROWS))
HOME_ROW_LIST_IDS: tuple[int, ...] = tuple(gid + 10 for gid in HOME_ROW_GROUP_IDS)


# Discover's row slots. Sized for the LARGEST group tab rather than a fixed
# three. Today that's "Now" at 11 (`now` + `availability`); the 16 is kept as
# headroom because slots are cheap (an unused one renders nothing) while
# running out silently truncates a tab -- and Acclaimed absorbs every unknown
# kind the server may add, so its size isn't bounded by anything we control.
#
# 7000+ because MainWindow is one merged window whose ids must be globally
# unique -- Home holds 4100-5800, Browse 6000-6200, Search 6700-6860, so the
# obvious 6400+100*i scheme collides with Search's keyboard (6700) outright.
MAX_DISCOVER_ROWS = 16
DISCOVER_ROW_GROUP_IDS: tuple[int, ...] = tuple(7000 + 20 * i for i in range(MAX_DISCOVER_ROWS))
DISCOVER_ROW_LIST_IDS: tuple[int, ...] = tuple(gid + 10 for gid in DISCOVER_ROW_GROUP_IDS)


# ------------------------------------------------------------ Discover tabs --
# GET /discovery/page returns all 32 shelves in one flat list, each tagged with
# a `kind`. The real Apple TV app groups them under four pills rather than
# scrolling all 32, and the grouping is purely by kind -- live server counts
# 2026-07-31: now 8, availability 3, standard 4, decade 6, genre 7, house 4.
#
# This mapping is the design spec's (TV-DESIGN.md 7.9.2, dated 2026-07-31), not
# one inferred from screenshots. It differs from what our reference captures
# show in two ways, both resolved in the spec's favour on Adrian's call --
# the spec is newer than the shipped tvOS build we captured:
#
#   * `house` files under Acclaimed, not Now. (Captures showed Reality TV, a
#     `house` shelf, sitting in Now directly above the `availability` block.)
#   * An unknown kind falls into ACCLAIMED, not Now. The spec sweeps any
#     kind it does not know into that tab and tells us never to drop a
#     shelf -- the important half is that it must never vanish; which tab
#     catches it is the arbitrary part.
#
# Dropping `house` from Now also retires DISCOVER_SHELF_ORDER_LAST, which
# existed solely to sort `top-reality-tv` to the end of Now's `house` block so
# it landed adjacent to Coming Soon the way the capture showed. With `house`
# gone from the tab entirely there is nothing left for that hack to fix, and
# shelves now keep the server's order within a kind, everywhere, with no
# exceptions.
#
# Now stays the largest tab (8 + 3 = 11); Acclaimed is 8 plus whatever unknown
# kinds arrive. MAX_DISCOVER_ROWS keeps its headroom rather than shrinking to
# fit today's counts -- see its own comment.
DISCOVER_TAB_KINDS: dict[str, tuple[str, ...]] = {
    "now": ("now", "availability"),
    "acclaimed": ("standard", "house"),
    "genres": ("genre",),
    "decades": ("decade",),
}
# Where a shelf goes when its `kind` matches nothing above. Deliberately NOT
# the same constant as the tab that opens first (that's DISCOVER_DEFAULT_TAB).
DISCOVER_UNKNOWN_KIND_TAB = "acclaimed"
DISCOVER_DEFAULT_TAB = "now"

# (tab key, label, pill width). Widths are measured, not guessed: the labels are
# static, so each pill is exactly its rendered label plus 26px padding a side at
# tofa_font_button (inter_tight_semibold 28). Verified against the reference --
# 110/186/144/165 measured off the capture vs. text widths of 58/134/91/111,
# i.e. a constant 52-54px total padding across all four. Recompute with:
#   PIL.ImageFont.truetype("inter_tight_semibold.ttf", 28).getbbox(label)
# if a label ever changes; fragments.py can't do it itself (stdlib-only, and
# PIL doesn't exist inside Kodi).
DISCOVER_TABS: tuple[tuple[str, str, int], ...] = (
    ("now", "Now", 110),
    ("acclaimed", "Acclaimed", 186),
    ("genres", "Genres", 144),
    ("decades", "Decades", 165),
)
DISCOVER_TAB_GAP = 18
DISCOVER_TAB_HEIGHT = 54

# One single-item list per pill, same shape as Browse's four Sort/Filter/
# Quality/Genre pills -- a Kodi <list> has one fixed itemwidth, so four
# text-hugging widths can't be one list. 6900+ is clear of Browse (6000-6200),
# Search (6700-6860) and the Discover rows (7000-7310).
DISCOVER_TAB_LIST_IDS: tuple[int, ...] = tuple(6900 + 10 * i for i in range(len(DISCOVER_TABS)))

# Pill x offsets are NOT here: they derive from tokens.CONTENT_LEFT, and this
# module stays free of that dependency. See fragments.discover_tab_positions().


def row_title(row: dict, localize) -> str:
    """A display name for one `home_screen.rows` entry, WITHOUT touching the
    network.

    _home_load() names rows too, but it can only do so while it is already
    fetching them -- a discovery row it does not have a local label for falls
    back to the title the server sent with the shelf. The Settings editor
    lists rows before anything is fetched and must never block on HTTP to
    draw a label, so it de-slugs the list type instead ("trending-movies" ->
    "Trending Movies"). The two agree wherever a local label exists, which is
    every builtin and the original seven shelves.

    Returns "" for a row this add-on does not understand, so callers can skip
    it the same way _home_load() does rather than showing a blank line.
    """
    row_type = row.get("type")
    if row_type == "builtin":
        label_id = BUILTIN_ROW_LABELS.get(row.get("id"))
        return localize(label_id) if label_id else ""
    if row_type == "discovery":
        list_type = row.get("discoveryList")
        if not list_type:
            return ""
        label_id = DISCOVERY_LIST_LABELS.get(list_type)
        if label_id:
            return localize(label_id)
        return list_type.replace("-", " ").replace("_", " ").title()
    if row_type == "genre":
        return row.get("genre") or ""
    return ""
