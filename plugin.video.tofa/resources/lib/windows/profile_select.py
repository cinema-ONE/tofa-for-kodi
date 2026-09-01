# -*- coding: utf-8 -*-
"""Interactive "Who's watching?" profile picker + PIN entry, mirroring
tofa's own apps. Parallel to signin.py: profiles.py has the bare HTTP
calls, this drives the dialog and persists the result via auth.py.

Entry points:
  - ensure_profile_selected(session, tok): the proactive, per-launch gate.
    Fast path is a single dataclass-field check, zero network calls, since
    every plugin action / window open is a fresh process that would
    otherwise re-pay this on every single request. Only falls through to
    fetching the profile list (and, if needed, the dialog) on first launch
    after sign-in or once a locked profile's ~4h profile_token expires.
  - switch_profile(): Settings' "Switch Profile" action -- always shows the
    picker, bypassing the fast path deliberately (see its own docstring).
"""
from __future__ import annotations

import threading
import time

import xbmc
import xbmcgui

from .. import addonref, api, auth, avatar_presets, http, log
from .. import profiles as profiles_api
from ..api import MediaServerClient
from . import kodigui, theme

_ = addonref.localize  # lazy, see addonref.py

class ProfileCanceled(Exception):
    """Raised when the user backs out of profile selection -- callers treat
    this the same as a declined sign-in (nothing to show, back out)."""


def _initials(name: str) -> str:
    """Matches tofa's own apps: first two characters of a single-word name,
    else the first letter of the first word plus the first letter of the
    last word (e.g. "Claude Code" -> "CC", not "C"). "?" for an
    empty/unnamed profile."""
    words = (name or "").split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def _resolve_preset_urls(session, tok: auth.Tokens, profiles: list) -> dict:
    """profile.id -> a loadable URL for its `preset:` avatar, or absent.

    Resolved HERE rather than inside the dialog, matching
    _resolve_avatar_photos: the network belongs with the caller that already
    holds a session, and the window stays a window.

    The artwork is NOT bundled -- see avatar_presets for why, and for the six
    ids 0.9.29 retired. A missing entry means the caller draws the monogram,
    which covers a retired preset, an id newer than our cache, and an
    unreachable server alike."""
    urls: dict = {}
    for profile in profiles:
        url = avatar_presets.url_for(session, tok.server, profile.avatar_ref,
                                     tok.access_token)
        if url:
            urls[profile.id] = url
    return urls


def _resolve_avatar_photos(session, tok: auth.Tokens, profiles: list) -> dict:
    """profile.id -> a directly-loadable image URL for any profile with a
    real `avatar_image_url` (a custom-uploaded photo), resolved the same
    way poster/backdrop art is (see MediaServerClient.resolve_image_url).
    Best-effort: returns {} on any failure -- including the image-token
    endpoint being account-scoped, which a multi-locked-profile household
    can hit before any profile is picked -- so every profile falls back
    to its preset/initial instead."""
    urls: dict = {}
    with_photo = [p for p in profiles if p.avatar_image_url]
    if not with_photo:
        return urls
    try:
        client = api.client_for(session, tok)
        for p in with_photo:
            url = client.resolve_image_url(p.avatar_image_url)
            if url:
                urls[p.id] = url
    except http.ApiError:
        return {}
    return urls


