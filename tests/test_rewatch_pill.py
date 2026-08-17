"""When the Detail action row offers Rewatch, and when it must not.

Rewatch means "start from the beginning". That is a DIFFERENT action from
the primary pill only while the primary says Resume. On a finished title the
primary falls back to Play -- which already starts from the beginning -- so
a Rewatch beside it is the same action under a second name, and the viewer
has to choose between two identical buttons. Reported from the box after
watching a film to the end.

The rule is therefore one condition, shared by the label and the pill:
the row shows Resume + Rewatch, or it shows Play alone.

Run:  python3 test_rewatch_pill.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Row:
    """Just enough of DetailWindow for the one method under test.

    The real thing is a WindowXML and cannot be built without Kodi, but this
    method only reads a duration and writes a label and two properties -- so
    the method itself is run, unbound, rather than a copy of its rule."""

    def __init__(self, duration_ms=90 * 60 * 1000):
        self.play_duration_ms = duration_ms
        self.resume_ms = 0
        self.play_completed = False
        self.props = {}
        self.label = None
        # A film: no episode number rides along with the verb.
        self._next_up_season = None
        self._next_up_episode_number = None

    _primary_label = DetailWindow._primary_label

    def _set_primary_label(self, label, glyph=None):
        self.label = label

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, "")


def apply(position_ms, completed, duration_ms=90 * 60 * 1000):
    row = Row(duration_ms)
    DetailWindow._apply_primary_progress(row, position_ms, completed)
    return row


# ---- the reported case ----------------------------------------------------
# Watched to the end, then back to Detail. Play is right; Rewatch is not.
finished = apply(0, True)
check("finished: the primary says Play", finished.label == "Play", str(finished.label))
check("finished: NO Rewatch pill beside it",
      finished.props["show_rewatch"] == "", repr(finished.props["show_rewatch"]))
check("finished: no progress sliver under Play",
      finished.props["primary_progress_fill"] == "")
check("finished: the completed flag is kept for the options menu",
      finished.play_completed is True)

# A server that keeps the position on a completed title lands here too, and
# it is the same screen to the viewer: the primary still says Play.
finished_with_position = apply(88 * 60 * 1000, True)
check("finished WITH a leftover position: still Play",
      finished_with_position.label == "Play", str(finished_with_position.label))
check("finished WITH a leftover position: still no Rewatch",
      finished_with_position.props["show_rewatch"] == "")
check("finished: nothing to resume to",
      finished_with_position.resume_ms == 0)

# ---- mid-watch: Rewatch is the whole point --------------------------------
# Confirmed against the real Apple TV app, which shows Resume and Rewatch
# side by side on a title only ~2% in.
early = apply(2 * 60 * 1000, False)
check("2% in: the primary says Resume", early.label == "Resume", str(early.label))
check("2% in: Rewatch IS offered", early.props["show_rewatch"] == "1")
check("2% in: the resume point is kept", early.resume_ms == 2 * 60 * 1000)
check("2% in: not marked completed", early.play_completed is False)

half = apply(45 * 60 * 1000, False)
check("halfway: Resume and Rewatch together",
      half.label == "Resume" and half.props["show_rewatch"] == "1")
check("halfway: the pill carries a progress sliver",
      half.props["primary_progress_fill"] != "")

# ---- untouched ------------------------------------------------------------
fresh = apply(0, False)
check("never played: the primary says Play", fresh.label == "Play", str(fresh.label))
check("never played: no Rewatch", fresh.props["show_rewatch"] == "")

# ---- the invariant behind all of the above --------------------------------
# One condition drives both, so these two can never disagree: Rewatch is
# shown exactly when the primary is NOT a plain Play.
for pos, done_ in ((0, False), (0, True), (1000, False), (1000, True),
                   (45 * 60 * 1000, False), (90 * 60 * 1000, True)):
    row = apply(pos, done_)
    resume = row.label.startswith("Resume")
    shown = bool(row.props["show_rewatch"])
    check(f"pos={pos} completed={done_}: Rewatch iff Resume",
          resume == shown, f"label={row.label} rewatch={shown}")

# ---- an episode carries its number into the verb --------------------------
row = Row()
row._next_up_season, row._next_up_episode_number = 1, 3
DetailWindow._apply_primary_progress(row, 5 * 60 * 1000, False)
check("a show mid-episode: 'Resume S1 E3' plus Rewatch",
      row.label == "Resume S1 E3" and row.props["show_rewatch"] == "1",
      str(row.label))
row = Row()
row._next_up_season, row._next_up_episode_number = 1, 3
DetailWindow._apply_primary_progress(row, 0, True)
check("a finished episode: 'Play S1 E3' alone",
      row.label == "Play S1 E3" and row.props["show_rewatch"] == "",
      str(row.label))


failed = [n for n, ok in RESULTS if not ok]
print()
print(f"rewatch pill: Resume and Rewatch, or Play alone ({len(RESULTS)} checks)")
if failed:
    raise SystemExit(1)
