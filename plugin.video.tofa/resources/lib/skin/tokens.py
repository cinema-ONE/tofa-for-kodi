# -*- coding: utf-8 -*-
"""The skin's design tokens: spacing, geometry, colour and type roles.

Single source of truth for values that were previously repeated as literals
across fragments.py and the .tpl files -- `CELL_HEIGHT` alone was computed in
Python and then hand-copied into main.xml.tpl fifteen times, kept in sync only
by comment. Templates can't reference Python, so screens.py passes these in as
format kwargs (see `template_kwargs()`); anything a template needs must be
exported there rather than retyped.

Deliberately stdlib-only and free of xbmc imports, so `build.render_all()`
still runs outside Kodi.

Spacing/geometry are measured off real Apple TV captures, not carried over
from the old values -- see feedback_apple_tv_source_of_truth. Where a measured
value and an existing one disagreed, the measurement won.
"""
from __future__ import annotations

# ---------------------------------------------------------------- spacing --
# One ramp. Everything else is expressed in terms of these, so "make it more
# generous" is one edit rather than a hunt through two thousand lines of XML.
SPACE_XS = 8
SPACE_SM = 16
SPACE_MD = 24
SPACE_LG = 32
SPACE_XL = 48
SPACE_2XL = 64

SCREEN_W = 1920
SCREEN_H = 1080

# Left edge of screen content -- per screen, because the real app genuinely
# uses different ones. All measured off native 1920x1080 captures in
# internal-docs/atv-reference/, not eyeballed:
#
#   Home      156   hero title, meta, ratings, synopsis, row headers, logo
#   Discover  170   tab pills, row headers, poster art
#   Browse     68   sidebar rail's outer edge (see nav/sidebar fragments)
#   Search     80   keyboard column (its own documented edge)
#
# The design spec states these as 76 and 90, which is the SAME geometry read
# from inside the 80px inset tvOS applies to its layout container: 76+80=156,
# 90+80=170, and the 14px gap between the two screens matches exactly. Its
# horizontal numbers are relative, so never paste them in as coordinates --
# see project_tv_design_spec_margins_are_inset.
HOME_LEFT = 156
DISCOVER_LEFT = 170

# Width available to a row's label/list. Derived from the LARGER margin so the
# one value is safe on both screens: on Home it simply stops 14px short of the
# right edge, and rows overflow off-screen there anyway.
CONTENT_WIDTH = SCREEN_W - DISCOVER_LEFT

# Top scrim behind the nav bar.
SCRIM_H = 140

#: Profile avatar in the top-right of the nav row. Measured off the Apple TV
#: app: a 64px circle centred at (1748, 80), which is the nav bar's own
#: vertical centre. Visual only -- see the template's own note.
NAV_AVATAR_SIZE = 64
NAV_AVATAR_X = 1748 - NAV_AVATAR_SIZE // 2
NAV_AVATAR_Y = 80 - NAV_AVATAR_SIZE // 2
#: The art sits at 92% of the ring -- BOTH a preset and an uploaded photo.
#: The web app fills the circle with a photo (object-cover) and insets only
#: presets, but at 64px over a hero that read as touching the border, and
#: Adrian asked for it "down a notch". One number for both also means the
#: marker does not resize when a profile switches between the two.
#:
#: Historical note on where 92% came from. Both
#: numbers are the web app's, read out of its avatar renderer rather than
#: guessed: presets get `width/height: 92%` with `object-fit: contain`, a
#: photo gets `h-full w-full object-cover`.
#:
#: It was 44-in-64 before, fitted to the old Fluent Emoji presets, which
#: floated in their own canvas at ~88% ink. The 0.9.29 presets are busts
#: that bleed to the canvas edge (measured: 100% vertically), so at 44 they
#: floated in the middle of the ring with a gap all round -- and at the full
#: 64 they touched it, which Adrian spotted against the web UI: "the profile
#: pictures are slightly smaller than the circle. Ours touch the border."
#:
#: NOTE there is still no Apple TV reference for this
#: (feedback_apple_tv_source_of_truth) -- tofa's TV clients have not shipped
#: the new avatars. The web app is the only extant rendering.
NAV_AVATAR_ART = round(NAV_AVATAR_SIZE * 0.92)
NAV_AVATAR_ART_X = NAV_AVATAR_X + (NAV_AVATAR_SIZE - NAV_AVATAR_ART) // 2
NAV_AVATAR_ART_Y = NAV_AVATAR_Y + (NAV_AVATAR_SIZE - NAV_AVATAR_ART) // 2
#: Soft drop shadow behind the avatar, so it separates from whatever the Home
#: hero happens to be showing. 4 allows floating chrome a soft, large shadow,
#: but only where it floats over artwork -- the nav row's only such case.
#: The 16px spread and the 3px downward bias are FITTED to the real Apple TV,
#: not picked -- see gen_avatar_shadow(); the offset is baked into the art, so
#: the control simply sits centred on the avatar.
NAV_AVATAR_SHADOW_PAD = 16
NAV_AVATAR_SHADOW = NAV_AVATAR_SIZE + 2 * NAV_AVATAR_SHADOW_PAD
NAV_AVATAR_SHADOW_X = NAV_AVATAR_X - NAV_AVATAR_SHADOW_PAD
NAV_AVATAR_SHADOW_Y = NAV_AVATAR_Y - NAV_AVATAR_SHADOW_PAD

# ------------------------------------------------------------- poster card --
# 252x378, the size TV-DESIGN states twice -- 7.4 ("252x378pt cards") and
# 7.9.3 ("a standard 2:3 poster (252x378 ...)") -- both in 1:1 sections. It
# also reconciles the row that mixes the two card forms: 7.9.3 locks the open
# 16:9 frame's HEIGHT to the poster's and derives 378 -> 672, which is
# already what DISCOVER_FOCUS_ART_* uses. At the old 372 the portrait and
# wide cards in the SAME Discover row were 6px different, against 7.9.3's
# "both forms are the same total height".
#
# Measured live off the real app at ~257 wide (2026-07-31, gutter detection
# on native-1080p captures); 252 + a soft edge either side is the same
# number, so spec and app agree and the old 248 was simply narrow.
POSTER_W = 252
POSTER_H = 378

#: The artwork-less poster card, following the macOS app (see
#: fragments.poster_visual). Proportions taken off its own card: the mark sits
#: a little above centre at about a third of the card's width, with the title
#: directly beneath it. Ink is deliberately dim -- this is a placeholder, not
#: a thing to look at.
POSTER_PLACEHOLDER_PAD = 16
POSTER_PLACEHOLDER_ICON_Y = 134
POSTER_PLACEHOLDER_ICON_H = 80
POSTER_PLACEHOLDER_TITLE_Y = 228
#: ONE line, not two. macOS wraps this title over two or three lines; Kodi
#: will not. <wrapmultiline> is honoured on a static label (Detail's synopsis
#: uses it) but NOT on a label inside a list ITEM layout -- tested at 68 and
#: at 96 high, both ellipsised on one line. Wrapping would mean splitting the
#: title in Python per item and setting two properties, which every card
#: builder would then have to remember: the drift this family already suffers
#: from. Left as one ellipsised line until it is worth that.
POSTER_PLACEHOLDER_TITLE_H = 34
POSTER_PLACEHOLDER_INK = "0x8FA9C4D6"

#: Format badges down the poster's left edge, under the rating chip. Measured
#: off the macOS app: pills on a 30px pitch with ~22 of ink, sharing the
#: rating chip's own 8px inset. The BOX is as wide as the widest pill
#: (DTS-HD MA renders 99 wide at this height) because a pill is drawn
#: aspect-kept and left-aligned inside it -- see fragments.format_badges.
CARD_BADGE_X = 8
CARD_BADGE_Y = 50
CARD_BADGE_H = 22
CARD_BADGE_PITCH = 30
CARD_BADGE_BOX_W = 110
CARD_BADGE_SLOTS = 3
#: Where the stack starts when there is NO rating chip above it: the chip's
#: own inset, so the badges simply take its place instead of leaving a hole.
CARD_BADGE_TOP_Y = 8

# Slack around the poster inside its cell: the focus glow bleeds into it, so
# it can't be zero. It must be >= GLOW_PAD in tools/gen_poster_assets.py
# (10), NOT equal to it -- the glow is 10 on all four sides and the extra
# horizontal room here is just unused slack.
HPAD = 14
TOP_PAD = 10
# = 280. The spec never states the gap between cards, only the card, so this
# comes off the live app: measured column pitch is ~281 on Browse and ~275 on
# the person screen. Was 296 (a 48px gap where the app's is ~28), which read
# visibly looser than the real thing -- the card width was only 3.5% off but
# the GAP was nearly double.
CELL_W = POSTER_W + 2 * HPAD

# The right edge every bleeding row runs to: one HPAD past the screen, so
# the trailing cell padding falls off it. A rows REGION (the grouplist that
# stacks the rows) has to reach the same place -- a grouplist clips its
# children to its own width, so a row list extended past the screen is
# simply cut back to the region's edge. That clip is what kept a ~14px strip
# of background at the right of Home after the lists themselves were widened.
ROW_BLEED_RIGHT = SCREEN_W + HPAD
HOME_ROWS_W = ROW_BLEED_RIGHT - HOME_LEFT
DISCOVER_ROWS_W = ROW_BLEED_RIGHT - DISCOVER_LEFT



