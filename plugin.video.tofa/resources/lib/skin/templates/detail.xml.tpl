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
                            <colordiffuse>{BORDER}</colordiffuse>
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
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_1_label)]</label>
                        </control>
                        <control type="image" id="5114">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
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
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_2_label)]</label>
                        </control>
                        <control type="image" id="5116">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
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
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_3_label)]</label>
                        </control>
                        <control type="image" id="5118">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
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
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_4_label)]</label>
                        </control>
                        <control type="image" id="5120">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
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
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
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
            <control type="group" id="5300">
                <posx>0</posx>
                <posy>0</posy>
                <visible>String.IsEqual(Window.Property(detailpage),page2)</visible>
                <animation effect="slide" start="0,60" end="0,0" time="220" tween="quadratic" easing="out" condition="String.IsEqual(Window.Property(detailpage),page2)">Conditional</animation>
                <animation effect="fade" start="0" end="100" time="200">Visible</animation>

                <!-- ~85% dark scrim over the shared backdrop. -->
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>{SCREEN_W}</width>
                    <height>{SCREEN_H}</height>
                    <colordiffuse>0xD9030B10</colordiffuse>
                    <texture>white-square.png</texture>
                </control>

                <!-- Header row: eyebrow title + pill tabs.

                     TWO title labels, one per tab count, because Kodi parses
                     width at load and $INFO does not resolve in a coordinate
                     - so a single label cannot be one size for a film and
                     another for a series. Labels carry no id, so duplicating
                     them is free; duplicating the TABS would not be, since
                     two controls sharing id 6100 would make Control.HasFocus
                     and setFocusId ambiguous.

                     The old single label was 380 wide and 274 of this
                     library's 841 shows (32.6%) overflowed it - measured at
                     inter_tight_semibold 39, uppercased. "THE WALKING DEAD:
                     DEAD CITY" needs 579px and lost about its last third.

                     A TV show keeps 844 (100..944, clear of the Episodes
                     pill at 968); a film has no Episodes pill, so it keeps
                     1058 (100..1158, clear of Cast & Crew at 1182). 844 fits
                     ~96% of the shows here, against 67% at the old 380, and
                     covers "THE WALKING DEAD: DEAD CITY" at 579. -->
                <control type="label">
                    <visible>String.IsEqual(Window.Property(is_tv),1)</visible>
                    <posx>100</posx>
                    <posy>66</posy>
                    <width>844</width>
                    <height>44</height>
                    <aligny>center</aligny>
                    <font>tofa_font_section_title</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(eyebrow_title)]</label>
                </control>
                <control type="label">
                    <visible>!String.IsEqual(Window.Property(is_tv),1)</visible>
                    <posx>100</posx>
                    <posy>66</posy>
                    <width>1058</width>
                    <height>44</height>
                    <aligny>center</aligny>
                    <font>tofa_font_section_title</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(eyebrow_title)]</label>
                </control>

                <!-- Tab bar: left-to-right order is Episodes first for TV,
                     then Cast & Crew / About / More Like This. The
                     CURRENT/active tab is white outline + white text;
                     accent color is reserved for the tab that currently
                     holds keyboard FOCUS, a separate state from "active".
                     A short accent underline segment sits under the
                     active tab regardless of focus.

                     Uses tools/gen_tab_pill_assets.py's exact-size assets
                     (one fill+outline pair per tab's own width, no
                     9-patch/border attribute), same technique
                     poster_visual()/episode_card() use: a 9-patch
                     border-stretch of a pure-circle asset has no
                     straight edge to tile the middle from and warps into
                     an arrow/bulge shape once stretched this much
                     narrower than the action row.

                     POSITIONS ARE RIGHT-ALIGNED, not the reference's. The
                     app flows this row - title sized to its own text, tabs
                     immediately after, gaps a constant 76 (measured on
                     Android 0.1.11: WORKAHOLICS 96..258, then 312, 474, 663,
                     795, with "0/10 watched" ending at 1824). Kodi cannot
                     flow: width and posx are parsed at load and $INFO does
                     not resolve in a coordinate, so a title-sized-to-text
                     layout is not expressible here.

                     So the bar is pinned to the RIGHT margin instead: the
                     last pill ends at 1820, the same 100px inset the title
                     keeps on the left.

                     That margin had to be cleared first. The "N/M watched"
                     count used to sit up here right-aligned to 1820, and the
                     first cut of this drove "More Like This" straight through
                     it; the count now rides the SEASON heading's row, which
                     is where the reference also draws it and which is the row
                     it actually describes. See its own note below.

                     Widths are baked into the per-tab assets
                     (gen_tab_pill_assets.py) and gaps are 24, so with
                     Episodes 190 / Cast 220 / About 140 / More 230 the row
                     starts at 968 for a series and, with Episodes hidden, at
                     1182 for a film. Each underline stays centred under its
                     own pill: offset (W - underline)/2, i.e. 45/50/35/50.

                     The bar therefore does NOT move between a film and a
                     series - only the title's width does. That is a
                     deliberate departure from "centre the trio for a film":
                     centring would make the row jump position depending on
                     what you opened, and right-pinning gives the title more
                     room in both cases (844 series / 1058 film). -->
                <!-- Episodes (TV only) -->
                <control type="group">
                    <visible>String.IsEqual(Window.Property(is_tv),1)</visible>
                    <control type="image">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <colordiffuse>0x1EFFFFFF</colordiffuse>
                        <texture>tab-pill-episodes.png</texture>
                    </control>
                    <control type="image">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>tab-pill-episodes-outline.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),episodes) + !Control.HasFocus(6100)</visible>
                    </control>
                    <control type="image">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>tab-pill-episodes-outline.png</texture>
                        <visible>Control.HasFocus(6100)</visible>
                    </control>
                    <control type="image">
                        <posx>1013</posx>
                        <posy>109</posy>
                        <width>100</width>
                        <height>3</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>white-square.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),episodes)</visible>
                    </control>
                    <control type="label">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>Episodes</label>
                        <visible>Control.HasFocus(6100)</visible>
                    </control>
                    <control type="label">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Episodes</label>
                        <visible>String.IsEqual(Window.Property(detail_tab),episodes) + !Control.HasFocus(6100)</visible>
                    </control>
                    <control type="label">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>Episodes</label>
                        <visible>!String.IsEqual(Window.Property(detail_tab),episodes)</visible>
                    </control>
                    <control type="button" id="6100">
                        <posx>968</posx>
                        <posy>66</posy>
                        <width>190</width>
                        <height>44</height>
                        <texturefocus>transparent-6px.png</texturefocus>
                        <texturenofocus>transparent-6px.png</texturenofocus>
                        <label></label>
                        <onup>5210</onup>
                        <onright>6110</onright>
                        <!-- Down goes to the EPISODE GRID, not the season
                             rail. The grid opens on the episode the hero's
                             Resume pill names, so moving down from
                             "Resume S1 E3" arrives on E3; landing on the
                             rail first put a second press between the
                             viewer and the thing they were already looking
                             at. The rail is one press LEFT from the grid,
                             which is where a viewer goes when they want a
                             different season rather than this episode. -->
                        <ondown>6410</ondown>
                    </control>
                </control>

                <!-- Cast & Crew -->
                <control type="group">
                    <control type="image">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <colordiffuse>0x1EFFFFFF</colordiffuse>
                        <texture>tab-pill-castcrew.png</texture>
                    </control>
                    <control type="image">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>tab-pill-castcrew-outline.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),cast) + !Control.HasFocus(6110)</visible>
                    </control>
                    <control type="image">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>tab-pill-castcrew-outline.png</texture>
                        <visible>Control.HasFocus(6110)</visible>
                    </control>
                    <control type="image">
                        <posx>1232</posx>
                        <posy>109</posy>
                        <width>120</width>
                        <height>3</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>white-square.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),cast)</visible>
                    </control>
                    <control type="label">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>Cast &amp; Crew</label>
                        <visible>Control.HasFocus(6110)</visible>
                    </control>
                    <control type="label">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Cast &amp; Crew</label>
                        <visible>String.IsEqual(Window.Property(detail_tab),cast) + !Control.HasFocus(6110)</visible>
                    </control>
                    <control type="label">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>Cast &amp; Crew</label>
                        <visible>!String.IsEqual(Window.Property(detail_tab),cast)</visible>
                    </control>
                    <control type="button" id="6110">
                        <posx>1182</posx>
                        <posy>66</posy>
                        <width>220</width>
                        <height>44</height>
                        <texturefocus>transparent-6px.png</texturefocus>
                        <texturenofocus>transparent-6px.png</texturenofocus>
                        <label></label>
                        <onup>5210</onup>
                        <onleft>6100</onleft>
                        <onright>6120</onright>
                        <ondown>6200</ondown>
                    </control>
                </control>

                <!-- About -->
                <control type="group">
                    <control type="image">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <colordiffuse>0x1EFFFFFF</colordiffuse>
                        <texture>tab-pill-about.png</texture>
                    </control>
                    <control type="image">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>tab-pill-about-outline.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),about) + !Control.HasFocus(6120)</visible>
                    </control>
                    <control type="image">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>tab-pill-about-outline.png</texture>
                        <visible>Control.HasFocus(6120)</visible>
                    </control>
                    <control type="image">
                        <posx>1461</posx>
                        <posy>109</posy>
                        <width>70</width>
                        <height>3</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>white-square.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),about)</visible>
                    </control>
                    <control type="label">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>About</label>
                        <visible>Control.HasFocus(6120)</visible>
                    </control>
                    <control type="label">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>About</label>
                        <visible>String.IsEqual(Window.Property(detail_tab),about) + !Control.HasFocus(6120)</visible>
                    </control>
                    <control type="label">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>About</label>
                        <visible>!String.IsEqual(Window.Property(detail_tab),about)</visible>
                    </control>
                    <control type="button" id="6120">
                        <posx>1426</posx>
                        <posy>66</posy>
                        <width>140</width>
                        <height>44</height>
                        <texturefocus>transparent-6px.png</texturefocus>
                        <texturenofocus>transparent-6px.png</texturenofocus>
                        <label></label>
                        <onup>5210</onup>
                        <onleft>6110</onleft>
                        <onright>6130</onright>
                        <!-- Itself, NOT the cast panel. About's body is a
                             textbox, so there is nothing below this tab to
                             move into; aiming Down at 6200 (a copy of the
                             Cast tab's own target) put focus in Cast's grid,
                             and since the tab follows focus that silently
                             switched the page to Cast & Crew. Down on a tab
                             with no focusable content does nothing. -->
                        <ondown>6120</ondown>
                    </control>
                </control>

                <!-- More Like This -->
                <control type="group">
                    <control type="image">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <colordiffuse>0x1EFFFFFF</colordiffuse>
                        <texture>tab-pill-morelikethis.png</texture>
                    </control>
                    <control type="image">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <colordiffuse>white</colordiffuse>
                        <texture>tab-pill-morelikethis-outline.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),more) + !Control.HasFocus(6130)</visible>
                    </control>
                    <control type="image">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>tab-pill-morelikethis-outline.png</texture>
                        <visible>Control.HasFocus(6130)</visible>
                    </control>
                    <control type="image">
                        <posx>1640</posx>
                        <posy>109</posy>
                        <width>130</width>
                        <height>3</height>
                        <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                        <texture>white-square.png</texture>
                        <visible>String.IsEqual(Window.Property(detail_tab),more)</visible>
                    </control>
                    <control type="label">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                        <label>More Like This</label>
                        <visible>Control.HasFocus(6130)</visible>
                    </control>
                    <control type="label">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>More Like This</label>
                        <visible>String.IsEqual(Window.Property(detail_tab),more) + !Control.HasFocus(6130)</visible>
                    </control>
                    <control type="label">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>More Like This</label>
                        <visible>!String.IsEqual(Window.Property(detail_tab),more)</visible>
                    </control>
                    <control type="button" id="6130">
                        <posx>1590</posx>
                        <posy>66</posy>
                        <width>230</width>
                        <height>44</height>
                        <texturefocus>transparent-6px.png</texturefocus>
                        <texturenofocus>transparent-6px.png</texturenofocus>
                        <label></label>
                        <onup>5210</onup>
                        <onleft>6120</onleft>
                        <ondown>6300</ondown>
                    </control>
                </control>

                <!-- Hairline rule under the header row. -->
                <control type="image">
                    <posx>100</posx>
                    <posy>124</posy>
                    <width>1720</width>
                    <height>1</height>
                    <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                    <texture>white-square.png</texture>
                </control>

                <!-- Cast & Crew tab content: two labeled WRAPPING GRIDS
                     (fragments.py:person_card(), called once per list)
                     stacked in one grouplist. orientation="vertical" on a
                     panel with a fixed width/itemwidth wraps row-by-row
                     left-to-right (same convention as Browse's own poster
                     grid, main.xml.tpl id 6200); it does not mean
                     single-column. CAST_TILE/CAST_PHOTO tile the
                     CAST_PANEL_W-wide panel into exactly CAST_COLS columns
                     with zero leftover.

                     Each panel is sized at runtime to its own row count
                     (detail.py:_size_person_panels), capped at the rows
                     that fit the viewport, so the grouplist below owns the
                     scrolling wherever it can and an empty section
                     collapses instead of leaving a hole. The heights
                     declared here are just a pre-data placeholder. Crew's
                     block only renders (in Python) when the title has crew
                     data. -->
                <control type="group">
                    <visible>String.IsEqual(Window.Property(detail_tab),cast)</visible>

