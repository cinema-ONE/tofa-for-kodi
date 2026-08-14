# -*- coding: utf-8 -*-
"""The startup splash: the mark and wordmark wiped in, as the tofa apps do.

Shown WHENEVER THE APP WOULD OTHERWISE BE BUILT OVER NOTHING -- which means
every launch that does not already have a splash on screen, and a profile
switch, and nothing else. A minimize keeps the window alive, so coming back
rebuilds nothing and shows no splash.

It used to be once per Kodi run, mimicking the tofa apps, which do not replay
their splash when you back out and come straight back in. That rule cost more
than it bought. The splash is not decoration: it is the only thing covering
the window build, and Kodi has no third window to fall back on. Under the old
rule the second launch of a Kodi run built the app over KODI'S OWN HOME, and
closing the window for a profile switch uncovered it for a second (measured:
1.02s). Adrian's call, 2026-08-09: replaying the animation is the cheaper
price. See launch_home.py's restart loop.

So the gate is "is one already up", not "has one been shown". That cannot be
a module-level flag either way: every plugin:// action is a fresh Python
process, and the script entry point starts a new interpreter each launch, so
a module global would answer for this launch only -- while the window it is
answering about outlives the process that showed it, sitting in Kodi's
back-stack under the app. It lives as a property on Kodi's own home window
(id 10000), which outlives our processes and dies with Kodi.

The animation is entirely declarative: every strip carries its own WindowOpen
fade with its own delay (see skin/fragments.py:splash_wipe), so this class
only has to open the window and wait out the sequence. Nothing here drives a
frame.

It does NOT close itself. The real window is built underneath it and calls
dismiss() when it has something to show, so the hand-over is splash -> app
with nothing in between -- see ensure_up().
"""
from __future__ import annotations

import time

import xbmc
import xbmcgui

from .. import log
from . import kodigui, theme

#: Kodi's home window. Properties set here survive our processes and are
#: cleared when Kodi itself restarts, which is exactly the lifetime wanted.
_SESSION_WINDOW = 10000
#: Whether a splash window EXISTS in Kodi's window history right now.
#:
#: A Window property rather than a module global because the two launches that
#: disagree about the answer are two PROCESSES: the splash a cold start
#: `.show()`s outlives the script that made it, sitting in Kodi's back-stack
#: under the app, and the next launch of the same Kodi run has no Python
#: reference to it at all.
_ALIVE_PROPERTY = "tofa.splash_alive"

#: When the last strip has finished fading: the wordmark starts at 290, takes
#: 460 to cross, and its own fade is 120 (tokens.SPLASH_*). Was 1400, from the
#: mark wipe that re-measurement cut from 1280 to 430.
_ANIMATION_MS = 290 + 460 + 120

#: Hold after that, then hand over.
#:
#: The real app holds ~2000ms and runs ~3050ms end to end; this is a DELIBERATE
#: divergence, because unlike the animation the hold buys nothing to look at
#: and every millisecond of it is a millisecond of cold start. What the splash
#: has to cover is the launch's own fetching, and _MIN_VISIBLE_S below is the
#: floor for that, not a target to pad up to.
_HOLD_MS = 900

#: How long the splash is guaranteed to be up. Because the launch does its
#: fetching during it (see prefetch.py) this is not time ADDED to the start
#: any more -- a cold start costs whichever of the two is longer, not both.
_MIN_VISIBLE_S = (_ANIMATION_MS + _HOLD_MS) / 1000.0

#: After its run the splash stops swallowing Back. Normally nothing reaches
#: it -- the launch dismisses it a moment later -- so this only matters if a
#: launch died between showing and dismissing. Being stuck behind a splash
#: that eats every key would be far worse than seeing Kodi's menu.
_ESCAPABLE_AFTER_S = _MIN_VISIBLE_S

#: Kodi's Back / Previous-menu actions (ACTION_NAV_BACK, ACTION_PREVIOUS_MENU).
_BACK_ACTIONS = (92, 10)