# Caption block under the poster.
CAPTION_GAP = SPACE_SM        # poster bottom -> meta line
CAPTION_META_H = 24
# Title line -> meta line. Zero because the two label boxes already carry
# their own slack: at 34/4 the rendered gap between "Hugo" and its
# "2011 . 126 MIN LEFT" was 16px of ink, enough that the last row's caption
# ran off the bottom of a 1080 screen.
CAPTION_TITLE_GAP = 0
# 32, not 34: measured, the 24pt semibold's ink occupies 31px of this box
# from its top, so 32 keeps a pixel of descender clearance while giving the
# row back 2px. Do not go to 30 -- that clips the g in a title like "Hugo".
CAPTION_TITLE_H = 32
CAPTION_BOTTOM = 6

# Full cell height. THE definition -- every row list's <height>/<itemheight>
# derives from this instead of restating 466.
CELL_H = (
    TOP_PAD + POSTER_H + CAPTION_GAP + CAPTION_META_H
    + CAPTION_TITLE_GAP + CAPTION_TITLE_H + CAPTION_BOTTOM
)

# --------------------------------------------------------------- poster row --
# A row = title label, gap, then the horizontal list. Home used 64, Discover
# 48, Search 50 for the same relationship; unified on the most generous.
ROW_TITLE_H = 34
ROW_TITLE_GAP = SPACE_2XL
ROW_H = ROW_TITLE_GAP + CELL_H
ROW_GAP = SPACE_MD            # between stacked rows (was 18)
ROW_PITCH = ROW_H + ROW_GAP

# Lists sit at -HPAD so the first poster's art aligns to the page margin
# rather than to its cell's padded edge.
ROW_LIST_X = -HPAD

# A row's own block INCLUDES the gap that follows it, and the grouplists
# that stack rows run itemgap=0. That is what lets a rows region bleed off
# the bottom of the screen while a FOCUSED row still stops clear of it:
# Kodi reveals a focused child in full, so the child's trailing pad becomes
# the margin under its caption, and the next row -- drawn past the screen
# edge -- is cut by the screen rather than by an invisible clip above it.
#
# Sizing the VIEWPORT short (the previous approach) gave the margin but no
# bleed, because the two are the same edge for a grouplist. They are not for
# a horizontal list: there Kodi does not clamp the scroll to the viewport's
# far edge, so a row's width can simply run to the screen edge and the
# focused card does not move. Measured both ways.
ROW_BLOCK_H = ROW_H + ROW_GAP

# Rows regions run to the bottom of the screen now; the margin under the
# last caption comes from ROW_BLOCK_H's trailing pad instead.
# Search's shelves sit at an ABSOLUTE 382 (parent group 6800's 324 + a local
# 58) -- the parent's offset has to be in the sum or Kodi's
# keep-focused-item-in-view math under-scrolls and cuts off the lower rows.
DISCOVER_ROWS_H = SCREEN_H - 252
# The shelves' own local posy inside group 6800, and the ABSOLUTE y that
# lands on. Both are needed: Kodi's keep-focused-item-in-view math wants the
# region's true screen position, so the parent's 324 has to be in the sum or
# the lower rows under-scroll and get cut.
#
# 49, not the old 58. The Top Result's poster then lands on 383, which is
# where the live Apple TV puts it; at 58 our whole column sat 9px low and
# every text line with it (measured +3 after centring).
# The "Results for ..." caption's own posy inside group 6800, chosen so its
# BASELINE lands on the app's 359 and the Top Result poster below it gets the
# 23px of air the app leaves (we had 5). Kodi top-aligns a label by the font's
# ascent, so box top = 359 - 0.9688*30 = 330, i.e. 6 inside a group at 324.
#
# Depends on FONT_RESULTS_CAPTION's size: re-derive if that moves.
SEARCH_CAPTION_Y = 6
SEARCH_SHELVES_Y = 49
SEARCH_SHELVES_ABS_Y = 324 + SEARCH_SHELVES_Y
SEARCH_SHELVES_H = SCREEN_H - SEARCH_SHELVES_ABS_Y
# Where the results column's own content starts, measured off the live Apple
# TV app (2026-08-06): its "Results for", "Actors" and "Discover" labels and
# its Top Result poster all sit on 666. Ours sat on 771 -- 105px further in,
# which pushed the whole right-hand column off the app's grid.
SEARCH_COLUMN_X = 666
# The grouplist inside it is pulled 20 left so a card's focus glow is not
# clipped, so the shelves themselves begin here. Both the clip and the lists
# inside it run to the screen edge, same reasoning as DETAIL_SHELF_W.
SEARCH_SHELF_X = SEARCH_COLUMN_X - 20
SEARCH_SHELF_W = ROW_BLEED_RIGHT - SEARCH_SHELF_X

# Search's Top Result cell. Typed in TWO places before this existed -- the
# itemlayout inside fragments.py:top_result_card() and the <itemwidth>/
# <itemheight>/<height> of list 6805 and group 6806 in main.xml.tpl -- which
# is the same split that let the episode grid's 350/320 disagree with its own
# template. Kodi advances a vertical list by the ITEMLAYOUT's declared height
# and lays the row out at its declared width, so the two have to agree.
#
# The height is authored, not derived: TOP_PAD + POSTER_H is 388 and the cell
# is 390, i.e. the poster block plus the 2px the focus border's bottom stroke
# needs. There is no caption underneath -- Top Result's text sits to the
# RIGHT of the poster, which is the whole reason it is not a poster_card().
TOP_RESULT_CELL_W = 1089
# 7.3: "bare poster 220x330pt", and the live Apple TV measures exactly that
# (ratio 0.667). NOT the grid card's 252x378 -- this is a hero, not a cell,
# and it also carries none of the grid card's chips (verified 2026-08-06 on a
# title WITH scores: "Up", Critics 93 / Audience 82, shows no rating chip and
# no format badges here while every Movies card below it does).
TOP_RESULT_POSTER_W = 220
TOP_RESULT_POSTER_H = 330
# The cell's own left inset. 20, matching the grouplist's -20 pull, so the
# poster lands exactly on SEARCH_COLUMN_X and its focus glow still has
# GLOW_PAD to bleed into.
TOP_RESULT_POSTER_X = 20
TOP_RESULT_POSTER_Y = TOP_PAD
# Poster block plus the glow's room underneath it.
TOP_RESULT_CELL_H = TOP_RESULT_POSTER_Y + TOP_RESULT_POSTER_H + TOP_PAD
# Text column. The app measures a 48px gutter off the poster's right edge.
TOP_RESULT_TEXT_X = TOP_RESULT_POSTER_X + TOP_RESULT_POSTER_W + 48
TOP_RESULT_TEXT_W = 700
TOP_RESULT_OVERVIEW_W = 760

# Search's shelves CARRY their own trailing gap and grouplist 6810 runs
# itemgap=0 -- the same arrangement ROW_BLOCK_H describes above, which Search
# was the last scrolling region not to adopt. Its 32 lived in `<itemgap>`, and
# an itemgap sits BETWEEN items: the last shelf therefore came to rest flush
# against the bottom of the screen with no air under its captions, while Home,
# Discover and Settings all end with a pad. Moving the same 32 into each
# shelf's own height leaves every gap BETWEEN shelves exactly as it was and
# gives the last one a margin.
# Where a Search shelf's LIST starts inside its group, i.e. how much room the
# section title above it gets. Shared by Movies / Shows / Actors / Discover so
# the four cannot drift.
#
# 65, not the 50 each shelf used to type. Measured on the live Apple TV: its
# "Movies" title ink ends at 793 and the row's card art begins at 825, a gap
# of 31; ours was 16, roughly half. A card sits TOP_PAD (and a person tile
# PERSON_GLOW_PAD, the same 10) below its list's posy, so the band is the gap
# plus that: 43 + 31 + 1 - 10 = 65 in group-relative terms.
# Recent Searches. search_history.MAX_ENTRIES queries plus the trailing
# "Clear" row, times the row height. A Kodi list draws floor(height/itemheight)
# whole rows and CLIPS the remainder, so this has to be an exact multiple or
# the last entry arrives sliced. The list starts at an absolute y of 384
# (group 6800's 324 + its own group's 10 + 50), so 11 rows end at 1022, still
# clear of the screen bottom.
SEARCH_HISTORY_ROW_H = 58
SEARCH_HISTORY_ROWS = 10 + 1
SEARCH_HISTORY_H = SEARCH_HISTORY_ROWS * SEARCH_HISTORY_ROW_H

SEARCH_SECTION_BAND = 65

# 7.3's Actors shelf: "circular headshots 180pt". The live Apple TV measures
# a 181px photo on a 256 pitch; ours were 130 on 170, ~28% under both. The
# photo size picks the person-border/glow asset pair, so it must be one of
# gen_poster_assets.py's PERSON_PHOTOS.
#
# Detail's Cast & Crew stays at CAST_PHOTO (190) on a 290 pitch: the two are
# genuinely different sizes in the app, not one card at one size, and Detail
# already matched. The cell height keeps the same 22px of slack under the
# role line that CAST_TILE gives its own.
SEARCH_ACTOR_PHOTO = 180
SEARCH_ACTOR_CELL_W = 256
SEARCH_ACTOR_CELL_H = 280
# Section label band above the row, then the row itself.
SEARCH_ACTOR_ROW_Y = SEARCH_SECTION_BAND
SEARCH_ACTOR_ROW_H = SEARCH_ACTOR_CELL_H

