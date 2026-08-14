"""A locked profile's token dies of old age after ~4h. Nothing may read that
as "nothing has been watched".

The incident (box, 2026-08-09): the token expired 43 minutes into an episode
of Murder, She Wrote. Playback was unaffected -- the stream carries its own
token -- but every progress call 401'd from then on, and the Detail page
underneath came back from playback saying "Play S1 E1" on the show whose S1
E14 had just finished, with no tick on E14 and the grid selection dragged
back to E1. Three wrong statements, all of them one failed read.

Two properties are tested here, one per half of the fix:

  1. a client whose profile token has expired is not reused (so the PIN pad
     gets its chance), and
  2. a read that FAILS never turns into a fact -- progress.fetch_many with
     `required=True` raises rather than answering {}.

Run:  python3 test_expired_profile_token.py
"""
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, http, progress

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Tokens:
    """Just the fields api.client_for reads off auth.Tokens."""
    server = "http://server"
    access_token = "bearer"
    device_id = "dev"
    server_fallback = None
    profile_id = "p1"
    profile_token = None
    profile_token_expires_at = None


def client(**overrides):
    tok = Tokens()
    for k, v in overrides.items():
        setattr(tok, k, v)
    return api.client_for(None, tok)


HOUR = 3600.0

# --------------------------------------------------------------------------
# 1. Knowing the token is dead
# --------------------------------------------------------------------------

check("an unlocked profile never expires (no token to expire)",
      not client(profile_token=None, profile_token_expires_at=0).profile_token_expired())

check("a fresh ~4h token is good",
      not client(profile_token="t", profile_token_expires_at=time.time() + 4 * HOUR
                 ).profile_token_expired())

check("THE INCIDENT: a token that lapsed mid-episode is expired",
      client(profile_token="t", profile_token_expires_at=time.time() - 150
             ).profile_token_expired())

# The margin exists so a client isn't handed out to make a call it cannot
# finish -- the request goes out after the check, not during it.
check("a token with seconds left is already treated as expired",
      client(profile_token="t", profile_token_expires_at=time.time() + 5
             ).profile_token_expired())

# A token file written before this field existed carries no expiry at all.
# Treating "unknown" as "valid forever" is how the bug survived; it must
# fall the other way.
check("a token with no known expiry is not trusted",
      client(profile_token="t", profile_token_expires_at=None).profile_token_expired())

# client_for is the one constructor precisely so no call site can forget to
# pass the expiry through.
built = client(profile_token="t", profile_token_expires_at=1234.0)
check("client_for carries the expiry through",
      built.profile_token_expires_at == 1234.0 and built.profile_token == "t")


# --------------------------------------------------------------------------
# 2. A failed read is not an answer
# --------------------------------------------------------------------------

class Failing:
    """A server that 401s the way an expired profile token really did."""
    def media_progress_batch(self, file_ids):
        raise http.ApiError(401, "unauthorized",
                            "Unauthorized: Invalid or expired profile token")


class Answering:
    def __init__(self, items):
        self.items = items
    def media_progress_batch(self, file_ids):
        return {"items": [i for i in self.items if i["media_file_id"] in file_ids]}


FILES = ["f1", "f2", "f3"]

check("a failed read is still {} for a caller that can live with it",
      progress.fetch_many(Failing(), FILES) == {})

raised = False
try:
    progress.fetch_many(Failing(), FILES, required=True)
except http.ApiError:
    raised = True
check("required=True raises instead of answering {}", raised)

# The rule the incident tripped: with the map empty, "first not completed"
# is episode one -- a confident answer built out of a failed request.
candidates = [(1, n, {"episode_number": n}, {"id": "f%d" % n}) for n in (1, 2, 3)]
check("an empty map really does mean episode one (why it must not happen)",
      progress.next_up(candidates, {}, None)[1] == 1)

fresh = progress.fetch_many(
    Answering([{"media_file_id": "f1", "completed": True},
               {"media_file_id": "f2", "completed": True}]),
    FILES, required=True)
check("a real read is unchanged by required=",
      progress.next_up(candidates, fresh, None)[1] == 3, str(fresh))

# --------------------------------------------------------------------------
# 3. Asking for the PIN at a moment the viewer chose
# --------------------------------------------------------------------------
# A locked profile must re-enter its PIN every ~4h (no refresh endpoint), so
# the only thing the client controls is WHEN. Pressing Play declares how long
# the viewer will be busy; the gate takes that as the margin the token has to
# clear, which is what moves the prompt off the middle of a film.

from resources.lib.windows import profile_select  # noqa: E402

ASKED = []


def gate(token_left_s, margin_s):
    """ensure_profile_selected's fast-path test, in isolation -- the branch
    that decides between "no network call" and "put the PIN pad up"."""
    tok = Tokens()
    tok.profile_token = "t"
    tok.profile_token_expires_at = time.time() + token_left_s
    now = time.time()
    return not (tok.profile_id and (not tok.profile_token
                or (tok.profile_token_expires_at or 0) > now + margin_s))


FILM = 118 * 60          # a 118-minute film
EPISODE = 46 * 60

check("default margin: 40 minutes left is plenty for one API call",
      not gate(40 * 60, profile_select.MARGIN_S))
check("THE INTERRUPTION: 40 minutes left does not cover a 118-minute film",
      gate(40 * 60, FILM))
check("a token good past the credits asks for nothing",
      not gate(3 * 3600, FILM))
check("binge case: 30 minutes left does not cover the next episode",
      gate(30 * 60, EPISODE))
check("mid-TTL, one more episode fits",
      not gate(2 * 3600, EPISODE))

# An unlocked profile has no token, so no runtime can ever provoke a prompt.
check("renew_for_playback is a no-op for a runtime of zero",
      profile_select.renew_for_playback(0) is False)
check("renew_for_playback survives a junk runtime",
      profile_select.renew_for_playback(None) is False
      and profile_select.renew_for_playback("nonsense") is False)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
