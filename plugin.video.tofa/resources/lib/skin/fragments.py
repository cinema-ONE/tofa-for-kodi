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

from . import icon_glyphs
from . import tokens as T


def logo_block() -> str:
    """Fox icon + "tofa" wordmark, top-left (70x70, tofa_font_row_title),
    used by every screen that has this block. Sign-in's icon-only variant
    (no wordmark, its own size/position) is deliberately separate and not
    part of this fragment.

    posx 150, not the page margin itself: the logo artwork carries ~6px of
    transparent padding, so the glyph's ink lands on Home's 156 the same way
    the hero title below it does. Measured, both in our render and in
    internal-docs/atv-reference/home-full.png."""
    return """        <control type="image">
            <posx>150</posx>
            <posy>45</posy>
            <width>70</width>
            <height>70</height>
            <aspectratio>keep</aspectratio>
            <texture>$INFO[Window.Property(logo_file)]</texture>
        </control>
        <control type="label">
            <posx>228</posx>
            <posy>45</posy>
            <width>200</width>
            <height>70</height>
            <aligny>center</aligny>
            <font>tofa_font_row_title</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>tofa</label>
        </control>"""


def nav_bar(
    *,
    ondown_target: int,
    list_id: int = 3000,
    group_id: int = 2000,
    group_posx: int = 440,
    group_posy: int = 46,
) -> str:
    """The top nav pill cluster: background panel + the 5-tab list. Same
    markup on every screen that has one; the only thing that legitimately
    varies per screen is `ondown_target` (where focus lands moving off the
    nav into that screen's own content).

    group_posx=440, not the true screen-centered value (445): shifted 5px
    left so the nav panel's left edge lines up with Browse's Sort pill and
    poster grid (both posx=440)."""
    return f"""        <control type="group" id="{group_id}">
            <posx>{group_posx}</posx>
            <posy>{group_posy}</posy>
            <control type="image">
                <width>1030</width>
                <height>68</height>
                <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                <texture border="34">capsule-h68.png</texture>
            </control>
            <control type="image">
                <width>1030</width>
                <height>68</height>
                <colordiffuse>{T.SURFACE_RAISED}</colordiffuse>
                <texture border="34">capsule-h68-outline.png</texture>
            </control>

            <control type="list" id="{list_id}">
                <posx>4</posx>
                <posy>2</posy>
                <width>1022</width>
                <height>64</height>
                <orientation>horizontal</orientation>
                <itemwidth>204</itemwidth>
                <itemheight>64</itemheight>
                <onleft>{list_id}</onleft>
                <onright>{list_id}</onright>
                <ondown>{ondown_target}</ondown>
                <itemlayout width="204" height="64">
                    <!-- Box must be >= the font's point size, or Kodi
                         renders a degenerate dot instead of the glyph. -->
                    <control type="label">
                        <posx>27</posx>
                        <posy>11</posy>
                        <width>42</width>
                        <height>42</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_36</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                    </control>
                    <control type="label">
                        <posx>74</posx>
                        <width>120</width>
                        <height>64</height>
                        <align>left</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                </itemlayout>
                <!-- Kodi keeps rendering the list's SELECTED item via
                     focusedlayout even after the list loses window focus,
                     so itemlayout above never actually applies to the
                     current tab; the focused/blurred distinction lives
                     here instead, split on Control.HasFocus(list_id). -->
                <focusedlayout width="204" height="64">
                    <!-- Full-size pill: nav bar has literal focus. Also
                         shown via Window.Property(nav_closing) while this
                         window is closing after a tab switch (set by
                         windows/*.py's _open_nav_target() before opening
                         the target window), so the tab doesn't visibly
                         shrink to the small pill on the way out. -->
                    <control type="image">
                        <posy>2</posy>
                        <width>204</width>
                        <height>60</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture border="30">capsule-h60.png</texture>
                        <visible>Control.HasFocus({list_id}) | !String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>
                    <control type="label">
                        <posx>27</posx>
                        <posy>11</posy>
                        <width>42</width>
                        <height>42</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_36</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                        <visible>Control.HasFocus({list_id}) | !String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>
                    <control type="label">
                        <posx>74</posx>
                        <width>120</width>
                        <height>64</height>
                        <align>left</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>Control.HasFocus({list_id}) | !String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>

                    <!-- Smaller pill: tab still selected but nav bar no
                         longer has literal focus. Insets 8px evenly on all
                         sides from the full pill's bounds; a fixed-size
                         asset (nav-pill-small.png, 188x44) rather than a
                         percentage scale of capsule-pill.png, to keep the
                         margin even on all four sides. -->
                    <control type="image">
                        <posx>8</posx>
                        <posy>10</posy>
                        <width>188</width>
                        <height>44</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture>nav-pill-small.png</texture>
                        <visible>!Control.HasFocus({list_id}) + String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>
                    <control type="label">
                        <posx>35</posx>
                        <posy>11</posy>
                        <width>42</width>
                        <height>42</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_36</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                        <visible>!Control.HasFocus({list_id}) + String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>
                    <control type="label">
                        <posx>82</posx>
                        <width>104</width>
                        <height>64</height>
                        <align>left</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>!Control.HasFocus({list_id}) + String.IsEmpty(Window.Property(nav_closing))</visible>
                    </control>
                </focusedlayout>
            </control>
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


def watchlist_badge_item() -> str:
    """Circular +/checkmark badge, top-right, Discover-only (its items
    aren't necessarily in the library yet, so need a way to add them).
    28x28, same 8px edge inset as the rating badge."""
    return f"""                    <control type="image">
                        <posx>{CHIP_X}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
                    <control type="image">
                        <posx>{CHIP_X}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.BORDER_SOFT}</colordiffuse>
                        <texture border="14">capsule-h28-outline.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
{badge_glyph_labels(CHIP_X, 8)}
                    <control type="image">
                        <posx>{CHIP_X}</posx>
                        <posy>44</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(cinema_glyph))</visible>
                    </control>
                    <control type="label">
                        <posx>{CHIP_X}</posx>
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


def watchlist_badge_focused() -> str:
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
    return f"""                    <control type="image">
                        <posx>{CHIP_X}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.CANVAS_CHIP}</colordiffuse>
                        <texture border="14">capsule-h28.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
                    <control type="image">
                        <posx>{CHIP_X}</posx>
                        <posy>8</posy>
                        <width>28</width>
                        <height>28</height>
                        <colordiffuse>{T.BORDER_SOFT}</colordiffuse>
                        <texture border="14">capsule-h28-outline.png</texture>
                        <visible>!String.IsEmpty(ListItem.Property(watchlist_glyph))</visible>
                    </control>
{badge_glyph_labels(CHIP_X, 8)}"""


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