{cast_empty}

                    <!-- Cast and Crew live in ONE grouplist so the whole
                         region scrolls together. They used to be four
                         absolutely-positioned controls, which meant moving
                         down into Crew scrolled Crew's panel internally
                         while Cast stayed pinned above it; the page could
                         never move as a unit.

                         Same construction Home (grouplist 4090) and
                         Discover (6390) already use for their stacked
                         shelves. A grouplist stacks its children by their
                         own declared heights and ignores their posy, so
                         nothing in here carries an absolute y, and it skips
                         invisible children, which is what lets Crew's
                         label and panel simply disappear on a title with no
                         crew instead of leaving a hole.

                         posx is relative to the grouplist now: the labels
                         sit at 8 to land on the same 100 the panels' 92
                         plus their own inset produce. -->
                    <control type="grouplist" id="6250">
                        <visible>!String.IsEmpty(Window.Property(has_cast_content))</visible>
                        <posx>92</posx>
                        <posy>150</posy>
                        <width>{CAST_PANEL_W}</width>
                        <height>{CAST_VIEWPORT_H}</height>
                        <orientation>vertical</orientation>
                        <itemgap>0</itemgap>
                        <scrolltime>{SCROLLTIME}</scrolltime>

                        <control type="label">
                            <posx>8</posx>
                            <width>400</width>
                            <height>46</height>
                            <font>tofa_font_button</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>Cast</label>
                        </control>
                        <!-- Placeholder height only: two rows' worth, so the
                             pre-data layout is sane. detail.py overwrites it
                             with the real row count the moment cast loads.
                             It must be an exact multiple of the itemheight
                             either way; at 500 the second row was clipped
                             80px into its own 290-tall cell, cutting off
                             exactly the name and role that sit at the cell's
                             bottom. -->
                        <control type="panel" id="6200">
                            <posx>0</posx>
                            <width>{CAST_PANEL_W}</width>
                            <height>{CAST_PANEL_H_MAX}</height>
                            <onup>6110</onup>
                            <ondown>6210</ondown>
                            <orientation>vertical</orientation>
                            <itemwidth>{CAST_TILE}</itemwidth>
                            <itemheight>{CAST_TILE}</itemheight>
                            <scrolltime>{SCROLLTIME}</scrolltime>

