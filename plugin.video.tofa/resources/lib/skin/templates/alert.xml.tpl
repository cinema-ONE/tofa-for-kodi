<?xml version="1.0" encoding="UTF-8"?>
<!--
  Alert TEMPLATE, rendered to script-tofa-alert.xml by
  resources/lib/skin/screens.py:render_alert(). DO NOT HAND-EDIT the
  rendered file.

  The skinned replacement for xbmcgui.Dialog().ok(); a title, a message
  and one button. Seven call sites across sign-in, addon.py and the player
  were showing Kodi's stock system dialog in the middle of an otherwise
  fully skinned UI (#3).

  Distinct from 7.2's card-options panel (script-tofa-cardoptions.xml)
  despite the shared chrome, for one reason: the message must WRAP. That
  panel's subtitle is a single-line label, and these messages are server
  error strings of unknown length, so a truncated one would hide the part
  that says what went wrong. A <textbox> is the only Kodi control that
  wraps, and it cannot live inside a list item.
-->
<window>
    <defaultcontrol always="true">{BUTTON_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{SCREEN_W}</width>
            <height>{SCREEN_H}</height>
            <texture>white-square.png</texture>
            <colordiffuse>0x94000000</colordiffuse>
        </control>

        <control type="group">
            <posx>{PANEL_X}</posx>
            <posy>{PANEL_Y}</posy>

            <control type="image">
                <posx>-42</posx>
                <posy>-24</posy>
                <width>{SHADOW_W}</width>
                <height>{SHADOW_H}</height>
                <colordiffuse>0x9E000000</colordiffuse>
                <texture border="64">panel-shadow-r22.png</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{PANEL_W}</width>
                <height>{PANEL_H}</height>
                <colordiffuse>{SURFACE_FLOATING}</colordiffuse>
                <texture border="22">panel-r22.png</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>{PANEL_W}</width>
                <height>{PANEL_H}</height>
                <colordiffuse>{BORDER_FLOATING}</colordiffuse>
                <texture border="22">panel-r22-outline.png</texture>
            </control>

            <!-- Optional leading glyph, tinted by the caller: a warning
                 triangle for a failure, nothing at all for a plain notice.
                 2's rule that colour is never the sole signal holds here ;
                 the message says what happened; this only sets the tone. -->
            <control type="label">
                <posx>{PAD}</posx>
                <posy>{TITLE_Y}</posy>
                <width>{GLYPH_W}</width>
                <height>44</height>
                <aligny>center</aligny>
                <font>{FONT_ICON_29}</font>
                <textcolor>$INFO[Window.Property(alert_tint)]</textcolor>
                <label>$INFO[Window.Property(alert_glyph)]</label>
                <visible>!String.IsEmpty(Window.Property(alert_glyph))</visible>
            </control>
            <control type="label">
                <posx>{TITLE_X}</posx>
                <posy>{TITLE_Y}</posy>
                <width>{TITLE_W}</width>
                <height>44</height>
                <aligny>center</aligny>
                <font>{FONT_DIALOG_TITLE}</font>
                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                <label>$INFO[Window.Property(alert_title)]</label>
            </control>

            <control type="textbox">
                <posx>{PAD}</posx>
                <posy>{MESSAGE_Y}</posy>
                <width>{INNER_W}</width>
                <height>{MESSAGE_H}</height>
                <font>{FONT_BODY}</font>
                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                <label>$INFO[Window.Property(alert_message)]</label>
            </control>

            <!-- Accent-filled capsule, the same one the Filter picker's Done
                 button uses; a transparent <button> over it carries focus,
                 because a Kodi button cannot draw a 9-patch capsule itself. -->
            <control type="group">
                <posx>{BUTTON_X}</posx>
                <posy>{BUTTON_Y}</posy>
                <control type="image">
                    <width>{BUTTON_W}</width>
                    <height>64</height>
                    <colordiffuse>$INFO[Window.Property(accent_color)]</colordiffuse>
                    <texture border="32">capsule-h64.png</texture>
                </control>
                <control type="image">
                    <visible>Control.HasFocus({BUTTON_ID})</visible>
                    <width>{BUTTON_W}</width>
                    <height>64</height>
                    <colordiffuse>white</colordiffuse>
                    <texture border="32">capsule-h64-outline.png</texture>
                </control>
                <control type="label">
                    <width>{BUTTON_W}</width>
                    <height>64</height>
                    <align>center</align>
                    <aligny>center</aligny>
                    <font>{FONT_ROW_TITLE}</font>
                    <textcolor>$INFO[Window.Property(on_accent_color)]</textcolor>
                    <label>$INFO[Window.Property(alert_button)]</label>
                </control>
                <control type="button" id="{BUTTON_ID}">
                    <width>{BUTTON_W}</width>
                    <height>64</height>
                    <onup>{BUTTON_ID}</onup>
                    <ondown>{BUTTON_ID}</ondown>
                    <onleft>{BUTTON_ID}</onleft>
                    <onright>{BUTTON_ID}</onright>
                    <texturefocus>transparent-6px.png</texturefocus>
                    <texturenofocus>transparent-6px.png</texturenofocus>
                    <label></label>
                </control>
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