#: The window currently up, or None. Module-level because show and dismiss
#: are called from different places in the launch, and within one launch
#: that is one process.
_pending = None
_shown_at = 0.0

#: Set by hand_over(), read by SplashWindow.onInit. Once the app has taken
#: over, any FURTHER onInit of the splash is a re-activation, not the first
#: show: Kodi navigated back to it through its window history when the app's
#: window closed (reproduced: launch, open Detail, back out, Exit -> the splash
#: replays and sticks, because .show() left it in the back-stack under the
#: modal MainWindow). The splash then steps aside instead of replaying -- see
#: onInit. Module-level and one-way: a launch is one process, and the flag only
#: ever goes False->True within it.
_handed_over = False


class SplashWindow(kodigui.BaseWindow):
    # All four matter: BaseWindow defaults path/theme to "" and res to 720p,
    # and Kodi reports the resulting miss as "XML File for Window is missing"
    # rather than as a bad path.
    xmlFile = "script-tofa-splash.xml"
    path = kodigui.ADDON.getAddonInfo("path")
    theme = "Main"
    res = "1080i"

    def onInit(self, count: int = 0):
        # `count` is NOT optional decoration. XMLBase.onInit RETRIES ITSELF as
        # self.onInit(count=count + 1) when control 666 is not ready yet, and
        # an override without the parameter turns that retry into a TypeError
        # that kills the whole launch script. It is a race, so it passes most
        # of the time and then does not: seen once as
        # "SplashWindow.onInit() got an unexpected keyword argument 'count'"
        # with the add-on left on a blank screen.
        #
        # MUST also chain: XMLBase.onInit is what sets
        # Window.Property(tofa_window), the only reliable way to identify one
        # of our screens (System.CurrentWindow resolves ours to "System" or
        # worse) and what tools/kodictl.py asserts on.
        super(SplashWindow, self).onInit(count=count)
        if _handed_over:
            # NOT the first show. The app already took over (hand_over ran),
            # so this onInit is Kodi re-activating the splash from its window
            # history -- the app's window closed and Kodi walked back to the
            # .show()n splash sitting beneath it. Replaying the wipe here is
            # the "start animation appeared again" on exit, and because nothing
            # takes this second showing down it strands the viewer on it. Step
            # aside instead: closing the splash -- which IS the current window
            # now, so this is a plain self-close, not project_kodi_double_close
            # -- lets Kodi land on whatever was under it (its own Home).
            #
            # And this is the moment the fallback stops existing: from here
            # on there is no splash in the history, so a later restart has to
            # raise its own rather than expect to walk back onto this one.
            _mark_alive(False)
            self.doClose()
            return
        # The wipe starts NOW -- this onInit is what put the window on screen,
        # whether it is the first show or Kodi re-activating it for a profile
        # switch. Restamping here is what lets wait_out() hold the new window
        # back for a full animation in both cases; ensure_up()'s own stamp
        # only covers a splash this process raised itself.
        global _shown_at
        _shown_at = time.monotonic()
        # Dress again. ensure_up() already did it before showing -- it HAS
        # to, see there -- but this onInit also runs when Kodi re-activates
        # the splash from its history on a profile switch, and that is the
        # path where the accent has just changed. Re-resolving a texture the
        # control already built is not enough on its own for the mark (same
        # reason as in ensure_up), but the wipe replays from the top on
        # re-activation, so the strips are rebuilt with it.
        self.dress()
        # Nothing to focus afterwards: the splash has no focusable control by
        # design. Said out loud because every other window sets focus here, so
        # the absence would otherwise read as an omission.
        self._escapable_at = time.monotonic() + _ESCAPABLE_AFTER_S

    def dress(self):
        """Put the last known accent's fox on the splash.

        7.10: the mark wears the profile's fox, the wordmark stays white.
        Measured on the real Android app rather than assumed -- its Amber
        profile shows an amber fox and a white "tofa" (2026-08-13).

        Reads the STORED accent and never resolves a live one. The splash is
        raised before MainWindow is imported, on no network and with no
        profile chosen, precisely to cover that work -- so asking the server
        here would make the thing that hides the wait into a thing that waits.
        theme._persist_accent keeps that stored value current.

        The mark snaps to one of 14 (artwork), the glow takes the accent
        EXACTLY (a white texture under colordiffuse), so a custom accent still
        colours the splash correctly even though no fox is cut for it.
        """
        from ..skin import tokens as T
        slug, glow = T.SPLASH_FOX_DEFAULT, "0xFF" + theme.DEFAULT_ACCENT
        try:
            stored = (kodigui.ADDON.getSettingString("accent_color") or "").lstrip("#").upper()
            if len(stored) == 6:
                slug, glow = theme.fox_slug(stored), "0xFF" + stored
        except Exception as exc:                        # noqa: BLE001
            # A splash in the brand's own colours is a complete splash; only
            # the personalisation is lost, so this may never take the window
            # down with it.
            log.warning(f"splash: keeping the default fox ({exc})")
        self.setProperty(T.SPLASH_FOX_PROPERTY, slug)
        self.setProperty(T.SPLASH_GLOW_PROPERTY, glow)

    def onAction(self, action):
        # Swallows everything WHILE THE ANIMATION RUNS. The splash is not
        # interactive, and letting Back close it early would drop the viewer
        # onto whatever is behind it before the real window has opened --
        # which is the very thing this window exists to prevent.
        #
        # Afterwards it becomes escapable. Normally nothing can reach it by
        # then (the real window is modal and on top), so this only fires if
        # the launch failed on its way to dismissing us, and in that case
        # being stuck behind an undismissable splash would be far worse than
        # seeing Kodi's menu.
        if action.getId() not in _BACK_ACTIONS:
            return
        if time.monotonic() < getattr(self, "_escapable_at", 0.0):
            return
        log.warning("splash: dismissed by Back -- the launch never took it down")
        dismiss()


