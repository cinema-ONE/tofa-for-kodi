# -*- coding: utf-8 -*-
"""One render function per screen: reads that screen's template (its
current XML, verbatim, with shared blocks replaced by {fragment_name}
placeholders) from resources/lib/skin/templates/ and splices in the
fragments.py output. Templates are plain text, not Python string literals,
so the still-one-off parts of each screen stay easy to hand-edit.
"""
from __future__ import annotations

import os

from . import fragments
from . import icon_glyphs
from . import tokens as T
from .. import branding
from .. import settings_options
from .. import home_rows
from .. import settings_pages
from .. import foxes

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

NAV_LIST_ID = 3000


def _load(name: str) -> str:
    path = os.path.join(_TEMPLATES_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_main() -> str:
    """The merged Home/Browse/Discover/Search/Settings window (see
    windows/main.py:MainWindow). Renders "home", "browse", "discover" and
    "search", spliced into main.xml.tpl. nav_bar()'s ondown_target is only
    the static default for whichever section is active at render time
    (Home); every other section's real Down target is rewired at runtime
    instead (see MainWindow._section_down_targets), since a fragment baked
    once into static XML can't vary by which section is visible."""
    row_kwargs: dict[str, str] = {}

    def _home_row_block(group_ids, list_ids):
        """One full set of Home row slots, self-contained in its own chain.

        Rendered TWICE -- once per "Featured spotlight" state -- because the
        two states need two grouplist HEIGHTS and a grouplist's height cannot
        be conditional. See home_rows.HOME_ROW_GROUP_IDS_NOHERO.

        The two sets share their `row{i}_title` properties deliberately: only
        the ids differ, so nothing that FILLS a row has to know which set is
        live. Each chain is wired within its own ids, since the other set is
        hidden and Kodi will not move focus onto a hidden control."""
        blocks = []
        for idx, list_id in enumerate(list_ids):
            item_xml, focused_xml = fragments.poster_card(
                list_id, has_progress=True, caption_field="caption_meta",
                cell_w=T.ROW_CELL_W,
            )
            prev_id = list_ids[idx - 1] if idx else NAV_LIST_ID
            next_id = list_ids[idx + 1] if idx + 1 < len(list_ids) else list_id
            blocks.append(fragments.poster_row(
                group_id=group_ids[idx],
                list_id=list_id,
                title_property="row{0}_title".format(idx),
                onup=prev_id, ondown=next_id,
                item_xml=item_xml, focused_xml=focused_xml,
                list_width=T.row_bleed_width(T.HOME_LEFT),
                cell_w=T.ROW_CELL_W,
            ))
        return "\n\n".join(blocks)

    row_kwargs["home_rows"] = _home_row_block(
        home_rows.HOME_ROW_GROUP_IDS, home_rows.HOME_ROW_LIST_IDS)
    row_kwargs["home_rows_nohero"] = _home_row_block(
        home_rows.HOME_ROW_GROUP_IDS_NOHERO, home_rows.HOME_ROW_LIST_IDS_NOHERO)
    grid_item, grid_focused = fragments.poster_card(
        6200, has_progress=False, caption_field="caption_meta",
        extra_bottom_pad=T.GRID_GAP_BROWSE, size=fragments.POSTER_GRID,
    )

    watchlist_item_xml = fragments.watchlist_badge_item()
    watchlist_focused_xml = fragments.watchlist_badge_focused()
    discover_blocks = []
    strip_id = home_rows.DISCOVER_TAB_STRIP_ID
    for idx, list_id in enumerate(home_rows.DISCOVER_ROW_LIST_IDS):
        # Discover's focused card is the wide backdrop one, not the portrait
        # poster every other row uses -- see fragments.discover_card().
        item_xml, focused_xml = fragments.discover_card(list_id)
        prev_id = home_rows.DISCOVER_ROW_LIST_IDS[idx - 1] if idx else strip_id
        next_id = (home_rows.DISCOVER_ROW_LIST_IDS[idx + 1]
                   if idx + 1 < len(home_rows.DISCOVER_ROW_LIST_IDS) else list_id)
        discover_blocks.append(fragments.poster_row(
            group_id=home_rows.DISCOVER_ROW_GROUP_IDS[idx],
            list_id=list_id,
            title_property="discover_row{0}_title".format(idx),
            onup=prev_id, ondown=next_id,
            item_xml=item_xml, focused_xml=focused_xml,
            list_width=T.row_bleed_width(T.DISCOVER_LEFT),
            cell_w=T.ROW_CELL_W,
            pos=(T.DISCOVER_ROWS_X, T.DISCOVER_FOCUS_ROW_Y if idx else T.DISCOVER_ROWS_Y),
            block_h=T.DISCOVER_ROW_PITCH,
            indent="                    ",
        ))
    strip = fragments.discover_subtab_strip(
        list_id=strip_id, onup=NAV_LIST_ID, ondown=home_rows.DISCOVER_ROW_LIST_IDS[0])
    row_kwargs["discover_rows"] = "\n\n".join(
        fragments.discover_row_block(idx, xml, strip if idx == 0 else "")
        for idx, xml in enumerate(discover_blocks))
    row_kwargs["discover_filters"] = fragments.discover_filters_popover(
        home_rows.DISCOVER_FILTER_LIST_ID)

    # Browse (app 2.0): the landing's tiles, the view's two header pills and
    # its chip row. Chip words and widths are MainWindow's (_browse_sync_chips).
    tile_item, tile_focused = fragments.browse_tile(6020)
    folders_item, folders_focused = fragments.browse_header_pill(
        6130, glyph="$INFO[ListItem.Property(view_glyph)]",
        label="$INFO[ListItem.Property(view_label)]", width=T.BROWSE_FOLDERS_W)
    surprise_item, surprise_focused = fragments.browse_header_pill(
        6140, glyph=f"&#x{icon_glyphs.DICE_5:04X};", label="Surprise me",
        width=T.BROWSE_SURPRISE_W)
    chip_indent = "                    "
    sort_chip = fragments.browse_chip(6110, indent=chip_indent)
    unwatched_chip = fragments.browse_chip(6115, indent=chip_indent)
    filter_chip = fragments.browse_chip(6120, indent=chip_indent)
    genre_chips = "\n".join(fragments.browse_chip(6151 + i, indent=chip_indent)
                            for i in range(T.BROWSE_GENRE_CHIPS))

    alpha_item, alpha_focused = fragments.alpha_rail_pill(6220)

    (top_result_item, top_result_focused,
     top_result_text) = fragments.top_result_card(6805)
    movies_item, movies_focused = fragments.poster_card(
        6820, has_progress=False, caption_field="caption_meta"
    )
    shows_item, shows_focused = fragments.poster_card(
        6830, has_progress=False, caption_field="caption_meta"
    )
    # A custom collection whose name matches the query, as a row of its
    # members: the server's search returns no collections (vault #242).
    search_collection_item, search_collection_focused = fragments.poster_card(
        6870, has_progress=False, caption_field="caption_meta"
    )
    # Search's Discover shelf: same card as every other watchlist-badged
    # shelf; see MainWindow for why this list id is also registered into
    # self.discover_rows.
    search_discover_item, search_discover_focused = fragments.poster_card(
        6850,
        has_progress=False,
        caption_field="caption_meta",
        extra_item_xml=watchlist_item_xml,
        extra_focused_xml=watchlist_focused_xml,
    )

    # Search's Actors row is the SAME card as Detail's Cast & Crew, just
    # smaller and captioned with a title count instead of a role. It used to
    # be hand-written here, and had drifted: its photo carried a circular
    # diffuse mask but an <aspectratio>center</aspectratio> with no
    # scalediffuse="false", so Kodi mapped the mask onto the photo's own
    # size and the visible 130px window showed the middle of a much larger
    # circle -- i.e. a square. person_card() has always had that right.
    search_actor_item, search_actor_focused = fragments.person_card(
        6840, cell_width=T.SEARCH_ACTOR_CELL_W, cell_height=T.SEARCH_ACTOR_CELL_H,
        photo_size=T.SEARCH_ACTOR_PHOTO,
        placeholder_mode="icon", subtitle_property="titles_label")

    collection_item, collection_focused = fragments.collection_row(6210)
    custom_item, custom_focused = fragments.collection_row(6215)

    # Browse's "back to all collections" pill. Only drawn while a collection
    # is open; the real app keeps the viewer inside Browse and offers this
    # rather than a separate screen.
    # The folder view's two states with nothing to show; words set by
    # MainWindow._browse_load_folder_grid.
    folder_state = fragments.empty_state(
        visible="!String.IsEmpty(Window.Property(browse_folder_state))",
        glyph=f"&#x{icon_glyphs.FOLDER:04X};",
        title="$INFO[Window.Property(browse_folder_title)]",
        message="$INFO[Window.Property(browse_folder_message)]",
        posx=T.BROWSE_LEFT, width=T.BROWSE_GRID_W, indent="            ",
    )
    # ------------------------------------------------------------ settings
    # 8110, 8115 and 8120 are separate one-item lists sharing one layout: the
    # fragment gates its focus ring on Control.HasFocus(list_id), so the id
    # baked in here has to be the one that actually holds focus. 8110's copy
    # is reused for the other two only because all three rows look identical
    # at rest -- rendered once per id, rather than once and aliased.
    settings_action_item, settings_action_focused = fragments.settings_action_row(8110)
    settings_action_item_2, settings_action_focused_2 = fragments.settings_action_row(8120)
    settings_action_item_3, settings_action_focused_3 = fragments.settings_action_row(8115)

    # SWITCH, not PROFILE: the app groups Switch Profile and Switch Server
    # under one heading (build 17), and one eyebrow over both is what makes
    # them read as a pair of destinations rather than two unrelated actions.
    settings_switch_eyebrow = fragments.settings_group_eyebrow(
        posy=T.SETTINGS_SECTION_BAND, label="SWITCH", indent="                        ")
    settings_session_eyebrow = fragments.settings_group_eyebrow(
        posy=T.SETTINGS_SECTION_BAND, label="SESSION", indent="                        ")
    # The tail child's three sections. Only CONNECTION's row is focusable;
    # the other two report values, which is why they live here rather than in
    # children of their own (see the template).
    settings_account_tail = "\n".join((
        fragments.settings_group_eyebrow(
            posy=T.SETTINGS_ACCOUNT_TAIL_EMAIL_Y, label="ACCOUNT",
            indent="                        "),
        fragments.settings_value_row(
            posy=T.SETTINGS_ACCOUNT_TAIL_EMAIL_Y, label="Email",
            value_property="settings_email", indent="                        "),
        fragments.settings_group_eyebrow(
            posy=T.SETTINGS_ACCOUNT_TAIL_SERVER_Y, label="SERVER",
            indent="                        "),
        # The server's name only: 6 shows no user or library counts here.
        fragments.settings_value_row(
            posy=T.SETTINGS_ACCOUNT_TAIL_SERVER_Y, label="Server",
            value_property="settings_server", indent="                        "),
        fragments.settings_group_eyebrow(
            posy=T.SETTINGS_ACCOUNT_CONNECTION_ROW_Y, label="CONNECTION",
            indent="                        "),
    ))
    # width= is not optional here: the Account pane is the NARROW detail
    # column, and a switch positioned against the wide one lands off the
    # row entirely (the fragment's own docstring says so).
    # Two segments, not the rating row's three; the wide detail column here.
    settings_quality_eyebrow = fragments.settings_group_eyebrow(
        posy=T.SETTINGS_SECTION_BAND, label="QUALITY",
        indent="                        ")
    settings_direct_item, settings_direct_focused = fragments.settings_toggle_row(
        8130, width=T.SETTINGS_DETAIL_W)

    settings_episodes_item, settings_episodes_focused = fragments.settings_toggle_row(8310)
    settings_spoilers_item, settings_spoilers_focused = fragments.settings_toggle_row(8315)
    settings_watched_item, settings_watched_focused = fragments.settings_toggle_row(8312)
    settings_spotlight_item, settings_spotlight_focused = fragments.settings_toggle_row(8320)
    settings_pausescreen_item, settings_pausescreen_focused = fragments.settings_toggle_row(8495)
    settings_motion_item, settings_motion_focused = fragments.settings_toggle_row(8295)
    settings_homerow_editors = "".join(
        fragments.settings_home_row_editor(i, gid, lid) for i, (gid, lid) in enumerate(
            zip(home_rows.HOME_ROW_EDIT_GROUP_IDS, home_rows.HOME_ROW_EDIT_IDS)))
    # Value rows that open a picker: same shape as an action row, with the
    # current choice where the glyph would be.
    settings_region_item, settings_region_focused = fragments.settings_choice_row(
        8360, value_property="settings_region")
    # The rows picked in the right-column picker, one list each. Up/Down
    # within a group is XML; hops between groups are wired in main.py.
    _chain = [k for k, _l, _p in settings_options.CHOICE_ROWS if k != "rating"]
    _ids = {k: lid for k, lid, _p in settings_options.CHOICE_ROWS}
    _skip = [k for k, _l, _h in settings_options.SEGMENT_ROWS]
    settings_seg_groups = {}
    for _key, _lid, _prop in settings_options.CHOICE_ROWS:
        _name = {"rating": "settings_rating_group",
                 "quality": "settings_quality_group",
                 "nextup": "settings_nextup_group",
                 "nextupstyle": "settings_nextupstyle_group"}.get(
                     _key, "settings_seg_{0}_group".format(_key))
        if _key == "rating":
            _y, _up, _down = T.SETTINGS_SECTION_BAND, 8205, 8310
        else:
            _at = _chain.index(_key)
            _up = _ids[_chain[_at - 1]] if _at else 8000
            _down = _ids[_chain[_at + 1]] if _at + 1 < len(_chain) else _lid
            _y = (T.SETTINGS_SKIP_ROW_Y[_skip.index(_key)] if _key in _skip
                  else T.settings_stack_row_y(1) if _key == "nextupstyle"
                  else T.SETTINGS_SECTION_BAND)
        settings_seg_groups[_name] = fragments.settings_choice_list(
            _lid, value_property=_prop + "_value", posy=_y, onup=_up, ondown=_down)

    settings_audiolang_item, settings_audiolang_focused = fragments.settings_choice_row(
        8510, value_property="settings_audio_lang")
    settings_audiolang2_item, settings_audiolang2_focused = fragments.settings_choice_row(
        8540, value_property="settings_audio_lang2")
    settings_sublang_item, settings_sublang_focused = fragments.settings_choice_row(
        8520, value_property="settings_sub_lang")
    settings_sublang2_item, settings_sublang2_focused = fragments.settings_choice_row(
        8550, value_property="settings_sub_lang2")
    settings_alwayssubs_item, settings_alwayssubs_focused = fragments.settings_toggle_row(8530)
    settings_licences_item, settings_licences_focused = fragments.settings_action_row(
        8620, width=T.SETTINGS_DETAIL_W)
    settings_fonts_item, settings_fonts_focused = fragments.settings_action_row(
        8710, width=T.SETTINGS_DETAIL_W_WIDE)
    settings_artbudget_item, settings_artbudget_focused = fragments.settings_choice_row(
        8720, value_property="settings_art_budget")
    settings_artclear_item, settings_artclear_focused = fragments.settings_action_row(
        8730, width=T.SETTINGS_DETAIL_W_WIDE)

    scaffolds = []
    for page in settings_pages.PAGES:
        if page.built:
            continue
        scaffolds.append(fragments.empty_state(
            visible="String.IsEqual(Window.Property(settings_page),{0})".format(page.key),
            glyph="&#x{0:04X};".format(page.glyph),
            title="Not built yet",
            # Em dashes, not "--": this is label TEXT, so the XML-comment
            # rule does not apply and the literal hyphens would just render.
            message=(settings_pages.SCAFFOLD_MESSAGE_NATIVE if page.opens_native
                     else settings_pages.SCAFFOLD_MESSAGE),
            posx=T.SETTINGS_DETAIL_X,
            width=T.SETTINGS_DETAIL_W_WIDE,
            indent="            ",
        ))

    # The hero describes whichever home-row card is focused, so its synopsis
    # may only autoscroll while one of them actually holds focus. Derived
    # from the row ids rather than written out, so a tenth row cannot leave
    # the hero silently frozen on it.
    hero_scroll_when = " | ".join(
        "Control.HasFocus({0})".format(list_id)
        for list_id in home_rows.HOME_ROW_LIST_IDS)

    return _load("main.xml.tpl").format(
        toast=fragments.toast(),
        hero_scroll_when=hero_scroll_when,
        settings_info_panel=fragments.settings_info_panel(),
        settings_preview=fragments.settings_preview(),
        settings_picker_panel=fragments.settings_picker_panel(),
        settings_tab_strip=fragments.settings_tab_strip(
            list_id=8000, onup=3000, ondown=8110),
        settings_action_item=settings_action_item,
        settings_action_focused=settings_action_focused,
        settings_action_item_2=settings_action_item_2,
        settings_action_focused_2=settings_action_focused_2,
        settings_action_item_3=settings_action_item_3,
        settings_action_focused_3=settings_action_focused_3,
        settings_switch_eyebrow=settings_switch_eyebrow,
        settings_session_eyebrow=settings_session_eyebrow,
        settings_account_tail=settings_account_tail,
        settings_quality_eyebrow=settings_quality_eyebrow,
        settings_direct_item=settings_direct_item,
        settings_direct_focused=settings_direct_focused,
        settings_connection_note=fragments.settings_note_card(
            posy=T.SETTINGS_ACCOUNT_RELAY_NOTE_Y, title="Connection",
            body_property="settings_connection_body",
            height=T.SETTINGS_ACCOUNT_RELAY_NOTE_H),
        settings_fox_row=fragments.settings_choice_list(
            8205, value_property="settings_fox_value",
            posy=T.SETTINGS_SECTION_BAND, onup=8000, ondown=8900,
            dot_values=tuple("{0} Fox".format(n) for n, _h, _l in foxes.PRESETS),
            dot_colour="$INFO[Window.Property(settings_fox_dot)]"),
        # Group-relative, not absolute: inside a grouplist child, posy 0 is
        # the child's own top. Passing the eyebrow BAND puts the label at 0.
        settings_fox_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="THEME",
            indent="                        "),
        settings_mediacards_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="MEDIA CARDS",
            indent="                        "),
        settings_homescreen_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="HOME SCREEN",
            indent="                        "),
        settings_region_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="REGION",
            indent="                        "),
        settings_motion_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="MOTION",
            indent="                        "),
        settings_player_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="PLAYER",
            indent="                        "),
        settings_pausescreen_item=settings_pausescreen_item,
        settings_pausescreen_focused=settings_pausescreen_focused,
        settings_motion_item=settings_motion_item,
        settings_motion_focused=settings_motion_focused,
        settings_privacy_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="PRIVACY",
            indent="                        "),
        settings_about_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="ABOUT",
            indent="                        "),
        settings_device_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="THIS DEVICE",
            indent="                        "),
        # One card, two blocks: the name paints the whole fill, the Version
        # row beneath paints none -- the Server/Libraries pattern.
        settings_about_name_row=fragments.settings_name_row(
            posy=T.SETTINGS_SECTION_BAND,
            # addon.xml is what names this add-on; see branding.py. It used to
            # be a literal here, and addon.xml said "tofa" while this card
            # said "tofa for Kodi" -- the exact drift a second copy invites.
            title=branding.app_name(),
            subtitle=("An unofficial tofa client, engineered with the tofa team,",
                      "who also help support it"),
            width=T.SETTINGS_DETAIL_W, card_height=T.SETTINGS_ABOUT_CARD_H,
            indent="                        "),
        settings_version_row=fragments.settings_value_row(
            posy=T.SETTINGS_ABOUT_VERSION_Y, label="Version",
            value_property="settings_version", width=T.SETTINGS_DETAIL_W,
            height=T.SETTINGS_VALUE_ROW_STACKED_H, card_height=0,
            indent="                        "),
        settings_deviceid_row=fragments.settings_value_row(
            posy=T.SETTINGS_DEVICE_ROW1_Y, label="Device ID",
            value_property="settings_device_id", width=T.SETTINGS_DETAIL_W_WIDE,
            height=T.SETTINGS_ACTION_ROW_H, indent="                        "),
        settings_diagnostics_note=fragments.settings_note_card(
            posy=T.SETTINGS_SECTION_BAND, title="Playback diagnostics",
            body_property="settings_diagnostics_body"),
        settings_licences_item=settings_licences_item,
        settings_licences_focused=settings_licences_focused,
        settings_fonts_item=settings_fonts_item,
        settings_fonts_focused=settings_fonts_focused,
        settings_artcache_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="ARTWORK CACHE",
            indent="                        "),
        settings_artbudget_item=settings_artbudget_item,
        settings_artbudget_focused=settings_artbudget_focused,
        settings_artclear_item=settings_artclear_item,
        settings_artclear_focused=settings_artclear_focused,
        settings_support_rail=fragments.settings_qr_rail(
            eyebrow="REPORT A PROBLEM",
            texture="qr-support.png",
            caption_property="settings_support_caption",
        ),
        settings_region_item=settings_region_item,
        settings_region_focused=settings_region_focused,
        settings_skip_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="SKIP SEGMENTS",
            indent="                        "),
        settings_nextup_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="NEXT EPISODE",
            indent="                        "),
        settings_audio_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="AUDIO",
            indent="                        "),
        settings_subs_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="SUBTITLES",
            indent="                        "),
        settings_audiolang_item=settings_audiolang_item,
        settings_audiolang_focused=settings_audiolang_focused,
        settings_audiolang2_item=settings_audiolang2_item,
        settings_audiolang2_focused=settings_audiolang2_focused,
        settings_sublang_item=settings_sublang_item,
        settings_sublang_focused=settings_sublang_focused,
        settings_sublang2_item=settings_sublang2_item,
        settings_sublang2_focused=settings_sublang2_focused,
        settings_alwayssubs_item=settings_alwayssubs_item,
        settings_alwayssubs_focused=settings_alwayssubs_focused,
        settings_spotlight_item=settings_spotlight_item,
        settings_spotlight_focused=settings_spotlight_focused,
        settings_homeadd_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_HOMEADD_Y, label="ADD A ROW",
            indent="                        "),
        settings_homeadd_discover=fragments.settings_choice_list(
            8340, value_property="settings_homeadd_none",
            posy=T.SETTINGS_HOMEADD_Y, onup=8340, ondown=8345),
        settings_homeadd_genre=fragments.settings_choice_list(
            8345, value_property="settings_homeadd_none",
            posy=T.SETTINGS_HOMEADD_Y + T.SETTINGS_HOMEROW_PITCH,
            onup=8340, ondown=8345),
        **settings_seg_groups,
        settings_homerow_editors=settings_homerow_editors,
        settings_episodes_item=settings_episodes_item,
        settings_episodes_focused=settings_episodes_focused,
        settings_spoilers_item=settings_spoilers_item,
        settings_watched_item=settings_watched_item,
        settings_watched_focused=settings_watched_focused,
        settings_spoilers_focused=settings_spoilers_focused,
        settings_page_scaffolds="\n".join(scaffolds),
        settings_qr_rail=fragments.settings_qr_rail(
            eyebrow="MANAGE ACCOUNT",
            texture="qr-account.png",
            caption_property="settings_qr_caption",
        ),
        folder_state=folder_state,
        collection_item=collection_item,
        collection_focused=collection_focused,
        custom_item=custom_item,
        browse_sort_panel=fragments.browse_sort_panel(6230),
        browse_wall=fragments.browse_wall() + fragments.browse_poster_row(),
        browse_feature=fragments.browse_feature(),
        custom_focused=custom_focused,
        **T.template_kwargs(),
        logo_block=fragments.logo_block(),
        nav_bar=fragments.nav_bar(ondown_target=home_rows.HOME_ROW_LIST_IDS[0]),
        nav_avatar_button=fragments.nav_avatar_button(
            ondown_target=home_rows.HOME_ROW_LIST_IDS[0]),
        search_actor_item=search_actor_item,
        search_actor_focused=search_actor_focused,
        grid_item=grid_item,
        grid_focused=grid_focused,
        tile_item=tile_item,
        tile_focused=tile_focused,
        surprise_item=surprise_item,
        surprise_focused=surprise_focused,
        sort_chip=sort_chip,
        unwatched_chip=unwatched_chip,
        filter_chip=filter_chip,
        genre_chips=genre_chips,
        # No quality_* pair: the Quality pill went when its axis moved into
        # the Filter dialog, and the template stopped naming it then. The
        # fragment was still being built and passed for nothing.
        folders_item=folders_item,
        folders_focused=folders_focused,
        alpha_item=alpha_item,
        alpha_focused=alpha_focused,
        top_result_item=top_result_item,
        top_result_focused=top_result_focused,
        top_result_text=top_result_text,
        movies_item=movies_item,
        movies_focused=movies_focused,
        search_collection_item=search_collection_item,
        search_collection_focused=search_collection_focused,
        shows_item=shows_item,
        shows_focused=shows_focused,
        search_discover_item=search_discover_item,
        search_discover_focused=search_discover_focused,
        **row_kwargs,
    )


