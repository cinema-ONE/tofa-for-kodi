# -*- coding: utf-8 -*-
"""TV-DESIGN 7.2's card options panel.

The long-press context menu for any poster/episode card, plus the Detail
hero's Options pill. This module owns the option SET and the panel; the
caller owns what each choice does, because the same six actions mean
slightly different things on a library title, a Continue Watching card and
an out-of-library Discover card.

The dialog is deliberately dumb: it renders rows, returns the chosen
action's key, and does no API work of its own. Doing the work here would
mean this module needed a client, a progress lookup and a watchlist
lookup -- all of which the calling screen already has in hand, since it
had to build the card.

Trigger on Kodi is the remote's context/menu key, not a real long-press:
Kodi's focus engine exposes no press-phase for Select, and 10.2 sanctions
the dedicated key where one is free.
"""
from __future__ import annotations

import xbmcgui

from . import kodigui, theme
from ..skin import icon_glyphs
from ..skin import tokens as T

# Action keys returned via `picked`. Strings rather than an enum so a caller
# can ignore one it doesn't implement without a KeyError, which is the same
# open-vocabulary posture 16 asks for on server data.
PLAY = "play"
DETAILS = "details"
MARK_WATCHED = "mark_watched"
MARK_UNWATCHED = "mark_unwatched"
WATCHLIST_ADD = "watchlist_add"
WATCHLIST_REMOVE = "watchlist_remove"
REMOVE_FROM_CW = "remove_from_cw"
# Season-scoped variants, for the panel the season sidebar opens. Separate
# keys rather than reusing PLAY/MARK_WATCHED because the caller acts on a
# whole season, and a shared key would make the two indistinguishable at the
# call site the moment a screen offers both.
PLAY_SEASON = "play_season"
MARK_SEASON_WATCHED = "mark_season_watched"
MARK_SEASON_UNWATCHED = "mark_season_unwatched"
CANCEL = "cancel"
EXIT = "exit"
MINIMIZE = "minimize"
SIGN_OUT = "sign_out"
CLEAR_ARTWORK = "clear_artwork"
PAIR_AGAIN = "pair_again"
ROW_UP = "row_up"
ROW_DOWN = "row_down"
ROW_ON = "row_on"
ROW_OFF = "row_off"
ROW_REMOVE = "row_remove"

# (key, label, icon, destructive). Order is 7.2's, which is not arbitrary:
# the two actions that change what you SEE next (play, open) come first, the
# two that change state sit in the middle, and the one that removes
# something is last before Cancel.
_CATALOG = {
    # 6 establishes "Resume/Play" as ONE action whose label follows watch
    # state. 7.2 writes this row as "Play (if in library)", which names the
    # CONDITION rather than fixing the word, so the panel follows the same
    # rule the detail hero already does: the two must never disagree about
    # the same action on the same title, which is what prompted this.
    #
    # Whether a given title SHOULD read Resume is a separate question about
    # progress data, not about labels -- see the dismissed-title divergence
    # noted in the commit that added this.
    PLAY: ("Play", icon_glyphs.PLAY, False),
    DETAILS: ("Go to Details", icon_glyphs.CHEVRON_RIGHT, False),
    MARK_WATCHED: ("Mark as Watched", icon_glyphs.CHECK, False),
    MARK_UNWATCHED: ("Mark as Unwatched", icon_glyphs.MINUS_CIRCLE, False),
    WATCHLIST_ADD: ("Add to Watchlist", icon_glyphs.BOOKMARK, False),
    WATCHLIST_REMOVE: ("Remove from Watchlist", icon_glyphs.BOOKMARK_OFF, False),
    REMOVE_FROM_CW: ("Remove from Continue Watching", icon_glyphs.CIRCLE_X, True),
    PLAY_SEASON: ("Play Season", icon_glyphs.PLAY, False),
    MARK_SEASON_WATCHED: ("Mark Season as Watched", icon_glyphs.CHECK, False),
    MARK_SEASON_UNWATCHED: ("Mark Season as Unwatched", icon_glyphs.MINUS_CIRCLE, False),
    CANCEL: ("Cancel", icon_glyphs.CIRCLE_X, False),
    # Exit confirmation. Not a card action, but this IS the app's "floating
    # panel with a list of actions" component (7.2), so it renders the
    # confirmation rather than a native Kodi dialog -- same reasoning that
    # put the Sort/Filter pickers in PickerDialog.
    EXIT: ("Exit tofa", icon_glyphs.LOG_OUT, True),
    MINIMIZE: ("Minimize", icon_glyphs.MINIMIZE, False),
    # Settings > Account > Sign Out. Same reasoning as EXIT, and destructive
    # for a stronger reason: exiting loses what is in flight, this loses the
    # pairing and needs the whole device-code flow again to undo.
    SIGN_OUT: ("Sign Out", icon_glyphs.LOG_OUT, True),
    # Settings > This Device. NOT marked destructive: the red ink is reserved
    # for what cannot be undone, and every byte this removes comes back by
    # itself the next time the artwork is on screen.
    # GALLERY_VERTICAL_END, not CIRCLE_X: Cancel already owns CIRCLE_X, and
    # this panel shows the two rows together -- identical glyphs on both made
    # the confirm and the refusal read as the same button at a glance.
    CLEAR_ARTWORK: ("Clear Artwork Cache", icon_glyphs.GALLERY_VERTICAL_END, False),
    # Settings > Account > Switch Server, on an install that cannot switch
    # without the device flow. Destructive for the same reason SIGN_OUT is:
    # taking it ends the current pairing, and the second screen is the only
    # way back.
    PAIR_AGAIN: ("Pair Again", icon_glyphs.REFRESH_CW, True),
    # Settings > Appearance > Home Screen. The app gives each row three
    # independently focusable controls; a Kodi list item cannot, so the same
    # three choices arrive here instead (see _settings_home_row_clicked).
    ROW_UP: ("Move Up", icon_glyphs.ARROW_UP, False),
    ROW_DOWN: ("Move Down", icon_glyphs.ARROW_DOWN, False),
    ROW_ON: ("Show on Home", icon_glyphs.CHECK, False),
    ROW_OFF: ("Hide from Home", icon_glyphs.MINUS_CIRCLE, False),
    # Only offered on a row the viewer ADDED (a Discover or genre row). The
    # builtin set is fixed and can only be hidden, which is also all the real
    # app offers -- but a row you added and cannot delete would accumulate,
    # so removal is a deliberate superset here.
    ROW_REMOVE: ("Remove row", icon_glyphs.CIRCLE_X, True),
}


