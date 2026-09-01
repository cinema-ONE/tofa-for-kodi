# -*- coding: utf-8 -*-
"""TV-DESIGN 7.7's pre-play options panel: Quality / Audio / Subtitles for
the file the Detail hero is about to play.

Reached from the Options pill. 7.7 is explicit that a selection is persisted
the moment it is made and never begins playback, so this panel has no Play
affordance and Back is not a cancel -- the picks are already applied by the
time you can press it, which is what the collapsed header row shows.

Collapsed by default, one section expanded at a time. That is a documented
divergence from 7.7's flat form; the reasoning is in
fragments.py:collapsible_row(), which owns the row grammar.

What each section actually controls is NOT symmetric, and the difference
matters more than the shared appearance suggests:

  Quality    the SERVER's decision. Picking a tier sends max_bitrate on the
             next /stream/{id}/info, and anything below Original forces a
             transcode -- confirmed against the live server, which answers
             "Transcoding to match selected quality (720p (4 Mbps))".
  Audio      KODI's decision, applied after playback starts. The info
             endpoint has no audio_stream_index parameter at all: on
             DirectPlay the whole container arrives and the player owns the
             choice. Under a transcode the server has already picked one
             track and this list will hold only that one.
  Subtitles  likewise Kodi's, via the same post-start route.
"""
from __future__ import annotations

from typing import Any, Optional

import xbmcgui

from . import kodigui, theme
from .. import log, tracks
from ..profile import DEFAULT_AUDIO_CODECS

#: Mirrors player.py: the panel must rank tracks the way playback will.
_PLAYABLE_AUDIO_CODECS = frozenset(
    c.strip().lower() for c in DEFAULT_AUDIO_CODECS.split(",") if c.strip())
from ..skin import fragments, icon_glyphs

LIST_ID = 100
GROUP_ID = 200
SHADOW_ID = 201
FILL_ID = 202
OUTLINE_ID = 203
HINT_ID = 204

QUALITY = "quality"
AUDIO = "audio"
SUBTITLES = "subtitles"

# The two subtitle rows that aren't tracks. Both are real answers and they
# are NOT the same answer: AUTOMATIC leaves the stream alone, so Kodi's own
# subtitle preferences and the container's default/forced flags decide, and
# OFF actively turns subtitles off. Collapsing them into one row would make
# the header claim "Off" on a file that is about to display a forced
# narrative track -- which is what the first version of this panel did.
AUTOMATIC = None
OFF = -1


class Selection:
    """What the panel decided, in the shape the callers actually need.

    A small object rather than a dict because three call sites read it and
    two of them (detail.py's play path, player.py's post-start track apply)
    are in different processes' worth of code from where it is built."""

    def __init__(self) -> None:
        self.quality_tag: Optional[str] = None      # None = Original
        self.max_bitrate: Optional[int] = None      # None = unconstrained
        #: "original" once the viewer has explicitly CHOSEN Original, and
        #: None until then. The server cannot tell those apart otherwise --
        #: both send no max_bitrate -- so without this it falls back on its
        #: own banding and re-decides a band the viewer has already picked.
        #: It caps nothing by itself; see CapabilityProfile.quality_mode.
        self.quality_mode: Optional[str] = None
        # Settings > Playback & Video > QUALITY, honoured for a playback the
        # viewer has not picked a quality for. Read from the cached copy
        # rather than a live whoami: this runs on the way into playback, and
        # playbackprefs exists precisely so that path never waits on the
        # network (see its docstring).
        #
        # Only "original" is expressible. "auto" is the server's own default
        # banding and is said by saying NOTHING -- this client has no
        # connection probe, so an `auto` it sent would be a claim it cannot
        # back (CapabilityProfile.quality_mode).
        try:
            from .. import playbackprefs
            if (playbackprefs.last_known() or {}).get("default_quality") == "original":
                self.quality_mode = "original"
        except Exception:                                    # noqa: BLE001
            pass
        self.audio_index: Optional[int] = None      # stream index, or None
        self.subtitle_index: Optional[int] = None   # stream index, OFF, or None

    def __repr__(self) -> str:
        return (f"Selection(quality_tag={self.quality_tag!r}, "
                f"max_bitrate={self.max_bitrate!r}, "
                f"quality_mode={self.quality_mode!r}, "
                f"audio_index={self.audio_index!r}, "
                f"subtitle_index={self.subtitle_index!r})")


