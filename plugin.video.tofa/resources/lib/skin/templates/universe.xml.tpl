<?xml version="1.0" encoding="UTF-8"?>
<!--
  Universe page TEMPLATE for screens.py:render_universe() (app 2.1.0); never
  hand-edit script-tofa-universe.xml. universepage.py sets the pills' x.
-->
<window>
    <defaultcontrol always="true">{CONTINUE_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <control type="image">
            <visible>String.IsEmpty(Window.Property(u_backdrop))</visible>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <aspectratio>stretch</aspectratio>
            <texture>detail-no-backdrop.png</texture>
        </control>
        <control type="image" id="9000">
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <aspectratio>scale</aspectratio>
            <fadetime>{HERO_CROSSFADE_MS}</fadetime>
            <texture background="true">$INFO[Window.Property(u_backdrop)]</texture>
        </control>
        <control type="image">
            <width>1500</width>
            <height>{SCREEN_H}</height>
            <colordiffuse>0xF2030B10</colordiffuse>
            <texture>fade-left.png</texture>
        </control>
        <control type="image">
            <posy>400</posy>
            <width>{SCREEN_W}</width>
            <height>680</height>
            <colordiffuse>0xF0030B10</colordiffuse>
            <texture>fade-bottom.png</texture>
        </control>

        <control type="group">
            <animation effect="slide" start="0,0" end="0,{UNI_NO_CHAPTERS_DY}" time="0" condition="String.IsEmpty(Window.Property(u_chapters))">Conditional</animation>

            <!-- The universe. -->
            <control type="group">
                <visible>String.IsEmpty(Window.Property(u_state))</visible>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_TITLE_Y}</posy>
                    <width>1700</width>
                    <height>{UNI_TITLE_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_HERO}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(u_name)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_SUMMARY_Y}</posy>
                    <width>1600</width>
                    <height>{UNI_SUMMARY_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_SIDEBAR}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(u_summary)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_OVERVIEW_Y}</posy>
                    <width>{UNI_OVERVIEW_W}</width>
                    <height>{UNI_OVERVIEW_H}</height>
                    <wrapmultiline>true</wrapmultiline>
                    <font>{FONT_BODY}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(u_overview)]</label>
                </control>
            </control>

            <!-- A focused poster's title. -->
            <control type="group">
                <visible>String.IsEqual(Window.Property(u_state),title)</visible>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_EYEBROW_Y}</posy>
                    <width>1600</width>
                    <height>{UNI_EYEBROW_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_ACCOUNT}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(u_name)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_COUNT_Y}</posy>
                    <width>1600</width>
                    <height>{UNI_COUNT_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_POSTER_TITLE}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(u_position)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_TITLE_Y}</posy>
                    <width>1700</width>
                    <height>{UNI_TITLE_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_HERO}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(u_title)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_META_Y}</posy>
                    <width>1600</width>
                    <height>{UNI_SUMMARY_H}</height>
                    <aligny>center</aligny>
                    <font>{FONT_SETTINGS_VALUE}</font>
                    <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                    <label>$INFO[Window.Property(u_meta)]</label>
                </control>
                <control type="label">
                    <posx>{UNI_LEFT}</posx>
                    <posy>{UNI_OVERVIEW_Y}</posy>
                    <width>{UNI_OVERVIEW_W}</width>
                    <height>{UNI_OVERVIEW_H}</height>
                    <wrapmultiline>true</wrapmultiline>
                    <font>{FONT_BODY}</font>
                    <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                    <label>$INFO[Window.Property(u_title_overview)]</label>
                </control>
            </control>

{pills}

            <control type="list" id="{STRIP_ID}">
                <posx>{STRIP_X}</posx>
                <posy>{UNI_STRIP_TOP}</posy>
                <width>{STRIP_W}</width>
                <height>{STRIP_H}</height>
                <onup condition="Control.IsVisible({CONTINUE_GROUP_ID})">{CONTINUE_ID}</onup>
                <onup condition="!Control.IsVisible({CONTINUE_GROUP_ID}) + String.IsEmpty(Window.Property(u_state))">{ORDER_ID}</onup>
                <onup condition="!Control.IsVisible({CONTINUE_GROUP_ID}) + !String.IsEmpty(Window.Property(u_state))">{DETAILS_ID}</onup>
                <onleft>{STRIP_ID}</onleft>
                <onright>{STRIP_ID}</onright>
                <ondown>{STRIP_ID}</ondown>
                <orientation>horizontal</orientation>
                <itemwidth>{UNI_STRIP_PITCH}</itemwidth>
                <itemheight>{STRIP_H}</itemheight>
                <scrolltime>{SCROLLTIME}</scrolltime>
{strip_item}
{strip_focused}
            </control>
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
