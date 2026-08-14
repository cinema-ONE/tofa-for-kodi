"""The PIN pad must never be a room with no door.

The incident (box, 2026-08-10): a ~4h profile token expired, so the add-on
launched straight onto the PIN pad for the locked profile. There was no way
out. Back cancelled the dialog and closed the add-on, "Back to profiles" was
labelled "Cancel" and did the same, and the picker was never reachable -- so
the household could not switch to one of their three UNLOCKED profiles
without knowing the locked one's PIN. Anyone without that PIN was simply
locked out of the app.

TV-DESIGN 9.2 puts the two halves in ONE screen, crossfading between picker
and keypad rather than pushing a second screen. A state you cannot leave is
not a state.

The cause was that the re-lock path handed the dialog a list of exactly ONE
profile, which made a picker behind the keypad pointless, which made Back
mean "leave". Fixed by handing it the whole household and keying the way out
on the profile COUNT instead of on how the dialog happened to open.

Run:  python3 test_profile_pin_backout.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import profile_select

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Profile:
    def __init__(self, pid, name, locked=False):
        self.id = pid
        self.name = name
        self.is_locked = locked
        self.is_kids = False
        self.avatar_ref = None


LOCKED = Profile("p1", "cinemaONE", locked=True)
KID = Profile("p2", "The Kid")
CLAUDE = Profile("p3", "Claude Code")
GUEST = Profile("p4", "Guest")
HOUSEHOLD = [LOCKED, KID, CLAUDE, GUEST]


class Dialog:
    """Just the state ProfileDialog's own way-out logic reads.

    Bound rather than constructed: ProfileDialog.__init__ goes through
    kodigui.BaseDialog and Kodi's window machinery, and none of that is what
    is under test here.
    """

    def __init__(self, profiles, current_id=""):
        self._profiles = profiles
        self._current_id = current_id

    _alone = profile_select.ProfileDialog._alone
    _pin_target = profile_select.ProfileDialog._pin_target


# --------------------------------------------------------------------------
# 1. Is there a way out at all?
# --------------------------------------------------------------------------

check("THE LOCKOUT: a locked profile in a real household has a way back",
      not Dialog(HOUSEHOLD, "p1")._alone())

check("a one-profile household genuinely has nowhere to go",
      Dialog([LOCKED], "p1")._alone())

# The old code keyed this on start_in_pin, so opening on the keypad always
# meant "no way back" regardless of how many profiles existed. That is the
# exact bug; the count is the honest test.
check("the way out does not depend on how the dialog opened",
      Dialog(HOUSEHOLD, "p1")._alone() is Dialog(HOUSEHOLD, "")._alone())

check("an empty list is treated as alone, not crashed on",
      Dialog([], "")._alone())


# --------------------------------------------------------------------------
# 2. The keypad opens on the RIGHT profile
# --------------------------------------------------------------------------
# Now that the whole household is passed, profiles[0] is whoever happens to
# be first -- not whoever is being re-verified.

check("the keypad opens on the profile being re-verified, not tile one",
      Dialog(HOUSEHOLD, "p1")._pin_target() is LOCKED)

reordered = [KID, CLAUDE, LOCKED, GUEST]
check("...even when that profile is not first in the list",
      Dialog(reordered, "p1")._pin_target() is LOCKED)

check("an unknown stored id falls back to the first tile rather than raising",
      Dialog(HOUSEHOLD, "gone")._pin_target() is LOCKED)


# --------------------------------------------------------------------------
# 3. ensure_profile_selected routes the re-lock case correctly
# --------------------------------------------------------------------------
# The trap this guards: backing out to the picker and choosing an UNLOCKED
# profile has to PERSIST that choice. _run_picker is the only place that
# happens, so the re-lock branch must go through it -- opening ProfileDialog
# by hand (as it used to) would leave the new choice unsaved and the next
# launch would re-read the old profile_id and ask for the PIN again, forever.

CALLS = []


class Tok:
    def __init__(self, profile_id=None, profile_token=None, expires=None):
        self.profile_id = profile_id
        self.profile_token = profile_token
        self.profile_token_expires_at = expires
        self.server = "http://server"
        # The real auth.Tokens always carries this; the stub did not, and
        # list_profiles gained a `fallback=tok.server_fallback` argument.
        self.server_fallback = None
        self.access_token = "bearer"
        self.device_id = "dev"


def fake_picker(session, tok, items, *, start_in_pin=False, current_id=""):
    CALLS.append({"items": items, "start_in_pin": start_in_pin,
                  "current_id": current_id})
    return items[0]


SAVED = []
profile_select._run_picker = fake_picker
profile_select.profiles_api.list_profiles = lambda *a, **k: HOUSEHOLD
profile_select.auth.save_profile_selection = lambda *a: SAVED.append(a)
profile_select.auth.load = lambda: Tok("p1")

# An expired token on a profile that still exists and is locked.
CALLS.clear()
profile_select.ensure_profile_selected(None, Tok("p1", "dead", 0))
check("the re-lock case goes through _run_picker (so a new choice is saved)",
      len(CALLS) == 1, str(CALLS))
check("THE FIX: it is handed the whole household, not just the locked one",
      CALLS and CALLS[0]["items"] == HOUSEHOLD,
      str(CALLS[0]["items"] if CALLS else None))
check("it still opens straight on the keypad -- one PIN, no picker to walk",
      CALLS and CALLS[0]["start_in_pin"] is True)
check("and it names which profile to unlock",
      CALLS and CALLS[0]["current_id"] == "p1")

# A stored profile that has been deleted server-side: there is nothing to
# unlock, so a PIN pad would be a prompt for a profile that no longer exists.
# The old code fell back to items[0] and put one up anyway.
CALLS.clear()
SAVED.clear()
profile_select.ensure_profile_selected(None, Tok("vanished", "dead", 0))
check("a deleted stored profile shows the plain picker, not a stray PIN pad",
      CALLS and CALLS[0]["start_in_pin"] is False, str(CALLS))

# An unlocked profile never needs the dialog at all -- unchanged fast path.
CALLS.clear()
SAVED.clear()
profile_select.ensure_profile_selected(None, Tok("p3", "dead", 0))
check("an unlocked stored profile still resolves with no dialog",
      not CALLS and SAVED == [("p3", None, None)], f"{CALLS} {SAVED}")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
