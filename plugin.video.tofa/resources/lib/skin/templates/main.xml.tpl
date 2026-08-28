<?xml version="1.0" encoding="UTF-8"?>
<!--
  Merged main screen TEMPLATE, rendered to script-tofa-main.xml by
  resources/lib/skin/screens.py:render_main() (see resources/lib/skin/
  for the plain-Python fragment mechanism this project uses instead of
  Kodi's native <include>, which doesn't work for Python WindowXML).

  ONE persistent window replaces the old separate per-screen windows: the
  nav bar (built once, by windows/main.py:MainWindow.onFirstInit) never
  gets destroyed/rebuilt on a tab switch.

  Each section's own content lives in its own top-level <group>, gated by
  <visible>String.IsEqual(Window.Property(active_section),X)</visible>.
  Switching sections only flips this property (plus lazy-loading that
  section's data the first time); it never touches the nav bar's control
  tree.
-->
<window>
    <defaultcontrol always="true">3000</defaultcontrol>
    <backgroundcolor>0xff030b10</backgroundcolor>
    <coordinates>
        <system>0</system>
    </coordinates>
    <controls>
        <!-- ============================================================
             HOME SECTION (control ids 4000-5899/9000)
             ============================================================ -->
        <control type="group" id="3800">
            <posx>0</posx>
            <posy>0</posy>
            <visible>String.IsEqual(Window.Property(active_section),home)</visible>

            <!-- Same fallback Detail uses, for the same reason: a title with
                 no backdrop leaves 9000 drawing nothing. Reachable from Home
                 because an artwork-less item can sit in Continue Watching:
                 anything in a library like "Videos" is playable and none of
                 it has art. See tools/gen_backdrop_fallback.py. -->
            <control type="image">
                <visible>String.IsEmpty(Window.Property(hero_backdrop))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <aspectratio>stretch</aspectratio>
                <texture>detail-no-backdrop.png</texture>
            </control>

            <!-- Hero billboard: full-bleed backdrop of the focused item.

                 fadetime is the spec's crossfade, NOT an animation: 7.10.2
                 asks for the focus follower to cross-fade ~300ms, and an
                 <animation> cannot express "when the texture changes"; it
                 fires on window and focus events. Kodi reads fadetime on a
                 plain image control and hands it to CGUIImage::SetCrossFade
                 (GUIControlFactory.cpp), which is exactly this.

                 The swap is already debounced by SettleTimer at
                 FOCUS_SETTLE_MS, so this fades once per settled focus rather
                 than once per keypress down a row. -->
            <control type="image" id="9000">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <aspectratio>scale</aspectratio>
                <fadetime>{HERO_CROSSFADE_MS}</fadetime>
                <texture>-</texture>
            </control>

            <!-- Kodi has no gradient-fill primitive, so this stacks flat
                 image washes at descending opacity to fake a gradient. -->
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
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <colordiffuse>0x38030B10</colordiffuse>
                <texture>white-square.png</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>439</posy>
                <width>{SCREEN_W}</width>
                <height>641</height>
                <colordiffuse>0xE6030B10</colordiffuse>
                <texture>fade-bottom.png</texture>
            </control>

            <!-- Top scrim behind the shared nav bar; each section paints
                 its own since the canvas differs per section. -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCRIM_H}</height>
                <colordiffuse>{SCRIM_TOP}</colordiffuse>
                <texture>fade-top.png</texture>
            </control>

            <!-- Hero info block: title, metadata dot-line, ratings line,
                 2-line synopsis. Starts at the shared content left edge,
                 so it lines up with the rows below it. -->
            <!-- 239, not 259. Measured against the real Apple TV app: it
                 leaves 42px between the hero logo's baseline and the meta
                 line, we left 62. Moving the GROUP up carries the title,
                 meta, ratings and synopsis together, so their spacing (and
                 the no-logo case, where the title label occupies the top of
                 this group) is untouched; the logo compensates below to keep
                 its own baseline. The 20px this frees goes to the rows,
                 whose last caption was running off the bottom edge. -->
            <!-- Hidden by "Featured spotlight" (home_screen.show_hero).
                 The whole FOREGROUND goes: logo, title, metadata, ratings,
                 synopsis. The backdrop above stays, and keeps following
                 focus, which is what the reference app does. main.py moves
                 the rows up to take the space.

                 Gated on a property that means HIDDEN, so a window that has
                 not read the preference yet shows the hero rather than
                 flashing an empty screen. -->
            <control type="group" id="4000">
                <posx>{HOME_LEFT}</posx>
                <posy>239</posy>

                <!-- 7.10.2's crossfade, for the half of the hero that cannot
                     literally cross-fade. The backdrop above uses <fadetime>,
                     which needs two textures to dissolve between; a label has
                     one string and changes it in a single frame. So this dips:
                     out over half the clock, and Python swaps EVERY property in
                     this group (logo included) while it is invisible, then
                     clears the flag and the reverse brings it back.

                     On the group, not per label, so the block moves as one
                     piece; it also puts the logo/text-title switch between
                     two titles inside the invisible moment, rather than
                     leaving it a hard cut of its own.

                     Visible/Hidden on a <visible> condition, NOT a Conditional
                     animation. A Conditional was tried first and measured, and
                     only half of it ran: recorded at 60fps with the clock
                     turned up to 1000ms, the outgoing block sat at full
                     brightness for the entire second the flag was set (proven
                     by log: the flag really was set 1006ms before the swap),
                     then jumped to zero AT the swap and faded in correctly.
                     Kodi never advanced the forward run while only a Window
                     property had changed; it engaged the animation when the
                     labels' own $INFO content changed, by which point the
                     condition was going false again. Same family as the
                     re-evaluated-with-the-layout trap in
                     reference_kodi_list_item_animation, and the reason that
                     memory's rule is about CONDITIONAL on a ListItem property
                     rather than this case.

                     A <visible> condition is re-evaluated every frame, and
                     Kodi holds the hide back until the Hidden animation has
                     finished playing, which is exactly the dip. -->
                <!-- The second clause is "Featured spotlight" (see the
                     comment on this group). It is merged into THIS condition
                     rather than added as another <visible> on the group: a
                     control may only carry one, and a second silently wins
                     or loses with nothing to say which. Merging also means
                     switching the setting off dissolves the hero out through
                     the animations below, instead of it vanishing. -->
                <visible>!String.IsEqual(Window.Property(hero_swapping),1) + String.IsEmpty(Window.Property(home_hero_off))</visible>
                <animation effect="fade" start="100" end="0"
                           time="{HERO_TEXT_DISSOLVE_MS}">Hidden</animation>
                <animation effect="fade" start="0" end="100"
                           time="{HERO_TEXT_DISSOLVE_MS}">Visible</animation>

                <!-- Bottom-anchored, so the box's height is a CEILING on
                     the logo rather than its position: whatever the artwork's
                     aspect, its baseline stays put and the meta line below
                     never moves. 137 is measured, not chosen; the real Apple
                     TV app renders Hugo's logo 134px tall and this artwork
                     carries ~4px of transparent padding, so a 170 box was
                     giving us 166, a quarter taller than the app. -->
                <control type="image" id="4005">
                    <posx>0</posx>
                    <posy>-71</posy>
                    <width>560</width>
                    <height>137</height>
                    <aspectratio align="left" aligny="bottom">keep</aspectratio>
                    <texture>$INFO[Window.Property(hero_logo)]</texture>
                    <visible>!String.IsEmpty(Window.Property(hero_logo))</visible>
                </control>
                <!-- Renders ONLY when the title has no logo art (its own
                     visible= below), standing in for artwork rather than
                     heading a screen - so it is tofa_font_hero_title (61),
                     not tofa_font_hero (77). 77 measured RIGHT for the one
                     surface that really is a heading, the server picker.

                     WRAPS instead of ellipsising, because the app does.
                     Measured off a live capture of this very title with no
                     logo (2026-08-19): Apple TV lays it over two lines,
                     "To the Journey: Looking Back" / "at Star Trek:
                     Voyager", the longer line 822px. 830 is that column.
                     The width was 1608 (SCREEN_W - 2 * HOME_LEFT) and ran
                     one unbroken line most of the way across the screen,
                     which is half of why it read as oversized - the other
                     half being the 77.

                     BOTTOM-ANCHORED, THE ONLY WAY KODI ALLOWS. There is no
                     <aligny>bottom</aligny> for a label: GUIControlFactory
                     maps "bottom" to the SAME value as "top" (it passes
                     {{0, 0, XBFONT_CENTER_Y, 0}} as {{default, top, center,
                     bottom}}), and CGUILabelControl has no GetHeight() to
                     shrink the box to its text - only GetWidth(), which is
                     what <width>auto</width> uses. So the text hangs from
                     the TOP however the box is sized, and a one-line title
                     would leave a line of empty space above the meta row.

                     The box is therefore positioned for the TWO-line case
                     (-64 + 170 = 106 = id 4002's posy, so its bottom edge
                     IS the meta line's top edge), and the animation below
                     slides it down exactly one line when the title only
                     needs one. hero_title_lines comes from Python, which
                     also inserts the break - see textmetrics.hero_title_wrap.

                     If 4002's posy moves, this posy has to follow it.

                     Verified against the live capture: the app leaves 27px
                     between the title's last line and the meta ink. -->
                <control type="label" id="4001">
                    <posy>-64</posy>
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
                <control type="label" id="4002">
                    <posy>106</posy>
                    <width>1000</width>
                    <height>24</height>
                    <font>tofa_font_body</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(hero_meta_line)]</label>
                </control>
                <control type="label" id="4003">
                    <posy>148</posy>
                    <width>1000</width>
                    <height>22</height>
                    <font>tofa_font_micro</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(hero_ratings_line)]</label>
                </control>
                <control type="textbox" id="4004">
                    <posy>184</posy>
                    <width>820</width>
                    <height>90</height>
                    <font>tofa_font_body</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(hero_synopsis)]</label>
                    <!-- ONLY WHILE A ROW HAS FOCUS. Kodi takes a condition here,
                         not just a boolean, so this needs no second copy. The hero
                         mirrors whichever card is focused, so when focus is up on
                         the nav bar it is describing something the viewer is not
                         looking at, and a synopsis crawling by itself on an
                         untouched Home is motion nobody asked for.

                         HOUSE RULE (2026-08-15): a screen may run at most ONE
                         vertical marquee, for a long synopsis, and at most ONE
                         horizontal marquee, for the focused card or option
                         title. Toasts are the exception. The two axes are the
                         point: a synopsis scrolling up while the title under
                         the cursor scrolls sideways stays readable, where two
                         of either does not. This control is Home's vertical
                         one; the horizontal one is the focused card title in
                         fragments.py, gated on Control.HasFocus of the same
                         list. They run together, and that is intended.

                         The rule used to read "only the focused item
                         marquees", which does not survive contact: the hero is
                         never itself focused, so that reading would silence it
                         entirely. -->
                    <autoscroll delay="2000" time="4000" repeat="6000">{hero_scroll_when}</autoscroll>
                </control>
            </control>

            <!-- Vertically-scrolling rows region; hero block above stays
                 fixed. grouplist auto-scrolls to keep the focused group
                 within its declared height, clipping the rest. -->
            <!-- Height IS one row, as the token, so the two can't drift:
                 it was a hand-typed 535 against a ROW_H of 536, leaving each
                 shelf a pixel taller than the viewport meant to hold it. The
                 extra pixel falls past the screen edge, so this is a
                 consistency fix rather than a visible one. -->
            <control type="grouplist" id="4090">
                <posx>{HOME_LEFT}</posx>
                <posy>{HOME_ROWS_Y}</posy>
                <width>{HOME_ROWS_W}</width>
                <height>{HOME_ROWS_H}</height>
                <orientation>vertical</orientation>
                <itemgap>0</itemgap>
                <scrolltime>{SCROLLTIME}</scrolltime>

                <!-- Holds the rows down at the hero geometry. Hidden when
                     "Featured spotlight" is off, and a grouplist lays out
                     only its VISIBLE children, so every row moves up by this
                     much and the second one comes into view. That is the
                     whole mechanism: no control is resized, because a
                     grouplist's height cannot be. -->
                <control type="group" id="4085">
                    <visible>String.IsEmpty(Window.Property(home_hero_off))</visible>
                    <width>{HOME_ROWS_W}</width>
                    <height>{HOME_HERO_SPACER_H}</height>
                </control>

            <!-- Server-driven rows: up to 9 slots (see
                 resources/lib/home_rows.py). Header text comes from a
                 Window.Property set per slot; the whole group hides via
                 <visible> when that property is empty. -->
{home_rows}
            </control>
        </control>

        <!-- ============================================================
             BROWSE SECTION (control ids 6000-6299)
             ============================================================ -->
        <control type="group" id="3900">
            <posx>0</posx>
            <posy>0</posy>
            <visible>String.IsEqual(Window.Property(active_section),browse)</visible>

            <!-- flat canvas wash so the grid reads on #030b10 -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <colordiffuse>{CANVAS}</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <!-- Top nav bar scrim -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCRIM_H}</height>
                <colordiffuse>{SCRIM_TOP}</colordiffuse>
                <texture>fade-top.png</texture>
            </control>

            <!-- Sidebar: eyebrow + glass rows. Two separate list controls
                 (fixed sources 6000, per-library rows 6010) with a real
                 empty gap between them plus a hairline divider: Kodi's
                 <list> control can't vary itemheight per item, so a real
                 gap needs a second list rather than a per-item property
                 on one shared list. -->
            <control type="label">
                <posx>70</posx>
                <posy>190</posy>
                <width>268</width>
                <height>24</height>
                <font>tofa_font_eyebrow</font>
                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                <label>LIBRARY</label>
            </control>

            <control type="list" id="6000">
                <posx>68</posx>
                <posy>222</posy>
                <width>300</width>
                <height>240</height>
                <onup>3000</onup>
                <onleft>6000</onleft>
                <!-- Right jumps straight to the grid, not the filter row:
                     the filter row can be hidden, and Kodi can't focus an
                     invisible control. Still reachable via Down from the
                     nav bar or Up from the grid. -->
                <onright>6200</onright>
                <ondown>6010</ondown>
                <orientation>vertical</orientation>
                <itemwidth>300</itemwidth>
                <itemheight>60</itemheight>
{sidebar_item}

