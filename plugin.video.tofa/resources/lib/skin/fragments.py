# -*- coding: utf-8 -*-
"""Shared XML fragment builders: plain functions returning XML strings, no
template DSL. See resources/lib/skin/build.py for how these get spliced
into each screen's rendered file.

ONE THING HERE DOES NOT SURVIVE TO THE OUTPUT. Write a capsule the obvious
way -- `<texture border="30">capsule-h60.png</texture>` -- and keep writing
it that way; build.py's `_slice_pills()` rewrites every solid one into a
left cap, a stretched middle and a right cap (and every square one into a
single circle) on the way out. So the rendered XML will not match what you
wrote, on purpose: a 9-patch corner cannot be shipped at 4K resolution and
these pieces can. Outlined PILLS are left alone and still ship as 9-patches.

Nothing to do differently when adding a capsule. The note is here because
this is where you would look first when the output surprises you.
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple

from . import icon_glyphs
from . import tokens as T
from .. import settings_options
from .. import textmetrics


def logo_block() -> str:
    """The fox mark, top-left: app 2.0.0 dropped the "tofa" wordmark beside
    it. Inked 55x66 at (93, 35) on the capture; tofa-logo*.png has no
    transparent margin, so the control is the ink box."""
    return f"""        <control type="image">
            <posx>{T.NAV_MARK_X}</posx>
            <posy>{T.NAV_MARK_Y}</posy>
            <width>{T.NAV_MARK_W}</width>
            <height>{T.NAV_MARK_H}</height>
            <aspectratio>keep</aspectratio>
            <texture>$INFO[Window.Property(logo_file)]</texture>
            <animation effect="zoom" end="{T.NAV_MARK_COLLAPSED_ZOOM}" center="{T.NAV_MARK_X},{T.NAV_MARK_Y}" time="200" tween="cubic" easing="out" condition="{T.NAV_COLLAPSED}">Conditional</animation>
        </control>"""


# The tab list spans the bar in five equal slots, and each slot's drawing is
# shifted to its tab's measured spot: Kodi lists only know one item width.
_NAV_LIST_Y = 30
_NAV_SLOT = 360
_NAV_FOCUSED = "Control.HasFocus({list_id}) | !String.IsEmpty(Window.Property(nav_closing))"
_NAV_RESTING = "!Control.HasFocus({list_id}) + String.IsEmpty(Window.Property(nav_closing))"


def _nav_mark(x: int, w: int, y: int, h: int, texture: str, visible: str) -> str:
    """One accent mark (underline or dot) inside a tab's slot."""
    return f"""
                        <control type="image">
                            <posx>{x}</posx>
                            <posy>{y - _NAV_LIST_Y}</posy>
                            <width>{w}</width>
                            <height>{h}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture{texture}</texture>
                            <visible>{visible}</visible>
                        </control>"""


def _nav_slot(idx: int, *, focused: bool, list_id: int) -> str:
    """Everything tab `idx` draws, in item-relative coordinates.

    The focused layout is the SELECTED tab: underline while the bar has
    focus, a dot once focus has gone down into the page. Other tabs rest in
    half-white, except the current one, which stays white."""
    off = idx * _NAV_SLOT
    gate = f"String.IsEqual(ListItem.Property(nav_idx),{idx})"
    on = _NAV_FOCUSED.format(list_id=list_id)
    rest = _NAV_RESTING.format(list_id=list_id)
    current = "!String.IsEmpty(ListItem.Property(is_current))"
    if idx < len(T.NAV_TAB_INK):
        x, w = T.NAV_TAB_INK[idx][0] - off, T.NAV_TAB_INK[idx][1]
        centre = x + w // 2
        label_x = x - T.NAV_TAB_LSB[idx]
        white = "$INFO[Window.Property(text_primary)]"
        if focused:
            colours = ((white, ""),)
        else:
            colours = ((white, f"\n                            <visible>{current}</visible>"),
                       (T.NAV_TAB_REST, "\n                            <visible>"
                        "String.IsEmpty(ListItem.Property(is_current))</visible>"))
        body = "".join(f"""
                        <control type="label">
                            <posx>{label_x}</posx>
                            <posy>{T.NAV_TAB_LABEL_Y - _NAV_LIST_Y}</posy>
                            <width>{w + 20}</width>
                            <height>{T.NAV_TAB_LABEL_H}</height>
                            <font>tofa_font_nav_tab</font>
                            <textcolor>{colour}</textcolor>
                            <label>$INFO[ListItem.Label]</label>{vis}
                        </control>""" for colour, vis in colours)
        line_x, line_w = x - 1, w + 2
    else:
        # Settings, as a gear rather than a word.
        x = T.NAV_GEAR_X - off
        centre = x + T.NAV_GEAR_SIZE // 2
        body = f"""
                        <control type="label">
                            <posx>{x}</posx>
                            <posy>{T.NAV_GEAR_Y - _NAV_LIST_Y}</posy>
                            <width>{T.NAV_GEAR_SIZE}</width>
                            <height>{T.NAV_GEAR_SIZE}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_36</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Property(icon_glyph)]</label>
                        </control>"""
        line_w = T.NAV_ICON_UNDERLINE_W
        line_x = centre - line_w // 2
    dot_x = centre - T.NAV_DOT_SIZE // 2
    if focused:
        marks = (_nav_mark(line_x, line_w, T.NAV_UNDERLINE_Y, T.NAV_UNDERLINE_H,
                           f' border="{T.NAV_UNDERLINE_H // 2}">capsule-h{T.NAV_UNDERLINE_H}.png', on)
                 + _nav_mark(dot_x, T.NAV_DOT_SIZE, T.NAV_DOT_Y, T.NAV_DOT_SIZE, ">circle.png", rest))
    else:
        marks = _nav_mark(dot_x, T.NAV_DOT_SIZE, T.NAV_DOT_Y, T.NAV_DOT_SIZE, ">circle.png",
                          f"{rest} + {current}")
    return f"""
                    <control type="group">
                        <visible>{gate}</visible>{body}{marks}
                    </control>"""


def nav_bar(*, ondown_target: int, list_id: int = 3000, group_id: int = 2000,
            avatar_id: int = 3001) -> str:
    """The top bar's tabs and gear: one horizontal list, so Left/Right, focus
    memory and the section switch all keep working off a single control.
    Right from the gear goes to the avatar, which the template draws."""
    slots = len(T.NAV_TAB_INK) + 1
    item = "".join(_nav_slot(i, focused=False, list_id=list_id) for i in range(slots))
    sel = "".join(_nav_slot(i, focused=True, list_id=list_id) for i in range(slots))
    return f"""        <control type="group" id="{group_id}">
            {T.NAV_COLLAPSE_FADE}
            <control type="list" id="{list_id}">
                <posx>0</posx>
                <posy>{_NAV_LIST_Y}</posy>
                <width>{_NAV_SLOT * slots}</width>
                <height>80</height>
                <orientation>horizontal</orientation>
                <onleft>{list_id}</onleft>
                <onright>{avatar_id}</onright>
                <ondown>{ondown_target}</ondown>
                <itemlayout width="{_NAV_SLOT}" height="80">{item}
                </itemlayout>
                <focusedlayout width="{_NAV_SLOT}" height="80">{sel}
                </focusedlayout>
            </control>
        </control>"""


def nav_avatar_button(*, ondown_target: int, list_id: int = 3000) -> str:
    """The avatar's focus target and its underline; the template draws the
    art and ring underneath. Left goes back to the gear."""
    return f"""        <control type="image">
            <posx>{T.NAV_AVATAR_UNDERLINE_X}</posx>
            <posy>{T.NAV_UNDERLINE_Y}</posy>
            <width>{T.NAV_ICON_UNDERLINE_W}</width>
            <height>{T.NAV_UNDERLINE_H}</height>
            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
            <texture border="{T.NAV_UNDERLINE_H // 2}">capsule-h{T.NAV_UNDERLINE_H}.png</texture>
            <visible>Control.HasFocus({T.NAV_AVATAR_ID})</visible>
            {T.NAV_COLLAPSE_FADE}
        </control>
        <control type="button" id="{T.NAV_AVATAR_ID}">
            <posx>{T.NAV_AVATAR_X}</posx>
            <posy>{T.NAV_AVATAR_Y}</posy>
            <width>{T.NAV_AVATAR_SIZE}</width>
            <height>{T.NAV_AVATAR_SIZE}</height>
            <texturefocus>transparent-6px.png</texturefocus>
            <texturenofocus>transparent-6px.png</texturenofocus>
            <label></label>
            <onleft>{list_id}</onleft>
            <onright>{T.NAV_AVATAR_ID}</onright>
            <onup>{T.NAV_AVATAR_ID}</onup>
            <ondown>{ondown_target}</ondown>
        </control>"""


def rating_badge(zoom_anim: str = "", extra_visible: str = "") -> str:
    """Top-left rating pill: fill + outline + centered label. Fixed
    52x28/tofa_font_micro, used by every poster card. Carries a tofa score
    (0-100 integer), not a 0-10 one.

    Outline is badge-outline.png, a dedicated exact-size (52x28) asset
    with a thin 1px stroke, rather than the shared white-outline-rounded.png
    (border=4) which reads as too heavy at this size.

    `zoom_anim` is the focused copy's poster-matching zoom animation XML
    (empty for the unfocused copy): same center/start/end as the
    poster/border so the badge scales as a rigid unit with them instead of
    visibly lagging behind. `extra_visible` ANDs a further condition onto
    the group -- the focused copy passes !Control.HasFocus() so the badge
    clears out from under the focused card, matching the real app."""
    gate = "!String.IsEmpty(ListItem.Property(rating))"
    if extra_visible:
        gate = f"{gate} + {extra_visible}"
    return f"""                    <control type="group">
                        <visible>{gate}</visible>
                        <control type="image">
                            <posx>8</posx>
                            <posy>8</posy>
                            <width>52</width>
                            <height>28</height>
                            <colordiffuse>{T.BADGE_SCRIM}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                        </control>
                        <control type="image">
                            <posx>8</posx>
                            <posy>8</posy>
                            <width>52</width>
                            <height>28</height>
                            <colordiffuse>{T.BORDER}</colordiffuse>
                            <texture>badge-outline.png</texture>
                        </control>
                        <control type="label">
                            <posx>8</posx>
                            <posy>8</posy>
                            <width>52</width>
                            <height>28</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_micro</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Property(rating)]</label>
                        </control>{zoom_anim}
                    </control>"""


# Corner chips (rating badge, watchlist/plus chip) sit 8px in from the
# poster's edge and are 28 square. The x was hand-written as 212 back when
# POSTER_W was 248, and silently went 4px out of register the moment the
# card was resized -- derive it.
CHIP_SIZE = 28
CHIP_INSET = 8
CHIP_X = T.POSTER_W - CHIP_SIZE - CHIP_INSET


class PosterSize(NamedTuple):
    """A poster card's size and the exact-size art cut for it: Kodi scales a
    texture's corner and stroke with it, so each size has its own set."""
    w: int
    h: int
    mask: str
    border: str
    glow: str


POSTER_STD = PosterSize(T.POSTER_W, T.POSTER_H,
                        "poster-mask.png", "poster-border.png", "card-glow.png")
# The title page's shelves (app 2.0.0), on the Top Result's 220x330 art.
POSTER_COMPACT = PosterSize(T.DETAIL_P2_POSTER_W, T.DETAIL_P2_POSTER_H,
                            "top-result-mask.png", "top-result-border.png",
                            "top-result-glow.png")
# Browse's grid (app 2.0): seven columns of 212x318.
POSTER_GRID = PosterSize(T.GRID_POSTER_W, T.GRID_POSTER_H, "grid-poster-mask.png",
                         "grid-poster-border.png", "grid-poster-glow.png")


def poster_cell(size: PosterSize = POSTER_STD) -> tuple[int, int]:
    """(width, height) of a poster_card() cell at `size`."""
    return size.w + 2 * T.HPAD, T.CELL_H - T.POSTER_H + size.h


def badge_glyph_labels(x: int, y: int) -> str:
    """The card chip's glyph, drawn TWICE with opposite conditions.

    "+" (not in your library) is white; the requested CLOCK is accent-tinted
    -- the two states of one contract (16 calls both "exact three-platform,
    do not vary", measured on
    internal-docs/atv-reference/discover-badges-plus-vs-clock.png).

    Two labels rather than one with a per-item colour: the accent is a
    per-profile value behind a network cache, and resolving it once per CARD
    would put a settings/HTTP lookup on the card-build path, which is the
    hottest loop in this client (project_home_card_build_perf). A window
    property is resolved by the skin, for free, and every window that draws
    these cards already sets it.
    """
    return f"""                    <control type="label">
                        <posx>{x}</posx>
                        <posy>{y}</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Property(watchlist_glyph)]</label>
                        <visible>String.IsEmpty(ListItem.Property(badge_requested))</visible>
                    </control>
                    <control type="label">
                        <posx>{x}</posx>
                        <posy>{y}</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>$INFO[ListItem.Property(watchlist_glyph)]</label>
                        <visible>!String.IsEmpty(ListItem.Property(badge_requested))</visible>
                    </control>"""


def watchlist_badge_item(size: PosterSize = POSTER_STD) -> str:
    """Circular +/checkmark badge, top-right, Discover-only (its items
    aren't necessarily in the library yet, so need a way to add them).
    28x28, same 8px edge inset as the rating badge."""
    chip_x = size.w - CHIP_SIZE - CHIP_INSET
    return f"""                    <control type="image">
                        <posx>{chip_x}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
                    <control type="image">
                        <posx>{chip_x}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.BORDER_SOFT}</colordiffuse>
                        <texture border="14">capsule-h28-outline.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
{badge_glyph_labels(chip_x, 8)}
                    <control type="image">
                        <posx>{chip_x}</posx>
                        <posy>44</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(cinema_glyph))</visible>
                    </control>
                    <control type="label">
                        <posx>{chip_x}</posx>
                        <posy>44</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>{T.CINEMA_AMBER}</textcolor>
                        <label>$INFO[ListItem.Property(cinema_glyph)]</label>
                        <visible>!String.IsEmpty(ListItem.Property(cinema_glyph))</visible>
                    </control>"""


def watchlist_badge_focused(size: PosterSize = POSTER_STD) -> str:
    """The SAME badge as watchlist_badge_item(): dark chip, soft outline,
    white glyph. A focusedlayout needs its own copy of the markup, which is
    the only reason this exists separately.

    It used to accent-FILL while focused, "to signal it's actionable". The
    real Apple TV app doesn't: its chip is the same translucent dark circle
    with a white plus whether or not the card is selected (measured on
    internal-docs/atv-reference/detail-more-like-this.png). The other two
    variants here, watchlist_badge_item() and _wide, were already dark; this
    was the odd one out on both counts, because it ALSO set the glyph in
    tofa_font_poster_title, which has nothing at a Lucide codepoint -- so the
    selected card in every Discover-style row drew a notdef blob on a teal
    circle. Shared fragment, so Discover's own rows and Search's Discover
    shelf had it too."""
    chip_x = size.w - CHIP_SIZE - CHIP_INSET
    return f"""                    <control type="image">
                        <posx>{chip_x}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
                    <control type="image">
                        <posx>{chip_x}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.BORDER_SOFT}</colordiffuse>
                        <texture border="14">capsule-h28-outline.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
{badge_glyph_labels(chip_x, 8)}"""


HPAD, TOP_PAD = T.HPAD, T.TOP_PAD  # poster_visual()'s inset; see its docstring

# Poster-card progress bar height. Must equal gen_poster_assets.py's BAR_H:
# the strips are cut to exactly this, and each one's alpha is clipped to the
# poster's rounded bottom corners at this height, so a control of any other
# height would stretch that clip out of register with the corner.
#
# 6 is the top of 6's stated 3-6px range, and independently what the real
# Apple TV app measures. The episode card's bar follows THIS rather than
# 7.1's 4pt, so there is one bar height across the UI and both cards lose
# the same 2px to their focus border's bottom stroke. Keep
# gen_episode_assets.py's BAR_H in step too: its strips are clipped to ITS
# corners at this height.
_POSTER_BAR_H = 6
# Must match GLOW_PAD in tools/gen_poster_assets.py: person-glow-<N>.png
# bleeds this far outside a focused person tile's photo, and the tile's
# contents are shifted down by it so the halo has room inside the cell.
PERSON_GLOW_PAD = 10

# Must match GLOW_PAD in tools/gen_poster_assets.py: card-glow.png is drawn
# with exactly this much blurred bleed on all four sides, so the control
# that draws it has to be inflated by the same amount or the halo scales.
GLOW_PAD = 10


def format_badges(zoom_anim: str = "") -> str:
    """The 4K / DV / ATMOS pills stacked under the rating chip.

    Each pill is a FINISHED IMAGE, not a label on a scrim: Kodi cannot size a
    control to a list item's own text, so a box that fits "DTS-HD MA" would
    leave "DV" swimming in it. `aspectratio=keep` with `align=left` draws the
    pill at its true aspect against the box's left edge and leaves the rest
    transparent, so the visible pill is exactly as wide as its text from a
    fixed-size control. See tools/gen_badge_assets.py.

    Slots are POSITIONAL, like Detail's badge row: a title with no dynamic
    range simply has fewer, and nothing has to shuffle. The box is as wide as
    the widest pill (DTS-HD MA, 99 at 1080p) so none is ever squeezed.

    Not hidden on focus, unlike the rating chip on some lists -- the macOS app
    keeps them on the focused card.
    """
    def stack(top: int, gate: str) -> str:
        slots = []
        for index in range(T.CARD_BADGE_SLOTS):
            slots.append(f"""                            <control type="image">
                                <visible>!String.IsEmpty(ListItem.Property(badge_fmt_{index + 1}))</visible>
                                <posx>{T.CARD_BADGE_X}</posx>
                                <posy>{top + index * T.CARD_BADGE_PITCH}</posy>
                                <width>{T.CARD_BADGE_BOX_W}</width>
                                <height>{T.CARD_BADGE_H}</height>
                                <aspectratio align="left" aligny="center">keep</aspectratio>
                                <texture>$INFO[ListItem.Property(badge_fmt_{index + 1})]</texture>{zoom_anim}
                            </control>""")
        body = "\n".join(slots)
        return f"""                        <control type="group">
                            <visible>{gate}</visible>
{body}
                        </control>"""

    # TWO stacks, one gated on there being a rating chip above them and one
    # on there not being. A card with no score should not leave a hole where
    # the chip would have been -- the badges take its place.
    #
    # Two whole copies because Kodi cannot condition a <posy>: position is
    # fixed when the layout is parsed, and there is no animation that moves a
    # control based on a list item's own property. Same reason the seek toast
    # ships as two mirrored copies rather than one that moves.
    has_rating = "!String.IsEmpty(ListItem.Property(rating))"
    return (stack(T.CARD_BADGE_Y, has_rating) + "\n"
            + stack(T.CARD_BADGE_TOP_Y, "String.IsEmpty(ListItem.Property(rating))"))


def poster_placeholder(zoom_anim: str = "",
                       size: PosterSize = POSTER_STD) -> str:
    """The wash, mark and title an artwork-less card shows.

    ONE definition, used by BOTH copies poster_visual builds. The first pass
    edited only the unfocused one, so focusing an artwork-less card swapped it
    back to the old flat plate with no mark and no title -- exactly the
    card-fragment drift this family keeps producing.

    Follows the macOS app, a deliberate exception to Apple-TV-is-the-source:
    the TV apps leave the card EMPTY, Apple TV puts the title in as text, and
    macOS adds the mark too. The user chose macOS (2026-08-04).

    `zoom_anim` is the focused copy's poster-matching zoom, so the mark and
    title scale as one rigid unit with the card instead of sitting still while
    it grows.
    """
    # The mark and title keep their place on the card at any size.
    icon_y = round(T.POSTER_PLACEHOLDER_ICON_Y * size.h / T.POSTER_H)
    title_y = round(T.POSTER_PLACEHOLDER_TITLE_Y * size.h / T.POSTER_H)
    return f"""                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{size.w}</width>
                            <height>{size.h}</height>
                            <texture diffuse="{size.mask}">poster-placeholder.png</texture>{zoom_anim}
                        </control>
                        <control type="group">
                            <visible>String.IsEmpty(ListItem.Art(poster))</visible>
                            <control type="label">
                                <visible>String.IsEmpty(ListItem.Property(is_folder))</visible>
                                <posx>0</posx>
                                <posy>{icon_y}</posy>
                                <width>{size.w}</width>
                                <height>{T.POSTER_PLACEHOLDER_ICON_H}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_ICON_56}</font>
                                <textcolor>{T.POSTER_PLACEHOLDER_INK}</textcolor>
                                <label>&#x{icon_glyphs.FILM:04X};</label>{zoom_anim}
                            </control>
                            <control type="label">
                                <visible>!String.IsEmpty(ListItem.Property(is_folder))</visible>
                                <posx>0</posx>
                                <posy>{icon_y}</posy>
                                <width>{size.w}</width>
                                <height>{T.POSTER_PLACEHOLDER_ICON_H}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_ICON_56}</font>
                                <textcolor>{T.POSTER_PLACEHOLDER_INK}</textcolor>
                                <label>&#x{icon_glyphs.FOLDER:04X};</label>{zoom_anim}
                            </control>
                            <control type="label">
                                <posx>{T.POSTER_PLACEHOLDER_PAD}</posx>
                                <posy>{title_y}</posy>
                                <width>{size.w - T.POSTER_PLACEHOLDER_PAD * 2}</width>
                                <height>{T.POSTER_PLACEHOLDER_TITLE_H}</height>
                                <align>center</align>
                                <font>{T.FONT_METADATA}</font>
                                <textcolor>{T.POSTER_PLACEHOLDER_INK}</textcolor>
                                <label>$INFO[ListItem.Label]</label>{zoom_anim}
                            </control>
                        </control>"""


def poster_visual(
    list_id: int,
    *,
    has_progress: bool = False,
    extra_item_xml: str = "",
    extra_focused_xml: str = "",
    hide_rating_on_focus: bool = True,
    size: PosterSize = POSTER_STD,
) -> tuple[str, str]:
    """Returns (item_xml, focused_xml): just the poster's own visual block
    (placeholder tile, poster art, rating badge, optional progress bar,
    focus border, focus glow) as a single `<control type="group">...
    </control>`, already offset by (HPAD, TOP_PAD), with no outer
    <itemlayout>/<focusedlayout> tags and no caption. Factored out of
    poster_card() (below) so a caller with a differently-shaped cell
    (Search's Top Result, with text to the right of the poster instead of
    a caption below it) can reuse the exact same poster rendering instead
    of hand-copying it and letting the two drift apart. Any future
    differently-shaped poster cell should call this instead of copying
    poster_card()'s body.

    The group is offset by (HPAD, TOP_PAD) instead of sitting at the
    cell's own (0,0): room for the focus glow to bleed outward into,
    borrowed from slack already unused within the cell rather than
    growing its width (see gen_card_glow() in tools/gen_poster_assets.py).
    HPAD fits within the horizontal slack either side of the poster
    (CELL_W - POSTER_W). It only has to be >= GLOW_PAD, not equal to it:
    the glow is a uniform 10 on all four sides, and TOP_PAD is that 10."""
    # f-string, and it has to stay one: this was a plain quoted string, so
    # every poster card in the app shipped the placeholder text itself as its
    # zoom centre. Kodi cannot parse that, falls back to a centre of its own,
    # and the card's parts then scale about different points -- which is how
    # the progress bar came to slide out from under the focus border while
    # the poster and its border, being identical in size, still agreed.
    ZOOM = (f'center="{size.w // 2},{size.h // 2}" '
            'time="140" tween="cubic" easing="out"')
    # The rating badge stays on the FOCUSED card too. Apple TV clears it out
    # from under the focus on Browse/Home (verified in browse-full.png: the
    # focused "Mind Thief" has no chip while its neighbours show 51 and 53),
    # and 7.4's person grid keeps it. The macOS app keeps it everywhere.
    #
    # The two apps disagree, so this is a product call rather than a
    # measurement: the repo owner chose to SHOW it (2026-08-04), on the
    # grounds that a score is most wanted for the thing you are looking at.
    # See internal-docs/DIVERGENCES.md. hide_rating_on_focus is kept as a
    # parameter so the decision is one edit away from being reversed.
    _focus_gate = ""

    def _progress_block(zoom_anim: str) -> str:
        if not has_progress:
            return ""
        # The strips are cut to the standard card's width and corners.
        assert size == POSTER_STD, "progress strips exist at POSTER_STD only"
        return f"""
                    <!-- 6's progress bar: bottom-aligned INSIDE the poster,
                         touching its left, bottom and right edges, track
                         white 10% under a flat accent fill.

                         posy is computed, never typed. It was once the
                         literal 362, correct for the 248x372 poster of the
                         day; the card later grew to {size.w}x{size.h}
                         and left the bar floating 6px clear of the bottom,
                         with the corner clipping baked into each strip no
                         longer lining up with the corner it was cut for.

                         Both layers are one of 51 pre-rendered
                         poster-progress/<even-pct>.png strips; Kodi cannot
                         size a control from a list-item property, so the
                         percentage is which texture gets picked. The track
                         is simply the 100% strip in a different tint, which
                         is also what gives it the poster's corner curve for
                         free. Both carry the poster/border's exact zoom
                         animation, so the bar scales as a rigid part of the
                         card rather than sliding against it on focus. -->
                    <control type="image">
                        <visible>!String.IsEmpty(ListItem.Property(progress_pct))</visible>
                        <posx>0</posx>
                        <posy>{size.h - _POSTER_BAR_H}</posy>
                        <width>{size.w}</width>
                        <height>{_POSTER_BAR_H}</height>
                        <colordiffuse>{T.CARD_PROGRESS_TRACK}</colordiffuse>
                        <texture>poster-progress/100.png</texture>{zoom_anim}
                    </control>
                    <control type="image">
                        <visible>!String.IsEmpty(ListItem.Property(progress_pct))</visible>
                        <posx>0</posx>
                        <posy>{size.h - _POSTER_BAR_H}</posy>
                        <width>{size.w}</width>
                        <height>{_POSTER_BAR_H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>$INFO[ListItem.Property(progress_fill)]</texture>{zoom_anim}
                    </control>"""

    zoom_anim = f'\n                        <animation effect="zoom" start="100" end="104.5" {ZOOM}>Focus</animation>'

    progress_block = _progress_block("")
    progress_block_focused = _progress_block(zoom_anim)

    item = f"""                    <control type="group">
                        <posx>{HPAD}</posx>
                        <posy>{TOP_PAD}</posy>
{poster_placeholder(size=size)}
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{size.w}</width>
                            <height>{size.h}</height>
                            <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                            <texture diffuse="{size.mask}">$INFO[ListItem.Art(poster)]</texture>
                        </control>
{rating_badge()}
{format_badges()}{progress_block}
{extra_item_xml}                    </control>"""

    focused = f"""                    <control type="group">
                        <posx>{HPAD}</posx>
                        <posy>{TOP_PAD}</posy>
                        <!-- Accent focus glow drawn first (behind poster/
                             border), negative posx/posy so it bleeds into
                             the cell's unused slack (GLOW_PAD=10px, see
                             tools/gen_poster_assets.py:gen_card_glow()).
                             Poster/border painted on top cover the inward
                             half, leaving only the outward-fading edge
                             visible. -->
                        <control type="image">
                            <visible>Control.HasFocus({list_id})</visible>
                            <posx>-{GLOW_PAD}</posx>
                            <posy>-{GLOW_PAD}</posy>
                            <width>{size.w + 2 * GLOW_PAD}</width>
                            <height>{size.h + 2 * GLOW_PAD}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>{size.glow}</texture>
                            <!-- Centre is POSTER_W/2, matching the poster
                                 and border rather than this control's own
                                 width: an animation centre is expressed in
                                 the PARENT's coordinates, and this control
                                 starts at -10, so its true centre is
                                 -10 + (POSTER_W + 20)/2 = POSTER_W/2. Using
                                 its own half-width put the centre 10px down
                                 and right, which zoomed the halo about a
                                 different point than the card it wraps. -->
                            <animation effect="zoom" start="100" end="104.5" center="{size.w // 2},{size.h // 2}" time="140" tween="cubic" easing="out">Focus</animation>
                        </control>
                        <!-- The placeholder plate zooms with everything
                             else. It is what a card with no artwork has
                             INSTEAD of a poster, so if it alone stays at
                             100% while the glow, art and border grow to
                             104.5% it ends up ~5px inside the border, and
                             the glow's inward half (which the artwork is
                             supposed to cover) shows through as a teal
                             band between plate and border. Invisible on a
                             card that has art, since the art covers the
                             plate; the only cards it ever showed on were
                             the ones the plate exists for. -->
{poster_placeholder(zoom_anim, size)}
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{size.w}</width>
                            <height>{size.h}</height>
                            <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                            <texture diffuse="{size.mask}">$INFO[ListItem.Art(poster)]</texture>
                            <animation effect="zoom" start="100" end="104.5" center="{size.w // 2},{size.h // 2}" time="140" tween="cubic" easing="out">Focus</animation>
                        </control>
                        <!-- Gated on real container focus, not just
                             list-cursor position: focusedlayout otherwise
                             renders for the list's remembered selection
                             even while a different control holds actual
                             focus. -->
                        <control type="image">
                            <visible>Control.HasFocus({list_id})</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{size.w}</width>
                            <height>{size.h}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>{size.border}</texture>
                            <animation effect="zoom" start="100" end="104.5" center="{size.w // 2},{size.h // 2}" time="140" tween="cubic" easing="out">Focus</animation>
                        </control>
{rating_badge(zoom_anim, extra_visible=_focus_gate)}
{format_badges(zoom_anim)}{progress_block_focused}
{extra_focused_xml}                    </control>"""

    return item, focused


