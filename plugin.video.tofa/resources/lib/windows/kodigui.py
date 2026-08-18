# -*- coding: utf-8 -*-
"""Adapted from plex-for-kodi (https://github.com/plexinc/plex-for-kodi), GPL-2.0.

Source: lib/windows/kodigui.py. Ported classes: BaseFunctions, XMLBase,
BaseWindow, BaseDialog, ControlledBase/ControlledWindow/ControlledDialog,
DummyDataSource/EmptyDataSource, ManagedListItem, ManagedControlList,
_MWBackground/MultiWindow, SafeControlEdit, PropertyTimer, WindowProperty,
GlobalProperty, waitForVisibility.

Stripped of everything Plex-specific so this imports cleanly on xbmc/xbmcgui/
xbmcaddon/xbmcvfs/os/sys alone -- no plexnet, no plexapp, no Jinja templating
(tofa-for-kodi uses static XML, not plex-for-kodi's templated skins).

Two small Plex-specific pieces were load-bearing for the framework but not
deep coupling, so they're replaced below with minimal local stand-ins
rather than dropped: a generic on/off/trigger pub-sub (`plexapp.util.APP`)
used to tell every open window "close yourself" on app shutdown/sign-out,
and a grab-bag of Kodi helpers (logging, an xbmc.Monitor wrapper, settings
access, background-image helpers).
"""
from __future__ import absolute_import

import os
import threading
import time
import traceback

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

# Generic on/off/trigger pub-sub -- minimal local stand-in for
# plexnet.signalsmixin.SignalsMixin (plex-for-kodi's util.APP used it only
# for this). Kept tiny and untyped: only .on/.off/.trigger are called.
class _SignalBus(object):
    def __init__(self):
        self._handlers = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        handlers = self._handlers.get(event)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def trigger(self, event, *args, **kwargs):
        for handler in list(self._handlers.get(event, [])):
            try:
                handler(*args, **kwargs)
            except Exception:
                traceback.print_exc()


APP = _SignalBus()


class NoDataException(Exception):
    pass


def DEBUG_LOG(message, *args):
    if args:
        message = message.format(*args)
    xbmc.log(u"[plugin.video.tofa] {0}".format(message), xbmc.LOGDEBUG)


def LOG(message, *args):
    if args:
        message = message.format(*args)
    xbmc.log(u"[plugin.video.tofa] {0}".format(message), xbmc.LOGINFO)


def ERROR(message, *args):
    if args:
        message = message.format(*args)
    xbmc.log(u"[plugin.video.tofa] {0}".format(message), xbmc.LOGERROR)
    xbmc.log(traceback.format_exc(), xbmc.LOGERROR)


def setGlobalProperty(key, value):
    xbmcgui.Window(10000).setProperty(u"{0}.{1}".format(ADDON_ID, key), value)


def showNotification(header, time_ms=3000, message=""):
    xbmcgui.Dialog().notification(header, message, xbmcgui.NOTIFICATION_INFO, time_ms)


class _AddonSettings(object):
    """Minimal stand-in for plex-for-kodi's util.addonSettings -- only the
    handful of background-related flags BaseWindow._onInit() reads. tofa's
    settings.xml doesn't (yet) expose these as user-facing settings, so this
    just hardcodes the sane defaults rather than reading nonexistent
    setting ids."""
    useSolidBackground = False
    backgroundColour = "-"
    customBackgroundColour = ""
    dbgCrossfade = False
    useBgFallback = True
    dynamicBackgrounds = True


addonSettings = _AddonSettings()
useSolidBackground = addonSettings.useSolidBackground
SKIN_PLEXTUARY = False  # was a Plex reskin detection; no equivalent concept here.
HOME_BUTTON_MAPPED = None  # optional physical Home-button keymap; unmapped by default.

# ---------------------------------------------------------- held-Back unwind --
# "Hold Back to return to the top level" (10.1's escape hatch), implemented
# without a long-press API, because Kodi has none: the Python Action object
# exposes getId/getButtonCode/getAmount but no press phase and no hold time
# (CAction::GetHoldTime is C++-only). This is the same wall 10.2 hit for
# Select, which is why card options uses the context key instead.
#
# What IS observable is the key's AUTO-REPEAT. Holding Back delivers a stream
# of ACTION_NAV_BACK, and since each pushed window closes on the first one it
# sees, the repeats already cascade up the window stack on their own. All
# that is missing is telling a held key apart from three deliberate presses,
# which is what the timestamp below does -- and stopping the cascade at the
# top level so a long hold doesn't fall through and exit the add-on.
# 600, not a tighter value: this only has to separate a held key's repeats
# from deliberate presses, and the cost of the two errors is lopsided --
# guessing "held" too eagerly swallows one Back, guessing it too rarely
# quits the add-on out from under the user.
BACK_UNWIND_MS = 600
_last_back_close = 0.0


def note_back_close():
    """Called by a window closing itself on Back, so the next window up can
    tell whether the Back it is about to receive is the same held key."""
    global _last_back_close
    _last_back_close = time.time()


def back_is_held_repeat():
    """True when a Back arrives soon enough after the last Back-close to be
    an auto-repeat of a still-held key rather than a fresh press."""
    return (time.time() - _last_back_close) * 1000.0 < BACK_UNWIND_MS


class _Monitor(xbmc.Monitor):
    """Local stand-in for plex-for-kodi's util.MONITOR (lib/monitor.py's
    UtilityMonitor) -- only the waitFor/waitAmount/abortRequested surface
    this framework file actually calls."""

    def waitFor(self, amount=0.1):
        return self.waitForAbort(amount)

    def waitAmount(self, amount, interval=0.1):
        return int(amount / interval) if interval else 0


MONITOR = _Monitor()