{sidebar_focused}
            </control>

            <!-- Static divider; the real gap comes from the two list
                 controls' own posy, not from this line. -->
            <control type="image">
                <posx>84</posx>
                <posy>476</posy>
                <width>268</width>
                <height>1</height>
                <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <control type="list" id="6010">
                <posx>68</posx>
                <posy>491</posy>
                <width>300</width>
                <height>560</height>
                <onup>6000</onup>
                <onleft>6010</onleft>
                <onright>6200</onright>
                <ondown>6010</ondown>
                <orientation>vertical</orientation>
                <itemwidth>300</itemwidth>
                <itemheight>60</itemheight>
{sidebar_lib_item}

{sidebar_lib_focused}
            </control>

            <!-- Collection drill-down heading. The real app keeps the
                 viewer INSIDE Browse when a collection is opened: same
                 sidebar, same grid, plus a title above the toolbar and a
                 way back to the collection list. Both are hidden until a
                 collection is open. -->
            <control type="label" id="6250">
                <visible>!String.IsEmpty(Window.Property(browse_heading))</visible>
                <posx>440</posx>
                <!-- MEASURED off the real app's own collection screen: its
                     heading ink is 29 tall and sits at y=197, where
                     tofa_font_heading (57) gave us 46 and read far too big.
                     section_title is the closest tier and is literally the
                     section-header font, which is what this is. posy is
                     back-solved from the ink top, since a Kodi label's box
                     sits above the cap by the font's own ascender slack. -->
                <posy>184</posy>
                <width>1400</width>
                <height>52</height>
                <font>tofa_font_section_title</font>
                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                <label>$INFO[Window.Property(browse_heading)]</label>
            </control>

            <!-- glass_pill() emits a group with an x but no y; its vertical
                 position comes from whatever encloses it, exactly as the
                 Detail action row does. Sits between the heading and the
                 grid at 299. -->
            <!-- On the HEADING's row, not a row of its own. Both reference
                 apps fit the title and one control row; their back pill
                 sits inline with Sort, which our four full-width buttons
                 leave no space for. Putting it beside the title costs no
                 extra row, so the grid still starts where theirs does. -->
            <!-- The fourth toolbar slot, freed by folding Quality into the
                 Filter dialog. Both reference apps put every control on one
                 row; ours could not until that button went away. -->
            <control type="group">
                <posy>261</posy>
{collection_back}
            </control>

            <!-- Sort/Filter/Quality/Genre: 4 evenly-spaced wide buttons
                 spanning the full row width, each showing its current
                 value via a *_label ListItem property kept in sync by
                 main.py. Single-item lists, not plain buttons, for the
                 focus-ring + controlID-for-onClick behavior that needs. -->
            <control type="list" id="6110">
                <visible>!String.IsEmpty(Window.Property(browse_filterbar))</visible>
                <posx>440</posx>
                <posy>190</posy>
                <width>346</width>
                <height>62</height>
                <onup>3000</onup>
                <onleft>6000</onleft>
                <onright>6120</onright>
                <ondown>6200</ondown>
                <orientation>horizontal</orientation>
                <itemwidth>346</itemwidth>
                <itemheight>62</itemheight>
{sort_item}

{sort_focused}
            </control>

            <!-- Filter: accent-filled when a non-default Watch Status/Year
                 is active (ListItem property "active", set in
                 _browse_filter_clicked()), glass otherwise. -->
            <control type="list" id="6120">
                <visible>!String.IsEmpty(Window.Property(browse_filterbar))</visible>
                <posx>802</posx>
                <posy>190</posy>
                <width>346</width>
                <height>62</height>
                <onup>3000</onup>
                <onleft>6110</onleft>
                <onright>6100</onright>
                <ondown>6200</ondown>
                <orientation>horizontal</orientation>
                <itemwidth>346</itemwidth>
                <itemheight>62</itemheight>
{filter_item}

{filter_focused}
            </control>

            <!-- Quality: accent-filled when a non-"Any" value is active
                 (ListItem property "active", set in
                 _browse_quality_clicked()), glass otherwise. -->
            <control type="list" id="6100">
                <visible>!String.IsEmpty(Window.Property(browse_filterbar))</visible>
                <posx>1164</posx>
                <posy>190</posy>
                <width>346</width>
                <height>62</height>
                <onup>3000</onup>
                <onleft>6120</onleft>
                <onright>6100</onright>
                <ondown>6200</ondown>
                <orientation>horizontal</orientation>
                <itemwidth>346</itemwidth>
                <itemheight>62</itemheight>
{genre_item}

