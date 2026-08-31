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
                list_id, has_progress=True, caption_field="caption_meta"
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
            ))
        return "\n\n".join(blocks)

    row_kwargs["home_rows"] = _home_row_block(
        home_rows.HOME_ROW_GROUP_IDS, home_rows.HOME_ROW_LIST_IDS)
    row_kwargs["home_rows_nohero"] = _home_row_block(
        home_rows.HOME_ROW_GROUP_IDS_NOHERO, home_rows.HOME_ROW_LIST_IDS_NOHERO)
    grid_item, grid_focused = fragments.poster_card(
        6200, has_progress=False, caption_field="caption_meta",
        extra_bottom_pad=T.GRID_GAP_BROWSE,
    )

    watchlist_item_xml = fragments.watchlist_badge_item()
    watchlist_focused_xml = fragments.watchlist_badge_focused()
    discover_blocks = []
    for idx, list_id in enumerate(home_rows.DISCOVER_ROW_LIST_IDS):
        # Discover's focused card is the wide backdrop one, not the portrait
        # poster every other row uses -- see fragments.discover_card().
        item_xml, focused_xml = fragments.discover_card(list_id)
        prev_id = home_rows.DISCOVER_ROW_LIST_IDS[idx - 1] if idx else NAV_LIST_ID
        next_id = (home_rows.DISCOVER_ROW_LIST_IDS[idx + 1]
                   if idx + 1 < len(home_rows.DISCOVER_ROW_LIST_IDS) else list_id)
        discover_blocks.append(fragments.poster_row(
            group_id=home_rows.DISCOVER_ROW_GROUP_IDS[idx],
            list_id=list_id,
            title_property="discover_row{0}_title".format(idx),
            onup=prev_id, ondown=next_id,
            item_xml=item_xml, focused_xml=focused_xml,
            list_width=T.row_bleed_width(T.DISCOVER_LEFT),
        ))
    row_kwargs["discover_rows"] = "\n\n".join(discover_blocks)

    # Discover's four tab pills. Each is its own 1-item list (see
    # fragments.discover_tab_pill), wired into a ring so Left/Right cycles
    # through them; Down always lands on the first row slot, which
    # MainWindow re-points per tab at runtime the same way Home's rows are.
    tab_ids = home_rows.DISCOVER_TAB_LIST_IDS
    tab_x = fragments.discover_tab_positions()
    tab_blocks = []
    for idx, (key, _label, width) in enumerate(home_rows.DISCOVER_TABS):
        tab_blocks.append(fragments.discover_tab_pill(
            tab_ids[idx],
            tab_key=key,
            width=width,
            posx=tab_x[idx],
            onleft=tab_ids[idx - 1] if idx else tab_ids[0],
            onright=tab_ids[idx + 1] if idx + 1 < len(tab_ids) else tab_ids[-1],
            ondown=home_rows.DISCOVER_ROW_LIST_IDS[0],
        ))
    row_kwargs["discover_tabs"] = "\n\n".join(tab_blocks)

    sidebar_item, sidebar_focused = fragments.sidebar_row(6000)
    sidebar_lib_item, sidebar_lib_focused = fragments.sidebar_row(6010)
    # NO PREFIXES on this row. Every pill now shows its VALUE and nothing
    # else -- "Date Added", not "Sort: Date Added" -- because the icon
    # already says which axis it is and the words were eating the column the
    # values need (fragments._pill_label has the measurements). It also makes
    # the three pills read as one row of values rather than three sentences.
    #
    # This is a deliberate divergence: the real app keeps "Sort: Title" (read
    # off Android 0.1.11 and the Apple TV capture, which agree). It does not
    # need the room -- its pills are content-width, ours are a fixed 346.
    # The Sort glyph is a PROPERTY, not a literal: it states the direction the
    # grid is actually running (arrow-down descending, arrow-up ascending, and
    # only Shuffle keeps the generic up-and-down pair, having no direction).
    # MainWindow._browse_sort_glyph writes it -- and it is the only thing on
    # screen that can report a reverse toggle, which leaves the label alone.
    sort_item, sort_focused = fragments.browse_pill(
        6110, icon="$INFO[ListItem.Property(sort_glyph)]",
        label_prefix="", label_property="sort_label", always_active=True,
    )
    # Filter needs the whole column either way: it names up to three axes at
    # once. MainWindow._browse_filter_label writes the entire line, including
    # the bare word "Filter" when nothing is set (which is what the real app
    # shows there permanently). See _pill_label.
    filter_item, filter_focused = fragments.browse_pill(
        6120, icon="&#xE460;",
        label_prefix="", label_property="filter_label",
    )
    # Genre joins the other two: no prefix, and MainWindow._browse_genre_label
    # writes the bare word "Genre" when nothing is picked, the genre's own
    # name when something is.
    genre_item, genre_focused = fragments.browse_pill(
        6100, icon="&#xE17F;",
        label_prefix="", label_property="genre_label",
    )

    alpha_item, alpha_focused = fragments.alpha_rail_pill(6220)

    (top_result_item, top_result_focused,
     top_result_text) = fragments.top_result_card(6805)
    movies_item, movies_focused = fragments.poster_card(
        6820, has_progress=False, caption_field="caption_meta"
    )
    shows_item, shows_focused = fragments.poster_card(
        6830, has_progress=False, caption_field="caption_meta"
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

    collection_item, collection_focused = fragments.collection_card(6210)

    # Browse's "back to all collections" pill. Only drawn while a collection
    # is open; the real app keeps the viewer inside Browse and offers this
    # rather than a separate screen.
    collection_back = fragments.glass_pill(
        # height 58, not an invented 56: glass_pill() builds its texture
        # name from the height, and capsule-h56.png does not exist, so the
        # pill rendered as bare text with no glass behind it.
        6260, group_id=6261, x=1526, width=346, height=64, ondown=6200, onleft=6100,
        visible="!String.IsEmpty(Window.Property(browse_heading))",
        label_xml=fragments.action_pill_content(
            346, "All Collections", "&#xE06E;", height=64),
    )

    # ------------------------------------------------------------ settings
    settings_nav_item, settings_nav_focused = fragments.settings_nav_row(8000)
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
        # One card, two rows: the app draws a single 153-tall fill behind
        # Server and Libraries with no divider between them, so the first row
        # paints the whole card and the second paints none.
        fragments.settings_value_row(
            posy=T.SETTINGS_ACCOUNT_TAIL_SERVER_Y, label="Server",
            value_property="settings_server",
            height=T.SETTINGS_VALUE_ROW_STACKED_H,
            card_height=T.SETTINGS_VALUE_ROW_STACKED_H * 2,
            indent="                        "),
        fragments.settings_value_row(
            posy=T.SETTINGS_ACCOUNT_TAIL_SERVER_Y + T.SETTINGS_VALUE_ROW_STACKED_H,
            label="Libraries", value_property="settings_libraries",
            height=T.SETTINGS_VALUE_ROW_STACKED_H, card_height=0,
            indent="                        "),
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

    settings_fox_item, settings_fox_focused = fragments.settings_fox_tile(8200)
    settings_episodes_item, settings_episodes_focused = fragments.settings_toggle_row(8310)
    settings_spotlight_item, settings_spotlight_focused = fragments.settings_toggle_row(8320)
    settings_homerow_item, settings_homerow_focused = fragments.settings_home_row(8330)
    # One editor row per slot, each a DIRECT child of the appearance
    # grouplist so the grouplist chains them for up/down and scrolls the
    # focused one into view. Slots past the account's row count hide
    # themselves on an empty title property, which also takes them out of
    # that chain.
    settings_homerow_editors = "".join(
        fragments.settings_home_row_editor(i) for i in range(home_rows.MAX_HOME_ROWS))
    settings_add_row_item, settings_add_row_focused = fragments.settings_add_row(8340)
    # Value rows that open a picker: same shape as an action row, with the
    # current choice where the glyph would be.
    settings_region_item, settings_region_focused = fragments.settings_choice_row(
        8360, value_property="settings_region")
    # One segmented row per segment type, wider pills than the media-cards
    # one because "Do nothing" is nearly the default pill's whole width.
    # The eight rows whose options are individually focusable pills. One
    # fragment, one id map (settings_options.SEGMENTED_GROUPS), so a new
    # segmented setting is a table entry rather than another hand-built row.
    settings_seg_groups = {}
    for _key, _gid, _sids, _prop in settings_options.SEGMENTED_GROUPS:
        _name = {"rating": "settings_rating_group",
                 "quality": "settings_quality_group",
                 "nextup": "settings_nextup_group"}.get(
                     _key, "settings_seg_{0}_group".format(_key))
        _w = (T.SETTINGS_NEXTUP_PILL_W if _key == "nextup"
              else T.SETTINGS_SEGMENT_PILL_W)
        # Each row keeps the posy its list carried: these sit in a plain
        # group, where children do NOT stack themselves, and dropping the
        # posy piled all five skip rows on one another.
        _skip = [k for k, _l, _h in settings_options.SEGMENT_ROWS]
        if _key in _skip and _skip.index(_key):
            _y = T.SETTINGS_SKIP_ROW_Y[_skip.index(_key)]
        else:
            _y = T.SETTINGS_SECTION_BAND
        settings_seg_groups[_name] = fragments.settings_segmented_group(
            _gid, _sids, prop=_prop, seg_width=_w, posy=_y)

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
        settings_nav_item=settings_nav_item,
        settings_nav_focused=settings_nav_focused,
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
        settings_fox_item=settings_fox_item,
        settings_fox_focused=settings_fox_focused,
        # Group-relative, not absolute: inside a grouplist child, posy 0 is
        # the child's own top. Passing the eyebrow BAND puts the label at 0.
        settings_fox_eyebrow=fragments.settings_group_eyebrow(
            posy=T.SETTINGS_SECTION_BAND, label="FOX",
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
        settings_add_row_item=settings_add_row_item,
        settings_add_row_focused=settings_add_row_focused,
        **settings_seg_groups,
        settings_homerow_editors=settings_homerow_editors,
        settings_homerow_item=settings_homerow_item,
        settings_homerow_focused=settings_homerow_focused,
        settings_episodes_item=settings_episodes_item,
        settings_episodes_focused=settings_episodes_focused,
        settings_page_scaffolds="\n".join(scaffolds),
        settings_qr_rail=fragments.settings_qr_rail(
            eyebrow="MANAGE ACCOUNT",
            texture="qr-account.png",
            caption_property="settings_qr_caption",
        ),
        collection_back=collection_back,
        collection_item=collection_item,
        collection_focused=collection_focused,
        **T.template_kwargs(),
        logo_block=fragments.logo_block(),
        nav_bar=fragments.nav_bar(ondown_target=home_rows.HOME_ROW_LIST_IDS[0]),
        search_actor_item=search_actor_item,
        search_actor_focused=search_actor_focused,
        grid_item=grid_item,
        grid_focused=grid_focused,
        sidebar_item=sidebar_item,
        sidebar_focused=sidebar_focused,
        sidebar_lib_item=sidebar_lib_item,
        sidebar_lib_focused=sidebar_lib_focused,
        sort_item=sort_item,
        sort_focused=sort_focused,
        filter_item=filter_item,
        filter_focused=filter_focused,
        # No quality_* pair: the Quality pill went when its axis moved into
        # the Filter dialog, and the template stopped naming it then. The
        # fragment was still being built and passed for nothing.
        genre_item=genre_item,
        genre_focused=genre_focused,
        alpha_item=alpha_item,
        alpha_focused=alpha_focused,
        top_result_item=top_result_item,
        top_result_focused=top_result_focused,
        top_result_text=top_result_text,
        movies_item=movies_item,
        movies_focused=movies_focused,
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
    window. Cast and Crew are two separate wrapping grids stacked in one
    grouplist, so person_card() is called twice. CAST_TILE/CAST_PHOTO give
    CAST_COLS columns across the panel, matching the real app; each panel's
    HEIGHT is set at runtime from its item count (see
    windows/detail.py:_size_person_panels), so the number in the template is
    only a pre-data placeholder."""
    # 6200/6210/6300 = windows/detail.py:DetailWindow.CAST_LIST/CREW_LIST/
    # SIMILAR_LIST -- not imported from there (screens.py stays
    # independent of window classes); kept in sync by hand like every
    # other hardcoded id in this file.
    cast_item, cast_focused = fragments.person_card(
        6200, cell_height=T.CAST_TILE, photo_size=T.CAST_PHOTO)
    crew_item, crew_focused = fragments.person_card(
        6210, cell_height=T.CAST_TILE, photo_size=T.CAST_PHOTO)
    # More Like This is TWO labelled shelves, not one grid: captured off the
    # real Apple TV app (internal-docs/atv-reference/detail-more-like-this.png,
    # 2026-08-01). "More Like This" holds what the library already has;
    # "More to Discover" holds the requestable ones and puts the `plus`
    # not-in-library chip on every card, exactly as Discover's own rows do.
    # So the category axis IS the owned/requestable split the API returns --
    # an earlier note in this repo guessed it wasn't and told the next reader
    # not to assume it; the capture settles it.
    similar_item, similar_focused = fragments.poster_card(
        6300, has_progress=False, caption_field="caption_meta")
    discover_item, discover_focused = fragments.poster_card(
        6310, has_progress=False, caption_field="caption_meta",
        extra_item_xml=fragments.watchlist_badge_item(),
        extra_focused_xml=fragments.watchlist_badge_focused(),
    )
    # Standard shelf metrics, unchanged: they already reproduce the app's row
    # pitch here (ours 560, measured 556 art-top to art-top).
    similar_rows = "\n\n".join((
        fragments.poster_row(
            group_id=6301, list_id=6300, title_property="similar_row_title",
            onup=6130, ondown=6310,
            item_xml=similar_item, focused_xml=similar_focused,
            list_width=T.row_bleed_width(100),
            indent="                        ",
        ),
        fragments.poster_row(
            group_id=6311, list_id=6310, title_property="discover_row_title",
            onup=6300, ondown=6310,
            item_xml=discover_item, focused_xml=discover_focused,
            list_width=T.row_bleed_width(100),
            indent="                        ",
        ),
    ))
    episode_item, episode_focused = fragments.episode_card(6410)
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

    cast_empty = fragments.empty_state(
        visible="String.IsEmpty(Window.Property(has_cast_content))",
        glyph="&#x{0:X};".format(icon_glyphs.USERS),
        title="No cast information",
        message="We don't have credits for this title yet.",
    )
    # The error flavour 9.7 defines separately -- not reaching the server is
    # not the same answer as having nothing, even though our first pass
    # rendered one sentence for both. No Apple TV capture of this one exists,
    # so only the wording is ours; the layout is the shared scaffold.
    similar_empty = fragments.empty_state(
        visible="String.IsEqual(Window.Property(similar_state),empty)",
        glyph="&#x{0:X};".format(icon_glyphs.GALLERY_VERTICAL_END),
        title="Nothing similar yet",
        message="We couldn't find related titles for this one.",
    ) + "\n" + fragments.empty_state(
        visible="String.IsEqual(Window.Property(similar_state),error)",
        glyph="&#x{0:X};".format(icon_glyphs.GALLERY_VERTICAL_END),
        title="Couldn't load related titles",
        message="Something went wrong reaching the server. Try again later.",
    )
    # Season sidebar (id 6400) stays hand-typed in detail.xml.tpl, not
    # fragments.py:sidebar_row(): its itemlayout has real structural
    # asymmetries (single always-on fill, no active/inactive count-label
    # split) that sidebar_row() doesn't support.

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
        cast_item=cast_item,
        cast_focused=cast_focused,
        crew_item=crew_item,
        crew_focused=crew_focused,
        similar_rows=similar_rows,
        similar_empty=similar_empty,
        cast_empty=cast_empty,
        episode_item=episode_item,
        episode_focused=episode_focused,
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
    grid_item, grid_focused = fragments.poster_card(
        GRID_ID,
        has_progress=False,
        caption_field="caption_meta",
        extra_item_xml=chip,
        extra_focused_xml=chip,
        # Grid pitch, not row pitch -- see GRID_GAP_* in tokens.py. Must
        # match the panel's <itemheight> ({GRID_CELL_H}) or Kodi ignores it.
        extra_bottom_pad=T.GRID_GAP,
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
