<?xml version="1.0" encoding="UTF-8"?>
<!--
  Card options panel TEMPLATE, rendered to script-tofa-cardoptions.xml by
  resources/lib/skin/screens.py:render_cardoptions(). DO NOT HAND-EDIT the
  rendered file.

  TV-DESIGN 7.2: the long-press context menu for any poster/episode card,
  and the Detail hero's Options pill. Centred glass card over a black 58%
  scrim; rows are icon + label, destructive rows carry red ink at rest.

  On Kodi the trigger is the remote's context/menu key rather than a real
  long-press. Kodi's focus engine has no press-phase notion for Select, and
  10.2 sanctions the dedicated key explicitly: "Where the remote has a
  dedicated context/menu key that is free at that moment, map it as an
  alternative trigger".

  A single <list> carries every row rather than one control per action.
  The option set is conditional (7.2 lists six conditions), so the row count
  is only known at runtime, and one fixed itemheight is exactly what a
  uniform 68pt row wants.
-->
<!-- Bare <window>, no type/id: Kodi assigns a WindowXMLDialog's id at
     runtime, and declaring one makes it a fixed-id window whose id no longer
     matches getCurrentWindowDialogId(). Every setProperty() then lands on a
     window that isn't the one rendering, so the header and every textcolor
     bound to a Window.Property come out empty. That is exactly how this
     first showed up: only the destructive row, whose red is a literal, was
     legible. Every other window in this skin is a bare <window> too. -->
<window>
    <defaultcontrol always="true">{LIST_ID}</defaultcontrol>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <!-- Scrim. 7.2 says black 58%; a plain flat fill rather than a
             gradient because the panel is centred, so no side "owns" the
             copy the way Discover's open card has one. -->
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

            <!-- Drop shadow. 7.2: "shadow black 62% blur 42 y18 (floating,
                 so shadow allowed)", the one documented exception to 4's
                 rule that resting chrome casts none. Drawn first, inflated
                 by the blur on every side and pushed down by the stated y18.
                 Its 9-patch border covers blur + radius so the soft corner
                 is never stretched. -->
            <control type="image">
                <posx>-42</posx>
                <posy>-24</posy>
                <width>{SHADOW_W}</width>
                <height>{SHADOW_H}</height>
                <colordiffuse>0x9E000000</colordiffuse>
                <texture border="64">panel-shadow-r22.png</texture>
            </control>

            <!-- Panel: opaque dark fill + hairline. NOT a translucent glass
                 wash: 4 says a platform without real blur substitutes a
                 "dark tint at ~85-92% opacity", naming Kodi, and 13 makes
                 that unconditional for Kodi-class clients. Hairline is
                 BORDER_FLOATING (white 16%), the value 7.2 names.

                 Radius 22 per 7.2, on its own
                 asset rather than a 9-patch of a shared capsule, because a
                 9-patch corner draws UNSCALED: the asset's radius must equal
                 the border it is sliced at. See tools/gen_panel_assets.py. -->
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

            <!-- Header. The eyebrow only renders for the Detail hero
                 variant, which 7.2 gives an "Options" eyebrow and an
                 explicit Cancel row; card long-press has neither. -->
            <control type="label">
                <posx>{PAD}</posx>
                <posy>{PAD}</posy>
                <width>{INNER_W}</width>
                <height>22</height>
                <font>{FONT_EYEBROW}</font>
                <textcolor>$INFO[Window.Property(text_tertiary)]</textcolor>
                <label>$INFO[Window.Property(options_eyebrow)]</label>
                <visible>!String.IsEmpty(Window.Property(options_eyebrow))</visible>
            </control>
            <control type="label">
                <posx>{PAD}</posx>
                <posy>{TITLE_Y}</posy>
                <width>{INNER_W}</width>
                <height>44</height>
                <font>{FONT_DIALOG_TITLE}</font>
                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                <!-- Marquee: an episode title plus its show name overflows
                     {INNER_W} routinely, and this is the one line that says
                     WHAT the panel is about to act on, so a truncated
                     version is the wrong thing to leave on screen. Kodi
                     only scrolls a label that actually overflows, so a
                     short title stays still.

                     scrollsuffix is EM SPACES (U+2003): Kodi discards a
                     text node made only of ASCII whitespace, so plain
                     spaces arrive empty and the text wraps with no gap. -->
                <scroll>true</scroll>
                <scrollsuffix>   </scrollsuffix>
                <label>$INFO[Window.Property(options_title)]</label>
            </control>
            <control type="label">
                <posx>{PAD}</posx>
                <posy>{SUBTITLE_Y}</posy>
                <width>{INNER_W}</width>
                <height>28</height>
                <font>{FONT_METADATA}</font>
                <textcolor>$INFO[Window.Property(text_secondary)]</textcolor>
                <label>$INFO[Window.Property(options_subtitle)]</label>
                <visible>!String.IsEmpty(Window.Property(options_subtitle))</visible>
            </control>

            <!-- itemwidth/itemheight are REQUIRED as their own tags, not just
                 as attributes on the layouts below. Without them the list
                 rendered every row's plate but left all but the last row's
                 label and icon empty, which looks like a data problem and
                 isn't one. Copied from the working picker dialog.

                 The self-targeting nav tags keep focus inside the panel:
                 a dialog has nowhere else for it to go. -->
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
                <scrolltime>{SCROLLTIME}</scrolltime>
{option_row}
{option_row_focused}
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