def poster_placeholder(zoom_anim: str = "") -> str:
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
    return f"""                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{T.POSTER_W}</width>
                            <height>{T.POSTER_H}</height>
                            <texture diffuse="poster-mask.png">poster-placeholder.png</texture>{zoom_anim}
                        </control>
                        <control type="group">
                            <visible>String.IsEmpty(ListItem.Art(poster))</visible>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{T.POSTER_PLACEHOLDER_ICON_Y}</posy>
                                <width>{T.POSTER_W}</width>
                                <height>{T.POSTER_PLACEHOLDER_ICON_H}</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{T.FONT_ICON_56}</font>
                                <textcolor>{T.POSTER_PLACEHOLDER_INK}</textcolor>
                                <label>&#x{icon_glyphs.FILM:04X};</label>{zoom_anim}
                            </control>
                            <control type="label">
                                <posx>{T.POSTER_PLACEHOLDER_PAD}</posx>
                                <posy>{T.POSTER_PLACEHOLDER_TITLE_Y}</posy>
                                <width>{T.POSTER_W - T.POSTER_PLACEHOLDER_PAD * 2}</width>
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
    ZOOM = (f'center="{T.POSTER_W // 2},{T.POSTER_H // 2}" '
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
        return f"""
                    <!-- 6's progress bar: bottom-aligned INSIDE the poster,
                         touching its left, bottom and right edges, track
                         white 10% under a flat accent fill.

                         posy is computed, never typed. It was once the
                         literal 362, correct for the 248x372 poster of the
                         day; the card later grew to {T.POSTER_W}x{T.POSTER_H}
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
                        <posy>{T.POSTER_H - _POSTER_BAR_H}</posy>
                        <width>{T.POSTER_W}</width>
                        <height>{_POSTER_BAR_H}</height>
                        <colordiffuse>{T.CARD_PROGRESS_TRACK}</colordiffuse>
                        <texture>poster-progress/100.png</texture>{zoom_anim}
                    </control>
                    <control type="image">
                        <visible>!String.IsEmpty(ListItem.Property(progress_pct))</visible>
                        <posx>0</posx>
                        <posy>{T.POSTER_H - _POSTER_BAR_H}</posy>
                        <width>{T.POSTER_W}</width>
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
{poster_placeholder()}
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{T.POSTER_W}</width>
                            <height>{T.POSTER_H}</height>
                            <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                            <texture diffuse="poster-mask.png">$INFO[ListItem.Art(poster)]</texture>
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
                            <width>{T.POSTER_W + 2 * GLOW_PAD}</width>
                            <height>{T.POSTER_H + 2 * GLOW_PAD}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>card-glow.png</texture>
                            <!-- Centre is POSTER_W/2, matching the poster
                                 and border rather than this control's own
                                 width: an animation centre is expressed in
                                 the PARENT's coordinates, and this control
                                 starts at -10, so its true centre is
                                 -10 + (POSTER_W + 20)/2 = POSTER_W/2. Using
                                 its own half-width put the centre 10px down
                                 and right, which zoomed the halo about a
                                 different point than the card it wraps. -->
                            <animation effect="zoom" start="100" end="104.5" center="{T.POSTER_W // 2},{T.POSTER_H // 2}" time="140" tween="cubic" easing="out">Focus</animation>
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
{poster_placeholder(zoom_anim)}
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{T.POSTER_W}</width>
                            <height>{T.POSTER_H}</height>
                            <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                            <texture diffuse="poster-mask.png">$INFO[ListItem.Art(poster)]</texture>
                            <animation effect="zoom" start="100" end="104.5" center="{T.POSTER_W // 2},{T.POSTER_H // 2}" time="140" tween="cubic" easing="out">Focus</animation>
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
                            <width>{T.POSTER_W}</width>
                            <height>{T.POSTER_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>poster-border.png</texture>
                            <animation effect="zoom" start="100" end="104.5" center="{T.POSTER_W // 2},{T.POSTER_H // 2}" time="140" tween="cubic" easing="out">Focus</animation>
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
    CAPTION_TITLE_TOP = TOP_PAD + T.POSTER_H + T.CAPTION_GAP
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
    CAPTION_W = T.POSTER_W - 8

    item_visual, focused_visual = poster_visual(
        list_id,
        has_progress=has_progress,
        extra_item_xml=extra_item_xml,
        extra_focused_xml=extra_focused_xml,
        hide_rating_on_focus=hide_rating_on_focus,
    )

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
                        <width>{T.POSTER_W - 8}</width>
                        <height>{T.CAPTION_META_H + T.CAPTION_BOTTOM - _MICRO_BASELINE_DROP}</height>
                        <align>right</align>
                        <font>{T.FONT_MICRO}</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>$INFO[ListItem.Property(caption_trailing)]</label>
                    </control>"""

    item = f"""                <itemlayout width="{T.CELL_W}" height="{CELL_HEIGHT}">
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

    focused = f"""                <focusedlayout width="{T.CELL_W}" height="{CELL_HEIGHT}">
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
    cell_width: int = T.CAST_TILE,
    cell_height: int = T.CAST_TILE,
    photo_size: int = T.CAST_PHOTO,
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
                </focusedlayout>"""

    return item, focused


EPISODE_CELL_W, EPISODE_CELL_H = T.EPISODE_CELL_W, T.EPISODE_CELL_H
# 320, not 270: row-to-row gap widened to match Browse's own poster grid
# (~124px between poster rows on the real Apple TV app); ~134px art-to-art
# here once _EP_PAD is factored in.
EPISODE_THUMB_W, EPISODE_THUMB_H = 330, 186
# HPAD/TOP_PAD/glow bleed all share one value here (unlike poster_visual's
# HPAD=20 vs GLOW_PAD=10): the cell only has exactly 20px of horizontal
# slack (350-330), none to spare beyond exactly what the glow needs not to
# clip. See tools/gen_episode_assets.py.
_EP_PAD = 10


def episode_card(list_id: int) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for a 16:9 episode
    thumbnail card, Detail's Episodes tab grid. Same technique as
    poster_visual() (exact-size mask/border/glow assets rather than a
    stretched 9-slice, see tools/gen_episode_assets.py), adapted for a
    landscape 330x186 still instead of a portrait poster.

    ListItem properties consumed: Art(thumb), Property(has_thumb),
    Property(caption), Property(watched), Label (title)."""
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

    def _overlays(anim: str) -> str:
        return f"""
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
                    <control type="label">
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


def _pill_label(label_prefix: str, label_property: str) -> str:
    """A Browse pill's text: "Genre: Action", or the bare value.

    An EMPTY prefix hands the whole line to the window, and the 71px the
    word would have taken with it. Sort and Filter both take that deal now;
    Genre is the only pill still carrying a prefix, because its own values
    are bare nouns and "All" alone would not say what it was all of.

    The measurement behind it, off the shipped font (inter_tight_semibold
    26) against the 248px the label column actually has:

        Filter: Unwatched                 207px   fits
        Filter: Unwatched, 2020s          296px   Kodi cuts it to
                                                  "Filter: In Progress, ..."
        Unwatched, 2020s                  225px   fits whole

    -- which is why a Browse filtered on two axes could only ever show the
    first one. Nothing is lost by dropping the word: each pill keeps its own
    glyph, and an active filter keeps the accent fill that says so. The
    window puts the bare word "Filter" back when there is nothing to name.
    """
    value = f"$INFO[ListItem.Property({label_property})]"
    return f"{label_prefix}: {value}" if label_prefix else value


def browse_pill(
    list_id: int,
    *,
    icon: str,
    label_prefix: str,
    label_property: str,
    always_active: bool = False,
) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for one of Browse's 4
    single-item pill lists (Sort/Filter/Quality/Genre, ids 6110/6120/
    6130/6100).

    `always_active=True` (Sort only) skips the ListItem.Property(active)
    branching entirely: Sort has no inactive state, it always shows
    accent-tinted text on an accent-tinted glass fill, only the outline
    responds to focus. `always_active=False` (Filter/Quality/Genre)
    renders the full active&times;focused 2&times;2 state matrix: inactive
    glass (SURFACE_REST idle / SURFACE_RAISED focused-outline-only) vs. active
    accent-tinted glass (accent_pill_fill fill in both idle and focused
    states, outline swaps white<->accent_color on focus), same "Kodi
    always renders focusedlayout for the CURRENT item" gating sidebar_row()
    also needs.

    Position and navigation aren't parameters either: posx/onleft/onright
    live on the wrapping <control type="list"> in main.xml.tpl, and all 4
    callers share <onup>3000</onup> (nav) / <ondown>6200</ondown> (grid)."""
    W, H = 346, 62

    if always_active:
        item = f"""                <itemlayout width="{W}" height="{H}">
                    <control type="image">
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="label">
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{_pill_label(label_prefix, label_property)}</label>
                    </control>
                    <control type="label">
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                </itemlayout>"""
        focused = f"""                <focusedlayout width="{W}" height="{H}">
                    <control type="image">
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>white</colordiffuse>
                        <texture border="29">capsule-h58-outline.png</texture>
                    </control>
                    <control type="label">
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{_pill_label(label_prefix, label_property)}</label>
                    </control>
                    <control type="label">
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                </focusedlayout>"""
        return item, focused

    # active/inactive x focused/unfocused 2x2 matrix (Filter/Quality/Genre)
    label = _pill_label(label_prefix, label_property)
    item = f"""                <itemlayout width="{W}" height="{H}">
                    <control type="image">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="image">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>{label}</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{label}</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{W}" height="{H}">
                    <control type="image">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>{T.SURFACE_RAISED}</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="image">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                        <texture border="29">capsule-h58.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id}) + !String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="29">capsule-h58-outline.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id}) + String.IsEqual(ListItem.Property(active),1)</visible>
                        <width>{W}</width>
                        <height>58</height>
                        <colordiffuse>white</colordiffuse>
                        <texture border="29">capsule-h58-outline.png</texture>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>16</posx>
                        <posy>15</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_24</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{icon}</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>{label}</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>50</posx>
                        <width>248</width>
                        <height>58</height>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>{label}</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                        <posx>312</posx>
                        <posy>18</posy>
                        <width>24</width>
                        <height>24</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>&#xE211;</label>
                    </control>
                </focusedlayout>"""
    return item, focused


def sidebar_row(list_id: int, *, width: int = 300) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for a Browse sidebar
    row: Browse's fixed-sources sidebar (id 6000) and per-library sidebar
    (id 6010, same itemlayout, only the list-level wiring differs).

    Styled to match the Settings sidebar (settings_nav_row) rather than the
    Apple TV app's own Browse rail, by explicit request 2026-08-03: two rails
    that sit in the same place across two sections should not use two
    different active treatments. What that changed here -- the app's Browse
    rail marks its active row with a raised wash plus a 3px accent bar and
    accent text, which is what this used to draw:

      * active row is now a SOLID accent fill with on-accent text, as
        Settings' is; the left bar is gone, redundant against a filled row.
      * focus adds the same neutral white rim, for the same reason it is not
        accent there (FOCUS_RIM_NEUTRAL: an accent rim on an accent fill
        cannot be seen).
      * the fill uses rounded-14 rather than white-square-rounded, whose real
        radius is ~4px whatever border it is sliced at
        (project_corner_radius_consolidation) -- so these rows were barely
        rounded while Settings' were properly so.

    Geometry is deliberately NOT copied over: these rows are single-line with
    a trailing count, in a 300px rail beside a poster grid, where Settings'
    are two-line with a chevron in a 420px one. Only the state machine and
    the surface treatment are shared.

    ACTIVE is not the same as selected here, unlike in Settings. Browse has
    TWO sidebar lists, so the row whose content is on screen can live in the
    list that does not hold the cursor -- which is why both layouts carry
    both states rather than letting focusedlayout stand in for "active".

    Detail's season sidebar (id 6400) is NOT a caller of this: its
    itemlayout has real structural differences beyond a size/icon
    parameter (unfocused state collapses to a single always-on SURFACE_RAISED
    fill with no separate dimmer inactive shade, and a single count label
    with no active/inactive color split), so it stays hand-typed in
    detail.xml.tpl rather than forcing a different state machine through
    this fragment."""
    H = 60
    label_w = width - 60 - 70

    def _state(active: bool, focused: bool = False) -> str:
        """One complete row in one state. Every accented layer is drawn once
        per state rather than conditionally recoloured within one control.

        A library name can outrun a 300px rail ("Movies (Deutsch)"), so the
        label marquees -- but ONLY while the list really holds focus, which is
        why it is drawn twice with complementary gates rather than once with
        <scroll>. focusedlayout renders for the ACTIVE row even when the
        cursor is off in the grid, and a rail that scrolls its own text
        forever in the background is exactly the "panel that never sits still"
        the options panel avoided."""
        gate = "" if active else "!"
        fill = ("$INFO[Window.Property(accent_color)]" if active
                else T.SURFACE_FAINT)
        text = ("$INFO[Window.Property(on_accent_color)]" if active
                else "$INFO[Window.Property(text_primary)]")
        count = ("$INFO[Window.Property(on_accent_color)]" if active
                 else "$INFO[Window.Property(text_tertiary)]")

        def _label(visible: str, marquee: bool) -> str:
            scroll = ("""
                            <scroll>true</scroll>
                            <scrollsuffix>   </scrollsuffix>""" if marquee else "")
            gate_xml = f"""
                            <visible>{visible}</visible>""" if visible else ""
            return f"""
                        <control type="label">{gate_xml}
                            <posx>60</posx>
                            <posy>2</posy>
                            <width>{label_w}</width>
                            <height>54</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_SIDEBAR}</font>
                            <textcolor>{text}</textcolor>
                            <label>$INFO[ListItem.Label]</label>{scroll}
                        </control>"""

        # One plain label unless this IS the focused layout, in which case a
        # complementary pair: the marquee copy only exists where it can ever
        # be visible, rather than being emitted everywhere and hidden.
        if focused:
            label_block = (_label(f"!Control.HasFocus({list_id})", False)
                           + _label(f"Control.HasFocus({list_id})", True))
        else:
            label_block = _label("", False)
        return f"""
                    <control type="group">
                        <visible>{gate}String.IsEqual(ListItem.Property(active),1)</visible>
                        <control type="image">
                            <posx>0</posx>
                            <posy>2</posy>
                            <width>{width}</width>
                            <height>54</height>
                            <colordiffuse>{fill}</colordiffuse>
                            <texture border="14">rounded-14.png</texture>
                        </control>
                        <control type="label">
                            <posx>18</posx>
                            <posy>14</posy>
                            <width>30</width>
                            <height>30</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_26}</font>
                            <textcolor>{text}</textcolor>
                            <label>$INFO[ListItem.Property(icon_glyph)]</label>
                        </control>
{label_block}
                        <control type="label">
                            <posx>{width - 82}</posx>
                            <posy>2</posy>
                            <width>70</width>
                            <height>54</height>
                            <align>right</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>{count}</textcolor>
                            <label>$INFO[ListItem.Property(count)]</label>
                        </control>
                    </control>"""

    item = f"""                <itemlayout width="{width}" height="{H}">{_state(False)}{_state(True)}
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{width}" height="{H}">{_state(False, focused=True)}{_state(True, focused=True)}
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>2</posy>
                        <width>{width}</width>
                        <height>54</height>
                        <colordiffuse>{T.FOCUS_RIM_NEUTRAL}</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>
                </focusedlayout>"""
    return item, focused


