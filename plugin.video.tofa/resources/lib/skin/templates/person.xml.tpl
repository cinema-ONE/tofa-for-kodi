<?xml version="1.0" encoding="UTF-8"?>
<!--
  Person / filmography TEMPLATE, rendered to script-tofa-person.xml by
  resources/lib/skin/screens.py:render_person(). DO NOT HAND-EDIT the
  rendered file.

  TV-DESIGN 7.4. Opened by clicking a face in the detail screen's Cast or
  Crew grid, which was a dead end until now.

  Two data sources, one grid: titles you own come from GET /media?cast=,
  the rest from GET /discovery/person?name=. The server strips owned
  titles out of the second, so they concatenate without deduping.

  DELIBERATE KODI DIVERGENCE: the section headers.
  7.4 puts "In your library" and "Not in your library" INLINE, as two
  headings inside one scrolling grid, with the page header pinned above.
  Kodi cannot express that: a panel scrolls internally, a grouplist
  scrolls by whole control, and nesting one in the other gives you a tall
  panel whose focused row scrolls out of the grouplist's view. The
  established pattern in this codebase for stacked grids (detail's
  Cast/Crew, script-tofa-detail.xml) is two fixed-viewport panels, but at
  CELL_H a single row is 472 tall and two sections plus their headers do
  not fit on a 1080 canvas at all.

  So: ONE panel holding both halves in order, and ONE section label above
  it that re-labels itself as focus crosses the boundary (person.py's
  _sync_section_label). Same information, same two counts, same styling;
  it just sticks instead of scrolling away. The per-card distinction 7.4
  asks for is unaffected and carries the real signal: owned cards show the
  rating badge, un-owned ones show the plus chip instead.
-->
<window>
    <defaultcontrol always="true">{GRID_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <!-- 7.4's one-off vertical gradient. A real texture, not a flat
             fill: Kodi has no gradient primitive. Full-bleed and drawn
             first, so everything below sits on it. -->
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <texture>person-bg.png</texture>
        </control>

        <!-- Header. Pinned: it is outside the panel, so the grid scrolls
             under it exactly as the real app does. -->
        <control type="label">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_NAME_Y}</posy>
            <width>1400</width>
            <height>56</height>
            <font>{FONT_HEADING}</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>$INFO[Window.Property(person_name)]</label>
        </control>
        <control type="label">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_SUBTITLE_Y}</posy>
            <width>1400</width>
            <height>28</height>
            <font>{FONT_METADATA}</font>
            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
            <label>$INFO[Window.Property(person_subtitle)]</label>
        </control>

        <!-- Section label. 7.4 gives the trailing count its own muted tier,
             which would normally need a second control positioned after the
             title; the two titles differ in length, and textmetrics.py only
             carries advance widths for tofa_font_metadata, so there is no
             ruler for this font. Kodi labels accept inline [COLOR] markup
             instead, so person.py builds the whole string in one go. -->
        <control type="label" id="{SECTION_LABEL_ID}">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_SECTION_Y}</posy>
            <width>1400</width>
            <height>34</height>
            <font>{FONT_ROW_TITLE}</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>$INFO[Window.Property(section_title)]</label>
        </control>

        <!-- Empty / error state, 9.7's shared scaffold. 7.4 owns the
             CONDITION (shown only when BOTH halves resolve empty, and a half
             that FAILED is not a half that is empty), so person.py sets
             person_state and this only reads it. Both blocks read the same
             title/message properties; they differ in flavour, which is what
             turns the glyph and title red for an error. -->
{empty_state}

{error_state}

        <!-- Shifted left by HPAD so the poster ART lands on PERSON_LEFT
             rather than its padded cell edge; same correction Browse's
             grid makes. -->
        <control type="panel" id="{GRID_ID}">
            <posx>{PERSON_GRID_X}</posx>
            <posy>{PERSON_GRID_Y}</posy>
            <width>{PERSON_GRID_W}</width>
            <height>{PERSON_GRID_H}</height>
            <onup>{GRID_ID}</onup>
            <ondown>{GRID_ID}</ondown>
            <onleft>{GRID_ID}</onleft>
            <onright>{GRID_ID}</onright>
            <orientation>vertical</orientation>
            <itemwidth>{CELL_W}</itemwidth>
            <itemheight>{GRID_CELL_H}</itemheight>
            <scrolltime>{SCROLLTIME}</scrolltime>
{grid_item}

{grid_focused}
        </control>

        <!-- kodigui framework sentinel (must exist in every window XML). -->
        <control type="label" id="666">
            <posx>-100</posx>
            <posy>-100</posy>
            <width>1</width>
            <height>1</height>
            <label></label>
        </control>
    </controls>
</window>