{genre_focused}
            </control>

            <!-- Main 5-column poster grid. -->
            <!-- 7.5's collections index is a LANDSCAPE grid, so it cannot
                 share the poster panel: a Kodi panel has one itemwidth and
                 one itemheight. Two panels, one visible at a time. -->
            <!-- Pulled back by GLOW_PAD on both axes, and grown by the same
                 on the height, because collection_card()'s content group is
                 offset by GLOW_PAD inside its cell so the focus halo has
                 somewhere to bleed (a panel clips each item to its cell, and
                 all of this cell's slack is on its right and bottom). Net
                 effect on the grid is zero: the first tile still lands on
                 440,299 and the pitch is COLLECTION_CELL_W/H either way. -->
            <control type="panel" id="6210">
                <visible>!String.IsEmpty(Window.Property(browse_collections))</visible>
                <posx>430</posx>
                <posy>289</posy>
                <width>{COLLECTION_GRID_W}</width>
                <height>791</height>
                <onleft>6000</onleft>
                <onup>6100</onup>
                <orientation>vertical</orientation>
                <itemwidth>{COLLECTION_CELL_W}</itemwidth>
                <itemheight>{COLLECTION_CELL_H}</itemheight>
                <scrolltime>{SCROLLTIME}</scrolltime>

{collection_item}

{collection_focused}
            </control>

            <control type="panel" id="6200">
                <visible>String.IsEmpty(Window.Property(browse_collections))</visible>
                <!-- Shifted left by HPAD, not sat at 440: poster_card()
                     insets the poster art HPAD within its own cell, so this
                     brings the visible poster art back in line with the nav
                     bar/Sort pill's shared 440 edge. Both derived, so the
                     grid follows CELL_W instead of silently going out of
                     register when the card changes width. -->
                <posx>{BROWSE_GRID_X}</posx>
                <posy>299</posy>
                <width>{BROWSE_GRID_W}</width>
                <height>781</height>
                <!-- onup targets the whole panel regardless of which
                     column is focused; 6110 (Sort) is the row's leftmost
                     control. -->
                <onup>6110</onup>
                <onleft>6000</onleft>
                <!-- Right off the LAST column reaches the A-Z rail; inside a
                     row Kodi moves the cursor and never consults this. Same
                     way the Android app is reached, measured on the box.

                     RE-AIMED at runtime by _browse_fill_alpha_rail(): the
                     rail is not on every source, and a static onright cannot
                     know that, so on a library without one this would point
                     Right at a hidden control. -->
                <onright>6220</onright>
                <ondown>6200</ondown>
                <orientation>vertical</orientation>
                <itemwidth>{CELL_W}</itemwidth>
                <!-- Not shifted by -HPAD like Home/Discover/Search: this
                     5-column grid sits flush against the sidebar
                     (itemwidth*5 == panel width exactly), so shifting it
                     left to align the first column would crowd it. -->
                <itemheight>{BROWSE_CELL_H}</itemheight>
                <scrolltime>{SCROLLTIME}</scrolltime>
{grid_item}

{grid_focused}
            </control>

            <!-- A-Z filter rail, down the right margin. "All" first, "#"
                 last, which is both the Android app's order and the
                 server's own bucket name (/api/v1/media?letter=#).

                 Shown only where it earns its place, which is the window's
                 call, not the skin's: see _browse_alpha_wanted(). That
                 subsumes the collections case; a collection is a set, and
                 the letter filter applies to titles.

                 onright is deliberately absent so build.py's _stop_wraps
                 fills it: this is the rightmost control on the screen. -->
            <control type="list" id="6220">
                <visible>String.IsEqual(Window.Property(browse_alpha),1)</visible>
                <posx>{ALPHA_RAIL_X}</posx>
                <posy>{ALPHA_RAIL_Y}</posy>
                <width>{ALPHA_PILL_W}</width>
                <height>{ALPHA_RAIL_H}</height>
                <onup>6100</onup>
                <onleft>6200</onleft>
                <orientation>vertical</orientation>
                <itemwidth>{ALPHA_PILL_W}</itemwidth>
                <itemheight>{ALPHA_PITCH}</itemheight>
                <scrolltime>{SCROLLTIME}</scrolltime>
{alpha_item}

{alpha_focused}
            </control>
        </control>

        <!-- ============================================================
             DISCOVER SECTION (control ids 6300-6699). Row-title
             properties are discover_rowN_title, not rowN_title, since
             that name is already Home's and Window.Property() is shared
             window-wide.
             ============================================================ -->
        <control type="group" id="3910">
            <posx>0</posx>
            <posy>0</posy>
            <visible>String.IsEqual(Window.Property(active_section),discover)</visible>

            <!-- Flat canvas wash (no hero billboard on Discover). -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <colordiffuse>{CANVAS}</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <!-- Top nav bar scrim -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCRIM_H}</height>
                <colordiffuse>{SCRIM_TOP}</colordiffuse>
                <texture>fade-top.png</texture>
            </control>

            <!-- No screen title: the nav bar already marks the section, and
                 the real app opens straight onto its tab pills. -->

            <!-- Tab pills (Now / Acclaimed / Genres / Decades). The server
                 sends all 32 shelves flat; these group them by the shelf's
                 own `kind`, matching the real app. See home_rows.py's
                 DISCOVER_TAB_KINDS for the mapping and why "Now" holds
                 three kinds. -->
{discover_tabs}

            <!-- grouplist, not a plain group with conditional slide
                 animations: those don't auto-scroll, see Home's own row
                 region. posy 252, not 267: the reference's first row title
                 has its INK at ~265, and a label's ink sits ~13px below its
                 control's top (font ascent). 267 was measured off the ink and
                 used as the control position, which pushed the whole rows
                 region (and every caption under it) 16px low. -->
            <control type="grouplist" id="6390">
                <posx>{DISCOVER_LEFT}</posx>
                <posy>252</posy>
                <width>{DISCOVER_ROWS_W}</width>
                <height>{DISCOVER_ROWS_H}</height>
                <orientation>vertical</orientation>
                <itemgap>0</itemgap>
                <scrolltime>{SCROLLTIME}</scrolltime>

            <!-- ============================ ROW 0 ============================ -->
{discover_rows}
            </control>
        </control>

        <!-- ============================================================
             SEARCH SECTION: matches the real Apple TV app's Grid keyboard
             layout (6 columns keeps worst-case a-to-z at ~5-6 moves) and
             its richer results (Top Result + Movies + Shows + Actors +
             Discover). Query text lives in a real Kodi edit control
             (QUERY_EDIT_ID), not a plain label, for native
             on-screen-keyboard-on-Select and physical-keyboard typing for
             free (see MainWindow.onAction's _search_sync_from_edit()).
             ============================================================ -->
        <control type="group" id="3920">
            <posx>0</posx>
            <posy>0</posy>
            <visible>String.IsEqual(Window.Property(active_section),search)</visible>

            <!-- Canvas base wash 0x101010: a neutral dark grey, not this
                 add-on's usual near-black-navy 0x030B10 elsewhere. Search
                 reads more neutral/grey on the real app. -->
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <colordiffuse>0xFF101010</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCRIM_H}</height>
                <colordiffuse>0xC8101010</colordiffuse>
                <texture>fade-top.png</texture>
            </control>

            <!-- Results-pane backdrop: a subtly blue-tinted panel behind
                 the whole right column, plus a thin rule above it.
                 Independent of the results GROUP below (own absolute
                 position) since it's a full-bleed backdrop. -->
            <control type="image">
                <posx>590</posx>
                <posy>261</posy>
                <width>1248</width>
                <height>1</height>
                <colordiffuse>0xFF525252</colordiffuse>
                <texture>white-square.png</texture>
            </control>
            <control type="image">
                <posx>590</posx>
                <posy>290</posy>
                <width>1330</width>
                <height>790</height>
                <colordiffuse>{SURFACE_PLACEHOLDER}</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <!-- ========================= LEFT: KEYBOARD PANE ========================= -->
            <control type="group" id="6710">
                <!-- posx 80, not the shared CONTENT_LEFT: Search's
                     left pane sits further left on the real Apple TV app,
                     opening up more breathing room before the results
                     column starts. -->
                <posx>80</posx>
                <posy>150</posy>

                <!-- texturefocus/texturenofocus are explicitly EMPTY, not
                     just omitted: Kodi's engine-level default edit-control
                     style otherwise still applies a button-shaped focus
                     texture even without one set. Icon is the same Lucide
                     font every other icon in this add-on uses
                     (icon_glyphs.SEARCH), not a raster texture. -->
                <control type="label">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>60</width>
                    <height>60</height>
                    <align>center</align>
                    <aligny>center</aligny>
                    <font>tofa_font_icons_56</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>&#xE151;</label>
                </control>
                <control type="edit" id="6701">
                    <posx>72</posx>
                    <posy>0</posy>
                    <width>500</width>
                    <height>60</height>
                    <aligny>center</aligny>
                    <font>tofa_font_row_title</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <hinttext>Search</hinttext>
                    <texturefocus></texturefocus>
                    <texturenofocus></texturenofocus>
                    <onup>3000</onup>
                    <ondown>6702</ondown>
                    <onleft>6701</onleft>
                    <onright>6805</onright>
                </control>

                <!-- abc / 123 tab switcher; no globe icon since this add-on
                     has no multi-language support. Track spans the full
                     keyboard width (444), matching the letters grid
                     below.

                     Measured off the real Apple TV app: the track is ONE
                     flat fill end to end (SURFACE_TRACK), and the selected
                     mode is signalled by label colour alone; there is no
                     brighter pill behind the active segment. Kodi's own
                     d-pad focus is a separate thing and still gets the solid
                     white tile below, matching the letter keys. -->
                <control type="image">
                    <posx>0</posx>
                    <posy>96</posy>
                    <width>444</width>
                    <height>60</height>
                    <colordiffuse>{SURFACE_TRACK}</colordiffuse>
                    <texture border="30">white-square-rounded.png</texture>
                </control>
                <control type="list" id="6702">
                    <posx>0</posx>
                    <posy>96</posy>
                    <width>444</width>
                    <height>60</height>
                    <onup>6701</onup>
                    <onleft>6702</onleft>
                    <!-- The results pane, same as the letter grid (6700), the
                         numpad (6703) and the space row (6704) below. This
                         used to point back at 6702, so Right on "123" wrapped
                         to "abc" and there was no way out of the switcher
                         except Up or Down. Right steps abc->123 inside the
                         list first, so only the last tab ever fires this.
                         Retargeted at runtime by
                         windows/main.py:_search_wire_right_target(), which
                         swaps 6805 for the Recent Searches list while idle. -->
                    <onright>6805</onright>
                    <orientation>horizontal</orientation>
                    <itemwidth>222</itemwidth>
                    <itemheight>60</itemheight>
                    <scrolltime>120</scrolltime>

                    <!-- Non-current item. The active keyboard mode
                         (ListItem.Property(is_active)) reads as primary-tier
                         text on the shared track; inactive drops to
                         secondary. No fill either way. -->
                    <itemlayout width="222" height="60">
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_row_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>!String.IsEmpty(ListItem.Property(is_active))</visible>
                        </control>
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_row_title</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>String.IsEmpty(ListItem.Property(is_active))</visible>
                        </control>
                    </itemlayout>

                    <!-- Kodi's <list> renders focusedlayout for the
                         current item unconditionally, regardless of
                         whether the list control itself holds real input
                         focus, so each state is explicitly gated on
                         Control.HasFocus(6702) (same pattern as the Genre
                         pill, list 6100). When merely selected but not
                         focused, this mirrors itemlayout's own is_active
                         tint so it carries no misleading "focused"
                         signal. -->
                    <focusedlayout width="222" height="60">
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_row_title</font>
                            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>!Control.HasFocus(6702) + !String.IsEmpty(ListItem.Property(is_active))</visible>
                        </control>
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_row_title</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>!Control.HasFocus(6702) + String.IsEmpty(ListItem.Property(is_active))</visible>
                        </control>
                        <control type="image">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <colordiffuse>white</colordiffuse>
                            <texture border="26">white-square-rounded.png</texture>
                            <visible>Control.HasFocus(6702)</visible>
                        </control>
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>214</width>
                            <height>52</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_row_title</font>
                            <textcolor>{ON_LIGHT_TEXT}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>Control.HasFocus(6702)</visible>
                        </control>
                    </focusedlayout>
                </control>

                <!-- Letters grid (a-z, 6 cols x 5 rows), "abc" tab. -->
                <control type="panel" id="6700">
                    <posx>0</posx>
                    <posy>186</posy>
                    <width>444</width>
                    <height>370</height>
                    <visible>String.IsEqual(Window.Property(keyboard_mode),abc)</visible>
                    <onup>6702</onup>
                    <onleft>6700</onleft>
                    <onright>6805</onright>
                    <ondown>6704</ondown>
                    <orientation>vertical</orientation>
                    <itemwidth>74</itemwidth>
                    <itemheight>74</itemheight>
                    <scrolltime>120</scrolltime>

                    <itemlayout width="74" height="74">
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>74</width>
                            <height>74</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_section_title</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </itemlayout>

                    <focusedlayout width="74" height="74">
                        <control type="image">
                            <posx>7</posx>
                            <posy>7</posy>
                            <width>60</width>
                            <height>60</height>
                            <colordiffuse>white</colordiffuse>
                            <texture border="14">white-square-rounded.png</texture>
                            <animation effect="zoom" start="100" end="106" center="37,37" time="120" tween="cubic" easing="out">Focus</animation>
                        </control>
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>74</width>
                            <height>74</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_section_title</font>
                            <textcolor>{ON_LIGHT_TEXT}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </focusedlayout>
                </control>

                <!-- Digits + punctuation grid, "123" tab: same 6-col
                     shape and key visual language as the letters grid
                     (see _search_digit_defs()). -->
                <control type="panel" id="6703">
                    <posx>0</posx>
                    <posy>186</posy>
                    <width>444</width>
                    <height>518</height>
                    <visible>String.IsEqual(Window.Property(keyboard_mode),123)</visible>
                    <onup>6702</onup>
                    <onleft>6703</onleft>
                    <onright>6805</onright>
                    <ondown>6704</ondown>
                    <orientation>vertical</orientation>
                    <itemwidth>74</itemwidth>
                    <itemheight>74</itemheight>
                    <scrolltime>120</scrolltime>

                    <itemlayout width="74" height="74">
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>74</width>
                            <height>74</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_section_title</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </itemlayout>

                    <focusedlayout width="74" height="74">
                        <control type="image">
                            <posx>7</posx>
                            <posy>7</posy>
                            <width>60</width>
                            <height>60</height>
                            <colordiffuse>white</colordiffuse>
                            <texture border="14">white-square-rounded.png</texture>
                            <animation effect="zoom" start="100" end="106" center="37,37" time="120" tween="cubic" easing="out">Focus</animation>
                        </control>
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>74</width>
                            <height>74</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_section_title</font>
                            <textcolor>{ON_LIGHT_TEXT}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </focusedlayout>
                </control>

                <!-- SPACE / backspace / CLEAR: always visible under
                     whichever grid is active (see _search_spacerow_defs()).
                     Icon item's label text is empty and its icon property
                     carries the glyph instead (or vice versa); one
                     itemlayout handles both shapes. -->
                <control type="list" id="6704">
                    <posx>0</posx>
                    <posy>724</posy>
                    <width>444</width>
                    <height>56</height>
                    <onup>6700</onup>
                    <onleft>6704</onleft>
                    <onright>6805</onright>
                    <ondown>6704</ondown>
                    <orientation>horizontal</orientation>
                    <itemwidth>148</itemwidth>
                    <itemheight>56</itemheight>
                    <scrolltime>120</scrolltime>

                    <itemlayout width="148" height="56">
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>148</width>
                            <height>56</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_eyebrow</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>148</width>
                            <height>56</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_29</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(icon)]</label>
                            <visible>!String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                    </itemlayout>

                    <!-- Control.HasFocus(6704)-gated, same reasoning as
                         the tab row's list 6702 above. Not-focused state
                         mirrors itemlayout exactly (plain, no pill) since
                         these 3 buttons have no separate "active" concept
                         the way abc/123 do. -->
                    <focusedlayout width="148" height="56">
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>148</width>
                            <height>56</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_eyebrow</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>!Control.HasFocus(6704) + String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                        <control type="label">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>148</width>
                            <height>56</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_29</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[ListItem.Property(icon)]</label>
                            <visible>!Control.HasFocus(6704) + !String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                        <control type="image">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>140</width>
                            <height>48</height>
                            <colordiffuse>white</colordiffuse>
                            <texture border="24">white-square-rounded.png</texture>
                            <visible>Control.HasFocus(6704)</visible>
                        </control>
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>140</width>
                            <height>48</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_eyebrow</font>
                            <textcolor>{ON_LIGHT_TEXT}</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                            <visible>Control.HasFocus(6704) + String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                        <control type="label">
                            <posx>4</posx>
                            <posy>4</posy>
                            <width>140</width>
                            <height>48</height>
                            <align>center</align>
                            <aligny>center</aligny>
                            <font>tofa_font_icons_29</font>
                            <textcolor>{ON_LIGHT_TEXT}</textcolor>
                            <label>$INFO[ListItem.Property(icon)]</label>
                            <visible>Control.HasFocus(6704) + !String.IsEmpty(ListItem.Property(icon))</visible>
                        </control>
                    </focusedlayout>
                </control>
            </control>

            <!-- ========================= RIGHT: RESULTS PANE ========================= -->
            <control type="group" id="6800">
                <posx>{SEARCH_COLUMN_X}</posx>
                <posy>324</posy>

                <control type="label">
                    <posx>0</posx>
                    <posy>{SEARCH_CAPTION_Y}</posy>
                    <width>1100</width>
                    <height>34</height>
                    <font>{FONT_RESULTS_CAPTION}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(results_caption)]</label>
                    <!-- Hidden on the no-results state: the empty state
                         below already names the query, and the real Apple
                         TV app shows one or the other, never both. -->
                    <visible>!String.IsEmpty(Window.Property(query)) + !String.IsEqual(Window.Property(has_results),0)</visible>
                </control>

                <!-- Idle / first-run empty state: no history for this
                     profile yet. No separate "Search" label under the
                     icon since it's redundant with the highlighted Search
                     nav tab above and the subtitle below. -->
                <control type="group">
                    <posx>0</posx>
                    <posy>250</posy>
                    <visible>String.IsEmpty(Window.Property(query)) + String.IsEqual(Window.Property(has_history),0)</visible>
                    <control type="label">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>1000</width>
                        <height>96</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_64</font>
                        <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                        <label>&#xE151;</label>
                    </control>
                    <control type="label">
                        <posx>0</posx>
                        <posy>124</posy>
                        <width>1000</width>
                        <height>30</height>
                        <align>center</align>
                        <font>tofa_font_row_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>Search movies, shows and people</label>
                    </control>
                </control>

                <!-- Recent Searches: local-only (no server endpoint, see
                     search_history.py). A simple clickable list of past
                     queries, same row language as Browse's sidebar (fill
                     tint on select, accent icon). Clicking an entry
                     re-runs that search. -->
                <control type="group">
                    <posx>0</posx>
                    <posy>10</posy>
                    <visible>String.IsEmpty(Window.Property(query)) + !String.IsEqual(Window.Property(has_history),0)</visible>
                    <control type="label">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>600</width>
                        <height>34</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>Recent Searches</label>
                    </control>
                    <control type="list" id="6860">
                        <posx>0</posx>
                        <posy>50</posy>
                        <width>600</width>
                        <!-- EXACTLY search_history.MAX_ENTRIES * itemheight.
                             A Kodi list draws floor(height/itemheight) whole
                             rows and then CLIPS whatever is left over, so the
                             old 500 showed 8 rows plus a sliced 9th. 10 x 58
                             is 580, and the list starts at an absolute y of
                             384 (group 6800's 324 + this group's 10 + 50), so
                             it still ends 116px clear of the screen bottom. -->
                        <height>{SEARCH_HISTORY_H}</height>
                        <!-- Nav bar, not itself: a self-reference here read
                             as "Up does nothing" and stranded the column. -->
                        <onup>3000</onup>
                        <ondown>6860</ondown>
                        <onleft>6701</onleft>
                        <onright>6860</onright>
                        <orientation>vertical</orientation>
                        <itemwidth>600</itemwidth>
                        <itemheight>58</itemheight>
                        <scrolltime>150</scrolltime>

                        <itemlayout width="600" height="58">
                            <control type="label">
                                <posx>4</posx>
                                <posy>0</posy>
                                <width>36</width>
                                <height>58</height>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_24</font>
                                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                                <label>$INFO[ListItem.Property(icon)]</label>
                            </control>
                            <control type="label">
                                <posx>48</posx>
                                <posy>0</posy>
                                <width>548</width>
                                <height>58</height>
                                <aligny>center</aligny>
                                <font>tofa_font_row_title</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                        </itemlayout>

                        <focusedlayout width="600" height="58">
                            <!-- Same Control.HasFocus gating as the tab
                                 row/spacerow above. -->
                            <control type="image">
                                <visible>Control.HasFocus(6860)</visible>
                                <posx>0</posx>
                                <posy>2</posy>
                                <width>600</width>
                                <height>54</height>
                                <colordiffuse>{SURFACE_RAISED}</colordiffuse>
                                <texture border="16">white-square-rounded.png</texture>
                            </control>
                            <control type="label">
                                <posx>4</posx>
                                <posy>0</posy>
                                <width>36</width>
                                <height>58</height>
                                <aligny>center</aligny>
                                <font>tofa_font_icons_24</font>
                                <textcolor>$INFO[Window.Property(accent_color)]</textcolor>
                                <label>$INFO[ListItem.Property(icon)]</label>
                            </control>
                            <control type="label">
                                <posx>48</posx>
                                <posy>0</posy>
                                <width>548</width>
                                <height>58</height>
                                <aligny>center</aligny>
                                <font>tofa_font_row_title</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                        </focusedlayout>
                    </control>
                </control>

                <!-- No-results state, modelled on the real Apple TV app
                     (captured 2026-08-01): a magnifier over ONE line that
                     carries the query itself, centred in the results pane.

                     It used to be a 57px "No results" headline in a 40px
                     box with a second line 48px below it, which is not
                     enough room for the font and drew the subtitle
                     straight through the headline. It was also centred on
                     THIS group, whose origin (771) is the content column
                     rather than the pane, leaving it ~59px right of
                     centre. Both fixed by centring on the pane's own rule
                     (screen 590..1838, so 443 in local coordinates) and
                     giving each line a box its font actually fits in. -->
                <control type="group">
                    <posx>0</posx>
                    <posy>0</posy>
                    <visible>!String.IsEmpty(Window.Property(query)) + String.IsEqual(Window.Property(has_results),0)</visible>
                    <control type="label">
                        <posx>143</posx>
                        <posy>90</posy>
                        <width>600</width>
                        <height>70</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_icons_56</font>
                        <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                        <label>&#xE151;</label>
                    </control>
                    <control type="label">
                        <posx>-107</posx>
                        <posy>181</posy>
                        <width>1100</width>
                        <height>52</height>
                        <align>center</align>
                        <aligny>center</aligny>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>$INFO[Window.Property(no_results_caption)]</label>
                    </control>
                </control>

                <!-- grouplist height (698) is computed from this group's
                     ABSOLUTE screen posy (382 = parent group 6800's posy
                     324 + this control's local posy 58), not just
                     1080-58: the parent's own offset must be subtracted
                     too, or Kodi's keep-focused-item-in-view scroll math
                     under-scrolls and cuts off lower rows. -->
                <!-- posx=-20/width=1109 (not 0/1089): a grouplist clips
                     its children to its own declared bounds. Every child
                     list below sits at posx=-20 or -10 internally
                     (matching poster_card()'s HPAD=20 inset, same "-20
                     cancels HPAD" convention Browse's grid panel uses at
                     the top level), extended 20px further so each card's
                     focus glow (bleeding a further -10px beyond that)
                     isn't clipped by this grouplist's own clip region. -->
                <control type="grouplist" id="6810">
                    <posx>-20</posx>
                    <posy>{SEARCH_SHELVES_Y}</posy>
                    <width>{SEARCH_SHELF_CLIP_W}</width>
                    <height>{SEARCH_SHELVES_H}</height>
                    <orientation>vertical</orientation>
                    <!-- 0, NOT the 32 this used to carry. Each shelf group
                         below now includes SEARCH_SHELF_TRAIL in its own
                         height, so the gap BETWEEN shelves is unchanged (still
                         the deliberately-roomier 32 Search uses, since its
                         shelves sit under a much bigger Top Result block) and
                         the LAST shelf finally gets the same trailing margin.
                         An itemgap sits between items and gives the last one
                         nothing; see ROW_BLOCK_H in tokens.py, which is the
                         same fix Home and Discover already had. -->
                    <itemgap>0</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                <!-- Top Result: single-item list (same "always exactly
                     one row" pattern as Browse's Sort/Filter/Quality/Genre
                     pills), focusable/clickable like a normal card. The
                     item/focused placeholders below are generated by
                     fragments.py:top_result_card(), which calls the same
                     poster_visual() every other poster in the app uses,
                     not hand-copied XML. -->
                <control type="group" id="6806">
                    <height>{SEARCH_TOP_RESULT_BLOCK_H}</height>
                    <visible>!String.IsEmpty(Window.Property(query)) + !String.IsEmpty(Window.Property(has_top_result))</visible>
                    <!-- posx=0, same as every other poster row's own list
                         inside grouplist 6810 (Movies 6820, Shows 6830,
                         Search-Discover 6850): the grouplist's own posx=-20
                         already provides the room the itemlayout's HPAD
                         inset and its glow need. -->
                    <control type="list" id="6805">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>{SEARCH_SHELF_W}</width>
                        <height>{TOP_RESULT_CELL_H}</height>
                        <!-- The nav bar. This used to name 6810, the
                             grouplist this list is INSIDE, which Kodi
                             cannot act on: Up from the Top Result did
                             nothing at all. -->
                        <onup>3000</onup>
                        <ondown>6820</ondown>
                        <onleft>6701</onleft>
                        <onright>6805</onright>
                        <orientation>vertical</orientation>
                        <itemwidth>{TOP_RESULT_CELL_W}</itemwidth>
                        <itemheight>{TOP_RESULT_CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{top_result_item}

{top_result_focused}
                    </control>
                    <!-- The text block is STATIC and lives here, beside the
                         list rather than inside its item layout, because Kodi
                         ignores <wrapmultiline> on a label in a list ITEM
                         layout and the synopsis has to wrap to three lines.
                         Its coordinates are the item layout's own: list 6805
                         sits at this group's (0,0), so the two share an
                         origin. Driven by Window.Property(top_result_*), set
                         in windows/main.py:_search_fill_top_result(). -->
{top_result_text}
                </control>

                <control type="group" id="6821">
                    <height>{SEARCH_SHELF_BLOCK_H}</height>
                    <visible>!String.IsEqual(Window.Property(movies_count),0)</visible>
                    <!-- posx=22, not 2: this label lives inside grouplist
                         6810, same as list 6820 below it, so it needs the
                         same +20 compensation for the grouplist's own
                         posx=-20. font tofa_font_section_title (39pt), not
                         font20_title: matches Home's row-title convention
                         (see group 4100 above) and reads clearly bigger
                         than the 24pt poster titles below it. -->
                    <control type="label">
                        <posx>22</posx>
                        <posy>0</posy>
                        <width>600</width>
                        <height>34</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Movies</label>
                    </control>
                    <control type="list" id="6820">
                        <posx>0</posx>
                        <posy>{SEARCH_SECTION_BAND}</posy>
                        <width>{SEARCH_SHELF_W}</width>
                        <height>{CELL_H}</height>
                        <onup>6805</onup>
                        <ondown>6830</ondown>
                        <onleft>6701</onleft>
                        <onright>6820</onright>
                        <orientation>horizontal</orientation>
                        <itemwidth>{CELL_W}</itemwidth>
                        <itemheight>{CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{movies_item}

{movies_focused}
                    </control>
                </control>

                <control type="group" id="6831">
                    <height>{SEARCH_SHELF_BLOCK_H}</height>
                    <visible>!String.IsEqual(Window.Property(shows_count),0)</visible>
                    <control type="label">
                        <posx>22</posx>
                        <posy>0</posy>
                        <width>600</width>
                        <height>34</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Shows</label>
                    </control>
                    <control type="list" id="6830">
                        <posx>0</posx>
                        <posy>{SEARCH_SECTION_BAND}</posy>
                        <width>{SEARCH_SHELF_W}</width>
                        <height>{CELL_H}</height>
                        <onup>6820</onup>
                        <ondown>6840</ondown>
                        <onleft>6701</onleft>
                        <onright>6830</onright>
                        <orientation>horizontal</orientation>
                        <itemwidth>{CELL_W}</itemwidth>
                        <itemheight>{CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{shows_item}

{shows_focused}
                    </control>
                </control>

                <!-- Actors shelf: circular photo (real profile_url when
                     the server has one, else a placeholder circle + a
                     generic person icon, same diffuse="circle.png" mask
                     technique as the "Who's watching?" profile picker's
                     avatars). Clicking an actor re-runs the same search
                     using their exact name: no actor-filmography endpoint
                     exists server-side to open a dedicated page. -->
                <control type="group" id="6841">
                    <height>{SEARCH_ACTORS_BLOCK_H}</height>
                    <visible>!String.IsEqual(Window.Property(actors_count),0)</visible>
                    <control type="label">
                        <posx>22</posx>
                        <posy>0</posy>
                        <width>600</width>
                        <height>34</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Actors</label>
                    </control>
                    <control type="list" id="6840">
                        <posx>10</posx>
                        <posy>{SEARCH_ACTOR_ROW_Y}</posy>
                        <width>{SEARCH_SHELF_W}</width>
                        <height>{SEARCH_ACTOR_ROW_H}</height>
                        <onup>6830</onup>
                        <ondown>6850</ondown>
                        <onleft>6701</onleft>
                        <onright>6840</onright>
                        <orientation>horizontal</orientation>
                        <itemwidth>{SEARCH_ACTOR_CELL_W}</itemwidth>
                        <itemheight>{SEARCH_ACTOR_CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{search_actor_item}

{search_actor_focused}
                    </control>
                </control>

                <!-- Discover shelf: external (not-yet-owned) titles, same
                     +/check watchlist badge as the Discover section's own
                     rows (see MainWindow's comment on self.discover_rows). -->
                <control type="group" id="6851">
                    <height>{SEARCH_SHELF_BLOCK_H}</height>
                    <visible>!String.IsEqual(Window.Property(search_discover_count),0)</visible>
                    <control type="label">
                        <posx>22</posx>
                        <posy>0</posy>
                        <width>600</width>
                        <height>34</height>
                        <font>tofa_font_section_title</font>
                        <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                        <label>Discover</label>
                    </control>
                    <control type="list" id="6850">
                        <posx>0</posx>
                        <posy>{SEARCH_SECTION_BAND}</posy>
                        <width>{SEARCH_SHELF_W}</width>
                        <height>{CELL_H}</height>
                        <onup>6840</onup>
                        <ondown>6850</ondown>
                        <onleft>6701</onleft>
                        <onright>6850</onright>
                        <orientation>horizontal</orientation>
                        <itemwidth>{CELL_W}</itemwidth>
                        <itemheight>{CELL_H}</itemheight>
                        <scrolltime>{SCROLLTIME}</scrolltime>

{search_discover_item}

{search_discover_focused}
                    </control>
                </control>
                </control>
            </control>
        </control>

        <!-- ============================================================
             SETTINGS SECTION (control ids 8000-8299). Replaces Kodi's own
             ADDON.openSettings() dialog, the last stock-Kodi surface the
             add-on had. Three columns, all measured off
             internal-docs/atv-reference/settings-account.png: sidebar /
             detail / an optional right rail (present on Account and
             Privacy & About only, which is why the detail column has two
             widths rather than one plus a hidden rail).

             Page within the section is Window.Property(settings_page);
             every property here is settings_-prefixed because
             Window.Property names are shared window-wide even though
             control ids are not.
             ============================================================ -->
        <control type="group" id="3930">
            <posx>0</posx>
            <posy>0</posy>
            <visible>String.IsEqual(Window.Property(active_section),settings)</visible>

            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{SCREEN_W}</width>
                <height>{SCREEN_H}</height>
                <colordiffuse>{CANVAS}</colordiffuse>
                <texture>white-square.png</texture>
            </control>

            <!-- ===================== SIDEBAR ===================== -->
            <!-- Account card. A display, never focusable: the row that
                 opens account settings is Account in the list below. -->
            <control type="group">
                <posx>{SETTINGS_LEFT}</posx>
                <posy>{SETTINGS_PROFILE_Y}</posy>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>{SETTINGS_SIDEBAR_W}</width>
                    <height>{SETTINGS_PROFILE_H}</height>
                    <colordiffuse>{PANEL_WASH}</colordiffuse>
                    <texture border="20">rounded-20.png</texture>
                </control>
                <control type="image">
                    <posx>20</posx>
                    <posy>21</posy>
                    <width>56</width>
                    <height>56</height>
                    <aspectratio scalediffuse="false">scale</aspectratio>
                    <texture diffuse="circle.png">$INFO[Window.Property(settings_avatar_photo)]</texture>
                    <visible>!String.IsEmpty(Window.Property(settings_avatar_photo))</visible>
                </control>
                <control type="image">
                    <posx>22</posx>
                    <posy>23</posy>
                    <width>52</width>
                    <height>52</height>
                    <aspectratio scalediffuse="false">scale</aspectratio>
                    <texture diffuse="circle.png">$INFO[Window.Property(settings_avatar)]</texture>
                    <visible>String.IsEmpty(Window.Property(settings_avatar_photo)) + !String.IsEmpty(Window.Property(settings_avatar))</visible>
                </control>
                <!-- ...and the monogram when there is none. Same reasoning
                     as the nav marker: the art is server-side now, so "no
                     art" is an ordinary state rather than an error. -->
                <control type="label">
                    <visible>String.IsEmpty(Window.Property(settings_avatar)) + String.IsEmpty(Window.Property(settings_avatar_photo))</visible>
                    <posx>20</posx>
                    <posy>21</posy>
                    <width>56</width>
                    <height>56</height>
                    <align>center</align>
                    <aligny>center</aligny>
                    <font>{FONT_METADATA}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(settings_avatar_initial)]</label>
                </control>
                <control type="label">
                    <posx>90</posx>
                    <posy>18</posy>
                    <width>310</width>
                    <height>30</height>
                    <aligny>center</aligny>
                    <font>{FONT_ACCOUNT}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(settings_account_line)]</label>
                </control>
                <control type="label">
                    <posx>90</posx>
                    <posy>46</posy>
                    <width>310</width>
                    <height>28</height>
                    <aligny>center</aligny>
                    <font>{FONT_METADATA}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(settings_server_line)]</label>
                </control>
            </control>

            <control type="label">
                <posx>{SETTINGS_LEFT}</posx>
                <posy>{SETTINGS_EYEBROW_Y}</posy>
                <width>{SETTINGS_SIDEBAR_W}</width>
                <height>28</height>
                <aligny>center</aligny>
                <font>{FONT_EYEBROW}</font>
                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                <label>SETTINGS</label>
            </control>

            <control type="list" id="8000">
                <posx>{SETTINGS_LEFT}</posx>
                <posy>{SETTINGS_NAV_Y}</posy>
                <width>{SETTINGS_SIDEBAR_W}</width>
                <height>{SETTINGS_NAV_LIST_H}</height>
                <onup>3000</onup>
                <ondown>8000</ondown>
                <onleft>8000</onleft>
                <onright>8110</onright>
                <orientation>vertical</orientation>
                <itemheight>{SETTINGS_NAV_PITCH}</itemheight>
                <scrolltime>{SCROLLTIME}</scrolltime>

{settings_nav_item}

{settings_nav_focused}
            </control>

            <!-- ============= DETAIL: shared heading ============= -->
            <control type="label">
                <posx>{SETTINGS_DETAIL_X}</posx>
                <posy>{SETTINGS_TITLE_Y}</posy>
                <width>{SETTINGS_DETAIL_W_WIDE}</width>
                <height>66</height>
                <aligny>center</aligny>
                <font>{FONT_HEADING}</font>
                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                <label>$INFO[Window.Property(settings_title)]</label>
            </control>
            <control type="label">
                <posx>{SETTINGS_DETAIL_X}</posx>
                <posy>{SETTINGS_SUBTITLE_Y}</posy>
                <width>{SETTINGS_DETAIL_W_WIDE}</width>
                <height>34</height>
                <aligny>center</aligny>
                <font>{FONT_BODY}</font>
                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                <label>$INFO[Window.Property(settings_subtitle)]</label>
            </control>

            <!-- ================= DETAIL: ACCOUNT ================= -->
            <!-- A grouplist, since 2026-08-13: the app's five sections total
                 1165 against a 699 viewport, so this pane scrolls exactly as
                 Appearance does. The two rules from that pane apply here in
                 full (project_kodi_grouplist_scroll_limit):

                 1. Each child is ONE group and must fit the viewport. The
                    tallest here is SWITCH at 327.
                 2. The grouplist chains its children's up/down and overrides
                    them, so no child declares onup/ondown. This is also why
                    Switch Profile and Switch Server are ONE two-item list
                    rather than two lists: a list handles its own item focus,
                    where two focusable siblings inside one child would fight
                    the chain.
                 -->
            <control type="group">
                <posx>{SETTINGS_DETAIL_X}</posx>
                <posy>0</posy>
                <visible>String.IsEqual(Window.Property(settings_page),account)</visible>

                <control type="grouplist" id="8190">
                    <posx>0</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8190</ondown>
                    <onleft>8000</onleft>
                    <onright>8190</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <!-- SWITCH: two children, one row each. A multi-item
                         list would eat Down at its last item and dead-end
                         the page; see SETTINGS_ACCOUNT_SWITCH_GROUP_H. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_ACCOUNT_SWITCH_GROUP_H}</height>
{settings_switch_eyebrow}
                        <control type="list" id="8110">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8110</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_action_item}

{settings_action_focused}
                        </control>
                    </control>

                    <!-- The same group continued, no eyebrow of its own. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_ACCOUNT_SWITCH2_GROUP_H}</height>
                        <control type="list" id="8115">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{SETTINGS_DETAIL_W}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8115</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_action_item_3}