def render_detail() -> str:
    """The movie/show Detail screen (see windows/detail.py:DetailWindow).
    A separate xbmcgui.WindowXML, not part of the merged MainWindow;
    pushed open on top of whatever screen is current, same as the Player
    window. Page 2 is fragments.detail_page2(); detail.py sizes its blocks
    at runtime (_p2_layout)."""
    # 6200/6300/6310/6320/6410 = windows/detail.py's CAST_LIST, SIMILAR_LIST,
    # DISCOVER_LIST, COLLECTION_LIST and EPISODE_ROW, kept in sync by hand.
    cast_cards = fragments.person_card(
        6200, cell_width=T.DETAIL_P2_CAST_CELL, cell_height=260,
        photo_size=T.DETAIL_P2_CAST_PHOTO)
    compact = fragments.POSTER_COMPACT
    similar_cards = fragments.poster_card(
        6300, has_progress=False, caption_field="caption_meta", size=compact)
    discover_cards = fragments.poster_card(
        6310, has_progress=False, caption_field="caption_meta", size=compact,
        extra_item_xml=fragments.watchlist_badge_item(compact),
        extra_focused_xml=fragments.watchlist_badge_focused(compact),
    )
    collection_cards = fragments.poster_card(
        6320, has_progress=False, caption_field="caption_meta", size=compact,
        extra_item_xml=fragments.watchlist_badge_item(compact),
        extra_focused_xml=fragments.watchlist_badge_focused(compact),
    )
    page2 = fragments.detail_page2(
        cast_cards=cast_cards, collection_cards=collection_cards,
        similar_cards=similar_cards, discover_cards=discover_cards,
        episode_cards=fragments.episode_card(6410))
    # 9.7's scaffold on the two tabs that can come up empty. An empty tab is
    # NOT hidden: the real Apple TV app keeps it and answers it with this, as
    # captured on Besenbinden (2026-08-01), which has neither cast nor similar
    # titles. Glyphs and both sentences are that capture's, verbatim.
    # 5260 = windows/detail.py:DetailWindow.PILL_RETRY, kept in sync by hand
    # like every other id in this file.
    RETRY_PILL_ID = 5260

    # PAGE 1's LOAD FAILURE, 9.7's error flavour.
    #
    # Until this, a Detail page whose media_detail call failed drew the hero
    # scaffold with nothing in it: no backdrop, no logo, and an action row
    # holding whatever the XML defaults to. Reported from the cinema box
    # 2026-08-21, where the request took 15s to fail and the page came up
    # hollow with nothing on it to say why -- the same "blank screen, no
    # explanation" shape the relay work already has open against Home.
    #
    # This is the FIRST screen to wire 9.7's Retry button, which empty_state
    # has described and no caller has been able to use: the others have no
    # reload path, and Detail's is simply _load() again.
    load_error = fragments.empty_state(
        visible="String.IsEqual(Window.Property(detail_state),error)",
        glyph="&#x{0:X};".format(icon_glyphs.TRIANGLE_ALERT),
        title="$INFO[Window.Property(detail_error_title)]",
        message="$INFO[Window.Property(detail_error_message)]",
        flavour="error",
        indent="                ",
    )
    # "Retry" is 9.7's own word for this button, twice over; not "Try
    # Again". 280 wide rather than the action row's 360, whose width is set
    # by "Resume Playing" rather than by the shape.
    retry_pill = fragments.glass_pill(
        RETRY_PILL_ID,
        x=(T.SCREEN_W - 280) // 2,
        width=280,
        # Nothing above, below or beside it -- NAV_STOP is an id no control
        # has, which is how every list on this screen refuses to wrap.
        ondown=T.NAV_STOP,
        onleft=T.NAV_STOP,
        onright=T.NAV_STOP,
        label_xml="""<control type="label">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>280</width>
                                <height>64</height>
                                <align>center</align>
                                <aligny>center</aligny>
                                <font>{0}</font>
                                <textcolor>$INFO[Window.Property(text_primary)]</textcolor>
                                <label>Retry</label>
                            </control>""".format(T.FONT_BUTTON),
    )

    # Primary CTA pill is NOT fragments.py:glass_pill() (see that
    # function's docstring); it stays hand-typed in the template.
    # Action row geometry measured off the real Apple TV app (2026-07-31),
    # relative to the row's own left edge: Resume 0/360, Options 373/271,
    # Rewatch 658/270, Watchlist 948/244, all 78 tall. ORDER is
    # Resume, Options, Rewatch, Watchlist -- Rewatch sits AFTER Options
    # there, not before it as this screen used to have it.
    #
    # THE WIDTHS ARE NO LONGER THOSE. Every pill except the primary is 325
    # now (PILL_W), a deliberate divergence recorded in DIVERGENCES.md. The
    # app sizes each pill to its own content at runtime; a Kodi window's
    # geometry is resolved once at load, so we cannot. Matching its numbers
    # therefore only worked while every label was known at build time -- and
    # the edition pill's is a name the SERVER chooses, which is what broke
    # it: at the measured 250 a real name clipped to "192...". One width for
    # all of them holds the longest name in the reference library and ends
    # the 271-vs-270 kind of accident that a per-pill number invites.
    #
    # 325 rather than 330: five pills at 330 need 1747px and the row has
    # 1740 (origin 100, content margin 1840). Measured, not guessed.
    #
    # onleft/onright below are the all-visible defaults only. Rewatch and
    # Watchlist are both conditionally visible, so a hidden one would strand
    # focus mid-row; DetailWindow._wire_action_row() re-points the chain over
    # whatever is actually showing, the same runtime-rewire MainWindow uses
    # for its per-section Down targets.
    PILL_H = 78
    PILL_W = fragments.ACTION_PILL_W
    options_pill = fragments.glass_pill(
        5225, group_id=5226, x=717, width=PILL_W, height=PILL_H, ondown=6110, onleft=5210, onright=5220,
        # Hidden for a title this server does not hold: there is nothing to
        # pick a quality, audio track or subtitle for. The Apple TV app shows
        # exactly two pills there, Not in library and Watchlist
        # (atv-reference/detail-not-in-library.png); detail.py sets
        # hide_options on that path only, so every owned title is unchanged.
        visible="String.IsEmpty(Window.Property(hide_options)) + !String.IsEmpty(Window.Property(pills_packed))",
        label_xml=fragments.action_pill_content(
            PILL_W, "Options", "&#xE29A;", height=PILL_H,
            trailing_glyph="&#xE211;"),
    )
    rewatch_pill = fragments.glass_pill(
        5220, group_id=5221, x=1058, width=PILL_W, height=PILL_H, ondown=6110, onleft=5225, onright=5230,
        visible="!String.IsEmpty(Window.Property(show_rewatch)) + !String.IsEmpty(Window.Property(pills_packed))",
        # 11: rewatch is `arrow.counterclockwise` / Replay. It had no icon
        # at all before.
        #
        # NAMED, not a raw codepoint. It shipped as a hardcoded 0xE18B,
        # which is Lucide `toggle-left` -- a toggle SWITCH, drawn on the pill
        # where the reference app draws a counterclockwise arrow. Every other
        # raw codepoint in this file and the static XMLs was checked against
        # tools/lucide_font_src/codepoints.json at the same time and they are
        # all correct; this was the only one. `rotate-ccw` is also what the
        # player's -10s button uses, which is what the app does too.
        label_xml=fragments.action_pill_content(
            PILL_W, "Rewatch", "&#x{0:X};".format(icon_glyphs.ROTATE_CCW),
            height=PILL_H),
    )
    # Fourth pill: the EDITION/version selector, matching the real app's
    # action row (Play / Options / Watchlist / [box] 4K). File selection used
    # to hide inside Options under a "Quality" heading, which is neither what
    # 7.7 calls it nor what the app does -- 7.7 reserves Options for pre-play
    # Quality/Audio/Subtitles and gives the file picker its own surface.
    # Only drawn when the title actually has more than one available file,
    # which is the minority; detail.py sets show_version.
    # 330, and measured on "Theatrical Cut" rather than "1080p". The pill
    # was sized for a resolution token, which is what the real app shows --
    # but the app's own libraries are not ours to design for. Every
    # multi-edition title in the reference library is NAMED, and in five of
    # six both editions share a resolution ("1408" is 2160 twice, "1941"
    # 1080 twice), so a resolution token would print the same word on both
    # and answer nothing. Measured across those six: 168px for "Theatrical
    # Cut" and "Director's Cut", 174 for "Special Edition", and two outliers
    # at 209 and 291 that marquee. 330 covers the pattern that repeats;
    # sizing for the longest would make this pill wider than Play.
    version_pill = fragments.glass_pill(
        5240, group_id=5241, x=376, width=PILL_W, height=PILL_H, ondown=6110, onleft=5230,
        visible="!String.IsEmpty(Window.Property(show_version)) + !String.IsEmpty(Window.Property(pills_packed))",
        label_xml=fragments.action_pill_content(
            PILL_W, "$INFO[Window.Property(version_label)]", "&#xE529;",
            height=PILL_H, trailing_glyph="&#xE211;",
            # The one action pill whose text is the SERVER's to choose. An
            # edition name runs as long as whoever named the file wanted
            # ("Director's Cut Extended Remastered"), and no width that also
            # leaves room for Play, Options and Watchlist will hold that. It
            # scrolls while focused instead; "1080p" and "4K" do not move,
            # because Kodi only marquees text that overruns its box.
            marquee_focus_id=5240),
    )
    # The out-of-library page's second action, and the only one that UNDOES
    # something: withdraw a request this viewer already made. Its own pill
    # rather than a state of the primary one, because the primary becomes the
    # inert "Requested" label at the same moment this appears -- the real app
    # shows exactly that pair (atv-reference/detail-requestable-request-pill.png
    # captures the before; pressing Request turns it into
    # "Requested" + this). CIRCLE_X is the app's own glyph here.
    cancel_request_pill = fragments.glass_pill(
        5250, group_id=5251, x=376, width=PILL_W, height=PILL_H, ondown=6110, onleft=5210,
        visible="!String.IsEmpty(Window.Property(show_cancel_request)) + !String.IsEmpty(Window.Property(pills_packed))",
        label_xml=fragments.action_pill_content(
            PILL_W, "Cancel request", "&#xE084;",
            height=PILL_H),
    )
    watchlist_pill = fragments.glass_pill(
        5230, group_id=5231, x=1399, width=PILL_W, height=PILL_H, ondown=6110, onleft=5220,
        visible="!String.IsEmpty(Window.Property(show_watchlist)) + !String.IsEmpty(Window.Property(pills_packed))",
        # The +/- was baked into the LABEL TEXT ("+ Watchlist"), which is why
        # this pill could never align with the others -- its glyph was a
        # character in a string rather than an icon control. Now a real icon
        # that flips plus/check, the same pair Discover's card chip uses.
        # 18 lists the watchlist glyph as an open cross-client
        # inconsistency (bookmark vs plus/check); this follows the live app's
        # detail hero, which shows the plus.
        label_xml=fragments.action_pill_content(
            PILL_W, "Watchlist", "$INFO[Window.Property(watchlist_glyph)]",
            height=PILL_H),
    )

    return _load("detail.xml.tpl").format(
        load_error=load_error,
        retry_pill=retry_pill,
        RETRY_PILL_ID=RETRY_PILL_ID,
        **T.template_kwargs(),
        page2=page2,
        rewatch_pill=rewatch_pill,
        options_pill=options_pill,
        watchlist_pill=watchlist_pill,
        cancel_request_pill=cancel_request_pill,
        version_pill=version_pill,
        toast=fragments.toast(),
    )


