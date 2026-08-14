"""Codepoints for the subset of Lucide's prebuilt icon font
(resources/skins/Main/fonts/lucide-icons.ttf, registered as
tofa_font_icons_<size> by fontinstall.py) actually wired into the UI.

Source of truth for the full 2027-icon map is
tools/lucide_font_src/codepoints.json (dev reference only, not shipped) --
copy a new icon's codepoint from there when wiring one up, don't guess.

Used as `&#x{GLYPH:04X};` inside a `<label>` control's own `<label>` tag
(Kodi skin XML wants an ASCII numeric character reference, never a raw
pasted multi-byte glyph). A `<label>` control showing a glyph needs
`<width>`/`<height>` >= the font's own point size, or Kodi renders a
degenerate solid dot regardless of the real glyph shape.

Whenever a constant here is added, removed, or reassigned, run
`python3 tools/gen_icon_reference.py` to refresh tools/icon_reference.html
-- it cross-checks its own WIRED_GROUPS listing against this module and
fails loudly on any mismatch.
"""

BOOKMARK = 0xE060
# Watchlist REMOVE. 11's table pairs `bookmark` with `bookmark.slash`, and
# Lucide's "-off" suffix is its own slashed-through variant (same pattern as
# eye-off / bell-off), so bookmark-off is the faithful match -- not
# bookmark-x or bookmark-minus, which are different marks.
#
# Watchlist is deliberately NOT plus/check: 11 reserves `plus` for Request
# and for the not-in-library badge, both of which appear on the same poster
# card as a watchlist affordance. See project_watchlist_glyph.
BOOKMARK_OFF = 0xE6DF
ROTATE_CCW_CLOCK = 0xE1F5
LAYERS = 0xE529
# The two empty-state marks on Detail page 2, both read off the real Apple TV
# app on a title with neither (Besenbinden, 2026-08-01): `users` for Cast &
# Crew, and for More Like This a box under two thin rules, which is
# gallery-vertical-end rather than the `layers` we had approximated it with.
USERS = 0xE1A4
# 9.7's error flavour asks for a "connectivity/warning glyph".
TRIANGLE_ALERT = 0xE193
GALLERY_VERTICAL_END = 0xE4D2
SHUFFLE = 0xE15E
CLAPPERBOARD = 0xE29B
TV = 0xE195
VIDEO = 0xE1A5
HOUSE = 0xE0F5
LAYOUT_GRID = 0xE0FF
SPARKLES = 0xE412
SEARCH = 0xE151
SETTINGS = 0xE154
# The Settings sidebar's own six section marks. Five of them mirror what the
# real Apple TV app shows against the same rows (person / play / speech-bubble
# / palette / raised hand); TV is ours, for the Kodi-only "This Device" page
# the app has no equivalent of. USER_ROUND, PLAY, CAPTIONS and TV were already
# wired for other screens and are reused verbatim rather than re-picked.
PALETTE = 0xE1DD
HAND = 0xE1D7
# 9.4 gives the default teal a small badge calling it the original -- the fox
# picker's badge on Tofa Fox. A star, not a check: a check would read as
# "this one is selected", which is a different state the tile already shows
# with its own coloured ring.
STAR = 0xE176
SLIDERS_HORIZONTAL = 0xE29A
# Browse's Filter pill. NOT sliders-horizontal, which this used to be and
# which Detail's Options pill and the player's own panels still use -- one
# mark meaning two different things is how "Options" and "Filter" started
# looking like the same control.
#
# list-filter is also what the real app draws there, read off the Android
# 0.1.11 toolbar at 3x (internal-docs/androidtv-reference/browse-toolbar.png):
# three PLAIN horizontal lines of decreasing width for Filter, against the
# knobbed sliders mark it puts on Quality. So this is the faithful glyph as
# well as the unambiguous one. Verified present in the shipped subset.
LIST_FILTER = 0xE460
CHEVRON_DOWN = 0xE06D
# The "this row opens a list of choices" mark, on every control that leads to
# a picker: Browse's four buttons, Detail's Options and Edition pills, and the
# section headers inside the pre-play options panel. A single chevron-down was
# doing that job and reads as a DIRECTION -- which is what it still means in
# the one place it stayed, the "scroll down for page 2" hint under Detail's
# tab row. The two-way pair says "cycle through values" instead.
CHEVRONS_UP_DOWN = 0xE211
# Sign-in dialog. The countdown line and the expired state's amber mark are
# the same clock at 18px and 80px; the retry pill's circular arrow is
# refresh-cw, whose two arrowheads read better at 20px than rotate-cw's one.
CLOCK = 0xE087
REFRESH_CW = 0xE145
# Card options rows (7.2). 11's table names these as SF `chevron.right`,
# `minus.circle` and `xmark.circle`; Lucide's equivalents are chevron-right,
# circle-minus and circle-x.
CHEVRON_RIGHT = 0xE06F
# Browse's "back to the collection list" pill: a DIRECTION, like
# CHEVRON_DOWN's scroll hint, not a dropdown affordance.
CHEVRON_LEFT = 0xE06E
MINUS_CIRCLE = 0xE07E
CIRCLE_X = 0xE084
CHECK = 0xE06C
ARROW_UP = 0xE04A
ARROW_DOWN = 0xE042
TAG = 0xE17F
LOCK = 0xE10B
DELETE = 0xE0AE
USER_ROUND = 0xE468
FILM = 0xE0D0
GLOBE = 0xE0E8
PLAY = 0xE13C
# Exit-confirmation rows (MainWindow's Back-at-top-level dialog). Both
# verified present in the shipped subset -- the ttf carries 1796 of Lucide's
# 2027 icons, so a codepoint from codepoints.json is not automatically there.
LOG_OUT = 0xE10E
MINIMIZE = 0xE11A
# Settings > Account > Switch Server. Lucide's `server` -- the stacked rack
# unit, not `hard-drive` (one enclosure, which is a disk) and not `globe`
# (which is what the cloud account is, and the row above it already means).
SERVER = 0xE153