class BaseFunctions(object):
    xmlFile = ''
    path = ''
    theme = ''
    res = '720p'
    width = 1280
    height = 720

    usesGenerate = False
    lastWinID = None
    lastDialogID = None

    def __init__(self):
        self.isOpen = True

    def onWindowFocus(self):
        # Not automatically called. Can be used by an external window manager
        pass

    def onClosed(self):
        pass

    @classmethod
    def open(cls, **kwargs):
        from .. import hostsetup
        from ..skin import build
        # Checked here, not just in service.py's Kodi-startup pass -- every
        # window class passes through this choke point regardless of entry
        # point, so a FONT_SET_VERSION bump gets caught the next time ANY
        # window opens, not just on Kodi restart. If a restart was just
        # triggered, Kodi is quitting -- bail out instead of building a
        # window that's wasted work.
        if hostsetup.ensure_host_setup():
            return None
        build.ensure_rendered()
        path = cls.path
        aggressive = kwargs.pop('aggressive', False)
        if os.getenv("INSTALLATION_DIR_AVOID_WRITE"):
            path = PROFILE
        window = cls(cls.xmlFile, path, cls.theme, cls.res, **kwargs)
        window.modal(aggressive=aggressive)
        return window

    @classmethod
    def create(cls, show=True, **kwargs):
        from .. import hostsetup
        from ..skin import build
        # See open()'s comment above -- same reasoning applies here.
        if hostsetup.ensure_host_setup():
            return None
        build.ensure_rendered()
        # Use the user addon data directory in installations where the extension installation directory is not writable
        path = cls.path
        if os.getenv("INSTALLATION_DIR_AVOID_WRITE"):
            path = PROFILE
        window = cls(cls.xmlFile, path, cls.theme, cls.res, **kwargs)

        if show:
            window.show()
            if xbmcgui.getCurrentWindowId() < 13000:
                window.isOpen = False
                return window

        window.isOpen = xbmcgui.getCurrentWindowId() >= 13000
        return window

    def modal(self, aggressive=False):
        self.isOpen = True
        try:
            self.doModal(aggressive=aggressive)
        except SystemExit:
            pass
        self.onClosed()
        self.isOpen = False

    def activate(self):
        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()
        xbmc.executebuiltin('ReplaceWindow({0})'.format(self._winID))

    def mouseXTrans(self, val):
        return int((val / self.getWidth()) * self.width)

    def mouseYTrans(self, val):
        return int((val / self.getHeight()) * self.height)

    def closing(self):
        return self._closing

    @classmethod
    def generate(self):
        return None

    def setProperties(self, prop_list, val_list_or_val):
        if isinstance(val_list_or_val, list) or isinstance(val_list_or_val, tuple):
            val_list = val_list_or_val
        else:
            val_list = [val_list_or_val] * len(prop_list)

        for prop, val in zip(prop_list, val_list):
            self.setProperty(prop, val)

    def propertyContext(self, prop, val='1'):
        return WindowProperty(self, prop, val)

    def setBoolProperty(self, key, boolean):
        self.setProperty(key, boolean and '1' or '')

    def getBoolProperty(self, key):
        return self.getProperty(key) == '1'

    def waitForVisibility(self, control):
        return waitForVisibility(control)

    def waitAndSetFocus(self, control):
        self.waitForVisibility(control)
        self.setFocusId(control)


LAST_BG_URL = None
BG_NA = ""


class XMLBase(object):
    defer_init = False
    defer_init_time = 0.25
    identity_property = "tofa_window"

    def onInit(self, count=0):
        if not self.started:
            if self.defer_init:
                DEBUG_LOG("Kodigui: Deferring init of {} for {}s", self, self.defer_init_time)
                MONITOR.waitForAbort(self.defer_init_time)
            try:
                self.getControl(666)
            except RuntimeError as e:
                if e.args and "Non-Existent Control" in e.args[0]:
                    if count < 8:
                        xbmc.sleep(250)
                        return self.onInit(count=count + 1)

                    ERROR("Possibly broken XML file: {}".format(self.xmlFile))
                    showNotification("Recompiling templates", time_ms=1000,
                                      message="Possibly broken XML file(s)")

                    try:
                        if xbmc.Player().isPlaying():
                            try:
                                xbmc.Player().stop()
                            except Exception:
                                pass

                        tries = 0
                        while xbmc.Player().isPlaying() and tries < MONITOR.waitAmount(5):
                            MONITOR.waitFor()
                            tries += 1
                    except Exception:
                        pass

                    xbmc.sleep(1000)

                    try:
                        self._errored = True
                        self.doClose()
                    except Exception:
                        pass
                    return
                raise
        # Names the screen for anything asking "which tofa screen is up?".
        # Kodi reports System.CurrentWindow as "System" for every Python
        # WindowXML -- sometimes as unrelated text, since it resolves the
        # window id through a localised string table -- so it can tell
        # neither our screens apart nor ours from Kodi's own. Windows and
        # dialogs get separate keys because both land on the same underlying
        # window (a dialog has no id of its own this early, so setProperty
        # falls through to the window beneath it), and one key would mean a
        # picker permanently renaming the screen that opened it.
        # tools/kodictl.py asserts on these before and after each step.
        #
        # setProperty writes TWO copies for a dialog -- one on the dialog and
        # one on the window beneath it -- and both are needed: Kodi resolves
        # Window.Property against the topmost window, so only the dialog's own
        # copy is readable while it is up, while only the one underneath
        # survives to be found stale afterwards. Which window "beneath" means
        # is decided here, before _onInit swaps _winID to the dialog's own id,
        # so it is remembered for doClose to clear the copy setProperty can no
        # longer reach.
        self._identity_winid = self._winID or xbmcgui.getCurrentWindowId()
        self.setProperty(self.identity_property, self.__class__.__name__)
        self._onInit()

    def goHomeAction(self, action):
        if (HOME_BUTTON_MAPPED is not None
                and action.getButtonCode() == int(HOME_BUTTON_MAPPED) and hasattr(self, "goHome")):
            DEBUG_LOG("Kodigui: Going home action")
            self.goHome(with_root=True)
            return True
        return