def render_cardoptions() -> str:
    """7.2's card-options panel (windows/cardoptions.py:CardOptionsDialog).

    Height is fixed rather than sized to the row count: Kodi resolves a
    window's geometry once at load, so a panel that grew per invocation would
    need a re-render per open. The list simply scrolls if an option set ever
    exceeds MAX_VISIBLE_ROWS, which today's six-option maximum does not."""
    LIST_ID = 100
    MAX_VISIBLE_ROWS = 6

    pad = fragments.OPTIONS_PAD
    panel_w = fragments.OPTIONS_PANEL_W
    row_pitch = fragments.OPTIONS_ROW_H + fragments.OPTIONS_ROW_GAP

    title_y = pad + 30
    subtitle_y = title_y + 48
    rows_y = subtitle_y + 40
    rows_h = row_pitch * MAX_VISIBLE_ROWS
    panel_h = rows_y + rows_h + pad - fragments.OPTIONS_ROW_GAP

    option_row, option_row_focused = fragments.option_row(LIST_ID)
    return _load("cardoptions.xml.tpl").format(
        **T.template_kwargs(),
        LIST_ID=LIST_ID,
        PANEL_W=panel_w,
        PANEL_H=panel_h,
        SHADOW_W=panel_w + 84,
        SHADOW_H=panel_h + 84,
        PANEL_X=(T.SCREEN_W - panel_w) // 2,
        PANEL_Y=(T.SCREEN_H - panel_h) // 2,
        PAD=pad,
        INNER_W=panel_w - pad * 2,
        TITLE_Y=title_y,
        SUBTITLE_Y=subtitle_y,
        ROWS_Y=rows_y,
        ROWS_H=rows_h,
        OPT_ROW_PITCH=row_pitch,
        option_row=option_row,
        option_row_focused=option_row_focused,
    )