SEARCH_SHELF_TRAIL = 32
SEARCH_TOP_RESULT_BLOCK_H = TOP_RESULT_CELL_H + SEARCH_SHELF_TRAIL
# The poster shelves (Movies / Shows / Discover) and the shorter Actors row.
# Derived, not typed: title band + the list's own height + the trailing gap.
# It was a literal 516, which silently stopped matching the moment the band
# grew from 50 to 65.
SEARCH_SHELF_BLOCK_H = SEARCH_SECTION_BAND + CELL_H + SEARCH_SHELF_TRAIL
SEARCH_ACTORS_BLOCK_H = SEARCH_ACTOR_ROW_Y + SEARCH_ACTOR_ROW_H + SEARCH_SHELF_TRAIL

SCROLLTIME = 200

#: A control id that does not, and must not, exist -- the way to tell a Kodi
#: PANEL "stop here" instead of wrapping round to item 1.
#:
#: A panel wraps on its own axis where a plain list does not, and Kodi decides
#: with `wrapAround = !action.HasActionsMeetingCondition()`: an ABSENT <ondown>
#: means wrap. Two things that look like fixes are not, both measured on
#: Detail's episode grid (2026-08-06):
#:
#:   no <ondown>          down from the last row ran 1, 5, 9, 1, 5, 9 ...
#:   <ondown>ITSELF</>    identical, 1, 5, 9, 1 -- naming the container stops
#:                        the internal wrap but then succeeds at focusing it,
#:                        and a panel taking focus resets to item 1. Search's
#:                        "abc"/"123" switcher was the same trap from the
#:                        other axis (see _search_wire_right_target).
#:
#: Naming an id that no control has satisfies the condition -- so the panel
#: does not wrap -- and then fails to find anywhere to go, so focus simply
#: stays put. Nothing to undo afterwards, and so nothing to flicker.
NAV_STOP = 9999

# How long the cursor must sit still before focus-driven work that is too
# expensive to repeat per keypress actually runs: the Home hero's
# full-screen backdrop, and Browse's load-the-library-on-highlight.
#
# 7.9.6 states it for the ambient wash -- roughly 180ms of stillness, so
# that running along a row cannot queue one full-screen blur per card
# crossed -- and
# the account's own `layout.focusedBackdropDelayMs` (200 on this server)
# overrides it at runtime. This is the fallback for a server that does not
# send one.
FOCUS_SETTLE_MS = 180

# 7.10.2: the hero is a focus follower and "crossfades ~300ms". Kodi's own
# <fadetime> on an image control does exactly this -- it cross-fades when the
# TEXTURE changes, which no <animation> can express (they fire on window and
# focus events, not on a texture swap).
#
# Runs after FOCUS_SETTLE_MS above, so scrubbing a row queues one fade at the
# end rather than one per card passed.
HERO_CROSSFADE_MS = 300

# The same 300ms clock, spent differently, for the hero's FOREGROUND block
# (logo, title, meta, ratings, synopsis).
#
# 7.10.2 asks the hero to crossfade -- the hero, not the hero's backdrop --
# and a crossfade needs two copies of the thing to dissolve between. An image
# control has them (Kodi keeps the outgoing texture; that is what fadetime
# does), a label does not: it has one string, which changes in a single frame.
# So the foreground DIPS instead: out over half the clock, swap while it is
# invisible, back in over the other half. Same total, same finish time as the
# backdrop's crossfade, and the swap itself is never seen.
#
# Deliberately half of HERO_CROSSFADE_MS rather than its own number, so the
# two halves of the hero cannot drift apart -- the failure 7.9.5 names, where
# a row "visibly changes width mid-transition" because two clocks disagreed.
HERO_TEXT_DISSOLVE_MS = HERO_CROSSFADE_MS // 2

# Browse's 5-column grid. Derived rather than typed so the grid follows
# CELL_W: at 296 the hand-written 420/1480 pair happened to be exact, and
# silently stopped being so the moment the cell changed width.
BROWSE_COLS = 5
BROWSE_GRID_X = 440 - HPAD      # poster art lands on the 440 edge the nav
                                # bar and Sort pill share
BROWSE_GRID_W = BROWSE_COLS * CELL_W

# ------------------------------------------------ Browse's A-Z rail (right) --
# "All", A..Z, then "#", down the right margin. Measured off the Android TV
# app at 1920x1080 (internal-docs/androidtv-reference/browse-alpha-rail.png):
# pill 80x58 at x 1782..1861, pitch 68, first pill y 301. Every pill is the
# same height, "All" INCLUDED -- an earlier note here said All was taller,
# from eyeballing rather than pixel runs.
#
# `#` is the app's last entry, not a guess: it sits below the fold in any
# resting capture, so the rail was focused and Down held to its end for
# browse-alpha-rail-bottom.png. It is also the server's own bucket name
# (`letter=#` returns the 168 non-alphabetic titles).
#
# The Apple TV app has not shipped this screen yet, so Android is the
# reference here by Adrian's decision, and the styling is expected to be
# revisited when it does.
#
# NARROWER than the app's 80, and pushed almost to the screen edge rather
# than sitting at its 58px margin. Adrian's call 2026-08-06, to keep Browse
# at five columns: the fifth column's poster art ends at 1812
# (BROWSE_GRID_X + 4*CELL_W + HPAD + POSTER_W), so 108px remain. The app
# buys its own room by shrinking its Browse poster to 214 instead; ours is
# the 252 the spec pins, so the rail gives way instead of the cards.
#
#   art ends 1812 | 36 gap | pill 1848..1912 | 8 right margin
#
# Height and pitch are still the app's, so only the axis that had to move
# has moved.
ALPHA_PILL_W = 64
ALPHA_PILL_H = 58
ALPHA_PITCH = 68
ALPHA_RAIL_X = 1848
ALPHA_RAIL_Y = 301
#: The pill is 58 tall in a 68 box, so every item CARRIES its own 10px
#: trailing pad and the list needs no itemgap. That is what lets the rail
#: run to the screen edge while the pill that comes to rest at the bottom
#: still has air under it -- the same trick as ROW_BLOCK_H (72294b7) and
#: SETTINGS_GROUP_TRAIL, recorded here because the number is implied by the
#: pitch rather than written down, and a future pitch change would silently
#: take the pad with it.
ALPHA_ITEM_TRAIL = ALPHA_PITCH - ALPHA_PILL_H
#: Runs to the screen edge, like every other scrolling region here
#: (DISCOVER_ROWS_H, SEARCH_SHELVES_H, DETAIL_SHELF_H, PERSON_GRID_H,
#: SETTINGS_GROUPLIST_H all end at SCREEN_H).
#:
#: It used to be a whole number of pitches -- 11 x 68 = 748 -- which left 31
#: dead pixels under the rail and, worse, cut the 12th pill off at an
#: invisible line 31px above the screen edge instead of at the edge. A rail
#: that stops short reads as "that is all there is"; one that runs off the
#: bottom reads as "keep going", which is true: 28 entries at pitch 68 is
#: 1904px against a 1080 screen, so it always scrolls.
ALPHA_RAIL_H = SCREEN_H - ALPHA_RAIL_Y
#: The rail's entries, in the app's order. "#" LAST, "All" first. The ORDER,
#: not the contents: a library only gets the pills its letter facets report
#: as non-empty, filtered through this tuple so the order is ours and not
#: the order the server happened to answer in.
ALPHA_KEYS = ("All",) + tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ("#",)
#: Below this many titles there is no rail. Roughly four screens of the
#: 5-column grid -- under that the library is a short scroll and a second
#: navigation column beside it costs more attention than it saves.
ALPHA_MIN_TITLES = 120

# ------------------------------------------------- collections index (7.5) --
# 7.5 treats a collection as a set rather than as a title, so its tile is
# landscape 16:9 where every other tile is 2:3 portrait. Three columns,
# tiles 448pt wide, radius 14, with gaps of 30 and 44. The caption under
# each one is a fixed 86pt tall so the rows stay aligned: the name at 22pt
# semibold over at most two lines, then the title count, tabular, white 50%.
#
# Verified independently against the Android TV app, which lays its own out
# at exactly these numbers: columns at x 432/910/1388 (pitch 478 = 448 + 30)
# and a row pitch of 382 (252 + 86 + 44).
COLLECTION_COLS = 3
COLLECTION_TILE_W = 448
COLLECTION_TILE_H = COLLECTION_TILE_W * 9 // 16    # 252
COLLECTION_RADIUS = 14
COLLECTION_GAP_X = 30
COLLECTION_GAP_Y = 44
COLLECTION_CAPTION_H = 86                          # fixed, so rows align
COLLECTION_CELL_W = COLLECTION_TILE_W + COLLECTION_GAP_X
COLLECTION_CELL_H = COLLECTION_TILE_H + COLLECTION_CAPTION_H + COLLECTION_GAP_Y
COLLECTION_GRID_W = COLLECTION_COLS * COLLECTION_CELL_W