def is_alive() -> bool:
    """Is there a splash window in Kodi's history for us to fall back onto?

    The flag alone is a CLAIM, not an observation, and it was wrong twice:

    - across processes, because Kodi destroys an interpreter's windows when
      the interpreter goes and nothing cleared the flag (fixed by release());
    - within ONE process, on the profile-switch path, which is what the owner
      still saw: the launch raises a splash, hand_over() drops our only
      reference to it, and by the time the switch closes MainWindow there is
      nothing in the history to walk back onto. The flag still said "1", so
      ensure_up() declined to raise one and the app rebuilt over Kodi's own
      Home. The log says it plainly: "splash: one is already up, not raising
      another", twice, with no splash on screen.

    So ask KODI as well. `Window.Property(tofa_window)` resolves against the
    CURRENT window and XMLBase.onInit stamps it with the class name, which is
    the one identification of our screens that works (System.CurrentWindow
    reports "System" for every Python WindowXML). If a splash is genuinely
    up, that reads SplashWindow.

    Polled briefly rather than sampled once: on the restart path this is
    called immediately after closeNow(), and Kodi re-activating the window
    beneath is not instantaneous. Biased toward RAISING -- a second splash
    costs one replayed animation, a missing one costs Kodi's menu.
    """
    if xbmcgui.Window(_SESSION_WINDOW).getProperty(_ALIVE_PROPERTY) != "1":
        return False
    deadline = time.monotonic() + 0.4
    while True:
        if xbmc.getInfoLabel("Window.Property(tofa_window)") == "SplashWindow":
            return True
        if time.monotonic() >= deadline:
            log.info("splash: flag says alive but no splash is on screen")
            _mark_alive(False)
            return False
        xbmc.sleep(50)


def _mark_alive(alive: bool) -> None:
    window = xbmcgui.Window(_SESSION_WINDOW)
    if alive:
        window.setProperty(_ALIVE_PROPERTY, "1")
    else:
        window.clearProperty(_ALIVE_PROPERTY)


