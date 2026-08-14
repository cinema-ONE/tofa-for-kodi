"""The one remote route into 8.11's stats readout.

Kodi's JSON-RPC method list is compiled in, so an add-on cannot register a
method of its own; `JSONRPC.NotifyAll` is the only channel that carries an
arbitrary message to a running add-on. Measured on a live Kodi 2026-08-11:

    sent  {"sender":"plugin.video.tofa","message":"stats",
           "data":{"mode":"panel"}}
    got   sender='plugin.video.tofa'  method='Other.stats'
          data='{"mode":"panel"}'   <- a STRING, always

What is worth locking here is the PARSING, because the payload is whatever
the sender typed and a malformed one must not change what is on screen:
`data` arrives as a JSON string even when it was sent as an object, as
`'null'` when omitted, and as `'"pill"'` for a bare string.

Run:  python3 test_stats_notify.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player as P
from resources.lib.windows import playerstats

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


mode_of = P._stats_mode_from_notification

# --- the documented shape, exactly as Kodi delivers it -------------------
check("an object payload yields its mode",
      mode_of('{"mode":"panel"}') == playerstats.PANEL, repr(mode_of('{"mode":"panel"}')))
check("pill", mode_of('{"mode":"pill"}') == playerstats.PILL)
check("cycle is passed through as its own word",
      mode_of('{"mode":"cycle"}') == P.STATS_CYCLE)

# "off" is spelled "" internally, because it is also the window property's
# empty state -- translated at the boundary so the documented vocabulary can
# say "off" like a human. Same class as ASK being 0 in the stereo marker:
# the internal falsy value is a REAL state.
check("off maps to playerstats.OFF, not to None",
      mode_of('{"mode":"off"}') == playerstats.OFF
      and mode_of('{"mode":"off"}') is not None,
      repr(mode_of('{"mode":"off"}')))

# --- the shapes someone will inevitably send -----------------------------
check("a bare string works too", mode_of('"panel"') == playerstats.PANEL)
check("case and padding are forgiven", mode_of('{"mode":"  PANEL "}') == playerstats.PANEL)

# --- a bad payload must never change the screen --------------------------
for bad, why in (
        ('null', "omitted data arrives as the string 'null'"),
        ('', "empty"),
        (None, "no data at all"),
        ('{"mode":"wat"}', "unknown mode"),
        ('{"mode":123}', "mode is not a string"),
        ('{"nope":"panel"}', "no mode key"),
        ('not json at all', "unparseable"),
        ('[1,2,3]', "a list"),
        ('{"mode":null}', "explicit null mode"),
):
    check(f"ignored: {why}", mode_of(bad) is None, repr(mode_of(bad)))


# --- the receiver filters on BOTH sender and message ---------------------
# Every add-on hears every notification, so a bare message match would let
# another add-on's "stats" notification drive our overlay.
class FakeWindow:
    def __init__(self):
        self.requested = []
    def request_stats_mode(self, mode):
        self.requested.append(mode)

win = FakeWindow()
mon = P._StatsNotifyMonitor(win)
mon.onNotification(P.STATS_NOTIFY_SENDER, P.STATS_NOTIFY_METHOD, '{"mode":"panel"}')
check("a matching notification reaches the window",
      win.requested == [playerstats.PANEL], str(win.requested))

win.requested.clear()
mon.onNotification("someone.else", P.STATS_NOTIFY_METHOD, '{"mode":"pill"}')
check("another add-on's notification is ignored", win.requested == [], str(win.requested))
mon.onNotification(P.STATS_NOTIFY_SENDER, "Other.something", '{"mode":"pill"}')
check("a different message is ignored", win.requested == [], str(win.requested))
mon.onNotification(P.STATS_NOTIFY_SENDER, "stats", '{"mode":"pill"}')
check("the un-prefixed message is ignored (Kodi always sends Other.)",
      win.requested == [], str(win.requested))
mon.onNotification(P.STATS_NOTIFY_SENDER, P.STATS_NOTIFY_METHOD, 'garbage')
check("a bad payload reaches nothing", win.requested == [], str(win.requested))

# The window is held WEAKLY: a Monitor lives until Kodi drops it, and a
# strong reference would keep a closed player (its lists, its artwork) alive.
import gc
win2 = FakeWindow()
mon2 = P._StatsNotifyMonitor(win2)
del win2
gc.collect()
mon2.onNotification(P.STATS_NOTIFY_SENDER, P.STATS_NOTIFY_METHOD, '{"mode":"panel"}')
check("a collected window is not resurrected, and does not raise",
      mon2._window_ref() is None, "the monitor still holds it")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