def option_keys(
    *,
    in_library: bool,
    fully_watched: bool,
    has_progress: bool,
    on_watchlist: bool,
    in_continue_watching: bool,
    detail_variant: bool = False,
) -> list[str]:
    """7.2's conditional option set, in its stated order.

    Each condition is the spec's, and each exists to keep the panel honest:
    Play only when there is something to play; Mark as Watched only when it
    isn't already; Mark as Unwatched only when there is progress to clear
    (so a never-started title doesn't offer to un-watch itself); Remove from
    Continue Watching only on the row it belongs to; Cancel only on the
    Detail variant, where the panel was opened from a button rather than by
    a context key that also dismisses it."""
    keys = []
    if in_library:
        keys.append(PLAY)
    keys.append(DETAILS)
    if in_library and not fully_watched:
        keys.append(MARK_WATCHED)
    if in_library and (has_progress or fully_watched):
        keys.append(MARK_UNWATCHED)
    keys.append(WATCHLIST_REMOVE if on_watchlist else WATCHLIST_ADD)
    if in_continue_watching:
        keys.append(REMOVE_FROM_CW)
    if detail_variant:
        keys.append(CANCEL)
    return keys


class CardOptionsDialog(kodigui.BaseDialog):
    xmlFile = "script-tofa-cardoptions.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    LIST_ID = 100

    def __init__(self, *args, **kwargs):
        self._resume = bool(kwargs.pop("resume", False))
        self._title = kwargs.pop("title", "")
        self._subtitle = kwargs.pop("subtitle", "")
        self._eyebrow = kwargs.pop("eyebrow", "")
        self._keys = list(kwargs.pop("keys", []))
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.option_list: kodigui.ManagedControlList | None = None
        # Read by the caller after open() returns; None means dismissed.
        self.picked: str | None = None

    def onFirstInit(self):
        # Window.Property is per-WINDOW, and this dialog is its own window:
        # without these every textcolor referencing a tier resolves to
        # nothing and the labels render invisible. Caught exactly that way on
        # first run -- only the destructive row, whose red is a literal, was
        # legible. Same block every window class carries; see
        # project_text_tier_consolidation.
        self.setProperty("accent_color", theme.default_accent())
        # 0x42 = 26%, 13's reduced-tier focus wash (0.17 -> 0.26), which
        # compensates for the dropped focus lift.
        self.setProperty("accent_wash_focus", theme.accent_with_alpha("42"))
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)

        self.setProperty("options_title", self._title)
        self.setProperty("options_subtitle", self._subtitle)
        self.setProperty("options_eyebrow", self._eyebrow)
        # Capacity, not the exact row count: ManagedControlList's third arg is
        # max_view_index, and passing the item count itself left every row but
        # the last rendering blank. Every other call site passes a fixed
        # ceiling (6, 25) well above what it adds.
        self.option_list = kodigui.ManagedControlList(self, self.LIST_ID, 10)

        items = []
        for key in self._keys:
            label, glyph, destructive = _CATALOG[key]
            if key == PLAY and self._resume:
                label = "Resume"
            mli = kodigui.ManagedListItem(label=label, data_source=key)
            mli.setProperty("icon_glyph", chr(glyph))
            mli.setProperty("destructive", "1" if destructive else "")
            items.append(mli)
        self.option_list.reset()
        if items:
            self.option_list.addItems(items)
        self.setFocusId(self.LIST_ID)

    def onClick(self, controlID):
        if controlID != self.LIST_ID or self.option_list is None:
            return
        item = self.option_list.getSelectedItem()
        if item is not None:
            # Cancel is a dismissal, not a result: reporting it would make
            # every caller special-case a key that means "do nothing".
            self.picked = None if item.dataSource == CANCEL else item.dataSource
        self.doClose()