def alpha_rail_pill(list_id: int) -> tuple[str, str]:
    """Returns (itemlayout_xml, focusedlayout_xml) for one pill of Browse's
    A-Z rail: "All", A..Z, then "#", down the right margin.

    Geometry is the Android TV app's, measured off
    internal-docs/androidtv-reference/browse-alpha-rail.png -- 80x58 at
    pitch 68. The Apple TV app has not shipped this screen, so Android is
    the reference by Adrian's decision (2026-08-06) and the styling is
    expected to be revisited when it does; nothing here is bespoke art.

    The STATE MACHINE is sidebar_row()'s, not the Android app's, for the
    reason recorded there: the app marks focus with an accent ring and
    accent glyph, but every other rail in this UI uses a solid accent fill
    for active and a neutral white rim for focus, and two rails on the same
    screen must not disagree. It also keeps focus readable ON the active
    pill, where an accent rim on an accent fill cannot be seen.

    ACTIVE is not the same as selected, exactly as in sidebar_row: the
    chosen letter stays filled while the cursor is off in the grid, so both
    layouts carry both states."""
    # The LAYOUT is a whole pitch tall; the capsule is H and sits centred in
    # it. That gap is the fix for a real bug, not styling: `<itemheight>` is
    # a PANEL container's property and a `type="list"` ignores it entirely,
    # taking its step from the ITEMLAYOUT's own height instead. So the rail
    # declared itemheight 68 with a 58-high layout and Kodi stepped 58 --
    # measured on a live capture, "All" ending at y358 and "A" starting at
    # y359, i.e. the pills touched and the 10px never reached the screen.
    #
    # Android draws pill 58 at pitch 68 with a clear 10px band between
    # (measured off internal-docs/androidtv-reference/browse-alpha-rail.png
    # and again live 2026-08-10). Making the layout the pitch is what
    # actually produces that band here.
    W, H = T.ALPHA_PILL_W, T.ALPHA_PILL_H
    PITCH = T.ALPHA_PITCH
    PAD = (PITCH - H) // 2

    def _state(active: bool) -> str:
        # Tested against the literal "1", the way browse_pill does, rather
        # than String.IsEmpty: the first cut used IsEmpty with the negation
        # the wrong way round and every pill came up accent-filled at once,
        # which reads as "the whole alphabet is selected".
        gate = "" if active else "!"
        fill = ("$INFO[Window.Property(accent_color)]" if active
                else T.SURFACE_FAINT)
        text = ("$INFO[Window.Property(on_accent_color)]" if active
                else "$INFO[Window.Property(text_primary)]")
        return f"""
                    <control type="group">
                        <visible>{gate}String.IsEqual(ListItem.Property(active),1)</visible>
                        <control type="image">
                            <posy>{PAD}</posy>
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>{fill}</colordiffuse>
                            <texture border="29">capsule-h{H}.png</texture>
                        </control>
                        <control type="label">
                            <posy>{PAD}</posy>
                            <width>{W}</width>
                            <height>{H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{text}</textcolor>
                            <!-- The GLYPH, not the label: the label is what
                                 a screen reader says ("F, 15 titles"), since
                                 Kodi reads ListItem.Label and a count drawn
                                 beside a 64px pill would be unreadable at
                                 ten feet. See _browse_alpha_speech(). -->
                            <label>$INFO[ListItem.Property(glyph)]</label>
                        </control>
                    </control>"""

    item = f"""                <itemlayout width="{W}" height="{PITCH}">{_state(False)}{_state(True)}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{W}" height="{PITCH}">{_state(False)}{_state(True)}
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posy>{PAD}</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.FOCUS_RIM_NEUTRAL}</colordiffuse>
                        <texture border="29">capsule-h{H}-outline.png</texture>
                    </control>
                </focusedlayout>"""
    return item, focused


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
    "The only one -- never bespoke per screen", so anything that needs to say
    "there is nothing here" calls this rather than typing three labels again.

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
    title, "no red anywhere". "error": the icon AND the title go status-red
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
    indent: str = "            ",
) -> str:
    """One complete poster row: header label + horizontal list, wrapped in a
    group that hides itself when `title_property` is empty.

    Home hand-wrote this block nine times and Discover three more, byte-
    identical apart from ids -- which is why the three screens drifted to
    three different title gaps and row heights. Generating it means a row
    count is now just a number (Discover's largest tab needs ~15), and the
    geometry comes from tokens.py rather than being retyped per block."""
    return f"""{indent}<control type="group" id="{group_id}">
{indent}    <height>{T.ROW_BLOCK_H}</height>
{indent}    <visible>!String.IsEmpty(Window.Property({title_property}))</visible>
{indent}    <control type="label">
{indent}        <width>{T.CONTENT_WIDTH}</width>
{indent}        <height>{T.ROW_TITLE_H}</height>
{indent}        <font>{T.FONT_SECTION_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>$INFO[Window.Property({title_property})]</label>
{indent}    </control>
{indent}    <control type="list" id="{list_id}">
{indent}        <posx>{T.ROW_LIST_X}</posx>
{indent}        <posy>{T.ROW_TITLE_GAP}</posy>
{indent}        <width>{list_width}</width>
{indent}        <height>{T.CELL_H}</height>
{indent}        <onup>{onup}</onup>
{indent}        <ondown>{ondown}</ondown>
{indent}        <orientation>horizontal</orientation>
{indent}        <itemwidth>{T.CELL_W}</itemwidth>
{indent}        <itemheight>{T.CELL_H}</itemheight>
{indent}        <scrolltime>{T.SCROLLTIME}</scrolltime>
{item_xml}

{focused_xml}
{indent}    </control>
{indent}</control>"""


def discover_tab_positions() -> tuple[int, ...]:
    """Left edge of each Discover tab pill, laid out from DISCOVER_LEFT.

    Lives here rather than in home_rows.py because the offsets derive from
    tokens.DISCOVER_LEFT, and home_rows.py is deliberately dependency-free."""
    from .. import home_rows

    xs, x = [], T.DISCOVER_LEFT
    for _, _, width in home_rows.DISCOVER_TABS:
        xs.append(x)
        x += width + home_rows.DISCOVER_TAB_GAP
    return tuple(xs)