class BaseWindow(XMLBase, xbmcgui.WindowXML, BaseFunctions):
    __slots__ = ("_closing", "_winID", "started", "finishedInit", "dialogProps", "isOpen", "_errored",
                 "_closeSignalled")
    supportsAutoPlay = False

    def __init__(self, *args, **kwargs):
        BaseFunctions.__init__(self)
        self._closing = False
        self._errored = False
        self._closeSignalled = False
        self._winID = None
        self.started = False
        self.finishedInit = False
        self.dialogProps = kwargs.get("dialog_props", None)

        carryProps = kwargs.get("window_props", None)
        if carryProps:
            self.setProperties(list(carryProps.keys()), list(carryProps.values()))

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose(force=True)

    def _onInit(self):
        global LAST_BG_URL
        self._winID = xbmcgui.getCurrentWindowId()
        BaseFunctions.lastWinID = self._winID
        self.setProperty('use_solid_background', useSolidBackground and '1' or '')
        if useSolidBackground:
            bgColour = addonSettings.backgroundColour if addonSettings.backgroundColour != "-" else "ff000000"
            self.setProperty('background_colour', "0x%s" % bgColour.lower())
            self.setProperty('background_colour_opaque', "0x%s" % bgColour.lower())
        else:
            # set background color to 0 to avoid kodi UI BG clearing, improves performance
            if addonSettings.dbgCrossfade:
                self.setProperty('background_colour', "0x00000000")
            else:
                self.setProperty('background_colour', "0xff030b10")
            self.setProperty('background_colour_opaque', "0xff030b10")

        self.setBoolProperty('use_bg_fallback', addonSettings.useBgFallback)
        self.setBoolProperty('dynamic_backgrounds', addonSettings.dynamicBackgrounds)

        try:
            if self.started:
                if hasattr(self, "onReInit"):
                    self.onReInit()
            else:
                self.started = True
                if LAST_BG_URL:
                    self.windowSetBackground(LAST_BG_URL)

                if self.__class__.__name__ not in ("HomeWindow", "BackgroundWindow"):
                    APP.on('close.windows', self.onCloseSignal)

                if hasattr(self, "onFirstInit"):
                    self.onFirstInit()
                self.finishedInit = True
            setGlobalProperty('active_window', self.__class__.__name__)

        except NoDataException:
            self.exitCommand = "NODATA"
            self.doClose()

    def onAction(self, action):
        if XMLBase.goHomeAction(self, action):
            return
        xbmcgui.WindowXML.onAction(self, action)

    def onReInit(self):
        pass

    def doAutoPlay(self, blind=False):
        pass

    def onBlindClose(self):
        pass

    def waitForOpen(self, base_win_id=None):
        def not_open():
            return (not base_win_id and not self.isOpen) or (base_win_id and xbmcgui.getCurrentWindowId() < base_win_id)

        if not not_open():
            DEBUG_LOG("Window {} opened: {}", self, self.isOpen)
            return True

        tries = 0
        while not_open() and tries < MONITOR.waitAmount(120, interval=1.0):
            if tries == 0:
                LOG("Couldn't open window {}, other dialog open? Retrying for 120s. ({}, {}, {})", self, base_win_id, xbmcgui.getCurrentWindowId(), self.isOpen)
            if MONITOR.abortRequested():
                LOG("Couldn't open window {}, abort requested ({}, {}, {})", self, base_win_id, xbmcgui.getCurrentWindowId(), self.isOpen)
                break
            self.show()
            if not not_open():
                break
            if not self.isOpen:
                tries += 1
                MONITOR.waitFor(1.0)
            else:
                break

        DEBUG_LOG("Window {} opened: {}", self, self.isOpen)

        return self.isOpen

    def setProperty(self, key, value):
        if self._closing:
            return

        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()

        try:
            xbmcgui.Window(self._winID).setProperty(key, value)
            xbmcgui.WindowXML.setProperty(self, key, value)
        except RuntimeError:
            DEBUG_LOG('kodigui.BaseWindow.setProperty: Missing window ({}) ({})', self._winID, key)

    def setCondFocusId(self, focus):
        if self.getFocusId() != focus:
            self.setFocusId(focus)

    def updateBackgroundFrom(self, ds):
        if addonSettings.dynamicBackgrounds and ds:
            art = ds.get('art') or ds.get('parentArt') or ds.get('grandparentArt')
            if art:
                return self.windowSetBackground(art)

    def windowSetBackground(self, value):
        if not addonSettings.dbgCrossfade:
            if not value:
                return
            self.setProperty("background_static", value)
            return value

        global LAST_BG_URL

        if not value:
            bg = LAST_BG_URL or BG_NA
            self.setProperty("background_static", bg)
            self.setProperty("background", BG_NA)
            LAST_BG_URL = BG_NA
            return BG_NA

        cur1 = self.getProperty('background')
        if not cur1:
            self.setProperty("background_static", value)
            self.setProperty("background", value)

        elif LAST_BG_URL != value:
            self.setProperty("background_static", LAST_BG_URL)
            self.setProperty("background", value)

        LAST_BG_URL = value
        return value

    def doClose(self, **kw):
        force = kw.get('force', True)
        APP.off('close.windows', self.onCloseSignal)
        DEBUG_LOG("{}: doClose called, force: {}", self.__class__.__name__, force)
        if not self.isOpen and not force:
            return
        self._closing = True
        self.isOpen = False
        self.close()

    def show(self, aggressive=False):
        self._closing = False
        # can we activate?
        ct = 0
        while xbmcgui.getCurrentWindowDialogId() > 9999 and ct < MONITOR.waitAmount(2):
            MONITOR.waitFor()
            ct += 1

        lastWinID = BaseFunctions.lastWinID

        xbmcgui.WindowXML.show(self)

        if aggressive:
            cid = xbmcgui.getCurrentWindowId()
            DEBUG_LOG("{}: checking window state (ID: {}, last: {}, current: {})", self, self._winID, lastWinID, cid)
            if (self._winID and cid != self._winID) or not self._winID or xbmcgui.getCurrentWindowId() == lastWinID:
                if xbmcgui.getCurrentWindowId() == lastWinID:
                    DEBUG_LOG('{}: not yet active, retrying', self.__class__.__name__)
                    MONITOR.waitFor()

                ct = 0
                while xbmcgui.getCurrentWindowId() == lastWinID and ct < MONITOR.waitAmount(2, interval=0.5) and not MONITOR.abortRequested():
                    ct += 1
                    xbmcgui.WindowXML.show(self)
                    MONITOR.waitFor(0.5)

                DEBUG_LOG("{}: activation state (ID: {}, last: {}, current: {})", self, self._winID, lastWinID, xbmcgui.getCurrentWindowId())

        self.isOpen = xbmcgui.getCurrentWindowId() >= 13000

    @property
    def is_active(self):
        return self._winID and BaseFunctions.lastWinID == self._winID

    @property
    def is_current_window(self):
        return self._winID and xbmcgui.getCurrentWindowId() == self._winID

    def onClosed(self):
        pass


class BaseDialog(XMLBase, xbmcgui.WindowXMLDialog, BaseFunctions):
    __slots__ = ("_closing", "_winID", "started", "isOpen", "_errored", "_closeSignalled", "dialogProps")

    identity_property = "tofa_dialog"

    def __init__(self, *args, **kwargs):
        BaseFunctions.__init__(self)
        self._closing = False
        self._errored = False
        self._closeSignalled = False
        self._winID = ''
        self.started = False

        carryProps = kwargs.get("dialog_props", None)
        self.dialogProps = carryProps
        if carryProps:
            self.setProperties(list(carryProps.keys()), list(carryProps.values()))

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose()

    def _onInit(self):
        self._winID = xbmcgui.getCurrentWindowDialogId()
        BaseFunctions.lastDialogID = self._winID
        if self.started:
            self.onReInit()
        else:
            self.started = True
            APP.on('close.dialogs', self.onCloseSignal)
            self.onFirstInit()

    def onAction(self, action):
        if XMLBase.goHomeAction(self, action):
            return
        xbmcgui.WindowXMLDialog.onAction(self, action)

    def onFirstInit(self):
        pass

    def onReInit(self):
        pass

    def setProperty(self, key, value):
        if self._closing:
            return

        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()

        try:
            xbmcgui.Window(self._winID).setProperty(key, value)
            xbmcgui.WindowXMLDialog.setProperty(self, key, value)
        except RuntimeError:
            xbmc.log('kodigui.BaseDialog.setProperty: Missing window', xbmc.LOGDEBUG)

    def doClose(self, **kw):
        APP.off('close.dialogs', self.onCloseSignal)
        # Both copies of the name (see onInit), before _closing makes
        # setProperty a no-op. Leaving either behind says a picker is still
        # open long after it closed.
        try:
            xbmcgui.Window(self._identity_winid).clearProperty(self.identity_property)
        except (RuntimeError, AttributeError):
            pass
        self.setProperty(self.identity_property, "")
        self._closing = True
        self.close()
        self.isOpen = False

    def show(self):
        self._closing = False
        xbmcgui.WindowXMLDialog.show(self)
        self.isOpen = True

    def onClosed(self):
        pass