def build_sections(info: dict[str, Any], selection: Selection,
                   audio_languages: Optional[list] = None) -> list[dict[str, Any]]:
    """Turn a /stream/{id}/info payload into the panel's section model.

    A section with no options at all is dropped rather than shown empty --
    7.7 says "first PRESENT section", which only means anything if a section
    can be absent. A section with exactly one option is kept: a viewer
    checking which audio track a disc defaults to is served by the header
    row alone, and hiding it would answer that question with silence."""
    sections: list[dict[str, Any]] = []

    tiers = info.get("quality_tiers") or []
    if tiers:
        options = []
        for tier in tiers:
            label, detail = tracks.quality_tier_label(tier)
            options.append({
                "label": label,
                "detail": detail,
                "tag": tier.get("tag"),
                "bitrate_kbps": tier.get("bitrate_kbps"),
                "is_original": bool(tier.get("is_original")),
            })
        chosen = next((i for i, o in enumerate(options)
                       if o["tag"] == selection.quality_tag), None)
        if chosen is None:
            chosen = next((i for i, o in enumerate(options) if o["is_original"]), 0)
        sections.append({"key": QUALITY, "title": "Quality",
                         "options": options, "selected": chosen})

    audio = info.get("audio_tracks") or []
    if audio:
        rows = tracks.disambiguate([tracks.audio_track_label(t) for t in audio])
        options = [{"label": label, "detail": detail, "index": t.get("index")}
                   for (label, detail), t in zip(rows, audio)]
        # What will ACTUALLY play, in the same order the player decides it:
        # an explicit pick, else the viewer's preferred language, else the
        # server's default, else the file's first track.
        #
        # The language step is the one that was missing. `selected_audio_
        # stream_index` is the server's idea of the file's default and takes
        # no account of preferred_audio_languages: on Mars Attacks!'s 4K disc
        # it is 1, the German track, because German comes first in the
        # container. The panel showed "German - Deutsch Dolby Digital 5.1" to
        # an English profile while playback correctly picked English, because
        # windows/player.py applies the preference and this did not.
        preferred = tracks.choose_audio(audio, audio_languages or [],
                                        playable=_PLAYABLE_AUDIO_CODECS)
        default = info.get("selected_audio_stream_index")
        chosen = next((i for i, o in enumerate(options)
                       if o["index"] == selection.audio_index), None)
        if chosen is None and preferred is not None:
            chosen = next((i for i, o in enumerate(options)
                           if o["index"] == preferred.get("index")), None)
        if chosen is None:
            chosen = next((i for i, o in enumerate(options) if o["index"] == default), 0)
        sections.append({"key": AUDIO, "title": "Audio",
                         "options": options, "selected": chosen})

    subs = info.get("subtitle_tracks") or []
    if subs:
        rows = tracks.disambiguate([tracks.subtitle_track_label(t) for t in subs])
        options = [
            {"label": "Automatic", "detail": "Player default", "index": AUTOMATIC},
            {"label": "Off", "detail": "", "index": OFF},
        ]
        options += [{"label": label, "detail": detail, "index": t.get("index")}
                    for (label, detail), t in zip(rows, subs)]
        # Automatic is index 0 and is also the "nothing chosen yet" state, so
        # an unset selection lands on it without a special case.
        chosen = next((i for i, o in enumerate(options)
                       if o["index"] == selection.subtitle_index), 0)
        sections.append({"key": SUBTITLES, "title": "Subtitles",
                         "options": options, "selected": chosen})

    return sections