{cast_item}

{cast_focused}
                        </control>

                        <control type="label">
                            <visible>!String.IsEmpty(Window.Property(has_crew))</visible>
                            <posx>8</posx>
                            <width>400</width>
                            <height>46</height>
                            <font>tofa_font_button</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>Crew</label>
                        </control>
                        <control type="panel" id="6210">
                            <visible>!String.IsEmpty(Window.Property(has_crew))</visible>
                            <posx>0</posx>
                            <width>{CAST_PANEL_W}</width>
                            <height>{CAST_PANEL_H_MAX}</height>
                            <onup>6200</onup>
                            <orientation>vertical</orientation>
                            <itemwidth>{CAST_TILE}</itemwidth>
                            <itemheight>{CAST_TILE}</itemheight>
                            <scrolltime>{SCROLLTIME}</scrolltime>

{crew_item}

{crew_focused}
                        </control>
                    </control>
                </control>

                <!-- About tab content: tagline + overview + ratings +
                     badges (left) and a structured eyebrow/value facts
                     panel (right), a two-column layout. Facts use the
                     same "fixed positional slots filled left-to-right,
                     ordered in Python, skip if absent" convention as the
                     hero's format badges above: detail.py:_about_facts()
                     decides which of the 5 possible facts apply and in
                     what order; the XML just renders
                     fact_N_eyebrow/fact_N_value for N in 1..5. -->
                <control type="group">
                    <visible>String.IsEqual(Window.Property(detail_tab),about)</visible>

                    <control type="label" id="6600">
                        <posx>100</posx>
                        <posy>168</posy>
                        <width>980</width>
                        <height>26</height>
                        <font>tofa_font_micro</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(about_tagline)]</label>
                        <visible>!String.IsEmpty(Window.Property(about_tagline))</visible>
                    </control>
                    <control type="textbox" id="6601">
                        <posx>100</posx>
                        <posy>204</posy>
                        <width>980</width>
                        <height>280</height>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(about_synopsis)]</label>
                    </control>
                    <control type="label" id="6602">
                        <posx>100</posx>
                        <posy>494</posy>
                        <width>980</width>
                        <height>24</height>
                        <font>tofa_font_poster_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(hero_ratings_line)]</label>
                    </control>
                    <!-- Same badges as the hero, and now the same
                         treatment: 34 tall in FONT_METADATA, sized to
                         hug their own text by detail.py rather than
                         sitting in fixed 150/200px slots. They always
                         read the same STRINGS (one set of
                         badge_N_label properties feeds both), so the
                         two rows looking different was the only thing
                         left saying otherwise. -->
                    <control type="group" id="6603">
                        <posx>100</posx>
                        <posy>553</posy>
                        <control type="image" id="6610">
                            <posx>0</posx>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_1_label))</visible>
                        </control>
                        <control type="label" id="6611">
                            <posx>0</posx>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_1_label)]</label>
                        </control>
                        <control type="image" id="6612">
                            <posx>158</posx>
                            <width>150</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_2_label))</visible>
                        </control>
                        <control type="label" id="6613">
                            <posx>158</posx>
                            <width>150</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_2_label)]</label>
                        </control>
                        <control type="image" id="6614">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_3_label))</visible>
                        </control>
                        <control type="label" id="6615">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_3_label)]</label>
                        </control>
                        <control type="image" id="6616">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_4_label))</visible>
                        </control>
                        <control type="label" id="6617">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_4_label)]</label>
                        </control>
                        <control type="image" id="6618">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <colordiffuse>{BORDER}</colordiffuse>
                            <texture border="4">white-square-rounded.png</texture>
                            <visible>!String.IsEmpty(Window.Property(badge_5_label))</visible>
                        </control>
                        <control type="label" id="6619">
                            <posx>316</posx>
                            <width>200</width>
                            <height>34</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[Window.Property(badge_5_label)]</label>
                        </control>
                    </control>

                    <!-- Facts panel: 6 fixed slots, stacked vertically at a 92px
                         pitch. The sixth is the projection ratio, which the
                         reference app does not carry at all; see
                         detail.py:_about_facts() for why it is appended last
                         rather than slotted among the five it does. -->
                    <control type="group">
                        <posx>1160</posx>
                        <posy>170</posy>

                        <control type="group">
                            <posy>0</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_1_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_1_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_1_value)]</label>
                            </control>
                        </control>
                        <control type="group">
                            <posy>92</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_2_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_2_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_2_value)]</label>
                            </control>
                        </control>
                        <control type="group">
                            <posy>184</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_3_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_3_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_3_value)]</label>
                            </control>
                        </control>
                        <control type="group">
                            <posy>276</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_4_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_4_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_4_value)]</label>
                            </control>
                        </control>
                        <control type="group">
                            <posy>368</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_5_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_5_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_5_value)]</label>
                            </control>
                        </control>
                        <control type="group">
                            <posy>460</posy>
                            <visible>!String.IsEmpty(Window.Property(fact_6_value))</visible>
                            <control type="label">
                                <width>660</width>
                                <height>22</height>
                                <font>tofa_font_eyebrow</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>| $INFO[Window.Property(fact_6_eyebrow)]</label>
                            </control>
                            <control type="label">
                                <posy>26</posy>
                                <width>660</width>
                                <height>34</height>
                                <font>tofa_font_button</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[Window.Property(fact_6_value)]</label>
                            </control>
                        </control>
                    </control>
                </control>

                <!-- More Like This tab content: TWO labelled shelves, not
                     one grid. Captured off the real Apple TV app
                     (internal-docs/atv-reference/detail-more-like-this.png):
                     "More Like This" carries what the library already holds,
                     "More to Discover" the requestable ones, whose cards
                     wear the same `plus` not-in-library chip Discover's own
                     rows use. So the split the API already returns IS the
                     category axis; an earlier pass here guessed otherwise
                     and built a flat 6-column grid mixing the two.

                     Stacked in a grouplist, the same construction Home
                     (4090) and Discover (6390) use. Each shelf is wrapped in
                     its own group by poster_row(), which is what keeps the
                     grouplist's navigation override off the focusable lists
                     inside; Cast & Crew's panels sit directly in their
                     grouplist and had to have Up/Down re-asserted from
                     Python because of it.

                     posx 100 puts label and art on the same content edge the
                     rest of the screen uses: poster_row lays its label at 0
                     and its list at ROW_LIST_X, which is exactly -HPAD, so
                     the card ART lands back on the grouplist's own x. -->
                <control type="group">
                    <visible>String.IsEqual(Window.Property(detail_tab),more)</visible>
                    <control type="grouplist" id="6350">
                        <posx>100</posx>
                        <posy>150</posy>
                        <width>{DETAIL_SHELF_W}</width>
                        <height>{DETAIL_SHELF_H}</height>
                        <orientation>vertical</orientation>
                        <itemgap>0</itemgap>
                        <scrolltime>{SCROLLTIME}</scrolltime>
                        <visible>String.IsEmpty(Window.Property(similar_state))</visible>

