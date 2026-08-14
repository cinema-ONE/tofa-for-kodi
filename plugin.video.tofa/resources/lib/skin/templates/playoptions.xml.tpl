<?xml version="1.0" encoding="UTF-8"?>
<!--
  Pre-play options TEMPLATE (TV-DESIGN 7.7), rendered to
  script-tofa-playoptions.xml by resources/lib/skin/screens.py:
  render_playoptions(). DO NOT HAND-EDIT the rendered file.

  Quality / Audio / Subtitles for the file the Detail hero is about to
  play, reached from the Options pill. 7.7: "selecting persists the pick
  immediately but never starts playback" ; there is deliberately no Play
  affordance on this panel.

  ONE list carries section headers and their options together, collapsed by
  default and expanded one section at a time; see fragments.py:
  collapsible_row() for why that is one control rather than three.

  Not the picker (script-tofa-picker.xml) and not the card-options panel
  (script-tofa-cardoptions.xml): the picker's row is a single 68px line
  shared with Sort/Filter and pixel-matched, and neither surface has a
  second text column or a disclosure state.
-->
<window>
    <defaultcontrol always="true">{LIST_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <!-- Scrim, matching the card-options panel: the two open from the
             same action row and a different dim between them would read as
             a different depth. -->
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <texture>white-square.png</texture>
            <colordiffuse>0x94000000</colordiffuse>
        </control>

        <!-- Every id below exists so windows/playoptions.py can resize the
             panel to the rows it is actually showing; see
             fragments.playoptions_geometry(). -->
        <control type="group" id="{GROUP_ID}">
            <posx>{PANEL_X}</posx>
            <posy>{PANEL_Y}</posy>

            <!-- Floating panel, so 4's no-shadow-on-resting-chrome rule
                 does not apply; same offsets and asset as 7.2's panel. -->
            <control type="image" id="{SHADOW_ID}">
                <posx>-42</posx>
                <posy>-24</posy>
                <width>{SHADOW_W}</width>
                <height>{SHADOW_H}</height>
                <colordiffuse>0x9E000000</colordiffuse>
                <texture border="64">panel-shadow-r22.png</texture>
            </control>
            <control type="image" id="{FILL_ID}">
                <posx>0</posx>
                <posy>0</posy>
                <width>{PANEL_W}</width>
                <height>{PANEL_H}</height>
                <colordiffuse>{SURFACE_FLOATING}</colordiffuse>
                <texture border="24">panel-r22.png</texture>
            </control>
            <control type="image" id="{OUTLINE_ID}">
                <posx>0</posx>
                <posy>0</posy>
                <width>{PANEL_W}</width>
                <height>{PANEL_H}</height>
                <colordiffuse>{BORDER_FLOATING}</colordiffuse>
                <texture border="24">panel-r22-outline.png</texture>
            </control>

            <control type="label">
                <posx>{PAD}</posx>
                <posy>{TITLE_Y}</posy>
                <width>{INNER_W}</width>
                <height>40</height>
                <aligny>center</aligny>
                <font>{FONT_DIALOG_TITLE}</font>
                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                <label>$INFO[Window.Property(options_title)]</label>
            </control>
            <!-- The FILE this panel is about. On a multi-edition title the
                 tracks differ per edition, so naming the one in hand is not
                 decoration: it is the difference between two dialogs that
                 otherwise look identical. -->
            <control type="label">
                <posx>{PAD}</posx>
                <posy>{SUBTITLE_Y}</posy>
                <width>{INNER_W}</width>
                <height>30</height>
                <aligny>center</aligny>
                <font>{FONT_METADATA}</font>
                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                <label>$INFO[Window.Property(options_subtitle)]</label>
            </control>

            <control type="list" id="{LIST_ID}">
                <posx>{PAD}</posx>
                <posy>{ROWS_Y}</posy>
                <width>{INNER_W}</width>
                <height>{ROWS_H}</height>
                <onup>{LIST_ID}</onup>
                <ondown>{LIST_ID}</ondown>
                <onleft>{LIST_ID}</onleft>
                <onright>{LIST_ID}</onright>
                <orientation>vertical</orientation>
                <itemwidth>{INNER_W}</itemwidth>
                <itemheight>{OPT_ROW_PITCH}</itemheight>
{option_row}
{option_row_focused}
            </control>

            <!-- 7.7's "optional trailing hint at 65%". Ours states what the
                 CURRENT selection will actually do (Direct Play, or the
                 transcode it forces), which is the one thing this panel can
                 tell a viewer that no badge on the detail page can. -->
            <control type="label" id="{HINT_ID}">
                <posx>{PAD}</posx>
                <posy>{HINT_Y}</posy>
                <width>{INNER_W}</width>
                <height>28</height>
                <aligny>center</aligny>
                <font>{FONT_MICRO}</font>
                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                <label>$INFO[Window.Property(options_hint)]</label>
            </control>
        </control>

        <!-- kodigui framework sentinel: BaseWindow/BaseDialog onInit polls for
             control 666 to know the XML finished loading. -->
        <control type="label" id="666">
            <visible>false</visible>
            <width>1</width>
            <height>1</height>
        </control>
    </controls>
</window>