def _hint(info: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    """What the current picks will actually do, in one line.

    Derived rather than re-negotiated: every non-Original tier forces a
    transcode by definition, and for Original the dry run already in hand
    is the answer. A round trip per keypress would be more current and
    would also make every arrow press wait on the network."""
    quality = next((s for s in sections if s["key"] == QUALITY), None)
    if quality:
        option = quality["options"][quality["selected"]]
        if not option["is_original"]:
            rate = tracks.bitrate_label(option["bitrate_kbps"])
            return f"Transcoded to {option['label']}" + (f" · {rate}" if rate else "")
    method = info.get("play_method")
    if method == "DirectPlay":
        return "Plays directly from the server, no transcoding"
    reasons = info.get("transcode_reasons") or []
    if reasons:
        return "Transcoded · " + "; ".join(reasons)
    return f"Play method: {method}" if method else ""


class PlaybackOptionsDialog(kodigui.BaseDialog):
    #: One-shot chooser mode, set from the `pick_once` kwarg. Declared on the
    #: class so _rebuild() can read it off any instance -- the section tests
    #: build a stand-in that never runs __init__.
    _pick_once = False

    xmlFile = "script-tofa-playoptions.xml"
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080
    # Must match the width its xmlFile was rendered at -- _resize() computes
    # the runtime geometry from it, and a mismatch would size the panel plate
    # to one window and the rows to another.
    PANEL_W = fragments.PLAYOPT_PANEL_W

    def __init__(self, *args, **kwargs):
        self._title = kwargs.pop("title", "Options")
        self._subtitle = kwargs.pop("subtitle", "")
        self._info = kwargs.pop("info", {}) or {}
        self.selection: Selection = kwargs.pop("selection", None) or Selection()
        # FLAT mode: a plain list of choices with no sections, closing on
        # pick. The Edition picker uses it so that dialog and this one share
        # a row grammar -- leading check column, label + detail, accent-wash
        # focus -- instead of the Sort/Filter picker's trailing-check row,
        # which sat one keypress away and looked like a different product.
        self._flat_rows = kwargs.pop("rows", None)
        self._flat_selected = kwargs.pop("selected_idx", 0)
        # A caller may hand over its own section model instead of a
        # /stream/{id}/info payload, in the same shape build_sections()
        # produces: {key, title, options:[{label, detail}], selected}.
        # Browse's Filter uses it to put Watch Status, Year and Quality
        # behind one collapsed panel; _apply() has nothing to say about
        # those keys and leaves them alone, so the caller simply reads
        # each section's `selected` back once the dialog closes.
        self._custom_sections = kwargs.pop("sections", None)
        # Sectioned mode normally APPLIES a pick and collapses back, because
        # its sections are settings that stay put. `pick_once` turns it into
        # a one-shot chooser instead: the first option picked closes the
        # panel and comes back as (section key, option index). That is what
        # a grouped "Add a row" needs -- three categories to look through,
        # one answer.
        self._pick_once = bool(kwargs.pop("pick_once", False))
        self._hint_text = kwargs.pop("hint", "")
        # preferences.playback.preferred_audio_languages, so the Audio
        # section can default to the track that will actually play. Absent
        # for the flat/custom-section callers, which have no audio section.
        self._audio_languages = kwargs.pop("audio_languages", None)
        self.picked_idx: Optional[int] = None
        #: (section key, option index) in pick_once mode; None if dismissed.
        self.picked_option: Optional[tuple] = None
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        if self._flat_rows is not None:
            self._sections = []
        elif self._custom_sections is not None:
            self._sections = self._custom_sections
        else:
            self._sections = build_sections(self._info, self.selection,
                                            self._audio_languages)
        # True only when THIS class built the sections from a /stream/{id}/
        # info payload, so it knows their option dicts carry `is_original`,
        # `tag`, `index` and the rest. A caller's own sections are its
        # namespace, not ours: their keys mean whatever the caller decided,
        # and their options are only required to have a label.
        self._derived_sections = (self._flat_rows is None
                                  and self._custom_sections is None)
        # Read back by callers that supplied their own sections.
        self.sections = self._sections
        # key of the one expanded section, or None with everything collapsed
        # -- which is the state the panel opens in.
        self._expanded: Optional[str] = None
        self.option_list: Optional[kodigui.ManagedControlList] = None
        # Parallel to the rendered rows: (section_key, option_index or None).
        # None marks a header. Rebuilt with the list, never inferred from it.
        self._model: list[tuple[str, Optional[int]]] = []

    def onFirstInit(self):
        # Per-WINDOW property store; a dialog inherits nothing from the
        # window underneath, so every colour token has to be set here or
        # each textcolor resolves empty and the labels render invisible.
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("accent_wash_focus", theme.accent_with_alpha("42"))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("options_title", self._title)
        self.setProperty("options_subtitle", self._subtitle)

        # Capacity, not the row count: ManagedControlList's third argument is
        # max_view_index, and passing the exact count leaves every row but the
        # last blank. Generous because an expanded subtitle section on a disc
        # rip can genuinely run past twenty.
        self.option_list = kodigui.ManagedControlList(self, LIST_ID, 60)
        # Flat mode opens on the current choice; sectioned mode opens on the
        # first header, every section collapsed.
        self._rebuild((None, self._flat_selected) if self._flat_rows is not None else None)
        self.setFocusId(LIST_ID)

    def _rebuild(self, focus: Optional[tuple] = None) -> None:
        """Re-render every row from the section model.

        A full rebuild per toggle rather than inserting and removing rows:
        Kodi's list has no stable identity across a mutation, so a partial
        edit would still need every row after the change point rewritten,
        and the check/chevron glyphs on untouched rows are derived state
        that would drift. 60 rows of ListItem construction is nothing beside
        the network call that filled this dialog.

        `focus` is a (section_key, option_index) pair, resolved to a row
        AFTER the model is rebuilt. Resolving it in the caller looks
        equivalent and is not: the caller holds the model as it was BEFORE
        the toggle, where the row it wants to land on does not exist yet.
        That is how this first went wrong -- every expand fell back to row 0
        and left the header highlighted rather than the current value, which
        read as Kodi refusing to move the selection."""
        items = []
        model: list[tuple[Optional[str], Optional[int]]] = []
        if self._flat_rows is not None:
            for i, row in enumerate(self._flat_rows):
                items.append(self._option_item(row["label"], row.get("detail", ""),
                                               i == self._flat_selected))
                model.append((None, i))
        for section in self._sections:
            expanded = section["key"] == self._expanded
            header = kodigui.ManagedListItem(label=section["title"])
            header.setProperty("section", section["key"])
            # A collapsed section reads back the value it holds. A one-shot
            # chooser holds none -- `selected` is only there to satisfy the
            # shared model -- so it shows how many choices are inside
            # instead, which is what a closed group has to say for itself.
            if self._pick_once:
                header.setProperty("value", str(len(section["options"])))
            else:
                chosen = section["options"][section["selected"]]
                header.setProperty("value", "" if expanded else chosen["label"])
            # chevrons-up-down, the same "opens a list of choices" mark the
            # Options pill that led here carries. A plain chevron
            # right/down pair reads as a DIRECTION, which is what it means
            # on the "scroll down for page 2" hint and not what it means
            # here.
            #
            # The same glyph in both states, deliberately. Lucide's
            # chevrons-down-up is the obvious counterpart for an open
            # section, but at 19px the two chevrons meet and it reads as an
            # x, i.e. "close" -- checked on a 6x magnification of the real
            # render rather than assumed. The mark says "this row cycles
            # through values", which stays true either way, and a section
            # that is open is already showing its options.
            header.setProperty("chevron", chr(icon_glyphs.CHEVRONS_UP_DOWN))
            items.append(header)
            model.append((section["key"], None))
            if not expanded:
                continue
            for i, option in enumerate(section["options"]):
                # A chooser has no current value, so no row gets the check.
                # `selected` is 0 there only because the shared model needs
                # a number; drawing a tick on row 0 would read as "this one
                # is already on your Home screen", which is the opposite of
                # what the list means.
                checked = (not self._pick_once) and i == section["selected"]
                items.append(self._option_item(option["label"],
                                               option.get("detail", ""), checked))
                model.append((section["key"], i))

        self._model = model
        self.option_list.reset()
        if items:
            self.option_list.addItems(items)
        focus_row = model.index(focus) if focus in model else 0
        if 0 <= focus_row < len(items):
            self.option_list.selectItem(focus_row)
        # Same rule as _apply: _hint() reads the transcode fields off the
        # quality section, so it may only run on sections this class built.
        # It raised on Browse's Filter for exactly that reason.
        self.setProperty(
            "options_hint",
            _hint(self._info, self._sections) if self._derived_sections
            else self._hint_text)
        self._resize(len(items))

    @staticmethod
    def _option_item(label: str, detail: str, checked: bool):
        item = kodigui.ManagedListItem(label=label)
        # Empty `section` is what the row layout gates on to draw the option
        # form (leading check column, indented label) rather than the header
        # one; it is not a missing value.
        item.setProperty("section", "")
        item.setProperty("detail", detail)
        item.setProperty("check", chr(icon_glyphs.CHECK) if checked else "")
        return item

    def _resize(self, row_count: int) -> None:
        """Shrink the panel to the rows it is actually showing.

        Without this the collapsed state -- the state it OPENS in -- is
        three rows floating in a panel laid out for nine, which defeats the
        point of collapsing. The XML has to be the tallest state, so the
        panel can only reach its real size from here. Same runtime-geometry
        technique detail.py uses for its hero stack; failures are logged and
        swallowed because a mis-sized panel is still usable and a raise
        here would take the dialog down."""
        geometry = fragments.playoptions_geometry(
            row_count, self.PANEL_W, has_hint=bool(self.getProperty("options_hint")))
        try:
            self.getControl(GROUP_ID).setPosition(geometry["PANEL_X"], geometry["PANEL_Y"])
            self.getControl(FILL_ID).setHeight(geometry["PANEL_H"])
            self.getControl(OUTLINE_ID).setHeight(geometry["PANEL_H"])
            self.getControl(SHADOW_ID).setHeight(geometry["SHADOW_H"])
            self.getControl(LIST_ID).setHeight(geometry["ROWS_H"])
            self.getControl(HINT_ID).setPosition(geometry["PAD"], geometry["HINT_Y"])
        except Exception as exc:
            log.warning(f"playoptions: could not resize panel: {exc!r}")

    def onClick(self, controlID):
        if controlID != LIST_ID or self.option_list is None:
            return
        position = self.option_list.getSelectedPosition()
        if not (0 <= position < len(self._model)):
            return
        section_key, option_index = self._model[position]
        if section_key is None:
            # Flat mode: picking IS the answer, so it closes, the same way
            # the Sort picker it replaces did.
            self.picked_idx = option_index
            self.doClose()
            return
        section = next(s for s in self._sections if s["key"] == section_key)

        if option_index is None:
            # Header: toggle, and collapse whatever else was open. An
            # accordion rather than independent toggles because the point of
            # collapsing at all is that the panel stays short -- three
            # sections open at once is the flat list this replaced.
            self._expanded = None if self._expanded == section_key else section_key
            if self._expanded == section_key:
                # Land on the CURRENT value, not the top of the section:
                # 7.7 asks for "initial focus = ... selected row", and the
                # same reasoning applies to each section as it opens.
                self._rebuild((section_key, section["selected"]))
            else:
                self._rebuild((section_key, None))
            return

        if self._pick_once:
            # A one-shot chooser: picking IS the answer, so it closes, the
            # same as flat mode. Nothing is applied and nothing collapses --
            # there is no state here to leave behind.
            self.picked_option = (section_key, option_index)
            self.doClose()
            return

        # Option: apply, then collapse back to the headers. Collapsing is
        # the confirmation -- the header now reads the value just chosen,
        # which is a clearer acknowledgement than a check mark on a row that
        # is about to scroll away.
        section["selected"] = option_index
        self._apply(section)
        self._expanded = None
        self._rebuild((section_key, None))

    def _apply(self, section: dict[str, Any]) -> None:
        # A caller that supplied its own sections reads `selected` back when
        # the dialog closes; there is no Selection to write and its option
        # dicts carry none of the fields below.
        #
        # Matching on key alone was a landmine, and Browse's Filter stepped
        # on it: its third section is legitimately titled "Quality" and was
        # keyed "quality", which is also this module's QUALITY constant. So
        # picking a filter value ran the transcode branch, raised KeyError
        # 'is_original' -- and the raise happened one line BEFORE the
        # collapse, so the section stayed open while Watch Status and Year,
        # whose keys mean nothing here, closed normally. Reported from the
        # box as "Quality doesn't collapse".
        if not self._derived_sections:
            return
        option = section["options"][section["selected"]]
        if section["key"] == QUALITY:
            # Original is expressed as "no constraint" rather than as its own
            # bitrate: sending the source's measured 91740 kbps as a ceiling
            # invites the decision engine to transcode a stream that momentarily
            # exceeds its own average.
            self.selection.quality_tag = None if option["is_original"] else option["tag"]
            self.selection.max_bitrate = None if option["is_original"] else option["bitrate_kbps"]
            # A DELIBERATE Original is not the same as never having
            # been asked, even though both send no ceiling.
            self.selection.quality_mode = "original" if option["is_original"] else None
        elif section["key"] == AUDIO:
            self.selection.audio_index = option["index"]
        elif section["key"] == SUBTITLES:
            self.selection.subtitle_index = option["index"]
        log.debug(f"playoptions: {self.selection!r}")

    def onAction(self, action):
        aid = action.getId()
        if aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            # Back closes an expanded section first and the panel second.
            # Without that step the only way out of a long subtitle list is
            # to scroll back to its header, and Back inside a disclosure
            # already means "up one level" everywhere else in this app.
            if self._flat_rows is None and self._expanded is not None:
                collapsing = self._expanded
                self._expanded = None
                self._rebuild((collapsing, None))
                return
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)