def ensure_up() -> None:
    """Play the splash, unless one is already on screen.

    RETURNS AT ONCE, with the splash on screen and NOT waited out. The launch
    is expected to do its work next (prefetch.warm()), then call wait_out(),
    then open the real window UNDER the splash, which dismiss() finally takes
    down. Closing it here instead is what left Kodi's own menu on screen for
    the ~0.8s the real window took to appear.

    The guard is is_alive() and not "has one been shown this Kodi run": the
    question worth asking is whether the app is about to be built over
    something or over nothing. A profile switch is the case where one IS
    already up -- Kodi re-activated it from its history as the old window
    closed -- and raising a second is the animation that flashed past on the
    box.

    Best-effort throughout: a splash that fails is a missing flourish, never a
    reason to not open the app. Any exception is logged and swallowed -- and
    takes the window with it, so a failure cannot leave one stranded. The
    alive flag is cleared by that failure path too, so a launch that could not
    show one does not leave the next caller believing it did.
    """
    global _pending, _shown_at
    if is_alive():
        log.info("splash: one is already up, not raising another")
        return
    try:
        # BUILT, DRESSED, THEN SHOWN -- not created-and-shown in one call.
        #
        # The fox strips name their texture through $INFO's three-argument
        # form, and Kodi resolves that ONCE, when the control is first built.
        # Setting the property in onInit is too late: onInit runs after the
        # window is up, so the mark had already resolved against an empty
        # property and drew nothing at all for the whole splash.
        #
        # It looked fine the first time it was tested, which is the dangerous
        # part -- the two orderings are milliseconds apart and the race can
        # fall either way. Caught 2026-08-13 only by screen-recording the
        # splash and finding the glow and wordmark present with no fox
        # between them.
        window = SplashWindow.create(show=False)
        if window is None:
            return
        window.dress()
        window.show()
        _pending = window
        _shown_at = time.monotonic()
        _mark_alive(True)
        log.info("splash: raised")
    except Exception as exc:                            # noqa: BLE001
        log.warning(f"splash: not shown ({exc})")
        dismiss()


def wait_out() -> None:
    """Block until the splash has been up for its full run.

    MUST be called before the real window is opened. The splash is a WINDOW,
    so the moment MainWindow opens it is covered -- open it early and the
    animation is simply cut off mid-wipe. This is what turns "return at once"
    into "return at once, then let the caller work, then finish the show".

    A no-op when no splash is up, so a warm launch pays nothing.

    Keyed on is_alive() rather than on `_pending`, which hand_over() clears:
    a splash re-activated from Kodi's history on a profile switch has no
    `_pending` and would otherwise skip the wait entirely, opening the new
    window over a wipe that had just restarted. Self-limiting either way,
    since a splash that has been up longer than its run has nothing left to
    wait for.
    """
    if not is_alive():
        return
    remaining = _MIN_VISIBLE_S - (time.monotonic() - _shown_at)
    if remaining <= 0:
        # The work outlasted the animation, which is the good case: the
        # splash was covering something the whole time.
        return
    # Monitor rather than time.sleep so a Kodi shutdown mid-splash is not
    # held up by us.
    xbmc.Monitor().waitForAbort(remaining)


def hand_over() -> None:
    """Give up ownership of the splash WITHOUT closing it, just before the
    real window is opened.

    This is the safe half of dismiss(). Opening a WindowXML does not stack
    over another one: Kodi DEINITS the splash and pushes the new window into
    its place, so the splash is taken down by the act of opening the app --
    no gap, and nothing for us to close. Calling doClose() afterwards would
    close whatever is CURRENT, which is the app itself
    (project_kodi_double_close_trap, and the failure dismiss() documents).

    So the ordering that removes the Kodi-menu flash is not "close it later",
    it is "do not close it at all". dismiss() before open() left Kodi's own
    window on screen for the ~1s the app took to build -- measured on the box
    at 0.8s, and that is the flash.

    If the launch dies before the app opens, the splash is left up with
    nothing over it; SplashWindow.onAction becomes escapable after
    _ESCAPABLE_AFTER_S precisely for that case.
    """
    global _pending, _handed_over
    _pending = None
    # From here on, any re-activation of the splash by Kodi's window history
    # (see onInit) means the app has closed and we're being walked back to --
    # step aside rather than replay.
    _handed_over = True