class ControlledBase:
    def doModal(self, aggressive=False):
        self.show(aggressive=aggressive)
        self.wait()

    def wait(self):
        while not self._closing and not MONITOR.waitFor():
            pass

    def close(self):
        self._closing = True


class ControlledWindow(ControlledBase, BaseWindow):
    # opt-in: actively dismiss the Kodi window on a genuine back-out (see onAction). Off by
    # default; ControlledBase.close() only flips a flag, so non-opted windows keep relying on
    # GC/parent re-activate and windows with their own teardown (video player) stay untouched.
    dismissOnClose = False
    _dismissed = False

    def _dismiss(self):
        """Remove the native Kodi window -- at most once, ever.

        The guard is the whole point. More than one path can decide a window
        is finished, and they race: backing out of the player stops playback
        AND closes the window, while Kodi delivers onPlayBackStopped on its
        own thread a few milliseconds later, and that handler closes too.

        A second xbmcgui.WindowXML.close() does NOT no-op on an
        already-removed window. It pops whatever is frontmost *now*, which is
        the window underneath -- so one Back out of the player closed the
        player and then Home as well, dumping the viewer on Kodi's menu.
        doClose() is idempotent and always runs; only the native removal
        needs protecting."""
        if self._dismissed or not self.dismissOnClose:
            return
        self._dismissed = True
        try:
            xbmcgui.WindowXML.close(self)
        except Exception:
            pass

    def closeNow(self):
        """Like doClose(), but also actually removes the native Kodi window
        immediately when dismissOnClose is set, same as a real Back
        keypress does (see onAction below) -- for callers that close a
        window programmatically (e.g. opening a replacement window
        in-process) rather than via the Back/Previous-menu action."""
        self.doClose()
        self._dismiss()

    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                # Timestamped so the window this returns to can tell a held
                # key's auto-repeat from a second deliberate press.
                note_back_close()
                self.doClose()
                self._dismiss()
                return
        except Exception:
            traceback.print_exc()

        BaseWindow.onAction(self, action)


class ControlledDialog(ControlledBase, BaseDialog):
    _dismissed = False

    def _dismiss(self):
        """Actually remove the dialog. At most once, ever.

        doClose() alone does NOT: BaseDialog.doClose() ends with
        self.close(), and on a ControlledBase that is just `_closing = True`
        -- a flag for wait() to notice, not a teardown. ControlledWindow has
        always compensated with its own _dismiss(); ControlledDialog never
        did, because until the player became one, nothing opened a
        ControlledDialog modally and the gap could not show.

        What it looked like: back out of the player, playback stops, the
        dialog clears its identity property and stops responding -- and stays
        on screen, on top of the Detail page, swallowing every key. The page
        underneath was visible and completely unnavigable.

        The guard is ControlledWindow's, for ControlledWindow's reason: a
        second close() does not no-op on an already-removed dialog, it pops
        whatever is frontmost now, which would be the window underneath.
        """
        if self._dismissed:
            return
        self._dismissed = True
        try:
            xbmcgui.WindowXMLDialog.close(self)
        except Exception:
            pass

    def closeNow(self):
        """ControlledWindow's name for "close AND remove", so callers that
        hold either kind do not care which they have."""
        self.doClose()
        self._dismiss()

    def show(self, aggressive=False):
        """Swallow `aggressive`, which only BaseWindow has.

        ControlledBase.doModal() passes it through unconditionally, and it
        reaches BaseWindow.show(aggressive=False) fine -- but
        BaseDialog.show() takes no arguments, so every ControlledDialog
        opened via open()/modal() died with "show() got an unexpected keyword
        argument 'aggressive'". Latent until PlayerWindow became the first
        ControlledDialog actually opened that way.

        Accepted and dropped rather than forwarded: `aggressive` selects
        BaseWindow's re-show-until-it-sticks behaviour, and a dialog has no
        equivalent to opt into.
        """
        BaseDialog.show(self)

    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                self.doClose()
                # ...and REMOVE it. doClose only flips the flag here; see
                # _dismiss. Backing out used to leave the dialog on screen
                # over whatever raised it, taking every key press with it.
                self._dismiss()
                return
        except Exception:
            traceback.print_exc()

        BaseDialog.onAction(self, action)


DUMMY_LIST_ITEM = xbmcgui.ListItem()


class DummyDataSource(object):
    def __nonzero__(self):
        return False

    __bool__ = __nonzero__

    def exists(self, *args, **kwargs):
        return False


class EmptyDataSource(DummyDataSource):
    def __getattr__(self, item):
        return None

    def __setattr__(self, key, value):
        raise NotImplementedError


DUMMY_DATA_SOURCE = DummyDataSource()