def poster_card(
    list_id: int,
    *,
    has_progress: bool,
    caption_field: str,
    extra_item_xml: str = "",
    extra_focused_xml: str = "",
    extra_bottom_pad: int = 0,
    hide_rating_on_focus: bool = True,
    size: PosterSize = POSTER_STD,
    cell_w: int | None = None,
) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for a CELL_W-wide poster
    card (poster POSTER_W x POSTER_H, rating badge, optional accent progress bar,
    meta+title captions), the one template every screen's poster grid/row
    uses. `caption_field` is "caption_meta" or "caption_year" (the two
    caption grammars observed across screens). `extra_item_xml` /
    `extra_focused_xml` let a caller splice in something screen-specific
    (e.g. Discover's watchlist badge) without this shared fragment needing
    to know about it. `extra_bottom_pad` grows the cell's bottom edge
    beyond its normal caption-sized height, for a caller whose outer
    list/panel control also wants a taller itemheight: Kodi's row-to-row
    advance follows the itemlayout's own declared height, not a
    separately-set outer <itemheight> tag.

    The poster's own visual block (mask/art/badge/progress/border/glow) is
    poster_visual() (above); this function just adds the meta+title
    caption underneath it and the outer <itemlayout>/<focusedlayout> cell.
    A caller needing a differently-shaped cell should call poster_visual()
    directly instead of copying this function's body.

    The cell's height grows beyond the poster+caption block, unlike its width:
    there's no equivalent free horizontal slack to borrow for the caption
    gap below the poster, so the extra 18px is pushed into every row's own
    spacing constants instead (each template's list posy / row-to-row
    offsets were bumped to match)."""
    # TITLE FIRST, then the metadata line. The other order shipped for a long
    # time; both the real app (captured 2026-07-31: "Big Brother" over "2000")
    # and TV-DESIGN.md SS6 ("title ... over metadata line") put the title on
    # top. Swapping the two lines leaves CELL_HEIGHT unchanged -- 34+4+24 is
    # the same block as 24+4+34 -- so no row geometry moves.
    # Derived from the tokens rather than restated. These five numbers also
    # add up to T.CELL_H, which every row list's height comes from, and they
    # were previously typed out again here -- so a change in one place moved
    # the captions while every list kept its old height, or the reverse.
    CAPTION_TITLE_TOP = TOP_PAD + size.h + T.CAPTION_GAP
    CAPTION_TITLE_HEIGHT = T.CAPTION_TITLE_H  # poster_title is 24pt; Kodi clips
    # item-layout content strictly to the cell, so a title with descenders
    # needs enough height not to have them cut off.
    CAPTION_TOP = CAPTION_TITLE_TOP + CAPTION_TITLE_HEIGHT + T.CAPTION_TITLE_GAP
    CELL_HEIGHT = CAPTION_TOP + T.CAPTION_META_H + T.CAPTION_BOTTOM + extra_bottom_pad
    # Every caption label's x and width, in one place. They were previously a
    # mix: the ITEM copy of the meta line derived its width from POSTER_W
    # while the FOCUSED copy of that same label, and both copies of the title,
    # typed the resulting 224 as a literal. Identical today, and exactly the
    # arrangement that let the progress bar's posy keep a stale 362 through a
    # card resize -- one copy of a control follows the token and its twin does
    # not, so a change to POSTER_W moves the unfocused caption and leaves the
    # focused one behind, visible only while a card is selected.
    CAPTION_X = 4 + HPAD
    # POSTER_W - 8, not - 28. CAPTION_X already encodes the deliberate 4px
    # inset from the art's left edge, and the right-aligned caption_trailing
    # label beside it has always used POSTER_W - 8, i.e. the SAME 4px inset on
    # the right. The title and the meta line stopped 20px short of that for no
    # recorded reason, so a Home card ellipsized 20px earlier than it needed
    # to and its right edge did not line up with the trailing "NN MIN LEFT".
    # Now all three captions share one column, 18..262 inside a 14..266 art.
    CAPTION_W = size.w - 8

    item_visual, focused_visual = poster_visual(
        list_id,
        has_progress=has_progress,
        extra_item_xml=extra_item_xml,
        extra_focused_xml=extra_focused_xml,
        hide_rating_on_focus=hide_rating_on_focus,
        size=size,
    )
    # A wider cell only widens the gap: the poster stays at HPAD.
    cell_w = cell_w or poster_cell(size)[0]

    # The meta line is TWO controls sharing one baseline, not one string.
    # 6 wants YEAR and NN MIN LEFT justified to opposite card edges on
    # Continue Watching -- confirmed in
    # internal-docs/atv-reference/home-full.png, where "2026" sits on the
    # art's left edge and "107 MIN LEFT" on its right, with NO separator
    # between them. A single joined string can only ever centre or hug one
    # side. Every other screen leaves caption_trailing empty and the right
    # control simply draws nothing, so this costs them one unused label.
    # Both widths DERIVE from POSTER_W rather than being typed: the trailing
    # one is wider so its right edge lands on the poster art's own right
    # edge, and the last time a caption number was left as a literal here it
    # kept its old value through a card resize and had to be found from a
    # screenshot.
    # The meta line does NOT change tier with focus, in either of its two
    # labels. It used to: text_tertiary at rest, text_secondary focused --
    # poster_card alone in the family, episode_card, collection_card and
    # person_card all sitting at text_secondary in both states.
    #
    # MEASURED on the reference captures rather than argued (same method as
    # theme.py's tier constants -- peak glyph alpha over the local
    # background):
    #
    #   browse-full.png   year, focused card      63.4%
    #                     year, three neighbours  63.7%
    #   home-full.png     year, focused CW card   63.4%
    #                     "107 MIN LEFT"          62.7%
    #
    # Flat 62-63% throughout, i.e. text_secondary, whether or not the card is
    # focused. The three other cards were right and this one was wrong. What
    # DOES brighten on focus is the TITLE, and separately -- see the note on
    # the title labels below.
    #
    # The TRAILING half is the exception, and follows the SPEC rather than the
    # measurement (Adrian's call, 2026-08-06). 6 sets Continue Watching's
    # metadata line in micro/uppercase at white 50%, with YEAR and the time
    # remaining pushed out to opposite card edges, and 3's type scale hands
    # a card caption of that kind the same micro role. So this label is
    # tofa_font_micro, not tofa_font_metadata -- a genuinely quieter treatment
    # than the year it shares a baseline with, which is the point of it.
    #
    # Two things the spec asks for that are NOT literal here:
    #   - UPPERCASE is already true by construction; progress.py's
    #     minutes_left_label() emits "116 MIN LEFT". No font casing needed.
    #   - white 50% has no tier. The tier scale is 100/62/42/24 and 50 is not
    #     on it (the spec contradicts its own 2 here), so rather than
    #     reintroduce a one-off alpha and a fourth Window.Property for a
    #     single label on a single row, this takes the nearest tier below,
    #     text_tertiary at 42%. The invariant that every textcolor in the app
    #     is one of three Window.Properties, with zero hex literals, is worth
    #     more than 8 percentage points on one caption.
    #
    # The spec treats the WHOLE CW metadata line as micro/50%, including the
    # year on the left. That half cannot follow: Home's rows are one
    # server-driven loop (see home_rows.py) and no row knows at render time
    # whether it is Continue Watching, so its caption is the shared one. Only
    # this trailing label is inherently CW-only -- nothing else ever fills
    # caption_trailing.
    #
    # KNOWN DIVERGENCE, measured before making the change: the real app does
    # NOT render this half smaller. In home-full.png "2026" and "107 MIN LEFT"
    # have cap heights of 26 and 25 px and share a baseline exactly (delta 0),
    # i.e. one size for the whole line. tofa_font_micro is 16 against
    # tofa_font_metadata's 23, so this ships at ~70% of the app's size. Taken
    # deliberately on the spec's authority (Adrian, 2026-08-06); reverting is
    # this one token.
    #
    # PUSHED DOWN so the two sizes share a baseline. Kodi TOP-aligns a label
    # by default and positions it by the font's ascent, so a 16pt line and a
    # 23pt line starting at the same posy do NOT sit on the same baseline --
    # the smaller one rides high by the difference of their ascents.
    #
    # TRAP: the obvious fix, <aligny>bottom</aligny>, does nothing. Kodi's
    # GUIControlFactory::GetAlignmentY only recognises "center"; every other
    # value, including "bottom", falls through to 0 = top. It parses, it
    # validates, it renders, and it is silently ignored -- this shipped that
    # way and read visibly high on screen. There is no bottom alignment for a
    # label; offset the control instead.
    #
    # The drop comes from the font, then from the screen. Inter Tight is 2048
    # upem with an hhea ascender of 1984, so ascent is 0.9688/em and
    # 0.9688 * (23 - 16) = 6.78 -- call it 7. Rendered and measured, 7 still
    # left the micro line exactly 1px high (ink bottoms at y=1049 against the
    # year's 1050, both hard cutoffs, no antialiasing tail), so the shipped
    # value is 8. Kodi rounds the scaled ascent somewhere this arithmetic
    # does not see; the measurement wins.
    #
    # Re-derive if either font's size moves in fontinstall.py -- both are
    # inter_tight_regular, so only the sizes matter -- and re-measure rather
    # than trusting the arithmetic.
    _MICRO_BASELINE_DROP = 8
    trailing = f"""
                    <control type="label">
                        <posx>{CAPTION_X}</posx>
                        <posy>{CAPTION_TOP + _MICRO_BASELINE_DROP}</posy>
                        <width>{size.w - 8}</width>
                        <height>{T.CAPTION_META_H + T.CAPTION_BOTTOM - _MICRO_BASELINE_DROP}</height>
                        <align>right</align>
                        <font>{T.FONT_MICRO}</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>$INFO[ListItem.Property(caption_trailing)]</label>
                    </control>"""

    item = f"""                <itemlayout width="{cell_w}" height="{CELL_HEIGHT}">
{item_visual}
                    <control type="label">
                        <posx>{CAPTION_X}</posx>
                        <posy>{CAPTION_TOP}</posy>
                        <width>{CAPTION_W}</width>
                        <height>{T.CAPTION_META_H}</height>
                        <font>tofa_font_metadata</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property({caption_field})]</label>
                    </control>{trailing}
                    <!-- Wrapped in a group so it is not a SIBLING of the
                         right-aligned caption_trailing label. Kodi shrinks a
                         list label to make room for a right-aligned one whose
                         box overlaps it in x, and it does not care that the
                         two sit on different rows: with "NN MIN LEFT"
                         present, this title was cut to 95px of its own 224
                         and ellipsized after about seven characters. Only
                         Continue Watching ever fills caption_trailing, which
                         is why only that row was affected. A group breaks
                         the sibling relationship and the title gets its
                         width back. -->
                    <control type="group">
                        <control type="label">
                            <posx>{CAPTION_X}</posx>
                            <posy>{CAPTION_TITLE_TOP}</posy>
                            <width>{CAPTION_W}</width>
                            <height>{CAPTION_TITLE_HEIGHT}</height>
                            <font>tofa_font_poster_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </control>
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{cell_w}" height="{CELL_HEIGHT}">
{focused_visual}
                    <control type="label">
                        <posx>{CAPTION_X}</posx>
                        <posy>{CAPTION_TOP}</posy>
                        <width>{CAPTION_W}</width>
                        <height>{T.CAPTION_META_H}</height>
                        <font>tofa_font_metadata</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property({caption_field})]</label>
                    </control>{trailing}
                    <!-- Wrapped in a group so it is not a SIBLING of the
                         right-aligned caption_trailing label. Kodi shrinks a
                         list label to make room for a right-aligned one whose
                         box overlaps it in x, and it does not care that the
                         two sit on different rows: with "NN MIN LEFT"
                         present, this title was cut to 95px of its own 224
                         and ellipsized after about seven characters. Only
                         Continue Watching ever fills caption_trailing, which
                         is why only that row was affected. A group breaks
                         the sibling relationship and the title gets its
                         width back. -->
                    <control type="group">
                        <!-- TWO COPIES WITH COMPLEMENTARY GATES, not one
                             control with <scroll>. focusedlayout renders for
                             a list's ACTIVE item even when the cursor is
                             somewhere else entirely, so an ungated marquee
                             scrolls forever in the background: on Home, the
                             first Continue Watching title marqueed while
                             focus was still up on the nav bar, before the
                             viewer had pressed anything. Kodi's <scroll> is
                             a plain boolean with no condition of its own,
                             which is why this is two controls. Same fix and
                             same reason as sidebar_row() and the settings
                             rows below.

                             A whole grid of scrolling titles would be
                             unreadable anyway; only the focused card is the
                             one being read.

                             scrollsuffix uses U+2003 (EM SPACE), not spaces:
                             Kodi strips ordinary whitespace from the suffix,
                             so a plain "   " gives a marquee whose end runs
                             straight into its own beginning with no gap.

                             A short title does not scroll at all: Kodi only
                             marquees a label whose text overruns its box.
                             Worth knowing before debugging this: two
                             "it does not work" observations here were both a
                             SHORT title being focused, not the markup. -->
                        <control type="label">
                            <visible>Control.HasFocus({list_id})</visible>
                            <posx>{CAPTION_X}</posx>
                            <posy>{CAPTION_TITLE_TOP}</posy>
                            <width>{CAPTION_W}</width>
                            <height>{CAPTION_TITLE_HEIGHT}</height>
                            <font>tofa_font_poster_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <scroll>true</scroll>
                            <scrollsuffix>\u2003\u2003\u2003</scrollsuffix>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>!Control.HasFocus({list_id})</visible>
                            <posx>{CAPTION_X}</posx>
                            <posy>{CAPTION_TITLE_TOP}</posy>
                            <width>{CAPTION_W}</width>
                            <height>{CAPTION_TITLE_HEIGHT}</height>
                            <font>tofa_font_poster_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </control>
                </focusedlayout>"""

    return item, focused


def top_result_card(list_id: int) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for Search's Top Result
    row: TOP_RESULT_CELL_W x TOP_RESULT_CELL_H, a BARE poster on the left and
    an eyebrow/title/meta/ratings/overview text block to its right.

    This does NOT call poster_visual(), and that is deliberate rather than the
    drift this module usually guards against. Two things genuinely differ,
    both measured on the live Apple TV app (2026-08-06):

    1. SIZE. 7.3 says "bare poster 220x330pt" and the app measures exactly
       that. The grid card is 252x378. Kodi scales a texture's corner radius
       and stroke with the texture, so the shared 252-wide mask/border drawn
       into a 220-wide control would render a 12.2px radius and a 1.7px
       stroke instead of 14 and 2 -- hence its own exact-size asset set (see
       gen_top_result_assets).
    2. BARE. The app draws no rating chip and no format badges here. Verified
       on a title that HAS scores: "Up" (Critics 93, Audience 82) shows
       neither on its Top Result poster, while every Movies card immediately
       below it carries its own. poster_visual() always draws both, because
       every grid card wants them. A hero is not a grid cell.

    The TEXT BLOCK IS VERTICALLY CENTRED on the poster, which is the layout's
    real signature and the thing we had most wrong (we top-aligned it, ~93px
    high). Measured: the app's block spans 416..681 against a poster spanning
    383..712 -- centres 548.5 and 547.5.

    Returns THREE parts: (itemlayout, focusedlayout, text_block). The layouts
    hold only the poster; the text is a STATIC block the template drops into
    group 6806 beside the list, driven by Window properties rather than
    ListItem ones.

    That split exists for one reason: `<wrapmultiline>` is ignored on a label
    inside a list ITEM layout (tested at 68 and 96 high, both ellipsised on
    one line -- see POSTER_PLACEHOLDER_TITLE_H's note in tokens.py). The app
    wraps the synopsis over three lines and we could only ever show one. As a
    static control it wraps. Nothing else about the block changed: it never
    varied with focus, so moving it out of the layouts costs no behaviour, and
    group 6806 already carries the has_top_result gate that hides it.

    KNOWN LIMIT: the app centres the lines ACTUALLY PRESENT. The block is
    positioned for the full five, so a title with no meta/ratings/overview (an
    artwork-less oddity like "Besenbinden") still sits high. Fixing that needs
    the builder to choose between pre-laid-out variants."""
    W, H = T.TOP_RESULT_POSTER_W, T.TOP_RESULT_POSTER_H
    PX, PY = T.TOP_RESULT_POSTER_X, T.TOP_RESULT_POSTER_Y
    CELL_W, CELL_H = T.TOP_RESULT_CELL_W, T.TOP_RESULT_CELL_H
    TEXT_X = T.TOP_RESULT_TEXT_X
    TEXT_W = T.TOP_RESULT_TEXT_W

    ZOOM = (f'\n                        <animation effect="zoom" start="100" '
            f'end="104.5" center="{PX + W // 2},{PY + H // 2}" time="140" '
            f'tween="cubic" easing="out">Focus</animation>')

    def _poster(anim: str) -> str:
        return f"""
                    <control type="image">
                        <posx>{PX}</posx>
                        <posy>{PY}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <texture diffuse="top-result-mask.png">poster-placeholder.png</texture>{anim}
                    </control>
                    <control type="group">
                        <visible>String.IsEmpty(ListItem.Art(poster))</visible>
                        <control type="label">
                            <posx>{PX}</posx>
                            <posy>{PY}</posy>
                            <width>{W}</width>
                            <height>{H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_56}</font>
                            <textcolor>{T.POSTER_PLACEHOLDER_INK}</textcolor>
                            <label>&#x{icon_glyphs.FILM:04X};</label>{anim}
                        </control>
                    </control>
                    <control type="image">
                        <posx>{PX}</posx>
                        <posy>{PY}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                        <texture diffuse="top-result-mask.png">$INFO[ListItem.Art(poster)]</texture>{anim}
                    </control>"""

    glow = f"""
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>{PX - GLOW_PAD}</posx>
                        <posy>{PY - GLOW_PAD}</posy>
                        <width>{W + 2 * GLOW_PAD}</width>
                        <height>{H + 2 * GLOW_PAD}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>top-result-glow.png</texture>{ZOOM}
                    </control>"""
    border = f"""
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>{PX}</posx>
                        <posy>{PY}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>top-result-border.png</texture>{ZOOM}
                    </control>"""

    # The y ladder, as a running stack rather than five typed offsets, then
    # shifted bodily so the block's centre lands on the poster's. Line slots
    # come from the app: eyebrow top +0, title +41, meta +108, ratings +150,
    # overview +191 with a 27.5 line pitch over 3 lines.
    EYEBROW_H, TITLE_H, META_H, RATINGS_H = 22, 52, 30, 30
    OVERVIEW_H = 84
    _EYEBROW, _TITLE, _META, _RATINGS, _OVERVIEW = 0, 41, 108, 150, 191
    # Centre on the block's INK, not on its boxes. The overview's control is
    # 84 tall so three wrapped lines cannot clip, but its ink is 3 x 27.5 =
    # 74, and centring the taller box pushed the whole stack 6px up against
    # the app. The app's own numbers say the same thing: its ink runs
    # 416..681 = 265 inside a 330 poster, and (330 - 265) / 2 = 32.5 is
    # exactly the 33 between its poster top (383) and its first line (416).
    OVERVIEW_INK_H = 74
    BLOCK_INK_H = _OVERVIEW + OVERVIEW_INK_H
    TOP = PY + (H - BLOCK_INK_H) // 2
    EYEBROW_Y = TOP + _EYEBROW
    TITLE_Y = TOP + _TITLE
    META_Y = TOP + _META
    RATINGS_Y = TOP + _RATINGS
    OVERVIEW_Y = TOP + _OVERVIEW

    # Colours measured on the same frame: eyebrow 47% (tertiary, 42 -- and
    # NOT 7.3's stated accent, which the app does not do), title 100%,
    # overview 60% (secondary). The meta line measures 86%, which is not on
    # the tier scale at all; it stays secondary rather than reintroduce a
    # one-off alpha for one label.
    TEXT_BLOCK = f"""                    <control type="label">
                        <posx>{TEXT_X}</posx>
                        <posy>{EYEBROW_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>{EYEBROW_H}</height>
                        <font>{T.FONT_TOP_RESULT_EYEBROW}</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>TOP RESULT</label>
                    </control>
                    <control type="label">
                        <posx>{TEXT_X}</posx>
                        <posy>{TITLE_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>{TITLE_H}</height>
                        <font>{T.FONT_TOP_RESULT_TITLE}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(top_result_title)]</label>
                    </control>
                    <control type="label">
                        <posx>{TEXT_X}</posx>
                        <posy>{META_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>{META_H}</height>
                        <font>tofa_font_body</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(top_result_meta)]</label>
                    </control>
                    <control type="label">
                        <posx>{TEXT_X}</posx>
                        <posy>{RATINGS_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>{RATINGS_H}</height>
                        <font>tofa_font_body</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(top_result_ratings)]</label>
                    </control>
                    <control type="label">
                        <posx>{TEXT_X}</posx>
                        <posy>{OVERVIEW_Y}</posy>
                        <width>{T.TOP_RESULT_OVERVIEW_W}</width>
                        <height>{OVERVIEW_H}</height>
                        <font>tofa_font_body</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <wrapmultiline>true</wrapmultiline>
                        <label>$INFO[Window.Property(top_result_overview)]</label>
                    </control>"""

    item = f"""                <itemlayout width="{CELL_W}" height="{CELL_H}">
{_poster("")}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{CELL_W}" height="{CELL_H}">
{glow}
{_poster(ZOOM)}
{border}
                </focusedlayout>"""
    return item, focused, TEXT_BLOCK