def _render_options_window(panel_w: int, detail_w: int) -> str:
    """The pre-play options window at a given width.

    Two windows come out of this one template: the Options panel and the
    Edition picker, which is the same panel with a much wider detail column
    (7.7's full row grammar rather than one fact per row). Separate windows
    rather than one resized at runtime, because a Kodi <itemlayout>'s column
    positions are resolved at load -- setWidth() would stretch the plate and
    leave the text where it was.

    Laid out for the MAXIMUM row count and shrunk at runtime by the dialog,
    which knows how many rows it is actually showing; both sides call
    fragments.playoptions_geometry() so they cannot disagree."""
    LIST_ID = 100
    option_row, option_row_focused = fragments.collapsible_row(
        LIST_ID, panel_w=panel_w, detail_w=detail_w)
    return _load("playoptions.xml.tpl").format(
        **T.template_kwargs(),
        **fragments.playoptions_geometry(fragments.PLAYOPT_MAX_ROWS, panel_w),
        LIST_ID=LIST_ID,
        GROUP_ID=200,
        SHADOW_ID=201,
        FILL_ID=202,
        OUTLINE_ID=203,
        HINT_ID=204,
        option_row=option_row,
        option_row_focused=option_row_focused,
    )


def render_playoptions() -> str:
    """7.7's pre-play options panel (windows/playoptions.py)."""
    return _render_options_window(fragments.PLAYOPT_PANEL_W, fragments.PLAYOPT_DETAIL_W)