{settings_action_focused_3}
                        </control>
                    </control>

                    <!-- SESSION -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_ACCOUNT_SESSION_GROUP_H}</height>
{settings_session_eyebrow}
                        <control type="list" id="8120">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8120</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_action_item_2}

{settings_action_focused_2}
                        </control>
                    </control>

                    <!-- ACCOUNT and SERVER report values and cannot be
                         focused, so they share the CONNECTION child rather
                         than being children of their own: a child with no
                         focusable content joins the grouplist's chain and
                         swallows a keypress. Their heights are still their
                         own group heights, so the spacing reads as three
                         sections. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_ACCOUNT_TAIL_GROUP_H}</height>
{settings_account_tail}
                        <control type="list" id="8130">
                            <posx>0</posx>
                            <posy>{SETTINGS_ACCOUNT_CONNECTION_ROW_Y}</posy>
                            <width>{SETTINGS_DETAIL_W}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8130</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_direct_item}

{settings_direct_focused}
                        </control>
                        <!-- Reports how THIS box actually reaches the server.
                             Non-focusable, so it rides in the toggle's child;
                             body swaps direct/relay in _settings_fill_connection. -->
{settings_connection_note}
                    </control>
                </control>
            </control>

            <!-- ================ DETAIL: APPEARANCE ================ -->
            <!-- The pane SCROLLS, so its groups are children of a grouplist.
                 Two Kodi behaviours shape this (project_kodi_grouplist_scroll_limit):

                 1. A grouplist scrolls to reveal a focused CHILD and never
                    for focus moving around inside one. So each group here is
                    exactly ONE child, eyebrow included, and the fox grid is a
                    <panel> that handles tile-to-tile focus internally. Every
                    child must also fit the viewport, or focus lands off
                    screen with nothing able to scroll to it.
                 2. A grouplist OVERRIDES its children's up/down, chaining
                    them and using its OWN onup/ondown at the two ends. That
                    is why the children below declare no onup/ondown of their
                    own and the grouplist carries them instead. It works here
                    because every child is a real group with focusable
                    content; a bare label child would silently join the chain
                    and swallow a keypress.
                 -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),appearance)</visible>
                <control type="grouplist" id="8290">
                    <posx>{SETTINGS_DETAIL_X}</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W_WIDE}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8290</ondown>
                    <onleft>8000</onleft>
                    <onright>8290</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <!-- FOX -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_FOX_GROUP_H}</height>
{settings_fox_eyebrow}
                        <control type="image">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_FOX_CARD_H}</height>
                            <colordiffuse>{PANEL_WASH}</colordiffuse>
                            <texture border="20">rounded-20.png</texture>
                        </control>
                        <control type="textbox">
                            <posx>{SETTINGS_FOX_CARD_PAD}</posx>
                            <posy>{SETTINGS_FOX_BLURB_ABS_Y}</posy>
                            <width>{SETTINGS_FOX_BLURB_W}</width>
                            <height>{SETTINGS_FOX_BLURB_H}</height>
                            <font>{FONT_METADATA}</font>
                            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                            <label>$INFO[Window.Property(settings_fox_blurb)]</label>
                        </control>
                        <control type="panel" id="8200">
                            <posx>{SETTINGS_FOX_CARD_PAD}</posx>
                            <posy>{SETTINGS_FOX_GRID_ABS_Y}</posy>
                            <width>{SETTINGS_FOX_GRID_W}</width>
                            <height>{SETTINGS_FOX_GRID_H}</height>
                            <!-- The nav bar, like every other first row in
                                 the app. Without a target here Kodi wraps a
                                 vertical panel instead: Up cycled row 1 ->
                                 2 -> 3 -> 1 forever and the fox grid could
                                 never be left upward at all. -->
                            <onup>3000</onup>
                            <onleft>8000</onleft>
                            <onright>8200</onright>
                            <orientation>vertical</orientation>
                            <itemwidth>{SETTINGS_FOX_CELL_W}</itemwidth>
                            <itemheight>{SETTINGS_FOX_CELL_H}</itemheight>
                            <scrolltime>{SCROLLTIME}</scrolltime>