class ManagedListItem(object):
    __slots__ = ("_listItem", "dataSource", "properties", "label", "label2", "iconImage", "thumbnailImage", "path",
                 "_ID", "_manager", "_valid")

    def __init__(self, label='', label2='', iconImage='', thumbnailImage='', path='', data_source=None,
                 properties=None, offscreen=False):
        # `offscreen` is not cosmetic -- it is the difference between a card
        # costing 0.03ms and 0.24ms on the box, and much more than that while
        # Home is loading. EVERY setter on xbmcgui.ListItem opens with
        #
        #     XBMCAddonUtils::GuiLock lock(languageHook, m_offscreen);
        #
        # and GuiLock's constructor calls g_application.LockFrameMoveGuard()
        # unless m_offscreen -- the mutex CApplication holds for the whole of
        # FrameMove + Render. So a ListItem write from a background thread
        # waits on the renderer, and our loads run off the action thread. At
        # 4K the box is fill-bound (~15fps), so that guard is held for most of
        # every frame and each of a card's ~8 writes queues behind it. That is
        # why the cost is spread evenly across label/setArt/rating/badges --
        # a label has nothing to do with artwork, but it takes the same lock.
        # See issue #11.
        #
        # Defaults to False because skipping the lock is only safe for an item
        # that is NOT being rendered while it is written. Pass True when the
        # item is built detached and handed to addItems() afterwards; leave it
        # False for anything mutated in place inside a live container (Browse
        # fills the blanks already sitting in its grid -- main.py
        # _browse_apply_grid_item), where the lock is what keeps our writes
        # off the render thread's reads.
        self._listItem = xbmcgui.ListItem(label, label2, path=path, offscreen=offscreen)
        # Only when there is art to set. Setting {"thumb": "", "icon": ""} is a
        # no-op with a real C++ call behind it, and Browse allocates one blank
        # ListItem per title in the library up front (main.py:_browse_blanks) --
        # 10,741 of them on the big library here, so the wasted call was paid
        # 10,741 times per source switch.
        if thumbnailImage or iconImage:
            self._listItem.setArt({"thumb": thumbnailImage, "icon": iconImage})
        self.dataSource = data_source
        self.properties = {}
        self.label = label
        self.label2 = label2
        self.iconImage = iconImage
        self.thumbnailImage = thumbnailImage
        self.path = path
        self._ID = None
        self._manager = None
        self._valid = True

        if properties:
            for k, v in properties.items():
                self.setProperty(k, v)

    def __nonzero__(self):
        return self._valid

    __bool__ = __nonzero__

    @property
    def listItem(self):
        if not self._listItem:
            if not self._manager:
                return None

            try:
                self._listItem = self._manager.getListItemFromManagedItem(self)
            except RuntimeError:
                return None

        return self._listItem

    def invalidate(self):
        self._valid = False
        self._listItem = DUMMY_LIST_ITEM
        self.dataSource = DUMMY_DATA_SOURCE

    def _takeListItem(self, manager, lid):
        self._manager = manager
        self._ID = lid
        self._listItem.setProperty('__ID__', lid)
        li = self._listItem
        self._listItem = None
        self._manager._properties.update(self.properties)
        return li

    def _updateListItem(self):
        self.listItem.setProperty('__ID__', self._ID)
        self.listItem.setLabel(self.label)
        self.listItem.setLabel2(self.label2)
        self.listItem.setArt({"thumb": self.thumbnailImage, "icon": self.iconImage})
        self.listItem.setPath(self.path)
        for k in self._manager._properties.keys():
            self.listItem.setProperty(k, self.properties.get(k) or '')

    def clear(self):
        self.label = ''
        self.label2 = ''
        self.iconImage = ''
        self.thumbnailImage = ''
        self.path = ''
        for k in self.properties:
            self.properties[k] = ''
        self._updateListItem()

    def pos(self):
        if not self._manager:
            return None
        return self._manager.getManagedItemPosition(self)

    def addContextMenuItems(self, items, replaceItems=False):
        self.listItem.addContextMenuItems(items, replaceItems)

    def addStreamInfo(self, stype, values):
        self.listItem.addStreamInfo(stype, values)

    def getLabel(self):
        return self.label

    def getLabel2(self):
        return self.label2

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getdescription(self):
        return self.listItem.getdescription()

    def getduration(self):
        return self.listItem.getduration()

    def getfilename(self):
        return self.listItem.getfilename()

    def isSelected(self):
        return self.listItem.isSelected()

    def select(self, selected):
        return self.listItem.select(selected)

    def setArt(self, values):
        return self.listItem.setArt(values)

    def setIconImage(self, icon):
        self.iconImage = icon
        return self.listItem.setArt({"icon": self.iconImage})

    def setInfo(self, itype, infoLabels):
        return self.listItem.setInfo(itype, infoLabels)

    def setLabel(self, label):
        self.label = label
        return self.listItem.setLabel(label)

    def setLabel2(self, label):
        self.label2 = label
        return self.listItem.setLabel2(label)

    def setMimeType(self, mimetype):
        return self.listItem.setMimeType(mimetype)

    def setPath(self, path):
        self.path = path
        return self.listItem.setPath(path)

    def setProperty(self, key, value):
        if self._manager:
            self._manager._properties[key] = 1
        self.properties[key] = value
        self.listItem.setProperty(key, value)
        return self

    def setProperties(self, prop_list, val_list_or_val):
        if isinstance(val_list_or_val, list) or isinstance(val_list_or_val, tuple):
            val_list = val_list_or_val
        else:
            val_list = [val_list_or_val] * len(prop_list)

        for prop, val in zip(prop_list, val_list):
            self.setProperty(prop, val)

    def setBoolProperty(self, key, boolean):
        return self.setProperty(key, boolean and '1' or '')

    def setSubtitles(self, subtitles):
        return self.listItem.setSubtitles(subtitles)

    def setThumbnailImage(self, thumb):
        self.thumbnailImage = thumb
        return self.listItem.setArt({"thumb": self.thumbnailImage})

    def onDestroy(self):
        pass