class ProfileDialog(kodigui.BaseDialog):
    xmlFile = "script-tofa-profile.xml"
    theme = "Main"
    res = "1080i"
    width = 1920
    height = 1080

    # One list control per realistic profile count (1-5, see
    # script-tofa-profile.xml's docstring for why fixed-width centered
    # variants rather than one dynamically-positioned list) -- counts
    # beyond 5 reuse the 5-wide variant and scroll.
    LIST_IDS = {1: 800, 2: 801, 3: 802, 4: 803, 5: 804}
    CANCEL_ID = 820
    DIGIT_IDS = {str(d): 900 + d for d in range(10)}
    ID_TO_DIGIT = {v: k for k, v in DIGIT_IDS.items()}
    BACKSPACE_ID = 910
    BACK_TO_PROFILES_ID = 920
    PIN_LENGTH = 4

    def __init__(self, *args, **kwargs):
        self._profiles = kwargs.pop("profiles")
        # profile.id -> resolved photo URL, see _resolve_avatar_photos().
        self._photo_urls = kwargs.pop("photo_urls", None) or {}
        # (Profile, pin) -> bool. Kept as a callback rather than importing
        # profiles_api/auth directly here, matching signin.py's split of
        # pure-UI dialog vs. network calls -- but reached from inside
        # onClick rather than an outer polling loop, since PIN retry-on-
        # wrong-entry must happen within one continuous keypad interaction
        # without reopening the dialog.
        self._preset_urls = kwargs.pop("preset_urls", None) or {}
        self._verify = kwargs.pop("verify_pin_callback")
        # Whose profile this already is, so the picker can open ON it.
        self._current_id = kwargs.pop("current_id", "") or ""
        # Open straight on the PIN pad for profiles[0], skipping the picker
        # entirely. For the re-lock case, where the profile is not in
        # question and only its expired token is -- see
        # ensure_profile_selected.
        self._start_in_pin = bool(kwargs.pop("start_in_pin", False))
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self._list_id = self.LIST_IDS[min(max(len(self._profiles), 1), 5)]
        self._profile_list = None
        self._entered_pin = ""
        self._current_profile = None
        self.chosen = None
        self.canceled = False

    def onFirstInit(self):
        # A fresh window property store, separate from MainWindow's own
        # (see PickerDialog's identical fix). Uses the FIXED default teal
        # (theme.DEFAULT_ACCENT), not theme.default_accent()'s usual
        # per-account lookup -- this screen's focus ring/text must not
        # depend on whichever profile was active before, or on the local
        # Kodi fallback setting.
        self.setProperty("accent_color", "0xFF" + theme.DEFAULT_ACCENT)
        self.setProperty("accent_pill_fill", "0x3D" + theme.DEFAULT_ACCENT)
        self.setProperty("text_primary", theme.TEXT_PRIMARY)
        self.setProperty("text_secondary", theme.TEXT_SECONDARY)
        self.setProperty("text_tertiary", theme.TEXT_TERTIARY)
        self.setProperty("heading", _(31090))
        self.setProperty("subheading", _(31091))
        self.setProperty("cancel_label", _(31092))
        self.setProperty("kids_label", _(31096))
        self.setProperty("profile_count", str(min(max(len(self._profiles), 1), 5)))
        # The PIN pane's exit pill says "Back to profiles" whenever there is a
        # picker worth returning to, and "Cancel" only when there genuinely
        # is not -- a one-profile household, where the grid behind would be a
        # single tile of the profile already being unlocked. Keyed on the
        # profile COUNT, not on start_in_pin: opening straight on the keypad
        # no longer implies the picker is empty. See _leave_pin_state.
        self.setProperty(
            "pin_exit_label", _(31092) if self._alone() else _(31094))
        # Kodi treats a <label> whose content is a bare integer as a
        # $LOCALIZE[N] string-table lookup, not literal text
        # (<label>1</label> renders Kodi's own string #1, "Pictures") --
        # routed through a Window.Property instead, never parsed as a
        # literal at XML-load time.
        for d in range(10):
            self.setProperty("digit_{0}".format(d), str(d))
        self._build_list()
        self.setProperty("state", "picker")
        # Dynamic Down/Up wiring between Cancel and whichever list variant
        # is actually visible -- same controlDown()/controlUp() technique
        # as windows/main.py's nav bar, since the target can't be a single
        # fixed static XML <onup>/<ondown>.
        self.getControl(self.CANCEL_ID).controlUp(self.getControl(self._list_id))
        self.getControl(self._list_id).controlDown(self.getControl(self.CANCEL_ID))
        if self._start_in_pin and self._profiles:
            # Position the picker underneath BEFORE swapping to the keypad, so
            # backing out lands on the profile being unlocked rather than on
            # tile one. The list is fully built either way -- Back falls to it.
            self._focus_current_profile()
            self._enter_pin_state(self._pin_target())
            return
        self.setFocusId(self._list_id)
        self._focus_current_profile()

    def _focus_current_profile(self):
        """Open on the profile already in use, not on whichever happens to be
        first.

        Two things were wrong with landing on the first tile. It made
        returning to the profile you were just on a matter of counting across
        the row -- a different number of presses per household. And where the
        first profile is PIN-locked, as it is on the owner's account, the
        default focus put a PIN pad in the way of switching to an unlocked
        profile further along; hit twice in one session while testing.

        Position, not focus: the list already has focus, and Kodi's selected
        position is what the focused layout draws. An unknown or absent id
        (a first-ever run, or a profile deleted server-side since) leaves the
        selection where it was, which is the first tile -- the old
        behaviour, and the right fallback."""
        if not self._current_id or not self._profile_list:
            return
        for pos, profile in enumerate(self._profiles):
            if profile.id == self._current_id:
                try:
                    self._profile_list.setSelectedItemByPos(pos)
                except Exception:  # noqa: BLE001 - never block the picker
                    log.debug("profile: could not preselect %s" % self._current_id)
                return

    def _build_list(self):
        lst = kodigui.ManagedControlList(self, self._list_id, max(1, len(self._profiles)))
        items = []
        for p in self._profiles:
            mli = kodigui.ManagedListItem(label=p.name)
            mli.setProperty("name", p.name)
            mli.setProperty("initial", _initials(p.name))
            mli.setProperty("avatar_texture", self._preset_urls.get(p.id, ""))
            mli.setProperty("photo_url", self._photo_urls.get(p.id, ""))
            mli.setProperty("locked", "1" if p.is_locked else "")
            mli.setProperty("kids", "1" if p.is_kids else "")
            items.append(mli)
        lst.reset()
        lst.addItems(items)
        self._profile_list = lst

    def _enter_pin_state(self, profile):
        self._current_profile = profile
        self._entered_pin = ""
        self.setProperty("pin_avatar_initial", _initials(profile.name))
        self.setProperty("pin_avatar_texture",
                         self._preset_urls.get(profile.id, ""))
        self.setProperty("pin_avatar_photo_url", self._photo_urls.get(profile.id, ""))
        self.setProperty("pin_heading", _(31093) % profile.name)
        self._render_dots()
        self.setProperty("state", "pin")
        # waitAndSetFocus, not a plain setFocusId -- the keypad's
        # Control.IsVisible only flips true once Kodi re-evaluates the XML's
        # <visible> condition against the state property just set above,
        # which isn't synchronous. A plain setFocusId aimed at a still-
        # invisible control silently no-ops, leaving nothing focused at
        # all. See onAction/onClick for the reverse (pin -> picker)
        # transition.
        self.waitAndSetFocus(self.DIGIT_IDS["1"])

    def _render_dots(self):
        for i in range(self.PIN_LENGTH):
            self.setBoolProperty("pin_dot_{0}".format(i), i < len(self._entered_pin))

    def _append_digit(self, digit: str):
        if len(self._entered_pin) >= self.PIN_LENGTH:
            return
        # Typing again answers the error, so it goes now rather than on a
        # timer -- a message that outlives what it was about reads as a
        # second failure.
        self.setProperty("pin_error", "")
        self._entered_pin += digit
        self._render_dots()
        if len(self._entered_pin) == self.PIN_LENGTH:
            self._submit_pin()

    #: One leg of the oscillation, in ms, and how many legs to run. The
    #: Apple TV's pane travels ~13px and settles in ~270ms, so four 70ms
    #: legs (out, back, out, back) land on the reference's duration. The
    #: 13px lives in the XML, next to the animation it belongs to.
    #:
    #: THE LEG IS DELIBERATELY LONGER THAN THE XML'S 45ms SLIDE. When the
    #: two were equal, each leg was still travelling when the next flip
    #: arrived, and a reversal from a partial offset finishes proportionally
    #: sooner: a 60fps capture showed the first leg reaching 8 of its 23
    #: captured pixels and then vanishing, followed by a 67ms dead gap. The
    #: 25ms of slack means a leg completes even when xbmc.sleep overshoots.
    SHAKE_LEG_MS = 70
    SHAKE_LEGS = 4

    #: Let onClick return before the first flip. _reject_pin runs ON the UI
    #: thread, and Kodi cannot draw a frame until it returns, so a flip
    #: issued immediately burns part of its own leg: measured as the same
    #: truncated first excursion above. The delay is invisible next to the
    #: error line appearing.
    SHAKE_START_DELAY_MS = 30

    def _reject_pin(self, message: str = ""):
        """9.2's wrong-PIN feedback: shake the pane, show an inline error.

        NOT a notification. It used to be one -- Kodi's own toast, in the
        host skin -- and 9.2 is explicit: the error goes inline, in status
        red, and NEVER into a modal. It was also the last stock Kodi dialog
        here. The line
        sits BELOW the keypad, where the Apple TV puts it, and reads
        "Incorrect PIN." verbatim from a recording of the real app.

        THE SHAKE IS A CONDITIONAL SLIDE, FLIPPED. Kodi has no shake effect
        and no keyframes, so the XML holds one slide that runs while
        `pin_shake` is set and reverses when it clears, and the loop below
        supplies the rhythm. Each flip is one leg.

        TWO THINGS MAKE IT WORK, both learned by getting them wrong:

        1. The animation goes on the ONE group that wraps the whole PIN
           pane. The keypad is twelve separate key groups, so putting it on
           "the keypad group" shakes the "1" button on its own.
        2. The flips run OFF THE UI THREAD. onClick IS Kodi's application
           thread: sleeping in it flips the properties on schedule while
           nothing redraws, so the animation never gets a frame to play.

        The thread re-checks `_closing` each leg, so closing the dialog
        mid-shake leaves nothing writing to a dead window.
        """
        self.setProperty("pin_error", message or _(31095))
        threading.Thread(target=self._shake, daemon=True).start()

    def _shake(self):
        """Flip `pin_shake` to drive the pane's oscillation. Off the UI
        thread; see _reject_pin."""
        xbmc.sleep(self.SHAKE_START_DELAY_MS)
        for leg in range(self.SHAKE_LEGS):
            if self._closing:
                return
            self.setProperty("pin_shake", "1" if leg % 2 == 0 else "")
            xbmc.sleep(self.SHAKE_LEG_MS)
        if not self._closing:
            self.setProperty("pin_shake", "")

    def _backspace(self):
        self._entered_pin = self._entered_pin[:-1]
        self._render_dots()

    def _submit_pin(self):
        pin = self._entered_pin
        try:
            ok = self._verify(self._current_profile, pin)
        except http.ApiError as exc:
            # Anything that is not "wrong PIN" -- the verify callback turns a
            # 401 into False and re-raises the rest. Found the hard way on
            # 2026-08-11: testing the shake earned an HTTP 429 "Too many PIN
            # attempts", which escaped through onAction and left the keypad
            # DEAD -- no error, no shake, nothing but a traceback in the log.
            # A viewer who has genuinely mistyped three times would hit the
            # same wall and be told nothing at all.
            #
            # The server's own message is used when it sends one: it is the
            # only thing that knows why ("Try again later"), and it is
            # already written for a human.
            log.warning(f"profile: PIN verify failed: {exc}")
            self._entered_pin = ""
            self._render_dots()
            # 429 gets OUR wording. The server sends "Too many requests: Too
            # many PIN attempts. Try again later." -- the same sentence twice,
            # opening with a status code. Adrian: "a bit long and redundant."
            # Every other failure keeps the server's text, which is the only
            # thing that knows what went wrong.
            if exc.status == 429:
                message = _(31098)
            else:
                message = exc.message or _(31097)
            self._reject_pin(message=message)
            return
        if ok:
            self.chosen = self._current_profile
            self.doClose()
            return
        # Wrong PIN: clear and let the user retry without leaving this screen.
        self._entered_pin = ""
        self._render_dots()
        self._reject_pin()
        # Still in "pin" state throughout this retry (never left it), so the
        # digit button is already visible -- a plain setFocusId is fine
        # here, unlike the state-transition cases elsewhere in this class.
        self.setFocusId(self.DIGIT_IDS["1"])

    def onClick(self, controlID):
        if controlID == self._list_id:
            idx = self._profile_list.getSelectedPosition()
            if idx < 0:
                return
            profile = self._profiles[idx]
            if profile.is_locked:
                self._enter_pin_state(profile)
            else:
                self.chosen = profile
                self.doClose()
            return
        if controlID == self.CANCEL_ID:
            self.canceled = True
            self.doClose()
            return
        if controlID == self.BACK_TO_PROFILES_ID:
            if not self._leave_pin_state():
                # Labelled "Cancel" in that mode, and it has to mean it.
                self.canceled = True
                self.doClose()
            return
        if controlID == self.BACKSPACE_ID:
            self._backspace()
            return
        digit = self.ID_TO_DIGIT.get(controlID)
        if digit is not None:
            self._append_digit(digit)

    def _typed_digit(self, action) -> str | None:
        """The digit a number key carries, or None for anything else.

        Kodi routes BOTH a remote's number pad and a keyboard's digit row to
        the contiguous ACTION_REMOTE_0..ACTION_REMOTE_9 block (58..67), so
        one branch covers both. Measured rather than assumed: pressing "5"
        on a keyboard arrives here as id 63 (REMOTE_0 + 5) with button code
        0xF035, and 0/1/9 land on 58/59/67 to match.
        """
        offset = action.getId() - xbmcgui.REMOTE_0
        return str(offset) if 0 <= offset <= 9 else None

    def onAction(self, action):
        # Type the PIN instead of walking the keypad. Only while the PIN
        # pane is up: a number key on the profile picker has no meaning, and
        # swallowing it there would just make the screen feel broken.
        #
        # Backspace is deliberately NOT bound to deleting a digit. Kodi's
        # keyboard map sends it as ACTION_NAV_BACK -- the same action the
        # remote's Back button sends, which this screen already uses to
        # leave PIN entry. Rebinding it would change what Back does for
        # everyone holding a remote, to fix something the keypad's own
        # backspace key already does.
        if self.getProperty("state") == "pin":
            digit = self._typed_digit(action)
            if digit is not None:
                self._append_digit(digit)
                return

        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            if self.getProperty("state") == "pin" and self._leave_pin_state():
                return
            self.canceled = True
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)

    def _alone(self) -> bool:
        """Is the PIN pad the only thing here -- nothing to go back TO?

        True only for a one-profile household. Then the grid behind is a
        single tile of the profile already being unlocked, so offering "Back
        to profiles" would land the viewer on a screen with one choice they
        have already made.
        """
        return len(self._profiles) <= 1

    def _pin_target(self):
        """Which profile start_in_pin opens the keypad on.

        By id, not position: the dialog is handed the whole household now, so
        profiles[0] is whoever happens to be first, not whoever is being
        re-verified. Falls back to the first tile if the stored id is not in
        the list, which is the same shape as _focus_current_profile's.
        """
        for profile in self._profiles:
            if profile.id == self._current_id:
                return profile
        return self._profiles[0]

    def _leave_pin_state(self) -> bool:
        """Back out of PIN entry to the picker; False when there is no picker
        to go back to, so the caller closes the dialog instead.

        This used to return False for the whole start_in_pin mode, because
        that mode was only ever handed ONE profile and dropping onto a
        one-tile "Who's watching?" would be a screen the viewer never came
        from. The re-lock caller now passes the whole household
        (ensure_profile_selected), so there is a real gate behind the keypad
        and Back belongs on it -- that is what §9.2 means by PIN being a state
        of this screen rather than a screen of its own. Without it, a viewer
        who does not know the locked profile's PIN cannot reach their own.
        """
        if self._alone():
            return False
        self.setProperty("state", "picker")
        self.waitAndSetFocus(self._list_id)
        return True