# --------------------------------------------------------- grid row pitch --
# A vertical GRID needs more air below the caption than a horizontal row
# does: in a grid the caption has another row's artwork directly beneath it,
# so without extra space it reads as belonging to the wrong card. CELL_H on
# its own (a row's cell) is too tight for any grid.
#
# The app does NOT use one value for this. Measured art-top to art-top off
# the native-1080p captures in internal-docs/atv-reference/:
#
#   Browse (browse-full.png)             505
#   Person (person-filmography.png)      489   <- GRID_GAP
#
# so it is a per-grid token, not a constant. Add one here for any new grid
# rather than reaching for CELL_H, which will look cramped -- that is exactly
# how the person grid first shipped.
#
# Kodi's row-to-row advance follows the ITEMLAYOUT's own declared height, so
# a grid must both pass its gap to poster_card(extra_bottom_pad=) and set the
# panel's <itemheight> to the matching *_CELL_H. Setting only one silently
# does nothing.
GRID_GAP = 17                                 # the default for a poster grid
GRID_GAP_BROWSE = 32                          # Browse's measured exception
GRID_CELL_H = CELL_H + GRID_GAP               # 489, app measures 489 (person)
BROWSE_CELL_H = CELL_H + GRID_GAP_BROWSE      # 504, app measures 505
# Detail's More Like This: two stacked shelves from x=100, mirroring that
# inset on the right (1920 - 100 - 100), and a viewport running from the
# header rule to the bottom of the screen. Two rows exceed it, so the
# grouplist scrolls between them exactly as the app's does.
# Runs to the screen's right edge, not to a mirrored 100px margin: a row
# that stops short leaves a dead band and clips its rightmost card on an
# invisible line instead of on the screen. Widening does NOT move a focused
# card -- Kodi refuses to clamp a horizontal list's scroll to the viewport's
# far edge, measured before and after on a 25-item row (the focused last
# card stayed at 1813 either way).
DETAIL_SHELF_W = ROW_BLEED_RIGHT - 100
DETAIL_SHELF_H = SCREEN_H - 150

# Cast & Crew tiles (Detail page 2). Square cells, not posters: 1740 of panel
# width / CAST_TILE = exactly CAST_COLS columns with nothing left over, and
# the app's own photo rows sit at 236 and 525 in
# internal-docs/atv-reference/detail-cast-crew.png -- pitch 289, so 290.
#
# These are shared with windows/detail.py, which sizes each panel at runtime
# from its own row count. Changing the tile here therefore moves both the XML
# and that calculation together.
CAST_TILE = 290
CAST_PHOTO = 190
CAST_COLS = 6
CAST_PANEL_W = CAST_COLS * CAST_TILE

# 2's status triad, semantic ONLY: "never use red outside status/destructive".
# Distinct from the rating quality ramp in windows/theme.py, whose own comment
# insists the two never move together -- a score is a reading, not an alarm.
# Only the red is needed so far; add the others here when something uses them.
STATUS_RED = "0xFFF87171"

# Top of 9.7's empty scaffold (fragments.py:empty_state()). Measured off the
# real Apple TV app: its icon slot centres on 521, and the slot is 64 tall.
EMPTY_STATE_Y = 521 - 32

# The scrolling viewport the two panels are stacked inside (grouplist 6250).
CAST_VIEWPORT_H = 930
# A panel taller than the viewport can never be scrolled by the grouplist
# (see detail.py:_size_person_panels), so a section is only allowed to grow
# to whole rows that fit. 3 * 290 = 870 of 930.
CAST_MAX_ROWS = CAST_VIEWPORT_H // CAST_TILE
CAST_PANEL_H_MAX = CAST_MAX_ROWS * CAST_TILE   # the XML's pre-data placeholder

# ------------------------------------------------- person / filmography --
# 7.4. All measured off internal-docs/atv-reference/person-filmography.png
# (native 1080p, so 1:1) rather than taken from the prose, which only gives
# the card size and the two font scales.
PERSON_LEFT = 176               # name, subtitle, section label, poster art
PERSON_COLS = 5
PERSON_GRID_X = PERSON_LEFT - HPAD
PERSON_GRID_W = PERSON_COLS * CELL_W
# posy values are the CONTROL's top; the numbers in the comments are where
# the measured ink lands. Each was corrected once after measuring our own
# render against the capture (the label box has its own internal leading,
# so the control top is not the ink top and cannot be read off the
# reference directly).
PERSON_NAME_Y = 115             # ink 136-175 in the capture
PERSON_SUBTITLE_Y = 191         # ink 199-219
PERSON_SECTION_Y = 272          # ink 280-304
PERSON_GRID_Y = 331 - TOP_PAD   # measured first poster top edge = 331
PERSON_GRID_H = SCREEN_H - PERSON_GRID_Y

# 7.4 runs a near-black vertical gradient across the whole screen and calls
# it a deliberate one-off, tinted darker than abyss. Measured top #191A22 ->
# bottom #111216: in practice
# LIGHTER than our CANVAS (#030B10) and tinted toward purple, so it is a
# genuine one-off and not a reuse of the page background. Drawn from a
# generated texture (tools/gen_panel_assets.py:gen_person_bg) because Kodi
# has no gradient primitive.
PERSON_BG_TOP = "0xFF191A22"
PERSON_BG_BOTTOM = "0xFF111216"

# ------------------------------------------------------------ settings (9) --
# A three-column page: sidebar / detail / optional right rail. Every number
# measured off internal-docs/atv-reference/settings-account.png (native 1080p,
# 1:1) -- 6 describes the page but gives no coordinates at all.
#
# The rail is present on Account and Privacy & About only; the other pages let
# the detail column run the full width instead, which is why there are two
# widths rather than one plus a hidden rail.
SETTINGS_LEFT = HOME_LEFT               # 156, shared with Home's content edge
SETTINGS_SIDEBAR_W = 420
SETTINGS_GUTTER = 56
SETTINGS_DETAIL_X = SETTINGS_LEFT + SETTINGS_SIDEBAR_W + SETTINGS_GUTTER   # 632
SETTINGS_RAIL_X = 1348
SETTINGS_RAIL_W = 360
SETTINGS_DETAIL_W = SETTINGS_RAIL_X - SETTINGS_GUTTER - SETTINGS_DETAIL_X  # 660
SETTINGS_DETAIL_W_WIDE = SETTINGS_RAIL_X + SETTINGS_RAIL_W - SETTINGS_DETAIL_X  # 1076

# Sidebar. The profile card sits above the SETTINGS eyebrow, outside the nav
# list -- it is a display, never focusable.
SETTINGS_PROFILE_Y = 227
SETTINGS_PROFILE_H = 98
SETTINGS_EYEBROW_Y = 344                # ink 354-364
SETTINGS_NAV_Y = 381
# Taller than the app's 90-on-a-96-pitch, and with more air between the two
# text lines, by explicit request 2026-08-03: the two-line row read cramped
# at the measured size. A deliberate divergence -- do not "correct" it back
# to the capture.
SETTINGS_NAV_ROW_H = 100
SETTINGS_NAV_PITCH = 108                # 8px between rows
# Six pages: the app's five, plus "This Device" for the Kodi-only settings
# (skin fonts, local accent fallback, device id) it has no equivalent of.
SETTINGS_NAV_PAGES = 6
SETTINGS_NAV_LIST_H = SETTINGS_NAV_PAGES * SETTINGS_NAV_PITCH

# Detail column. posy values are the CONTROL's top; the comment gives where
# the measured ink lands, same convention as the person tokens above -- a
# label box has its own leading, so the ink top cannot be used directly.
SETTINGS_TITLE_Y = 219                  # ink 240-278
SETTINGS_SUBTITLE_Y = 299               # ink 307-326
SETTINGS_CONTENT_Y = 406                # first card, and the rail panel, share it

# Rows. A two-line action row (a title over an explanatory line, e.g. Switch
# Profile, Sign Out) is 109; a single-line value row (label left, value right,
# e.g. Email) is 80. Both measured, and they are genuinely different rather
# than one padded to the other.
SETTINGS_ACTION_ROW_H = 109
SETTINGS_VALUE_ROW_H = 80
# Two value rows sharing one card (Server over Libraries) are shorter than a
# lone one: the app's two-row card is 153 tall, not 160. There is no divider
# rule between them -- looked for one, the fill is constant across the seam.
SETTINGS_VALUE_ROW_STACKED_H = 76
# Card bottom to next card top for two rows INSIDE one group, as against
# SETTINGS_GROUP_GAP between groups. Defined here with the row heights it
# goes with, since several sections stack rows this way.
SETTINGS_STACK_ROW_GAP = 12
# Card bottom to the next card top. The group's eyebrow label lives inside
# this gap, 25 above the card it introduces. Measured 60/61/61 down the page;
# taking 60 puts our four Account cards within 2px of the app's at the bottom.
SETTINGS_GROUP_GAP = 60
SETTINGS_GROUP_EYEBROW_RISE = 25
SETTINGS_ROW_RADIUS = 18                # 6: "glass value rows (radius ~18)"
# A detail-pane row that DOES something is brighter at rest than one that
# only reports a value -- the app's action cards (Switch Profile, Sign Out)
# measure +19 over the page background and its value cards (Email, Server)
# +9, so roughly 8% white against 4%. That contrast is the only thing
# separating "Sign Out" from "Signed in as" before either is focused, so the
# pair has to move together: SURFACE_REST for the actionable one, PANEL_WASH
# for the read-only one. Ours pushes further apart than the app's 8:4, at the
# user's request -- 4% still read as a button at 3m.
# A focused detail-pane row is accent-TINTED glass with accent text, not the
# solid accent fill 6 describes -- that treatment belongs to the sidebar. The
# shipped app measures 254145 for the fill against 252E30 at rest: the accent
# laid over the resting card at roughly an eighth. It is therefore an alpha
# applied to the LIVE accent, which is per-profile server data and cannot be a
# constant here -- windows/main.py sets it as the `settings_row_wash` property
# via theme.accent_with_alpha(), the same way accent_pill_fill already works.
SETTINGS_ROW_FOCUS_ALPHA = "20"         # 12.5%, measured