class ManagedControlList(object):
    __slots__ = ("controlID", "control", "items", "_sortKey", "_idCounter", "_maxViewIndex", "_properties",
                 "dataSource")

    def __init__(self, window, control_id, max_view_index, data_source=None):
        self.controlID = control_id
        self.control = window.getControl(control_id)
        self.items = []
        self._sortKey = None
        self._idCounter = 0
        self._maxViewIndex = max_view_index
        self._properties = {}
        self.dataSource = data_source

    def __getattr__(self, name):
        return getattr(self.control, name)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return self.items[idx]
        else:
            return self.getListItem(idx)

    def __iter__(self):
        for i in self.items:
            yield i

    def __len__(self):
        return self.size()

    def prev(self):
        pos = self.getSelectedPos() - 1
        if self.positionIsValid(pos):
            return pos
        return 0

    def _updateItems(self, bottom=None, top=None):
        if bottom is None:
            bottom = 0
            top = self.size()

        try:
            for idx in range(bottom, top):
                try:
                    li = self.control.getListItem(idx)
                except RuntimeError:
                    continue

                mli = self.items[idx]
                self._properties.update(mli.properties)
                mli._manager = self
                mli._listItem = li
                mli._updateListItem()
                mli.setProperty('index', str(idx))
        except RuntimeError:
            ERROR('kodigui.ManagedControlList._updateItems: Runtime error')
            return False

        return True

    def _nextID(self):
        self._idCounter += 1
        return str(self._idCounter)

    def reInit(self, window, control_id):
        self.controlID = control_id
        self.control = window.getControl(control_id)
        self.control.addItems([i._takeListItem(self, self._nextID()) for i in self.items])

    def setSort(self, sort):
        self._sortKey = sort

    def addItem(self, managed_item):
        self.items.append(managed_item)
        self.control.addItem(managed_item._takeListItem(self, self._nextID()))

    def addItems(self, managed_items):
        self.items += managed_items
        self.control.addItems([i._takeListItem(self, self._nextID()) for i in managed_items])

    def replaceItem(self, pos, mli):
        self[pos].onDestroy()
        self[pos].invalidate()
        self.items[pos] = mli
        li = self.control.getListItem(pos)
        mli._manager = self
        mli._listItem = li
        mli._updateListItem()

    def replaceItems(self, managed_items):
        if not self.items:
            self.addItems(managed_items)
            return True

        oldSize = self.size()

        for i in self.items:
            i.onDestroy()
            i.invalidate()

        self.items = managed_items
        size = self.size()
        if size != oldSize:
            pos = self.getSelectedPosition()

            if size > oldSize:
                for i in range(0, size - oldSize):
                    self.control.addItem(xbmcgui.ListItem())
            elif size < oldSize:
                diff = oldSize - size
                idx = oldSize - 1
                while diff:
                    self.control.removeItem(idx)
                    idx -= 1
                    diff -= 1

            if self.positionIsValid(pos):
                self.selectItem(pos)
            elif pos >= size:
                self.selectItem(size - 1)

        return self._updateItems(0, self.size())

    def getListItem(self, pos):
        li = self.control.getListItem(pos)
        mli = self.items[pos]
        mli._listItem = li
        return mli

    def getListItemByDataSource(self, data_source):
        for mli in self:
            if data_source == mli.dataSource:
                return mli
        return None

    def getSelectedItem(self):
        pos = self.control.getSelectedPosition()
        if not self.positionIsValid(pos):
            pos = self.size() - 1

        if pos < 0:
            return None
        return self.getListItem(pos)

    def getSelectedPos(self):
        pos = self.control.getSelectedPosition()
        if not self.positionIsValid(pos):
            pos = self.size() - 1

        if pos < 0:
            return None
        return pos

    def getItemByPos(self, pos):
        if self.positionIsValid(pos):
            return self.getListItem(pos)

    def setSelectedItemByPos(self, pos):
        if self.positionIsValid(pos):
            self.control.selectItem(pos)

    def setSelectedItem(self, item):
        pos = self.getManagedItemPosition(item)
        if self.positionIsValid(pos):
            self.control.selectItem(pos)

    def setSelectedItemByDataSource(self, data_source):
        mli = self.getListItemByDataSource(data_source)
        if mli:
            self.setSelectedItem(mli)
            return True
        return False

    def removeItem(self, index):
        old = self.items.pop(index)
        old.onDestroy()
        old.invalidate()

        self.control.removeItem(index)
        top = self.control.size() - 1
        if top < 0:
            return
        if top < index:
            index = top
        self.control.selectItem(index)

    def removeManagedItem(self, mli):
        self.removeItem(mli.pos())

    def insertItem(self, index, managed_item):
        pos = self.getSelectedPosition() + 1

        if index >= self.size() or index < 0:
            self.addItem(managed_item)
        else:
            self.items.insert(index, managed_item)
            self.control.addItem(managed_item._takeListItem(self, self._nextID()))
            self._updateItems(index, self.size())

        if self.positionIsValid(pos):
            self.selectItem(pos)

    def moveItem(self, mli, dest_idx):
        source_idx = mli.pos()
        if source_idx < dest_idx:
            rstart = source_idx
            rend = dest_idx + 1
        else:
            rstart = dest_idx
            rend = source_idx + 1
        mli = self.items.pop(source_idx)
        self.items.insert(dest_idx, mli)

        self._updateItems(rstart, rend)

    def swapItems(self, pos1, pos2):
        if not self.positionIsValid(pos1) or not self.positionIsValid(pos2):
            return False

        item1 = self.items[pos1]
        item2 = self.items[pos2]
        li1 = item1._listItem
        li2 = item2._listItem
        item1._listItem = li2
        item2._listItem = li1

        item1._updateListItem()
        item2._updateListItem()
        self.items[pos1] = item2
        self.items[pos2] = item1

        return True

    def shiftView(self, shift, hold_selected=False):
        if not self._maxViewIndex:
            return
        selected = self.getSelectedItem()
        selectedPos = selected.pos()
        viewPos = self.getViewPosition()

        if shift > 0:
            pushPos = selectedPos + (self._maxViewIndex - viewPos) + shift
            if pushPos >= self.size():
                pushPos = self.size() - 1
            self.selectItem(pushPos)
            newViewPos = self._maxViewIndex
        elif shift < 0:
            pushPos = (selectedPos - viewPos) + shift
            if pushPos < 0:
                pushPos = 0
            self.selectItem(pushPos)
            newViewPos = 0
        else:
            return

        if hold_selected:
            self.selectItem(selected.pos())
        else:
            diff = newViewPos - viewPos
            fix = pushPos - diff
            if self.positionIsValid(fix):
                self.selectItem(fix)

    def reset(self):
        self.dataSource = None
        for i in self.items:
            i.onDestroy()
            i.invalidate()
        self.items = []
        self.control.reset()

    def size(self):
        return len(self.items)

    def getViewPosition(self):
        try:
            return int(xbmc.getInfoLabel('Container({0}).Position'.format(self.controlID)))
        except Exception:
            return 0

    def getViewRange(self):
        viewPosition = self.getViewPosition()
        selected = self.getSelectedPosition()
        return list(range(max(selected - viewPosition, 0), min(selected + (self._maxViewIndex - viewPosition) + 1, self.size() - 1)))

    def positionIsValid(self, pos):
        return 0 <= pos < self.size()

    def sort(self, sort=None, reverse=False):
        sort = sort or self._sortKey

        self.items.sort(key=sort, reverse=reverse)

        self._updateItems(0, self.size())

    def reverse(self):
        self.items.reverse()
        self._updateItems(0, self.size())

    def getManagedItemPosition(self, mli):
        return self.items.index(mli)

    def isLastItem(self, mli=None):
        return self.getManagedItemPosition(mli or self.getSelectedItem()) + 1 == len(self)

    def getListItemFromManagedItem(self, mli):
        pos = self.items.index(mli)
        return self.control.getListItem(pos)

    def topHasFocus(self):
        return self.getSelectedPosition() == 0

    def bottomHasFocus(self):
        return self.getSelectedPosition() == self.size() - 1

    def invalidate(self):
        for item in self.items:
            item._listItem = DUMMY_LIST_ITEM

    def newControl(self, window=None, control_id=None):
        self.controlID = control_id or self.controlID
        self.control = window.getControl(self.controlID)
        self.control.addItems([xbmcgui.ListItem() for i in range(self.size())])
        self._updateItems()