INFO = 0xE0F9
# Card corner chips. PLUS was an ASCII "+" rendered in a TEXT font, which is
# why it never looked centred in its circle: a typographic plus sits on the
# math axis, not in the middle of the em box. CHECK and CLAPPERBOARD were
# already defined above for other surfaces; the chips reuse them.
PLUS = 0xE13D

# ------------------------------------------------------ player transport --
# 11's table names these as SF play.fill / pause.fill / gobackward.10 /
# goforward.10 / captions.bubble / speaker.wave.2.fill / slider.horizontal.3
# / waveform.path.ecg. PLAY and SLIDERS_HORIZONTAL are already defined above
# and the transport reuses them.
#
# Lucide has no numbered skip glyph, so the +/-10s buttons are rotate-ccw /
# rotate-cw with a separate "10" label centred inside the arc -- which is
# structurally what SF's gobackward.10 is too, and what the real Apple TV
# app renders. All six verified present in the shipped subset.
PAUSE = 0xE12E
ROTATE_CCW = 0xE148
ROTATE_CW = 0xE149
CAPTIONS = 0xE3A4
VOLUME_2 = 0xE1AB
# The stats/diagnostics overlay toggle. Lucide's `activity` is the same ECG
# trace SF calls waveform.path.ecg -- 11 names MonitorHeart as Material's
# nearest, which is a heart in a box; activity is the closer mark.
ACTIVITY = 0xE038
# The Adjust panel's own mark. It WAS `timer`, which was honest while the
# panel held only audio sync and subtitle sync -- both of which shift
# something in time. Adding the 3D mode row broke that, exactly as the note
# there predicted, so the mark now says "adjust", not "time".
#
# NOT sliders of any kind: SLIDERS_HORIZONTAL is the Quality button two slots
# away, and sliders-vertical / settings-2 are the same mark rotated, which is
# the mistake LIST_FILTER exists to undo. NOT a gauge either -- that reads as
# measurement and would collide with ACTIVITY on the Stats button beside it.
#
# A wrench is a simple silhouette at 26px (unlike monitor-cog, whose gear
# mushes) and says "something here is off and can be corrected", which is
# what every row in the panel does. Verified present in the shipped subset.
WRENCH = 0xE1B1

# 8.1's transport capsule on a TV EPISODE. The reference app swaps the
# -10s/+10s pair for previous/next EPISODE there (see
# internal-docs/atv-reference/player-chrome-episode.png) -- and can afford
# to, because 10.4 already gives left/right on the bare surface the seek.
SKIP_BACK = 0xE15F
SKIP_FORWARD = 0xE160
# The episode drawer's own button, slot 2 of the utility capsule.
LIST = 0xE106
# 8.10's "this one is playing" badge on an episode row's still. circle-play
# rather than square-play: the reference draws a filled disc.
CIRCLE_PLAY = 0xE080

# 8.5's skip pill. chevrons-right rather than skip-forward: skip-forward is
# already the transport's "next episode", and these are different actions.
CHEVRONS_RIGHT = 0xE073