def render_editions() -> str:
    """Detail's Edition picker (windows/playoptions.py:EditionDialog)."""
    return _render_options_window(fragments.EDITION_PANEL_W, fragments.EDITION_DETAIL_W)



def render_alert() -> str:
    """The skinned replacement for xbmcgui.Dialog().ok()
    (windows/cardoptions.py:AlertDialog).

    Fixed height, sized for a message of about five wrapped lines. Kodi
    resolves window geometry once at load and a <textbox> cannot report the
    height its text needed, so unlike the options panel this one cannot
    shrink to fit -- an over-long server error scrolls inside the box
    instead."""
    BUTTON_ID = 100
    PAD = 32
    PANEL_W = 760
    GLYPH_W = 40

    title_y = PAD
    message_y = title_y + 62
    message_h = 190
    button_y = message_y + message_h + 20
    panel_h = button_y + 64 + PAD
    button_w = 240

    return _load("alert.xml.tpl").format(
        **T.template_kwargs(),
        BUTTON_ID=BUTTON_ID,
        PANEL_W=PANEL_W,
        PANEL_H=panel_h,
        PANEL_X=(T.SCREEN_W - PANEL_W) // 2,
        PANEL_Y=(T.SCREEN_H - panel_h) // 2,
        SHADOW_W=PANEL_W + 84,
        SHADOW_H=panel_h + 84,
        PAD=PAD,
        INNER_W=PANEL_W - PAD * 2,
        GLYPH_W=GLYPH_W,
        TITLE_X=PAD + GLYPH_W + 14,
        TITLE_W=PANEL_W - PAD * 2 - GLYPH_W - 14,
        TITLE_Y=title_y,
        MESSAGE_Y=message_y,
        MESSAGE_H=message_h,
        BUTTON_X=(PANEL_W - button_w) // 2,
        BUTTON_Y=button_y,
        BUTTON_W=button_w,
    )