class _MWBackground(ControlledWindow):
    __slots__ = ("_multiWindow", "started")

    def __init__(self, *args, **kwargs):
        self._multiWindow = kwargs.get('multi_window')
        self.started = False
        BaseWindow.__init__(self, *args, **kwargs)

    def onInit(self):
        if self.started:
            return
        self.started = True
        self._multiWindow._open()
        self.close()


class MultiWindow(object):
    def __init__(self, windows=None, default_window=None, **kwargs):
        self._windows = windows
        self._next = default_window or self._windows[0]
        self._properties = {}
        self._current = None
        self._allClosed = False
        self._closeSignalled = False
        self.exitCommand = None

    def __getattr__(self, name):
        if self._current:
            return getattr(self._current, name)

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose()

    def setWindows(self, windows):
        self._windows = windows

    def setDefault(self, default):
        self._next = default or self._windows[0]

    def windowIndex(self, window):
        if hasattr(window, 'MULTI_WINDOW_ID'):
            for i, w in enumerate(self._windows):
                if window.MULTI_WINDOW_ID == w.MULTI_WINDOW_ID:
                    return i
            return 0
        else:
            return self._windows.index(window.__class__)

    def nextWindow(self, window=None):
        if window is False:
            window = self._windows[self.windowIndex(self._current)]

        if window:
            if window.__class__ == self._current.__class__:
                return None
        else:
            idx = self.windowIndex(self._current)
            idx += 1
            if idx >= len(self._windows):
                idx = 0
            window = self._windows[idx]

        self._next = window
        self._current.doClose()
        return self._next

    def _setupCurrent(self, cls):
        self._current = cls(cls.xmlFile, cls.path, cls.theme, cls.res)
        self._current.onFirstInit = self._onFirstInit
        self._current.onReInit = self.onReInit
        self._current.onClick = self.onClick
        self._current.onFocus = self.onFocus

        self._currentOnAction = self._current.onAction
        self._current.onAction = self.onAction

    @classmethod
    def open(cls, **kwargs):
        mw = cls(**kwargs)
        b = _MWBackground(mw.bgXML, mw.path, mw.theme, mw.res, multi_window=mw)
        b.modal()
        del b
        import gc
        gc.collect(2)
        return mw

    def _open(self):
        while not MONITOR.abortRequested() and not self._allClosed:
            self._setupCurrent(self._next)
            self._current.modal()

        self._current.doClose()
        del self._current
        del self._next
        del self._currentOnAction

    def setProperty(self, key, value):
        self._properties[key] = value
        self._current.setProperty(key, value)

    def _onFirstInit(self):
        for k, v in self._properties.items():
            self._current.setProperty(k, v)

        APP.on('close.windows', self.onCloseSignal)
        self.onFirstInit()

    def doClose(self, **kw):
        APP.off('close.windows', self.onCloseSignal)
        self._allClosed = True
        self._current.doClose()

    def goHomeAction(self, action):
        if (HOME_BUTTON_MAPPED is not None
                and action.getButtonCode() == int(HOME_BUTTON_MAPPED) and hasattr(self, "goHome")):
            DEBUG_LOG("MultiWindow: Going home action")
            self.goHome(with_root=True)
            return True
        return

    def onFirstInit(self):
        pass

    def onReInit(self):
        pass

    def onAction(self, action):
        if action == xbmcgui.ACTION_PREVIOUS_MENU or action == xbmcgui.ACTION_NAV_BACK:
            self.doClose()
        elif self.goHomeAction(action):
            return
        self._currentOnAction(action)

    def onClick(self, controlID):
        pass

    def onFocus(self, controlID):
        pass


class SafeControlEdit(object):
    CHARS_LOWER = 'abcdefghijklmnopqrstuvwxyz'
    CHARS_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    CHARS_NUMBERS = '0123456789'
    CURSOR = '[COLOR FFCC7B19]|[/COLOR]'

    def __init__(self, control_id, label_id, window, key_callback=None, grab_focus=False):
        self.controlID = control_id
        self.labelID = label_id
        self._win = window
        self._keyCallback = key_callback
        self.grabFocus = grab_focus
        self._text = ''
        self._compatibleMode = False
        self.setup()

    def setup(self):
        self._labelControl = self._win.getControl(self.labelID)
        self._winOnAction = self._win.onAction
        self._win.onAction = self.onAction
        self.updateLabel()

    def setCompatibleMode(self, on):
        self._compatibleMode = on

    def onAction(self, action):
        try:
            controlID = self._win.getFocusId()
            if controlID == self.controlID:
                if self.processAction(action.getId()):
                    return
            elif self.grabFocus:
                if self.processOffControlAction(action.getButtonCode()):
                    self._win.setFocusId(self.controlID)
                    return
        except Exception:
            traceback.print_exc()

        self._winOnAction(action)

    def processAction(self, action_id):
        if not self._compatibleMode:
            oldVal = self._text
            self._text = self._win.getControl(self.controlID).getText()

            if self._keyCallback:
                self._keyCallback(action_id, oldVal, self._text)

            self.updateLabel()

            return True
        oldVal = self.getText()

        if 61793 <= action_id <= 61818:  # Lowercase
            self.processChar(self.CHARS_LOWER[action_id - 61793])
        elif 61761 <= action_id <= 61786:  # Uppercase
            self.processChar(self.CHARS_UPPER[action_id - 61761])
        elif 61744 <= action_id <= 61753:
            self.processChar(self.CHARS_NUMBERS[action_id - 61744])
        elif action_id == 61728:  # Space
            self.processChar(' ')
        elif action_id == 61448:
            self.delete()
        else:
            return False

        if self._keyCallback:
            self._keyCallback(action_id, oldVal, self.getText())

        return True

    def processOffControlAction(self, action_id):
        oldVal = self.getText() if self._compatibleMode else self._text
        if 61505 <= action_id <= 61530:  # Lowercase
            self.processChar(self.CHARS_LOWER[action_id - 61505])
        elif 192577 <= action_id <= 192602:  # Uppercase
            self.processChar(self.CHARS_UPPER[action_id - 192577])
        elif 61488 <= action_id <= 61497:
            self.processChar(self.CHARS_NUMBERS[action_id - 61488])
        elif 61552 <= action_id <= 61561:
            self.processChar(self.CHARS_NUMBERS[action_id - 61552])
        elif action_id == 61472:  # Space
            self.processChar(' ')
        else:
            return False

        if self._keyCallback:
            self._keyCallback(action_id, oldVal, self.getText())

        return True

    def _setText(self, text):
        self._text = text

        if not self._compatibleMode:
            self._win.getControl(self.controlID).setText(text)
        self.updateLabel()

    def _getText(self):
        if not self._compatibleMode and self._win.getFocusId() == self.controlID:
            return self._win.getControl(self.controlID).getText()
        else:
            return self._text

    def updateLabel(self):
        self._labelControl.setLabel(self._getText() + self.CURSOR)

    def processChar(self, char):
        self._setText(self.getText() + char)

    def setText(self, text):
        self._setText(text)

    def getText(self):
        return self._getText()

    def append(self, text):
        self._setText(self.getText() + text)

    def delete(self):
        self._setText(self.getText()[:-1])