{similar_rows}
                    </control>
{similar_empty}
                </control>

                <!-- Episodes tab content (TV only): season sidebar (left)
                     + episode thumbnail grid (right), plus an "X/Y
                     watched" counter for the selected season. Sidebar
                     styling mirrors Browse's own sidebar row (glass fill,
                     accent left bar + accent text/icon when active) at a
                     narrower width to fit next to the grid. -->
                <control type="group">
                    <visible>String.IsEqual(Window.Property(detail_tab),episodes)</visible>

                    <control type="label">
                        <posx>100</posx>
                        <posy>150</posy>
                        <width>260</width>
                        <height>22</height>
                        <font>tofa_font_micro</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>SEASONS</label>
                    </control>

                    <!-- Season header: title + "X episodes · year ·
                         Continue SxEx" subtitle.

                         Title is section-title scale, not heading: heading is
                         57pt and Kodi does not clip a label vertically the way
                         it clips an item layout, so a 57pt glyph in this box
                         rendered straight through the subtitle underneath it.
                         Sized so title + subtitle both clear the episode grid
                         at posy 230. -->
                    <control type="label">
                        <posx>382</posx>
                        <posy>140</posy>
                        <width>890</width>
                        <height>48</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(season_title)]</label>
                    </control>
                    <!-- posx 382, not the grid's own 372: the cards are
                         inset by fragments.py's _EP_PAD (10), so a card's ink
                         starts 10px inside its cell. Measured on a live
                         capture, an unfocused still's first pixel is x=382
                         while this heading sat at 372, so the column read as
                         very slightly ragged. The grid PANEL stays at 372 -
                         its cells carry the pad - and only the headings move.

                         One line, two occupants. "10 episodes - 2026" while
                         the cursor is anywhere else; the FOCUSED episode's
                         synopsis while it is in the grid.

                         Sharing the line is what makes this free. The grid
                         below is three rows of 284 starting at 230, which is
                         exactly the screen height, so a synopsis given its
                         own row would push the third row off. The subtitle
                         is also the one thing here the grid already says:
                         the episode count is the grid, and the year is on
                         the hero.

                         The synopsis label runs to 1630 rather than the
                         subtitle's 900, stopping clear of the "N/M watched"
                         count that is right-aligned to 1820 ("100/100
                         watched" is 204 wide at this font). One line at 1258
                         is about 85 characters; Kodi ellipsizes the rest.
                         See detail.py:_sync_episode_synopsis. -->
                    <control type="label">
                        <visible>String.IsEmpty(Window.Property(episode_synopsis))</visible>
                        <posx>382</posx>
                        <posy>192</posy>
                        <width>890</width>
                        <height>26</height>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(season_subtitle)]</label>
                    </control>
                    <control type="label">
                        <visible>!String.IsEmpty(Window.Property(episode_synopsis))</visible>
                        <posx>382</posx>
                        <posy>192</posy>
                        <width>1248</width>
                        <height>26</height>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(episode_synopsis)]</label>
                    </control>
                    <!-- The count sits on the SEASON heading's row, right
                         aligned to 1820.

                         It used to ride the show-title row up at posy 75, on
                         a note claiming it "counts the whole SHOW, not the
                         season being browsed". That premise was wrong about
                         our own code: _render_episodes sets it from
                         len(episodes), i.e. the season being browsed, so it
                         was season data sitting in the show's header.

                         The reference draws it on BOTH rows and both read the
                         season's number (Android 0.1.11, Workaholics: "0/10
                         watched" at the title row AND beside "Season 1",
                         where season 1 has ten episodes and the show has
                         more). Down here it is next to the heading it
                         actually describes, and it frees the top right for
                         the tab bar, which needs the room far more - see the
                         tab bar's own note. Adrian's call, 2026-08-10.

                         posx is the RIGHT edge, not the left: for a window
                         label (unlike a list item's) Kodi anchors a
                         right-aligned label at posx and runs the width
                         leftwards. -->
                    <control type="label">
                        <posx>1820</posx>
                        <posy>140</posy>
                        <width>400</width>
                        <height>48</height>
                        <align>right</align>
                        <aligny>center</aligny>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>$INFO[Window.Property(episodes_watched_count)]</label>
                    </control>

                    <!-- Season sidebar is NOT fragments.py:sidebar_row():
                         this itemlayout has real structural asymmetries
                         versus Browse's sidebar lists (a single always-on
                         {SURFACE_RAISED} fill instead of a dimmer-inactive/
                         brighter-active pair, and a single count label
                         with no active/inactive color split), so forcing
                         it through the shared fragment would change its
                         actual rendered behavior. -->
                    <control type="list" id="6400">
                        <posx>92</posx>
                        <posy>230</posy>
                        <width>260</width>
                        <height>{EPISODE_GRID_H}</height>
                        <onup>6100</onup>
                        <onright>6410</onright>
                        <orientation>vertical</orientation>
                        <itemwidth>260</itemwidth>
                        <itemheight>60</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>
                        <itemlayout width="260" height="60">
                            <control type="image">
                                <posx>0</posx>
                                <posy>2</posy>
                                <width>256</width>
                                <height>54</height>
                                <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                                <texture border="16">white-square-rounded.png</texture>
                            </control>
                            <control type="image">
                                <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>0</posx>
                                <posy>8</posy>
                                <width>3</width>
                                <height>42</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture>white-square.png</texture>
                            </control>
                            <control type="label">
                                <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>18</posx>
                                <posy>2</posy>
                                <width>170</width>
                                <height>54</height>
                                <aligny>center</aligny>
                                <font>tofa_font_sidebar_label</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>18</posx>
                                <posy>2</posy>
                                <width>170</width>
                                <height>54</height>
                                <aligny>center</aligny>
                                <font>tofa_font_sidebar_label</font>
                                <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <posx>188</posx>
                                <posy>2</posy>
                                <width>60</width>
                                <height>54</height>
                                <align>right</align>
                                <aligny>center</aligny>
                                <font>tofa_font_metadata</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>$INFO[ListItem.Property(count)]</label>
                            </control>
                        </itemlayout>
                        <focusedlayout width="260" height="60">
                            <control type="image">
                                <posx>0</posx>
                                <posy>2</posy>
                                <width>256</width>
                                <height>54</height>
                                <colordiffuse>{SURFACE_FAINT}</colordiffuse>
                                <texture border="16">white-square-rounded.png</texture>
                            </control>
                            <control type="image">
                                <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>0</posx>
                                <posy>2</posy>
                                <width>256</width>
                                <height>54</height>
                                <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                                <texture border="16">white-square-rounded.png</texture>
                            </control>
                            <control type="image">
                                <visible>Control.HasFocus(6400)</visible>
                                <posx>0</posx>
                                <posy>2</posy>
                                <width>256</width>
                                <height>54</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture border="16">white-outline-rounded.png</texture>
                            </control>
                            <control type="image">
                                <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>0</posx>
                                <posy>8</posy>
                                <width>3</width>
                                <height>42</height>
                                <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                                <texture>white-square.png</texture>
                            </control>
                            <control type="label">
                                <visible>!String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>18</posx>
                                <posy>2</posy>
                                <width>170</width>
                                <height>54</height>
                                <aligny>center</aligny>
                                <font>tofa_font_sidebar_label</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <visible>String.IsEqual(ListItem.Property(active),1)</visible>
                                <posx>18</posx>
                                <posy>2</posy>
                                <width>170</width>
                                <height>54</height>
                                <aligny>center</aligny>
                                <font>tofa_font_sidebar_label</font>
                                <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <posx>188</posx>
                                <posy>2</posy>
                                <width>60</width>
                                <height>54</height>
                                <align>right</align>
                                <aligny>center</aligny>
                                <font>tofa_font_metadata</font>
                                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                                <label>$INFO[ListItem.Property(count)]</label>
                            </control>
                        </focusedlayout>
                    </control>

                    <!-- episode_card(): rounded corners + focus
                         border/glow, same technique as
                         poster_visual()/tools/gen_episode_assets.py (see
                         fragments.py:EPISODE_CELL_H). -->
                    <control type="panel" id="6410">
                        <posx>372</posx>
                        <posy>230</posy>
                        <width>{EPISODE_GRID_W}</width>
                        <height>{EPISODE_GRID_H}</height>
                        <onup>6100</onup>
                        <onleft>6400</onleft>
                        <orientation>vertical</orientation>
                        <itemwidth>{EPISODE_CELL_W}</itemwidth>
                        <itemheight>{EPISODE_CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{episode_item}

{episode_focused}
                    </control>
                </control>
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