def _run_picker(session, tok: auth.Tokens, items: list[profiles_api.Profile],
                *, start_in_pin: bool = False,
                current_id: str = "") -> profiles_api.Profile:
    """Show the profile gate and persist whatever comes back.

    `start_in_pin` opens on the PIN pad for `current_id` instead of the tile
    grid -- the re-lock case, where the profile is not in question and only
    its expired token is. The picker is still built and still reachable with
    Back; see ProfileDialog._leave_pin_state.
    """
    def verify(profile, pin):
        try:
            token, expires_at = profiles_api.verify_pin(
                session, tok.server, tok.access_token, tok.device_id, profile.id, pin
            )
        except http.ApiError as exc:
            if exc.status == 401:
                return False
            raise
        auth.save_profile_selection(profile.id, token, expires_at)
        return True

    photo_urls = _resolve_avatar_photos(session, tok, items)
    preset_urls = _resolve_preset_urls(session, tok, items)
    dialog = ProfileDialog.open(profiles=items, photo_urls=photo_urls,
                                preset_urls=preset_urls,
                                verify_pin_callback=verify,
                                current_id=current_id or tok.profile_id or "",
                                start_in_pin=start_in_pin)
    if not dialog or dialog.canceled or not dialog.chosen:
        raise ProfileCanceled()
    if not dialog.chosen.is_locked:
        auth.save_profile_selection(dialog.chosen.id, None, None)
    return dialog.chosen