def person_card(
    list_id: int,
    *,
    cell_width: int,
    cell_height: int,
    photo_size: int,
    placeholder_mode: str = "initials",
    subtitle_property: str = "role",
) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for a circular person
    card (photo + name + role/job subtitle), used by Detail's Cast & Crew
    grid.

    The defaults describe Detail's Cast & Crew tile, the larger of the two
    sizes this renders at. They used to be 290/272/140 -- a cell height and a
    photo size no caller passed and no asset was authored at, left over from
    before the tile was measured. Every caller overrides what it needs; the
    defaults now at least name a real card.

    `subtitle_property`: the ListItem property under the name -- "role" for
    Cast & Crew, "titles_label" ("2 titles") for Search's Actors row. The
    only thing that genuinely differs between the two screens; everything
    else is the same card and now renders from this one fragment.

    `placeholder_mode`: "initials" (Detail's convention: renders
    ListItem.Property(initials) text) or "icon" (Search's Actors-row
    convention: a generic person glyph, icon_glyphs.USER_ROUND). Not
    standardized on one value because both conventions are already
    shipped and it's unclear which the real app uses for an unphotographed
    cast/crew member on this screen specifically.

    TYPE comes from the spec, which is unusually explicit here: the name in
    row-title white, the character or role beneath it in metadata at white
    62%, both centred. So the name is tofa_font_row_title at text_primary --
    which is what it always was -- and the role is tofa_font_metadata at
    text_secondary. The role used to be tofa_font_poster_title, i.e. the font
    every OTHER card in the family sets its TITLE in, which made a supporting
    role line as heavy as a poster's name (semibold 24 against metadata's
    regular 23 -- the weight was the visible half of it, not the point).

    aspectratio must be `scale` WITH `scalediffuse="false"`: plain `scale`
    distorts the circular mask along with the photo (Kodi scales `diffuse`
    by the same transform as the main texture unless told not to);
    `scalediffuse="false"` keeps the mask a true circle while the photo
    still cover-crops correctly."""
    if placeholder_mode not in ("initials", "icon"):
        raise ValueError("placeholder_mode must be 'initials' or 'icon'")

    photo_x = (cell_width - photo_size) // 2
    # The whole photo block sits PERSON_GLOW_PAD down the cell so the focus
    # halo has somewhere to bleed. Same borrowed-slack trick poster_card()
    # uses: a Kodi list clips each item strictly to its cell, so a glow drawn
    # above posy 0 would simply not render. The cell has the room -- photo +
    # name + role leaves ~32px spare -- so nothing below moves.
    photo_y = PERSON_GLOW_PAD
    name_y = photo_y + photo_size + 10
    role_y = name_y + 34
    zoom_center = "{0},{1}".format(
        photo_x + photo_size // 2, photo_y + photo_size // 2)
    # The accent ring sits ON the photo's edge, exactly as a focused
    # poster's border sits on the poster. It used to be drawn on a box 10px
    # larger, which floated it 5px out into the halo band with a visible gap
    # of background between picture and rim -- a loose hoop around the tile
    # rather than the tile being focused.
    #
    # person-border-<photo_size>.png is authored at exactly this size (see
    # gen_person_border), which is also what pins its stroke to the same 2px
    # a focused poster gets: Kodi scales a texture's stroke with the
    # texture, so a ring drawn at any other size would thin or thicken.
    #
    # PER SIZE, hence the name. There was one 190px person-border.png and
    # Search's Actors row drew it into a 130px control, rendering its 2px
    # stroke at 1.4 and squeezing the halo's 10px fade band into 7 -- a
    # finer ring and a hard accent collar that Detail's cast did not have.
    # A new caller at a new photo_size needs a new pair from
    # tools/gen_poster_assets.py (add it to PERSON_PHOTOS); it will show up
    # as a missing texture rather than a silently rescaled one.
    rim_size = photo_size
    rim_x, rim_y = photo_x, photo_y
    rim_texture = f"person-border-{photo_size}.png"
    glow_texture = f"person-glow-{photo_size}.png"
    glow_size = photo_size + PERSON_GLOW_PAD * 2

    if placeholder_mode == "initials":
        placeholder_item = f"""                            <control type="label">
                                <posx>{photo_x}</posx>
                                <posy>{photo_y}</posy>
                                <width>{photo_size}</width>
                                <height>{photo_size}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_heading</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>$INFO[ListItem.Property(initials)]</label>
                                <visible>String.IsEmpty(ListItem.Property(has_photo))</visible>
                            </control>"""
        placeholder_focused = f"""                            <control type="label">
                                <posx>{photo_x}</posx>
                                <posy>{photo_y}</posy>
                                <width>{photo_size}</width>
                                <height>{photo_size}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_heading</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>$INFO[ListItem.Property(initials)]</label>
                                <visible>String.IsEmpty(ListItem.Property(has_photo))</visible>
                            </control>"""
    else:
        placeholder_item = f"""                            <control type="label">
                                <posx>{photo_x}</posx>
                                <posy>{photo_y}</posy>
                                <width>{photo_size}</width>
                                <height>{photo_size}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_56</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>&#xE468;</label>
                                <visible>String.IsEmpty(ListItem.Property(has_photo))</visible>
                            </control>"""
        placeholder_focused = f"""                            <control type="label">
                                <posx>{photo_x}</posx>
                                <posy>{photo_y}</posy>
                                <width>{photo_size}</width>
                                <height>{photo_size}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_56</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>&#xE468;</label>
                                <visible>String.IsEmpty(ListItem.Property(has_photo))</visible>
                            </control>"""

    item = f"""                <itemlayout width="{cell_width}" height="{cell_height}">
                    <!-- glass disc backing (fallback + monogram bg) -->
                    <control type="image">
                        <posx>{photo_x}</posx>
                        <posy>{photo_y}</posy>
                        <width>{photo_size}</width>
                        <height>{photo_size}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture>circle.png</texture>
                    </control>
{placeholder_item}
                    <control type="image">
                        <posx>{photo_x}</posx>
                        <posy>{photo_y}</posy>
                        <width>{photo_size}</width>
                        <height>{photo_size}</height>
                        <aspectratio scalediffuse="false" align="center" aligny="center">scale</aspectratio>
                        <texture diffuse="circle.png">$INFO[ListItem.Art(poster)]</texture>
                        <visible>!String.IsEmpty(ListItem.Property(has_photo))</visible>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>{name_y}</posy>
                        <width>{cell_width}</width>
                        <height>26</height>
                        <align>center</align>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>{role_y}</posy>
                        <width>{cell_width}</width>
                        <height>24</height>
                        <align>center</align>
                        <font>{T.FONT_METADATA}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property({subtitle_property})]</label>
                    </control>
                </itemlayout>"""

    # The halo and rim are gated on the CONTAINER having focus, not just on
    # this being the focused layout. Kodi draws the focusedlayout for a
    # list's selected item whether or not the list itself is focused, so
    # without this the first actor/cast member sat permanently ringed while
    # the viewer was somewhere else entirely. Same gate poster_visual() and
    # episode_card() already use.
    focused = f"""                <focusedlayout width="{cell_width}" height="{cell_height}">
                    <!-- Accent focus halo, drawn first so the photo and rim
                         cover its inward half and only the outward fade
                         shows. Circular sibling of poster_visual()'s
                         card-glow.png; see gen_person_glow(). -->
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>{photo_x - PERSON_GLOW_PAD}</posx>
                        <posy>0</posy>
                        <width>{glow_size}</width>
                        <height>{glow_size}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>{glow_texture}</texture>
                        <animation effect="zoom" start="100" end="104.5" center="{zoom_center}" time="140" tween="cubic" easing="out">Focus</animation>
                    </control>
                    <control type="image">
                        <posx>{photo_x}</posx>
                        <posy>{photo_y}</posy>
                        <width>{photo_size}</width>
                        <height>{photo_size}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture>circle.png</texture>
                        <animation effect="zoom" start="100" end="104.5" center="{zoom_center}" time="140" tween="cubic" easing="out">Focus</animation>
                    </control>
{placeholder_focused}
                    <control type="image">
                        <posx>{photo_x}</posx>
                        <posy>{photo_y}</posy>
                        <width>{photo_size}</width>
                        <height>{photo_size}</height>
                        <aspectratio scalediffuse="false" align="center" aligny="center">scale</aspectratio>
                        <texture diffuse="circle.png">$INFO[ListItem.Art(poster)]</texture>
                        <visible>!String.IsEmpty(ListItem.Property(has_photo))</visible>
                        <animation effect="zoom" start="100" end="104.5" center="{zoom_center}" time="140" tween="cubic" easing="out">Focus</animation>
                    </control>
                    <!-- 2px accent rim on focus, just outside the photo -->
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>{rim_x}</posx>
                        <posy>{rim_y}</posy>
                        <width>{rim_size}</width>
                        <height>{rim_size}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>{rim_texture}</texture>
                        <animation effect="zoom" start="100" end="104.5" center="{zoom_center}" time="140" tween="cubic" easing="out">Focus</animation>
                    </control>
                    <!-- TWO COPIES WITH COMPLEMENTARY GATES, not one
                         control with <scroll>. Same technique, same reason
                         and same suffix as poster_card()'s title;
                         focusedlayout renders for the grid's ACTIVE cell
                         even when the cursor is off on the tab bar, and
                         Kodi's <scroll> carries no condition of its own.

                         Measured before adding: at 26px semibold a full
                         name overruns this box rarely on Detail (290px)
                         and readily on Search's Actors row (256px);
                         "Jean-Claude Van Damme" is 300px, "Arnold
                         Schwarzenegger" 284. Rare is the point: those are
                         precisely the names that were being ellipsized,
                         and a name that fits does not scroll at all.

                         Centring is safe next to <scroll>: a label that
                         overruns has no slack left to centre within, so
                         the two never apply at once. Same note as
                         _action_pill_label(). -->
                    <control type="label">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>{name_y}</posy>
                        <width>{cell_width}</width>
                        <height>26</height>
                        <align>center</align>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <scroll>true</scroll>
                        <scrollsuffix>\u2003\u2003\u2003</scrollsuffix>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>!Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>{name_y}</posy>
                        <width>{cell_width}</width>
                        <height>26</height>
                        <align>center</align>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>{role_y}</posy>
                        <width>{cell_width}</width>
                        <height>24</height>
                        <align>center</align>
                        <font>{T.FONT_METADATA}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property({subtitle_property})]</label>
                    </control>
                </focusedlayout>"""

    return item, focused


EPISODE_CELL_W, EPISODE_CELL_H = T.EPISODE_CELL_W, T.EPISODE_CELL_H
# 320, not 270: row-to-row gap widened to match Browse's own poster grid
# (~124px between poster rows on the real Apple TV app); ~134px art-to-art
# here once _EP_PAD is factored in.
EPISODE_THUMB_W, EPISODE_THUMB_H = 400, 225
# The 28px gap between stills is split either side of each, room for the
# 10px glow (tools/gen_episode_assets.py).
_EP_PAD = 14


def episode_card(list_id: int) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for a 16:9 episode
    thumbnail card, Detail's Episodes tab grid. Same technique as
    poster_visual() (exact-size mask/border/glow assets rather than a
    stretched 9-slice, see tools/gen_episode_assets.py), adapted for a
    landscape 330x186 still instead of a portrait poster.

    ListItem properties consumed: Art(thumb), Property(has_thumb),
    Property(caption), Property(watched), Property(unaired),
    Property(nil_badge), Property(nil_glyph), Property(spoiler), Label
    (title)."""
    zoom_center = "{0},{1}".format(EPISODE_THUMB_W // 2, EPISODE_THUMB_H // 2)
    zoom_anim = (
        '\n                            <animation effect="zoom" start="100" end="104.5" '
        f'center="{zoom_center}" time="140" tween="cubic" easing="out">Focus</animation>'
    )

    caption_y = _EP_PAD + EPISODE_THUMB_H + 12
    title_y = caption_y + 24

    # 7.1's overlays on the still. All three are gated on a ListItem
    # property so an ordinary, fully-available, already-reachable episode
    # draws none of them.
    #
    # Progress capsule, the same height as the poster card's bar and sitting
    # FLUSH with the still's left, bottom and right edges -- the same treatment the poster card gets, and a
    # deliberate divergence from 7.1's 6px side / 5px bottom inset. The
    # shipped Apple TV app insets it here and not on poster cards; that
    # inconsistency is not worth reproducing.
    #
    # Flush means the bar reaches the rounded corners, so it can no longer be
    # a stretched white-square.png -- it uses episode-progress/<even-pct>.png
    # strips clipped to this card's own silhouette, exactly like the poster's.
    # The track is the 100% strip in a different tint, which is what gives it
    # the same corner curve without a second asset.
    #
    # Unaired badge sits top-LEADING, opposite the watched check's
    # top-trailing, so an episode can carry both without them colliding.
    # Coordinates here are relative to the group these overlays live in,
    # which is ALREADY offset by _EP_PAD and holds the still at its own
    # (0,0). Adding _EP_PAD again put the bar a full pad BELOW the still,
    # out on the caption -- which is what it had been doing.
    _PROG_H = _POSTER_BAR_H
    # The two corner overlays, both inset CHIP_INSET from the still's edge --
    # the same inset the poster card's rating and watchlist chips take from
    # the poster's. The unaired badge used to sit at 10 from the LEFT while
    # the watched check sat at 8 from the RIGHT, so an episode carrying both
    # had them 2px out of register with each other and with every chip on
    # every other card. Nothing here derived from anything; the three numbers
    # were separate literals and one of them, _BADGE_X, was being used as a
    # posy as well.
    #
    # The badges are different HEIGHTS (24 vs 28) and share a centre line
    # rather than a top edge, which is why the shorter one's y is not simply
    # CHIP_INSET. That relationship is now computed. It was previously true
    # only by coincidence of two hand-picked numbers, so any change to either
    # height would have quietly broken it.
    _WATCHED_SIZE = CHIP_SIZE
    _BADGE_H, _BADGE_W = 24, 118
    _BADGE_X = CHIP_INSET
    _WATCHED_Y = CHIP_INSET
    _BADGE_Y = _WATCHED_Y + (_WATCHED_SIZE - _BADGE_H) // 2
    _WATCHED_X = EPISODE_THUMB_W - CHIP_INSET - _WATCHED_SIZE
    _PROG_Y = EPISODE_THUMB_H - _PROG_H
    # "Not in library": the Apple TV app's pill for an episode you never had,
    # books glyph then words, top-leading where the unaired badge sits (the
    # two never show together -- detail.py hands a no-files episode to this
    # one). Sized off the app, not off our unaired badge: measured ~182x33 on
    # a card the same width as ours (332 there, 330 here), its words ~116
    # wide. Ours: the metadata font puts "Not in library" at 124px (Inter
    # Tight 23, measured), in a 180x34 capsule -- 10 pad, a 26 glyph box at
    # the 24 icon size, 6, a 126 box for the words, 12 pad.
    _NIL_W, _NIL_H = 180, 34
    _NIL_X = _NIL_Y = CHIP_INSET
    _NIL_GLYPH_X = _NIL_X + 10
    _NIL_TEXT_X = _NIL_GLYPH_X + 26 + 6

    def _overlays(anim: str) -> str:
        return f"""
                        <!-- An episode not in the library sits on the SERIES
                             backdrop, dimmed, as the Apple TV app draws it;
                             dimmed so it reads as unavailable at a glance and
                             the pill stays legible over bright key art. -->
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(nil_badge))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <colordiffuse>{T.BADGE_SCRIM_SOFT}</colordiffuse>
                            <texture diffuse="episode-mask.png">white-square.png</texture>{anim}
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(progress_fill))</visible>
                            <posx>0</posx>
                            <posy>{_PROG_Y}</posy>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{_PROG_H}</height>
                            <colordiffuse>{T.CARD_PROGRESS_TRACK}</colordiffuse>
                            <texture>episode-progress/100.png</texture>{anim}
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(progress_fill))</visible>
                            <posx>0</posx>
                            <posy>{_PROG_Y}</posy>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{_PROG_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>$INFO[ListItem.Property(progress_fill)]</texture>{anim}
                        </control>
                        <!-- 7.1's unaired badge: accent text in a dark
                             capsule, top-LEADING (opposite the watched
                             check's top-trailing, so an episode can carry
                             both). The capsule is not decoration now that
                             these cards fall back to season art: teal on a
                             sunlit desert is unreadable without it.

                             Fixed width, because Kodi cannot size a control
                             to a list item's text. It costs little here: the
                             labels are all 10-11 characters ("Airs Sep 13",
                             "Unavailable"), and the one outlier that sets
                             this width is "Airs tomorrow" at 97px. -->
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(unaired))</visible>
                            <posx>{_BADGE_X}</posx>
                            <posy>{_BADGE_Y}</posy>
                            <width>{_BADGE_W}</width>
                            <height>{_BADGE_H}</height>
                            <colordiffuse>{T.BADGE_SCRIM_SOFT}</colordiffuse>
                            <texture border="{_BADGE_H // 2}">capsule-h{_BADGE_H}.png</texture>{anim}
                        </control>
                        <control type="label">
                            <visible>!String.IsEmpty(ListItem.Property(unaired))</visible>
                            <posx>{_BADGE_X}</posx>
                            <posy>{_BADGE_Y}</posy>
                            <width>{_BADGE_W}</width>
                            <height>{_BADGE_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_MICRO}</font>
                            <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                            <label>$INFO[ListItem.Property(unaired)]</label>{anim}
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(nil_badge))</visible>
                            <posx>{_NIL_X}</posx>
                            <posy>{_NIL_Y}</posy>
                            <width>{_NIL_W}</width>
                            <height>{_NIL_H}</height>
                            <colordiffuse>{T.BADGE_SCRIM_SOFT}</colordiffuse>
                            <texture border="{_NIL_H // 2}">capsule-h{_NIL_H}.png</texture>{anim}
                        </control>
                        <control type="label">
                            <visible>!String.IsEmpty(ListItem.Property(nil_badge))</visible>
                            <posx>{_NIL_GLYPH_X}</posx>
                            <posy>{_NIL_Y}</posy>
                            <width>26</width>
                            <height>{_NIL_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_24</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(nil_glyph)]</label>{anim}
                        </control>
                        <control type="label">
                            <visible>!String.IsEmpty(ListItem.Property(nil_badge))</visible>
                            <posx>{_NIL_TEXT_X}</posx>
                            <posy>{_NIL_Y}</posy>
                            <width>{_NIL_X + _NIL_W - 12 - _NIL_TEXT_X}</width>
                            <height>{_NIL_H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(nil_badge)]</label>{anim}
                        </control>
                        <control type="label">
                            <visible>!String.IsEmpty(ListItem.Property(spoiler))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>Details hidden</label>{anim}
                        </control>"""

    def _watched_badge(anim: str) -> str:
        return f"""
                        <control type="image">
                            <visible>String.IsEqual(ListItem.Property(watched),1)</visible>
                            <posx>{_WATCHED_X}</posx>
                            <posy>{_WATCHED_Y}</posy>
                            <width>{_WATCHED_SIZE}</width>
                            <height>{_WATCHED_SIZE}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>circle.png</texture>{anim}
                        </control>
                        <control type="label">
                            <visible>String.IsEqual(ListItem.Property(watched),1)</visible>
                            <posx>{_WATCHED_X}</posx>
                            <posy>{_WATCHED_Y}</posy>
                            <width>{_WATCHED_SIZE}</width>
                            <height>{_WATCHED_SIZE}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_19</font>
                            <textcolor>$INFO[Window.Property(on_accent_color)]</textcolor>
                            <label>&#xE06C;</label>{anim}
                        </control>"""

    item = f"""                <itemlayout width="{EPISODE_CELL_W}" height="{EPISODE_CELL_H}">
                    <control type="group">
                        <posx>{_EP_PAD}</posx>
                        <posy>{_EP_PAD}</posy>
                        <!-- Muted placeholder tile (no still art) + real
                             still art, both masked to the same rounded
                             corner as a focused card so an unfocused one
                             doesn't visibly "square up". -->
                        <control type="image">
                            <visible>String.IsEmpty(ListItem.Property(has_thumb))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <colordiffuse>{T.SURFACE_PLACEHOLDER}</colordiffuse>
                            <texture diffuse="episode-mask.png">white-square.png</texture>
                        </control>
                        <control type="label">
                            <visible>String.IsEmpty(ListItem.Property(has_thumb)) + String.IsEmpty(ListItem.Property(spoiler))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_36</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>&#xE0D0;</label>
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(has_thumb))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <!-- scale, not keep: an unaired episode falls back
                                 to the SEASON POSTER (see detail.py), and a 2:3
                                 poster under `keep` would pillarbox inside this
                                 16:9 tile instead of filling it. scale fills and
                                 centre-crops, which is what the real app does.
                                 A real 16:9 still is unaffected either way.
                                 scalediffuse=false because scale otherwise
                                 maps the rounded-corner MASK onto the SCALED
                                 texture, so its corners land outside the
                                 cropped band and the card renders square. It
                                 is an attribute of <aspectratio>, not of
                                 <texture>; on the wrong element Kodi simply
                                 ignores it. Same trap the avatars hit. -->
                            <aspectratio scalediffuse="false" align="center" aligny="center">scale</aspectratio>
                            <texture diffuse="episode-mask.png">$INFO[ListItem.Art(thumb)]</texture>
                        </control>{_watched_badge("")}{_overlays("")}
                    </control>
                    <control type="label">
                        <posx>{_EP_PAD}</posx>
                        <posy>{caption_y}</posy>
                        <width>{EPISODE_THUMB_W}</width>
                        <height>20</height>
                        <font>tofa_font_micro</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property(caption)]</label>
                    </control>
                    <control type="label">
                        <posx>{_EP_PAD}</posx>
                        <posy>{title_y}</posy>
                        <width>{EPISODE_THUMB_W}</width>
                        <height>28</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{EPISODE_CELL_W}" height="{EPISODE_CELL_H}">
                    <!-- Same glow technique as poster_visual()'s
                         card-glow.png, sized for this card's 330x186
                         shape. -->
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{EPISODE_THUMB_W + _EP_PAD * 2}</width>
                        <height>{EPISODE_THUMB_H + _EP_PAD * 2}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>episode-glow.png</texture>
                        <animation effect="zoom" start="100" end="104.5" center="{_EP_PAD + EPISODE_THUMB_W // 2},{_EP_PAD + EPISODE_THUMB_H // 2}" time="140" tween="cubic" easing="out">Focus</animation>
                    </control>
                    <control type="group">
                        <posx>{_EP_PAD}</posx>
                        <posy>{_EP_PAD}</posy>
                        <control type="image">
                            <visible>String.IsEmpty(ListItem.Property(has_thumb))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <colordiffuse>{T.SURFACE_PLACEHOLDER}</colordiffuse>
                            <texture diffuse="episode-mask.png">white-square.png</texture>{zoom_anim}
                        </control>
                        <control type="label">
                            <visible>String.IsEmpty(ListItem.Property(has_thumb)) + String.IsEmpty(ListItem.Property(spoiler))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_36</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>&#xE0D0;</label>{zoom_anim}
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(has_thumb))</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <!-- scale, not keep: an unaired episode falls back
                                 to the SEASON POSTER (see detail.py), and a 2:3
                                 poster under `keep` would pillarbox inside this
                                 16:9 tile instead of filling it. scale fills and
                                 centre-crops, which is what the real app does.
                                 A real 16:9 still is unaffected either way.
                                 scalediffuse=false because scale otherwise
                                 maps the rounded-corner MASK onto the SCALED
                                 texture, so its corners land outside the
                                 cropped band and the card renders square. It
                                 is an attribute of <aspectratio>, not of
                                 <texture>; on the wrong element Kodi simply
                                 ignores it. Same trap the avatars hit. -->
                            <aspectratio scalediffuse="false" align="center" aligny="center">scale</aspectratio>
                            <texture diffuse="episode-mask.png">$INFO[ListItem.Art(thumb)]</texture>{zoom_anim}
                        </control>
                        <!-- Gated on real container focus, same reasoning
                             as poster_visual()'s border. -->
                        <control type="image">
                            <visible>Control.HasFocus({list_id})</visible>
                            <width>{EPISODE_THUMB_W}</width>
                            <height>{EPISODE_THUMB_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>episode-border.png</texture>{zoom_anim}
                        </control>{_watched_badge(zoom_anim)}{_overlays(zoom_anim)}
                    </control>
                    <control type="label">
                        <posx>{_EP_PAD}</posx>
                        <posy>{caption_y}</posy>
                        <width>{EPISODE_THUMB_W}</width>
                        <height>20</height>
                        <font>tofa_font_micro</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property(caption)]</label>
                    </control>
                    <!-- TWO COPIES WITH COMPLEMENTARY GATES, not one
                         control with <scroll>. Same technique, same reason
                         and same suffix as poster_card()'s title: an episode
                         name outruns 330px easily, focusedlayout renders for
                         the grid's ACTIVE cell even when the cursor is off
                         on the season rail or the tab bar, and Kodi's
                         <scroll> is a plain boolean with no condition of its
                         own. Ungated, the grid's current cell marqueed to
                         itself in the background. -->
                    <control type="label">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>{_EP_PAD}</posx>
                        <posy>{title_y}</posy>
                        <width>{EPISODE_THUMB_W}</width>
                        <height>28</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <scroll>true</scroll>
                        <scrollsuffix>\u2003\u2003\u2003</scrollsuffix>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>!Control.HasFocus({list_id})</visible>
                        <posx>{_EP_PAD}</posx>
                        <posy>{title_y}</posy>
                        <width>{EPISODE_THUMB_W}</width>
                        <height>28</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                </focusedlayout>"""

    return item, focused



def glass_pill(
    pill_id: int,
    *,
    x: int,
    width: int,
    group_id: int | None = None,
    ondown: int,
    onleft: int | None = None,
    onright: int | None = None,
    visible: str | None = None,
    height: int = 64,
    label_xml: str,
    leading_icon: str | None = None,
    trailing_icon: str | None = None,
) -> str:
    """Returns one static `<control type="group">...</control>` block for a
    "glass action pill" button: not a list item/itemlayout pair like every
    other fragment in this file, since Detail's Rewatch/Options/Watchlist
    row is 3 plain always-visible-or-conditionally-visible buttons, not a
    ManagedControlList. Faint SURFACE_REST/SURFACE_RAISED rest fill+outline,
    swapping to accent_pill_fill/accent_color on focus, all on
    capsule-pill.png/capsule-pill-outline.png border=32 (64 is the one
    action-pill height this app uses, so it's not a parameter).

    `label_xml` is the caller's own pre-built `<control type="label">...`
    block(s), not a plain string: the 3 real callers don't agree on
    alignment (Rewatch/Watchlist center a single label; Options left-
    aligns text next to a leading icon). `leading_icon`/`trailing_icon`
    are optional glyph codepoints (Options' icon + chevron); Rewatch/
    Watchlist pass neither.

    The Primary CTA pill is deliberately NOT this fragment: it's a
    genuinely different, solid-accent-fill treatment that exists exactly
    once in the app (see detail.xml.tpl), so extracting it would only add
    unused parameters here."""
    visible_xml = f"\n                            <visible>{visible}</visible>" if visible else ""
    onleft_xml = f"\n                                <onleft>{onleft}</onleft>" if onleft is not None else ""
    onright_xml = f"\n                                <onright>{onright}</onright>" if onright is not None else ""

    leading_xml = ""
    if leading_icon:
        leading_xml = f"""
                            <control type="label">
                                <posx>24</posx>
                                <posy>0</posy>
                                <width>24</width>
                                <height>{height}</height>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_19</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>{leading_icon}</label>
                            </control>"""

    trailing_xml = ""
    if trailing_icon:
        trailing_xml = f"""
                            <control type="label">
                                <posx>{width - 28}</posx>
                                <posy>0</posy>
                                <width>24</width>
                                <height>{height}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_19</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>{trailing_icon}</label>
                            </control>"""

    # The wrapping group carries an id so detail.py can re-pack the row when
    # a conditional pill is hidden: a group's position offsets its children,
    # so one setPosition() moves the whole pill.
    group_id_xml = f' id="{group_id}"' if group_id is not None else ""
    return f"""                        <control type="group"{group_id_xml}>
                            <posx>{x}</posx>{visible_xml}
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>{width}</width>
                                <height>{height}</height>
                                <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                                <texture border="{height // 2}">capsule-h{height}.png</texture>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>{width}</width>
                                <height>{height}</height>
                                <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                                <texture border="{height // 2}">capsule-h{height}.png</texture>
                                <visible>Control.HasFocus({pill_id})</visible>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>{width}</width>
                                <height>{height}</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture border="{height // 2}">capsule-h{height}-outline.png</texture>
                                <visible>Control.HasFocus({pill_id})</visible>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>{width}</width>
                                <height>{height}</height>
                                <colordiffuse>{T.SURFACE_RAISED}</colordiffuse>
                                <texture border="{height // 2}">capsule-h{height}-outline.png</texture>
                                <visible>!Control.HasFocus({pill_id})</visible>
                            </control>{leading_xml}
{label_xml}{trailing_xml}
                            <control type="button" id="{pill_id}">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>{width}</width>
                                <height>{height}</height>
                                <texturefocus>transparent-6px.png</texturefocus>
                                <texturenofocus>transparent-6px.png</texturenofocus>
                                <label></label>{onleft_xml}{onright_xml}
                                <ondown>{ondown}</ondown>
                            </control>
                        </control>"""


def alpha_rail_pill(list_id: int) -> tuple[str, str]:
    """One entry of Browse's A-Z rail (app 2.0): a small grey letter, "All"
    first and "#" last. The chosen letter sits in a grey disc and the focused
    one in the accent's. The layout is a whole pitch tall: a list steps by
    its itemlayout's height, not by <itemheight>."""
    W, D = T.ALPHA_PILL_W, T.ALPHA_PITCH
    active = "String.IsEqual(ListItem.Property(active),1)"

    def _disc(colour: str, vis: str) -> str:
        return f"""
                    <control type="image">
                        <visible>{vis}</visible>
                        <posx>{(W - D) // 2}</posx>
                        <width>{D}</width>
                        <height>{D}</height>
                        <colordiffuse>{colour}</colordiffuse>
                        <texture>circle.png</texture>
                    </control>"""

    def _glyph(colour: str, vis: str) -> str:
        return f"""
                    <control type="label">
                        <visible>{vis}</visible>
                        <width>{W}</width>
                        <height>{D}</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_MICRO}</font>
                        <textcolor>{colour}</textcolor>
                        <label>$INFO[ListItem.Property(glyph)]</label>
                    </control>"""

    rest = (_disc("0x4DFFFFFF", active)
            + _glyph("$INFO[Window.Property(text_primary)]", active)
            + _glyph("$INFO[Window.Property(text_secondary)]", "!" + active))
    focus = f"Control.HasFocus({list_id})"
    item = f"""                <itemlayout width="{W}" height="{D}">{rest}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{W}" height="{D}">
                    <control type="group">
                        <visible>!{focus}</visible>{rest}
                    </control>{_disc("$INFO[Window.Property(accent_color)]", focus)}{_glyph(
                        "$INFO[Window.Property(on_accent_color)]", focus)}
                </focusedlayout>"""
    return item, focused


def browse_tile(list_id: int) -> tuple[str, str]:
    """A tile of Browse's landing (app 2.0): art from the library under a
    dark fade, the name and a count (or the last title watched). The focused
    tile grows a little and takes an accent rim and glow."""
    W, H = T.BROWSE_TILE_W, T.BROWSE_TILE_H
    CW, CH = T.BROWSE_TILE_PITCH_X, T.BROWSE_TILE_PITCH_Y

    def _tile(rim: str) -> str:
        return f"""
                    <control type="image">
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>0xFF16222B</colordiffuse>
                        <texture diffuse="browse-tile-mask.png">white-square.png</texture>
                    </control>
                    <control type="image">
                        <width>{W}</width>
                        <height>{H}</height>
                        <aspectratio>scale</aspectratio>
                        <texture diffuse="browse-tile-mask.png">$INFO[ListItem.Art(thumb)]</texture>
                    </control>
                    <control type="image">
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>0xB3000000</colordiffuse>
                        <texture diffuse="browse-tile-mask.png">fade-bottom.png</texture>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(kind),surprise_me)</visible>
                        <posx>{W - 52}</posx>
                        <posy>14</posy>
                        <width>36</width>
                        <height>36</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_29}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>&#x{icon_glyphs.DICE_5:04X};</label>
                    </control>
                    <control type="label">
                        <posx>25</posx>
                        <posy>{H - 82}</posy>
                        <width>{W - 50}</width>
                        <height>38</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_BUTTON}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <posx>25</posx>
                        <posy>{H - 46}</posy>
                        <width>{W - 50}</width>
                        <height>26</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_BROWSE_CAPTION}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Label2]</label>
                    </control>{rim}"""

    focus = f"Control.HasFocus({list_id})"
    rim = f"""
                    <control type="image">
                        <visible>{focus}</visible>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>browse-tile-border.png</texture>
                    </control>"""
    glow = f"""
                    <control type="image">
                        <visible>{focus}</visible>
                        <posx>-10</posx>
                        <posy>-10</posy>
                        <width>{W + 20}</width>
                        <height>{H + 20}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>browse-tile-glow.png</texture>
                    </control>"""
    zoom = (f'<animation effect="zoom" start="100" end="103.5" center="{W // 2},{H // 2}" '
            f'time="150" tween="cubic" easing="out" condition="{focus}">Conditional</animation>')
    item = f"""                <itemlayout width="{CW}" height="{CH}">{_tile("")}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{CW}" height="{CH}">
                    <control type="group">
                        {zoom}{glow}{_tile(rim)}
                    </control>
                </focusedlayout>"""
    return item, focused


def browse_header_pill(list_id: int, *, glyph: str, label: str,
                       width: int) -> tuple[str, str]:
    """Folders and Surprise me beside a Browse view's title (app 2.0): glass
    with an icon and a word; focused, the accent's wash, rim and text."""
    H = T.BROWSE_CHIP_H

    def _body(colour: str, gate: str = "") -> str:
        vis = f"<visible>{gate}</visible>" if gate else ""
        return f"""
                    <control type="label">{vis}
                        <posx>22</posx><width>28</width><height>{H}</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_24}</font>
                        <textcolor>{colour}</textcolor>
                        <label>{glyph}</label>
                    </control>
                    <control type="label">{vis}
                        <posx>58</posx><width>{width - 76}</width><height>{H}</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_POSTER_TITLE}</font>
                        <textcolor>{colour}</textcolor>
                        <label>{label}</label>
                    </control>"""

    glass = f"""
                    <control type="image">
                        <width>{width}</width><height>{H}</height>
                        <colordiffuse>0x1AFFFFFF</colordiffuse>
                        <texture border="30">capsule-h60.png</texture>
                    </control>"""
    focus = f"Control.HasFocus({list_id})"
    white = "$INFO[Window.Property(text_primary)]"
    accent = "$INFO[Window.Property(accent_color)]"
    item = f"""                <itemlayout width="{width}" height="{H}">{glass}{_body(white)}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{width}" height="{H}">{glass}
                    <control type="image">
                        <visible>{focus}</visible>
                        <width>{width}</width><height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                        <texture border="30">capsule-h60.png</texture>
                    </control>
                    <control type="image">
                        <visible>{focus}</visible>
                        <width>{width}</width><height>{H}</height>
                        <colordiffuse>{accent}</colordiffuse>
                        <texture border="30">capsule-h60-outline.png</texture>
                    </control>{_body(accent, focus)}{_body(white, "!" + focus)}
                </focusedlayout>"""
    return item, focused


def browse_chip(control_id: int, *, indent: str = "                ") -> str:
    """One chip of a Browse view's chip row: a button whose width MainWindow
    sets, its words and resting fill window properties (browse_chip_<id>,
    _label) so a chosen chip reads as chosen. Python's setLabel would reset
    the font and colours. Focused: the accent's wash."""
    H = T.BROWSE_CHIP_H
    return f"""{indent}<control type="button" id="{control_id}">
{indent}    <width>{T.BROWSE_CHIP_PAD * 2}</width>
{indent}    <height>{H}</height>
{indent}    <font>{T.FONT_BODY}</font>
{indent}    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}    <focusedcolor>$INFO[Window.Property(accent_color)]</focusedcolor>
{indent}    <textoffsetx>{T.BROWSE_CHIP_PAD}</textoffsetx>
{indent}    <aligny>center</aligny>
{indent}    <texturefocus border="30" colordiffuse="$INFO[Window.Property(settings_row_wash)]">capsule-h60.png</texturefocus>
{indent}    <texturenofocus border="30" colordiffuse="$INFO[Window.Property(browse_chip_{control_id})]">capsule-h60.png</texturenofocus>
{indent}    <label>$INFO[Window.Property(browse_chip_{control_id}_label)]</label>
{indent}</control>"""


def empty_state(
    *,
    visible: str,
    glyph: str,
    title: str,
    message: str,
    flavour: str = "empty",
    posx: int = 0,
    posy: int = T.EMPTY_STATE_Y,
    width: int = T.SCREEN_W,
    indent: str = "                    ",
) -> str:
    """9.7's empty scaffold: centred column, icon then title then message.
    9.7 allows exactly one of these and no per-screen variants, so anything
    needing to say there is nothing here calls this rather than typing three
    labels again.

    The first hand-typed copy (More Like This) is what proved the point: it
    set the title in FONT_HEADING, which is 57px in a 40px-high slot 48px
    above the message, so the two lines rendered on top of each other.

    Every number below is measured off the real Apple TV app showing this
    exact scaffold (Besenbinden, 2026-08-01, native 1080p so 1:1): icon slot
    centred on 521, title on 590, message on 635, all centred on x=960. That
    puts the block a little above the middle of the content pane, not at the
    top where ours used to sit.

    Known 6px divergence, deliberate. The app appears to stack icon/title/
    message by their REAL heights and centre the whole column, so a taller
    glyph pushes the text down: its two states' blocks share a centre (572
    and 571) while their text sits 6px apart. This uses fixed slots, so text
    lands in the same place whatever the glyph. Measured against the app, the
    Cast state matches within 1px and the taller-glyphed More Like This state
    runs 6px high. Reproducing the app's model needs per-glyph rendered
    heights, which Kodi exposes for nothing (textmetrics.py only carries
    advance widths).

    The title is FONT_BUTTON, not FONT_SECTION_TITLE. 9.7 says "section-title
    scale", but the app's own section titles differ per screen, and the ones
    that share this screen -- the "Cast" and "Crew" labels -- are FONT_BUTTON
    here. Measured, the app's empty-state title renders 23px of cap where
    FONT_SECTION_TITLE gives 31 and FONT_BUTTON gives ~22, so the local
    section label is what 9.7 means on this screen.

    `title` and `message` are literal text or a $INFO[] reference -- both
    read the same from XML, so a caller with several messages can drive one
    scaffold from properties instead of emitting one block per sentence.

    `flavour` is 9.7's own split. "empty": neutral glyph at white 42%, white
    title, and no red at all. "error": the icon AND the title go status-red
    (2's `#f87171`, the semantic triad -- deliberately NOT the rating ramp's
    softer red, whose own comment forbids the two moving together). 9.7 also
    gives the error flavour a glass "Retry" button, which nothing here has
    yet: no screen using this has a reload path to wire it to."""
    if flavour not in ("empty", "error"):
        raise ValueError("empty_state: flavour must be 'empty' or 'error'")
    icon_colour = (T.STATUS_RED if flavour == "error"
                   else "$INFO[Window.Property(text_tertiary)]")
    title_colour = (T.STATUS_RED if flavour == "error"
                    else "$INFO[Window.Property(text_primary)]")
    icon_h, title_h, message_h = 64, 48, 34
    # Slot centres 521 / 590 / 635, expressed relative to the icon's own slot.
    title_y = (590 - title_h // 2) - (521 - icon_h // 2)
    message_y = (635 - message_h // 2) - (521 - icon_h // 2)
    return f"""{indent}<control type="group">
{indent}    <posx>{posx}</posx>
{indent}    <posy>{posy}</posy>
{indent}    <visible>{visible}</visible>
{indent}    <control type="label">
{indent}        <posy>0</posy>
{indent}        <width>{width}</width>
{indent}        <height>{icon_h}</height>
{indent}        <align>center</align>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_ICON_64}</font>
{indent}        <textcolor>{icon_colour}</textcolor>
{indent}        <label>{glyph}</label>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posy>{title_y}</posy>
{indent}        <width>{width}</width>
{indent}        <height>{title_h}</height>
{indent}        <align>center</align>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_BUTTON}</font>
{indent}        <textcolor>{title_colour}</textcolor>
{indent}        <label>{title}</label>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posy>{message_y}</posy>
{indent}        <width>{width}</width>
{indent}        <height>{message_h}</height>
{indent}        <align>center</align>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_BODY}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>{message}</label>
{indent}    </control>
{indent}</control>"""


def poster_row(
    *,
    group_id: int,
    list_id: int,
    title_property: str,
    onup: int,
    ondown: int,
    item_xml: str,
    focused_xml: str,
    list_width: int = T.CONTENT_WIDTH,
    cell_w: int = T.CELL_W,
    indent: str = "            ",
    pos: tuple[int, int] | None = None,
    block_h: int = T.ROW_BLOCK_H,
) -> str:
    """One complete poster row: header label + horizontal list, wrapped in a
    group that hides itself when `title_property` is empty.

    Home hand-wrote this block nine times and Discover three more, byte-
    identical apart from ids -- which is why the three screens drifted to
    three different title gaps and row heights. Generating it means a row
    count is now just a number (Discover's largest tab needs ~15), and the
    geometry comes from tokens.py rather than being retyped per block."""
    # The region starts at the lists' edge (HOME_ROWS_X), and a grouplist
    # ignores its children's own posx, so the inset goes on what is inside.
    inset = -T.ROW_LIST_X
    at = (f"\n{indent}    <posx>{pos[0]}</posx>\n{indent}    <posy>{pos[1]}</posy>"
          if pos else "")
    return f"""{indent}<control type="group" id="{group_id}">{at}
{indent}    <height>{block_h}</height>
{indent}    <visible>!String.IsEmpty(Window.Property({title_property}))</visible>
{indent}    <control type="label">
{indent}        <posx>{inset}</posx>
{indent}        <width>{T.CONTENT_WIDTH}</width>
{indent}        <height>{T.ROW_TITLE_H}</height>
{indent}        <font>{T.FONT_SECTION_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>$INFO[Window.Property({title_property})]</label>
{indent}    </control>
{indent}    <control type="list" id="{list_id}">
{indent}        <posx>{T.ROW_LIST_X + inset}</posx>
{indent}        <posy>{T.ROW_TITLE_GAP}</posy>
{indent}        <width>{list_width}</width>
{indent}        <height>{T.CELL_H}</height>
{indent}        <onup>{onup}</onup>
{indent}        <ondown>{ondown}</ondown>
{indent}        <orientation>horizontal</orientation>
{indent}        <itemwidth>{cell_w}</itemwidth>
{indent}        <itemheight>{T.CELL_H}</itemheight>
{indent}        <scrolltime>{T.SCROLLTIME}</scrolltime>
{item_xml}

{focused_xml}
{indent}    </control>
{indent}</control>"""


def _text_tab_slot(idx: int, selected: bool, focused: str, slot_w: int,
                   centres: tuple, widths: tuple) -> str:
    """One text tab in a strip list, drawn at its measured centre: half-white
    at rest, white when current, an underline on focus, a dot once left."""
    current = "!String.IsEmpty(ListItem.Property(is_current))"
    white = "$INFO[Window.Property(text_primary)]"
    off = idx * slot_w
    w = widths[idx]
    centre = centres[idx] - off
    x = centre - w // 2
    y = T.DISCOVER_SUBTAB_LABEL_Y
    if selected:
        colours = ((white, ""),)
    else:
        colours = ((white, f"<visible>{current}</visible>"),
                   (T.NAV_TAB_REST, "<visible>String.IsEmpty(ListItem.Property(is_current))</visible>"))
    labels = "".join(f"""
                        <control type="label">
                            <posx>{x}</posx>
                            <posy>{y}</posy>
                            <width>{w + 20}</width>
                            <height>{T.DISCOVER_SUBTAB_LABEL_H}</height>
                            <font>{T.FONT_CAPTION}</font>
                            <textcolor>{colour}</textcolor>
                            <label>$INFO[ListItem.Label]</label>{vis}
                        </control>""" for colour, vis in colours)
    marks = _nav_mark(centre - T.NAV_DOT_SIZE // 2, T.NAV_DOT_SIZE,
                      T.DISCOVER_SUBTAB_DOT_Y + _NAV_LIST_Y, T.NAV_DOT_SIZE,
                      ">circle.png", f"!{focused} + {current}")
    if selected:
        marks += _nav_mark(x - 1, w + 2, T.DISCOVER_SUBTAB_UNDERLINE_Y + _NAV_LIST_Y,
                           T.NAV_UNDERLINE_H,
                           f' border="{T.NAV_UNDERLINE_H // 2}">capsule-h{T.NAV_UNDERLINE_H}.png',
                           focused)
    return f"""
                    <control type="group">
                        <visible>String.IsEqual(ListItem.Property(tab_idx),{idx})</visible>{labels}{marks}
                    </control>"""


def settings_info_panel() -> str:
    """Settings' left column (app 2.0): a summary of the page while the tabs
    have focus, and the focused row's title, value, text and choices."""
    x, w = T.SETTINGS_LEFT, T.SETTINGS_INFO_W
    row = "!String.IsEmpty(Window.Property(settings_info))"
    white = "$INFO[Window.Property(text_primary)]"
    strong = "$INFO[Window.Property(text_strong)]"
    grey = "$INFO[Window.Property(text_secondary)]"
    accent = "$INFO[Window.Property(accent_color)]"

    def label(y, h, font, colour, text, vis="", lx=0, lw=w):
        v = f"\n                    <visible>{vis}</visible>" if vis else ""
        return f"""
                <control type="label">
                    <posx>{lx}</posx>
                    <posy>{y}</posy>
                    <width>{lw}</width>
                    <height>{h}</height>
                    <font>{font}</font>
                    <textcolor>{colour}</textcolor>
                    <label>{text}</label>{v}
                </control>"""

    def prop_set(name):
        return f"!String.IsEmpty(Window.Property({name}))"

    summary = ""
    for i in range(4):
        y = T.SETTINGS_SUM_Y + i * T.SETTINGS_SUM_PITCH
        gate = prop_set(f"settings_sum{i + 1}_key")
        summary += f"""
                <control type="image">
                    <posy>{y - 18}</posy>
                    <width>{w}</width>
                    <height>1</height>
                    <colordiffuse>{T.DISCOVER_DIVIDER}</colordiffuse>
                    <texture>white-square.png</texture>
                    <visible>{gate}</visible>
                </control>""" + label(
            y, 20, T.FONT_EYEBROW, grey,
            f"$INFO[Window.Property(settings_sum{i + 1}_key)]", gate) + label(
            y + 23, 34, T.FONT_ROW_TITLE, white,
            f"$INFO[Window.Property(settings_sum{i + 1}_value)]", gate)

    # The row state stacks in a grouplist, so a short body or no note
    # closes up and the choices follow straight after.
    stack = "".join(label(0, 30, T.FONT_BODY, strong,
                          f"$INFO[Window.Property(settings_info_body{n})]",
                          prop_set(f"settings_info_body{n}")) for n in (1, 2, 3))
    stack += f"""
                    <control type="group">
                        <height>{T.SETTINGS_INFO_NOTE_GAP}</height>
                        <visible>{prop_set("settings_info_note1")}</visible>
                    </control>"""
    stack += "".join(label(0, 27, T.FONT_METADATA, grey,
                           f"$INFO[Window.Property(settings_info_note{n})]",
                           prop_set(f"settings_info_note{n}")) for n in (1, 2))
    stack += f"""
                    <control type="group">
                        <height>{T.SETTINGS_INFO_OPTS_GAP}</height>
                        <visible>{prop_set("settings_info_opt1")}</visible>
                    </control>"""
    for n in range(1, 5):
        on = prop_set(f"settings_info_opt{n}_on")
        stack += f"""
                    <control type="group">
                        <height>{T.SETTINGS_INFO_OPT_PITCH}</height>
                        <visible>{prop_set(f"settings_info_opt{n}")}</visible>
                        <control type="image">
                            <posx>1</posx>
                            <posy>9</posy>
                            <width>12</width>
                            <height>12</height>
                            <colordiffuse>{accent}</colordiffuse>
                            <texture>circle.png</texture>
                            <visible>{on}</visible>
                        </control>
                        <control type="image">
                            <posx>1</posx>
                            <posy>9</posy>
                            <width>12</width>
                            <height>12</height>
                            <colordiffuse>{grey}</colordiffuse>
                            <texture>circle-outline.png</texture>
                            <visible>!{on}</visible>
                        </control>""" + label(
            0, 30, T.FONT_POSTER_TITLE, white,
            f"$INFO[Window.Property(settings_info_opt{n})]",
            f"!{prop_set(f'settings_info_opt{n}_dim')}", lx=30, lw=w - 30) + label(
            0, 30, T.FONT_POSTER_TITLE, grey,
            f"$INFO[Window.Property(settings_info_opt{n})]",
            prop_set(f"settings_info_opt{n}_dim"), lx=30, lw=w - 30) + label(
            32, 28, T.FONT_METADATA, grey,
            f"$INFO[Window.Property(settings_info_opt{n}_desc)]", lx=30, lw=w - 30) + """
                    </control>"""



    def row_group(vis, title_y, title_h, title_font, value_y, body_y):
        return f"""
            <control type="group">
                <posx>{x}</posx>
                <posy>0</posy>
                <visible>{vis}</visible>""" + label(
            title_y, title_h, title_font, white,
            "$INFO[Window.Property(settings_info_title)]") + f"""
                <control type="image">
                    <posx>1</posx>
                    <posy>{value_y + 12}</posy>
                    <width>10</width>
                    <height>10</height>
                    <colordiffuse>{accent}</colordiffuse>
                    <texture>circle.png</texture>
                    <visible>{prop_set("settings_info_value")} + !{prop_set("settings_info_now")}</visible>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>{value_y + 11}</posy>
                    <width>12</width>
                    <height>12</height>
                    <colordiffuse>{accent}</colordiffuse>
                    <texture>circle-outline.png</texture>
                    <visible>{prop_set("settings_info_now")}</visible>
                </control>
                <control type="grouplist">
                    <posx>24</posx>
                    <posy>{value_y}</posy>
                    <width>{w - 24}</width>
                    <height>34</height>
                    <orientation>horizontal</orientation>
                    <itemgap>14</itemgap>
                    <usecontrolcoords>true</usecontrolcoords>
                    <control type="label">
                        <width>auto</width>
                        <height>34</height>
                        <font>{T.FONT_ROW_TITLE}</font>
                        <textcolor>{white}</textcolor>
                        <label>$INFO[Window.Property(settings_info_value)]</label>
                    </control>
                    <control type="label">
                        <width>auto</width>
                        <height>34</height>
                        <font>{T.FONT_SIDEBAR}</font>
                        <textcolor>{grey}</textcolor>
                        <label>$INFO[Window.Property(settings_info_now)]</label>
                        <visible>{prop_set("settings_info_now")}</visible>
                    </control>
                </control>
                <control type="grouplist">
                    <posy>{body_y}</posy>
                    <width>{w}</width>
                    <height>{T.SCREEN_H - body_y}</height>
                    <orientation>vertical</orientation>
                    <itemgap>0</itemgap>
                    <usecontrolcoords>true</usecontrolcoords>{stack}
                </control>
            </control>"""

    # Under a preview (app 2.0) the words move down and the title shrinks.
    preview = "!String.IsEmpty(Window.Property(settings_preview))"
    return f"""
            <control type="group">
                <posx>{x}</posx>
                <posy>0</posy>
                <visible>!{row}</visible>{summary}
            </control>
""" + row_group(
        f"{row} + !{preview}", T.SETTINGS_INFO_TITLE_Y, 80, T.FONT_HERO_TITLE,
        T.SETTINGS_INFO_VALUE_Y, T.SETTINGS_INFO_BODY_Y) + row_group(
        f"{row} + {preview}", T.SETTINGS_PREVIEW_TITLE_Y, 50, T.FONT_SETTINGS_TITLE,
        T.SETTINGS_PREVIEW_VALUE_Y, T.SETTINGS_PREVIEW_BODY_Y)


def _settings_preview_fox() -> str:
    """Fox accent's preview: the focused fox's logo and name over its glow,
    and a little of the app drawn in its colour (tabs, Play, progress, a switch)."""
    fox = "$INFO[Window.Property(settings_preview_fox)]"
    white = "$INFO[Window.Property(text_primary)]"
    grey = "$INFO[Window.Property(text_secondary)]"

    def img(x, y, w, h, colour, texture, border=""):
        b = f' border="{border}"' if border else ""
        return f"""
                    <control type="image">
                        <posx>{x}</posx><posy>{y}</posy><width>{w}</width><height>{h}</height>
                        <colordiffuse>{colour}</colordiffuse>
                        <texture{b}>{texture}</texture>
                    </control>"""

    def text(x, y, w, h, font, colour, label, align="left"):
        return f"""
                    <control type="label">
                        <posx>{x}</posx><posy>{y}</posy><width>{w}</width><height>{h}</height>
                        <align>{align}</align><aligny>center</aligny>
                        <font>{font}</font><textcolor>{colour}</textcolor>
                        <label>{label}</label>
                    </control>"""

    return (img(0, 0, T.SETTINGS_PREVIEW_W, T.SETTINGS_PREVIEW_H,
                "$INFO[Window.Property(settings_preview_fox_glow)]", "settings-preview-glow.png")
            + f"""
                    <control type="image">
                        <posx>95</posx><posy>76</posy><width>130</width><height>152</height>
                        <aspectratio>keep</aspectratio>
                        <texture>$INFO[Window.Property(settings_preview_logo)]</texture>
                    </control>"""
            + text(40, 248, 240, 32, T.FONT_POSTER_TITLE, white,
                   "$INFO[Window.Property(settings_preview_fox_name)]", "center")
            + text(316, 74, 80, 28, T.FONT_ACCOUNT, white, "Home")
            + text(381, 74, 100, 28, T.FONT_ACCOUNT, grey, "Browse")
            + img(338, 104, 6, 6, fox, "circle.png")
            + img(316, 121, 106, 40, "$INFO[Window.Property(settings_preview_fox_fill)]",
                  "capsule-h40.png", "20")
            + img(316, 121, 106, 40, fox, "capsule-h40-outline.png", "20")
            + text(334, 121, 24, 40, T.FONT_ICON_19, fox, f"&#x{icon_glyphs.PLAY:04X};")
            + text(360, 121, 60, 40, T.FONT_ACCOUNT, fox, "Play")
            + text(316, 178, 100, 22, T.FONT_EYEBROW, fox, "S2 E4")
            + img(316, 204, 190, 5, "0x33FFFFFF", "white-square.png")
            + img(316, 204, 118, 5, fox, "white-square.png")
            + img(316, 224, 64, 38, fox, "capsule-h38.png", "19")
            + img(345, 227, 32, 32, "white", "circle.png"))


def _settings_preview_home() -> str:
    """The Home tab's preview: a small Home, the focused row framed in the
    accent with the row after it, under the spotlight when it is the first."""
    accent = "$INFO[Window.Property(accent_color)]"
    white = "$INFO[Window.Property(text_primary)]"
    grey = "$INFO[Window.Property(text_secondary)]"
    hero = "!String.IsEmpty(Window.Property(settings_preview_hero))"

    def text(x, y, w, h, font, colour, label, vis=""):
        v = f"<visible>{vis}</visible>" if vis else ""
        return f"""
                    <control type="label">{v}
                        <posx>{x}</posx><posy>{y}</posy><width>{w}</width><height>{h}</height>
                        <aligny>center</aligny>
                        <font>{font}</font><textcolor>{colour}</textcolor>
                        <label>{label}</label>
                    </control>"""

    def posters(prefix, y, h):
        out = ""
        for i in range(10):
            out += f"""
                    <control type="image">
                        <posx>{24 + 52 * i}</posx><posy>{y}</posy><width>46</width><height>{h}</height>
                        <colordiffuse>0xFF1C262D</colordiffuse>
                        <texture>white-square.png</texture>
                    </control>
                    <control type="image">
                        <posx>{24 + 52 * i}</posx><posy>{y}</posy><width>46</width><height>{h}</height>
                        <aspectratio aligny="top">scale</aspectratio>
                        <texture>$INFO[Window.Property(settings_preview_{prefix}{i})]</texture>
                    </control>"""
        return out

    def rows(top, vis):
        below = top + 118
        return f"""
                <control type="group">
                    <visible>{vis}</visible>
                    <control type="image">
                        <posx>18</posx><posy>{top}</posy><width>525</width><height>100</height>
                        <colordiffuse>{accent}</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>""" + text(
            24, top + 3, 500, 24, T.FONT_EYEBROW, accent,
            "$INFO[Window.Property(settings_preview_row_a)]") + posters(
            "a", top + 27, 68) + text(
            24, below + 3, 500, 24, T.FONT_EYEBROW, grey,
            "$INFO[Window.Property(settings_preview_row_b)]") + posters(
            "b", below + 27, min(68, T.SETTINGS_PREVIEW_H - below - 27)) + """
                </control>"""

    tabs = """
                    <control type="grouplist">
                        <posx>58</posx><posy>12</posy><width>500</width><height>26</height>
                        <orientation>horizontal</orientation>
                        <itemgap>16</itemgap>
                        <usecontrolcoords>true</usecontrolcoords>""" + "".join(f"""
                        <control type="label">
                            <width>auto</width><height>26</height><aligny>center</aligny>
                            <font>{T.FONT_ACCOUNT}</font>
                            <textcolor>{white if n == "Home" else grey}</textcolor>
                            <label>{n}</label>
                        </control>""" for n in ("Home", "Browse", "Discover", "Search")) + """
                    </control>"""
    return f"""
                    <control type="image">
                        <posx>20</posx><posy>12</posy><width>24</width><height>28</height>
                        <aspectratio>keep</aspectratio>
                        <texture>$INFO[Window.Property(logo_file)]</texture>
                    </control>{tabs}
                    <control type="image">
                        <posx>72</posx><posy>38</posy><width>5</width><height>5</height>
                        <colordiffuse>{accent}</colordiffuse>
                        <texture>circle.png</texture>
                    </control>
                    <control type="group">
                        <visible>{hero}</visible>
                        <control type="image">
                            <posx>18</posx><posy>50</posy><width>572</width><height>96</height>
                            <aspectratio>scale</aspectratio>
                            <texture diffuse="nextup-mask-352x198.png">$INFO[Window.Property(settings_preview_art)]</texture>
                        </control>
                        <control type="image">
                            <posx>18</posx><posy>50</posy><width>300</width><height>96</height>
                            <colordiffuse>0x99000000</colordiffuse>
                            <texture>fade-left.png</texture>
                        </control>""" + text(30, 76, 300, 26, T.FONT_ACCOUNT, white, "Featured tonight") + f"""
                        <control type="image">
                            <posx>30</posx><posy>107</posy><width>50</width><height>28</height>
                            <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>""" + text(40, 107, 40, 28, T.FONT_MICRO, accent, "Play") + """
                    </control>""" + rows(159, hero) + rows(50, "!" + hero)


def _nextup_overlays_for_preview() -> str:
    """The player's four Next Up styles, lifted from its static XML for the
    Settings preview: ids dropped, the style read from settings_preview_style,
    plus each style's ring and season bar, which the player places at runtime."""
    path = os.path.join(os.path.dirname(__file__), "static", "script-tofa-player.xml")
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    start = xml.index("            <!-- compact -->")
    end = xml.index("            <control type=\"group\">\n"
                    "                <visible>!String.IsEmpty(Window.Property(nextup_segments))</visible>",
                    start)
    body = re.sub(r' id="\d+"', "", xml[start:end])
    body = body.replace("Window.Property(nextup_style)", "Window.Property(settings_preview_style)")
    accent = "$INFO[Window.Property(accent_color)]"
    extra = ""
    for style, (_play, _close, ring, bar) in settings_options.NEXT_UP_GEOMETRY.items():
        parts = ""
        if ring:
            cx, cy, d = ring
            box = f"<posx>{cx - d // 2}</posx><posy>{cy - d // 2}</posy><width>{d}</width><height>{d}</height>"
            parts += f"""
                <control type="image">{box}
                    <colordiffuse>$INFO[Window.Property(nextup_ring_track)]</colordiffuse>
                    <texture>nextup-ring-track.png</texture>
                </control>
                <control type="image">{box}
                    <colordiffuse>{accent}</colordiffuse>
                    <texture>nextup-ring/28.png</texture>
                </control>"""
        if bar:
            x0, y, total = bar
            count, gap = 5, 6
            seg = (total - gap * (count - 1)) / count
            for i in range(count):
                colour = accent if i == 2 else "0x4DFFFFFF"
                parts += f"""
                <control type="image">
                    <posx>{int(round(x0 + i * (seg + gap)))}</posx><posy>{y}</posy>
                    <width>{int(round(seg))}</width><height>4</height>
                    <colordiffuse>{colour}</colordiffuse>
                    <texture>white-square.png</texture>
                </control>"""
        if parts:
            extra += f"""
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_preview_style),{style})</visible>{parts}
            </control>"""
    return body + extra


def settings_preview() -> str:
    """The left column's preview card (app 2.0): a backdrop from the library
    with our own player drawn over it -- Next Up in the focused style, or a
    skip button on the scrub bar -- for the rows that change what plays."""
    x, y = T.SETTINGS_LEFT, T.SETTINGS_PREVIEW_Y
    w, h = T.SETTINGS_PREVIEW_W, T.SETTINGS_PREVIEW_H
    kind = "String.IsEqual(Window.Property(settings_preview),{0})".format
    at_end = "String.IsEqual(Window.Property(settings_preview_at),end)"
    accent = "$INFO[Window.Property(accent_color)]"
    white = "$INFO[Window.Property(text_primary)]"
    grey = "$INFO[Window.Property(text_secondary)]"
    mask = "settings-preview-mask-{0}x{1}.png".format(w, h)

    def label(lx, ly, lw, lh, font, colour, text, align="left", vis=""):
        # Outside a list, a right-aligned label's posx is its RIGHT edge.
        v = f"<visible>{vis}</visible>" if vis else ""
        return f"""
                    <control type="label">{v}
                        <posx>{lx}</posx><posy>{ly}</posy>
                        <width>{lw}</width><height>{lh}</height>
                        <align>{align}</align><aligny>center</aligny>
                        <font>{font}</font>
                        <textcolor>{colour}</textcolor>
                        <label>{text}</label>
                    </control>"""

    def rect(rx, ry, rw, rh, colour, texture="white-square.png", border="", vis=""):
        v = f"<visible>{vis}</visible>" if vis else ""
        b = f' border="{border}"' if border else ""
        return f"""
                    <control type="image">{v}
                        <posx>{rx}</posx><posy>{ry}</posy>
                        <width>{rw}</width><height>{rh}</height>
                        <colordiffuse>{colour}</colordiffuse>
                        <texture{b}>{texture}</texture>
                    </control>"""

    def scrub(knob_x, left_time, right_time, vis=""):
        """The player's scrub bar, filled to `knob_x`, with its two times."""
        return (rect(22, 293, 557, 5, "0x4DFFFFFF", vis=vis)
                + rect(22, 293, knob_x - 22, 5, accent, vis=vis)
                + rect(knob_x - 8, 287, 16, 16, "white", "circle.png", vis=vis)
                + label(22, 306, 200, 24, T.FONT_MICRO, white, left_time, vis=vis)
                + label(586, 306, 200, 24, T.FONT_MICRO, white, right_time, "right", vis=vis))

    play_next = (
        rect(296, 196, 289, 81, "0xE6101418", "rounded-14.png", "14")
        + f"""
                    <control type="image">
                        <posx>306</posx><posy>206</posy>
                        <width>110</width><height>62</height>
                        <aspectratio>scale</aspectratio>
                        <texture diffuse="nextup-mask-128x72.png">$INFO[Window.Property(settings_preview_art)]</texture>
                    </control>"""
        + label(429, 208, 150, 28, T.FONT_ACCOUNT, white, "Episode 5")
        + label(429, 234, 150, 24, T.FONT_MICRO, grey, "Playing in 8 seconds")
        + rect(429, 263, 130, 3, "0x33FFFFFF") + rect(429, 263, 52, 3, accent)
        + scrub(579, "42:44", "-0:38"))

    pill = (rect(420, 238, 166, 42, "$INFO[Window.Property(accent_pill_fill)]",
                 "capsule-h40.png", "20")
            + rect(420, 238, 166, 42, accent, "capsule-h40-outline.png", "20")
            + label(436, 238, 24, 42, T.FONT_ICON_19, accent,
                    f"&#x{icon_glyphs.CHEVRONS_RIGHT:04X};")
            + label(462, 238, 120, 42, T.FONT_ACCOUNT, accent,
                    "$INFO[Window.Property(settings_preview_skip)]"))
    skip = (pill
            + label(36, 262, 200, 24, T.FONT_MICRO, white,
                    "$INFO[Window.Property(settings_preview_segment)]", vis=f"!{at_end}")
            + rect(53, 293, 22, 5, "0x99FFFFFF", vis=f"!{at_end}")
            + rect(532, 293, 47, 5, "0x99FFFFFF", vis=at_end)
            + scrub(53, "1:24", "-42:12", vis=f"!{at_end}")
            + scrub(532, "40:51", "-2:09", vis=at_end))

    # The overlays keep their 1920x1080 coordinates and are scaled onto the
    # card: zooming about c maps (0, 0) to c * (1 - s), so c = card / (1 - s).
    scale = float(w) / T.SCREEN_W
    zoom = round(100.0 * scale, 3)
    cx, cy = round(x / (1 - scale), 2), round(y / (1 - scale), 2)
    overlays = f"""
            <control type="group">
                <visible>!String.IsEmpty(Window.Property(settings_info)) + {kind("nextup_style")}</visible>
                <animation effect="zoom" start="{zoom}" end="{zoom}" center="{cx},{cy}" time="0" condition="true">Conditional</animation>
{_nextup_overlays_for_preview()}
            </control>"""
    return f"""
            <control type="group">
                <posx>{x}</posx>
                <posy>{y}</posy>
                <visible>!String.IsEmpty(Window.Property(settings_info)) + !String.IsEmpty(Window.Property(settings_preview))</visible>
                <control type="image">
                    <width>{w}</width>
                    <height>{h}</height>
                    <colordiffuse>0xFF16222B</colordiffuse>
                    <texture diffuse="{mask}">white-square.png</texture>
                </control>
                <control type="image">
                    <visible>!{kind("fox")} + !{kind("home")}</visible>
                    <width>{w}</width>
                    <height>{h}</height>
                    <aspectratio>scale</aspectratio>
                    <texture diffuse="{mask}">$INFO[Window.Property(settings_preview_art)]</texture>
                </control>
                <control type="group">
                    <visible>{kind("play_next")} | {kind("skip")}</visible>
                    <control type="image">
                        <posy>{h - 140}</posy>
                        <width>{w}</width>
                        <height>140</height>
                        <colordiffuse>0x99000000</colordiffuse>
                        <texture diffuse="{mask}">fade-bottom.png</texture>
                    </control>
                </control>
                <control type="group">
                    <visible>{kind("play_next")}</visible>{play_next}
                </control>
                <control type="group">
                    <visible>{kind("skip")}</visible>{skip}
                </control>
                <control type="group">
                    <visible>{kind("fox")}</visible>{_settings_preview_fox()}
                </control>
                <control type="group">
                    <visible>{kind("home")}</visible>{_settings_preview_home()}
                </control>
                <control type="image">
                    <width>{w}</width>
                    <height>{h}</height>
                    <colordiffuse>0x26FFFFFF</colordiffuse>
                    <texture border="20">rounded-20-outline.png</texture>
                </control>
            </control>""" + overlays


def settings_tab_strip(*, list_id: int, onup: int, ondown: int) -> str:
    """Settings' six pages as text tabs under the top bar (app 2.0), the
    same grammar as Discover's, with a divider under them."""
    focused = f"Control.HasFocus({list_id})"
    n = len(T.SETTINGS_TAB_CENTRES)
    slot_w = T.SETTINGS_TAB_SLOT
    item = "".join(_text_tab_slot(i, False, focused, slot_w, T.SETTINGS_TAB_CENTRES,
                                  T.SETTINGS_TAB_INK_W) for i in range(n))
    sel = "".join(_text_tab_slot(i, True, focused, slot_w, T.SETTINGS_TAB_CENTRES,
                                 T.SETTINGS_TAB_INK_W) for i in range(n))
    h = T.DISCOVER_DIVIDER_Y
    return f"""            <control type="list" id="{list_id}">
                <posx>0</posx>
                <posy>0</posy>
                <width>{slot_w * n}</width>
                <height>{h}</height>
                <orientation>horizontal</orientation>
                <itemwidth>{slot_w}</itemwidth>
                <itemheight>{h}</itemheight>
                <onup>{onup}</onup>
                <ondown>{ondown}</ondown>
                <onleft>{list_id}</onleft>
                <onright>{list_id}</onright>
                <itemlayout width="{slot_w}" height="{h}">{item}
                </itemlayout>
                <focusedlayout width="{slot_w}" height="{h}">{sel}
                </focusedlayout>
            </control>
            <control type="image">
                <posx>{T.SETTINGS_LEFT}</posx>
                <posy>{h}</posy>
                <width>{T.DISCOVER_DIVIDER_W}</width>
                <height>1</height>
                <colordiffuse>{T.DISCOVER_DIVIDER}</colordiffuse>
                <texture>white-square.png</texture>
            </control>"""


def discover_subtab_strip(*, list_id: int, onup: int, ondown: int) -> str:
    """Discover's sub-tabs as one list of text tabs, same grammar as the top
    bar: half-white at rest, white when current, an underline on the focused
    tab and a dot under the current one once focus has left the strip."""
    focused = f"Control.HasFocus({list_id})"

    def slot(idx: int, selected: bool) -> str:
        return _text_tab_slot(idx, selected, focused, T.DISCOVER_SUBTAB_SLOT,
                              T.DISCOVER_SUBTAB_CENTRES, T.DISCOVER_SUBTAB_INK_W)

    def filters_slot(selected: bool) -> str:
        """Icon, label and count badge, right-aligned; white only on focus."""
        off = n * T.DISCOVER_SUBTAB_SLOT
        out = []
        for badged in (False, True):
            shift = T.DISCOVER_FILTERS_BADGE_SHIFT if badged else 0
            label_x = T.DISCOVER_FILTERS_RIGHT - T.DISCOVER_FILTERS_LABEL_W - shift - off
            icon_x = label_x - T.DISCOVER_FILTERS_ICON_GAP - T.DISCOVER_FILTERS_ICON_W
            colour = (f"$INFO[Window.Property(text_primary)]" if selected else T.NAV_TAB_REST)
            rest = (f"<visible>!{focused}</visible>" if selected else "")
            texts = ""
            for c, vis in (((colour, f"<visible>{focused}</visible>"), (T.NAV_TAB_REST, rest))
                           if selected else ((colour, ""),)):
                texts += f"""
                            <control type="label">
                                <posx>{icon_x - 2}</posx>
                                <posy>{T.DISCOVER_FILTERS_ICON_Y}</posy>
                                <width>24</width>
                                <height>24</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_24</font>
                                <textcolor>{c}</textcolor>
                                <label>$INFO[ListItem.Property(icon_glyph)]</label>{vis}
                            </control>
                            <control type="label">
                                <posx>{label_x - 1}</posx>
                                <posy>{T.DISCOVER_SUBTAB_LABEL_Y}</posy>
                                <width>{T.DISCOVER_FILTERS_LABEL_W + 20}</width>
                                <height>{T.DISCOVER_SUBTAB_LABEL_H}</height>
                                <font>{T.FONT_CAPTION}</font>
                                <textcolor>{c}</textcolor>
                                <label>$INFO[ListItem.Label]</label>{vis}
                            </control>"""
            badge = ""
            if badged:
                bx = T.DISCOVER_FILTERS_RIGHT - T.DISCOVER_FILTERS_BADGE - off
                badge = f"""
                            <control type="image">
                                <posx>{bx}</posx>
                                <posy>{T.DISCOVER_FILTERS_BADGE_Y}</posy>
                                <width>{T.DISCOVER_FILTERS_BADGE}</width>
                                <height>{T.DISCOVER_FILTERS_BADGE}</height>
                                <colordiffuse>{T.DISCOVER_FILTERS_ROW_FILL}</colordiffuse>
                                <texture>circle.png</texture>
                            </control>
                            <control type="label">
                                <posx>{bx}</posx>
                                <posy>{T.DISCOVER_FILTERS_BADGE_Y}</posy>
                                <width>{T.DISCOVER_FILTERS_BADGE}</width>
                                <height>{T.DISCOVER_FILTERS_BADGE}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_EYEBROW}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[ListItem.Property(badge)]</label>
                            </control>"""
            line = ""
            if selected:
                line_x = icon_x - 2
                line = _nav_mark(line_x, T.DISCOVER_FILTERS_RIGHT - off - line_x,
                                 T.DISCOVER_SUBTAB_UNDERLINE_Y + _NAV_LIST_Y, T.NAV_UNDERLINE_H,
                                 f' border="{T.NAV_UNDERLINE_H // 2}">capsule-h{T.NAV_UNDERLINE_H}.png',
                                 focused)
            gate = ("!String.IsEmpty(ListItem.Property(badge))" if badged
                    else "String.IsEmpty(ListItem.Property(badge))")
            out.append(f"""
                        <control type="group">
                            <visible>{gate}</visible>{texts}{badge}{line}
                        </control>""")
        return f"""
                    <control type="group">
                        <visible>String.IsEqual(ListItem.Property(tab_idx),{n})</visible>{"".join(out)}
                    </control>"""

    n = len(T.DISCOVER_SUBTAB_CENTRES)
    item = "".join(slot(i, False) for i in range(n)) + filters_slot(False)
    sel = "".join(slot(i, True) for i in range(n)) + filters_slot(True)
    return f"""            <control type="list" id="{list_id}">
                <posx>0</posx>
                <posy>0</posy>
                <width>{T.DISCOVER_SUBTAB_SLOT * (n + 1)}</width>
                <height>{T.DISCOVER_DIVIDER_Y}</height>
                <orientation>horizontal</orientation>
                <onup>{onup}</onup>
                <ondown>{ondown}</ondown>
                <onleft>{list_id}</onleft>
                <onright>{list_id}</onright>
                <itemlayout width="{T.DISCOVER_SUBTAB_SLOT}" height="{T.DISCOVER_DIVIDER_Y}">{item}
                </itemlayout>
                <focusedlayout width="{T.DISCOVER_SUBTAB_SLOT}" height="{T.DISCOVER_DIVIDER_Y}">{sel}
                </focusedlayout>
            </control>
            <control type="image">
                <posx>{T.DISCOVER_LEFT}</posx>
                <posy>{T.DISCOVER_DIVIDER_Y}</posy>
                <width>{T.DISCOVER_DIVIDER_W}</width>
                <height>1</height>
                <colordiffuse>{T.DISCOVER_DIVIDER}</colordiffuse>
                <texture>white-square.png</texture>
            </control>"""


def discover_filters_popover(list_id: int) -> str:
    """The Filters popover under the strip's Filters item: four on/off rows,
    then a rule and "Reset filters" while any is on."""
    rw, rh = T.DISCOVER_FILTERS_ROW_W, T.DISCOVER_FILTERS_ROW_H
    ring_x = rw - T.DISCOVER_FILTERS_RING_RIGHT - T.DISCOVER_FILTERS_RING
    ring_y = (rh - T.DISCOVER_FILTERS_RING) // 2
    on = "!String.IsEmpty(ListItem.Property(is_on))"
    reset = "!String.IsEmpty(ListItem.Property(is_reset))"

    def row(focused: bool) -> str:
        fill = "$INFO[Window.Property(accent_pill_fill)]" if focused else T.DISCOVER_FILTERS_ROW_FILL
        edge = "$INFO[Window.Property(accent_color)]" if focused else T.DISCOVER_FILTERS_ROW_EDGE
        ink = "$INFO[Window.Property(accent_color)]" if focused else "$INFO[Window.Property(text_primary)]"
        ring = "$INFO[Window.Property(accent_color)]" if focused else T.DISCOVER_FILTERS_RING_REST
        disc = "$INFO[Window.Property(accent_color)]" if focused else "$INFO[Window.Property(text_primary)]"
        tick = "$INFO[Window.Property(on_accent_color)]" if focused else T.CANVAS

        def body(y: int, with_ring: bool) -> str:
            ring_xml = f"""
                        <control type="image">
                            <posx>{ring_x}</posx>
                            <posy>{y + ring_y}</posy>
                            <width>{T.DISCOVER_FILTERS_RING}</width>
                            <height>{T.DISCOVER_FILTERS_RING}</height>
                            <colordiffuse>{ring}</colordiffuse>
                            <texture border="{T.DISCOVER_FILTERS_RING // 2}">capsule-h{T.DISCOVER_FILTERS_RING}-outline.png</texture>
                            <visible>!{on}</visible>
                        </control>
                        <control type="image">
                            <posx>{ring_x}</posx>
                            <posy>{y + ring_y}</posy>
                            <width>{T.DISCOVER_FILTERS_RING}</width>
                            <height>{T.DISCOVER_FILTERS_RING}</height>
                            <colordiffuse>{disc}</colordiffuse>
                            <texture border="{T.DISCOVER_FILTERS_RING // 2}">capsule-h{T.DISCOVER_FILTERS_RING}.png</texture>
                            <visible>{on}</visible>
                        </control>
                        <control type="label">
                            <posx>{ring_x}</posx>
                            <posy>{y + ring_y}</posy>
                            <width>{T.DISCOVER_FILTERS_RING}</width>
                            <height>{T.DISCOVER_FILTERS_RING}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_19</font>
                            <textcolor>{tick}</textcolor>
                            <label>{chr(icon_glyphs.CHECK)}</label>
                            <visible>{on}</visible>
                        </control>""" if with_ring else ""
            return f"""
                        <control type="image">
                            <posx>0</posx>
                            <posy>{y}</posy>
                            <width>{rw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{fill}</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>{y}</posy>
                            <width>{rw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{edge}</colordiffuse>
                            <texture border="14">rounded-14-outline.png</texture>
                        </control>
                        <control type="label">
                            <posx>{T.DISCOVER_FILTERS_LABEL_X}</posx>
                            <posy>{y}</posy>
                            <width>{ring_x - T.DISCOVER_FILTERS_LABEL_X - 12}</width>
                            <height>{rh}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{ink}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>{ring_xml}"""

        gap = T.DISCOVER_FILTERS_RESET_GAP
        return f"""
                    <control type="group">
                        <visible>!{reset}</visible>{body(0, True)}
                    </control>
                    <control type="group">
                        <visible>{reset}</visible>
                        <control type="image">
                            <posx>0</posx>
                            <posy>{gap // 2 - 6}</posy>
                            <width>{rw}</width>
                            <height>1</height>
                            <colordiffuse>{T.DISCOVER_FILTERS_PANEL_EDGE}</colordiffuse>
                            <texture>white-square.png</texture>
                        </control>{body(gap, False)}
                    </control>"""

    top = T.DISCOVER_FILTERS_ROW_Y - T.DISCOVER_FILTERS_PANEL_Y
    rows_h = 3 * T.DISCOVER_FILTERS_PITCH + rh
    panels = ""
    for with_reset in (False, True):
        h = top * 2 + rows_h + (T.DISCOVER_FILTERS_PITCH + T.DISCOVER_FILTERS_RESET_GAP if with_reset else 0)
        gate = ("!" if with_reset else "") + "String.IsEmpty(Window.Property(discover_filter_count))"
        for tex, colour in (("rounded-20.png", T.DISCOVER_FILTERS_PANEL_FILL),
                            ("rounded-20-outline.png", T.DISCOVER_FILTERS_PANEL_EDGE)):
            panels += f"""
                <control type="image">
                    <posx>{T.DISCOVER_FILTERS_PANEL_X}</posx>
                    <posy>{T.DISCOVER_FILTERS_PANEL_Y}</posy>
                    <width>{T.DISCOVER_FILTERS_PANEL_W}</width>
                    <height>{h}</height>
                    <colordiffuse>{colour}</colordiffuse>
                    <texture border="20">{tex}</texture>
                    <visible>{gate}</visible>
                </control>"""
    list_h = 4 * T.DISCOVER_FILTERS_PITCH + T.DISCOVER_FILTERS_RESET_GAP + rh
    pitch = T.DISCOVER_FILTERS_PITCH
    return f"""            <control type="group">
                <visible>!String.IsEmpty(Window.Property(discover_filters_open))</visible>{panels}
                <control type="list" id="{list_id}">
                    <posx>{T.DISCOVER_FILTERS_ROW_X}</posx>
                    <posy>{T.DISCOVER_FILTERS_ROW_Y}</posy>
                    <width>{rw}</width>
                    <height>{list_h}</height>
                    <orientation>vertical</orientation>
                    <onup>{list_id}</onup>
                    <ondown>{list_id}</ondown>
                    <onleft>{list_id}</onleft>
                    <onright>{list_id}</onright>
                    <itemlayout width="{rw}" height="{pitch}">{row(False)}
                    </itemlayout>
                    <focusedlayout width="{rw}" height="{pitch}">{row(True)}
                    </focusedlayout>
                </control>
            </control>"""


# Title page 2's sections, in page order: (key, block id, visibility).
DETAIL_P2_SECTIONS = (
    ("episodes", 5410, "!String.IsEmpty(Window.Property(p2_has_episodes))"),
    ("collection", 5420, "!String.IsEmpty(Window.Property(collection_row_title))"),
    ("cast", 5430, "!String.IsEmpty(Window.Property(has_cast_content))"),
    ("similar", 5440, "!String.IsEmpty(Window.Property(similar_row_title))"),
    ("discover", 5450, "!String.IsEmpty(Window.Property(discover_row_title))"),
    ("about", 5460, ""),
)
DETAIL_P2_GROUPLIST = 5400
DETAIL_ABOUT_BUTTON = 5465


def _p2_header(text: str) -> str:
    return f"""
                        <control type="label">
                            <posx>{T.DETAIL_P2_LEFT - 1}</posx>
                            <width>1200</width>
                            <height>40</height>
                            <font>{T.FONT_BUTTON}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>{text}</label>
                        </control>"""


def _p2_block(key: str, block_id: int, visible: str, content: str) -> str:
    """One screen-tall block plus its spacer; Python sets the heights and the
    content's y once it knows which section comes first (detail._p2_layout)."""
    gate = f"\n                <visible>{visible}</visible>" if visible else ""
    # The episode block is always first and fills the screen from the top.
    y = 0 if key == "episodes" else T.DETAIL_P2_HEADER_Y
    return f"""
                <control type="group" id="{block_id}">
                    <height>{T.SCREEN_H}</height>{gate}
                    <control type="group" id="{block_id + 1}">
                        <posy>{y}</posy>
                        <animation effect="fade" start="100" end="{T.DETAIL_P2_DIM}" time="150" condition="!ControlGroup({block_id}).HasFocus()">Conditional</animation>{content}
                    </control>
                </control>
                <control type="group" id="{block_id + 2}">
                    <height>0</height>{gate}
                </control>"""


def _p2_row(list_id: int, title_property: str, item_xml: str, focused_xml: str) -> str:
    cell_w, cell_h = poster_cell(POSTER_COMPACT)
    return _p2_header(f"$INFO[Window.Property({title_property})]") + f"""
                        <control type="list" id="{list_id}">
                            <posx>{T.DETAIL_P2_LEFT - T.HPAD}</posx>
                            <posy>{T.DETAIL_P2_ROW_LIST_Y}</posy>
                            <width>{T.row_bleed_width(T.DETAIL_P2_LEFT)}</width>
                            <height>{cell_h}</height>
                            <orientation>horizontal</orientation>
                            <itemwidth>{cell_w}</itemwidth>
                            <itemheight>{cell_h}</itemheight>
                            <scrolltime>{T.SCROLLTIME}</scrolltime>
{item_xml}
{focused_xml}
                        </control>"""


def _season_pill(focused: bool, list_id: int) -> str:
    """A season pill: glass at rest, brighter with a rim when it is the
    season shown, an accent rim and label while the pills hold focus."""
    w, h = T.DETAIL_EP_PILL_W, T.DETAIL_EP_PILL_H
    active = "String.IsEqual(ListItem.Property(active),1)"
    focus = f"Control.HasFocus({list_id})" if focused else "false"
    def img(tex: str, colour: str, vis: str) -> str:
        return f"""
                                <control type="image">
                                    <width>{w}</width>
                                    <height>{h}</height>
                                    <colordiffuse>{colour}</colordiffuse>
                                    <texture border="{h // 2}">{tex}</texture>
                                    <visible>{vis}</visible>
                                </control>"""
    def label(colour: str, vis: str) -> str:
        return f"""
                                <control type="label">
                                    <width>{w}</width>
                                    <height>{h}</height>
                                    <align>center</align>
                                    <aligny>center</aligny>
                                    <font>{T.FONT_CAPTION}</font>
                                    <textcolor>{colour}</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                    <visible>{vis}</visible>
                                </control>"""
    body = (img(f"capsule-h{h}.png", T.SURFACE_FAINT, f"!{active}")
            + img(f"capsule-h{h}.png", T.SURFACE_RAISED, active)
            + img(f"capsule-h{h}-outline.png", "0x66FFFFFF", f"{active} + !{focus}")
            + img(f"capsule-h{h}-outline.png", "$INFO[Window.Property(accent_color)]", focus)
            + label("$INFO[Window.Property(accent_color)]", focus)
            + label("$INFO[Window.Property(text_primary)]",
                    f"!{focus} + String.IsEmpty(ListItem.Property(dim))")
            + label("$INFO[Window.Property(text_tertiary)]",
                    f"!{focus} + !String.IsEmpty(ListItem.Property(dim))"))
    tag = "focusedlayout" if focused else "itemlayout"
    cell = w + T.DETAIL_EP_PILL_GAP
    return f"""                        <{tag} width="{cell}" height="{h}">{body}
                        </{tag}>"""


def _hint(y: int, glyph: int, label_y: int, text: str, visible: str) -> str:
    """The centred scroll hint: a chevron and a spaced eyebrow."""
    return f"""
            <control type="group">
                <visible>{visible}</visible>
                <control type="label">
                    <posx>{T.SCREEN_W // 2 - 20}</posx>
                    <posy>{y}</posy>
                    <width>40</width>
                    <height>24</height>
                    <align>center</align>
                    <aligny>center</aligny>
                    <font>tofa_font_icons_24</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>{chr(glyph)}</label>
                </control>
                <control type="label">
                    <posx>{T.SCREEN_W // 2 - 300}</posx>
                    <posy>{label_y}</posy>
                    <width>600</width>
                    <height>22</height>
                    <align>center</align>
                    <font>{T.FONT_EYEBROW}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>{text}</label>
                </control>
            </control>"""


def detail_page2(*, cast_cards, collection_cards, similar_cards, discover_cards,
                 episode_cards) -> str:
    """Title page 2 as one scrolling page (app 2.0.0): the episode block or
    collection, Cast & Crew, More Like This, More to Discover and About."""
    left = T.DETAIL_P2_LEFT
    # Three lines wrapped in Python (detail._sync_episode_block): Kodi has no
    # per-control line spacing, and the app's is 43px.
    synopsis = "".join(f"""
                        <control type="label">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_EP_SYNOPSIS_Y + i * T.DETAIL_EP_SYNOPSIS_PITCH}</posy>
                            <width>{T.DETAIL_EP_SYNOPSIS_W}</width>
                            <height>{T.DETAIL_EP_SYNOPSIS_PITCH}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_EP_SYNOPSIS}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(ep_synopsis_{i + 1})]</label>
                        </control>""" for i in range(3))
    episodes = f"""
                        <control type="label">
                            <posx>{left - 1}</posx>
                            <posy>{T.DETAIL_EP_SHOW_TITLE_Y}</posy>
                            <width>1300</width>
                            <height>56</height>
                            <font>tofa_font_player_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(p2_title)]</label>
                        </control>
                        <control type="group">
                            <!-- The episode's details show only while its row or pills have focus, as in the app. -->
                            <visible>ControlGroup(5410).HasFocus()</visible>
                            <animation effect="fade" time="150">VisibleChange</animation>
                        <control type="label">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_EP_META_Y}</posy>
                            <width>1300</width>
                            <height>32</height>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[Window.Property(ep_meta)]</label>
                        </control>
                        <control type="label">
                            <posx>{left - 2}</posx>
                            <posy>{T.DETAIL_EP_TITLE_Y}</posy>
                            <width>1600</width>
                            <height>80</height>
                            <font>{T.FONT_HERO_TITLE}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(ep_title)]</label>
                        </control>
{synopsis}
                        <control type="image">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_EP_BADGE_Y}</posy>
                            <width>89</width>
                            <height>34</height>
                            <colordiffuse>{T.FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(ep_badge))</visible>
                        </control>
                        <control type="label">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_EP_BADGE_Y}</posy>
                            <width>89</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(ep_badge)]</label>
                        </control>
                        <control type="label">
                            <posx>{left + 107}</posx>
                            <posy>{T.DETAIL_EP_BADGE_Y}</posy>
                            <width>1000</width>
                            <height>34</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[Window.Property(ep_hint)]</label>
                        </control>
                        </control>
                        <control type="list" id="6400">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_EP_PILLS_Y}</posy>
                            <width>{T.SCREEN_W - left}</width>
                            <height>{T.DETAIL_EP_PILL_H}</height>
                            <orientation>horizontal</orientation>
                            <scrolltime>{T.SCROLLTIME}</scrolltime>
{_season_pill(False, 6400)}
{_season_pill(True, 6400)}
                        </control>
                        <control type="list" id="6410">
                            <posx>{left - _EP_PAD}</posx>
                            <posy>{T.DETAIL_EP_ROW_Y - _EP_PAD}</posy>
                            <width>{T.SCREEN_W - left + _EP_PAD + EPISODE_CELL_W}</width>
                            <height>{EPISODE_CELL_H}</height>
                            <orientation>horizontal</orientation>
                            <scrolltime>{T.SCROLLTIME}</scrolltime>
{episode_cards[0]}
{episode_cards[1]}
                        </control>"""
    cast = _p2_header("Cast &amp; Crew") + f"""
                        <control type="list" id="6200">
                            <posx>{left - (T.DETAIL_P2_CAST_CELL - T.DETAIL_P2_CAST_PHOTO) // 2}</posx>
                            <posy>{T.DETAIL_P2_CAST_LIST_Y}</posy>
                            <width>{T.SCREEN_W}</width>
                            <height>260</height>
                            <orientation>horizontal</orientation>
                            <scrolltime>{T.SCROLLTIME}</scrolltime>
{cast_cards[0]}
{cast_cards[1]}
                        </control>"""
    pad = T.DETAIL_P2_ABOUT_PAD
    facts = "".join(f"""
                            <control type="label">
                                <posx>{T.DETAIL_P2_FACT_EYEBROW_X}</posx>
                                <posy>{T.DETAIL_P2_ABOUT_LINE1_Y + i * T.DETAIL_P2_FACT_PITCH}</posy>
                                <width>{T.DETAIL_P2_FACT_VALUE_X - T.DETAIL_P2_FACT_EYEBROW_X - 10}</width>
                                <height>{T.DETAIL_P2_FACT_PITCH}</height>
                                <aligny>center</aligny>
                                <font>{T.FONT_METADATA}</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>$INFO[Window.Property(fact_{i + 1}_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posx>{T.DETAIL_P2_FACT_VALUE_X}</posx>
                                <posy>{T.DETAIL_P2_ABOUT_LINE1_Y + i * T.DETAIL_P2_FACT_PITCH}</posy>
                                <width>{T.DETAIL_P2_ABOUT_W - T.DETAIL_P2_FACT_VALUE_X - pad}</width>
                                <height>{T.DETAIL_P2_FACT_PITCH}</height>
                                <aligny>center</aligny>
                                <font>{T.FONT_METADATA}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_{i + 1}_value)]</label>
                            </control>""" for i in range(6))
    # Tagline, then the synopsis wrapped in Python (detail._render_page2),
    # dropped a line and a bit when there is a tagline, as in the app.
    text_w = T.DETAIL_P2_FACT_EYEBROW_X - pad - 60
    lines = "".join(f"""
                                <control type="label">
                                    <posy>{i * T.DETAIL_P2_ABOUT_PITCH}</posy>
                                    <width>{text_w}</width>
                                    <height>{T.DETAIL_P2_ABOUT_PITCH}</height>
                                    <aligny>center</aligny>
                                    <font>{T.FONT_EP_SYNOPSIS}</font>
                                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                    <label>$INFO[Window.Property(about_line_{i + 1})]</label>
                                </control>""" for i in range(6))
    about_text = f"""
                            <control type="label">
                                <posx>{pad}</posx>
                                <posy>{T.DETAIL_P2_ABOUT_LINE1_Y}</posy>
                                <width>{text_w}</width>
                                <height>{T.DETAIL_P2_ABOUT_PITCH}</height>
                                <aligny>center</aligny>
                                <font>{T.FONT_ROW_TITLE}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>[I]$INFO[Window.Property(about_tagline)][/I]</label>
                            </control>
                            <control type="group">
                                <posx>{pad}</posx>
                                <posy>{T.DETAIL_P2_ABOUT_LINE1_Y}</posy>
                                <animation effect="slide" end="0,{T.DETAIL_P2_ABOUT_TAGLINE_DROP}" time="0" condition="!String.IsEmpty(Window.Property(about_tagline))">Conditional</animation>{lines}
                            </control>"""
    about = _p2_header("About") + f"""
                        <control type="group">
                            <posx>{left}</posx>
                            <posy>{T.DETAIL_P2_ABOUT_Y}</posy>
                            <control type="image">
                                <width>{T.DETAIL_P2_ABOUT_W}</width>
                                <height>{T.DETAIL_P2_ABOUT_H_CARD}</height>
                                <colordiffuse>0x0DFFFFFF</colordiffuse>
                                <texture border="20">rounded-20.png</texture>
                            </control>
                            <control type="image">
                                <width>{T.DETAIL_P2_ABOUT_W}</width>
                                <height>{T.DETAIL_P2_ABOUT_H_CARD}</height>
                                <colordiffuse>0x1AFFFFFF</colordiffuse>
                                <texture border="20">rounded-20-outline.png</texture>
                                <visible>!Control.HasFocus({DETAIL_ABOUT_BUTTON})</visible>
                            </control>
                            <control type="image">
                                <width>{T.DETAIL_P2_ABOUT_W}</width>
                                <height>{T.DETAIL_P2_ABOUT_H_CARD}</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture border="20">rounded-20-outline.png</texture>
                                <visible>Control.HasFocus({DETAIL_ABOUT_BUTTON})</visible>
                            </control>
{about_text}{facts}
                            <control type="button" id="{DETAIL_ABOUT_BUTTON}">
                                <width>{T.DETAIL_P2_ABOUT_W}</width>
                                <height>{T.DETAIL_P2_ABOUT_H_CARD}</height>
                                <texturefocus>transparent-6px.png</texturefocus>
                                <texturenofocus>transparent-6px.png</texturenofocus>
                                <label></label>
                            </control>
                        </control>"""
    contents = {
        "episodes": episodes,
        "collection": _p2_row(6320, "collection_row_title", *collection_cards),
        "cast": cast,
        "similar": _p2_row(6300, "similar_row_title", *similar_cards),
        "discover": _p2_row(6310, "discover_row_title", *discover_cards),
        "about": about,
    }
    blocks = "".join(_p2_block(key, bid, vis, contents[key])
                     for key, bid, vis in DETAIL_P2_SECTIONS)
    top = _hint(26, icon_glyphs.CHEVRON_UP, 52, "OVERVIEW",
                "!String.IsEmpty(Window.Property(p2_at_top))")
    bottom = _hint(1036, icon_glyphs.CHEVRON_DOWN, 1014, "$INFO[Window.Property(p2_next_hint)]",
                   "!String.IsEmpty(Window.Property(p2_next_hint))")
    return f"""            <control type="grouplist" id="{DETAIL_P2_GROUPLIST}">
                <posx>0</posx>
                <posy>0</posy>
                <width>{T.SCREEN_W}</width>
                <height>{T.SCREEN_H}</height>
                <orientation>vertical</orientation>
                <itemgap>{T.DETAIL_P2_GAP}</itemgap>
                <scrolltime>{T.SCROLLTIME}</scrolltime>{blocks}
            </control>{top}{bottom}"""


def discover_row_block(index: int, row_xml: str, header_xml: str = "") -> str:
    """One child of Discover's grouplist: a screen-tall block with its row at
    DISCOVER_FOCUS_ROW_Y, or row 0's shorter block under the sub-tabs."""
    if index:
        h, gate = T.SCREEN_H, f"\n                    <visible>!String.IsEmpty(Window.Property(discover_row{index}_title))</visible>"
    else:
        h, gate = T.DISCOVER_ROW0_H, ""
    return f"""                <control type="group">
                    <height>{h}</height>{gate}
{header_xml}
{row_xml}
                </control>"""


# Discover's focused card is a WIDE backdrop card, not the portrait poster the
# other screens use. Measured off the real app 2026-07-31: unfocused cards keep
# the normal CELL_W pitch, the focused one takes the wide art plus the same
# HPAD either side, and the row reflows around it
# (Kodi's list does honour a wider focusedlayout, verified live before building
# this). Art is 668x378, i.e. 16:9 -- a backdrop, with the title's logo artwork
# over it and BOTH ratings underneath.
#
# 7.9.3 locks the open frame's HEIGHT to the poster height and lets its width
# fall out of 16:9. Doing it the other way round -- width first, height
# derived -- gives the lead card badly wrong proportions, which is why 7.9.3
# rules that order out explicitly. So these are derived in that order, not typed. At
# POSTER_H=378 that is the same 672 they were before.
DISCOVER_FOCUS_ART_H = T.POSTER_H
DISCOVER_FOCUS_ART_W = DISCOVER_FOCUS_ART_H * 16 // 9
DISCOVER_FOCUS_CELL_W = DISCOVER_FOCUS_ART_W + T.ROW_CELL_W - T.POSTER_W


def discover_card(
    list_id: int,
    *,
    caption_field: str = "caption_meta",
) -> tuple[str, str]:
    """(itemlayout, focusedlayout) for a Discover row card.

    itemlayout is the shared portrait poster; focusedlayout is the wide
    backdrop card. The rank chip and watchlist chip ride along on both, so a
    card doesn't lose them on focus.

    Kodi draws a list's SELECTED item through focusedlayout whether or not the
    list holds input focus, and uses that layout's width to lay the row out --
    so a row you've navigated away from keeps its expanded card. That matches
    the real app, which also leaves the previously-selected card wide; what it
    does NOT keep is the focus ring. So the glow and the accent border are the
    only things gated on Control.HasFocus() here, and everything else stays
    unconditional. Gating the whole visual instead would leave a portrait
    poster floating in a 716-wide slot."""
    item_xml, _unused = poster_card(
        list_id,
        has_progress=False,
        caption_field=caption_field,
        extra_item_xml=watchlist_badge_item(),
        extra_focused_xml=watchlist_badge_focused(),
        cell_w=T.ROW_CELL_W,
    )

    # The itemlayout is the poster card's, unwrapped. It briefly carried a
    # group whose only job was to host the CLOSING half of 7.9.5's width
    # swap; that swap is gone (see the note on the focusedlayout below), and
    # a wrapper with nothing to animate is a level of nesting for nothing.

    W, H = DISCOVER_FOCUS_ART_W, DISCOVER_FOCUS_ART_H
    x = HPAD
    # Same caption rhythm as the portrait card, so a focused card's title sits
    # on the same baseline as its neighbours'. Derived from tokens rather than
    # copied from poster_card()'s locals.
    CAPTION_TITLE_TOP = T.TOP_PAD + T.POSTER_H + T.CAPTION_GAP
    CAPTION_TITLE_HEIGHT = T.CAPTION_TITLE_H
    CAPTION_TOP = CAPTION_TITLE_TOP + CAPTION_TITLE_HEIGHT + T.CAPTION_TITLE_GAP
    CELL_HEIGHT = T.CELL_H
    focused = f"""                <focusedlayout width="{DISCOVER_FOCUS_CELL_W}" height="{CELL_HEIGHT}">
                    <control type="group">
                        <width>{DISCOVER_FOCUS_CELL_W}</width>
                        <height>{CELL_HEIGHT}</height>
                        <!-- NO width animation here, deliberately, and it is
                             not for want of trying: the 450ms open/close was
                             built, shipped and then removed on 2026-08-13
                             after Adrian saw it at size ("the shrinking of
                             the artwork in the left card feels weird").

                             The reason it cannot look right is Kodi's, not
                             the implementation's. `zoom` is a RENDER
                             transform, so it squashes the artwork the card
                             is made of instead of narrowing a frame over a
                             still image the way the app does. At the 40%
                             start that is a 2.5x horizontal compression on
                             the first frames. Kodi has no crop-on-resize, so
                             there is no version of this that scales the cell
                             without deforming its picture.

                             7.9.5's reduce-motion clause asks for exactly
                             this: no tween, the card just arrives at the
                             new size. So this is a sanctioned path rather
                             than a gap. The DISSOLVE below stays.

                             Before rebuilding this, read 5bc3af9: the three
                             findings it cost (Conditional not Focus; the
                             direction decides which edge holds still; per
                             ITEM, never per window) are all still true, and
                             none of them was the problem. -->

                    <!-- Focus glow FIRST, behind everything: card-glow.png
                         is a filled soft rect (alpha ~90 throughout), not a
                         hollow ring, so the artwork painted on top covers its
                         inward half and only the outward-fading bleed shows.
                         Drawn last instead it tints the whole card teal, which is
                         exactly what happened first time round.
                         Same technique and asset as poster_visual(). -->
                    <control type="image">
                        <posx>{x - GLOW_PAD}</posx>
                        <posy>{TOP_PAD - GLOW_PAD}</posy>
                        <width>{W + 2 * GLOW_PAD}</width>
                        <height>{H + 2 * GLOW_PAD}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>discover-wide-glow.png</texture>
                        <visible>Control.HasFocus({list_id})</visible>
                    </control>
                    <control type="image">
                        <posx>{x}</posx>
                        <posy>{TOP_PAD}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.SURFACE_PLACEHOLDER}</colordiffuse>
                        <texture diffuse="discover-wide-mask.png">white-square.png</texture>
                    </control>
                    <control type="image">
                        <posx>{x}</posx>
                        <posy>{TOP_PAD}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <aspectratio scalediffuse="false">scale</aspectratio>
                        <texture diffuse="discover-wide-mask.png">$INFO[ListItem.Property(backdrop)]</texture>
                        <!-- 7.9.5's arriving DISSOLVE, and now once again
                             the ONLY half of 7.9.5 this card plays: the
                             width swap was built, shipped and removed
                             (2026-08-13, see the focusedlayout's note). The
                             card just arrives at the new size, which is what
                             7.9.5's reduce-motion clause asks for, and the
                             dissolve is what sells the change.

                             450ms, the WHOLE clock, and it used to be 158.
                             That 158 was 0.35 of the clock, which is what
                             7.9.5 asks for; but the reason it asks is that
                             the incoming backdrop should have resolved
                             BEFORE the frame has finished opening, a lead
                             over a 450ms opening that no longer happens
                             here. With the
                             width gone the dissolve is not racing anything;
                             it IS the swap, so it runs the clock the swap
                             was specified on.

                             This fires once per card PASSED on a scroll,
                             not once per swap, which is why ANIMATION.md
                             gates it on a measurement instead of taste.
                             Measured on the cinema box at both values. -->
                        <animation effect="fade" start="0" end="100" time="450">Visible</animation>
                    </control>
                    <!-- Legibility scrim for the logo and scores. Covers the
                         WHOLE card and runs left-to-right, not bottom-up:
                         7.9.4 gives the copy the left third of the card, so
                         dimming the far corner only dulls artwork that never
                         sits under any text.
                         The old bottom-up fade dimmed the full width of the
                         bottom edge, including the right half no text ever
                         reaches.

                         Stops, strength dial and canvas tint are all baked
                         into the asset by tools/gen_poster_assets.py:
                         gen_discover_open_scrim(), so there's no colordiffuse
                         here and nothing to keep in sync by hand. Built 1:1
                         with the card for the same reason the mask beside it
                         is. -->
                    <control type="image">
                        <posx>{x}</posx>
                        <posy>{TOP_PAD}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <texture diffuse="discover-wide-mask.png">discover-open-scrim.png</texture>
                    </control>
                    <control type="image">
                        <posx>{x + 24}</posx>
                        <posy>{TOP_PAD + H - 150}</posy>
                        <width>260</width>
                        <height>84</height>
                        <aspectratio align="left" aligny="bottom">keep</aspectratio>
                        <texture>$INFO[ListItem.Property(logo)]</texture>
                        <visible>!String.IsEmpty(ListItem.Property(logo))</visible>
                    </control>
                    <!-- Both scores, always: the real app's focused card shows
                         critics AND audience regardless of the profile's
                         preferred_card_rating.

                         One control carries "78 CRITICS 76 AUDIENCE", so the
                         CRITICS/AUDIENCE words take this textcolor while the
                         numerals override it inline (main.py's
                         _discover_open_card_numeral). Tertiary, not primary:
                         the spec puts these labels at white 45% so the
                         numerals carry the line, and our tertiary tier
                         (measured 42%) is that role; a literal 45% would
                         reintroduce exactly the kind of one-off alpha the
                         text-tier consolidation removed.

                         Still divergent: the spec also sets the value at 22
                         and the label at 14 with +0.8 tracking. Two sizes in
                         one Kodi label is not expressible, so that needs the
                         line split into separate value/label controls with
                         measured x offsets, the way Detail's format badges
                         are laid out. -->
                    <control type="label">
                        <posx>{x + 24}</posx>
                        <posy>{TOP_PAD + H - 52}</posy>
                        <width>{W - 48}</width>
                        <height>28</height>
                        <aligny>center</aligny>
                        <font>tofa_font_micro</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>$INFO[ListItem.Property(scores_line)]</label>
                    </control>
                    <!-- Thin solid border, the same treatment the portrait
                         cards in Browse/Home get (poster-border.png). Its own
                         1:1 asset so its radius matches the mask's exactly. -->
                    <control type="image">
                        <posx>{x}</posx>
                        <posy>{TOP_PAD}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>discover-wide-border.png</texture>
                        <visible>Control.HasFocus({list_id})</visible>
                    </control>
                    <!-- Chips sit INSIDE the artwork, inset 11px like the
                         reference. rating_badge()'s own offsets are relative
                         to its parent, so it needs this group rather than
                         landing on the cell's corner (it did, clipped). -->
                    <control type="group">
                        <posx>{x + 3}</posx>
                        <posy>{TOP_PAD + 3}</posy>
{rating_badge()}
                    </control>
{watchlist_badge_focused_wide()}
                    <control type="image">
                        <posx>{HPAD + DISCOVER_FOCUS_ART_W - 11 - 28}</posx>
                        <posy>{TOP_PAD + 11 + 36}</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(cinema_glyph))</visible>
                    </control>
                    <control type="label">
                        <posx>{HPAD + DISCOVER_FOCUS_ART_W - 11 - 28}</posx>
                        <posy>{TOP_PAD + 11 + 36}</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>{T.CINEMA_AMBER}</textcolor>
                        <label>$INFO[ListItem.Property(cinema_glyph)]</label>
                        <visible>!String.IsEmpty(ListItem.Property(cinema_glyph))</visible>
                    </control>
                    <control type="label">
                        <posx>{x + 4}</posx>
                        <posy>{CAPTION_TOP}</posy>
                        <width>{W - 8}</width>
                        <height>24</height>
                        <font>tofa_font_metadata</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property({caption_field})]</label>
                    </control>
                    <control type="label">
                        <posx>{x + 4}</posx>
                        <posy>{CAPTION_TITLE_TOP}</posy>
                        <width>{W - 8}</width>
                        <height>{CAPTION_TITLE_HEIGHT}</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    </control>
                </focusedlayout>"""
    return item_xml, focused


def watchlist_badge_focused_wide() -> str:
    """Watchlist chip pinned to the WIDE focused card's top-right, inset 11px
    inside the artwork like the reference."""
    x = HPAD + DISCOVER_FOCUS_ART_W - 11 - 28
    return f"""                    <control type="image">
                        <posx>{x}</posx>
                        <posy>{TOP_PAD + 11}</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
{badge_glyph_labels(x, TOP_PAD + 11)}"""


# ------------------------------------------------------- card options (7.2) --
# Geometry from 7.2, which is 1:1 with our canvas (its label size 26 is
# exactly FONT_ROW_TITLE, and 7.9's poster/open-card numbers land on ours
# unscaled). Not the half-density scale 3/6 use -- see
# project_spec_number_conventions.
OPTIONS_PANEL_W = 620
OPTIONS_PAD = 32
OPTIONS_ROW_H = 68
OPTIONS_ROW_GAP = 10
OPTIONS_ICON = 24


def option_row(list_id: int) -> tuple[str, str]:
    """Returns (itemlayout, focusedlayout) for one card-options row.

    ListItem properties consumed: Property(icon_glyph), Property(destructive),
    Label.

    Destructive rows are red INK at rest and a red focus wash -- never a red
    fill (7.2, and 2's rule against colour alone carrying a meaning: the row
    still reads as a normal row, the word is what says it's destructive).
    Both states are drawn as separate colour-swapped copies gated on
    Property(destructive), because Kodi cannot branch a <textcolor> on a
    ListItem property inline.

    The gap between rows lives INSIDE the item height rather than in an
    <itemgap>: a Kodi list's focus rectangle is the whole item cell, so a
    real gap would put the focus wash on the gap too."""
    cell_h = OPTIONS_ROW_H + OPTIONS_ROW_GAP
    label_x = OPTIONS_PAD + OPTIONS_ICON + 18

    # 7.2's row lift, on the FOCUSED layout only. Centred on the row's own
    # box so it grows about its middle rather than its top-left corner.
    #
    # This used to be deliberately absent, on the reasoning that "a Kodi-class
    # client is reduced-tier unconditionally" (13). That reading was wrong and
    # is corrected here: 13 is written for "heterogeneous-hardware platforms
    # (Kodi on a Pi)" -- unknowable hardware a client should FAIL CLOSED on --
    # not for the known boxes this add-on runs on. Measured on the cinema box,
    # the far more expensive full-screen hero cross-fade cost nothing at all
    # (100% keep-up, CPU 35-37% driving against 37-40% without it), so a
    # one-shot 1.03 zoom on one row is not the thing to economise on.
    #
    # 150ms and 1.03, both from 7.2 -- deliberately NOT the 140ms/1.045 the
    # content cards use. 5 sets that pair for CONTENT; 7.2 asks for a smaller,
    # slower lift on a chrome row, and the two are different on purpose.
    row_w = OPTIONS_PANEL_W - OPTIONS_PAD * 2
    ROW_ZOOM = (f'\n                        <animation effect="zoom" start="100" '
                f'end="103" center="{row_w // 2},{OPTIONS_ROW_H // 2}" '
                f'time="150" tween="cubic" easing="out">Focus</animation>')

    def _row(focused: bool) -> str:
        # The wash and rim stay at their boosted values (wash 0.26, rim
        # stroked at 2) rather than dropping to 13's full-tier 0.17/1.5. That
        # pairing is 13's COMPENSATION for having no lift, so with the lift
        # back the row now carries both. Left as-is deliberately: changing the
        # resting weight of every options row is a look decision, not a motion
        # one, and it is not what this change is for.
        fill = f"""
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{OPTIONS_PANEL_W - OPTIONS_PAD * 2}</width>
                            <height>{OPTIONS_ROW_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_wash_focus)]</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{OPTIONS_PANEL_W - OPTIONS_PAD * 2}</width>
                            <height>{OPTIONS_ROW_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="14">rounded-14-outline.png</texture>
                        </control>""" if focused else f"""
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{OPTIONS_PANEL_W - OPTIONS_PAD * 2}</width>
                            <height>{OPTIONS_ROW_H}</height>
                            <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>"""

        def _ink(destructive: bool) -> str:
            gate = ("!String.IsEmpty(ListItem.Property(destructive))" if destructive
                    else "String.IsEmpty(ListItem.Property(destructive))")
            colour = "0xFFF87171" if destructive else (
                "$INFO[Window.Property(accent_color)]" if focused
                else "$INFO[Window.Property(text_primary)]"
            )
            return f"""
                        <control type="label">
                            <visible>{gate}</visible>
                            <posx>{OPTIONS_PAD}</posx>
                            <posy>0</posy>
                            <width>{OPTIONS_ICON}</width>
                            <height>{OPTIONS_ROW_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_24}</font>
                            <textcolor>{colour}</textcolor>
                            <label>$INFO[ListItem.Property(icon_glyph)]</label>
                        </control>
                        <control type="label">
                            <visible>{gate}</visible>
                            <posx>{label_x}</posx>
                            <posy>0</posy>
                            <width>{OPTIONS_PANEL_W - OPTIONS_PAD - label_x}</width>
                            <height>{OPTIONS_ROW_H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{colour}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>"""

        tag = "focusedlayout" if focused else "itemlayout"
        body = f"{fill}{_ink(False)}{_ink(True)}"
        if focused:
            # An <animation> has to live on a CONTROL; a <focusedlayout> is
            # not one, so the row's contents get a group to carry the lift.
            # Sized to the row rather than the cell so the zoom centres on
            # the plate the viewer sees, not on the plate plus its gap.
            body = (f"""
                    <control type="group">
                        <width>{row_w}</width>
                        <height>{OPTIONS_ROW_H}</height>{ROW_ZOOM}{body}
                    </control>""")
        return (f"""                <{tag} width="{OPTIONS_PANEL_W - OPTIONS_PAD * 2}" height="{cell_h}">"""
                f"""{body}
                </{tag}>""")

    return _row(False), _row(True)



# ------------------------------------------- Pre-play options (7.7) rows --
# One geometry for BOTH row kinds this dialog draws, so a section header and
# the options under it share a baseline grid. Wider than the card-options
# panel (620) because these rows carry a second column: a commentary track's
# title is the reason anyone opens the Audio section, and at 620 it truncated
# before the word "Commentary".
# One width for both windows this fragment renders, matched to the main nav
# capsule (nav_bar's 1030) so the two plates the user sees most read as the
# same object at the same size.
#
# It used to be 1140, sized to the longest thing either window has to say: an
# audio track named after its commentary credit, "English · Audio Commentary
# by filmmaker and writer Jon Spira…" (Hugo's 4K track after
# tracks.shorten_title()), which measures 745px in tofa_font_row_title. At
# 1030 the label column is 649, so that row no longer fits statically -- the
# focused row marquees instead, which is why the two changes belong together.
PLAYOPT_PANEL_W = 1030
PLAYOPT_PAD = 32
PLAYOPT_ROW_H = 64
PLAYOPT_ROW_GAP = 6
# Leading check column. 7.7 reserves a fixed width for it on every option
# row whether or not that row holds a check, which is what keeps the labels
# in one line down the panel.
PLAYOPT_CHECK_W = 34
PLAYOPT_CHECK_GAP = 14
# Ceiling on VISIBLE rows; beyond it the list scrolls. Nine is what fits
# without the panel starting to feel like a page, and only a subtitle
# section on a disc rip reaches it.
PLAYOPT_MAX_ROWS = 9
# The options panel's detail column holds one short fact per row: a channel
# layout, a bitrate, "Player default". It was 205, sized for "1080p · 44.3
# Mbps" at 191px -- and then 0.9.28's bit depth arrived and "DTS-HD MA 7.1
# 24-bit" (220px) came out as "DTS-HD MA 7.1 24...". Then the three facts
# gained middle dots between them, which is another ~34px: the widest is now
# "TrueHD Atmos . 7.1 . 24-bit" at 278px.
#
# textmetrics IS the right measure here, unlike for a row LABEL: this column
# and the player picker's both use tofa_font_metadata, the one font it
# carries advances for. See feedback_textmetrics_is_one_font.
#
# Every pixel here is taken straight out of the label beside it, which is the
# column actually short of room -- but that label is a language, and this
# panel is 1030 wide, so it can afford 45 of them.
PLAYOPT_DETAIL_W = 285

# The Edition picker is the same panel with a much larger detail column: it
# carries 7.7's full row grammar -- resolution, dynamic range, video codec,
# audio codec and size GB -- where the options panel's details are one short
# fact each. Measured: that string runs ~400px in the common case and ~600px
# on a title whose edition is named AND is 4K AND Dolby Vision AND Atmos, and
# deciding between two editions is exactly when the tail of it matters.
#
# A separate WINDOW rather than a runtime reflow: a Kodi <itemlayout>'s
# internal column positions are baked in at load, so setWidth() on the panel
# would stretch the plate and leave the text where it was. Same PANEL width
# though -- two dialogs one keypress apart on the same action row should not
# be different sizes.
EDITION_DETAIL_W = 600

#: ...and a wider PANEL to put it in, so the NAME column is not the thing
#: that pays for it.
#:
#: At the shared 1030 the name column comes out 254px, and the reference
#: library's edition names do not fit it: "Black and White Version" measures
#: 270. The name is the whole point of the row -- it is what the viewer is
#: choosing between, and in five of that library's six multi-edition titles
#: BOTH editions share a resolution, so the detail column cannot tell them
#: apart either.
#:
#: The 70px does not come out of the detail column, which has none to give:
#: measured across those same titles with 7.7's full grammar, the widest row
#: is "4K . Dolby Vision . HEVC . TrueHD Atmos 7.1 . 69.2 GB" at 555 of its
#: 600. So the panel grows instead, which is the one thing here that is
#: free. It leaves this dialog 70px wider than the options panel it is a
#: keypress away from -- a deliberate exception to their matching sizes,
#: bought for the only column whose content is chosen by a stranger.
EDITION_PANEL_W = PLAYOPT_PANEL_W + 70


def playoptions_geometry(row_count: int, panel_w: int = PLAYOPT_PANEL_W,
                         has_hint: bool = True) -> dict[str, int]:
    """Panel geometry for a given number of visible rows.

    Shared by the renderer, which lays the XML out for the maximum, and by
    the dialog, which shrinks the panel to what it is actually showing every
    time a section opens or closes. Kodi resolves a window's geometry once at
    load, so the collapsed state cannot come from the XML -- but Control
    setPosition/setHeight work fine afterwards, which is how plex-for-kodi's
    dropdown.py sizes its own popups. One function so the two can't drift:
    a mismatch here would be a panel whose fill and whose list disagree
    about where the bottom is."""
    rows = max(1, min(row_count, PLAYOPT_MAX_ROWS))
    pitch = PLAYOPT_ROW_H + PLAYOPT_ROW_GAP
    title_y = PLAYOPT_PAD
    subtitle_y = title_y + 46
    rows_y = subtitle_y + 42
    # The trailing gap of the last row's cell is padding already; counting it
    # again leaves a visibly deeper gutter under the list than over it.
    rows_h = pitch * rows - PLAYOPT_ROW_GAP
    hint_y = rows_y + rows_h + 18
    # No hint, no band. The Edition picker has nothing to say there, and
    # reserving its height anyway left a visibly bottom-heavy panel.
    panel_h = (hint_y + 28 if has_hint else rows_y + rows_h) + PLAYOPT_PAD
    return {
        "PANEL_W": panel_w,
        "PANEL_H": panel_h,
        "PANEL_X": (1920 - panel_w) // 2,
        "PANEL_Y": (1080 - panel_h) // 2,
        "SHADOW_W": panel_w + 84,
        "SHADOW_H": panel_h + 84,
        "PAD": PLAYOPT_PAD,
        "INNER_W": panel_w - PLAYOPT_PAD * 2,
        "TITLE_Y": title_y,
        "SUBTITLE_Y": subtitle_y,
        "ROWS_Y": rows_y,
        "ROWS_H": rows_h,
        "HINT_Y": hint_y,
        "OPT_ROW_PITCH": pitch,
    }


def collapsible_row(list_id: int, panel_w: int = PLAYOPT_PANEL_W,
                    detail_w: int = PLAYOPT_DETAIL_W) -> tuple[str, str]:
    """Returns (itemlayout, focusedlayout) for the pre-play options list,
    which carries two kinds of row in ONE layout:

      section header   Quality            Original ·  2160p          v
      option             [check] 1080p                    8 Mbps

    Gated on Property(section) rather than split across two lists, because
    the whole point of the collapse is that expanding Quality pushes Audio
    and Subtitles DOWN -- they are one scroll, one focus chain, one
    keypress from any row to any other. Two lists could not do that.

    7.7 describes this surface as flat: eyebrow headers with every row of
    every section always visible. That is right for the tvOS app and wrong
    here. Measured on the real Android app 2026-08-01, the flat form is a
    12-row scroll on an ordinary disc rip (6 quality tiers, 2 audio, 3
    subtitle), and the eyebrow that says which section you are in scrolls
    off the top while you are still inside it. Collapsed, the same dialog
    opens as three rows that each state their current value -- which is
    what a viewer came to check most of the time -- and expands only the
    one being changed. The row grammar, check column and accent-wash focus
    are 7.7's unchanged.

    ListItem properties consumed: Label, Property(section), Property(value),
    Property(detail), Property(chevron), Property(check)."""
    inner = panel_w - PLAYOPT_PAD * 2
    cell_h = PLAYOPT_ROW_H + PLAYOPT_ROW_GAP

    # Right-hand furniture, laid out from the right edge in: the chevron
    # column is the anchor and the value column ends just short of it, so a
    # header's value and an option's detail terminate on the same pixel.
    chevron_x = inner - 24 - PLAYOPT_CHECK_W
    right_edge = chevron_x - 14
    # 440, not the 300 this started at. The header's value is the whole
    # point of the collapsed state -- it is what a viewer opened the panel to
    # read -- and at 300 an audio track named after its commentary truncated
    # to "English . Audio Commen...". The header LABEL only ever holds
    # "Quality", "Audio" or "Subtitles", so it can give the room up.
    value_w = min(440, right_edge - 24 - 180)
    value_x = right_edge - value_w
    # An option row draws NO chevron, so it can use the column the header
    # reserves for one -- 48px that were simply blank on every row but the
    # three headers. Both text columns get wider for free, which is what
    # made the Edition rows fit: "1080p · DTS-HD MA 7.1" measures 237px in
    # tofa_font_metadata and was truncating at "DTS-HD M...".
    #
    # The default 260 covers that and the widest quality detail ("1080p ·
    # 44.3 Mbps", 191px; bitrate_label drops the decimal above 100 Mbps so a
    # 4-digit rate cannot grow it). The Edition window passes a much larger
    # one and a wider panel to go with it, since its rows carry 7.7's full
    # grammar rather than one fact.
    detail_x = inner - 24 - detail_w

    option_label_x = 24 + PLAYOPT_CHECK_W + PLAYOPT_CHECK_GAP

    HEADER = "!String.IsEmpty(ListItem.Property(section))"
    OPTION = "String.IsEmpty(ListItem.Property(section))"

    def _row(focused: bool) -> str:
        # Focus state is 7.7's accent wash + rim, in 13's reduced tier form
        # (wash 0.26, rim stroked at 2, no scale lift) -- identical grammar
        # to option_row() above, so the two panels never read as different
        # components.
        if focused:
            fill = f"""
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{inner}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_wash_focus)]</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{inner}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="14">rounded-14-outline.png</texture>
                        </control>"""
            ink = "$INFO[Window.Property(accent_color)]"
            muted = "$INFO[Window.Property(accent_color)]"
        else:
            # Two resting fills, one per row kind: an option sits on the
            # FAINTER plate so an expanded section reads as nested under its
            # header rather than as three more peers of it. Indentation
            # alone did not carry that on a 10-foot screen.
            fill = f"""
                        <control type="image">
                            <visible>{HEADER}</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{inner}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>
                        <control type="image">
                            <visible>{OPTION}</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{inner}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <colordiffuse>{T.SURFACE_FAINT}</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>"""
            ink = "$INFO[Window.Property(text_primary)]"
            muted = "$INFO[Window.Property(text_secondary)]"

        # Marquee the left-hand label, and only on the focused row. A label
        # column of 649 cannot hold a track named after its commentary credit
        # (see PLAYOPT_PANEL_W), and a row the user is standing on is exactly
        # the one whose tail they want. Scrolling every row at once would be
        # a panel that never sits still.
        #
        # No <scrollspeed>: Kodi's default is the same rate the rest of the
        # add-on's marquees run at. The suffix replaces Kodi's default "|",
        # which would draw a literal pipe mid-sentence at the wrap.
        #
        # EM SPACES (U+2003), not ASCII spaces: Kodi's XML parser strips a
        # text node that is nothing but ASCII whitespace, so a suffix of
        # plain spaces silently arrives empty and the label wraps with no gap
        # at all ("...historian Paul Talbot…English · Audio Comm..." reads as
        # one run-on string). U+2003 is not ASCII whitespace, survives the
        # parser, and is an en-width gap each.
        marquee = ("""
                            <scroll>true</scroll>
                            <scrollsuffix>   </scrollsuffix>""" if focused else "")

        return f"""
                        <control type="label">
                            <visible>{HEADER}</visible>
                            <posx>24</posx>
                            <posy>0</posy>
                            <width>{value_x - 24 - 16}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{ink}</textcolor>{marquee}
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>{HEADER}</visible>
                            <posx>{value_x}</posx>
                            <posy>0</posy>
                            <width>{value_w}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <align>right</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>{muted}</textcolor>
                            <label>$INFO[ListItem.Property(value)]</label>
                        </control>
                        <control type="label">
                            <visible>{HEADER}</visible>
                            <posx>{chevron_x}</posx>
                            <posy>0</posy>
                            <width>{PLAYOPT_CHECK_W}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_19}</font>
                            <textcolor>{muted}</textcolor>
                            <label>$INFO[ListItem.Property(chevron)]</label>
                        </control>
                        <control type="label">
                            <visible>{OPTION}</visible>
                            <posx>24</posx>
                            <posy>0</posy>
                            <width>{PLAYOPT_CHECK_W}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_24}</font>
                            <textcolor>{"$INFO[Window.Property(accent_color)]" if not focused else ink}</textcolor>
                            <label>$INFO[ListItem.Property(check)]</label>
                        </control>
                        <control type="label">
                            <visible>{OPTION}</visible>
                            <posx>{option_label_x}</posx>
                            <posy>0</posy>
                            <width>{detail_x - option_label_x - 16}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{ink}</textcolor>{marquee}
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>{OPTION}</visible>
                            <posx>{detail_x}</posx>
                            <posy>0</posy>
                            <width>{detail_w}</width>
                            <height>{PLAYOPT_ROW_H}</height>
                            <align>right</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>{muted}</textcolor>
                            <label>$INFO[ListItem.Property(detail)]</label>
                        </control>""", fill

    def _layout(focused: bool) -> str:
        body, fill = _row(focused)
        tag = "focusedlayout" if focused else "itemlayout"
        return (f"""                <{tag} width="{inner}" height="{cell_h}">"""
                f"""{fill}{body}
                </{tag}>""")

    return _layout(False), _layout(True)


# --------------------------------------------------- Detail action pills --
# Every pill in Detail's action row draws the same way: a leading icon and a
# label, sized as one group and CENTRED in the pill. Before this they had
# four different arrangements -- Play's icon at x=44 with a full-width
# centred label, Options' at x=24 with a left-aligned one, and Rewatch and
# Watchlist with no icon at all (Watchlist put a literal "+" in its text).
#
# Centred as a group rather than left-aligned like Browse's capsules: those
# are one fixed width holding a variable value, so their content must start
# at a fixed inset. These are per-label widths measured off the real app, so
# left-aligning would leave a different-sized hole on the right of each.
# Confirmed against the live app, where each icon+label pair sits mid-pill.
ACTION_ICON_W = 28
ACTION_ICON_GAP = 10

# tofa_font_button (inter_tight_semibold 28) advances, measured with
# PIL.ImageFont.truetype(...).getlength(). Same convention as
# home_rows.DISCOVER_TABS' pill widths: static labels, so measure once
# rather than guess. Recompute if the font or its size changes.
#: Every Detail action pill except the primary one, which stays 360.
#:
#: The app sizes each pill to its own content; Kodi resolves a window's
#: geometry once at load, so we cannot. Per-pill numbers copied from it
#: therefore only held while every label was known at build time, and the
#: edition pill's is a name the SERVER chooses -- which is exactly where it
#: broke. One width holds the longest name in the reference library and
#: retires the 271-vs-270 kind of accident a hand-tuned number invites.
#:
#: 325, not 330: five pills at 330 want 1747px and the row has 1740 (origin
#: 100, content margin 1840). Recorded in DIVERGENCES.md.
ACTION_PILL_W = 325

#: The uniform gap between them, replacing 20/13/14/20.
ACTION_PILL_GAP = 16

#: There was a table of measured label widths here -- Play 53, Options 99,
#: Watchlist 118 and so on -- because the layout centred icon+label+chevron
#: as a group and could not do that without knowing how wide the label was.
#: Nothing measures a label any more (see action_pill_layout), so the table
#: is gone rather than left to rot: every entry in it was a number that had
#: to be re-measured by hand whenever a word changed, and the one label it
#: could never hold was the only one that actually varied.


#: How far the icon and the chevron sit from their pill's ends.
#:
#: The app's own number is 40, measured off atv-reference/
#: detail-watchlist-pill-crop.png at 2x: its Options icon starts 82 from the
#: left and its chevron ends 80 from the right, symmetrically, inside a
#: 258-wide pill.
#:
#: Ours is 24, and the reason is the width we already diverged on. 40 in a
#: 258 pill is 15% of it; the same 40 in our 325 leaves the icon marooned
#: with the text a long way off, which is what "move them closer to the
#: border" is describing. It also buys the label 32px it needs: at 40 the
#: symmetric box below is 169 wide and "Cancel request" (197) does not fit
#: in it.
ACTION_PILL_INSET = 24


def action_pill_layout(pill_width: int,
                       *, trailing: bool = False) -> tuple[int, int, int, int]:
    """(icon_x, label_x, label_w, trailing_x) for one Detail action pill.

    ANCHORED, not group-centred: the icon sits at the left inset, the chevron
    at the right one, and the label is centred in whatever is between. It
    used to lay the three out as one centred GROUP, which is what the app
    does -- and which needs the label's width, which needs the label.

    That was fine while every label was a literal in this file. It stopped
    being fine when the edition pill started showing a name the SERVER
    chooses: the group could only be centred for a measured SAMPLE, so the
    common case drifted off-centre ("1080p" in a box cut for "Theatrical
    Cut" left 94px of dead space on one side), and a name longer than the
    sample overhung the pill.

    Anchoring removes the measurement from the problem entirely. It also
    lines the icons up down the row, which centring never did -- at a uniform
    325 the icons landed at 75, 88, 84, 26 and 45, and the odd one out was
    visible without measuring anything (Adrian spotted Watchlist).

    The cost, stated where it is paid: a short label no longer sits in the
    middle of its PILL, but in the middle of the room the icon and chevron
    leave it. That is the same trade the app avoids by resizing pills at
    runtime, which Kodi cannot do."""
    icon_x = ACTION_PILL_INSET
    label_x = icon_x + ACTION_ICON_W + ACTION_ICON_GAP
    trailing_x = pill_width - ACTION_PILL_INSET - ACTION_ICON_W
    # SYMMETRIC, whether or not there is a chevron: the label box reserves as
    # much on the right as the icon takes on the left, so its centre is the
    # PILL's centre and centred text lands where the eye expects it.
    #
    # It used to run to the right inset when no chevron followed, which put
    # 38 more px on the right of the box than the left and pushed the text
    # that far off-centre -- visible without measuring, on exactly the pills
    # that have no chevron to explain it. A chevron pill was already
    # symmetric by accident, the chevron mirroring the icon.
    #
    # The room given up is real but unused: 201px holds every label in the
    # row, "Cancel request" (197) included.
    label_right = pill_width - label_x
    return icon_x, label_x, max(0, label_right - label_x), trailing_x


def action_pill_content(pill_width: int, label_xml_label: str, glyph: str,
                        *, height: int,
                        trailing_glyph: str | None = None,
                        marquee_focus_id: int | None = None) -> str:
    """Icon at the left inset, chevron at the right, label centred between.

    `label_xml_label` is what goes inside <label> (a literal or an $INFO).
    There is no longer a string to MEASURE: see action_pill_layout for why
    that stopped working and what replaced it.

    `marquee_focus_id` is for the one pill whose label is not ours to keep
    short: the EDITION pill, which shows a name the server chose. "Director's
    Cut Extended Remastered" is an ordinary edition name, and no pill width
    that also leaves room for Play, Options and Watchlist will hold it. So
    that pill's label scrolls while its pill has focus, in the two-copy form
    the cards use -- see poster_visual for why it is two controls with
    complementary gates and not one with <scroll>, and for why the suffix is
    EM SPACE.

    Kodi only marqueees a label that overruns its box, so a short one
    ("1080p", "4K") is unaffected and does not move."""
    icon_x, label_x, label_w, trailing_x = action_pill_layout(
        pill_width, trailing=bool(trailing_glyph))
    trailing_xml = "" if not trailing_glyph else f"""
                            <control type="label">
                                <posx>{trailing_x}</posx>
                                <posy>0</posy>
                                <width>{ACTION_ICON_W}</width>
                                <height>{height}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_ICON_19}</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>{trailing_glyph}</label>
                            </control>"""
    return f"""                            <control type="label">
                                <posx>{icon_x}</posx>
                                <posy>0</posy>
                                <width>{ACTION_ICON_W}</width>
                                <height>{height}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_ICON_24}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>{glyph}</label>
                            </control>
{_action_pill_label(label_x, label_w, height, label_xml_label, marquee_focus_id)}{trailing_xml}"""


def _action_pill_label(label_x: int, label_w: int, height: int,
                       label_xml_label: str, marquee_focus_id: int | None) -> str:
    """The pill's text: one control, or two complementary ones to marquee.

    ALWAYS centred, because the box is no longer cut to the string: every
    label now gets the whole span between the icon and the chevron (see
    action_pill_layout), and left-aligning in that would push "4K" hard
    against the icon with 150px of nothing after it.

    Centring is safe next to <scroll>: Kodi only scrolls a label that
    overruns its box, and a label that overruns has no slack left to centre
    within. So the two never apply at once."""
    body = """
                                <align>center</align>
                                <posy>0</posy>
                                <width>{w}</width>
                                <height>{h}</height>
                                <aligny>center</aligny>
                                <font>{font}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>""".format(
        w=label_w, h=height, font=T.FONT_BUTTON)
    if marquee_focus_id is None:
        return f"""                            <control type="label">
                                <posx>{label_x}</posx>{body}
                                <label>{label_xml_label}</label>
                            </control>"""
    return f"""                            <control type="label">
                                <visible>Control.HasFocus({marquee_focus_id})</visible>
                                <posx>{label_x}</posx>{body}
                                <scroll>true</scroll>
                                <scrollsuffix>   </scrollsuffix>
                                <label>{label_xml_label}</label>
                            </control>
                            <control type="label">
                                <visible>!Control.HasFocus({marquee_focus_id})</visible>
                                <posx>{label_x}</posx>{body}
                                <label>{label_xml_label}</label>
                            </control>"""


def collection_row(list_id: int) -> tuple[str, str]:
    """One row of the collections view: up to three 16:9 cards (app 2.0).

    A row is one list item, so a fixedlist can hold the focused row in place
    the way the app does; Window.Property(browse_coll_col) says which card
    has focus, and a short row lends it to its last card.

    Art, in order: the backdrop; else four member posters, top-cropped, 2x2;
    else one poster, centre-cropped; else a film glyph."""
    W, H, P = T.COLLECTION_TILE_W, T.COLLECTION_TILE_H, T.COLLECTION_PAD
    QW, QH = W // 2, H // 2
    col = "Window.Property(browse_coll_col)"

    def _focus(i: int) -> str:
        return (f"Control.HasFocus({list_id}) + [String.IsEqual({col},{i}) | "
                f"[String.IsEqual(ListItem.Property(last),{i}) + "
                f"Integer.IsGreater({col},{i})]]")

    def _img(texture: str, visible: str, *, w=W, h=H, x=0, y=0, mask="collection-mask.png",
             aspect="scale", diffuse="", top=False) -> str:
        tint = f"\n                            <colordiffuse>{diffuse}</colordiffuse>" if diffuse else ""
        keep = ' align="center" aligny="center"' if aspect == "keep" else ""
        keep = ' aligny="top"' if top else keep
        return f"""
                        <control type="image">
                            <visible>{visible}</visible>
                            <posx>{x}</posx>
                            <posy>{y}</posy>
                            <width>{w}</width>
                            <height>{h}</height>{tint}
                            <aspectratio scalediffuse="false"{keep}>{aspect}</aspectratio>
                            <texture diffuse="{mask}">{texture}</texture>
                        </control>"""

    def _tile(i: int, focused: bool) -> str:
        c = f"c{i}"
        prop = lambda name: f"ListItem.Property({c}{name})"  # noqa: E731
        has = f"!String.IsEmpty({prop('')})"
        art, poster, m1 = (f"!String.IsEmpty({prop(n)})" for n in ("_art", "_poster", "_m1"))
        no_art = f"String.IsEmpty({prop('_art')})"
        cropped = f"{no_art} + String.IsEmpty({prop('_m1')}) + {poster}"
        x, cx, cy = P + i * T.COLLECTION_PITCH_X, W // 2, H // 2
        glow = rim = zoom = ""
        if focused:
            gate = _focus(i)
            glow = f"""
                        <control type="image">
                            <visible>{gate}</visible>
                            <posx>-{GLOW_PAD}</posx>
                            <posy>-{GLOW_PAD}</posy>
                            <width>{W + 2 * GLOW_PAD}</width>
                            <height>{H + 2 * GLOW_PAD}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>collection-glow.png</texture>
                        </control>"""
            rim = f"""
                        <control type="image">
                            <visible>{gate}</visible>
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>collection-border.png</texture>
                        </control>"""
            zoom = (f"\n                        <animation effect=\"zoom\" start=\"100\" end=\"104\" "
                    f"center=\"{x + cx},{P + cy}\" time=\"140\" tween=\"cubic\" easing=\"out\" "
                    f"condition=\"{gate}\">Conditional</animation>")
        quads = "".join(
            _img(f"$INFO[{prop('_m' + str(n + 1))}]", f"{no_art} + {m1}", w=QW, h=QH,
                 x=(n % 2) * QW, y=(n // 2) * QH, mask=f"collection-quad-{q}.png", top=True)
            for n, q in enumerate(("tl", "tr", "bl", "br")))
        card = f"""
                    <control type="group">
                        <visible>{has}</visible>
                        <posx>{x}</posx>
                        <posy>{P}</posy>{zoom}{glow}{_img("white-square.png", "true", diffuse=T.COLLECTION_PLATE)}
                        <control type="label">
                            <visible>{no_art} + String.IsEmpty({prop('_m1')}) + String.IsEmpty({prop('_poster')})</visible>
                            <width>{W}</width>
                            <height>{H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_56}</font>
                            <textcolor>0x47FFFFFF</textcolor>
                            <label>&#x{icon_glyphs.FILM:04X};</label>
                        </control>{_img(f"$INFO[{prop('_poster')}]", cropped)}{quads}{_img(f"$INFO[{prop('_art')}]", art)}
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>0x1FFFFFFF</colordiffuse>
                            <texture>collection-hairline.png</texture>
                        </control>{rim}
                    </control>"""
        return card + _caption(i, x, has, focused)

    def _caption(i: int, x: int, has: str, focused: bool) -> str:
        """Name and count under the card; a long name marquees on focus only."""
        top = P + H + T.COLLECTION_CAPTION_Y

        def _title(gate: str, scroll: bool) -> str:
            marquee = ("""
                        <scroll>true</scroll>
                        <scrollsuffix>\u2003\u2003\u2003</scrollsuffix>""" if scroll else "")
            return f"""
                    <control type="label">
                        <visible>{gate}</visible>
                        <posx>{x}</posx>
                        <posy>{top}</posy>
                        <width>{W}</width>
                        <height>{T.CAPTION_TITLE_H}</height>
                        <font>{T.FONT_CARD_TITLE}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>{marquee}
                        <label>$INFO[ListItem.Property(c{i})]</label>
                    </control>"""
        title = (_title(f"{has} + {_focus(i)}", True)
                 + _title(f"{has} + ![{_focus(i)}]", False)) if focused else _title(has, False)
        return title + f"""
                    <control type="label">
                        <visible>{has}</visible>
                        <posx>{x}</posx>
                        <posy>{top + T.COLLECTION_META_DY}</posy>
                        <width>{W}</width>
                        <height>26</height>
                        <font>{T.FONT_BROWSE_CAPTION}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[ListItem.Property(c{i}_meta)]</label>
                    </control>"""

    size = f'width="{T.COLLECTION_LIST_W}" height="{T.COLLECTION_PITCH_Y}"'
    tiles = lambda focused: "".join(_tile(i, focused) for i in range(T.COLLECTION_COLS))  # noqa: E731
    return (f"                <itemlayout {size}>{tiles(False)}\n                </itemlayout>",
            f"                <focusedlayout {size}>{tiles(True)}\n                </focusedlayout>")


# ======================================================================
# Settings (9) -- the sidebar, the detail pane's rows, and the QR rail.
# ======================================================================
#
# Two focus treatments live on this screen and they are NOT the same, which
# is the thing most likely to get "fixed" back to wrong. Both sampled off
# internal-docs/atv-reference/:
#
#   sidebar row      solid accent fill, DARK label      (59C3BD / 104D51)
#   detail-pane row  accent-tinted glass, ACCENT label  (254145 / 73C2BE)
#
# 6 wants the second one filled with the accent and lettered dark -- that is
# true of the sidebar and not of the detail pane. The shipped app disagrees
# with its own spec here and the app wins (feedback_apple_tv_source_of_truth).


def settings_action_row(list_id: int, width: int = T.SETTINGS_DETAIL_W) -> tuple[str, str]:
    """A focusable one-line row with a trailing glyph (Switch Profile, Sign
    Out), as a one-item list so the grouplist scrolls it into view.

    `destructive` on the ListItem turns the title and glyph red. Every focus
    layer is gated on Control.HasFocus: a one-item list's item is always
    "selected", so Kodi draws its focusedlayout even while focus is away."""
    H = T.SETTINGS_ACTION_ROW_H
    TEXT_X = 27
    GLYPH_X = width - 76
    TEXT_W = GLYPH_X - TEXT_X - 16

    def _labels(title_color: str, glyph_color: str, gate: str = "") -> str:
        focus = f"{gate} + " if gate else ""
        red = "String.IsEqual(ListItem.Property(destructive),1)"
        return f"""
                    <control type="label">
                        <visible>{focus}!{red}</visible>
                        <posx>{TEXT_X}</posx>
                        <posy>0</posy>
                        <width>{TEXT_W}</width>
                        <height>{H}</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_ROW}</font>
                        <textcolor>{title_color}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>{focus}{red}</visible>
                        <posx>{TEXT_X}</posx>
                        <posy>0</posy>
                        <width>{TEXT_W}</width>
                        <height>{H}</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_ROW}</font>
                        <textcolor>{T.STATUS_RED}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>{focus}!{red}</visible>
                        <posx>{GLYPH_X}</posx>
                        <posy>{H // 2 - 18}</posy>
                        <width>36</width>
                        <height>36</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_26}</font>
                        <textcolor>{glyph_color}</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                    </control>
                    <control type="label">
                        <visible>{focus}{red}</visible>
                        <posx>{GLYPH_X}</posx>
                        <posy>{H // 2 - 18}</posy>
                        <width>36</width>
                        <height>36</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_26}</font>
                        <textcolor>{T.STATUS_RED}</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                    </control>"""

    card = _settings_row_card(width, H)
    item = f"""                <itemlayout width="{width}" height="{H}">{card}{_labels(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]")}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{width}" height="{H}">{card}{
                        _settings_row_focus(list_id, width, H)}{_labels(
                        "$INFO[Window.Property(accent_color)]",
                        "$INFO[Window.Property(accent_color)]",
                        gate=f"Control.HasFocus({list_id})")}{_labels(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        gate=f"!Control.HasFocus({list_id})")}
                </focusedlayout>"""
    return item, focused


def _settings_row_card(width: int, height: int) -> str:
    """A Settings row's resting glass."""
    return f"""
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{height}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>"""


def _settings_row_focus(list_id: int, width: int, height: int) -> str:
    """The focused row's accent wash and rim, only while `list_id` has focus."""
    return f"""
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{height}</height>
                        <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{height}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="20">rounded-20-outline.png</texture>
                    </control>"""


def settings_value_row(*, posy: int, label: str, value_property: str,
                       width: int = T.SETTINGS_DETAIL_W,
                       height: int = T.SETTINGS_VALUE_ROW_H,
                       card_height: int | None = None,
                       indent: str = "                ") -> str:
    """A read-only detail-pane row: label left, value right, both on the row's
    vertical centre. Email / Server / Libraries are these.

    Not focusable and not a list -- there is nothing to activate, and leaving
    it out of the focus order is what lets the D-pad run straight from one
    real control to the next. It is also visibly quieter than
    settings_action_row(): PANEL_WASH against that one's SURFACE_REST,
    the app's own 4%-vs-8% split. That contrast is the only thing telling
    "Sign Out" from "Signed in as" before either is focused, so the two fills
    have to be changed together or not at all.

    `card_height` paints a fill taller than the row itself, for the first of
    several rows sharing one card (Server over Libraries): the text still
    centres on its own `height`, while the background covers the whole card.
    `card_height=0` paints none at all, for the rows after that first one."""
    # Outside a list, Kodi takes a right-aligned label's posx as its RIGHT edge.
    TEXT_X = 27
    fill_h = height if card_height is None else card_height
    background = f"""
{indent}<control type="image">
{indent}    <posx>0</posx>
{indent}    <posy>0</posy>
{indent}    <width>{width}</width>
{indent}    <height>{fill_h}</height>
{indent}    <colordiffuse>{T.PANEL_WASH}</colordiffuse>
{indent}    <texture border="20">rounded-20.png</texture>
{indent}</control>""" if fill_h else ""
    return f"""{indent}<control type="group">
{indent}    <posx>0</posx>
{indent}    <posy>{posy}</posy>{background}
{indent}    <control type="label">
{indent}        <posx>{TEXT_X}</posx>
{indent}        <posy>0</posy>
{indent}        <width>{width // 2}</width>
{indent}        <height>{height}</height>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_SETTINGS_ROW}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>{label}</label>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posx>{width - 27}</posx>
{indent}        <posy>0</posy>
{indent}        <width>{width // 2 - 40}</width>
{indent}        <height>{height}</height>
{indent}        <align>right</align>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_SETTINGS_VALUE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>$INFO[Window.Property({value_property})]</label>
{indent}    </control>
{indent}</control>"""


def settings_name_row(*, posy: int, title: str, subtitle: tuple[str, ...],
                      width: int = T.SETTINGS_DETAIL_W,
                      height: int = T.SETTINGS_ABOUT_NAME_H,
                      card_height: int | None = None,
                      indent: str = "                ") -> str:
    """A name over a quieter note about it, the note given as ALREADY-BROKEN
    lines.

    Unlike settings_value_row, everything is on the LEFT and nothing is a
    Window.Property: this is fixed text about the add-on itself, so baking it
    into the rendered XML is honest (nothing at runtime can change what the
    add-on is called or whether it is official).

    `subtitle` is a tuple of lines, not a sentence, because neither Kodi text
    control does what is wanted here: <label> will not wrap at all, and
    <textbox> wraps where it likes -- see SETTINGS_ABOUT_NAME_SUB_LINES for the
    measured split it chose and why it was rejected. Callers own the break, so
    it can be balanced.

    Written for ABOUT's "tofa for Kodi" over its unofficial-status note, and
    shares a card with the Version row below it the way Server shares one with
    Libraries -- hence the same `card_height` escape hatch."""
    TEXT_X = 27
    fill_h = height if card_height is None else card_height
    background = f"""
{indent}<control type="image">
{indent}    <posx>0</posx>
{indent}    <posy>0</posy>
{indent}    <width>{width}</width>
{indent}    <height>{fill_h}</height>
{indent}    <colordiffuse>{T.PANEL_WASH}</colordiffuse>
{indent}    <texture border="20">rounded-20.png</texture>
{indent}</control>""" if fill_h else ""
    sub_lines = "".join(f"""
{indent}    <control type="label">
{indent}        <posx>{TEXT_X}</posx>
{indent}        <posy>{T.SETTINGS_ABOUT_NAME_SUB_Y + i * T.SETTINGS_ABOUT_NAME_SUB_H}</posy>
{indent}        <width>{width - TEXT_X * 2}</width>
{indent}        <height>{T.SETTINGS_ABOUT_NAME_SUB_H}</height>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_METADATA}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>{line}</label>
{indent}    </control>""" for i, line in enumerate(subtitle))
    return f"""{indent}<control type="group">
{indent}    <posx>0</posx>
{indent}    <posy>{posy}</posy>{background}
{indent}    <control type="label">
{indent}        <posx>{TEXT_X}</posx>
{indent}        <posy>{T.SETTINGS_ABOUT_NAME_TITLE_Y}</posy>
{indent}        <width>{width - TEXT_X * 2}</width>
{indent}        <height>{T.SETTINGS_ABOUT_NAME_TITLE_H}</height>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_ROW_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>{title}</label>
{indent}    </control>{sub_lines}
{indent}</control>"""


def settings_group_eyebrow(*, posy: int, label: str,
                           indent: str = "                ") -> str:
    """The uppercase group label above a card (PROFILE, SESSION, SERVER...).

    `posy` is the CARD's top; the label is placed above it by the measured
    rise, so callers only ever have to think about where the card goes."""
    return f"""{indent}<control type="label">
{indent}    <posx>0</posx>
{indent}    <posy>{posy - T.SETTINGS_GROUP_EYEBROW_RISE - 12}</posy>
{indent}    <width>{T.SETTINGS_DETAIL_W_WIDE}</width>
{indent}    <height>28</height>
{indent}    <aligny>center</aligny>
{indent}    <font>{T.FONT_EYEBROW}</font>
{indent}    <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
{indent}    <label>{label}</label>
{indent}</control>"""


def settings_qr_rail(*, eyebrow: str, texture: str, caption_property: str,
                     indent: str = "            ") -> str:
    """The right-hand rail: an eyebrow, then a glass panel holding the QR card
    and its caption.

    The QR is a fixed 292px asset with its white card and radius-20 corners
    baked in (tools/gen_qr_assets.py), so it is drawn at exactly that size and
    never stretched -- it is not a 9-patch and border-stretching one bulges
    its corners (project_kodi_9patch_needs_straight_edges).

    The caption is a textbox, not a label: it is three lines and a Kodi label
    does not wrap, it ellipsises. FONT_METADATA rather than FONT_BODY because
    the app's caption measures ~22px, and at FONT_BODY's 24 the same sentence
    takes four lines and the last one falls off the panel."""
    qr_x = (T.SETTINGS_RAIL_W - T.SETTINGS_QR) // 2
    return f"""{indent}<control type="label">
{indent}    <posx>{T.SETTINGS_RAIL_X}</posx>
{indent}    <posy>{T.SETTINGS_RAIL_Y - T.SETTINGS_GROUP_EYEBROW_RISE - 12}</posy>
{indent}    <width>{T.SETTINGS_RAIL_W}</width>
{indent}    <height>28</height>
{indent}    <aligny>center</aligny>
{indent}    <font>{T.FONT_EYEBROW}</font>
{indent}    <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
{indent}    <label>{eyebrow}</label>
{indent}</control>
{indent}<control type="group">
{indent}    <posx>{T.SETTINGS_RAIL_X}</posx>
{indent}    <posy>{T.SETTINGS_RAIL_Y}</posy>
{indent}    <control type="image">
{indent}        <posx>0</posx>
{indent}        <posy>0</posy>
{indent}        <width>{T.SETTINGS_RAIL_W}</width>
{indent}        <height>{T.SETTINGS_RAIL_PANEL_H}</height>
{indent}        <colordiffuse>{T.SURFACE_FAINT}</colordiffuse>
{indent}        <texture border="20">rounded-20.png</texture>
{indent}    </control>
{indent}    <control type="image">
{indent}        <posx>{qr_x}</posx>
{indent}        <posy>{T.SETTINGS_QR_Y - T.SETTINGS_RAIL_Y}</posy>
{indent}        <width>{T.SETTINGS_QR}</width>
{indent}        <height>{T.SETTINGS_QR}</height>
{indent}        <texture>{texture}</texture>
{indent}    </control>
{indent}    <control type="textbox">
{indent}        <posx>22</posx>
{indent}        <posy>{T.SETTINGS_QR_CAPTION_Y - T.SETTINGS_RAIL_Y}</posy>
{indent}        <width>{T.SETTINGS_RAIL_W - 44}</width>
{indent}        <height>94</height>
{indent}        <align>center</align>
{indent}        <font>{T.FONT_METADATA}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>$INFO[Window.Property({caption_property})]</label>
{indent}    </control>
{indent}</control>"""


def settings_fox_tile(list_id: int) -> tuple[str, str]:
    """One tile of the fox picker (app 2.0): the preset's logo over its name
    on glass tinted its own colour.

    The current fox adds a rim and a check badge, the focused one a stronger
    tint. Each item carries its colours as properties (tile_color/_wash/
    _current/_focus), since a tile shows its own hue, not the live accent."""
    W, H = T.SETTINGS_FOX_TILE_W, T.SETTINGS_FOX_TILE_H
    ART = 80
    current = "String.IsEqual(ListItem.Property(selected),1)"

    def _tile(fill: str, rim: bool, label_font: str, label_colour: str) -> str:
        ring = f"""
                    <control type="image">
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[ListItem.Property(tile_color)]</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>""" if rim else ""
        return f"""
                    <control type="image">
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[ListItem.Property({fill})]</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>{ring}
                    <control type="image">
                        <posx>{(W - ART) // 2}</posx>
                        <posy>16</posy>
                        <width>{ART}</width>
                        <height>{ART}</height>
                        <aspectratio>keep</aspectratio>
                        <texture>$INFO[ListItem.Art(thumb)]</texture>
                    </control>
                    <control type="label">
                        <posy>{H - 50}</posy>
                        <width>{W}</width>
                        <height>32</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{label_font}</font>
                        <textcolor>{label_colour}</textcolor>
                        <label>$INFO[ListItem.Label2]</label>
                    </control>"""

    badge = f"""
                    <control type="group">
                        <visible>{current}</visible>
                        <control type="image">
                            <posx>{W - 34}</posx>
                            <posy>8</posy>
                            <width>26</width>
                            <height>26</height>
                            <colordiffuse>$INFO[ListItem.Property(tile_color)]</colordiffuse>
                            <texture>circle.png</texture>
                        </control>
                        <control type="label">
                            <posx>{W - 34}</posx>
                            <posy>8</posy>
                            <width>26</width>
                            <height>26</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_19}</font>
                            <textcolor>{T.CANVAS}</textcolor>
                            <label>&#x{icon_glyphs.CHECK:04X};</label>
                        </control>
                    </control>"""
    white = "$INFO[Window.Property(text_primary)]"
    grey = "$INFO[Window.Property(text_secondary)]"

    def _states(focused: bool) -> str:
        rest = f"""
                    <control type="group">
                        <visible>!{current}</visible>{_tile("tile_wash", False, T.FONT_BODY, grey)}
                    </control>
                    <control type="group">
                        <visible>{current}</visible>{_tile("tile_current", True, T.FONT_POSTER_TITLE, white)}
                    </control>"""
        if not focused:
            return rest + badge
        return f"""
                    <control type="group">
                        <visible>!Control.HasFocus({list_id})</visible>{rest}
                    </control>
                    <control type="group">
                        <visible>Control.HasFocus({list_id})</visible>{_tile(
                            "tile_focus", True, T.FONT_POSTER_TITLE, white)}
                    </control>{badge}"""

    cell = f'width="{T.SETTINGS_FOX_CELL_W}" height="{T.SETTINGS_FOX_CELL_H}"'
    item = f"""                <itemlayout {cell}>{_states(False)}
                </itemlayout>"""
    focused = f"""                <focusedlayout {cell}>{_states(True)}
                </focusedlayout>"""
    return item, focused


def _settings_control_row(list_id: int, *, trailing: str, trailing_focused: str = "",
                          trailing_w: int = 360,
                          width: int = T.SETTINGS_DETAIL_W_WIDE,
                          height: int = T.SETTINGS_ACTION_ROW_H) -> tuple[str, str]:
    """The body shared by the toggle and choice rows: glass, focus wash and
    rim, and a one-line title, with `trailing` against the right edge.

    `trailing_focused` replaces `trailing` in the focusedlayout, for a value
    that turns accent with its row."""
    TEXT_X = 27
    TEXT_W = width - TEXT_X - trailing_w

    def _title(colour: str, gate: str = "") -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="label">{vis}
                        <posx>{TEXT_X}</posx>
                        <posy>0</posy>
                        <width>{TEXT_W}</width>
                        <height>{height}</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_ROW}</font>
                        <textcolor>{colour}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>"""

    card = _settings_row_card(width, height)
    item = f"""                <itemlayout width="{width}" height="{height}">{card}{_title(
                        "$INFO[Window.Property(text_primary)]")}{trailing}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{width}" height="{height}">{card}{
                        _settings_row_focus(list_id, width, height)}{_title(
                        "$INFO[Window.Property(accent_color)]",
                        f"Control.HasFocus({list_id})")}{_title(
                        "$INFO[Window.Property(text_primary)]",
                        f"!Control.HasFocus({list_id})")}{trailing_focused or trailing}
                </focusedlayout>"""
    return item, focused


def _settings_switch(width: int, height: int) -> str:
    """The app's capsule switch at a row's right edge: 64x38, a white knob,
    the accent track when the item is `checked`. The knob cannot slide in
    Kodi, so two parked knobs swap."""
    SW, SH, KNOB = 64, 38, 32
    X = width - 27 - SW
    Y = (height - SH) // 2
    on = "String.IsEqual(ListItem.Property(checked),1)"
    return f"""
                    <control type="image">
                        <posx>{X}</posx>
                        <posy>{Y}</posy>
                        <width>{SW}</width>
                        <height>{SH}</height>
                        <colordiffuse>{T.SURFACE_TRACK}</colordiffuse>
                        <texture border="19">capsule-h38.png</texture>
                    </control>
                    <control type="image">
                        <visible>{on}</visible>
                        <posx>{X}</posx>
                        <posy>{Y}</posy>
                        <width>{SW}</width>
                        <height>{SH}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="19">capsule-h38.png</texture>
                    </control>
                    <control type="image">
                        <visible>!{on}</visible>
                        <posx>{X + 3}</posx>
                        <posy>{Y + 3}</posy>
                        <width>{KNOB}</width>
                        <height>{KNOB}</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>circle.png</texture>
                    </control>
                    <control type="image">
                        <visible>{on}</visible>
                        <posx>{X + SW - KNOB - 3}</posx>
                        <posy>{Y + 3}</posy>
                        <width>{KNOB}</width>
                        <height>{KNOB}</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>circle.png</texture>
                    </control>"""


def settings_toggle_row(list_id: int, **kwargs) -> tuple[str, str]:
    """A row whose value is on/off, drawn as the app's capsule switch.
    Our own art rather than Kodi's <radiobutton>, whose art is the host skin's."""
    W = kwargs.get("width", T.SETTINGS_DETAIL_W_WIDE)
    H = kwargs.get("height", T.SETTINGS_ACTION_ROW_H)
    return _settings_control_row(list_id, trailing=_settings_switch(W, H),
                                 trailing_w=64 + 54, **kwargs)


def settings_home_row_editor(slot: int, group_id: int, list_id: int,
                             width: int = T.SETTINGS_DETAIL_W_WIDE) -> str:
    """Slot `slot` of Home's row editor (app 2.0): the row's name, "Shown" or
    "Hidden" (Label2) and a switch; Select opens the row's menu in the picker.

    Its own grouplist child so the grouplist scrolls it into view; the group
    hides on an empty title property, which also drops it from the chain."""
    H = T.SETTINGS_ACTION_ROW_H
    first = slot == 0
    state_x = width - 27 - 64 - 16 - 240

    def _state(colour: str, gate: str = "") -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="label">{vis}
                        <posx>{state_x}</posx>
                        <width>240</width>
                        <height>{H}</height>
                        <align>right</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_VALUE}</font>
                        <textcolor>{colour}</textcolor>
                        <label>$INFO[ListItem.Label2]</label>
                    </control>"""

    switch = _settings_switch(width, H)
    grey = "$INFO[Window.Property(text_secondary)]"
    item, focused = _settings_control_row(
        list_id, trailing=_state(grey) + switch,
        trailing_focused=(_state("$INFO[Window.Property(accent_color)]",
                                 f"Control.HasFocus({list_id})")
                          + _state(grey, f"!Control.HasFocus({list_id})") + switch),
        trailing_w=width - state_x, width=width)
    eyebrow = settings_group_eyebrow(
        posy=T.SETTINGS_SECTION_BAND, label="ROWS, IN ORDER",
        indent="                        ") + "\n" if first else ""
    return f"""
                    <control type="group" id="{group_id}">
                        <visible>!String.IsEmpty(Window.Property(homerow_{slot}_title))</visible>
                        <width>{width}</width>
                        <height>{T.SETTINGS_HOMEROW_FIRST_H if first else T.SETTINGS_HOMEROW_PITCH}</height>
{eyebrow}                        <control type="list" id="{list_id}">
                            <posy>{T.SETTINGS_SECTION_BAND if first else 0}</posy>
                            <width>{width}</width>
                            <height>{H}</height>
                            <onleft>{list_id}</onleft>
                            <onright>{list_id}</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{H}</itemheight>
                            <scrolltime>0</scrolltime>
{item}
{focused}
                        </control>
                    </control>"""


def settings_choice_row(list_id: int, *, value_property: str,
                        dot_values: tuple = (), dot_colour: str = "",
                        **kwargs) -> tuple[str, str]:
    """A row whose value is one of several, shown as "value >" and picked in
    the right-column picker (app 2.0). The value turns accent with its row.

    `dot_values` puts a `dot_colour` dot before each of those values, placed
    from its text width at render time: a list layout cannot move a control."""
    W = kwargs.get("width", T.SETTINGS_DETAIL_W_WIDE)
    H = kwargs.get("height", T.SETTINGS_ACTION_ROW_H)
    dots = ""
    for value in dot_values:
        width = textmetrics.text_width(value) * 28 / textmetrics.SIZE
        dots += f"""
                    <control type="image">
                        <visible>String.IsEqual(Window.Property({value_property}),{value})</visible>
                        <posx>{int(W - 57 - width - 12 - 16)}</posx>
                        <posy>{(H - 16) // 2}</posy>
                        <width>16</width>
                        <height>16</height>
                        <colordiffuse>{dot_colour}</colordiffuse>
                        <texture>circle.png</texture>
                    </control>"""

    def _trailing(colour: str, gate: str = "") -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="label">{vis}
                        <posx>{W - 57 - 460}</posx>
                        <posy>0</posy>
                        <width>460</width>
                        <height>{H}</height>
                        <align>right</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_VALUE}</font>
                        <textcolor>{colour}</textcolor>
                        <label>$INFO[Window.Property({value_property})]</label>
                    </control>
                    <control type="label">{vis}
                        <posx>{W - 52}</posx>
                        <posy>0</posy>
                        <width>36</width>
                        <height>{H}</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_29}</font>
                        <textcolor>{colour}</textcolor>
                        <label>&#x{icon_glyphs.CHEVRON_RIGHT:04X};</label>
                    </control>"""

    rest = dots + _trailing("$INFO[Window.Property(text_secondary)]")
    focused = (dots + _trailing("$INFO[Window.Property(accent_color)]",
                                f"Control.HasFocus({list_id})")
               + _trailing("$INFO[Window.Property(text_secondary)]",
                           f"!Control.HasFocus({list_id})"))
    return _settings_control_row(list_id, trailing=rest, trailing_focused=focused,
                                 trailing_w=460 + 57, **kwargs)


def settings_choice_list(list_id: int, *, value_property: str, posy: int,
                         onup: int, ondown: int,
                         width: int = T.SETTINGS_DETAIL_W_WIDE, **row) -> str:
    """A whole one-item list holding a settings_choice_row."""
    H = T.SETTINGS_ACTION_ROW_H
    item, focused = settings_choice_row(list_id, value_property=value_property,
                                        width=width, **row)
    return f"""
                        <control type="list" id="{list_id}">
                            <posx>0</posx>
                            <posy>{posy}</posy>
                            <width>{width}</width>
                            <height>{H}</height>
                            <onup>{onup}</onup>
                            <ondown>{ondown}</ondown>
                            <onleft>{list_id}</onleft>
                            <onright>{list_id}</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{H}</itemheight>
                            <scrolltime>0</scrolltime>
{item}
{focused}
                        </control>"""


def settings_picker_panel() -> str:
    """The app 2.0 picker: a panel over the top of the right column with the
    row's title and its options, the current one ticked, the rest of the
    column dimmed. windows/main.py sizes 8992/8993/8990 to the options."""
    x, y = T.SETTINGS_DETAIL_X, T.SETTINGS_PICKER_Y
    w = T.SETTINGS_DETAIL_W
    lw = w - 2 * T.SETTINGS_PICKER_PAD
    rh = T.SETTINGS_PICKER_ROW_H
    max_h = T.SETTINGS_PICKER_MAX_ROWS * T.SETTINGS_PICKER_PITCH
    panel_h = T.SETTINGS_PICKER_LIST_Y + max_h - 3 + T.SETTINGS_PICKER_FOOT
    current = "String.IsEqual(ListItem.Property(current),1)"
    has_detail = "!String.IsEmpty(ListItem.Property(detail))"

    def _row(colour: str, rim: str, wash: str = "") -> str:
        fill = f"""
                        <control type="image">
                            <width>{lw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{wash}</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>""" if wash else f"""
                        <control type="image">
                            <width>{lw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{T.SETTINGS_PICKER_ROW}</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>
                        <control type="image">
                            <visible>{current}</visible>
                            <width>{lw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{T.SETTINGS_PICKER_CURRENT}</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>"""
        return fill + f"""
                        <control type="image">
                            <visible>{current if not wash else "true"}</visible>
                            <width>{lw}</width>
                            <height>{rh}</height>
                            <colordiffuse>{rim}</colordiffuse>
                            <texture border="20">rounded-20-outline.png</texture>
                        </control>
                        <control type="label">
                            <posx>27</posx>
                            <width>{lw - 220}</width>
                            <height>{rh}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_SETTINGS_OPTION}</font>
                            <textcolor>{colour}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>{has_detail}</visible>
                            <posx>{lw - 90 - 160}</posx>
                            <width>160</width>
                            <height>{rh}</height>
                            <align>right</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_SETTINGS_VALUE}</font>
                            <textcolor>{colour if wash else "$INFO[Window.Property(text_secondary)]"}</textcolor>
                            <label>$INFO[ListItem.Property(detail)]</label>
                        </control>
                        <control type="label">
                            <visible>{current}</visible>
                            <posx>{lw - 60}</posx>
                            <width>36</width>
                            <height>{rh}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_29}</font>
                            <textcolor>{colour}</textcolor>
                            <label>&#x{icon_glyphs.CHECK:04X};</label>
                        </control>"""

    item = _row("$INFO[Window.Property(text_primary)]", T.SETTINGS_PICKER_CURRENT_RIM)
    focused = _row("$INFO[Window.Property(accent_color)]",
                   "$INFO[Window.Property(accent_color)]",
                   wash="$INFO[Window.Property(settings_row_wash)]")
    fox_item, fox_focused = settings_fox_tile(8200)
    mode = "String.IsEqual(Window.Property(settings_picker),{0})".format
    return f"""
            <control type="group">
                <visible>!String.IsEmpty(Window.Property(settings_picker))</visible>
                <control type="image">
                    <posx>{x - 40}</posx>
                    <posy>{T.SETTINGS_CONTENT_Y - 60}</posy>
                    <width>{T.SCREEN_W - x + 40}</width>
                    <height>{T.SCREEN_H - T.SETTINGS_CONTENT_Y + 60}</height>
                    <colordiffuse>{T.SETTINGS_PICKER_DIM}</colordiffuse>
                    <texture>white-square.png</texture>
                </control>
                <control type="group">
                    <posx>{x}</posx>
                    <posy>{y}</posy>
                    <control type="image" id="8992">
                        <!-- resized-at-runtime -->
                        <width>{w}</width>
                        <height>{panel_h}</height>
                        <colordiffuse>{T.SETTINGS_PICKER_FILL}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>
                    <control type="image" id="8993">
                        <!-- resized-at-runtime -->
                        <width>{w}</width>
                        <height>{panel_h}</height>
                        <colordiffuse>{T.SETTINGS_PICKER_RIM}</colordiffuse>
                        <texture border="20">rounded-20-outline.png</texture>
                    </control>
                    <control type="label">
                        <posx>27</posx>
                        <posy>26</posy>
                        <width>{w - 54}</width>
                        <height>44</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_SETTINGS_PICKER}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(settings_picker_title)]</label>
                    </control>
                    <control type="label">
                        <posx>{w - 27}</posx>
                        <posy>26</posy>
                        <width>{w // 2}</width>
                        <height>44</height>
                        <align>right</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_BODY}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(settings_picker_hint)]</label>
                    </control>
                    <control type="panel" id="8200">
                        <visible>{mode("fox")}</visible>
                        <posx>{T.SETTINGS_PICKER_PAD}</posx>
                        <posy>{T.SETTINGS_PICKER_LIST_Y}</posy>
                        <width>{T.SETTINGS_FOX_COLS * T.SETTINGS_FOX_CELL_W}</width>
                        <height>{T.SETTINGS_FOX_ROWS * T.SETTINGS_FOX_CELL_H}</height>
                        <onup>8200</onup>
                        <ondown>8200</ondown>
                        <onleft>8200</onleft>
                        <onright>8200</onright>
                        <orientation>vertical</orientation>
                        <itemwidth>{T.SETTINGS_FOX_CELL_W}</itemwidth>
                        <itemheight>{T.SETTINGS_FOX_CELL_H}</itemheight>
                        <scrolltime>{T.SCROLLTIME}</scrolltime>
{fox_item}
{fox_focused}
                    </control>
                    <control type="list" id="8990">
                        <visible>{mode("list")}</visible>
                        <posx>{T.SETTINGS_PICKER_PAD}</posx>
                        <posy>{T.SETTINGS_PICKER_LIST_Y}</posy>
                        <width>{lw}</width>
                        <height>{max_h}</height>
                        <onup>8990</onup>
                        <ondown>8990</ondown>
                        <onleft>8990</onleft>
                        <onright>8990</onright>
                        <orientation>vertical</orientation>
                        <itemheight>{T.SETTINGS_PICKER_PITCH}</itemheight>
                        <scrolltime>{T.SCROLLTIME}</scrolltime>
                        <itemlayout width="{lw}" height="{T.SETTINGS_PICKER_PITCH}">{item}
                        </itemlayout>
                        <focusedlayout width="{lw}" height="{T.SETTINGS_PICKER_PITCH}">{focused}
                        </focusedlayout>
                    </control>
                </control>
            </control>"""


def settings_note_card(*, posy: int, title: str, body_property: str,
                       width: int = T.SETTINGS_DETAIL_W,
                       height: int = T.SETTINGS_NOTE_CARD_H,
                       indent: str = "                        ") -> str:
    """A card that only EXPLAINS something -- a title over wrapped prose, no
    control of any kind.

    Not focusable, so it stays out of the D-pad order entirely, and drawn on
    PANEL_WASH like the other read-only surfaces rather than the brighter
    fill an actionable row gets.

    A <textbox>, because a Kodi label does not wrap; see settings_qr_rail for
    the same reasoning."""
    return f"""{indent}<control type="group">
{indent}    <posx>0</posx>
{indent}    <posy>{posy}</posy>
{indent}    <control type="image">
{indent}        <posx>0</posx>
{indent}        <posy>0</posy>
{indent}        <width>{width}</width>
{indent}        <height>{height}</height>
{indent}        <colordiffuse>{T.PANEL_WASH}</colordiffuse>
{indent}        <texture border="20">rounded-20.png</texture>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posx>27</posx>
{indent}        <posy>18</posy>
{indent}        <width>{width - 54}</width>
{indent}        <height>34</height>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_ROW_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>{title}</label>
{indent}    </control>
{indent}    <control type="textbox">
{indent}        <posx>27</posx>
{indent}        <posy>56</posy>
{indent}        <width>{width - 54}</width>
{indent}        <height>{height - 70}</height>
{indent}        <font>{T.FONT_METADATA}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>$INFO[Window.Property({body_property})]</label>
{indent}    </control>
{indent}</control>"""


def splash_wipe(*, prefix: str, count: int, x: int, y: int, width: int,
                height: int, start: int, wipe: int, fade: int, ease: bool,
                indent: str = "        ", per_fox: bool = False) -> str:
    """One left-to-right wipe, as `count` strips that fade in one after another.

    Kodi has no clip or mask animation -- a texture is always drawn whole -- so
    an image cannot be uncovered in place by any single control. Cutting it
    into vertical strips and staggering their WindowOpen fades is the only way
    to reproduce the apps' reveal, and it costs no extra pixels: the strips
    ARE the image (see tools/gen_splash_assets.py).

    Each strip gets its own `delay`, so Kodi drives the whole animation and
    nothing here needs a Python timer.

    THE STRIPS ARE NOT EVENLY WIDE, and laying them out as if they were is
    what put a visible dent in the mark's right end. gen_splash_assets.py
    cuts at a FIXED SPLASH_STRIP_W and the last strip is whatever is left
    over: the fox mark is 13 strips of 16 units plus a runt of 5, the
    wordmark 10 of 16 plus 13. This used to divide `width` into `count`
    equal shares instead, so every control was ~15.2 units wide -- which
    squashed the 13 full strips to 0.94x and stretched that 5-unit runt to
    3.0x, since `aspectratio=stretch` scales each texture into whatever box
    it is given. The seams between the squashed strips read as the mark
    being 1-2px out; the runt read as a dent.

    Mirroring the generator's own arithmetic makes every control exactly as
    wide as its texture, so `stretch` becomes a 1:1 blit."""
    step = T.SPLASH_STRIP_W
    out = []
    for index in range(count):
        left = min(index * step, width)
        right = min(left + step, width)
        delay = T.splash_strip_delay(index, count, start, wipe, ease)
        # per_fox: the strip set is chosen at RUNTIME, because which fox the
        # splash wears is the last profile's accent and this XML is rendered
        # once at build time. $INFO's three-argument form wraps the property in
        # a prefix and postfix, so one property picks all 14 strips; the
        # alternative was 14 properties each holding a whole filename.
        #
        # It also fails safe in the one way that matters: an unset property
        # makes $INFO yield NOTHING rather than "splash-mark--00.png", so a
        # splash that somehow opens before the property is written draws an
        # empty mark instead of a missing-texture box. windows/splash.py sets
        # it before the window is shown, and defaults it to the Tofa fox.
        texture = (f"$INFO[Window.Property({T.SPLASH_FOX_PROPERTY}),{prefix}-,-{index:02d}.png]"
                   if per_fox else f"{prefix}-{index:02d}.png")
        out.append(f"""{indent}<control type="image">
{indent}    <posx>{x + left}</posx>
{indent}    <posy>{y}</posy>
{indent}    <width>{right - left}</width>
{indent}    <height>{height}</height>
{indent}    <aspectratio>stretch</aspectratio>
{indent}    <texture>{texture}</texture>
{indent}    <animation effect="fade" start="0" end="100" time="{fade}" delay="{delay}" tween="sine" easing="out">WindowOpen</animation>
{indent}</control>""")
    return "\n".join(out)


# 8.9's toast: geometry in one place, because the PLAYER's copy of this
# block is hand-written. script-tofa-player.xml is a static screen, so it
# cannot call this function; test_toast_surface.py asserts the two agree on
# everything that matters rather than trusting them to.
TOAST_W = 1100
TOAST_H = 52          # capsule-h52 -> border=26, see gen_capsule_pill_assets
TOAST_X = (1920 - TOAST_W) // 2
TOAST_Y = 40
TOAST_PAD_H = 18      # 8.9: "pad 18h/10v"
TOAST_FADE_IN = 180
TOAST_FADE_OUT = 250  # 8.9 wants every toast fading in under 300ms
TOAST_PROPERTY = "tofa_toast"


def toast(indent: str = "        ") -> str:
    """8.9's transient message toast: a top-centre capsule.

    8.9 fixes the shape -- black 60%, 18h/10v of padding, semibold white,
    every toast fading in under 300ms -- and parks it above centre so it
    can never run into the clock in the top bar. The auto-quality toast is
    deliberately not shown (see player.py:_auto_skip -- the viewer
    configured it, so announcing it is noise); this is that same capsule
    carrying the messages that USED to be Kodi's own notification popup.

    READ FROM WINDOW 10000, NOT THE CURRENT WINDOW. The background service
    is a separate process from every window, and window properties are the
    only store both can reach -- the same one the seekbar patch and the
    splash marker use. That is also why the condition names the window
    explicitly: an unqualified Window.Property() resolves against whatever
    is topmost, which for a toast raised during playback is the player
    dialog rather than the store the service wrote to.

    Place it LAST in a window, so it draws over everything.

    FIXED WIDTH, AND A MARQUEE WHEN THAT IS NOT ENOUGH. Auto-width is
    effectively impossible in Kodi (it offers it only inside list layouts),
    so the spec's 18h padding is exact only for a message that fills the
    capsule. Adrian's call, 2026-08-11: fixed width is accepted, and long
    text scrolls rather than truncating -- which matters here because some
    of these strings are server-supplied error text of no known length.
    Recorded in internal-docs/DIVERGENCES.md.
    """
    return f"""{indent}<control type="group">
{indent}    <visible>!String.IsEmpty(Window(10000).Property({TOAST_PROPERTY}))</visible>
{indent}    <animation effect="fade" start="0" end="100" time="{TOAST_FADE_IN}">Visible</animation>
{indent}    <animation effect="fade" start="100" end="0" time="{TOAST_FADE_OUT}">Hidden</animation>
{indent}    <control type="image">
{indent}        <posx>{TOAST_X}</posx>
{indent}        <posy>{TOAST_Y}</posy>
{indent}        <width>{TOAST_W}</width>
{indent}        <height>{TOAST_H}</height>
{indent}        <colordiffuse>{T.BADGE_SCRIM}</colordiffuse>
{indent}        <texture border="{TOAST_H // 2}">capsule-h{TOAST_H}.png</texture>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posx>{TOAST_X + TOAST_PAD_H}</posx>
{indent}        <posy>{TOAST_Y}</posy>
{indent}        <width>{TOAST_W - 2 * TOAST_PAD_H}</width>
{indent}        <height>{TOAST_H}</height>
{indent}        <align>center</align>
{indent}        <valign>center</valign>
{indent}        <font>{T.FONT_BUTTON}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <scroll>true</scroll>
{indent}        <scrollsuffix>\u2003\u2003\u2003</scrollsuffix>
{indent}        <label>$INFO[Window(10000).Property({TOAST_PROPERTY})]</label>
{indent}    </control>
{indent}</control>"""