def arm_for_restart() -> None:
    """The next re-activation is the app coming BACK, not leaving.

    Call this before closing a window that will be immediately reopened (a
    profile switch; see MainWindow.request_restart). Kodi keeps the .show()n
    splash in its window history underneath the app, so closing the app walks
    back to it -- and once hand_over() has run, onInit reads that as "the app
    has exited" and steps aside, which puts Kodi's own Home on screen.

    Reported from the box: "the startup animation showed very quickly, then I
    saw the Kodi menu, then our Home". Two faults in one. The splash beneath
    stepped aside, exposing Kodi; and the launcher then raised a SECOND
    splash, which is the animation that flashed past.

    Clearing the flag turns that re-activation back into a first show: the
    wipe replays and, crucially, the splash STAYS up -- with nothing to take
    it down until the new window opens over it, which is exactly the cover
    the rebuild needs. hand_over() re-arms the step-aside afterwards, so a
    genuine exit still behaves."""
    global _handed_over
    _handed_over = False


def dismiss() -> None:
    """Take the splash down. Idempotent, and a no-op when none was shown.

    MUST BE CALLED WHILE THE SPLASH IS STILL THE CURRENT WINDOW -- i.e.
    before the real window is opened, not after.

    Opening a WindowXML does not stack it over another WindowXML: Kodi
    DEINITS the splash and pushes the new window in its place. Closing the
    splash object after that point does not close the splash, it closes
    whatever is current -- which is the app that just opened. Seen exactly
    that way in the log while building this:

        Window Deinit splash.xml     <- MainWindow opening replaced it
        Window Init   main.xml
        SplashWindow: doClose called
        Window Deinit main.xml       <- closed the app instead

    the same shape as project_kodi_double_close_trap. doClose defaults to
    force=True, so the isOpen guard inside it does not save us.

    The gap this used to leave (Kodi's menu, while the real window was built)
    is closed from the other end instead: prefetch.warm() has already fetched
    what the window needs, so it paints almost at once.
    """
    global _pending
    window, _pending = _pending, None
    if window is None:
        return
    _mark_alive(False)
    try:
        window.doClose()
    except Exception as exc:                            # noqa: BLE001
        log.warning(f"splash: could not close ({exc})")


def release() -> None:
    """This process is ending, so any splash it owns is ending with it.

    THE BUG THIS FIXES, measured on the box 2026-08-10. `_ALIVE_PROPERTY`
    lives on Kodi's home window so it can outlive our processes -- but the
    SPLASH cannot. Kodi destroys the windows an interpreter created when that
    interpreter is torn down, so the flag was making a claim about a window
    that no longer existed.

    It was only ever cleared in two places, and neither covers the common
    exit. onInit clears it when Kodi walks back onto the splash and it steps
    aside; dismiss() clears it when we still hold a reference -- and by then
    hand_over() has set `_pending = None`, so dismiss() returns at its first
    line and clears nothing. Leave the add-on any way that does not re-activate
    the splash (Kodi's own Home button, for one) and the flag stayed "1"
    forever.

    From then on every profile switch asked ensure_up() whether a splash was
    up, was told yes, raised none -- and rebuilt the app over KODI'S OWN HOME.
    Read straight off the box: `tofa.splash_alive` = "1", one single
    `script-tofa-splash.xml` load in the whole log (the cold start, from a
    process that had long exited), and four profile switches after it with no
    splash at all. The worst was 10.9s of Kodi's menu.

    Deliberately biased toward showing: clearing this when a splash IS still
    alive costs a second animation, which is cosmetic. Not clearing it when
    the splash is gone costs ten seconds of the wrong application on screen.
    """
    _mark_alive(False)
