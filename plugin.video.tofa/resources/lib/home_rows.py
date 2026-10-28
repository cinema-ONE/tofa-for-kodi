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
    # Server 0.12.0's universes: the franchises you are part way through.
    "continue_saga": 31134,
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
    # Server 0.9.35's lifecycle feature: titles the server's own rules have
    # flagged for removal, from GET /lifecycle/leaving-soon. The web app
    # offers it under "Home rows" and draws it only when the server reports
    # the `lifecycle` capability; an older server answers 404, which
    # fetch_builtin_row turns into an empty row, and an empty row hides.
    "leaving_soon": 31123,
    "top_rated_movies": 31062,
    "top_rated_tv": 31063,
    "suggested": 31064,
}

# ------------------------------------------------- the account's DEFAULTS --
# The eleven rows a tofa account starts with (ten before 0.12.0's saga
# row). Every tofa app REFUSES to remove one of these -- you can only switch
# it off -- and Adrian confirmed the rule holds on macOS, the web app, iOS
# and tvOS alike (2026-08-27).
#
# Read out of the web app's own bundle rather than inferred from a screenshot,
# because nothing in the row data marks them: the two trending rows are typed
# `discovery` exactly like a row a viewer added, and the API has no field
# telling them apart. The web app carries the list client-side and so must we.
#
#     Bn = the nine builtin ids below
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
    "continue_saga",
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

# The builtin rows the editor may OFFER: every one it knows minus the nine
# it can never remove. Today that is `recently_released` -- the mixed
# movies-and-shows row the 0.9.29 split superseded but did not retire -- and
# `leaving_soon` (0.9.35), which the caller drops on a server without the
# `lifecycle` capability, as the web app does.
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


def normalize_home_screen(home: dict | None) -> dict:
    """The home_screen preference as every tofa app READS it, which is not
    quite as it is stored.

    Mirrors the web app's normaliser (`$n` in its bundle, 0.9.35): the stored
    rows keep their order, and then every one of the default rows the
    profile LACKS is appended at the end, enabled -- the builtins first,
    then the two trending discovery rows. A profile that predates the
    recently_released split therefore still shows both halves of it, on Home
    and in the editor, on the web, on macOS and here. The first time the
    editor saves, the appended rows are written back, which is also what the
    web app does.

    Returns a NEW dict {show_hero, rows} and never touches the input. Rows
    without a string `id` are dropped, as the web drops them; `enabled`
    defaults to True and a missing type reads as builtin. Unlike the web, a
    row keeps its other fields and its type even when we cannot draw it.
    """
    defaults = ([{"id": rid, "type": "builtin", "enabled": True}
                 for rid in HOME_ROW_DEFAULT_BUILTINS]
                + [{"id": "discover-" + key[len("discover-"):], "type": "discovery",
                    "enabled": True, "discoveryList": key[len("discover-"):]}
                   for key in HOME_ROW_DEFAULT_DISCOVERY])
    home = home if isinstance(home, dict) else {}
    show_hero = home.get("show_hero")
    if not isinstance(show_hero, bool):
        show_hero = True
    stored = home.get("rows")
    if not isinstance(stored, list) or not stored:
        return {"show_hero": show_hero, "rows": defaults}
    rows: list[dict] = []
    for row in stored:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        # Every stored field and type is kept: this list is written back on
        # the first edit, and a newer app's row must survive it intact.
        row_type = row.get("type")
        out = dict(row, type=row_type if isinstance(row_type, str) and row_type else "builtin",
                   enabled=row.get("enabled") if isinstance(row.get("enabled"), bool) else True)
        rows.append(out)
    present = {r["id"] for r in rows}
    if "continue_saga" not in present:
        # The web (0.12.0) slots the saga row in under Continue Watching
        # rather than at the end; with no Continue Watching, first.
        at = next((i + 1 for i, r in enumerate(rows) if r["id"] == "continue_watching"), 0)
        rows.insert(at, {"id": "continue_saga", "type": "builtin", "enabled": True})
        present.add("continue_saga")
    for default in defaults:
        if default["id"] not in present:
            rows.append(dict(default))
    return {"show_hero": show_hero, "rows": rows}


def shows_universes(preferences: dict | None) -> bool:
    """The web's Universes switch (0.12.0): on unless set to false."""
    return (preferences or {}).get("show_universes") is not False


def deslug(list_type: str) -> str:
    """"new-noteworthy-tv" -> "New Noteworthy TV". The last-resort name for a
    shelf whose title nothing supplied; `str.title()` alone would write "Tv",
    which is not how anyone writes it."""
    words = list_type.replace("-", " ").replace("_", " ").split()
    return " ".join("TV" if w.lower() == "tv" else w.capitalize() for w in words)


def row_is_default(row: dict) -> bool:
    """Is this one of the rows every account starts with?"""
    return row.get("id") in HOME_ROW_PROTECTED_IDS


def row_removable(row: dict) -> bool:
    """May the viewer take this row OFF the list, as opposed to switching it
    off? Mirrors the web app's `Jn`.

    A default row never can. Anything else can, provided we recognise it:
    a discovery, genre or library row, or a builtin from BUILTIN_ROW_LABELS.

    A row matching none of those is one this add-on does not understand, and
    it is left alone deliberately -- removing what we cannot name would
    delete another app's row on the viewer's behalf.
    """
    if row_is_default(row):
        return False
    row_type = row.get("type")
    if row_type in ("genre", "discovery", "library"):
        return True
    if row.get("genre") or row.get("discoveryList"):
        return True
    return row_type == "builtin" and row.get("id") in BUILTIN_ROW_LABELS