# Right rail: eyebrow, then one glass panel holding the QR card and its
# caption. The QR asset is a fixed-size 292 square with the white card and its
# radius-20 corners baked in (tools/gen_qr_assets.py) -- not a 9-patch, so it
# must be drawn at exactly this size (project_kodi_9patch_needs_straight_edges).
# Account page card tops, stacked from SETTINGS_CONTENT_Y. Derived rather
# than typed so a row-height or gap change moves all four together; the app
# measures 406/574/743/883 against these 406/575/744/884.
#
# PROFILE / SERVER / ACCOUNT / SESSION, and the pane has no grouplist, so
# the four have to FIT: 406 + 3 action rows + 1 value row + 3 gaps lands the
# last card's bottom at 993, with 87 to spare. That budget is why SERVER is
# one action row (Switch Server, its server name and library count on the
# summary line) rather than the action row PLUS the two-row value card that
# reported the same two facts before switching existed -- keeping both put
# the bottom at 1205, off the screen with nothing able to scroll to it.

# --- 9.4's fox / accent picker, on the Appearance page ---
# 9.4 asks for a grid of fox tiles, one for each of the 14 accents in 2's
# list. Measured off
# internal-docs/atv-reference/settings-appearance.png: the card runs the full
# detail width with a 26px inset, six columns of 157 on a 173.5 pitch, rows on
# a 175 pitch. Tile width is derived from the column count so the two cannot
# disagree -- the gap is what absorbs the rounding, exactly as the app's does.
SETTINGS_FOX_COLS = 6
SETTINGS_FOX_ROWS = 3                   # 14 tiles over 6 columns
SETTINGS_FOX_CARD_PAD = 26
SETTINGS_FOX_GAP_X = 17
SETTINGS_FOX_GAP_Y = 29
SETTINGS_FOX_TILE_W = (
    (SETTINGS_DETAIL_W_WIDE - 2 * SETTINGS_FOX_CARD_PAD
     - (SETTINGS_FOX_COLS - 1) * SETTINGS_FOX_GAP_X) // SETTINGS_FOX_COLS
)                                       # 157
SETTINGS_FOX_TILE_H = 146
SETTINGS_FOX_CELL_W = SETTINGS_FOX_TILE_W + SETTINGS_FOX_GAP_X
SETTINGS_FOX_CELL_H = SETTINGS_FOX_TILE_H + SETTINGS_FOX_GAP_Y
# Blurb above the tiles ("Pick a fox. It sets your accent ..."), two lines.
SETTINGS_FOX_BLURB_Y = 20
SETTINGS_FOX_BLURB_H = 72
SETTINGS_FOX_GRID_Y = SETTINGS_FOX_BLURB_Y + SETTINGS_FOX_BLURB_H + 6
SETTINGS_FOX_CARD_H = (
    SETTINGS_FOX_GRID_Y + SETTINGS_FOX_ROWS * SETTINGS_FOX_CELL_H
    - SETTINGS_FOX_GAP_Y + SETTINGS_FOX_CARD_PAD
)
SETTINGS_FOX_BLURB_W = SETTINGS_DETAIL_W_WIDE - 2 * SETTINGS_FOX_CARD_PAD
# The "original" star badge on the Tofa Fox tile. Literal teal, and literal on
# purpose: it names ONE tile, so it must not follow the window accent (which
# changes with the pick, and previews mid-move) nor read a per-item property
# in a <textcolor> (Kodi resolves that against the container's FOCUSED item,
# not the item being drawn, so the badge took whichever fox had the cursor).
# Same hex as theme.DEFAULT_ACCENT / settings.xml's <default>, which cannot be
# imported here -- this module has to render outside Kodi.
SETTINGS_FOX_DEFAULT_BADGE = "0xFF2DD4BF"

# --- the scrolling detail pane ---
# Groups are children of a grouplist, so their geometry is RELATIVE to the
# child rather than to the screen. Each child leads with its own eyebrow, in
# a band of this height, so the eyebrow scrolls with the group it labels
# instead of being a separate child (a bare label child would join the
# grouplist's own up/down chain and swallow a keypress).
SETTINGS_GROUP_EYEBROW_BAND = SETTINGS_GROUP_EYEBROW_RISE + 12
# A grouplist has ONE itemgap for all its children, but this pane needs two
# spacings: a big one between sections (FOX / HOME SCREEN / MEDIA CARDS /
# REGION) and a small one between children that are parts of the SAME section
# -- the home-row editor is three children (toggle, list, add-rows) and they
# read as one thing.
#
# So the itemgap is the SMALL one, and every child that BEGINS a section
# carries the difference as its own lead-in. Section boundaries still measure
# SETTINGS_GROUP_GAP; parts of a section sit SETTINGS_GROUPLIST_GAP apart.
SETTINGS_GROUPLIST_GAP = 12
# Every group CARRIES its own trailing gap, and the grouplist's itemgap is 0.
# Same trick as the rows regions' ROW_BLOCK_H (72294b7), for the same reason:
# the region has to run to the screen edge so partly-visible content bleeds
# off it, but the row that comes to rest AT the bottom still needs air under
# it -- otherwise its focus ring lands on the last pixel row. Putting the gap
# in the item gives both; shortening the viewport gives neither.
#
# SPACE_MD, which is ROW_GAP -- the same trailing pad Home and Discover give
# their last row, so the three screens end the same way. Measured on the real
# screens with the last row focused: Home's caption ink stops 29px above the
# edge and Discover's 28px, both of which are this 24px pad plus the ~4px of
# slack the caption BOX carries under its text. A settings row ends in a card
# border rather than text and has no such slack, so matching the token is the
# faithful match; copying the 28 would be copying a text metric.
SETTINGS_GROUP_TRAIL = SPACE_MD
SETTINGS_GROUPLIST_ITEMGAP = 0
# Boundaries between groups must still measure SETTINGS_GROUP_GAP, and that
# budget is now split differently: more of it sits under a group as its pad,
# so less is left as the next group's lead-in.
SETTINGS_SECTION_LEAD = SETTINGS_GROUP_GAP - SETTINGS_GROUP_TRAIL
# Where a section-leading child's first row starts: its lead-in, then the
# band its eyebrow occupies.
SETTINGS_SECTION_BAND = SETTINGS_SECTION_LEAD + SETTINGS_GROUP_EYEBROW_BAND
# Shifted by whatever the pad took OUT of the section lead-in, so growing the
# pad moves the bottom of the region's content and nothing else. Without this
# the first section on every page would ride up by that same amount, which is
# a page-wide change nobody asked for in return for a gap at the bottom.
SETTINGS_GROUPLIST_Y = (SETTINGS_CONTENT_Y - SETTINGS_GROUP_EYEBROW_BAND
                        + (SETTINGS_GROUP_TRAIL - SETTINGS_GROUPLIST_GAP))
# Runs to the screen edge, like every other scrolling region here
# (DISCOVER_ROWS_H, SEARCH_SHELVES_H, DETAIL_SHELF_H, PERSON_GRID_H all end
# at SCREEN_H). This one used to stop 24px short on the reasoning that a card
# flush with the edge reads as clipped -- but a region that stops short reads
# as the content ENDING, which is worse and was the whole point of 72294b7.
# A part-drawn row at the edge is the honest signal that there is more below.
SETTINGS_GROUPLIST_H = SCREEN_H - SETTINGS_GROUPLIST_Y

# Account, matching the app's build 17. The pane SCROLLS now (a grouplist,
# like Appearance), because the app's five sections do not fit a 1080 screen:
# they total 1165 against a 699 viewport. Each child fits on its own, which
# is the rule that matters -- a child taller than the viewport can never be
# scrolled fully into view.
#
# SWITCH is two children, one row each -- NOT one two-item list, which was
# tried first and traps focus. Measured 2026-08-13: a multi-item list inside
# a grouplist CONSUMES Down at its last item (our lists stop rather than
# wrap), so focus never reaches the next child and the page dead-ends on
# Switch Server. A one-item list hands the keypress back and the grouplist
# chains on, which is exactly why Appearance's single-row children work.
# The eyebrow belongs to the first child; the second is the same visual
# group continued, so the gap between them is a stack gap, not a group gap.
SETTINGS_ACCOUNT_SWITCH_ROW_PITCH = SETTINGS_ACTION_ROW_H + SETTINGS_STACK_ROW_GAP
SETTINGS_ACCOUNT_SWITCH_GROUP_H = (
    SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_STACK_ROW_GAP)
SETTINGS_ACCOUNT_SWITCH2_GROUP_H = SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL
SETTINGS_ACCOUNT_SESSION_GROUP_H = (
    SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL)
SETTINGS_ACCOUNT_EMAIL_GROUP_H = (
    SETTINGS_SECTION_BAND + SETTINGS_VALUE_ROW_H + SETTINGS_GROUP_TRAIL)
# SERVER is the app's two-row value card again (Server over Libraries), one
# 152-tall fill with no divider -- see the ORIGINAL note on
# SETTINGS_VALUE_ROW_STACKED_H. It came back when the pane learned to scroll.
SETTINGS_ACCOUNT_SERVER_GROUP_H = (
    SETTINGS_SECTION_BAND + 2 * SETTINGS_VALUE_ROW_STACKED_H
    + SETTINGS_GROUP_TRAIL)
# ACCOUNT, SERVER and CONNECTION share ONE grouplist child. Neither of the
# first two can take focus, and a focusless child joins the chain and eats a
# keypress -- so they ride with the toggle, which can. They keep their own
# group spacing, so the eye still reads three sections.
SETTINGS_ACCOUNT_TAIL_EMAIL_Y = SETTINGS_SECTION_BAND
SETTINGS_ACCOUNT_TAIL_SERVER_Y = (
    SETTINGS_ACCOUNT_TAIL_EMAIL_Y + SETTINGS_VALUE_ROW_H + SETTINGS_GROUP_GAP)