class EditionDialog(PlaybackOptionsDialog):
    """Detail's Edition picker: the options panel in flat mode, on a wider
    window.

    Wider because its rows carry 7.7's whole grammar -- resolution, dynamic
    range, video codec, audio codec, size GB -- where the options panel's
    detail column holds one short fact. Choosing between two editions is
    precisely when all of that matters, so the row is sized for the long
    string rather than the common one.

    Its own XML rather than a reflowed one: a Kodi <itemlayout> resolves its
    column positions at load. The flat mode itself is generic.

    The panel is 70px WIDER than the options panel, which those two dialogs
    being a keypress apart argues against and the content requires anyway.
    At the shared width the NAME column came out 254px and the reference
    library's names did not fit it -- "Black and White Version" is 270 --
    while the detail column, measured across the same titles, was already
    within 45px of its own limit. Something had to give and the panel is the
    only part of this that costs nothing. See fragments.EDITION_PANEL_W.

    PANEL_W must match the width its xmlFile was RENDERED at: _resize()
    computes the runtime geometry from it, and a mismatch sizes the plate to
    one window and the rows to another."""

    xmlFile = "script-tofa-editions.xml"
    PANEL_W = fragments.EDITION_PANEL_W


def show_choice(*, title: str, subtitle: str, rows: list[dict[str, Any]],
                selected_idx: int = 0, hint: str = "") -> Optional[int]:
    """A one-off picker on the NARROW-detail window: long labels, short
    details. The skinned replacement for xbmcgui.Dialog().select().

    Same flat mode as show_editions, different column split. An edition row
    is a short name against a long spec string; a server row is the reverse,
    a name of unknown length against a one-word role, and running it through
    the edition window would truncate the name to make room for "owner"."""
    if not rows:
        return None
    dialog = PlaybackOptionsDialog.open(
        title=title, subtitle=subtitle, rows=rows,
        selected_idx=selected_idx, hint=hint)
    picked = getattr(dialog, "picked_idx", None)
    del dialog
    return picked