{settings_fox_item}

{settings_fox_focused}
                        </control>
                    </control>

                    <!-- HOME SCREEN: three children, not one.
                         The row list gets a child of its own so it can be
                         sized to the account's real row count and still fit
                         the viewport; sharing a child with the eyebrow, the
                         toggle and the two add-rows capped it at five. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_HOMESCREEN_GROUP_H}</height>
{settings_homescreen_eyebrow}
                        <control type="list" id="8320">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8320</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_spotlight_item}

{settings_spotlight_focused}
                        </control>
                    </control>

                    <!-- ONE GROUP PER ROW, not a list, so each row can
                         carry three independently focusable controls the way
                         the reference app does: move up, move down, and the
                         switch. A list cannot: Kodi builds item layouts with
                         insideContainer=true, so an item's controls are drawn
                         but never join the focus tree and the list itself is
                         the single focus target. A grouplist of real buttons
                         is what Kodi's own Estuary uses for SettingsCategory.

                         Each row is a DIRECT child of the appearance
                         grouplist, which is what makes up/down between rows
                         and scroll-into-view work; the buttons inside are
                         grandchildren, so their navigation is wired in
                         Python (see _settings_wire_home_rows) rather than
                         here, because a grouplist OVERRIDES its children's
                         up/down and grandchildren resolve to nothing.

                         Slots past the account's row count hide themselves
                         on an empty title property, which also takes them
                         out of the grouplist's chain. -->
{settings_homerow_editors}

                    <!-- ONE "Add a row", holding three groups. It was two
                         tiles until the reference apps settled on a single
                         grouped picker; 8350 is retired, not reused. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_HOMEADD_H}</height>
                        <control type="list" id="8340">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_HOMEADD_H}</height>
                            <onleft>8000</onleft>
                            <onright>8340</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_HOMEADD_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_add_row_item}