SETTINGS_ACCOUNT_CONNECTION_ROW_Y = (
    SETTINGS_ACCOUNT_TAIL_SERVER_Y + 2 * SETTINGS_VALUE_ROW_STACKED_H
    + SETTINGS_GROUP_GAP)
SETTINGS_ACCOUNT_TAIL_GROUP_H = (
    SETTINGS_ACCOUNT_CONNECTION_ROW_Y + SETTINGS_ACTION_ROW_H
    + SETTINGS_GROUP_TRAIL)
SETTINGS_FOX_BLURB_ABS_Y = SETTINGS_SECTION_BAND + SETTINGS_FOX_BLURB_Y
SETTINGS_FOX_GRID_ABS_Y = SETTINGS_SECTION_BAND + SETTINGS_FOX_GRID_Y
SETTINGS_FOX_GROUP_H = SETTINGS_SECTION_BAND + SETTINGS_FOX_CARD_H + SETTINGS_GROUP_TRAIL
# Media cards: two rows, each its own one-item list. Same in-group spacing
# as any other stacked pair, named separately only for its call sites.
SETTINGS_MEDIACARDS_ROW_GAP = SETTINGS_STACK_ROW_GAP
SETTINGS_MEDIACARDS_SECOND_Y = (
    SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_MEDIACARDS_ROW_GAP
)
SETTINGS_MEDIACARDS_GROUP_H = SETTINGS_MEDIACARDS_SECOND_Y + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL

# Home-screen editor: the spotlight toggle, then the row list.
# The list shows a FIXED number of rows and scrolls internally past that. It
# has to: an account may send up to MAX_HOME_ROWS (9), and a grouplist child
# taller than the viewport strands focus with nothing able to scroll to it
# (project_kodi_grouplist_scroll_limit). Capping the child and letting the
# list scroll itself is that memory's own prescribed fix.
SETTINGS_HOMEROW_H = 64
# The row list is its OWN grouplist child, and sized at runtime to however
# many rows the account actually has (windows/main.py:_settings_size_home_rows).
#
# Its own child on purpose. While the whole HOME SCREEN group was one child,
# the eyebrow, the spotlight toggle and the two "add" rows ate 322 of the 687
# viewport and left room for five rows -- so an eight-row account had three
# hidden behind an internal scroll for no reason but layout. Split out, the
# list gets the whole viewport and every allowed row count fits.
#
# The cap is still real and still load-bearing: a grouplist child TALLER than
# the viewport strands focus, because the list has no overflow of its own to
# scroll and the grouplist thinks its focused child is already at offset 0
# (project_kodi_grouplist_scroll_limit). Past the cap the list keeps its
# internal scroll, which is that memory's own prescribed fallback.
SETTINGS_HOMEROWS_MAX_VISIBLE = SETTINGS_GROUPLIST_H // SETTINGS_HOMEROW_H
# Declared at the MAXIMUM, then shrunk at runtime to the real row count.
# That direction matters: Kodi allocates a list's item slots from the height
# it is declared with at load, so a list declared short and grown later gets
# the layout space but not the extra slots -- measured, it kept drawing five
# rows inside a 512px box. Declared tall and shrunk, every slot exists.
SETTINGS_HOMEROWS_H = SETTINGS_HOMEROWS_MAX_VISIBLE * SETTINGS_HOMEROW_H
# The two "add a row" actions sit under the list, as they do in the app.
SETTINGS_HOMEADD_H = 84
SETTINGS_HOMEADD_SECOND_Y = SETTINGS_HOMEADD_H + 8
SETTINGS_HOMEADD_GROUP_H = SETTINGS_HOMEADD_SECOND_Y + SETTINGS_HOMEADD_H + SETTINGS_GROUP_TRAIL
# The spotlight toggle keeps the eyebrow, since it labels the section.
SETTINGS_HOMESCREEN_GROUP_H = SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL

# Playback & Video and Audio & Subtitles: plain stacks of action-height rows
# under one eyebrow, so their group height is just a row count.
def settings_stack_group_h(rows: int) -> int:
    """Height of a section-leading group: `rows` action-height rows under an
    eyebrow, plus the section lead-in."""
    return (SETTINGS_SECTION_BAND + rows * SETTINGS_ACTION_ROW_H
            + (rows - 1) * SETTINGS_MEDIACARDS_ROW_GAP + SETTINGS_GROUP_TRAIL)


def settings_stack_row_y(index: int) -> int:
    """Y of row `index` inside such a group."""
    return (SETTINGS_SECTION_BAND
            + index * (SETTINGS_ACTION_ROW_H + SETTINGS_MEDIACARDS_ROW_GAP))


# Five segment rows (intro/recap/preview/outro/commercial), as the web and
# desktop apps show. 5*109 + 4*12 + 37 = 630, inside the 687 grouplist
# viewport -- so the whole group is one child that fits, and focus moving
# between its rows needs no scroll (project_kodi_grouplist_scroll_limit).
SETTINGS_SEGMENT_COUNT = 5
SETTINGS_SKIP_GROUP_H = settings_stack_group_h(SETTINGS_SEGMENT_COUNT)
# QUALITY: one segmented row, and the app's FIRST group on this page -- its
# order is QUALITY, NEXT EPISODE, SKIP SEGMENTS, and ours started at the
# second.
SETTINGS_QUALITY_GROUP_H = (
    SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL)
SETTINGS_SKIP_ROW_Y = tuple(settings_stack_row_y(i)
                            for i in range(SETTINGS_SEGMENT_COUNT))
# "Do nothing" is 108px of ink, so these pills are half again the default.
SETTINGS_SEGMENT_PILL_W = 150
# NEXT EPISODE is a SECOND child of the playback grouplist rather than a
# sixth SEGMENTS row: six rows would be 6*109 + 5*12 + 37 = 751 against a 687
# viewport, and a child taller than the viewport cannot be scrolled to
# (project_kodi_grouplist_scroll_limit). Two children each shorter than the
# viewport is exactly the shape that grouplist scrolling does handle.
SETTINGS_NEXTUP_GROUP_H = settings_stack_group_h(1)
#: "Automatically" is 133px of ink against "Do nothing"'s 108, so this row
#: gets its own width -- reusing SETTINGS_SEGMENT_PILL_W would leave it 8px
#: of padding where the segment rows get 21, and read as a different control.
SETTINGS_NEXTUP_PILL_W = 175
# Audio & Subtitles is TWO groups, mirroring the web/desktop app's two cards:
# Audio (primary + secondary language) and Subtitles (primary + secondary +
# the always-show toggle). It was one "LANGUAGE" group with a single language
# per axis, which could neither show nor set the secondary the other clients
# write -- a non-English locale gets [locale, "eng"] from them.
SETTINGS_AUDIO_GROUP_H = settings_stack_group_h(2)
SETTINGS_SUBS_GROUP_H = settings_stack_group_h(3)
SETTINGS_LANG_ROW1_Y = settings_stack_row_y(1)
SETTINGS_LANG_ROW2_Y = settings_stack_row_y(2)

# A read-only explanation card: title line, then three wrapped lines.
SETTINGS_NOTE_CARD_H = 18 + 34 + 4 + 3 * 27 + 18
SETTINGS_PRIVACY_GROUP_H = SETTINGS_SECTION_BAND + SETTINGS_NOTE_CARD_H + SETTINGS_GROUP_TRAIL
# ABOUT is not a plain row stack: it leads with a name block ("tofa for Kodi"
# over the note that this is an unofficial add-on the tofa team still helps
# with -- agreed with tofa 2026-08-03), which shares ONE card with the Version
# row beneath it, exactly as Server shares a card with Libraries. Then the
# Open Source Notices row, which is a real list and keeps its action height.
# Title over summary, on settings_action_row's own measurements (23/34 then
# 58/28) so this block reads as the same kind of thing as every other
# two-line row in Settings. A first pass sized the note at FONT_CAPTION,
# which is semibold 25 against the title's semibold 26 -- near-identical, so
# it read as a second title rather than a note about the first.
SETTINGS_ABOUT_NAME_TITLE_Y = 23
SETTINGS_ABOUT_NAME_TITLE_H = 34
SETTINGS_ABOUT_NAME_SUB_Y = 58
SETTINGS_ABOUT_NAME_SUB_H = 28
# The note runs to two lines, and they are BROKEN BY HAND rather than wrapped.
# A Kodi <label> does not wrap at all, and the <textbox> that would has no say
# in where it breaks: measured against Inter Tight Regular 23 in the 622px the
# card leaves, it splits this sentence 608/163, which reads as a line that
# overflowed rather than one that was set. The hand break is 536/235.
SETTINGS_ABOUT_NAME_SUB_LINES = 2
SETTINGS_ABOUT_NAME_H = (SETTINGS_ABOUT_NAME_SUB_Y
                         + SETTINGS_ABOUT_NAME_SUB_LINES * SETTINGS_ABOUT_NAME_SUB_H
                         + 10)
SETTINGS_ABOUT_CARD_H = SETTINGS_ABOUT_NAME_H + SETTINGS_VALUE_ROW_STACKED_H
SETTINGS_ABOUT_VERSION_Y = SETTINGS_SECTION_BAND + SETTINGS_ABOUT_NAME_H
SETTINGS_ABOUT_ROW1_Y = (SETTINGS_SECTION_BAND + SETTINGS_ABOUT_CARD_H
                         + SETTINGS_MEDIACARDS_ROW_GAP)
SETTINGS_ABOUT_GROUP_H = SETTINGS_ABOUT_ROW1_Y + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL
SETTINGS_DEVICE_GROUP_H = settings_stack_group_h(2)
SETTINGS_DEVICE_ROW1_Y = settings_stack_row_y(1)