def show_grouped_choice(*, title: str, subtitle: str,
                        groups: list[dict[str, Any]],
                        hint: str = "") -> Optional[tuple]:
    """Pick ONE option from several named groups, collapsed until opened.

    Returns (group key, option index), or None if dismissed.

    The shape the web app uses for "Add a row": one control holding three
    labelled groups rather than one button per group. Reusing the collapsed
    section panel rather than a flat list keeps the categories the reference
    shows -- a flat list of every Discover shelf, every genre and every
    builtin run together is the thing the grouping exists to avoid.

    A group with no options is dropped; if that leaves nothing, so is the
    dialog.
    """
    sections = [{"key": g["key"], "title": g["title"], "selected": 0,
                 "options": g["options"]}
                for g in groups if g.get("options")]
    if not sections:
        return None
    dialog = PlaybackOptionsDialog.open(
        title=title, subtitle=subtitle, sections=sections,
        pick_once=True, hint=hint)
    picked = getattr(dialog, "picked_option", None)
    del dialog
    return picked


def show_editions(*, title: str, subtitle: str, rows: list[dict[str, Any]],
                  selected_idx: int = 0) -> Optional[int]:
    """Open the Edition picker and return the index picked, or None if
    dismissed.

    Uses this panel's row grammar rather than the Sort/Filter picker's, whose
    trailing check column and accent-FILLED focus are a different visual
    language one keypress away on the same action row. That picker keeps its
    own look because Browse's four buttons are pixel-matched to the real app;
    this pill never was."""
    if not rows:
        return None
    dialog = EditionDialog.open(
        title=title, subtitle=subtitle, rows=rows, selected_idx=selected_idx)
    picked = getattr(dialog, "picked_idx", None)
    del dialog
    return picked


