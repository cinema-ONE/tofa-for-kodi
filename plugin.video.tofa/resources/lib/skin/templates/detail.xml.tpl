<?xml version="1.0" encoding="UTF-8"?>
<!--
  Media detail screen TEMPLATE, rendered to script-tofa-detail.xml by
  resources/lib/skin/screens.py:render_detail() (see resources/lib/skin/
  for the plain-Python fragment mechanism this project uses instead of
  Kodi's native <include>, which doesn't work for Python WindowXML).
  Consumed by resources/lib/windows/detail.py.

  This is a *pushed* screen: no top nav cluster. Back closes it (handled
  by ControlledWindow.onAction). Two vertically-stacked pages live in one
  window and share the same full-bleed backdrop:
    - Page 1 (hero): title-logo/text, meta, ratings, format badges,
      synopsis, action pills (Play/Rewatch/Options/Watchlist).
    - Page 2 (tabs): heavy dark scrim over the same backdrop, with the
      Cast & Crew / About / More Like This pill tabs, plus an Episodes tab
      for TV.
  Pressing Down from the action row (handled in detail.py onAction) sets
  Window.Property(detailpage) to "page2" and explicitly focuses a page-2
  control. The two page groups overlay at y0 and toggle visibility on
  that property via String.IsEqual (StringCompare was removed in Kodi
  v19+).