# The artwork cache: its size budget, then the button that empties it. A
# SECOND group under THIS DEVICE rather than two more rows in the first,
# because the grouplist scrolls per CHILD -- one oversized child would have
# to scroll internally, which it cannot (project_kodi_grouplist_scroll_limit).
SETTINGS_ARTCACHE_GROUP_H = settings_stack_group_h(2)
SETTINGS_ARTCACHE_ROW1_Y = settings_stack_row_y(1)

# Region: editable, but the add-on never consumes the value. `region` drives
# release dates for titles not in the library, which is a server-side
# concern, so setting it here is for tofa's other surfaces rather than for
# anything this client draws. The country list is hardcoded because no
# endpoint enumerates the regions the server accepts -- unlike LANGUAGES,
# which now comes from /media/facets. Filed under the server-API-gaps issue.
# Its row is an ACTION-height list (it opens a picker), not a value row --
# they were 29px apart and the region card was clipped by exactly that.
SETTINGS_REGION_GROUP_H = SETTINGS_SECTION_BAND + SETTINGS_ACTION_ROW_H + SETTINGS_GROUP_TRAIL
# The panel's own box. Width runs one GAP past the last column so Kodi has
# somewhere to put the trailing gap of the rightmost cell (a cell is
# tile+gap); height is whole rows, since a panel scrolls by whole rows and a
# fractional viewport can never come to rest against its last one.
SETTINGS_FOX_GRID_W = SETTINGS_FOX_COLS * SETTINGS_FOX_CELL_W
SETTINGS_FOX_GRID_H = SETTINGS_FOX_ROWS * SETTINGS_FOX_CELL_H

SETTINGS_RAIL_PANEL_H = 430
SETTINGS_RAIL_RADIUS = 24
SETTINGS_QR = 292
SETTINGS_QR_Y = 431                     # 25 below the panel top
SETTINGS_QR_CAPTION_Y = 741             # ink 753-808, three centred lines

# ---------------------------------------------------------------- surfaces --
# The glass ladder. Was eight ad-hoc white alphas (0x0F/0x14/0x1E/0x1F/0x33/
# 0x40/0x66); 0x1E and 0x1F were within one step of each other and merge.
# 2's own ladder puts a panel wash at white 2-4% behind card and panel fills,
# the band it lists BELOW hairline (6-8%) -- for a surface that only displays,
# against SURFACE_REST's 8% for one that can be activated. Taken at the bottom
# of the band so the difference survives a 3m viewing distance: at 4% a
# read-only row still read as a button next to a real one.
#
# Not settings-specific despite arriving with that screen; any future
# read-only card belongs on this rather than on a fainter shade of glass.
PANEL_WASH = "0x06FFFFFF"
# 5's focus rim is "2dp accent-colored", which assumes the focused thing is
# glass. On a surface already filled with the accent -- the Settings sidebar's
# active row -- an accent rim is invisible. 9.2 covers that case directly for
# the profile picker, where the ring around the active profile is 3px of
# white 90%, deliberately neutral instead of accent. So the rim goes neutral
# wherever the fill is the accent itself.
FOCUS_RIM_NEUTRAL = "0xE6FFFFFF"
SURFACE_FAINT = "0x0FFFFFFF"    # sidebar row base
SURFACE_REST = "0x14FFFFFF"     # default glass fill
SURFACE_RAISED = "0x1FFFFFFF"   # hover/active glass, panel outlines
# The unfilled groove a control slides/segments within: the player OSD's
# progress track and Search's abc/123 switcher. Brighter than SURFACE_RAISED
# because it reads as recessed rather than raised. 0x29 measured off the real
# Apple TV app's switcher (JetKVM capture calibrated against known canvas and
# white-text anchors; per-channel 0x24/0x2B/0x2F) -- and independently already
# the player OSD's own hand-picked track value.
SURFACE_TRACK = "0x29FFFFFF"
# The unfilled part of a CARD's progress bar, which is a different thing from
# the groove above and much quieter. 6 says white 10%; a live JetKVM capture
# of the real Apple TV app's Continue Watching row solves to 7-10% across
# three cards (white-over-art, sampled against the poster art immediately
# above each bar). SURFACE_TRACK's 0x29 was visibly too pale here -- it read
# as a grey band laid across the bottom of the poster rather than as the
# unfilled remainder of a bar.
CARD_PROGRESS_TRACK = "0x1AFFFFFF"
BORDER_SOFT = "0x33FFFFFF"      # badge outlines on art
BORDER = "0x40FFFFFF"           # rating badge outline, dividers on art
DIVIDER = "0x66FFFFFF"          # hairlines on flat ground

CANVAS = "0xFF030B10"           # page background
SCRIM_TOP = "0xC8030B10"        # nav-bar scrim
CANVAS_CHIP = "0xB3030B10"      # canvas at 70%, for a chip sitting on artwork
                                # (the watchlist badge) rather than on a page
# Fill for FLOATING chrome (dialogs, overlays, menus) on a platform with no
# real blur. 4 names ours specifically -- Kodi is its example of a platform
# that cannot blur, and its substitute is a dark tint somewhere around
# 85-92% opacity plus a hairline, which it judges close enough at 3m -- and
# 13 repeats it as the unconditional Kodi-class substitution. 90% canvas,
# mid-band.
#
# NOT SURFACE_RAISED: that is the white 12% wash for glass sitting ON a
# blurred backdrop. Used without the blur it is simply a see-through panel,
# which is exactly how the card-options dialog first shipped -- the synopsis
# behind it read straight through the rows.
SURFACE_FLOATING = "0xE6030B10"
# Hairline for that same floating chrome. 7.2 names white 16% explicitly;
# 4's band for floating chrome is 8-16%, so this is its top edge, where
# SURFACE_RAISED (12%) sat near the bottom.
#
# Numerically identical to SURFACE_TRACK today, deliberately kept separate:
# one is a hairline on a dialog, the other is the groove a control slides
# within, and they have no reason to move together. Same convention as
# ON_LIGHT_TEXT above.
BORDER_FLOATING = "0x29FFFFFF"
BADGE_SCRIM = "0x99000000"      # dark chip behind text on artwork
# 7.1's unaired capsule specifically: "black 48%", lighter than BADGE_SCRIM's
# 60% because it sits under accent text rather than white, and the accent
# carries enough contrast of its own that a heavier plate would read as a
# solid tag stuck on the art.
BADGE_SCRIM_SOFT = "0x7A000000"
# The in-cinemas clapperboard glyph. Sampled off the real app's card chip
# (median RGB 201,168,57); the only non-accent hue in the card furniture.
CINEMA_AMBER = "0xFFC9A839"
#: The same amber at ~70%, for the IN CINEMAS pill's outline. Measured off
#: atv-reference/detail-not-in-library.png, whose ring reads dimmer than its
#: own text rather than being a second colour.
CINEMA_AMBER_SOFT = "0xB3C9A839"

# Text on a fixed light fill -- the focused Search keyboard key, which is
# always white. NOT the same role as Window.Property(on_accent_color): that
# one is computed per accent by theme.py:on_accent_text() and flips to white
# on dark accents, which would be invisible here. Same value today, different
# reasons to change.
ON_LIGHT_TEXT = "0xFF04211E"
# Opaque fill where content is absent: empty posters, missing cast photos,
# Search's not-yet-searched results pane. Replaces what used to be the
# `TofaSurface` constant in a skin-level Includes.xml -- deleted, because
# Kodi only reads a skin's includes when that skin is ACTIVE, and ours
# never is (see project_windowxml_no_includes).
#: Also the tile that shows through a poster/backdrop card when the title has
#: no artwork at all -- which is what the whole "Videos" library looks like
#: (2,773 items, every one of them poster_path: null). Neither tofa app draws
#: a designed placeholder there: an artwork-less item is simply this flat
#: tinted card, no icon and no wordmark, with the title below it as usual.
#:
#: Sampled from the Android TV app's own Videos grid, which is a deliberate
#: exception to "Apple TV is the only design source"
#: (feedback_apple_tv_source_of_truth): none of the 50 Apple TV reference
#: captures happens to contain an artwork-less item, and the two apps agree
#: everywhere else that has been compared. If an Apple TV capture ever
#: disagrees, it wins and this is a one-line change.
#:
#: Was 0xFF10171C, which is the same red and green but markedly less blue
#: (B 28 against 43) -- close enough to look deliberate and still be wrong.
SURFACE_PLACEHOLDER = "0xFF11182B"