def show_sections(*, title: str, subtitle: str = "",
                  sections: list[dict[str, Any]]) -> Optional[list[int]]:
    """Open the collapsed panel over a caller's OWN sections.

    Returns the chosen index per section, in order, or None when there was
    nothing to show. Like 7.7's own panel there is no cancel: a pick is
    applied as it is made, and the collapsed header states it -- so the
    caller compares the returned indices against what it passed in to know
    whether anything actually changed."""
    sections = [s for s in sections if s.get("options")]
    if not sections:
        return None
    dialog = PlaybackOptionsDialog.open(
        title=title, subtitle=subtitle, sections=sections)
    result = [s["selected"] for s in getattr(dialog, "sections", sections)]
    del dialog
    return result


def show(*, title: str, subtitle: str, info: dict[str, Any],
         selection: Optional[Selection] = None,
         audio_languages: Optional[list] = None) -> Selection:
    """Open the panel and return the (possibly unchanged) Selection.

    Always returns one, never None: 7.7's picks persist as they are made, so
    there is no dismissal that means "forget what I chose"."""
    selection = selection or Selection()
    dialog = PlaybackOptionsDialog.open(
        title=title, subtitle=subtitle, info=info, selection=selection,
        audio_languages=audio_languages)
    result = getattr(dialog, "selection", selection)
    del dialog
    return result