{settings_add_row_focused}
                        </control>
                    </control>

                    <!-- The line the reference app puts under the row
                         editor. It carries two facts a viewer cannot infer
                         from the controls: that the list order IS the Home
                         order, and that turning a row off follows the
                         account rather than staying on this device.

                         The text arrives as a WINDOW PROPERTY, not as
                         $LOCALIZE[31122]. Kodi resolves $LOCALIZE in a
                         window XML against the ACTIVE SKIN's strings, and
                         31000-31999 is the range skins use: Estuary's
                         #31122 is "Unwatched TV Shows", which is exactly
                         what this line displayed. It fails silently and
                         differently per skin, so nothing in this add-on's
                         XML may use $LOCALIZE; check_xml.py enforces it. -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_HOMEROWS_NOTE_H}</height>
                        <control type="label">
                            <posx>18</posx>
                            <posy>0</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_HOMEROWS_NOTE_H}</height>
                            <aligny>center</aligny>
                            <font>tofa_font_metadata</font>
                            <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                            <label>$INFO[Window.Property(home_rows_note)]</label>
                        </control>
                    </control>

                    <!-- MEDIA CARDS -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_MEDIACARDS_GROUP_H}</height>
{settings_mediacards_eyebrow}
{settings_rating_group}
                        <control type="list" id="8310">
                            <posx>0</posx>
                            <posy>{SETTINGS_MEDIACARDS_SECOND_Y}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8300</onup>
                            <onleft>8000</onleft>
                            <onright>8310</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_episodes_item}