#: How long a token must still be good for before an ordinary caller will
#: use it -- enough to cover the request it is about to make, no more.
MARGIN_S = 30


def ensure_profile_selected(session, tok: auth.Tokens, margin_s: float = MARGIN_S) -> auth.Tokens:
    """Resolve (and if necessary re-verify) the household profile.

    `margin_s` is how far into the future the token has to remain valid.
    The default is "long enough for the call I am about to make". A caller
    that is about to be unable to ask -- playback, which then runs for an
    hour with no chance to put a PIN pad anywhere sensible -- passes the
    length of what it is starting, so the PIN is asked for at the moment the
    viewer pressed Play rather than 40 minutes into the film. See
    DetailWindow._renew_profile_token_for.
    """
    now = time.time()
    if tok.profile_id and (not tok.profile_token
                           or (tok.profile_token_expires_at or 0) > now + margin_s):
        return tok  # already resolved, and (if locked) not expired -- no network call

    items = profiles_api.list_profiles(session, tok.server, tok.access_token,
                                       tok.device_id, fallback=tok.server_fallback)
    if not items:
        return tok  # nothing to resolve against; let the request that follows fail naturally

    if tok.profile_id:
        chosen_source = next((p for p in items if p.id == tok.profile_id), None)
        if chosen_source is not None and not chosen_source.is_locked:
            auth.save_profile_selection(chosen_source.id, None, None)
            return auth.load()
        # A known profile's token merely expired: open ON its PIN pad, so the
        # common case is still one keypad and no picker to walk. But hand the
        # dialog the WHOLE household, not just this one profile, so Back
        # reaches "Who's watching?" instead of dead-ending.
        #
        # It used to pass [chosen_source] alone, which made the PIN pad a
        # trap: the only ways out were the right PIN or cancelling the add-on
        # entirely, so a household could not switch to an unlocked profile
        # without knowing the locked one's PIN. §9.2 puts PIN and picker in
        # ONE screen, crossfading between the two states rather than pushing
        # a second screen, and a state you cannot leave is not that.
        #
        # Via _run_picker rather than ProfileDialog.open directly, because
        # backing out and choosing an UNLOCKED profile has to persist that
        # choice -- and _run_picker is where that already happens. Opening the
        # dialog by hand here is exactly how this would come back as an
        # unbreakable PIN loop: chosen but never saved, so the next launch
        # re-reads the old profile_id and asks again.
        #
        # start_in_pin only when the stored profile still exists. If it has
        # been deleted server-side, there is nothing to unlock and the plain
        # picker is the honest screen -- the old code fell back to items[0]
        # and put up a PIN pad for an unrelated profile.
        _run_picker(session, tok, items,
                    start_in_pin=chosen_source is not None,
                    current_id=tok.profile_id)
        return auth.load()

    if len(items) == 1 and not items[0].is_locked:
        # Single-profile, no-PIN household -- skip the screen entirely.
        auth.save_profile_selection(items[0].id, None, None)
        return auth.load()

    _run_picker(session, tok, items)
    return auth.load()