def render_person() -> str:
    """7.4's person/filmography page (windows/person.py:PersonWindow).

    One grid for both halves -- see the template's header for why the
    section headings stick rather than sitting inline.

    The plus chip is spliced into BOTH layouts, not just the focused one:
    on this screen it means "not in your library" (11's own pairing for
    `plus`) rather than an actionable watchlist toggle the way it does on
    Discover, so it has to read the same focused or not. person.py leaves
    the glyph property empty on owned titles, which is what hides it."""
    GRID_ID = 8000
    SECTION_LABEL_ID = 8010
    SECTION_COUNT_ID = 8011

    # 9.7's scaffold replaces the single left-aligned line this screen used
    # to draw. Title and message are properties because person.py has three
    # different things to say (nothing on file / couldn't reach the server /
    # couldn't load the filmography) and only two flavours to say them in.
    empty_state = fragments.empty_state(
        visible="String.IsEqual(Window.Property(person_state),empty)",
        glyph="&#x{0:X};".format(icon_glyphs.CLAPPERBOARD),
        title="$INFO[Window.Property(empty_title)]",
        message="$INFO[Window.Property(empty_message)]",
        indent="        ",
    )
    error_state = fragments.empty_state(
        visible="String.IsEqual(Window.Property(person_state),error)",
        glyph="&#x{0:X};".format(icon_glyphs.TRIANGLE_ALERT),
        title="$INFO[Window.Property(empty_title)]",
        message="$INFO[Window.Property(empty_message)]",
        flavour="error",
        indent="        ",
    )

    chip = fragments.watchlist_badge_item()
    size = fragments.POSTER_PERSON
    grid_item, grid_focused = fragments.poster_card(
        GRID_ID,
        has_progress=False,
        caption_field="caption_meta",
        extra_item_xml=chip,
        extra_focused_xml=chip,
        # The cell must be exactly the panel's <itemheight>, or Kodi ignores it.
        extra_bottom_pad=T.PERSON_CELL_H - fragments.poster_cell(size)[1],
        size=size,
        cell_w=T.PERSON_CELL_W,
        # 7.4's grid keeps the rating badge on the FOCUSED card, unlike
        # Browse/Home which clear it. Both are the real app's own behaviour
        # on their own screen: person-filmography.png shows 43 still on the
        # focused card, browse-full.png shows none.
        hide_rating_on_focus=False,
    )
    return _load("person.xml.tpl").format(
        **T.template_kwargs(),
        GRID_ID=GRID_ID,
        SECTION_LABEL_ID=SECTION_LABEL_ID,
        SECTION_COUNT_ID=SECTION_COUNT_ID,
        PILL_ID=8020,
        PERSON_NAME_W=T.PERSON_GRID_X - T.PERSON_NAME_X - 20,
        film_panel=fragments.person_film_panel(8030),
        grid_item=grid_item,
        grid_focused=grid_focused,
        empty_state=empty_state,
        error_state=error_state,
    )


