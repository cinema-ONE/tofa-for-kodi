# -*- coding: utf-8 -*-
"""One constructor for a poster card's ListItem.

WHY THIS EXISTS. Five screens build the same poster card -- Home rows, the
Browse grid, Search's shelves, Detail's More Like This, and a person's
filmography -- and until now each built it by hand. They are drawn by ONE
fragment (skin/fragments.py:poster_card), so every property that fragment
reads has to be set five separate times, and a new one gets forgotten on
whichever screen the author was not looking at.

That is not hypothetical. `rating` was set at five sites; adding format
badges meant finding all five, and the same day a placeholder was added to
poster_visual's unfocused copy but not its focused one. The fragment side was
fixed by removing the duplicate; this is the Python side of the same problem
(project_card_fragment_drift).

The rule this sets up: anything poster_card() reads for EVERY card belongs
here, and a caller only sets what is genuinely its own -- the caption
grammar, a watchlist flag, a progress bar. If you find yourself adding the
same setProperty to more than one screen, it belongs in this function
instead.

Deliberately NOT a class or a subclass of ManagedListItem: callers keep
setting their own properties on the returned item, and a wrapper would only
add a layer to see through.
"""
from __future__ import annotations

from . import kodigui, theme
from .. import badges
from ..skin import icon_glyphs


def apply_poster(mli, item: dict, poster_url: str, *, label: str | None = None,
                 prefs: dict | None = None, data_source=None):
    """Put a poster card's whole appearance onto an EXISTING ListItem.

    Separate from poster_item() because Browse fills a grid that was already
    allocated to its full length: a blank item is standing in the slot and has
    to BECOME the real card, in place, without the container's length changing
    (main.py: _browse_blanks). Mutating a managed item writes straight
    through to what Kodi is showing, so this is also how plex-for-kodi fills
    its chunks.

    Not done by building a new item and swapping it in: ManagedListItem.setArt
    writes through to the underlying ListItem and records nothing, so a
    freshly built item's poster is exactly what replaceItem() would drop on
    the floor. Whatever a card needs has to be applied to the live item.

    `prefs` is the profile blob; both the rating chip and the badges are
    gated on their own switch inside it (show_card_ratings,
    show_format_badges), so passing it is what makes those preferences work.
    Callers hold it cached -- fetching it here would mean one call per card.

    `data_source` defaults to `item`, which is what four of the five callers
    want; the fifth passes its own wrapper dict.
    """
    mli.dataSource = item if data_source is None else data_source
    mli.setLabel(label if label is not None else (item.get("title") or ""))
    mli.thumbnailImage = poster_url
    mli.setArt({"thumb": poster_url, "poster": poster_url})
    mli.setProperty("rating", theme.card_rating_text(item, prefs))
    badges.apply(mli, item, (prefs or {}).get("show_format_badges", True))
    return mli


def poster_item(item: dict, poster_url: str, *, label: str | None = None,
                prefs: dict | None = None, data_source=None, offscreen=False):
    """A new poster card ListItem with everything poster_card() reads.

    `offscreen=True` skips Kodi's frame-move guard on every write -- pass it
    when the card is built detached and added with addItems() afterwards,
    which is every caller here. See ManagedListItem.__init__ for why that
    matters on the box, and issue #11 for what it cost.
    """
    return apply_poster(kodigui.ManagedListItem(offscreen=offscreen), item, poster_url,
                        label=label, prefs=prefs, data_source=data_source)


#: The card's top-right chip. "+" = NOT IN YOUR LIBRARY -- a BADGE, not a
#: watchlist control and not a button; the action it foreshadows is Request,
#: which 7.9 puts on the detail screen. The CLOCK is the same badge once the
#: server is already getting the title. 16 calls both of them exact contracts
#: across the three platforms and says not to vary them; the app draws the
#: clock in the accent
#: on the same dark chip (atv-reference/discover-badges-plus-vs-clock.png).
PLUS_GLYPH = chr(icon_glyphs.PLUS)
CLOCK_GLYPH = chr(icon_glyphs.CLOCK)

#: RequestStatus values that mean "on its way". `denied` and `failed` are
#: deliberately absent: a clock over a request that is not coming is a lie,
#: and the plus is honest -- the title can be asked for again.
COMING_STATUSES = frozenset((
    "pending_approval", "requested", "downloading", "retrying", "available"))


def apply_library_badge(mli, item: dict, *, in_library: bool) -> None:
    """The top-right chip: nothing owned, a clock coming, a plus otherwise.

    `request_status` comes straight off the shelf item -- no second call, on
    the client's hottest loop. It is only trustworthy BECAUSE this runs on
    out-of-library items: measured against the live server 2026-08-08, a
    discovery page of 1209 items had 543 in-library items claiming
    "requested" (anything the *arr stack tracks reads that way, and an owned
    title is tracked by definition) but only 19 out-of-library ones, which
    were exactly the four titles actually on request or being fetched. So the
    field is noise above the `in_library` gate and precise below it.

    That also matches what the app shows: The Odyssey wears the clock while
    being merely tracked, with no request of ours behind it. The clock says
    "coming", not "you asked for this".

    `in_library` is the CALLER's, not `item["in_library"]`: Detail's More to
    Discover shelf decides it from whether the item has a local id at all.
    """
    status = str(item.get("request_status") or "").lower()
    coming = not in_library and status in COMING_STATUSES
    mli.setProperty("watchlisted", "1" if in_library else "")
    mli.setProperty(
        "watchlist_glyph",
        "" if in_library else (CLOCK_GLYPH if coming else PLUS_GLYPH))
    # Read by the chip's two glyph labels to pick white vs accent; see
    # skin/fragments.py:badge_glyph_labels().
    mli.setProperty("badge_requested", "1" if coming else "")
