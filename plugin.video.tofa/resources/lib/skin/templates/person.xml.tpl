<?xml version="1.0" encoding="UTF-8"?>
<!--
  Person / filmography TEMPLATE, rendered to script-tofa-person.xml by
  resources/lib/skin/screens.py:render_person(). DO NOT HAND-EDIT the
  rendered file. App 2.0: a fixed left column, four posters across on the
  right (titles you have, then more of their work), and a Filmography panel.
-->
<window>
    <defaultcontrol always="true">{GRID_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <!-- The canvas with a soft glow at the top, where the app blurs the
             photo (tools/gen_panel_assets.py:gen_person_bg). -->
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <texture>person-bg.png</texture>
        </control>

        <!-- Left column (app 2.0), fixed while the grid scrolls. -->
        <control type="image">
            <visible>String.IsEmpty(Window.Property(person_photo))</visible>
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_PHOTO_Y}</posy>
            <width>{PERSON_PHOTO_W}</width>
            <height>{PERSON_PHOTO_H}</height>
            <colordiffuse>0x14FFFFFF</colordiffuse>
            <texture diffuse="person-photo-mask.png">white-square.png</texture>
        </control>
        <control type="label">
            <visible>String.IsEmpty(Window.Property(person_photo))</visible>
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_PHOTO_Y}</posy>
            <width>{PERSON_PHOTO_W}</width>
            <height>{PERSON_PHOTO_H}</height>
            <align>center</align>
            <aligny>center</aligny>
            <font>{FONT_PERSON_NAME}</font>
            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
            <label>$INFO[Window.Property(person_initials)]</label>
        </control>
        <control type="image">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_PHOTO_Y}</posy>
            <width>{PERSON_PHOTO_W}</width>
            <height>{PERSON_PHOTO_H}</height>
            <aspectratio scalediffuse="false">scale</aspectratio>
            <texture diffuse="person-photo-mask.png" background="true">$INFO[Window.Property(person_photo)]</texture>
        </control>
        <control type="label">
            <posx>{PERSON_NAME_X}</posx>
            <posy>{PERSON_NAME_Y}</posy>
            <width>{PERSON_NAME_W}</width>
            <height>70</height>
            <font>{FONT_PERSON_NAME}</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>$INFO[Window.Property(person_name)]</label>
        </control>
        <control type="label">
            <posx>{PERSON_NAME_X}</posx>
            <posy>{PERSON_ROLE_Y}</posy>
            <width>{PERSON_NAME_W}</width>
            <height>34</height>
            <font>{FONT_BODY}</font>
            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
            <label>$INFO[Window.Property(person_role)]</label>
        </control>
        <control type="button" id="{PILL_ID}">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_PILL_Y}</posy>
            <width>{PERSON_PILL_W}</width>
            <height>{PERSON_PILL_H}</height>
            <onright>{GRID_ID}</onright>
            <texturefocus colordiffuse="$INFO[Window.Property(accent_wash_focus)]">person-pill.png</texturefocus>
            <texturenofocus colordiffuse="0x21FFFFFF">person-pill.png</texturenofocus>
            <font>{FONT_CARD_TITLE}</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <focusedcolor>$INFO[Window.Property(accent_color)]</focusedcolor>
            <align>center</align>
            <aligny>center</aligny>
            <label>Filmography</label>
        </control>
        <control type="image">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_RULE_Y}</posy>
            <width>{PERSON_RULE_W}</width>
            <height>1</height>
            <colordiffuse>0x33FFFFFF</colordiffuse>
            <texture>white-square.png</texture>
        </control>
        <control type="label">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_CREDITS_EYEBROW_Y}</posy>
            <width>{PERSON_RULE_W}</width>
            <height>22</height>
            <font>{FONT_EYEBROW}</font>
            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
            <label>CREDITS</label>
        </control>
        <control type="label">
            <posx>{PERSON_LEFT}</posx>
            <posy>{PERSON_CREDITS_Y}</posy>
            <width>{PERSON_RULE_W}</width>
            <height>34</height>
            <font>{FONT_CAPTION}</font>
            <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
            <label>$INFO[Window.Property(person_credits)]</label>
        </control>

        <!-- One label over the grid names the section in focus: Kodi cannot
             give one panel two inline headings (rows are one height). -->
        <control type="label" id="{SECTION_LABEL_ID}">
            <posx>{PERSON_SECTION_X}</posx>
            <posy>{PERSON_SECTION_Y}</posy>
            <width>1100</width>
            <height>24</height>
            <font>{FONT_EYEBROW}</font>
            <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
            <label>$INFO[Window.Property(section_title)]</label>
        </control>

{empty_state}

{error_state}

        <control type="panel" id="{GRID_ID}">
            <posx>{PERSON_GRID_X}</posx>
            <posy>{PERSON_GRID_Y}</posy>
            <width>{PERSON_GRID_W}</width>
            <height>{PERSON_GRID_H}</height>
            <onup>{GRID_ID}</onup>
            <ondown>{GRID_ID}</ondown>
            <onleft>{PILL_ID}</onleft>
            <onright>{GRID_ID}</onright>
            <orientation>vertical</orientation>
            <itemwidth>{PERSON_CELL_W}</itemwidth>
            <itemheight>{PERSON_CELL_H}</itemheight>
            <scrolltime>{SCROLLTIME}</scrolltime>
{grid_item}

{grid_focused}
        </control>
{film_panel}

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