def render_splash() -> str:
    """The cold-start splash (windows/splash.py).

    Deliberately has NO controls that can take focus and no <defaultcontrol>:
    it is shown, it plays, it closes itself. Anything focusable would let a
    keypress interact with a screen that has nothing to interact with.

    Built entirely from fragments rather than a template because it is two
    wipes and a backdrop -- there is no hand-written structure worth a .tpl.
    """
    # per_fox: the mark comes in 14 colours and the wordmark in one. That
    # asymmetry is the app's, measured on a live Android capture -- the Amber
    # profile's fox is amber and its "tofa" is still white.
    mark = fragments.splash_wipe(
        prefix="splash-mark", count=T.SPLASH_MARK_STRIPS,
        x=T.SPLASH_MARK_X, y=T.SPLASH_MARK_Y,
        width=T.SPLASH_MARK_W, height=T.SPLASH_MARK_H,
        start=T.SPLASH_MARK_DELAY, wipe=T.SPLASH_MARK_WIPE,
        fade=T.SPLASH_MARK_FADE, ease=True, per_fox=True)
    word = fragments.splash_wipe(
        prefix="splash-word", count=T.SPLASH_WORD_STRIPS,
        x=T.SPLASH_WORD_X, y=T.SPLASH_WORD_Y,
        width=T.SPLASH_WORD_W, height=T.SPLASH_WORD_H,
        start=T.SPLASH_WORD_DELAY, wipe=T.SPLASH_WORD_WIPE,
        fade=T.SPLASH_WORD_FADE, ease=False)
    glow_x = T.SPLASH_MARK_X + T.SPLASH_MARK_W // 2 - T.SPLASH_GLOW_W // 2
    glow_y = T.SPLASH_MARK_Y + T.SPLASH_MARK_H // 2 - T.SPLASH_GLOW_H // 2
    return f"""<window>
    <coordinates>
        <system>1</system>
        <posx>0</posx>
        <posy>0</posy>
    </coordinates>
    <controls>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{T.SCREEN_W}</width>
            <height>{T.SCREEN_H}</height>
            <texture colordiffuse="{T.SPLASH_BG}">white-square.png</texture>
        </control>
        <control type="image">
            <posx>{glow_x}</posx>
            <posy>{glow_y}</posy>
            <width>{T.SPLASH_GLOW_W}</width>
            <height>{T.SPLASH_GLOW_H}</height>
            <aspectratio>stretch</aspectratio>
            <texture colordiffuse="$INFO[Window.Property({T.SPLASH_GLOW_PROPERTY})]">splash-glow.png</texture>
            <animation effect="fade" start="0" end="100" time="600" tween="sine" easing="out">WindowOpen</animation>
        </control>
{mark}
{word}
        <!-- kodigui.XMLBase.onInit polls for control 666 to learn that the
             window's XML has actually loaded. A window without it is NOT
             merely un-probeable: onInit retries eight times at 250ms, so the
             splash blocked for two seconds, then declared its own XML broken,
             flashed a "Recompiling templates" notification, and ran that
             recovery path's xbmc.Player().stop(). Every other screen carries
             this control; the splash was written by hand and missed it. -->
        <control type="label" id="666">
            <visible>false</visible>
            <width>1</width>
            <height>1</height>
        </control>
    </controls>
</window>
"""