def renew_for_playback(runtime_ms) -> bool:
    """Ask for the PIN NOW if the profile token would die during what is
    about to play. Returns whether a new token was issued.

    A locked profile's token lasts ~4h and the server has no way to renew one
    without the PIN -- there is no refresh endpoint, only verify-pin (asked
    for on issue #7). So somewhere in every fifth hour a viewer has to type
    it, and if nobody chooses when, the moment is chosen by whichever call is
    first past the expiry. On the box that was 40 minutes into an episode.

    Pressing Play is the moment the viewer is already at the keyboard,
    already waiting a beat, and has just declared how long they intend to be
    busy. Asking here costs one prompt they were getting anyway, at the one
    point in the next two hours where it is not an interruption. This is the
    reason `ensure_profile_selected` takes a margin at all.

    Best effort in every direction. A declined PIN still plays: the stream
    carries its own token, good for 24h, so the only casualty is progress
    reporting -- exactly what would have been lost anyway. Nothing here may
    stop playback.
    """
    try:
        runtime_ms = int(runtime_ms or 0)
    except (TypeError, ValueError):
        return False
    if runtime_ms <= 0:
        return False
    try:
        session = http.new_session()
        tok = auth.ensure_fresh(session)
        if not tok.profile_token:
            return False  # unlocked profile -- no token, nothing to expire
        renewed = ensure_profile_selected(session, tok, margin_s=runtime_ms / 1000.0)
        return renewed.profile_token != tok.profile_token
    except (auth.NotSignedIn, ProfileCanceled, http.ApiError) as exc:
        log.warning(f"profile: playing without renewing the token first: {exc}")
        return False