def show(
    *,
    title: str,
    keys: list[str],
    subtitle: str = "",
    eyebrow: str = "",
    resume: bool = False,
) -> str | None:
    """Open the panel and return the chosen action key, or None if
    dismissed. Returns None immediately for an empty option set rather than
    flashing an empty panel."""
    if not keys:
        return None
    dialog = CardOptionsDialog.open(
        title=title, subtitle=subtitle, eyebrow=eyebrow, keys=keys, resume=resume
    )
    picked = getattr(dialog, "picked", None)
    del dialog
    return picked


class AlertDialog(kodigui.BaseDialog):
    """The skinned replacement for xbmcgui.Dialog().ok().

    Its own window rather than a card-options panel with one row, because
    the message has to WRAP: these carry server error strings of unknown
    length, and that panel's subtitle is a single-line label that would hide
    the part saying what went wrong. Kodi's only wrapping control is
    <textbox>, which cannot live in a list item."""

    xmlFile = "script-tofa-alert.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    BUTTON_ID = 100

    def __init__(self, *args, **kwargs):
        self._title = kwargs.pop("title", "")
        self._message = kwargs.pop("message", "")
        self._button = kwargs.pop("button", "OK")
        self._error = bool(kwargs.pop("error", False))
        kodigui.BaseDialog.__init__(self, *args, **kwargs)

    def onFirstInit(self):
        self.setProperty("accent_color", theme.default_accent())
        self.setProperty("on_accent_color", theme.on_accent_text())
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("alert_title", self._title)
        self.setProperty("alert_message", self._message)
        self.setProperty("alert_button", self._button)
        # 9.7's error flavour glyph, and 2's status red. A plain notice gets
        # no glyph at all rather than a neutral one, so the mark means
        # something when it is there.
        self.setProperty("alert_glyph",
                         chr(icon_glyphs.TRIANGLE_ALERT) if self._error else "")
        self.setProperty("alert_tint", T.STATUS_RED if self._error else "")
        self.setFocusId(self.BUTTON_ID)

    def onClick(self, controlID):
        if controlID == self.BUTTON_ID:
            self.doClose()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)


def alert(title: str, message: str, *, button: str = "OK",
          error: bool = False) -> None:
    """Show a message and wait for acknowledgement; the skinned
    Dialog().ok(). `error` adds 9.7's warning glyph in status red."""
    dialog = AlertDialog.open(title=title, message=message, button=button,
                              error=error)
    del dialog


def confirm_exit() -> str | None:
    """The Back-at-top-level confirmation, modelled on plex-for-kodi's own
    (lib/windows/home.py:confirmExit): Exit / Minimize / Cancel.

    Minimize is the one that needs explaining: it drops to Kodi's home
    window WITHOUT tearing the add-on down, so coming back is instant and
    nothing is re-fetched. That is what makes an accidental Back cheap.

    Exit is marked destructive (red ink at rest, 7.2) because it is the
    only irreversible row here -- everything in flight is lost.

    Returns the chosen key, or None when dismissed."""
    return show(
        title="Exit tofa?",
        subtitle="Minimize keeps tofa running in the background.",
        keys=[EXIT, MINIMIZE, CANCEL],
    )


def confirm_clear_artwork() -> bool:
    """Settings > This Device > Clear artwork cache, confirmed in the panel.

    Worth confirming even though nothing is lost: it can mean a few hundred
    megabytes fetched again over the next few screens, and on a metered or
    slow link that is the part the user would want to have been asked about.
    The subtitle says what comes back rather than what goes, because that is
    the question someone hesitating over this button is actually asking."""
    return show(
        title="Clear artwork cache?",
        # One line. The panel's subtitle is a single row and clips the rest --
        # a second sentence about the account being safe never got read.
        subtitle="It downloads again as you browse.",
        keys=[CLEAR_ARTWORK, CANCEL],
    ) == CLEAR_ARTWORK


def confirm_sign_out() -> bool:
    """Settings > Account > Sign Out, confirmed in the same panel.

    Says what signing back in will cost, because that is the part that is
    not obvious from the button: the device-code flow needs a second screen
    and a browser, so this is not a one-keypress mistake to undo."""
    return show(
        title="Sign out of tofa?",
        subtitle="You will need to pair this device with your server again.",
        keys=[SIGN_OUT, CANCEL],
    ) == SIGN_OUT


def confirm_pair_again() -> bool:
    """Settings > Account > Switch Server, when this device has no cloud
    session left to list the account's servers with.

    Two ways to land here and the viewer can tell neither apart nor act on
    the difference: paired before the add-on kept the cloud token at all, or
    left off long enough for it to expire. So the panel names the COST
    rather than the cause -- pairing again is the price either way, and it
    is the same price Sign Out quotes."""
    return show(
        title="Pair again to switch servers?",
        subtitle="This device's sign-in is too old to list your other servers.",
        keys=[PAIR_AGAIN, CANCEL],
    ) == PAIR_AGAIN