# ------------------------------------------------------------------- type --
# Roles, not sizes. Nothing outside this module should name a tofa_font_*
# directly, and nothing should ever name a Kodi built-in (font13/font45/...):
# those resolve against whatever host skin is active and render differently
# per skin.
FONT_HERO = "tofa_font_hero"                # hero title
FONT_HEADING = "tofa_font_heading"          # full-screen headings (sign-in)
FONT_DIALOG_TITLE = "tofa_font_dialog_title"  # 7.2 card-options title (34/Bold)
FONT_SECTION_TITLE = "tofa_font_section_title"  # row/section headers
FONT_ROW_TITLE = "tofa_font_row_title"      # nav tabs, Browse pills
FONT_BUTTON = "tofa_font_button"            # CTA pills, Discover tab pills
FONT_LINK = "tofa_font_link"                # pairing URL (mono)
FONT_CODE = "tofa_font_code"                # pairing code (mono, oversized)
FONT_POSTER_TITLE = "tofa_font_poster_title"
FONT_BODY = "tofa_font_body"
FONT_METADATA = "tofa_font_metadata"
#: Settings' identity card, first line; see fontinstall.FONTS.
FONT_ACCOUNT = "tofa_font_account"
FONT_CAPTION = "tofa_font_caption"
FONT_MICRO = "tofa_font_micro"              # badge numerals, captions
FONT_EYEBROW = "tofa_font_eyebrow"
FONT_RESULTS_CAPTION = "tofa_font_results_caption"
FONT_TOP_RESULT_TITLE = "tofa_font_top_result_title"
FONT_TOP_RESULT_EYEBROW = "tofa_font_top_result_eyebrow"
FONT_SIDEBAR = "tofa_font_sidebar_label"
FONT_ICON_19 = "tofa_font_icons_19"
FONT_ICON_24 = "tofa_font_icons_24"
FONT_ICON_26 = "tofa_font_icons_26"
FONT_ICON_29 = "tofa_font_icons_29"
FONT_ICON_36 = "tofa_font_icons_36"
FONT_ICON_56 = "tofa_font_icons_56"
FONT_ICON_64 = "tofa_font_icons_64"
FONT_ICON_80 = "tofa_font_icons_80"

# Text tiers live in windows/theme.py (they're set as Window.Properties at
# runtime because they don't vary by screen). Reference them in XML as
# $INFO[Window.Property(text_primary)] etc, never as a literal.


# ---------------------------------------------------- episode grid (7.1) --
# Cell pitch, and the grid viewport built from it. Both the fragment that
# draws a cell and the template that sizes the panel read these, because
# they used to be typed separately (350/320 in each) and the panel's height
# was a third number again.
#
# 284 is the real Apple TV app's measured row pitch, and it is 36 less than
# the 320 we had: a cell's content ends 260 in (10 pad + 186 still + 12 +
# caption + title), so 320 left 60px of dead air under every row and only
# 2.5 rows fitted the viewport. At 284 the gap is 24 and THREE rows fit.
#
# The viewport is an exact multiple of the pitch on purpose. Kodi scrolls a
# panel by whole rows, so a viewport that is 2.5 rows tall can never come to
# rest against the last one -- which is what left ~200px of empty grid below
# the final row of a 39-episode season.
EPISODE_CELL_W = 350
EPISODE_CELL_H = 284
EPISODE_GRID_ROWS = 3
EPISODE_GRID_W = 1460
EPISODE_GRID_H = EPISODE_CELL_H * EPISODE_GRID_ROWS


# ------------------------------------------------- startup splash (cold) --
# Every number here is measured off a genuine cold start of the Android TV
# app, recorded over ADB at 1920x1080 (tools/gen_splash_assets.py carries the
# capture method). The mark and the wordmark are each uncovered by their own
# left-to-right wipe -- the art does not move -- and the wordmark's wipe is a
# SECOND, later one over roughly the same x range, which is why the two
# cannot share a single sweeping edge.
SPLASH_MARK_W, SPLASH_MARK_H = 213, 256
SPLASH_WORD_W, SPLASH_WORD_H = 173, 85
#: Ink positions, not optical centres: measured x/y of the artwork itself.
#: The wordmark sits at 871 rather than a tidy 873 (= centred on 960) because
#: that is where the app puts it.
SPLASH_MARK_X, SPLASH_MARK_Y = 854, 326
SPLASH_WORD_X, SPLASH_WORD_Y = 871, 649

#: Strip counts, and the width each was cut at. Kept in step with
#: tools/gen_splash_assets.py by check_xml.py, which fails on a strip the
#: skin names but media/ does not have.
SPLASH_STRIP_W = 16
SPLASH_MARK_STRIPS = 14
SPLASH_WORD_STRIPS = 11

#: Wipe timing, milliseconds from window open.
#:
#: RE-MEASURED 2026-08-13 off internal-docs/androidtv-reference/
#: splash-cold-start-amber-1.mp4, a 59fps capture of the real app, and the
#: numbers moved a long way. Relative to the mark's first ink:
#:
#:     mark wipe                  424ms   (was 1280 here)
#:     wordmark starts            ~170ms after the mark
#:     wordmark wipe              ~460ms
#:     both settled by            ~1070ms
#:
#: The old 1280 came from tracking the RIGHTMOST VISIBLE INK, which this
#: file's own docstring warned about and which over-measures by a factor of
#: three: the mark's right end is the thin tip of the play triangle, so the
#: last few columns hold almost no ink and take an age to cross any fixed
#: threshold however fast the edge is really moving. Measuring COVERAGE
#: instead -- per column, what fraction of that column's settled ink has
#: arrived -- makes the tip weigh the same as the solid left bar.
SPLASH_MARK_DELAY = 120
SPLASH_MARK_WIPE = 430
#: 120 + the measured 170ms lead, not the 840 that followed from the old
#: over-long mark wipe.
SPLASH_WORD_DELAY = 290
SPLASH_WORD_WIPE = 460
#: How long one strip takes to reach full opacity. Longer than the gap
#: between strips on purpose: overlapping fades are what turn a row of
#: blocks into one soft moving edge.
SPLASH_MARK_FADE = 180
#: Shape of the mark's wipe, as the exponent in `1 - (1 - t)**SPLASH_EASE`
#: applied to each strip's DELAY (see splash_strip_delay).
#:
#: ABOVE 1 the reveal starts slow and rushes the end; BELOW 1 it starts quick
#: and eases into the finish. It was 1.8 -- the first shape -- and the app
#: does the opposite: measured on the 59fps capture, 61% of the mark is
#: uncovered by the halfway point, where 1.8 had only reached 32%.
#:
#: 0.74 is not a taste call, it is that measurement solved for the exponent:
#: 1 - (1 - 0.61)**E = 0.5  =>  E = ln(0.5)/ln(0.39) = 0.736.
SPLASH_EASE = 0.74
SPLASH_WORD_FADE = 120

#: The glow is a gradient, so it is NOT 2x art; it is drawn at screen size and
#: Kodi's scaling of a smooth radial costs nothing.
SPLASH_GLOW_W, SPLASH_GLOW_H = 1100, 1100
SPLASH_BG = "FF07090A"

#: The window properties that dress the splash in the LAST USED PROFILE's fox.
#:
#: Both are written by windows/splash.py before the window is shown. The fox is
#: a slug (`amber`), one of the 14 in theme.PRESETS, and picks a strip set;
#: the glow is a full 0xAARRGGBB, because splash-glow.png is white and
#: colordiffuse can take it to ANY hex -- including a custom accent that has no
#: fox of its own (the web UI can set one; the 14 foxes cannot express it, so
#: the mark snaps to the nearest and only the glow is exact).
SPLASH_FOX_PROPERTY = "splash_fox"
SPLASH_GLOW_PROPERTY = "splash_glow"
#: What the splash wears when nothing has been remembered yet: first run,
#: signed out, or the profile picker not yet answered even once. The fixed
#: brand teal, matching windows/profile_select.py's own reasoning that a
#: pre-profile surface must not borrow whoever was here last.
SPLASH_FOX_DEFAULT = "tofa"


def splash_strip_delay(index: int, count: int, start: int, wipe: int,
                       ease: bool) -> int:
    """When strip `index` starts fading in.

    The reveal is QUICK OFF THE MARK AND EASES INTO THE FINISH, because that
    is what the real app does -- 61% of the mark uncovered by the halfway
    point (SPLASH_EASE carries the measurement and the arithmetic).

    This used to be the other way round, and the history is worth keeping
    because all of it was tuning by eye against a number that was wrong. The
    exponent went 2 -> smoothstep -> 1.8 chasing a tail that "read as a snap",
    when the tail being chased was an artefact: the wipe was set to 1280ms
    from a rightmost-visible-ink measurement, roughly three times the real
    424ms, so every shape tried had to distribute a third of a second of
    padding somewhere and none of them could look right.

    So: do not tune this by eye against the recording's tail. Measure
    COVERAGE per column against the settled frame -- the play triangle's tip
    holds almost no ink and crawls across any fixed brightness threshold
    however fast the edge is moving.

    The wordmark's wipe stays linear: at 460ms across 11 strips the shape has
    no room to read, and nothing in the capture suggests the app eases it."""
    if count <= 1:
        return start
    t = index / float(count - 1)
    if ease:
        t = 1.0 - (1.0 - t) ** SPLASH_EASE
    return int(round(start + wipe * t))


def row_bleed_width(row_left: int) -> int:
    """How wide a poster row's list must be to bleed off the right edge.

    Reaching x=1920 is not enough. A cell is CELL_W wide with the poster
    inset by HPAD either side, so when a row is scrolled to its END Kodi
    aligns the last CELL's right edge to the viewport's, leaving that cell's
    trailing HPAD as a strip of empty background between the final poster
    and the screen edge. Running the list one HPAD past the screen puts that
    strip off-screen instead, so the last poster ends exactly on the edge.

    Widening costs nothing elsewhere: Kodi does not clamp a horizontal
    list's scroll to its viewport's far edge, so a focused card does not
    move (measured, 25-item row, focused last card at 1813 either way)."""
    return SCREEN_W - (row_left + ROW_LIST_X) + HPAD


def template_kwargs() -> dict[str, object]:
    """Every token a .tpl file may interpolate as `{TOKEN_NAME}`.

    Templates have no constant mechanism of their own, so this is the only way
    they can share a value with the fragments. Add here rather than retyping a
    number into the XML."""
    return {
        name: value
        for name, value in globals().items()
        if name.isupper() and not name.startswith("_")
    }