def library_row(library_id: str) -> dict:
    """A "Recently Added in <library>" row, stored as the Apple TV app (2.1.2) stores it."""
    return {"type": "library", "id": "library-recent:" + library_id,
            "libraryId": library_id, "enabled": True}


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

#: Settings > Home's row editor (app 2.0): one card per slot, a one-item
#: list in its own group so the group can hide when the account has fewer
#: rows. Slot i: group 9100 + 10i, list 9101 + 10i (clear of 89xx and 9000).
HOME_ROW_EDIT_IDS: tuple[int, ...] = tuple(
    9101 + 10 * i for i in range(MAX_HOME_ROWS))
HOME_ROW_EDIT_GROUP_IDS: tuple[int, ...] = tuple(
    9100 + 10 * i for i in range(MAX_HOME_ROWS))

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
#: TWO row regions, and therefore two full sets of row slots -- one for each
#: state of "Featured spotlight".
#:
#: The hero leaves the rows exactly one row-block of screen; with the hero
#: off they get the whole content area and show 1.67 rows. That is a
#: difference in the grouplist's HEIGHT, and a grouplist's height cannot be
#: changed from either side: skin XML has no conditional <height>, and Kodi's
#: Python binding has no wrapper for GUICONTROL_GROUPLIST (getControl on one
#: raises "Unknown control type for python"). Two controls, each with its own
#: <visible>, is the only way to have both.
#:
#: 0.9.18 tried to avoid the duplication with ONE tall list and a spacer child
#: hidden with the hero. It laid out correctly at rest and broke the moment
#: the list scrolled: a grouplist draws its content from its own top edge, so
#: scrolling down drew the rows over the hero's logo, title and synopsis.
#:
#: Both sets carry the SAME `row{i}_title` window properties, so nothing that
#: fills a row has to know which set is live -- only MainWindow.ROW_LIST_IDS
#: does, and it swaps with the setting.
HOME_ROWS_GROUPLIST_ID = 4090
HOME_ROWS_GROUPLIST_ID_NOHERO = 4490

HOME_ROW_GROUP_IDS: tuple[int, ...] = tuple(4100 + 20 * i for i in range(MAX_HOME_ROWS))
HOME_ROW_LIST_IDS: tuple[int, ...] = tuple(gid + 10 for gid in HOME_ROW_GROUP_IDS)

#: The hero-off set. 4500-4810, clear of the hero block (4000-4005), the two
#: grouplists (4090/4490), the hero-on slots (4100-4410) and Browse (6000+).
#: check_xml.py proves it per render.
HOME_ROW_GROUP_IDS_NOHERO: tuple[int, ...] = tuple(
    4500 + 20 * i for i in range(MAX_HOME_ROWS))
HOME_ROW_LIST_IDS_NOHERO: tuple[int, ...] = tuple(
    gid + 10 for gid in HOME_ROW_GROUP_IDS_NOHERO)


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
# Discover's tabs, as the Apple TV app 2.1.0 has them. The server's layout-2
# page names all but Universes, which tofa's apps add before Genres.
DISCOVER_DEFAULT_TAB = "for-you"
DISCOVER_TABS: tuple[tuple[str, str], ...] = (
    ("for-you", "For You"),
    ("trending", "Trending"),
    ("coming-up", "Coming Up"),
    ("best-of", "Best Of"),
    ("universes", "Universes"),
    ("genres", "Genres"),
)
# The sub-tabs are one list (app 2.0.0's text tabs), clear of Browse
# (6000-6200), Search (6700-6860) and the Discover rows (7000-7310).
DISCOVER_TAB_STRIP_ID = 6900
# The strip's last item opens Filters: (server flag, label), in screen order.
DISCOVER_FILTERS: tuple[tuple[str, str], ...] = (
    ("hide_watched", "Hide watched movies"),
    ("hide_cinema", "Hide cinema-only movies"),
    ("hide_upcoming", "Hide upcoming"),
    ("only_in_library", "Only show my library"),
)
DISCOVER_FILTER_LIST_ID = 6950


def row_title(row: dict, localize, shelf_titles: dict | None = None,
              library_names: dict | None = None) -> str:
    """A display name for one `home_screen.rows` entry, WITHOUT touching the
    network.

    A discovery row is named by the SERVER: `shelf_titles` is the key ->
    title map read off /discovery/page (the window keeps one, filled by
    whichever of Home or the editor fetched the page first). That is the
    order the web app uses too -- its local map is only the fallback for a
    page that failed -- and it is what keeps the editor, the "Add a row"
    picker and Home saying the same name. Before this the editor de-slugged
    the key and so read "New Noteworthy Tv" for the shelf every other surface
    calls "New Series Worth Starting", and Home said "Trending TV Shows" where
    the apps say "Trending Shows".

    The local label map is the fallback, and deslug() the fallback's fallback,
    so the editor still draws without a network call.

    A library row is named after its library, from `library_names` (id ->
    name); one whose library is gone, or not yet known, is unnamed.

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
        title = (shelf_titles or {}).get(list_type)
        if title:
            return title
        label_id = DISCOVERY_LIST_LABELS.get(list_type)
        if label_id:
            return localize(label_id)
        return deslug(list_type)
    if row_type == "genre":
        return row.get("genre") or ""
    if row_type == "library":
        name = (library_names or {}).get(row.get("libraryId"))
        return "Recently Added in {0}".format(name) if name else ""
    return ""
