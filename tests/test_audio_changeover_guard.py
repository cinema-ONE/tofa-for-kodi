"""Play Next must not inherit the previous episode's audio track.

Reported 2026-08-19 from the cinema box (add-on issue #67): pressing the Up
Next rail's play button at the end of Murder, She Wrote S2 E18 started S2 E19
in GERMAN. E19's container defaults to German; English is the second track.

The client had resolved English correctly. What lost it was `_switch_audio`'s
shortcut -- it skips `setAudioStream()` when the wanted slot is already
active, and on the changeover path `_current_stream()` was still describing
the OUTGOING file. The log ordering is the proof:

    15:45:18.324  advancing without stop (keeping display mode)
    15:45:20.185  audio already on slot 1; not switching
    15:45:20.198  monitor: adopted session a9b516b8-...   <- 13ms LATER

against a normal start, where the same check runs 3ms AFTER adoption and is
right. `_showing_current_item()` is the fix: the shortcut is only trusted
when Kodi says it is playing the file we last handed it.

Exercises the REAL methods bound to a stand-in `self`, so the test cannot
drift from the implementation. Run:  python3 test_audio_changeover_guard.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeUIPlayer:
    def __init__(self):
        self.audio_switches = []
        self.subtitle_switches = []

    def setAudioStream(self, slot):
        self.audio_switches.append(slot)

    def setSubtitleStream(self, slot):
        self.subtitle_switches.append(slot)


class FakePlayer:
    """Only what the two guards touch."""

    def __init__(self, current_slot, showing_current, enabled=True):
        self.ui_player = FakeUIPlayer()
        self._current_slot = current_slot
        self._showing = showing_current
        self._enabled = enabled
        self._identity_checks = 0

    def _current_stream(self, subtitles):
        return self._current_slot, self._enabled

    def _showing_current_item(self):
        self._identity_checks += 1
        return self._showing


def switch_audio(current_slot, wanted, showing_current):
    p = FakePlayer(current_slot, showing_current)
    changed = PlayerWindow._switch_audio(p, wanted)
    return changed, p.ui_player.audio_switches, p._identity_checks


def switch_subtitle(current_slot, wanted, showing_current, enabled=True):
    p = FakePlayer(current_slot, showing_current, enabled)
    changed = PlayerWindow._switch_subtitle(p, wanted)
    return changed, p.ui_player.subtitle_switches


# --- the incident ---------------------------------------------------------
# Kodi says slot 1 (stale -- that was E18). We want slot 1 for E19. Without
# the identity check this skips, and E19 plays its own default, slot 0.
changed, switches, _ = switch_audio(current_slot=1, wanted=1, showing_current=False)
check("mid-changeover: a stale 'already on that slot' does NOT skip the switch",
      changed and switches == [1], "switches=%r" % switches)

# --- the shortcut still works when the read is trustworthy ----------------
changed, switches, _ = switch_audio(current_slot=1, wanted=1, showing_current=True)
check("settled: the shortcut still skips a pointless renderer change",
      (not changed) and switches == [], "switches=%r" % switches)

# --- a genuine change is never blocked ------------------------------------
for showing in (True, False):
    changed, switches, _ = switch_audio(current_slot=0, wanted=1, showing_current=showing)
    check("a real switch happens regardless of the identity check (showing=%s)" % showing,
          changed and switches == [1], "switches=%r" % switches)

# --- the identity check must not be paid when it cannot matter ------------
_, _, checks = switch_audio(current_slot=0, wanted=1, showing_current=True)
check("no identity round trip when a switch is needed anyway", checks == 0,
      "made %d identity checks" % checks)
_, _, checks = switch_audio(current_slot=1, wanted=1, showing_current=True)
check("identity checked only when the shortcut would fire", checks == 1,
      "made %d identity checks" % checks)

# --- subtitles carry the identical defect, so the identical fix -----------
changed, switches = switch_subtitle(current_slot=2, wanted=2, showing_current=False)
check("mid-changeover: stale subtitle slot does NOT skip the switch",
      changed and switches == [2], "switches=%r" % switches)
changed, switches = switch_subtitle(current_slot=2, wanted=2, showing_current=True)
check("settled: subtitle shortcut still skips",
      (not changed) and switches == [], "switches=%r" % switches)
# Off but on the right index still has to be turned on, identity or not.
changed, switches = switch_subtitle(current_slot=2, wanted=2, showing_current=True,
                                    enabled=False)
check("a disabled subtitle track is switched on even when the slot matches",
      changed and switches == [2], "switches=%r" % switches)

print("")
failed = [n for n, ok in RESULTS if not ok]
print("audio changeover guard: a stale read cannot cost the chosen track (%d checks)"
      % len(RESULTS))
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