def discover_tab_pill(
    list_id: int,
    *,
    tab_key: str,
    width: int,
    posx: int,
    onleft: int,
    onright: int,
    ondown: int,
    onup: int = 3000,
) -> str:
    """One Discover tab pill, as a complete single-item `<control type="list">`.

    Four text-hugging widths can't share one Kodi list (a list has a single
    itemwidth), so each pill is its own 1-item list -- the same shape Browse's
    Sort/Filter/Quality/Genre pills already use. Unlike those, position IS a
    parameter: the widths come from the measured label table in home_rows.py,
    so the x offsets can only be computed, not hand-written.

    Which pill is ACTIVE cannot ride on itemlayout-vs-focusedlayout. Kodi draws
    a list's current item through focusedlayout whether or not the list holds
    input focus, and in a 1-item list the sole item is always current -- so all
    four pills would render identically (they did, first time round). The
    active state is therefore gated on Window.Property(discover_tab) matching
    this pill's own key, which is baked in at render time since the four keys
    are static. Focus is a separate axis on top, via Control.HasFocus().
    """
    h = 54  # home_rows.DISCOVER_TAB_HEIGHT, measured off the reference
    active = f"String.IsEqual(Window.Property(discover_tab),{tab_key})"

    def _body() -> str:
        return f"""                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <colordiffuse>{T.SURFACE_FAINT}</colordiffuse>
                        <texture border="27">capsule-h54.png</texture>
                        <visible>!{active}</visible>
                    </control>
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <colordiffuse>{T.SURFACE_RAISED}</colordiffuse>
                        <texture border="27">capsule-h54-outline.png</texture>
                        <visible>!{active}</visible>
                    </control>
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="27">capsule-h54.png</texture>
                        <visible>{active}</visible>
                    </control>
                    <!-- Focus reads as a white outline over whichever fill is
                         showing, so a focused pill keeps its active/inactive
                         colour identity instead of swapping to a third look. -->
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <colordiffuse>white</colordiffuse>
                        <texture border="27">capsule-h54-outline.png</texture>
                        <visible>Control.HasFocus({list_id})</visible>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_BUTTON}</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>!{active}</visible>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{h}</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_BUTTON}</font>
                        <textcolor>$INFO[Window.Property(on_accent_color)]</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>{active}</visible>
                    </control>"""

    return f"""            <control type="list" id="{list_id}">
                <posx>{posx}</posx>
                <posy>174</posy>
                <width>{width}</width>
                <height>{h}</height>
                <onup>{onup}</onup>
                <ondown>{ondown}</ondown>
                <onleft>{onleft}</onleft>
                <onright>{onright}</onright>
                <orientation>horizontal</orientation>
                <itemwidth>{width}</itemwidth>
                <itemheight>{h}</itemheight>
                <itemlayout width="{width}" height="{h}">
{_body()}
                </itemlayout>

                <focusedlayout width="{width}" height="{h}">
{_body()}
                </focusedlayout>
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
# derived -- leaves the lead squat in a hole, which is why 7.9.3 rules it out
# explicitly. So these are derived in that order, not typed. At
# POSTER_H=378 that is the same 672 they were before.
DISCOVER_FOCUS_ART_H = T.POSTER_H
DISCOVER_FOCUS_ART_W = DISCOVER_FOCUS_ART_H * 16 // 9
DISCOVER_FOCUS_CELL_W = DISCOVER_FOCUS_ART_W + 2 * T.HPAD


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

                             7.9.5's own reduce-motion clause is "the card
                             simply IS its new size", which is exactly what
                             happens now, so this is a sanctioned path rather
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
                             card simply IS its new size, which is 7.9.5's
                             own reduce-motion wording, and the dissolve is
                             what sells the change.

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


def collection_card(list_id: int) -> tuple[str, str]:
    """7.5's collections index tile.

    "A collection is a set, not a title" -- so this is the one LANDSCAPE
    16:9 tile in an app of 2:3 portraits, and its numbers are the spec's
    verbatim (tile 448, radius 14, caption 86 fixed so rows align). The
    Android TV app lays its own out at exactly the same values, measured
    off a live uiautomator dump.

    7.5's artwork ladder, in the order it gives:
      backdrop  -> scaled and cropped to the tile, the normal case
      poster    -> FITTED, never cropped ("never crop a poster to 16:9"),
                   over a dimmed plate standing in for the blurred copy of
                   itself the spec asks for, which Kodi cannot produce
      neither   -> plate plus the film-stack glyph

    The caption is a fixed 86 whatever the name's length, which is what
    keeps a row of tiles aligned when one name wraps and its neighbour
    does not."""
    W, H = T.COLLECTION_TILE_W, T.COLLECTION_TILE_H
    CELL_W, CELL_H = T.COLLECTION_CELL_W, T.COLLECTION_CELL_H
    CAP_TOP = H + 10
    # Same focus lift the poster cards use, centred on THIS tile rather than
    # a poster's; poster_visual keeps its own copy local to itself.
    ZOOM = (f'\n                            <animation effect="zoom" start="100" end="104.5" '
            f'center="{W // 2},{H // 2}" time="140" tween="cubic" '
            f'easing="out">Focus</animation>')

    def _art(anim: str) -> str:
        return f"""
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>{T.SURFACE_PLACEHOLDER}</colordiffuse>
                            <texture diffuse="collection-mask.png">white-square.png</texture>{anim}
                        </control>
                        <control type="label">
                            <width>{W}</width>
                            <height>{H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_36</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>&#xE529;</label>
                            <visible>String.IsEmpty(ListItem.Art(thumb)) + String.IsEmpty(ListItem.Property(poster))</visible>{anim}
                        </control>
                        <!-- 7.5 puts the fitted poster over "a blurred (30pt)
                             dimmed (55%) copy of itself". Kodi has no blur,
                             so the copy is the same poster CROPPED to fill
                             and dimmed: it loses the softness but keeps what
                             the layer is actually for, a colour field drawn
                             from the artwork instead of a flat plate. -->
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>0x73FFFFFF</colordiffuse>
                            <aspectratio scalediffuse="false">scale</aspectratio>
                            <texture diffuse="collection-mask.png">$INFO[ListItem.Property(poster)]</texture>
                            <visible>String.IsEmpty(ListItem.Art(thumb)) + !String.IsEmpty(ListItem.Property(poster))</visible>{anim}
                        </control>
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <aspectratio scalediffuse="false" align="center" aligny="center">keep</aspectratio>
                            <texture diffuse="collection-mask.png">$INFO[ListItem.Property(poster)]</texture>
                            <visible>String.IsEmpty(ListItem.Art(thumb)) + !String.IsEmpty(ListItem.Property(poster))</visible>{anim}
                        </control>
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <aspectratio scalediffuse="false">scale</aspectratio>
                            <texture diffuse="collection-mask.png">$INFO[ListItem.Art(thumb)]</texture>
                            <visible>!String.IsEmpty(ListItem.Art(thumb))</visible>{anim}
                        </control>"""

    # The caption does NOT take the zoom, in EITHER state. It used to take it
    # in the focused one, alone in the card family: poster_card, person_card
    # and episode_card all lift only the artwork block and leave their text
    # where it is. Worse than merely inconsistent -- an animation centre is in
    # the parent's coordinates and this one is the TILE's centre (W/2, H/2),
    # 130px above the caption, so scaling about it pushed the name down ~6px
    # and the meta line ~10px as well as growing them. Focusing a collection
    # nudged its own caption out of line with every unfocused caption beside
    # it in the row.
    def _caption() -> str:
        return f"""
                        <control type="textbox">
                            <posy>{CAP_TOP}</posy>
                            <width>{W}</width>
                            <height>56</height>
                            <font>tofa_font_poster_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <posy>{CAP_TOP + 56}</posy>
                            <width>{W}</width>
                            <height>26</height>
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(caption_meta)]</label>
                        </control>"""

    # Accent focus halo, drawn FIRST so the artwork painted over it covers the
    # inward half and only the outward fade shows -- same asset construction
    # and same z-order as poster_visual(), episode_card() and discover_card().
    # This tile was the last card in the family with no glow at all, so a
    # focused collection read flatter than a focused anything-else.
    #
    # The cell HAS the room, but not where the halo needs it. Panel 6210's
    # itemwidth/itemheight are COLLECTION_CELL_W/H, i.e. tile plus gap, and
    # the tile drew at the cell's own (0,0) -- so all the slack was on the
    # right and bottom and a bleed of -GLOW_PAD would have been clipped away
    # on the top and left, Kodi clipping each item strictly to its cell. The
    # content group is therefore offset by GLOW_PAD (the borrowed-slack trick
    # poster_visual() and person_card() both use) and the panel is pulled back
    # by the same amount in main.xml.tpl, so every tile lands on the pixel it
    # landed on before and the halo has somewhere to go.
    glow = f"""
                        <control type="image">
                            <visible>Control.HasFocus({list_id})</visible>
                            <posx>-{GLOW_PAD}</posx>
                            <posy>-{GLOW_PAD}</posy>
                            <width>{W + 2 * GLOW_PAD}</width>
                            <height>{H + 2 * GLOW_PAD}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture>collection-glow.png</texture>
                            <!-- Centre in the PARENT's coordinates, so it is
                                 the tile's centre and not this control's own:
                                 it starts at -GLOW_PAD, so its true centre is
                                 -GLOW_PAD + (W + 2*GLOW_PAD)/2 = W/2. Using
                                 its own half-width would zoom the halo about
                                 a point GLOW_PAD down and right of the tile
                                 it wraps. -->
                            <animation effect="zoom" start="100" end="104.5" center="{W // 2},{H // 2}" time="140" tween="cubic" easing="out">Focus</animation>
                        </control>"""

    # Written as a 9-patch, but NOT shipped as one: build.py collects every
    # `border=` texture with a known draw size and gen_exact_assets.py emits
    # exact-rounded-14-outline-448x252.png at 2x, which the renderer
    # substitutes here. So this rim is already exact-size and crisp on the 4K
    # box like the poster/episode/person ones, without a hand-made twin of
    # its own -- the generic mechanism reaches it. Worth stating, because it
    # LOOKS like the one card border in the family still sharing 9-patch art.
    rim = f"""
                        <control type="image">
                            <width>{W}</width>
                            <height>{H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="{T.COLLECTION_RADIUS}">rounded-14-outline.png</texture>
                            <visible>Control.HasFocus({list_id})</visible>{ZOOM}
                        </control>"""

    item = f"""                <itemlayout width="{CELL_W}" height="{CELL_H}">
                    <control type="group">
                        <posx>{GLOW_PAD}</posx>
                        <posy>{GLOW_PAD}</posy>{_art("")}{_caption()}
                    </control>
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{CELL_W}" height="{CELL_H}">
                    <control type="group">
                        <posx>{GLOW_PAD}</posx>
                        <posy>{GLOW_PAD}</posy>{glow}{_art(ZOOM)}{rim}{_caption()}
                    </control>
                </focusedlayout>"""
    return item, focused


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
# 6 describes the second one as "solid accent fill with dark text" -- that is
# true of the sidebar and not of the detail pane. The shipped app disagrees
# with its own spec here and the app wins (feedback_apple_tv_source_of_truth).


def settings_nav_row(list_id: int) -> tuple[str, str]:
    """Sidebar row for the Settings section: icon, title, current-value
    subtitle, trailing chevron.

    Deliberately NOT a variant of sidebar_row() above, for the same reason
    Detail's season sidebar is not one: that fragment is a 300x60 single-line
    row whose active state is a raised wash plus a 3px accent bar, and this is
    a two-line row whose active state is a solid accent fill. Sharing them
    would mean threading a second state machine through one function rather
    than reusing anything.

    The resting fill is flat SURFACE_FAINT -- the same value Browse's sidebar
    uses, chosen so the two rails match. The real Apple TV row fades from +23
    over the page background at its top to +2 at its bottom, and this shipped
    that way first, from a generated gradient texture; it was the only
    gradient surface in the skin and was dropped by explicit request
    2026-08-03. A deliberate divergence.

    Active vs focused: Kodi draws focusedlayout for a list's SELECTED item
    even when the list has no keyboard focus, which is exactly the behaviour
    wanted here -- the row for the page being shown stays accent-filled while
    the user is off editing in the detail pane. The extra brightening and halo
    that mark real focus are gated on `Control.HasFocus(list_id)` on top of
    that, matching the app (its resting-active fill measures 3FBBB7 against
    58C6BF when the sidebar itself holds focus).

    Those focus-only layers are a brightening wash and a 2px rim. The rim is
    NEUTRAL white, not 5's accent -- see FOCUS_RIM_NEUTRAL: an accent rim on a
    row already filled with the accent cannot be seen, and 9.2 sets the
    precedent for going white in exactly that situation."""
    W = T.SETTINGS_SIDEBAR_W
    H = T.SETTINGS_NAV_ROW_H
    PITCH = T.SETTINGS_NAV_PITCH
    ICON_CX = 36            # icon box centre, measured 192 against a row at 156
    # Further from the icon than the app's 58, by request 2026-08-03 -- the
    # glyph and the title read as one clump at the measured gap. Same
    # deliberate-divergence note as the row height in tokens.py.
    TEXT_X = 78
    CHEVRON_X = W - 52
    # Only 6px of clearance before the chevron, not 12: pushing TEXT_X out
    # to 78 cost the label 20px and started ellipsising the longer subtitles.
    TEXT_W = CHEVRON_X - TEXT_X - 6
    # The two lines sit as a centred pair with a 36px gap between their
    # centres, up from the 29 the app uses -- see the row-height note in
    # tokens.py for why this screen is deliberately roomier than the capture.
    TITLE_Y = H // 2 - 34
    SUB_Y = H // 2 + 2

    def _labels(title_color: str, sub_color: str, chevron_color: str,
                marquee: bool | None = None) -> str:
        """`marquee=None` emits a still row (the itemlayout). True/False emit
        the focused layout's complementary pair: both text lines scroll, but
        only while the list really holds focus.

        Both lines, not just the title: they share one column, and it is the
        SUBTITLE that overflows in practice (an account row shows an email).
        Drawn as two gated copies rather than one conditional control because
        Kodi's <scroll> is a plain boolean, and focusedlayout renders for the
        active row even when the cursor is elsewhere -- so an ungated marquee
        would scroll the current page's row forever in the background."""
        # EM SPACES (U+2003), not ASCII: Kodi's parser discards a text node
        # that is only ASCII whitespace, so a plain-space suffix arrives
        # EMPTY and the wrap reads as one run-on string. This shipped wrong.
        scroll = ("""
                            <scroll>true</scroll>
                            <scrollsuffix>   </scrollsuffix>""" if marquee else "")
        gate = "" if marquee is None else f"""
                        <visible>{"" if marquee else "!"}Control.HasFocus({list_id})</visible>"""
        return f"""
                    <control type="label">{gate}
                        <posx>{ICON_CX - 18}</posx>
                        <posy>{H // 2 - 18}</posy>
                        <width>36</width>
                        <height>36</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_26}</font>
                        <textcolor>{title_color}</textcolor>
                        <label>$INFO[ListItem.Property(icon_glyph)]</label>
                    </control>
                    <control type="label">{gate}
                        <posx>{TEXT_X}</posx>
                        <posy>{TITLE_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>34</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_ROW_TITLE}</font>
                        <textcolor>{title_color}</textcolor>
                        <label>$INFO[ListItem.Label]</label>{scroll}
                    </control>
                    <control type="label">{gate}
                        <posx>{TEXT_X}</posx>
                        <posy>{SUB_Y}</posy>
                        <width>{TEXT_W}</width>
                        <height>28</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_METADATA}</font>
                        <textcolor>{sub_color}</textcolor>
                        <label>$INFO[ListItem.Property(summary)]</label>{scroll}
                    </control>
                    <control type="label">{gate}
                        <posx>{CHEVRON_X}</posx>
                        <posy>{H // 2 - 14}</posy>
                        <width>28</width>
                        <height>28</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>{chevron_color}</textcolor>
                        <label>&#x{icon_glyphs.CHEVRON_RIGHT:04X};</label>
                    </control>"""

    item = f"""                <itemlayout width="{W}" height="{PITCH}">
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.SURFACE_FAINT}</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>{_labels(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        "$INFO[Window.Property(text_tertiary)]")}
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{W}" height="{PITCH}">
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.SURFACE_RAISED}</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.FOCUS_RIM_NEUTRAL}</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>{_labels(
                        "$INFO[Window.Property(on_accent_color)]",
                        "$INFO[Window.Property(on_accent_color)]",
                        "$INFO[Window.Property(on_accent_color)]",
                        marquee=False)}{_labels(
                        "$INFO[Window.Property(on_accent_color)]",
                        "$INFO[Window.Property(on_accent_color)]",
                        "$INFO[Window.Property(on_accent_color)]",
                        marquee=True)}
                </focusedlayout>"""
    return item, focused


def settings_action_row(list_id: int, width: int = T.SETTINGS_DETAIL_W) -> tuple[str, str]:
    """A focusable detail-pane row: title over an explanatory line, with a
    trailing glyph. Switch Profile and Sign Out are both this shape.

    Rendered as a one-item list rather than a button, the same idiom Browse
    already uses for its Sort/Filter/Genre controls -- a Kodi <button> has one
    label and one label2 and cannot stack two lines, and a list gives the
    itemlayout/focusedlayout split every other styled control here uses.

    One item per list, and one list per grouplist child, is also what keeps
    the pane scrollable: a grouplist scrolls to reveal a focused CHILD and
    never for focus moving around inside one, so a row that is its own child
    always scrolls into view (project_kodi_grouplist_scroll_limit).

    `destructive` on the ListItem turns the title and glyph red -- 2's rule is
    that destructive reads as red TEXT over glass, not as a filled red row.

    Every layer of the focusedlayout, TEXT INCLUDED, is gated on
    `Control.HasFocus(list_id)`. A one-item list's only item is permanently
    "selected", so Kodi draws its focusedlayout the whole time the section is
    open -- ungated, Switch Profile rendered in accent while focus was still
    over in the sidebar, looking like the row the user was on."""
    H = T.SETTINGS_ACTION_ROW_H
    TEXT_X = 18             # ink lands at 659 against a card at 632
    GLYPH_X = width - 76
    TEXT_W = GLYPH_X - TEXT_X - 16

    def _labels(title_color: str, sub_color: str, glyph_color: str,
                gate: str = "") -> str:
        focus = f"{gate} + " if gate else ""
        # For the one label with no condition of its own to AND onto.
        focus_only = gate or "true"
        return f"""
                    <control type="label">
                        <visible>{focus}!String.IsEqual(ListItem.Property(destructive),1)</visible>
                        <posx>{TEXT_X}</posx>
                        <posy>23</posy>
                        <width>{TEXT_W}</width>
                        <height>34</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_ROW_TITLE}</font>
                        <textcolor>{title_color}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>{focus}String.IsEqual(ListItem.Property(destructive),1)</visible>
                        <posx>{TEXT_X}</posx>
                        <posy>23</posy>
                        <width>{TEXT_W}</width>
                        <height>34</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_ROW_TITLE}</font>
                        <textcolor>{T.STATUS_RED}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>{focus_only}</visible>
                        <posx>{TEXT_X}</posx>
                        <posy>58</posy>
                        <width>{TEXT_W}</width>
                        <height>28</height>
                        <aligny>center</aligny>
                        <font>{T.FONT_METADATA}</font>
                        <textcolor>{sub_color}</textcolor>
                        <label>$INFO[ListItem.Property(summary)]</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(destructive),1)</visible>
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
                        <visible>{focus}String.IsEqual(ListItem.Property(destructive),1)</visible>
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

    item = f"""                <itemlayout width="{width}" height="{H}">
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>{_labels(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        "$INFO[Window.Property(text_secondary)]")}
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{width}" height="{H}">
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="20">rounded-20-outline.png</texture>
                    </control>{_labels(
                        "$INFO[Window.Property(accent_color)]",
                        "$INFO[Window.Property(text_secondary)]",
                        "$INFO[Window.Property(accent_color)]",
                        gate=f"Control.HasFocus({list_id})")}{_labels(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        gate=f"!Control.HasFocus({list_id})")}
                </focusedlayout>"""
    return item, focused


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
    TEXT_X = 19
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
{indent}        <font>{T.FONT_ROW_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>{label}</label>
{indent}    </control>
{indent}    <control type="label">
{indent}        <posx>{width - 29}</posx>
{indent}        <posy>0</posy>
{indent}        <width>{width // 2 - 40}</width>
{indent}        <height>{height}</height>
{indent}        <align>right</align>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_BODY}</font>
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
    TEXT_X = 19
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
{indent}    <posy>{T.SETTINGS_CONTENT_Y - T.SETTINGS_GROUP_EYEBROW_RISE - 12}</posy>
{indent}    <width>{T.SETTINGS_RAIL_W}</width>
{indent}    <height>28</height>
{indent}    <aligny>center</aligny>
{indent}    <font>{T.FONT_EYEBROW}</font>
{indent}    <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
{indent}    <label>{eyebrow}</label>
{indent}</control>
{indent}<control type="group">
{indent}    <posx>{T.SETTINGS_RAIL_X}</posx>
{indent}    <posy>{T.SETTINGS_CONTENT_Y}</posy>
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
{indent}        <posy>{T.SETTINGS_QR_Y - T.SETTINGS_CONTENT_Y}</posy>
{indent}        <width>{T.SETTINGS_QR}</width>
{indent}        <height>{T.SETTINGS_QR}</height>
{indent}        <texture>{texture}</texture>
{indent}    </control>
{indent}    <control type="textbox">
{indent}        <posx>22</posx>
{indent}        <posy>{T.SETTINGS_QR_CAPTION_Y - T.SETTINGS_CONTENT_Y}</posy>
{indent}        <width>{T.SETTINGS_RAIL_W - 44}</width>
{indent}        <height>94</height>
{indent}        <align>center</align>
{indent}        <font>{T.FONT_METADATA}</font>
{indent}        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
{indent}        <label>$INFO[Window.Property({caption_property})]</label>
{indent}    </control>
{indent}</control>"""


def settings_fox_tile(list_id: int) -> tuple[str, str]:
    """9.4's fox tile: the artwork for one accent preset over its name.

    The logo is a raster per preset (`tofa-logo-<name>.png`) rather than one
    image tinted at runtime -- see theme.PRESETS, which owns that mapping and
    explains why the artwork cannot be colordiffused like the flat chrome can.
    So each item carries its own texture and the layout just draws it.

    Three states, and they are three because 9.4 asks for three: rest is a
    faint platter with a hairline ring; SELECTED (this is the live accent)
    takes a ring in the tile's own colour, which arrives as a per-item
    `tile_color` property rather than the window accent -- during a preview
    the two differ, and it is the tile's own hue that has to show; FOCUSED
    adds the neutral rim, for the same reason the sidebar row does.

    The star on the default marks 9.4's "Tofa Fox is the original look"
    badge."""
    W = T.SETTINGS_FOX_TILE_W
    H = T.SETTINGS_FOX_TILE_H
    ART = 78
    ART_X = (W - ART) // 2

    def _body(ring: str, ring_texture: str, label_color: str) -> str:
        return f"""
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.PANEL_WASH}</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{ring}</colordiffuse>
                        <texture border="14">{ring_texture}</texture>
                    </control>
                    <control type="image">
                        <posx>{ART_X}</posx>
                        <posy>16</posy>
                        <width>{ART}</width>
                        <height>{ART}</height>
                        <aspectratio>keep</aspectratio>
                        <texture>$INFO[ListItem.Art(thumb)]</texture>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>{H - 44}</posy>
                        <width>{W}</width>
                        <height>30</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_METADATA}</font>
                        <textcolor>{label_color}</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(ListItem.Property(is_default),1)</visible>
                        <posx>{W - 30}</posx>
                        <posy>10</posy>
                        <width>22</width>
                        <height>22</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>{T.SETTINGS_FOX_DEFAULT_BADGE}</textcolor>
                        <label>&#x{icon_glyphs.STAR:04X};</label>
                    </control>"""

    item = f"""                <itemlayout width="{T.SETTINGS_FOX_CELL_W}" height="{T.SETTINGS_FOX_CELL_H}">
                    <control type="group">
                        <visible>!String.IsEqual(ListItem.Property(selected),1)</visible>{_body(
                            T.BORDER_SOFT, "rounded-14-outline.png",
                            "$INFO[Window.Property(text_secondary)]")}
                    </control>
                    <control type="group">
                        <visible>String.IsEqual(ListItem.Property(selected),1)</visible>{_body(
                            "$INFO[ListItem.Property(tile_color)]", "rounded-14-outline.png",
                            "$INFO[Window.Property(text_primary)]")}
                    </control>
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{T.SETTINGS_FOX_CELL_W}" height="{T.SETTINGS_FOX_CELL_H}">
                    <control type="group">
                        <visible>!String.IsEqual(ListItem.Property(selected),1)</visible>{_body(
                            T.BORDER_SOFT, "rounded-14-outline.png",
                            "$INFO[Window.Property(text_secondary)]")}
                    </control>
                    <control type="group">
                        <visible>String.IsEqual(ListItem.Property(selected),1)</visible>{_body(
                            "$INFO[ListItem.Property(tile_color)]", "rounded-14-outline.png",
                            "$INFO[Window.Property(text_primary)]")}
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{W}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.FOCUS_RIM_NEUTRAL}</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>
                </focusedlayout>"""
    return item, focused


def _settings_control_row(list_id: int, *, trailing: str, trailing_w: int = 360,
                          width: int = T.SETTINGS_DETAIL_W_WIDE,
                          height: int = T.SETTINGS_ACTION_ROW_H) -> tuple[str, str]:
    """Shared body for the detail pane's two INTERACTIVE row shapes -- a
    toggle and a segmented choice. They differ only in what sits at the right
    end, so everything else (fill, focus wash, focus rim, title, subtitle,
    the two-copy focus gating) is built once here.

    Split out rather than copied because settings_action_row already proved
    how easily these drift: it shipped with its focus colours ungated and the
    row rendered focused while focus was elsewhere. One body, one fix.

    `trailing` is XML positioned against the row's right edge by its caller."""
    TEXT_X = 18
    # The label column is whatever the trailing control leaves. Passed in
    # rather than fixed: three "Do nothing"-sized pills need half again what
    # a toggle does, and a label sized for the toggle would run under them.
    TEXT_W = width - TEXT_X - trailing_w

    def _body(title_color: str, sub_color: str, gate: str) -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="group">{vis}
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>23</posy>
                            <width>{TEXT_W}</width>
                            <height>34</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{title_color}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>58</posy>
                            <width>{TEXT_W}</width>
                            <height>28</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>{sub_color}</textcolor>
                            <label>$INFO[ListItem.Property(summary)]</label>
                        </control>
                    </control>"""

    card = f"""
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{height}</height>
                        <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>"""

    focus_layers = f"""
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

    rest = _body("$INFO[Window.Property(text_primary)]",
                 "$INFO[Window.Property(text_secondary)]", "")
    item = f"""                <itemlayout width="{width}" height="{height}">{card}{rest}{trailing}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{width}" height="{height}">{card}{focus_layers}{_body(
                        "$INFO[Window.Property(accent_color)]",
                        "$INFO[Window.Property(text_secondary)]",
                        f"Control.HasFocus({list_id})")}{_body(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_secondary)]",
                        f"!Control.HasFocus({list_id})")}{trailing}
                </focusedlayout>"""
    return item, focused


def settings_toggle_row(list_id: int, **kwargs) -> tuple[str, str]:
    """A detail-pane row whose value is on/off, drawn as a capsule switch.

    Kodi has a <radiobutton>, deliberately not used: its ON/OFF art is the
    host skin's, so it would render differently under every skin the add-on
    runs on -- the same reason nothing here uses a Kodi built-in font.

    Reads `width` out of kwargs rather than assuming the wide detail column:
    Privacy & About is a narrow page (it carries a QR rail), and a switch
    positioned against the wide width lands clean off a 660px row."""
    W = kwargs.get("width", T.SETTINGS_DETAIL_W_WIDE)
    SW, SH = 72, 38
    X = W - 28 - SW
    Y = (T.SETTINGS_ACTION_ROW_H - SH) // 2
    KNOB = 30

    # 7.10.3 asks for the knob to travel in "~160ms ease-out". KODI CANNOT
    # DO IT, measured twice rather than assumed -- see ANIMATION.md. The knob
    # is two controls parked at each end and swapped by <visible> on a
    # ListItem property, because nothing can move a control from Python. A
    # slide animation on the arriving one does not play: that visibility is
    # re-evaluated WITH the itemlayout rather than treated as a transition,
    # so the Visible animation never fires. Tried on the control, on a
    # wrapping group, and finally at time="2000" where a real slide would be
    # impossible to miss -- screen-recorded at 30fps, the knob still moves in
    # a SINGLE frame. Confirmed on screen by the repo owner too.

    trailing = f"""
                    <control type="image">
                        <posx>{X}</posx>
                        <posy>{Y}</posy>
                        <width>{SW}</width>
                        <height>{SH}</height>
                        <colordiffuse>{T.SURFACE_TRACK}</colordiffuse>
                        <texture border="19">capsule-h38.png</texture>
                    </control>
                    <control type="image">
                        <visible>String.IsEqual(ListItem.Property(checked),1)</visible>
                        <posx>{X}</posx>
                        <posy>{Y}</posy>
                        <width>{SW}</width>
                        <height>{SH}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="19">capsule-h38.png</texture>
                    </control>
                    <control type="image">
                        <visible>!String.IsEqual(ListItem.Property(checked),1)</visible>
                        <posx>{X + 4}</posx>
                        <posy>{Y + 4}</posy>
                        <width>{KNOB}</width>
                        <height>{KNOB}</height>
                        <colordiffuse>$INFO[Window.Property(text_tertiary)]</colordiffuse>
                        <texture>circle.png</texture>
                    </control>
                    <control type="image">
                        <visible>String.IsEqual(ListItem.Property(checked),1)</visible>
                        <posx>{X + SW - KNOB - 4}</posx>
                        <posy>{Y + 4}</posy>
                        <width>{KNOB}</width>
                        <height>{KNOB}</height>
                        <colordiffuse>$INFO[Window.Property(on_accent_color)]</colordiffuse>
                        <texture>circle.png</texture>
                    </control>"""
    # The switch and its inset, nothing more -- the default 360 was sized for
    # a segmented control and left a narrow page's subtitle ellipsised.
    return _settings_control_row(list_id, trailing=trailing,
                                 trailing_w=SW + 56, **kwargs)


def settings_segmented_group(group_id: int, seg_ids: tuple, *,
                             prop: str, seg_width: int = 108,
                             posy: str = "0",
                             width: int = T.SETTINGS_DETAIL_W_WIDE,
                             height: int = T.SETTINGS_ACTION_ROW_H) -> str:
    """A settings row whose options are each independently focusable, as the
    reference app has them: `[Auto][Original]`, `[Play][Ask][Skip]`.

    The shape before it was a single focusable row whose Select CYCLED to the
    next option, chosen because "Left/Right cannot do it here -- Left already
    means back to the sidebar for every row on this pane". True for a LIST,
    whose row is one focus target; not true once each segment is its own
    control, because then only the LEFTMOST segment needs Left to mean the
    sidebar and the others move between segments. Same resolution as the
    home-row editor's arrows.

    Everything reads WINDOW properties under `prop`, since a group has no
    list item: <prop>_title, <prop>_summary, and per segment <prop>_seg<i>
    and <prop>_seg<i>_on. main.py fills them.

    The row's own focus wash/rim light up when ANY of its segments has
    focus, so the row still reads as one thing.
    """
    TEXT_X = 18
    SEG_H = 38
    GAP = 6
    n = len(seg_ids)
    total = n * seg_width + (n - 1) * GAP
    X0 = width - 28 - total
    Y = (height - SEG_H) // 2
    TEXT_W = width - TEXT_X - (total + 56)
    anyfocus = " | ".join(f"Control.HasFocus({i})" for i in seg_ids)

    segs = []
    for i, sid in enumerate(seg_ids):
        x = X0 + i * (seg_width + GAP)
        on = f"String.IsEqual(Window.Property({prop}_seg{i}_on),1)"
        focused = f"Control.HasFocus({sid})"
        segs.append(f"""
                        <control type="image">
                            <visible>{on}</visible>
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{seg_width}</width><height>{SEG_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="19">capsule-h38.png</texture>
                        </control>
                        <control type="image">
                            <visible>{focused} + !{on}</visible>
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{seg_width}</width><height>{SEG_H}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="19">capsule-h38-outline.png</texture>
                        </control>
                        <control type="label">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{seg_width}</width><height>{SEG_H}</height>
                            <align>center</align><aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(on_accent_color)]</textcolor>
                            <label>$INFO[Window.Property({prop}_seg{i})]</label>
                            <visible>{on}</visible>
                        </control>
                        <control type="label">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{seg_width}</width><height>{SEG_H}</height>
                            <align>center</align><aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property({prop}_seg{i})]</label>
                            <visible>!{on}</visible>
                        </control>
                        <control type="button" id="{sid}">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{seg_width}</width><height>{SEG_H}</height>
                            <texturefocus>transparent-6px.png</texturefocus>
                            <texturenofocus>transparent-6px.png</texturenofocus>
                            <label></label>
                        </control>""")

    return f"""
                    <control type="group" id="{group_id}">
                        <posy>{posy}</posy>
                        <width>{width}</width>
                        <height>{height}</height>
                        <control type="image">
                            <posx>0</posx><posy>0</posy>
                            <width>{width}</width><height>{height}</height>
                            <colordiffuse>{T.SURFACE_REST}</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>
                        <control type="image">
                            <visible>{anyfocus}</visible>
                            <posx>0</posx><posy>0</posy>
                            <width>{width}</width><height>{height}</height>
                            <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>
                        <control type="label">
                            <posx>{TEXT_X}</posx><posy>23</posy>
                            <width>{TEXT_W}</width><height>34</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property({prop}_title)]</label>
                        </control>
                        <control type="label">
                            <posx>{TEXT_X}</posx><posy>58</posy>
                            <width>{TEXT_W}</width><height>28</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>$INFO[Window.Property({prop}_summary)]</label>
                        </control>{"".join(segs)}
                    </control>"""


def settings_home_row_editor(slot: int, width: int = T.SETTINGS_DETAIL_W_WIDE) -> str:
    """One row of the home-screen editor: title, move up, move down, switch.

    THREE REAL FOCUS TARGETS, like the reference app. The previous shape was
    a list whose Select opened an action panel, because a list item cannot
    offer a third focus target -- Kodi builds item layouts with
    `insideContainer=true` so their controls are drawn but never join the
    focus tree. That constraint is real; the conclusion that a panel was the
    only answer was not. Real buttons inside a grouplist is what Kodi's own
    Estuary does for SettingsCategory, and it is what this uses.

    Everything is driven by WINDOW properties, not ListItem ones: these are
    ordinary controls, so there is no list item to read. main.py's
    _settings_fill_home_screen writes homerow_<slot>_* for each slot.

    The wrapping group is hidden when the account has fewer rows than slots,
    which also takes the row out of the grouplist's navigation chain.

    An arrow the row cannot use is DIMMED, not hidden, because that is what
    the reference app draws -- measured off a capture, its end-of-list arrow
    sits at 0.36-0.40 of a live one's brightness against the same
    background. `enable` on the button carries the other half: Kodi skips a
    disabled control when navigating, so the ends behave as well as look
    right.

    NAVIGATION IS WIRED IN PYTHON, not here. CGUIControlGroupList::AddControl
    OVERRIDES its children's up/down, and these buttons are grandchildren of
    the grouplist, which is exactly the case that resolves to nothing and
    makes Kodi wrap internally (reference_kodi_grouplist_children). See
    _settings_wire_home_rows.
    """
    # Local import for the same reason discover_tab_positions does it:
    # home_rows.py is deliberately dependency-free.
    from .. import home_rows

    up_id, down_id, tog_id, rm_id = home_rows.HOME_ROW_EDIT_IDS[slot]
    group_id = home_rows.HOME_ROW_EDIT_GROUP_IDS[slot]
    H = T.SETTINGS_HOMEROW_H
    TEXT_X = 18
    BTN = 58                      # capsule/circle asset heights that exist
    GAP = 12
    SW_W = 72                     # the switch, same as the pane's other rows
    TOG_X = width - 28 - SW_W
    # A row the viewer ADDED carries a fourth control, remove, between the
    # down arrow and the switch -- as the reference app does for e.g.
    # "Trending Anime". The arrows are laid out as if it is always there and
    # slide RIGHT by one slot when it is not, because Kodi cannot reposition
    # a control by condition but it can slide one; the same conditional-slide
    # idiom Detail uses to bottom-anchor its hero title.
    RM_X = TOG_X - GAP - BTN
    DOWN_X = RM_X - GAP - BTN
    UP_X = DOWN_X - GAP - BTN
    SHIFT = BTN + GAP
    Y = (H - BTN) // 2
    P = f"homerow_{slot}"

    DIM = 38                      # the reference app's unavailable arrow

    def circle(x: int, glyph: int, focus_id: int, flag: str) -> str:
        """The visual half of one arrow: a filled circle when focused, an
        outline when not, with the glyph on top. The button itself is
        transparent and sits over this -- the same split the rest of the
        skin uses, so focus never has to move to a textured control.

        The whole arrow fades to DIM when the row cannot move that way. It
        is a zero-time conditional fade on the wrapping group rather than a
        `<visible>`, because hiding it leaves a hole in the first and last
        rows where the reference app shows a greyed arrow."""
        return f"""
                        <control type="group">
                            <animation effect="fade" start="100" end="{DIM}" time="0"
                                       condition="String.IsEmpty(Window.Property({flag}))">Conditional</animation>
                        <control type="image">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texture>circle-outline.png</texture>
                            <colordiffuse>$INFO[Window.Property(text_tertiary)]</colordiffuse>
                        </control>
                        <control type="image">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texture>circle.png</texture>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <visible>Control.HasFocus({focus_id})</visible>
                        </control>
                        <control type="label">
                            <posx>{x}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <align>center</align><aligny>center</aligny>
                            <font>tofa_font_icons_26</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>{chr(glyph)}</label>
                        </control>
                        </control>"""

    # The pane's own switch, redrawn against WINDOW properties. Same
    # geometry and the same two-parked-knobs trick as settings_toggle_row
    # (Kodi cannot animate a control's position, see ANIMATION.md); it
    # cannot simply be reused because that one reads ListItem properties
    # and these rows are not list items.
    SH, KNOB = 38, 30
    SY = (H - SH) // 2
    on = f"String.IsEqual(Window.Property({P}_checked),1)"
    # The switch needs its OWN focus signal. The arrows show focus by
    # filling their circle, but a switch is already filled when it is on, so
    # focus has to read as a ring around it rather than a change of fill.
    # h52 outline against the 38-high switch = a 7px inset all round, and
    # 52 is a capsule height that actually ships an asset
    # (feedback_capsule_ninepatch_rule).
    RING_PAD = 7
    ring = f"""
                        <control type="image">
                            <visible>Control.HasFocus({tog_id})</visible>
                            <posx>{TOG_X - RING_PAD}</posx>
                            <posy>{(H - 38) // 2 - RING_PAD}</posy>
                            <width>{SW_W + 2 * RING_PAD}</width>
                            <height>52</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="26">capsule-h52-outline.png</texture>
                        </control>"""
    switch = f"""
                        <control type="image">
                            <posx>{TOG_X}</posx><posy>{SY}</posy>
                            <width>{SW_W}</width><height>{SH}</height>
                            <colordiffuse>{T.SURFACE_TRACK}</colordiffuse>
                            <texture border="19">capsule-h38.png</texture>
                        </control>
                        <control type="image">
                            <visible>{on}</visible>
                            <posx>{TOG_X}</posx><posy>{SY}</posy>
                            <width>{SW_W}</width><height>{SH}</height>
                            <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                            <texture border="19">capsule-h38.png</texture>
                        </control>
                        <control type="image">
                            <visible>!{on}</visible>
                            <posx>{TOG_X + 4}</posx><posy>{SY + 4}</posy>
                            <width>{KNOB}</width><height>{KNOB}</height>
                            <colordiffuse>$INFO[Window.Property(text_tertiary)]</colordiffuse>
                            <texture>circle.png</texture>
                        </control>
                        <control type="image">
                            <visible>{on}</visible>
                            <posx>{TOG_X + SW_W - KNOB - 4}</posx><posy>{SY + 4}</posy>
                            <width>{KNOB}</width><height>{KNOB}</height>
                            <colordiffuse>$INFO[Window.Property(on_accent_color)]</colordiffuse>
                            <texture>circle.png</texture>
                        </control>{ring}"""

    can_rm = f"!String.IsEmpty(Window.Property({P}_can_remove))"
    slide = (f"""
                            <animation effect="slide" start="0,0" end="{SHIFT},0"
                                       time="0" condition="!{can_rm}">Conditional</animation>""")

    remove = f"""
                        <control type="image">
                            <posx>{RM_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texture>circle-outline.png</texture>
                            <colordiffuse>$INFO[Window.Property(text_tertiary)]</colordiffuse>
                            <visible>{can_rm}</visible>
                        </control>
                        <control type="image">
                            <posx>{RM_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texture>circle.png</texture>
                            <colordiffuse>{T.STATUS_RED}</colordiffuse>
                            <visible>Control.HasFocus({rm_id}) + {can_rm}</visible>
                        </control>
                        <control type="label">
                            <posx>{RM_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <align>center</align><aligny>center</aligny>
                            <font>tofa_font_icons_26</font>
                            <textcolor>{T.STATUS_RED}</textcolor>
                            <label>{chr(icon_glyphs.MINUS_CIRCLE)}</label>
                            <visible>{can_rm} + !Control.HasFocus({rm_id})</visible>
                        </control>
                        <control type="label">
                            <posx>{RM_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <align>center</align><aligny>center</aligny>
                            <font>tofa_font_icons_26</font>
                            <textcolor>$INFO[Window.Property(on_accent_color)]</textcolor>
                            <label>{chr(icon_glyphs.MINUS_CIRCLE)}</label>
                            <visible>{can_rm} + Control.HasFocus({rm_id})</visible>
                        </control>
                        <control type="button" id="{rm_id}">
                            <posx>{RM_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texturefocus>transparent-6px.png</texturefocus>
                            <texturenofocus>transparent-6px.png</texturenofocus>
                            <label></label>
                            <enable>{can_rm}</enable>
                        </control>"""

    can_up = f"!String.IsEmpty(Window.Property({P}_can_up))"
    can_down = f"!String.IsEmpty(Window.Property({P}_can_down))"

    return f"""
                    <control type="group" id="{group_id}">
                        <width>{width}</width>
                        <height>{H}</height>
                        <visible>!String.IsEmpty(Window.Property({P}_title))</visible>
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>0</posy>
                            <width>{UP_X - TEXT_X - 16}</width>
                            <height>{H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property({P}_title)]</label>
                            <animation effect="slide" start="0,0" end="0,-9" time="0"
                                       condition="!String.IsEmpty(Window.Property({P}_sub))">Conditional</animation>
                        </control>
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>{H // 2 + 2}</posy>
                            <width>{UP_X - TEXT_X - 16}</width>
                            <height>24</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>$INFO[Window.Property({P}_sub)]</label>
                            <visible>!String.IsEmpty(Window.Property({P}_sub))</visible>
                        </control>
                        <control type="group">{slide}{circle(UP_X, icon_glyphs.ARROW_UP, up_id, f"{P}_can_up")}{circle(DOWN_X, icon_glyphs.ARROW_DOWN, down_id, f"{P}_can_down")}
                        </control>{remove}
{switch}
                        <control type="button" id="{up_id}">
                            <posx>{UP_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texturefocus>transparent-6px.png</texturefocus>
                            <texturenofocus>transparent-6px.png</texturenofocus>
                            <label></label>{slide}
                            <enable>{can_up}</enable>
                        </control>
                        <control type="button" id="{down_id}">
                            <posx>{DOWN_X}</posx><posy>{Y}</posy>
                            <width>{BTN}</width><height>{BTN}</height>
                            <texturefocus>transparent-6px.png</texturefocus>
                            <texturenofocus>transparent-6px.png</texturenofocus>
                            <label></label>{slide}
                            <enable>{can_down}</enable>
                        </control>
                        <control type="button" id="{tog_id}">
                            <posx>{TOG_X}</posx><posy>0</posy>
                            <width>{SW_W}</width><height>{H}</height>
                            <texturefocus>transparent-6px.png</texturefocus>
                            <texturenofocus>transparent-6px.png</texturenofocus>
                            <label></label>
                        </control>
                    </control>"""


def settings_home_row(list_id: int, width: int = T.SETTINGS_DETAIL_W_WIDE) -> tuple[str, str]:
    """One row of the home-screen editor: its name, and whether it is on.

    Compact and single-line, unlike the pane's other rows -- there are up to
    nine of them and they are a LIST of one thing, not nine separate settings.

    The state label is positioned by its LEFT edge even though it is
    right-aligned: inside a list item Kodi treats <posx> as the left edge,
    unlike a window-level label where a right-aligned posx IS the right edge
    (reference_kodi_layout_traps). Getting that backwards pushed the word
    clean off the row, which reads as "the property never got set".

    No inline up/down arrows, which is where this departs from the app. The
    app gives every row three independently focusable controls (up, down, and
    a switch); a D-pad has no way to reach a third control inside a list item,
    and Left is already "back to the sidebar" on this pane. Select opens a
    small action panel offering the same three choices instead."""
    H = T.SETTINGS_HOMEROW_H
    TEXT_X = 18

    def _body(title_color: str, state_color: str, gate: str) -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="group">{vis}
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>0</posy>
                            <width>{width - TEXT_X - 160}</width>
                            <height>{H}</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>{title_color}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <posx>{width - 28 - 130}</posx>
                            <posy>0</posy>
                            <width>130</width>
                            <height>{H}</height>
                            <align>right</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>{state_color}</textcolor>
                            <label>$INFO[ListItem.Property(state)]</label>
                        </control>
                    </control>"""

    # A row that is switched OFF is drawn muted, so the list reads as an
    # ordered set with some members greyed rather than as a list of labels
    # with a word after each.
    off = "String.IsEqual(ListItem.Property(checked),1)"
    rest = (_body("$INFO[Window.Property(text_primary)]",
                  "$INFO[Window.Property(text_tertiary)]", off)
            + _body("$INFO[Window.Property(text_tertiary)]",
                    "$INFO[Window.Property(text_tertiary)]", f"!{off}"))

    item = f"""                <itemlayout width="{width}" height="{H}">{rest}
                </itemlayout>"""

    focused = f"""                <focusedlayout width="{width}" height="{H}">
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>2</posy>
                        <width>{width}</width>
                        <height>{H - 4}</height>
                        <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                        <texture border="14">rounded-14.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>2</posy>
                        <width>{width}</width>
                        <height>{H - 4}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="14">rounded-14-outline.png</texture>
                    </control>{_body(
                        "$INFO[Window.Property(accent_color)]",
                        "$INFO[Window.Property(text_secondary)]",
                        f"Control.HasFocus({list_id})")}{_body(
                        "$INFO[Window.Property(text_primary)]",
                        "$INFO[Window.Property(text_tertiary)]",
                        f"!Control.HasFocus({list_id})")}
                </focusedlayout>"""
    return item, focused


def settings_add_row(list_id: int, width: int = T.SETTINGS_DETAIL_W_WIDE) -> tuple[str, str]:
    """9.4's two "add a row" actions under the home-screen editor.

    Accent text with a trailing plus, not a normal row: these ADD something
    rather than change something that is already there, and the app draws
    them that way. Shorter than an action row for the same reason -- the
    subtitle is one clause, not an explanation."""
    H = T.SETTINGS_HOMEADD_H
    TEXT_X = 18

    def _body(gate: str) -> str:
        vis = f"""
                        <visible>{gate}</visible>""" if gate else ""
        return f"""
                    <control type="group">{vis}
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>14</posy>
                            <width>{width - TEXT_X - 90}</width>
                            <height>32</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_ROW_TITLE}</font>
                            <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <posx>{TEXT_X}</posx>
                            <posy>46</posy>
                            <width>{width - TEXT_X - 90}</width>
                            <height>26</height>
                            <aligny>center</aligny>
                            <font>{T.FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(summary)]</label>
                        </control>
                        <control type="label">
                            <posx>{width - 28 - 40}</posx>
                            <posy>0</posy>
                            <width>40</width>
                            <height>{H}</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{T.FONT_ICON_26}</font>
                            <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                            <label>&#x{icon_glyphs.PLUS:04X};</label>
                        </control>
                    </control>"""

    card = f"""
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>{T.PANEL_WASH}</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>"""

    item = f"""                <itemlayout width="{width}" height="{H}">{card}{_body("")}
                </itemlayout>"""
    focused = f"""                <focusedlayout width="{width}" height="{H}">{card}
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(settings_row_wash)]</colordiffuse>
                        <texture border="20">rounded-20.png</texture>
                    </control>
                    <control type="image">
                        <visible>Control.HasFocus({list_id})</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{width}</width>
                        <height>{H}</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture border="20">rounded-20-outline.png</texture>
                    </control>{_body("")}
                </focusedlayout>"""
    return item, focused


def settings_choice_row(list_id: int, *, value_property: str,
                        **kwargs) -> tuple[str, str]:
    """A detail-pane row whose value is one of many, shown as text with a
    chevron and picked in a dialog.

    Used where a segmented control would not fit: 27 regions and 9 languages
    are both far past what three inline pills can hold. Same body as the
    toggle and the segmented row, so the four stay visually one family."""
    W = kwargs.get("width", T.SETTINGS_DETAIL_W_WIDE)
    trailing = f"""
                    <control type="label">
                        <posx>{W - 68 - 400}</posx>
                        <posy>0</posy>
                        <width>400</width>
                        <height>{T.SETTINGS_ACTION_ROW_H}</height>
                        <align>right</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_BODY}</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property({value_property})]</label>
                    </control>
                    <control type="label">
                        <posx>{W - 56}</posx>
                        <posy>0</posy>
                        <width>28</width>
                        <height>{T.SETTINGS_ACTION_ROW_H}</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>{T.FONT_ICON_19}</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>&#x{icon_glyphs.CHEVRON_RIGHT:04X};</label>
                    </control>"""
    return _settings_control_row(list_id, trailing=trailing,
                                 trailing_w=468, **kwargs)


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
{indent}        <posx>19</posx>
{indent}        <posy>18</posy>
{indent}        <width>{width - 38}</width>
{indent}        <height>34</height>
{indent}        <aligny>center</aligny>
{indent}        <font>{T.FONT_ROW_TITLE}</font>
{indent}        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
{indent}        <label>{title}</label>
{indent}    </control>
{indent}    <control type="textbox">
{indent}        <posx>19</posx>
{indent}        <posy>56</posy>
{indent}        <width>{width - 38}</width>
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
TOAST_FADE_OUT = 250  # 8.9: "all toasts fade <300ms"
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