{settings_episodes_focused}
                        </control>
                    </control>

                    <!-- REGION -->
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_REGION_GROUP_H}</height>
{settings_region_eyebrow}
                        <control type="list" id="8360">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onleft>8000</onleft>
                            <onright>8360</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_region_item}

{settings_region_focused}
                        </control>
                    </control>
                </control>
            </control>

            <!-- ============== DETAIL: PLAYBACK & VIDEO ============== -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),playback)</visible>
                <control type="grouplist" id="8490">
                    <posx>{SETTINGS_DETAIL_X}</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W_WIDE}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8490</ondown>
                    <onleft>8000</onleft>
                    <onright>8490</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_QUALITY_GROUP_H}</height>
{settings_quality_eyebrow}
{settings_quality_group}
                    </control>
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_NEXTUP_GROUP_H}</height>
{settings_nextup_eyebrow}
{settings_nextup_group}
                    </control>
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_SKIP_GROUP_H}</height>
{settings_skip_eyebrow}
{settings_seg_intro_group}
{settings_seg_recap_group}
{settings_seg_preview_group}
{settings_seg_outro_group}
{settings_seg_commercial_group}
                    </control>
                </control>
            </control>

            <!-- ============= DETAIL: AUDIO & SUBTITLES ============= -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),audio)</visible>
                <control type="grouplist" id="8590">
                    <posx>{SETTINGS_DETAIL_X}</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W_WIDE}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8590</ondown>
                    <onleft>8000</onleft>
                    <onright>8590</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_AUDIO_GROUP_H}</height>
{settings_audio_eyebrow}
                        <control type="list" id="8510">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>3000</onup>
                            <ondown>8540</ondown>
                            <onleft>8000</onleft>
                            <onright>8510</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_audiolang_item}

{settings_audiolang_focused}
                        </control>
                        <control type="list" id="8540">
                            <posx>0</posx>
                            <posy>{SETTINGS_LANG_ROW1_Y}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8510</onup>
                            <ondown>8520</ondown>
                            <onleft>8000</onleft>
                            <onright>8540</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_audiolang2_item}

{settings_audiolang2_focused}
                        </control>
                    </control>
                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_SUBS_GROUP_H}</height>
{settings_subs_eyebrow}
                        <control type="list" id="8520">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8540</onup>
                            <ondown>8550</ondown>
                            <onleft>8000</onleft>
                            <onright>8520</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_sublang_item}