-->
<window>
    <defaultcontrol always="true">5210</defaultcontrol>
    <backgroundcolor>0xff030b10</backgroundcolor>
    <coordinates>
        <system>0</system>
    </coordinates>
    <controls>
        <!-- What shows when the title has NO backdrop at all, which is every
             item in a library like "Videos". Without it control 9000 draws
             nothing and the window's flat backgroundcolor shows through, so
             the page reads as broken rather than as sparse. The tofa apps put
             a soft wash there; this is theirs, measured
             (tools/gen_backdrop_fallback.py).

             Drawn BEFORE 9000 so real artwork covers it, and gated on the
             property rather than swapped in from Python: 9000's image is set
             by setImage(), and a control whose texture is "-" cannot be asked
             whether it drew anything. -->
        <control type="image">
            <visible>String.IsEmpty(Window.Property(hero_backdrop))</visible>
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <aspectratio>stretch</aspectratio>
            <texture>detail-no-backdrop.png</texture>
        </control>

        <!-- Shared full-bleed backdrop, behind both pages. Same crossfade as
             Home's hero (7.10.2); this is the same billboard and the same
             control id, and the two disagreeing would be visible the moment
             you opened a title from a row. -->
        <control type="image" id="9000">
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <aspectratio>scale</aspectratio>
            <fadetime>{HERO_CROSSFADE_MS}</fadetime>
            <texture>-</texture>
        </control>

        <!-- The pager: page 1 and page 2 overlay at y0; each group's visibility
             is bound to Window.Property(detailpage). -->
        <control type="group" id="5000">

            <!-- ============================ PAGE 1 ============================ -->
            <control type="group" id="5100">
                <posx>0</posx>
                <posy>0</posy>
                <visible>!String.IsEqual(Window.Property(detailpage),page2)</visible>
                <animation effect="fade" start="100" end="0" time="160" condition="String.IsEqual(Window.Property(detailpage),page2)">Conditional</animation>

                <!-- Left-weighted + bottom scrims over the backdrop. -->
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>1500</width>
                    <height>{SCREEN_H}</height>
                    <colordiffuse>0xF2030B10</colordiffuse>
                    <texture>fade-left.png</texture>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>460</posy>
                    <width>{SCREEN_W}</width>
                    <height>620</height>
                    <colordiffuse>0xF0030B10</colordiffuse>
                    <texture>fade-bottom.png</texture>
                </control>

                <!-- Hero info block, bottom-left stack. Hidden outright
                     when the page failed to load: with no payload there is
                     nothing in this stack but an empty action row, which
                     reads as a broken screen rather than a failed one. -->
                <control type="group">
                    <posx>100</posx>
                    <posy>500</posy>
                    <visible>String.IsEmpty(Window.Property(detail_state))</visible>

                    <!-- Title-logo artwork when present, text title
                         fallback. Whole upper stack (logo through
                         synopsis) shifted up to free room for a taller
                         3-line synopsis below without pushing the
                         action-pill row down. -->
                    <!-- Vertical stack aligned to the reference app, in this
                         group's own coordinates (it sits at y=500): title
                         logo BOTTOM at 0, meta ink 55, ratings ink 108,
                         badges 158, "Plays as" slot 214, synopsis 266. The
                         logo is bottom-aligned, so its posy is
                         (0 - height). -->
                    <control type="image" id="5105">
                        <posx>0</posx>
                        <posy>-215</posy>
                        <width>620</width>
                        <height>180</height>
                        <aspectratio align="left" aligny="bottom">keep</aspectratio>
                        <texture>$INFO[Window.Property(hero_logo)]</texture>
                        <visible>!String.IsEmpty(Window.Property(hero_logo))</visible>
                    </control>
                    <!-- Same role and treatment as Home's id 4001, and for
                         the same reason: this renders only when the title
                         has no logo art. See that control for the full
                         measurement note.

                         The width was 1720 (1920 - 2 * 100) so a long
                         title would ellipsise "far later" - the German
                         case that drove it was "00 Schneider - Jagd auf
                         Nihil Baxter", clipped at "Nihil". Wrapping
                         answers that better than a wide single line does,
                         and it is what the app does: measured on a live
                         capture, Detail lays this title over two lines
                         with its longer line at 813px. 16's "truncate or
                         grow gracefully" for +35% German growth is now
                         served by the second line rather than by running
                         to the far margin.

                         Detail's own hero is 63 to Home's 59 on the app
                         (two agreeing metrics), but both take the single
                         61 - one size for the two content heroes is a
                         deliberate call, not an oversight.

                         BOTTOM-ANCHORED exactly like Home's id 4001, by
                         the same slide-when-one-line trick and for the same
                         reason - Kodi cannot bottom-align a label at all.
                         Read 4001's note for the source detail. -158 + 170
                         = 12 = id 5102's posy, so the box's bottom edge is
                         the meta line's top edge. -->
                    <control type="label" id="5101">
                        <posy>{HERO_TITLE_POSY_DETAIL}</posy>
                        <width>{HERO_TITLE_COLUMN}</width>
                        <height>170</height>
                        <wrapmultiline>true</wrapmultiline>
                        <font>tofa_font_hero_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(hero_title_display)]</label>
                        <visible>String.IsEmpty(Window.Property(hero_logo))</visible>
                        <animation effect="slide" start="0,0" end="0,{HERO_TITLE_LINE}" time="0"
                                   condition="String.IsEqual(Window.Property(hero_title_lines),1)">Conditional</animation>
                    </control>

                    <control type="label" id="5102">
                        <posy>12</posy>
                        <!-- 1264, not 1200: this line leads with the EPISODE
                             title on a series (detail.py:_apply_episode_meta_line),
                             which lengthens it well past what the show's own
                             year/rating/runtime/genres need. Measured in the
                             real font (inter_tight_semibold 26, via
                             tools/gen_text_metrics.py's 100x recipe): the
                             show-only line is 621px, a typical episode line
                             781px, and a long episode title 1075px. 1264 is
                             the synopsis textbox's width, the hero text
                             column's established right edge, rather than an
                             invented number. A genuinely extreme title still
                             truncates at the TAIL, which drops a genre and
                             keeps the episode title. -->
                        <width>1264</width>
                        <height>26</height>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(hero_meta_line)]</label>
                    </control>
                    <control type="label" id="5103">
                        <posy>64</posy>
                        <width>1200</width>
                        <height>24</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(hero_ratings_line)]</label>
                    </control>

                    <!-- Format badges row (4K / HDR10 / DTS-HD MA 5.1, ...).
                         3 positional slots filled left-to-right by
                         detail.py, so a slot never leaves a gap when only
                         2 of 3 badge kinds apply.

                         The posx/width here are placeholders. Kodi cannot
                         size a control from its label text, but
                         Control.setWidth()/setPosition() exist, so
                         detail.py:_layout_format_badges() measures each
                         label with resources/lib/textmetrics.py and lays
                         the row out at runtime. That is what makes the
                         badges hug their text like the real app's, instead
                         of sitting in fixed 150px slots.

                         Geometry from the reference (2026-07-31): height
                         34, 12px gaps, width = text + 13px padding a side,
                         label in tofa_font_metadata (that size is what
                         reproduces the reference's 52/93/180 widths). -->
                    <!-- "IN CINEMAS": a theatrical title with no home
                         release yet. Shares the BADGES row, not a row of its
                         own, because the two can never both appear: a
                         title still only in cinemas has no file, and format
                         badges describe a file. Same row, so the stack
                         arithmetic is untouched.

                         Fixed 180 wide: Kodi cannot size a control to its
                         own text, and this string never varies. Measured off
                         the reference (atv-reference/detail-not-in-library.png):
                         ink runs 10..162 from the stack's left edge, in the
                         same amber the Discover card's clapperboard chip
                         already uses. -->
                    <control type="group" id="5109">
                        <posy>123</posy>
                        <visible>!String.IsEmpty(Window.Property(cinema_label))</visible>
                        <control type="image">
                            <posx>0</posx>
                            <posy>-2</posy>
                            <width>180</width>
                            <height>38</height>
                            <colordiffuse>{CINEMA_AMBER_SOFT}</colordiffuse>
                            <texture border="19">capsule-h38-outline.png</texture>
                        </control>
                        <control type="label">
                            <posx>12</posx>
                            <posy>0</posy>
                            <width>28</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_19</font>
                            <textcolor>{CINEMA_AMBER}</textcolor>
                            <label>$INFO[Window.Property(cinema_glyph)]</label>
                        </control>
                        <control type="label">
                            <posx>48</posx>
                            <posy>0</posy>
                            <width>124</width>
                            <height>34</height>
                            <aligny>center</aligny>
                            <font>tofa_font_metadata</font>
                            <textcolor>{CINEMA_AMBER}</textcolor>
                            <label>$INFO[Window.Property(cinema_label)]</label>
                        </control>
                    </control>

                    <control type="group" id="5106">
                        <posy>123</posy>
                        <control type="image" id="5112">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_1_label))</visible>
                        </control>
                        <control type="label" id="5113">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_ACCOUNT}</font>
                            <textcolor>{FORMAT_PLATE_INK}</textcolor>
                            <label>$INFO[Window.Property(badge_1_label)]</label>
                        </control>
                        <control type="image" id="5114">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_2_label))</visible>
                        </control>
                        <control type="label" id="5115">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_ACCOUNT}</font>
                            <textcolor>{FORMAT_PLATE_INK}</textcolor>
                            <label>$INFO[Window.Property(badge_2_label)]</label>
                        </control>
                        <control type="image" id="5116">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_3_label))</visible>
                        </control>
                        <control type="label" id="5117">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_ACCOUNT}</font>
                            <textcolor>{FORMAT_PLATE_INK}</textcolor>
                            <label>$INFO[Window.Property(badge_3_label)]</label>
                        </control>
                        <control type="image" id="5118">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_4_label))</visible>
                        </control>
                        <control type="label" id="5119">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_ACCOUNT}</font>
                            <textcolor>{FORMAT_PLATE_INK}</textcolor>
                            <label>$INFO[Window.Property(badge_4_label)]</label>
                        </control>
                        <control type="image" id="5120">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{FORMAT_PLATE_FILL}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_5_label))</visible>
                        </control>
                        <control type="label" id="5121">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_ACCOUNT}</font>
                            <textcolor>{FORMAT_PLATE_INK}</textcolor>
                            <label>$INFO[Window.Property(badge_5_label)]</label>
                        </control>
                    </control>

                    <!-- "Plays as X": what the audio will actually come out
                         as. Not a guess about downmixing; this client forces
                         Direct Play (see player.py / CapabilityProfile), so
                         the source layout IS the output layout, and that is
                         what this states. If a transcoding path is ever
                         added, this must switch to the negotiated stream's
                         layout instead of the file's. -->
                    <control type="label" id="5108">
                        <posx>0</posx>
                        <posy>179</posy>
                        <width>28</width>
                        <height>24</height>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>&#xE0F9;</label>
                        <visible>!String.IsEmpty(Window.Property(plays_as_line))</visible>
                    </control>
                    <control type="label" id="5107">
                        <posx>30</posx>
                        <posy>179</posy>
                        <width>600</width>
                        <height>24</height>
                        <aligny>center</aligny>
                        <font>tofa_font_metadata</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>$INFO[Window.Property(plays_as_line)]</label>
                        <visible>!String.IsEmpty(Window.Property(plays_as_line))</visible>
                    </control>

                    <!-- Synopsis: 4 visible lines with autoscroll for
                         whatever still doesn't fit, same pattern as Home's
                         own hero synopsis (main.xml.tpl id 4004).
                         The reference shows four
                         (atv-reference/detail-not-in-library.png), and this
                         box showed three and autoscrolled the rest, so the
                         page opened mid-sentence often as not.
                         Width 1264 (not 860): the text runs over the hero
                         art on the right, which is what the real app does.
                         The 4th line used to collide with "Plays as"; the
                         whole stack above now sits 35 higher, so it does
                         not (detail.py: HERO_STACK).

                         129 is FOUR CELLS PLUS ONE, and both halves of that
                         matter. Kodi lays tofa_font_row_title out at 32/line
                         here, measured off the render at rest: line 4's ink
                         runs y=832 to 858, line 5's would start at 862.

                         The old 141 was four cells (128) plus 13px of
                         leftover, and Kodi draws a PARTIAL line into leftover
                         space, so the top of a 5th line showed as a row of
                         sheared-off ascenders under the block. Adrian spotted
                         it as "the top pixels of a 4th line".

                         So the bottom edge has to land in the gap BETWEEN
                         line 4's ink and line 5's, i.e. 859..861. Four exact
                         cells (128) puts it at 859, one pixel off line 4's
                         descenders; 129 puts it at 860, two clear either
                         way. That margin is the whole point: the pause card
                         in script-tofa-player.xml had none and clipped its
                         descenders on a 4K box while looking perfect at
                         1080p, because the control scales x2 but the font is
                         rendered natively and the line-height rounding does
                         not follow.

                         Do not "tidy" this to a multiple of the nominal
                         35.25 line height; that number was wrong and is what
                         produced 141 in the first place. -->
                    <!-- (four cells is 128; the +1 is descender headroom) -->
                    <control type="textbox" id="5104">
                        <posy>231</posy>
                        <width>1264</width>
                        <height>132</height>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(hero_synopsis)]</label>
                        <autoscroll delay="2000" time="4000" repeat="6000">true</autoscroll>
                    </control>

                    <!-- == Action pill row ==
                         All 4 pills use capsule-h64.png/capsule-h64-
                         outline.png at border=32 (height/2, a true
                         capsule), not white-square-rounded.png's
                         border=18 partial rounding. One asset per pill
                         HEIGHT: a 9-patch corner is drawn unscaled, so
                         the asset's baked radius must equal its border.
                         See tools/gen_capsule_pill_assets.py. -->
                    <control type="group">
                        <posy>392</posy>

                        <!-- Primary Resume/Play pill. NOT a solid accent
                             fill: captured from the real Apple TV app on
                             2026-07-31 with focus moved off it, and the
                             primary CTA is the SAME glass pill as
                             Options/Rewatch/Watchlist beside it (measured
                             ~0x2E white over the hero art, white label and
                             icon), with focus shown as an accent outline
                             rather than a fill swap. An earlier session
                             recorded the opposite and this block was built
                             solid; that was wrong. Same states as
                             fragments.py:glass_pill() so all four buttons in
                             the row stay consistent. -->
                        <control type="group" id="5219">
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>360</width>
                                <height>78</height>
                                <colordiffuse>{SURFACE_REST}</colordiffuse>
                                <texture border="39">capsule-h78.png</texture>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>360</width>
                                <height>78</height>
                                <colordiffuse>$INFO[Window.Property(accent_pill_fill)]</colordiffuse>
                                <texture border="39">capsule-h78.png</texture>
                                <visible>Control.HasFocus(5210)</visible>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>360</width>
                                <height>78</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture border="39">capsule-h78-outline.png</texture>
                                <visible>Control.HasFocus(5210)</visible>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>360</width>
                                <height>78</height>
                                <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                                <texture border="39">capsule-h78-outline.png</texture>
                                <visible>!Control.HasFocus(5210)</visible>
                            </control>
                            <!-- Resume progress: a full-width TRACK with the
                                 watched fraction filled on top. The track is
                                 not decoration; without it a just-started
                                 title renders a ~5px fill floating in the
                                 middle of the pill, which reads as a stray
                                 dot rather than progress. The real Apple TV
                                 app draws the same tiny fill (measured 1.8%
                                 of the bar on a 15-second resume) and it
                                 reads correctly purely because the track is
                                 there.

                                 Geometry proportional to the reference,
                                 measured on a 360x78 pill: track 6px tall
                                 (7.7% of pill height), 6px above the bottom,
                                 inset 28px each side (7.8%), so 84.4% of the
                                 pill width. Scaled to this 280x64 pill:
                                 5px tall, 5px up, inset 22, width 236.
                                 The inset is not cosmetic; the r=32 cap has
                                 already come in 13.3px at the bar's bottom
                                 row, so a smaller inset puts the bar's end
                                 outside the capsule. -->
                            <control type="image">
                                <posx>28</posx>
                                <posy>66</posy>
                                <width>304</width>
                                <height>6</height>
                                <colordiffuse>{SURFACE_TRACK}</colordiffuse>
                                <!-- SQUARE ends, to match the accent fill that
                                     sits on top of it. This was
                                     white-square-rounded at border 2, whose
                                     baked radius is ~4 whatever border says;
                                     4 of a 6px bar is two thirds of its
                                     height, so the right end read as a taper
                                     while the left, covered by the square
                                     accent strip, read as a clean edge.
                                     Measured on screen: left edge flat at
                                     x=128 on every row, right edge curving
                                     423 then 431 then 423. The accent strips
                                     (progress/NN.png) are square, so the track
                                     under them has to be. -->
                                <texture>white-square.png</texture>
                                <visible>!String.IsEmpty(Window.Property(primary_progress_fill))</visible>
                            </control>
                            <control type="image">
                                <posx>28</posx>
                                <posy>66</posy>
                                <width>304</width>
                                <height>6</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture>$INFO[Window.Property(primary_progress_fill)]</texture>
                                <visible>!String.IsEmpty(Window.Property(primary_progress_fill))</visible>
                            </control>
                            <!-- Icon + label as one centred group, same as
                                 the other three action pills. This one alone
                                 needs runtime positioning: its label flips
                                 Play <-> Resume, so the group's width (and
                                 therefore where it starts) changes with the
                                 title's watch state. DetailWindow.
                                 _layout_primary_pill() sets both x values;
                                 the ones here are the Play case, so the pill
                                 is already right before Python touches it. -->
                            <control type="label" id="5211">
                                <posx>135</posx>
                                <posy>0</posy>
                                <width>28</width>
                                <height>78</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_24</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(primary_glyph)]</label>
                            </control>
                            <control type="label" id="5212">
                                <!-- posx/width are set at runtime by
                                     detail.py:_layout_primary_pill, which is
                                     also what decides whether an icon is
                                     taking room on the left. CENTRED, like
                                     every other action pill's label: this
                                     one holds anything from "Play" to
                                     "Resume S2 E2" to "Coming to library". -->
                                <posx>78</posx>
                                <posy>0</posy>
                                <width>242</width>
                                <height>78</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(primary_label)]</label>
                            </control>
                            <control type="button" id="5210">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>360</width>
                                <height>78</height>
                                <texturefocus>transparent-6px.png</texturefocus>
                                <texturenofocus>transparent-6px.png</texturenofocus>
                                <label></label>
                                <onright>5220</onright>
                                <ondown>6110</ondown>
                            </control>
                        </control>

                        <!-- Rewatch pill (glass), only shown when watched. -->
{rewatch_pill}

                        <!-- Options pill (glass): opens the Quality picker
                             (reuses picker.py:PickerDialog, the same dialog
                             Browse's Sort/Filter/Quality/Genre use). Always
                             shown, unlike Rewatch/Watchlist. -->
{options_pill}

                        <!-- Watchlist toggle pill (glass). Label +/- driven. -->
{watchlist_pill}
{cancel_request_pill}

                        <!-- Edition / version picker. Hidden on the majority
                             of titles, which have a single file. -->
{version_pill}
                    </control>
                </control>

                <!-- Bottom-center hint: eyebrow + down chevron. Text is
                     built by detail.py:_wire_tab_navigation() from the tabs
                     this media type has, which is all of them bar Episodes
                     on a movie; an empty tab still exists and still shows
                     its own scaffold. Width 500 avoids clipping the 4-tab TV
                     hint "EPISODES · CAST · ABOUT · MORE". -->
                <control type="group">
                    <posx>760</posx>
                    <posy>1000</posy>
                    <visible>String.IsEmpty(Window.Property(detail_state))</visible>
                    <control type="label">
                        <width>500</width>
                        <height>24</height>
                        <align>center</align>
                        <font>tofa_font_eyebrow</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(detail_tabs_hint)]</label>
                    </control>
                    <control type="label">
                        <posy>40</posy>
                        <width>500</width>
                        <height>26</height>
                        <align>center</align>
                        <font>tofa_font_icons_19</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>&#xE06D;</label>
                    </control>
                </control>

                <!-- The page failed to load. 9.7's error flavour, driven by
                     detail.py:_set_load_error(); the two blocks above hide
                     themselves on the same property, so this is what page 1
                     IS in that state rather than an overlay on top of it.

                     The backdrop behind it is detail-no-backdrop.png, since
                     hero_backdrop never got set; that is the same soft wash
                     a title with no artwork gets, and the reason this reads
                     as sparse rather than as a hole. -->
{load_error}

                <!-- 9.7's Retry, the first one in the app: empty_state has
                     described this button since it was written and no screen
                     could wire it, having no reload path. Detail's is
                     _load() again. Sits below the message slot (centre 635)
                     with the same 64px pill the action row uses. -->
                <control type="group">
                    <posy>712</posy>
                    <visible>String.IsEqual(Window.Property(detail_state),error)</visible>
{retry_pill}
                </control>
            </control>

            <!-- ============================ PAGE 2 ============================ -->
            <!-- One scrolling page under the hero (app 2.0.0), generated by
                 fragments.detail_page2(); detail.py lays out its blocks. -->
            <control type="group" id="5300">
                <posx>0</posx>
                <posy>0</posy>
                <visible>String.IsEqual(Window.Property(detailpage),page2)</visible>
                <animation effect="slide" start="0,60" end="0,0" time="220" tween="quadratic" easing="out" condition="String.IsEqual(Window.Property(detailpage),page2)">Conditional</animation>
                <animation effect="fade" start="0" end="100" time="200">Visible</animation>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>{SCREEN_W}</width>
                    <height>{SCREEN_H}</height>
                    <colordiffuse>0xC8030B10</colordiffuse>
                    <texture>white-square.png</texture>
                </control>
{page2}
            </control>
        </control>
        <!-- 8.9's toast, LAST so it draws over the hero and every panel. -->
{toast}

        <!-- kodigui framework sentinel (must exist in every window XML). -->
        <control type="label" id="666">
            <visible>false</visible>
            <width>1</width>
            <height>1</height>
        </control>
    </controls>
</window>
