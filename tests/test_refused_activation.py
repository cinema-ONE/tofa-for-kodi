"""A window Kodi refuses to activate opens once the modal dialog is gone.

Kodi refuses any window activation while a modal dialog is up. The launch
then waited forever for a window that never opened, stranding the splash.

Run:  python3 test_refused_activation.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
import xbmc
import xbmcgui
from resources.lib.windows import kodigui

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}"
          f"{('  -- ' + detail) if detail and not ok else ''}")


class Hang(Exception):
    pass


class FakeKodi:
    """The slice of Kodi's window manager a modal open touches."""

    SPLASH, WINDOW, NO_DIALOG, YESNO = 13001, 13002, 9999, 10100
    HORIZON_S = 600.0     # a clock past this means the open hung
    EXIT_AFTER_S = 1.0    # the viewer leaves this long after it opens

    def __init__(self, modals=(), refuse_always=False, abort_at=None,
                 close_at=None, dialog_on_show=None):
        self.now = 0.0
        self.current = self.SPLASH
        self.modals = list(modals)          # [(opens, closes)] in seconds
        self.refuse_always = refuse_always
        self.abort_at = abort_at
        self.close_at = close_at            # someone closes the window
        self.dialog_on_show = dialog_on_show or {}  # show n -> dialog secs
        self.shows = []                     # (time, activated)
        self.polls = 0
        self.touched = []                   # anything that could answer one
        self.window = None
        self.opened_at = None

    def modal_up(self):
        return any(a <= self.now < b for a, b in self.modals)

    def show(self, window):
        """xbmcgui.WindowXML.show: synchronous, refused under a modal."""
        self.window = window
        secs = self.dialog_on_show.get(len(self.shows) + 1)
        if secs:
            self.modals.append((self.now, self.now + secs))
        refused = self.refuse_always or self.modal_up()
        self.shows.append((self.now, not refused))
        if not refused:
            self.current, self.opened_at = self.WINDOW, self.now

    def wait(self, amount=0.1):
        """MONITOR.waitFor: advances the clock; True means Kodi is quitting."""
        self.now += amount
        if self.now > self.HORIZON_S:
            raise Hang(f"still waiting at {self.now:.0f}s")
        if self.close_at is not None and self.now >= self.close_at:
            self.window._closing = True
        if self.opened_at is not None and \
                self.now >= self.opened_at + self.EXIT_AFTER_S:
            self.window._closing = True
        return self.abort_at is not None and self.now >= self.abort_at

    def cond(self, condition):
        if condition == "System.HasActiveModalDialog":
            self.polls += 1
            return self.modal_up()
        self.touched.append(("getCondVisibility", condition))
        return False


class FakeMonitor:
    def __init__(self, kodi):
        self.kodi = kodi

    def waitFor(self, amount=0.1):
        return self.kodi.wait(amount)

    def waitAmount(self, amount, interval=0.1):
        return int(amount / interval) if interval else 0

    def abortRequested(self):
        return self.kodi.abort_at is not None and self.kodi.now >= self.kodi.abort_at


class Window(kodigui.ControlledWindow):
    closed = 0

    def onClosed(self):
        self.closed += 1


def run(**scenario):
    """Open a window modally against a FakeKodi; returns (kodi, window, hung)."""
    kodi = FakeKodi(**scenario)
    xbmcgui.WindowXML.show = lambda self: kodi.show(self)
    xbmcgui.getCurrentWindowId = lambda: kodi.current
    xbmcgui.getCurrentWindowDialogId = lambda: (
        kodi.YESNO if kodi.modal_up() else kodi.NO_DIALOG)
    xbmc.getCondVisibility = kodi.cond
    xbmc.executebuiltin = lambda *a, **k: kodi.touched.append(("builtin", a))
    xbmc.executeJSONRPC = lambda *a, **k: kodi.touched.append(("jsonrpc", a))
    kodigui.MONITOR = FakeMonitor(kodi)
    window = Window("script-test.xml", "", "Main", "1080i")
    try:
        window.modal()
    except Hang as exc:
        return kodi, window, str(exc)
    return kodi, window, ""


# No dialog: one show, and not one condition evaluated.
kodi, win, hung = run()
check("no dialog: opens on the first show", not hung and kodi.shows == [(0.0, True)],
      hung or repr(kodi.shows))
check("no dialog: costs nothing extra", kodi.polls == 0, f"{kodi.polls} polls")

# The reported case: a modal is up at hand-over and answered at 5s.
kodi, win, hung = run(modals=[(0.0, 5.0)])
check("refused under a modal: does not hang", not hung, hung)
check("...shows exactly twice (no retry storm)", len(kodi.shows) == 2, repr(kodi.shows))
check("...the first show was refused", kodi.shows and kodi.shows[0][1] is False)
retry = kodi.shows[-1] if kodi.shows else (0.0, False)
check("...the retry opens it", retry[1] is True and kodi.opened_at is not None)
check("...within one poll of the dialog closing",
      5.0 - 1e-6 <= retry[0] <= 5.0 + kodigui._REFUSED_POLL_S + 1e-6,
      f"retried at {retry[0]:.2f}s")
check("...never touches the dialog", kodi.touched == [], repr(kodi.touched))
check("...and the window closes normally afterwards", win.closed == 1)

# A dialog up for a minute still means two shows, not one per poll.
kodi, win, hung = run(modals=[(0.0, 60.0)])
check("a long dialog: still exactly two shows",
      not hung and len(kodi.shows) == 2 and kodi.shows[-1][1] is True,
      hung or repr(kodi.shows))

# A second dialog lands the moment the retry fires (CoreELEC queues two).
kodi, win, hung = run(modals=[(0.0, 3.0)], dialog_on_show={2: 3.0})
check("refused again by a second dialog: waits that one out too",
      not hung and [ok for _, ok in kodi.shows] == [False, False, True],
      hung or repr(kodi.shows))
check("...and opens once it closes", not hung and kodi.shows[-1][0] >= 6.0 - 1e-6,
      repr(kodi.shows))

# Kodi quits while the dialog is still up.
kodi, win, hung = run(modals=[(0.0, 1000.0)], abort_at=10.0)
check("Kodi quitting: gives up instead of hanging", not hung, hung)
check("...without showing again", len(kodi.shows) == 1, repr(kodi.shows))
check("...and still runs onClosed", win.closed == 1)

# The window is closed by something else while it waits.
kodi, win, hung = run(modals=[(0.0, 1000.0)], close_at=8.0)
check("closed while waiting: stops", not hung and len(kodi.shows) == 1,
      hung or repr(kodi.shows))

# Refused with no modal dialog to blame: bounded, then give up.
kodi, win, hung = run(refuse_always=True)
check("refused for no visible reason: gives up instead of hanging", not hung, hung)
check("...after a bounded number of retries",
      len(kodi.shows) == 1 + kodigui._UNEXPLAINED_RETRIES, repr(kodi.shows))
check("...and never touches anything", kodi.touched == [], repr(kodi.touched))

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