def render_profile() -> str:
    """Who's watching (app 2.0) and its PIN pad (windows/profile_select.py).

    Three portraits a row, one list per row: Python sizes and centres each
    row (a short last row centres itself) and moves between rows by column.
    The PIN pad is a state of the same window, as it is in the app."""
    W, TX, TY = T.WHO_TILE, T.WHO_TILE_X, T.WHO_TILE_Y
    CW, CH = T.WHO_CELL_W, T.WHO_CELL_H
    picker = "String.IsEqual(Window.Property(state),picker)"
    pin = "String.IsEqual(Window.Property(state),pin)"

    def img(x, y, w, h, texture, colour="", vis="", extra=""):
        c = f"<colordiffuse>{colour}</colordiffuse>" if colour else ""
        v = f"\n                    <visible>{vis}</visible>" if vis else ""
        return f"""
                <control type="image">{v}
                    <posx>{x}</posx><posy>{y}</posy><width>{w}</width><height>{h}</height>{c}{extra}
                    <texture>{texture}</texture>
                </control>"""

    def label(x, y, w, h, font, colour, text, vis="", align="center"):
        v = f"\n                    <visible>{vis}</visible>" if vis else ""
        return f"""
                <control type="label">{v}
                    <posx>{x}</posx><posy>{y}</posy><width>{w}</width><height>{h}</height>
                    <align>{align}</align><aligny>center</aligny>
                    <font>{font}</font>
                    <textcolor>{colour}</textcolor>
                    <label>{text}</label>
                </control>"""

    white = "$INFO[Window.Property(text_primary)]"
    accent = "$INFO[Window.Property(accent_color)]"

    def portrait(x, y, size, src, initials_font):
        """Disc, then the photo, the preset (150 of 220) or the initials on
        the profile's own gradient. `src` is "ListItem.Property" or a
        Window.Property prefix ("Window.Property(pin_avatar_")."""
        if src == "item":
            photo, preset = "ListItem.Property(photo_url)", "ListItem.Property(avatar_texture)"
            mono, initial = "ListItem.Property(monogram_texture)", "ListItem.Property(initial)"
        else:
            photo, preset = "Window.Property(pin_avatar_photo_url)", "Window.Property(pin_avatar_texture)"
            mono, initial = "Window.Property(pin_avatar_monogram)", "Window.Property(pin_avatar_initial)"
        no_photo = f"String.IsEmpty({photo})"
        bare = f"{no_photo} + String.IsEmpty({preset})"
        inset = round(size * 35 / 220)
        mask = '<aspectratio scalediffuse="false">scale</aspectratio>'
        return (img(x, y, size, size, "circle.png", "0xFF0C151C")
                + img(x, y, size, size, f"$INFO[{mono}]", vis=bare)
                + img(x, y, size, size, f"$INFO[{photo}]", vis=f"!{no_photo}", extra=mask)
                       .replace("<texture>$INFO", '<texture diffuse="circle.png">$INFO')
                + img(x + inset, y + inset, size - 2 * inset, size - 2 * inset,
                      f"$INFO[{preset}]", vis=f"{no_photo} + !String.IsEmpty({preset})", extra=mask)
                       .replace("<texture>$INFO", '<texture diffuse="circle.png">$INFO')
                + label(x, y, size, size, initials_font, white, f"$INFO[{initial}]", vis=bare))

    def lock_chip(x, y):
        """A glass disc at the portrait's lower right, a filled white lock."""
        locked = "!String.IsEmpty(ListItem.Property(locked))"
        return (img(x, y, 75, 75, "circle.png", "0x0FFFFFFF", vis=locked)
                + img(x, y, 75, 75, "hairline-ring-75.png", "0x24FFFFFF", vis=locked)
                + img(x + 25, y + 37, 25, 17, "white-square.png", "0xFFFFFFFF", vis=locked)
                + label(x, y, 75, 75, T.FONT_ICON_36, white,
                        f"&#x{icon_glyphs.LOCK:04X};", vis=locked))

    def zoom(xml):
        z = (f'\n                    <animation effect="zoom" start="100" end="108" '
             f'center="{TX + W // 2},{TY + W // 2}" time="140" tween="cubic" easing="out">Focus</animation>')
        return xml.replace("\n                </control>", z + "\n                </control>")

    tile = portrait(TX, TY, W, "item", T.FONT_PROFILE_INITIALS)
    hairline = img(TX, TY, W, W, "hairline-ring-220.png", "0x3BFFFFFF")
    active = img(TX, TY, W, W, "active-ring-220.png", "0xE6FFFFFF",
                 vis="!String.IsEmpty(ListItem.Property(active))")
    chip = lock_chip(TX + 143, TY + 142)
    name = label(0, TY + W + 16, CW, 30, T.FONT_CARD_TITLE, white, "$INFO[ListItem.Property(name)]")
    glow = img(TX - 10, TY - 10, W + 20, W + 20, "ring-glow-220.png", accent)
    rim = img(TX - 2, TY - 2, W + 4, W + 4, "outer-rim-220.png", accent)
    rest = tile + hairline + active + chip + name

    def gated(xml, gate):
        """Every top-level control in `xml` also needs `gate` to show."""
        out = []
        for part in xml.split("\n                <control ")[1:]:
            part = "\n                <control " + part
            if "<visible>" in part.split("</control>")[0] and part.count("<visible>") >= 1:
                part = part.replace("<visible>", f"<visible>{gate} + [", 1).replace(
                    "</visible>", "]</visible>", 1)
            else:
                part = part.replace(">", f">\n                    <visible>{gate}</visible>", 1)
            out.append(part)
        return "".join(out)

    rows = ""
    for r in range(T.WHO_ROWS):
        # A list draws its selected item's focused layout even unfocused, so
        # that layout shows the rest look until the row itself has focus.
        has = f"Control.HasFocus({800 + r})"
        focused = (gated(tile + hairline + active + chip, f"!{has}")
                   + gated(zoom(glow + tile + rim + chip), has) + name)
        rows += f"""
        <control type="list" id="{800 + r}">
            <visible>{picker}</visible>
            <posx>0</posx><posy>{300 + r * T.WHO_ROW_PITCH}</posy>
            <width>{3 * CW}</width><height>{CH}</height>
            <orientation>horizontal</orientation>
            <itemlayout width="{CW}" height="{CH}">{rest}
            </itemlayout>
            <focusedlayout width="{CW}" height="{CH}">{focused}
            </focusedlayout>
        </control>"""

    def pill(x, y, w, h, button_id, text, font, nav=""):
        return f"""
            <control type="group">
                <posx>{x}</posx><posy>{y}</posy>
                <control type="image">
                    <width>{w}</width><height>{h}</height>
                    <colordiffuse>0x1AFFFFFF</colordiffuse>
                    <texture border="{h // 2}">capsule-h{h}.png</texture>
                </control>
                <control type="image">
                    <visible>Control.HasFocus({button_id})</visible>
                    <width>{w}</width><height>{h}</height>
                    <colordiffuse>0xFFFFFFFF</colordiffuse>
                    <texture border="{h // 2}">capsule-h{h}-outline.png</texture>
                </control>{label(0, 0, w, h, font, white, text)}
                <control type="button" id="{button_id}">
                    <width>{w}</width><height>{h}</height>{nav}
                    <texturefocus>transparent-6px.png</texturefocus>
                    <texturenofocus>transparent-6px.png</texturenofocus>
                    <label></label>
                </control>
            </control>"""

    cancel = pill(T.WHO_CANCEL_X, T.WHO_CANCEL_Y, T.WHO_CANCEL_W, T.WHO_CANCEL_H, 820,
                  "$INFO[Window.Property(cancel_label)]", T.FONT_MICRO)

    dots = ""
    for i, x in enumerate(T.PIN_DOT_X):
        on = f"String.IsEqual(Window.Property(pin_dot_{i}),1)"
        dots += (img(x, T.PIN_DOT_Y, T.PIN_DOT, T.PIN_DOT, "circle.png", "white", vis=on)
                 + img(x, T.PIN_DOT_Y, T.PIN_DOT, T.PIN_DOT, "circle-outline.png", "0x40FFFFFF",
                       vis=f"!{on}"))

    # The keypad, 1-9 then a gap, 0 and backspace; Up/Down/Left/Right by grid.
    keys = [str(d) for d in range(1, 10)] + ["", "0", "back"]
    key_id = {k: (900 + int(k) if k.isdigit() else 910) for k in keys if k}
    grid = [keys[i:i + 3] for i in range(0, 12, 3)]

    def neighbour(row, col, dr, dc):
        r, c = row + dr, col + dc
        while 0 <= r < 4 and 0 <= c < 3:
            if grid[r][c]:
                return key_id[grid[r][c]]
            r, c = r + dr, c + dc
        return None

    pad = ""
    for row in range(4):
        for col in range(3):
            k = grid[row][col]
            if not k:
                continue
            kid = key_id[k]
            nav = ""
            for tag, (dr, dc) in (("onup", (-1, 0)), ("ondown", (1, 0)),
                                  ("onleft", (0, -1)), ("onright", (0, 1))):
                target = neighbour(row, col, dr, dc)
                if target is None and tag == "ondown":
                    target = 920
                if tag == "ondown" and k == "0":
                    target = 920
                if target is not None:
                    nav += f"\n                    <{tag}>{target}</{tag}>"
            focus = f"Control.HasFocus({kid})"
            text = (f"&#x{icon_glyphs.DELETE:04X};" if k == "back"
                    else f"$INFO[Window.Property(digit_{k})]")
            font = T.FONT_ICON_29 if k == "back" else T.FONT_PIN_DIGIT
            S = T.PIN_KEY
            pad += f"""
            <control type="group">
                <posx>{T.PIN_KEY_X[col]}</posx><posy>{T.PIN_KEY_Y[row]}</posy>
                <visible>{pin}</visible>{img(0, 0, S, S, "circle.png", "0x12FFFFFF", vis="!" + focus)}{img(0, 0, S, S, "circle.png", "$INFO[Window.Property(accent_pill_fill)]", vis=focus)}{img(0, 0, S, S, "circle-outline.png", accent, vis=focus)}{label(0, 0, S, S, font, white, text, vis="!" + focus)}{label(0, 0, S, S, font, accent, text, vis=focus)}
                <control type="button" id="{kid}">
                    <width>{S}</width><height>{S}</height>{nav}
                    <texturefocus>transparent-6px.png</texturefocus>
                    <texturenofocus>transparent-6px.png</texturenofocus>
                    <label></label>
                </control>
            </control>"""

    back = pill(T.PIN_BACK_X, T.PIN_BACK_Y, T.PIN_BACK_W, T.PIN_BACK_H, 920,
                "$INFO[Window.Property(pin_exit_label)]", T.FONT_ROW_TITLE,
                nav="\n                    <onup>900</onup>")
    pin_avatar = portrait(T.PIN_AVATAR_X, T.PIN_AVATAR_Y, T.PIN_AVATAR,
                          "pin", T.FONT_TOP_RESULT_TITLE)
    pin_pane = f"""
        <!-- The whole pane shakes on a wrong PIN: profile_select flips
             pin_shake, and a conditional slide runs each leg. -->
        <control type="group">
            <animation effect="slide" start="0,0" end="13,0" time="45" tween="sine" condition="!String.IsEmpty(Window.Property(pin_shake))">Conditional</animation>
            <control type="group">
                <visible>{pin}</visible>{pin_avatar}{label(0, T.PIN_HEADING_Y, 1920, 40, T.FONT_SETTINGS_ROW, white, "$INFO[Window.Property(pin_heading)]")}{dots}
                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(pin_error))</visible>
                    <posx>0</posx><posy>{T.PIN_ERROR_Y}</posy><width>1920</width><height>40</height>
                    <align>center</align><aligny>center</aligny>
                    <font>tofa_font_caption</font>
                    <textcolor>0xFFF87171</textcolor>
                    <label>$INFO[Window.Property(pin_error)]</label>
                    <animation effect="fade" start="0" end="100" time="140">Visible</animation>
                </control>
            </control>{pad}
            <control type="group">
                <visible>{pin}</visible>{back}
            </control>
        </control>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<window>
    <defaultcontrol always="true">666</defaultcontrol>
    <backgroundcolor>0x00000000</backgroundcolor>
    <coordinates>
        <system>0</system>
    </coordinates>
    <controls>{img(0, 0, 1920, 1080, "white-square.png", T.CANVAS)}
        <control type="label" id="810">
            <visible>{picker}</visible>
            <posx>0</posx><posy>{300 - T.WHO_TITLE_ABOVE}</posy><width>1920</width><height>100</height>
            <align>center</align><aligny>center</aligny>
            <font>{T.FONT_WHOS_WATCHING}</font>
            <textcolor>{white}</textcolor>
            <label>$INFO[Window.Property(heading)]</label>
        </control>{rows}
        <control type="group">
            <visible>{picker}</visible>{cancel}
        </control>{pin_pane}
        <!-- kodigui framework sentinel. -->
        <control type="label" id="666">
            <visible>false</visible>
            <width>1</width>
            <height>1</height>
        </control>
    </controls>
</window>
"""