{settings_sublang_focused}
                        </control>
                        <control type="list" id="8550">
                            <posx>0</posx>
                            <posy>{SETTINGS_LANG_ROW1_Y}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8520</onup>
                            <ondown>8530</ondown>
                            <onleft>8000</onleft>
                            <onright>8550</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_sublang2_item}

{settings_sublang2_focused}
                        </control>
                        <control type="list" id="8530">
                            <posx>0</posx>
                            <posy>{SETTINGS_LANG_ROW2_Y}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8550</onup>
                            <ondown>8530</ondown>
                            <onleft>8000</onleft>
                            <onright>8530</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_alwayssubs_item}

{settings_alwayssubs_focused}
                        </control>
                    </control>
                </control>
            </control>

            <!-- ============== DETAIL: PRIVACY & ABOUT ============== -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),privacy)</visible>
                <control type="grouplist" id="8690">
                    <posx>{SETTINGS_DETAIL_X}</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8690</ondown>
                    <onleft>8000</onleft>
                    <onright>8690</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_PRIVACY_GROUP_H}</height>
{settings_privacy_eyebrow}
{settings_diagnostics_note}
                    </control>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W}</width>
                        <height>{SETTINGS_ABOUT_GROUP_H}</height>
{settings_about_eyebrow}
{settings_about_name_row}
{settings_version_row}
                        <control type="list" id="8620">
                            <posx>0</posx>
                            <posy>{SETTINGS_ABOUT_ROW1_Y}</posy>
                            <width>{SETTINGS_DETAIL_W}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>3000</onup>
                            <onleft>8000</onleft>
                            <onright>8620</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_licences_item}

{settings_licences_focused}
                        </control>
                    </control>
                </control>
                <control type="group">
{settings_support_rail}
                </control>
            </control>

            <!-- ================ DETAIL: THIS DEVICE ================ -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),device)</visible>
                <control type="grouplist" id="8790">
                    <posx>{SETTINGS_DETAIL_X}</posx>
                    <posy>{SETTINGS_GROUPLIST_Y}</posy>
                    <width>{SETTINGS_DETAIL_W_WIDE}</width>
                    <height>{SETTINGS_GROUPLIST_H}</height>
                    <onup>3000</onup>
                    <ondown>8790</ondown>
                    <onleft>8000</onleft>
                    <onright>8790</onright>
                    <orientation>vertical</orientation>
                    <itemgap>{SETTINGS_GROUPLIST_ITEMGAP}</itemgap>
                    <scrolltime>{SCROLLTIME}</scrolltime>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_DEVICE_GROUP_H}</height>
{settings_device_eyebrow}
                        <control type="list" id="8710">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>3000</onup>
                            <ondown>8720</ondown>
                            <onleft>8000</onleft>
                            <onright>8710</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_fonts_item}

{settings_fonts_focused}
                        </control>
{settings_deviceid_row}
                    </control>

                    <control type="group">
                        <width>{SETTINGS_DETAIL_W_WIDE}</width>
                        <height>{SETTINGS_ARTCACHE_GROUP_H}</height>
{settings_artcache_eyebrow}
                        <control type="list" id="8720">
                            <posx>0</posx>
                            <posy>{SETTINGS_SECTION_BAND}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8710</onup>
                            <ondown>8730</ondown>
                            <onleft>8000</onleft>
                            <onright>8720</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_artbudget_item}

{settings_artbudget_focused}
                        </control>
                        <control type="list" id="8730">
                            <posx>0</posx>
                            <posy>{SETTINGS_ARTCACHE_ROW1_Y}</posy>
                            <width>{SETTINGS_DETAIL_W_WIDE}</width>
                            <height>{SETTINGS_ACTION_ROW_H}</height>
                            <onup>8720</onup>
                            <ondown>8730</ondown>
                            <onleft>8000</onleft>
                            <onright>8730</onright>
                            <orientation>vertical</orientation>
                            <itemheight>{SETTINGS_ACTION_ROW_H}</itemheight>
                            <scrolltime>0</scrolltime>

{settings_artclear_item}

{settings_artclear_focused}
                        </control>
                    </control>
                </control>
            </control>

            <!-- ============ DETAIL: the unbuilt pages ============ -->
{settings_page_scaffolds}

            <!-- ==================== RIGHT RAIL ==================== -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(settings_page),account)</visible>
{settings_qr_rail}
            </control>
        </control>

        <!-- Shared chrome, rendered last so it paints on top of whichever
             section's own content is visible: Kodi draws controls in
             document order, and every section's content is full-bleed. -->
{logo_block}

{nav_bar}

        <!-- Profile avatar, top right. Purely a "who is this" marker, exactly
             as on Apple TV: NOT focusable and NOT a control, so the nav bar's
             own Left/Right ring is untouched and nothing can land on it.
             Switching profiles stays in Settings > Account.

             Measured off internal-docs/atv-reference: a 64px circle whose
             centre sits at (1748, 80), i.e. on the nav bar's own vertical
             centre line.

             scalediffuse="false" is load-bearing, not decoration: without it
             Kodi stretches the circular MASK along with the art and the
             avatar renders as an oval (project_kodi_aspectratio_scale_distorts). -->
        <control type="image">
            <visible>!String.IsEmpty(Window.Property(nav_avatar)) | !String.IsEmpty(Window.Property(nav_avatar_photo)) | !String.IsEmpty(Window.Property(nav_avatar_initial))</visible>
            <posx>{NAV_AVATAR_SHADOW_X}</posx>
            <posy>{NAV_AVATAR_SHADOW_Y}</posy>
            <width>{NAV_AVATAR_SHADOW}</width>
            <height>{NAV_AVATAR_SHADOW}</height>
            <texture>avatar-shadow.png</texture>
        </control>
        <!-- An uploaded photo FILLS the ring (object-cover in the web app);
             a preset sits at 92% inside it (object-contain). -->
        <control type="image">
            <visible>!String.IsEmpty(Window.Property(nav_avatar_photo))</visible>
            <posx>{NAV_AVATAR_ART_X}</posx>
            <posy>{NAV_AVATAR_ART_Y}</posy>
            <width>{NAV_AVATAR_ART}</width>
            <height>{NAV_AVATAR_ART}</height>
            <aspectratio scalediffuse="false">scale</aspectratio>
            <texture diffuse="circle.png">$INFO[Window.Property(nav_avatar_photo)]</texture>
        </control>
        <control type="image">
            <visible>String.IsEmpty(Window.Property(nav_avatar_photo)) + !String.IsEmpty(Window.Property(nav_avatar))</visible>
            <posx>{NAV_AVATAR_ART_X}</posx>
            <posy>{NAV_AVATAR_ART_Y}</posy>
            <width>{NAV_AVATAR_ART}</width>
            <height>{NAV_AVATAR_ART}</height>
            <aspectratio scalediffuse="false">scale</aspectratio>
            <texture diffuse="circle.png">$INFO[Window.Property(nav_avatar)]</texture>
        </control>
        <control type="image">
            <visible>!String.IsEmpty(Window.Property(nav_avatar)) | !String.IsEmpty(Window.Property(nav_avatar_photo)) | !String.IsEmpty(Window.Property(nav_avatar_initial))</visible>
            <posx>{NAV_AVATAR_X}</posx>
            <posy>{NAV_AVATAR_Y}</posy>
            <width>{NAV_AVATAR_SIZE}</width>
            <height>{NAV_AVATAR_SIZE}</height>
            <colordiffuse>{BORDER}</colordiffuse>
            <texture>circle-outline.png</texture>
        </control>
        <!-- The monogram, when there is no art to draw: a photo profile
             (this control deliberately never pays for an image token), a
             preset tofa has retired, or a server we cannot reach. It
             replaces a bundled generic fox, which was always SOMEONE
             ELSE'S face. -->
        <control type="label">
            <visible>String.IsEmpty(Window.Property(nav_avatar)) + String.IsEmpty(Window.Property(nav_avatar_photo)) + !String.IsEmpty(Window.Property(nav_avatar_initial))</visible>
            <posx>{NAV_AVATAR_X}</posx>
            <posy>{NAV_AVATAR_Y}</posy>
            <width>{NAV_AVATAR_SIZE}</width>
            <height>{NAV_AVATAR_SIZE}</height>
            <align>center</align>
            <aligny>center</aligny>
            <font>tofa_font_caption</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>$INFO[Window.Property(nav_avatar_initial)]</label>
        </control>

        <!-- Covers this window while a profile switch tears it down.
             LAST in the file, so it is over everything.

             The switch closes this window and the launcher raises the splash
             after closeNow() returns; between the profile picker closing and
             that, the Settings page it was pressed from is briefly back on
             screen. Reported as "a tiny flash ... it went back to the Settings
             screen for a split second".

             Raising the splash BEFORE the close is the obvious fix and is
             measured to be much worse; see _settings_switch_profile. This
             costs one control that is invisible unless the property is set,
             and the property is only ever set on the one code path that
             immediately closes the window. SPLASH_BG so the cover and the
             splash that follows it are the same colour, and the seam between
             them cannot be seen. -->
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>1080</height>
            <texture colordiffuse="{SPLASH_BG}">white-square.png</texture>
            <visible>!String.IsEmpty(Window.Property(switching_profile))</visible>
        </control>

        <!-- 8.9's toast, LAST so it draws over every section. Nothing in
             this window raises one today; it is here so that anything which
             ever does has somewhere to draw, rather than setting a property
             no window renders. Repo owner's call, for consistency. -->
{toast}

        <!-- kodigui framework sentinel: BaseWindow.onInit polls for control 666
             to know the XML finished loading. Must exist in every window XML. -->
        <control type="label" id="666">
            <visible>false</visible>
            <width>1</width>
            <height>1</height>
        </control>
    </controls>
</window>
