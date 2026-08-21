"""A Detail page that fails to load must SAY so, not draw an empty hero.

Reported from the cinema box 2026-08-21: after a break, opening House of the
Dragon gave a page with no backdrop, no logo and an empty Play pill. The
media_detail call had failed (a stale pooled connection timing out -- see
test_stale_pool_reset.py) and the handler set `self.media = {}`, packed the
action row and returned, which draws the hero scaffold with nothing in it.

Two things are checked here: that the failure puts page 1 into 9.7's error
state, and that the sentence it shows is true of the failure that happened.
A transport failure is worth telling the viewer to check their connection;
an ANSWER of 404 is not, and sending them to look at a connection that is
working would be worse than saying nothing.

Run:  python3 test_detail_load_error.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http  # noqa: E402
from resources.lib.windows.detail import DetailWindow  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeDetail:
    """The error-state half of the window, borrowed whole."""
    _load_error_copy = DetailWindow._load_error_copy
    _set_load_error = DetailWindow._set_load_error
    _clear_load_error = DetailWindow._clear_load_error
    _page1_focus_id = DetailWindow._page1_focus_id
    PILL_RETRY = DetailWindow.PILL_RETRY
    PILL_PRIMARY = DetailWindow.PILL_PRIMARY
    PILL_WATCHLIST = DetailWindow.PILL_WATCHLIST
    PILL_CANCEL_REQUEST = DetailWindow.PILL_CANCEL_REQUEST

    def __init__(self):
        self.props = {}
        self.focused = None

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, "")

    def setFocusId(self, control_id):
        self.focused = control_id

    def _primary_is_actionable(self):
        return True


def main():
    # --- the state itself ---------------------------------------------------
    w = FakeDetail()
    w._set_load_error("Couldn't load this title", "We couldn't reach your server.")
    check("a failed load puts page 1 into the error state",
          w.getProperty("detail_state") == "error", w.getProperty("detail_state"))
    check("...and the card carries the title and the message",
          w.getProperty("detail_error_title") and w.getProperty("detail_error_message"))
    check("...and focus moves to Retry, off the pills the template just hid",
          w.focused == DetailWindow.PILL_RETRY, str(w.focused))
    check("...so the page's resting focus is Retry too, ahead of the primary",
          w._page1_focus_id() == DetailWindow.PILL_RETRY)

    w._clear_load_error()
    check("clearing it puts the page back",
          w.getProperty("detail_state") == "")
    check("...and focus goes back to the primary pill",
          w._page1_focus_id() == DetailWindow.PILL_PRIMARY)

    # --- the words have to say what happened --------------------------------
    #
    # The whole reason this screen got a card is that a wrong explanation
    # sent a real investigation at the profile PIN for the best part of an
    # hour. A card that guesses wrong does that to the viewer, who has no
    # log to correct it with.
    #
    # The TITLE is checked as carefully as the message: it is the biggest
    # text on the screen and the first thing read, and a constant there
    # ("Couldn't load this title" on every branch) tells the viewer nothing
    # the blank page had not already told them.
    # A TIMEOUT IS ITS OWN CASE. The server answered -- we gave up first --
    # so the connection has just proved it works. Traced end to end on
    # 2026-08-21: the server was still executing the query 99ms after the
    # client hung up (vault issue #107). This branch used to be lumped in
    # with "reach" and sent the viewer to check a working network.
    title, message = DetailWindow._load_error_copy(
        http.ApiError(0, "timeout", "timed out"))
    check("a timeout does NOT blame the connection",
          "connection" not in (title + message).lower(), title + " / " + message)
    check("...the headline says the SERVER was slow",
          "took too long" in title.lower(), title)
    check("...and Retry is the right thing to offer, so it says so",
          "try again" in message.lower(), message)

    reach = [
        http.ApiError(0, "connection_error", "refused"),
        http.ApiError(503, "server_relay_not_connected", ""),
        http.ApiError(502, "bad_gateway", ""),
        None,                                              # no client at all
    ]
    for exc in reach:
        title, message = DetailWindow._load_error_copy(exc)
        label = exc.error if exc else "no client"
        check("nothing answered: the headline names REACH (%s)" % label,
              "reach" in title.lower(), title)
        check("...and the advice is to check the connection (%s)" % label,
              "connection" in message.lower(), message)

    # A REFUSED profile is the case this screen must not get wrong: the
    # server answered, so the connection is fine, and "check the connection"
    # would send the viewer to look at the one thing that is working.
    for status, label in ((403, "a locked profile"), (401, "an expired credential")):
        title, message = DetailWindow._load_error_copy(
            http.ApiError(status, "profile_locked", ""))
        check("%s does not blame the connection" % label,
              "connection" not in (title + message).lower(), title + " / " + message)
        check("...the headline names the profile (%s)" % label,
              "profile" in title.lower(), title)
        # Retry reuses the credential the server just refused, so pointing at
        # it would be pointing at the one action that cannot help.
        check("...and the advice is one Retry cannot carry out (%s)" % label,
              "switch profile" in message.lower(), message)

    title, message = DetailWindow._load_error_copy(
        http.ApiError(404, "not_found", "Media not found"))
    check("a 404 does NOT blame the connection, which is working",
          "connection" not in (title + message).lower(), title + " / " + message)
    check("...the headline says the title is not there",
          "isn't on your server" in title, title)
    check("...and the advice explains why it might not be",
          "removed from your library" in message, message)

    title, message = DetailWindow._load_error_copy(
        http.ApiError(500, "internal_error", ""))
    check("an unexplained answer says so without guessing why",
          "couldn't answer" in title.lower()
          and "connection" not in (title + message).lower(),
          title + " / " + message)

    # Every branch has to say two DIFFERENT things: what happened, and what
    # to do next. A branch that repeats itself across the two lines leaves
    # the viewer exactly where the blank page did.
    seen_titles = set()
    for exc in (None,
                http.ApiError(0, "timeout", ""),
                http.ApiError(403, "profile_locked", ""),
                http.ApiError(404, "not_found", ""),
                http.ApiError(500, "internal_error", "")):
        label = str(exc.status) if exc else "none"
        title, message = DetailWindow._load_error_copy(exc)
        check("the title is a phrase, not a sentence (status %s)" % label,
              not title.endswith("."), title)
        check("the message is punctuated prose (status %s)" % label,
              message.endswith("."), message)
        check("the message advises rather than repeating the title "
              "(status %s)" % label, message.lower() != title.lower())
        seen_titles.add(title)
    check("each kind of failure gets its OWN headline, not one shared one",
          len(seen_titles) == 5, str(sorted(seen_titles)))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("detail load error: the page says what went wrong, and says it "
          "truthfully (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
