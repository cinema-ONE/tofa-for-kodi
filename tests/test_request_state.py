"""The out-of-library detail pill, over every state the server can report.

Only two of these states can be produced on demand against a real server --
requesting a title and cancelling it -- and one of the others (`downloading`)
takes a real download to reach, so the rest are covered here instead of by
hand.  Run:  python3 test_request_state.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeWindow:
    """Only what _render_request_state touches."""
    REQUEST_STATE_LABELS = DetailWindow.REQUEST_STATE_LABELS
    # staticmethod() again on the way in: reading it off the class unwraps it,
    # and a bare function on a class binds itself to the instance.
    _downloading_label = staticmethod(DetailWindow._downloading_label)

    def __init__(self, media_type="movie"):
        self.discovery_media_type = media_type
        self.props = {}
        self.label = None
        self.glyph = None

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, "")

    def _set_primary_label(self, label, glyph=None):
        self.label = label
        self.glyph = glyph

    # under test
    def render(self, disc):
        DetailWindow._render_request_state(self, disc)
        return self

    @property
    def actionable(self):
        self.is_playable = False
        return DetailWindow._primary_is_actionable(self)

    @property
    def cancel_offered(self):
        return bool(self.props.get("show_cancel_request"))


MOVIE = {"integration_available": True}


# 1. No integration for this media type: nothing is requestable, whatever
#    else the payload says.
w = FakeWindow("tv").render({"integration_available": False,
                             "seasons": [{"season_number": 1}]})
check("no integration says so and offers nothing", w.label == "Not in library" and not w.actionable)

# 2. Nothing requested yet.
w = FakeWindow().render(dict(MOVIE))
check("a clean movie offers Request", w.label == "Request" and w.actionable)
w = FakeWindow("tv").render(dict(MOVIE, seasons=[{"season_number": 1}]))
check("a show with seasons offers Request", w.label == "Request" and w.actionable)
w = FakeWindow("tv").render(dict(MOVIE))
check("a show with no season list cannot be requested", w.label == "Not in library" and not w.actionable)

# 3. The live request states: report, do nothing, offer the withdrawal.
for status, label in (("pending_approval", "Pending approval"),
                      ("requested", "Requested"),
                      ("retrying", "Retrying")):
    w = FakeWindow().render(dict(MOVIE, request_status=status, request_id="r1"))
    check(f"{status} reads {label!r}, inert, cancellable",
          w.label == label and not w.actionable and w.cancel_offered,
          f"{w.label!r} actionable={w.actionable} cancel={w.cancel_offered}")

w = FakeWindow().render(dict(MOVIE, request_status="downloading", request_id="r1"))
check("downloading with no progress yet omits the percentage", w.label == "Downloading")
w = FakeWindow().render(dict(MOVIE, request_status="downloading", request_id="r1",
                             request_download={"progress": 0.423}))
check("downloading reports the percentage", w.label == "Downloading 42%", repr(w.label))

# 4. Failure: retry where the server still allows one, plain statement where not.
w = FakeWindow().render(dict(MOVIE, request_status="failed", request_id="r1", can_retry=True))
check("a retryable failure offers the retry", w.label == "Retry request" and w.actionable)
w = FakeWindow().render(dict(MOVIE, request_status="failed", request_id="r1", can_retry=False))
check("a spent failure states it and does nothing", w.label == "Request failed" and not w.actionable)
check("a failed request is still cancellable", w.cancel_offered)

# 5. A denial is about one ask, so asking again is the action.
w = FakeWindow().render(dict(MOVIE, request_status="denied", request_id="r1"))
check("denied offers another ask", w.label == "Request again" and w.actionable)
check("denied offers no cancel", not w.cancel_offered)

# 6. *arr, without a request of ours. THE REGRESSION: cancelling leaves the
#    title tracked for up to ~30s (and for good if it was cancelled before it
#    resolved to an instance), so tracked-with-no-file must stay requestable.
w = FakeWindow().render(dict(MOVIE, arr_status={"tracked": True, "has_file": False,
                                                "monitored": True}))
check("tracked but no file is still requestable", w.label == "Request" and w.actionable)
w = FakeWindow().render(dict(MOVIE, arr_status={"tracked": True, "has_file": True,
                                                "monitored": True}))
check("tracked WITH the file is coming to the library",
      w.label == "Coming to library" and not w.actionable)
check("someone else's acquisition offers no cancel", not w.cancel_offered)
w = FakeWindow().render(dict(MOVIE, request_status="available", request_id="r1"))
check("an available request is coming to the library too",
      w.label == "Coming to library" and not w.actionable)

# 7. Inert states never carry an icon -- a glyph on a pill that does nothing
#    reads as a broken button.
for disc in (dict(MOVIE, request_status="requested", request_id="r1"),
             dict(MOVIE, request_status="failed", request_id="r1"),
             dict(MOVIE, integration_available=False),
             dict(MOVIE, arr_status={"tracked": True, "has_file": True})):
    w = FakeWindow().render(disc)
    check(f"{w.label!r} carries no glyph", w.glyph == "")

# 8. Which seasons the picker must show as already asked for.
class SeasonWindow:
    def __init__(self, request_seasons):
        self.discovery_detail = {"request_seasons": request_seasons}
    def seasons(self):
        return DetailWindow._already_requested_seasons(self)

check("no request means nothing is pre-ticked", SeasonWindow(None).seasons() == set())
check("requested seasons come back",
      SeasonWindow([{"season_number": 1, "status": "requested"},
                    {"season_number": 2, "status": "downloading"}]).seasons() == {1, 2})
check("a denied or failed season stays askable",
      SeasonWindow([{"season_number": 1, "status": "denied"},
                    {"season_number": 2, "status": "failed"},
                    {"season_number": 3, "status": "available"}]).seasons() == {3})


# 9. The card badge: plus / clock / nothing (§16's three-platform contract).
from resources.lib.windows import cards


class FakeItem:
    def __init__(self):
        self.props = {}
    def setProperty(self, key, value):
        self.props[key] = value


def badge(item, in_library=False):
    mli = FakeItem()
    cards.apply_library_badge(mli, item, in_library=in_library)
    return mli.props


b = badge({}, in_library=True)
check("an owned title wears no badge at all",
      b["watchlist_glyph"] == "" and b["watchlisted"] == "1")
b = badge({})
check("out of library, not requested, is the plus",
      b["watchlist_glyph"] == cards.PLUS_GLYPH and not b["badge_requested"])
for status in sorted(cards.COMING_STATUSES):
    b = badge({"request_status": status})
    check(f"{status} wears the accent clock",
          b["watchlist_glyph"] == cards.CLOCK_GLYPH and b["badge_requested"] == "1")
for status in ("denied", "failed"):
    b = badge({"request_status": status})
    check(f"{status} goes back to the plus, not a clock",
          b["watchlist_glyph"] == cards.PLUS_GLYPH and not b["badge_requested"])
# The shelf field is noise ABOVE the in_library gate -- 543 of 1209 items on a
# live discovery page said "requested" purely because the *arr stack tracks
# every owned title. Below the gate it was exact.
b = badge({"request_status": "requested"}, in_library=True)
check("an owned title claiming 'requested' still wears nothing",
      b["watchlist_glyph"] == "" and not b["badge_requested"])


failed = [name for name, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