class PropertyTimer(object):
    def __init__(self, window_id, timeout, property_, value='', init_value='1', addon_id=None, callback=None):
        self._winID = window_id
        self._timeout = timeout
        self._property = property_
        self._value = value
        self._initValue = init_value
        self._endTime = 0
        self._thread = None
        self._addonID = addon_id
        self._closeWin = None
        self._closed = False
        self._callback = callback

    def _onTimeout(self):
        self._endTime = 0
        xbmcgui.Window(self._winID).setProperty(self._property, self._value)
        if self._addonID:
            xbmcgui.Window(10000).setProperty('{0}.{1}'.format(self._addonID, self._property), self._value)
        if self._closeWin:
            self._closeWin.doClose()
        if self._callback:
            self._callback()

    def _wait(self):
        while not MONITOR.abortRequested() and time.time() < self._endTime:
            xbmc.sleep(100)
        if MONITOR.abortRequested():
            return
        if self._endTime == 0:
            return
        self._onTimeout()

    def _stopped(self):
        return not self._thread or not self._thread.is_alive()

    def _reset(self):
        self._endTime = time.time() + self._timeout

    def _start(self):
        self.init(self._initValue)
        self._thread = threading.Thread(target=self._wait)
        self._thread.start()

    def stop(self, trigger=False):
        self._endTime = trigger and 1 or 0
        if not self._stopped():
            self._thread.join()

    def close(self):
        self._closed = True
        self.stop()

    def init(self, val):
        if val is False:
            return
        elif val is None:
            val = self._initValue

        xbmcgui.Window(self._winID).setProperty(self._property, val)
        if self._addonID:
            xbmcgui.Window(10000).setProperty('{0}.{1}'.format(self._addonID, self._property), val)

    def reset(self, close_win=None, init=None):
        self.init(init)

        if self._closed:
            return

        if not self._timeout:
            return

        self._closeWin = close_win
        self._reset()

        if self._stopped:
            self._start()


class WindowProperty(object):
    __slots__ = ("win", "prop", "val", "end", "old")

    def __init__(self, win, prop, val='1', end=''):
        self.win = win
        self.prop = prop
        self.val = val
        self.end = end
        self.old = self.win.getProperty(self.prop)

    def __enter__(self):
        self.win.setProperty(self.prop, self.val)
        return self

    def __exit__(self, exc_type, exc_value, traceback_):
        self.win.setProperty(self.prop, self.end or self.old)


class GlobalProperty(object):
    __slots__ = ("prop", "val", "end", "old")

    def __init__(self, prop, val='1', end=''):
        self.prop = prop
        self.val = val
        self.end = end
        self.old = xbmc.getInfoLabel('Window(10000).Property({0}.{1})'.format(ADDON_ID, prop))

    def __enter__(self):
        xbmcgui.Window(10000).setProperty('{0}.{1}'.format(ADDON_ID, self.prop), self.val)
        return self

    def __exit__(self, exc_type, exc_value, traceback_):
        xbmcgui.Window(10000).setProperty('{0}.{1}'.format(ADDON_ID, self.prop), self.end or self.old)


def waitForVisibility(control, amount=5):
    tries = 0
    while not xbmc.getCondVisibility('Control.IsVisible({0})'.format(control)) and tries < MONITOR.waitAmount(amount):
        MONITOR.waitFor()
        tries += 1


class SettleTimer:
    """Run a piece of work once focus has stopped moving.

    TV navigation arrives as a burst: a viewer holding Right crosses eight
    cards in a second, and anything the focus handler does synchronously --
    a full-screen texture swap, a library fetch -- is paid eight times, on
    the UI thread, while the frames it blocks are the ones that make the
    scroll feel smooth. Measured on the CoreELEC box, those bursts are what
    drop the frame rate to 1-4fps mid-row; the steady state is fine.

    TV-DESIGN 7.9.6 states the contract for the ambient wash -- roughly
    180ms of stillness, so that running along a row cannot queue one
    full-screen blur per card crossed -- and the server carries
    `layout.focusedBackdropDelayMs`
    for it. This generalises that to any focus-driven work.

    One worker per owner, parked on an Event: schedule() replaces whatever
    was pending, so only the LAST focus position does any work. The thread
    is a daemon and re-checks `alive` after waking, so a window that closes
    mid-delay drops the callback rather than touching a dead control.
    """

    __slots__ = ("_delay", "_wake", "_stop", "_pending", "_thread", "_lock", "_name")

    def __init__(self, delay_ms: int, name: str = "tofa-settle"):
        self._delay = max(0, delay_ms) / 1000.0
        self._name = name
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending = None
        self._thread = None

    @property
    def delay_ms(self) -> int:
        return int(self._delay * 1000)

    def set_delay(self, delay_ms: int):
        """Adopt the account's own delay once preferences have loaded."""
        self._delay = max(0, delay_ms) / 1000.0

    def schedule(self, fn):
        """Run `fn` when nothing else is scheduled for `delay_ms`."""
        if self._delay <= 0:
            fn()
            return
        with self._lock:
            self._pending = fn
        self._ensure_thread()
        self._wake.set()

    def cancel(self):
        with self._lock:
            self._pending = None

    def stop(self):
        self._stop.set()
        self.cancel()
        self._wake.set()

    def _ensure_thread(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self._name)
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            # No work pending: sleep until schedule() or stop() pokes us.
            if not self._wake.wait(30):
                continue
            self._wake.clear()
            # Drain the burst: every new schedule() re-sets the event, so
            # keep restarting the delay until one full quiet period passes.
            while self._wake.wait(self._delay):
                self._wake.clear()
                if self._stop.is_set():
                    return
            with self._lock:
                fn, self._pending = self._pending, None
            if fn is None or self._stop.is_set():
                continue
            try:
                fn()
            except Exception:
                # A settled callback runs off the UI thread; letting it
                # raise would kill the worker and silently stop every
                # later update.
                import traceback
                xbmc.log("tofa: settle callback failed\n" + traceback.format_exc(),
                         xbmc.LOGWARNING)