def switch_profile() -> bool:
    """Settings' "Switch Profile" action -- always shows the picker
    regardless of the current fast-path resolution state, unlike
    ensure_profile_selected's proactive per-launch check."""
    session = http.new_session()
    try:
        tok = auth.ensure_fresh(session)
    except auth.NotSignedIn:
        return False
    try:
        items = profiles_api.list_profiles(session, tok.server, tok.access_token,
                                       tok.device_id, fallback=tok.server_fallback)
    except http.ApiError as exc:
        # NEVER exc.message for a transport failure. http.request_json wraps
        # requests' own exception with str(exc), and that string is
        # urllib3 internals -- "HTTPConnectionPool(host='192.168.1.50',
        # port=33333): Max retries exceeded ... NewConnectionError(...)".
        # Adrian saw exactly that on a toast and asked what it meant, which
        # is the right question to ask of it.
        #
        # The SERVER's own messages are written for people and still shown.
        # Only the two transport codes get replaced, and the raw text goes
        # to the log with the address it was dialling -- which is the thing
        # worth knowing and the thing the toast could never say.
        log.warning("profiles: list failed against {0}: [{1}] {2}".format(
            tok.server, exc.error, exc.message))
        # 31051/31050 are signin._alert_api_error's own pair, reused so the
        # two paths word the same failure the same way.
        message = _(31051) if exc.status == 0 else _(31050) % exc.message
        xbmcgui.Dialog().notification(kodigui.ADDON.getAddonInfo("name"), message, xbmcgui.NOTIFICATION_ERROR)
        return False
    try:
        _run_picker(session, tok, items)
    except ProfileCanceled:
        return False
    return True
