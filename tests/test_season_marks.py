"""The season sidebar marks each row the way the Apple TV app does.

On 2026-09-21 the app's own update moved the "not in library" words OUT of
the season row. The row now ends in a mark where the episode count used to
be -- a tick for a finished season, "5 left" for one in progress, a circled
plus for one with nothing in the library, and a dot on the row you have
selected -- and the words live in the selected season's header instead,
along with a top-right line that reads "No episodes" or "Season complete".

The distinction that has to survive all of that is the one the count could
not make: "nothing here" against "a season you have finished". A plus and a
tick are different marks, so it does.

Two details worth pinning down, because each is a way to be wrong quietly:

  * The tally reads progress for every PLAYABLE file, and next-up's fetch was
    widened to Specials to supply it. Candidates leave Specials out by
    design, so without that a Specials season would read as all unwatched --
    an answer to a question nobody asked.
  * An episode you never had carries no spoiler hiding. On 2026-09-20 ten of
    Lioness's eleven Specials read "Details hidden", which hid the only thing
    the cards had to say.

Run:  python3 test_season_marks.py
"""
import datetime

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import episodes as E
from resources.lib.skin import icon_glyphs as G
from resources.lib.windows import detail as D
from resources.lib.windows.detail import DetailWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def f(fid, available=True):
    return {"id": fid, "available": available}


def ep(n, *files, air="2020-01-01"):
    return {"episode_number": n, "air_date": air, "files": list(files)}


def season(n, *eps):
    return {"season_number": n, "episodes": list(eps)}


DONE = {"completed": True}
HALF = {"completed": False, "position_ms": 600000}

# A season of four: two watched, one half-watched, one never started.
S1 = season(1, ep(1, f("a")), ep(2, f("b")), ep(3, f("c")), ep(4, f("d")))
P1 = {"a": DONE, "b": DONE, "c": HALF}

# ------------------------------------------------------------------ tally --
check("tally counts playable episodes and completed ones",
      E.season_tally(S1, P1) == (4, 2), str(E.season_tally(S1, P1)))
check("an unavailable file is not playable",
      E.season_tally(season(1, ep(1, f("x", False)), ep(2, f("y"))), {}) == (1, 0))
two_versions = season(1, ep(1, f("v1"), f("v2")))
check("two versions of one episode count once, by the FIRST available",
      E.season_tally(two_versions, {"v1": DONE}) == (1, 1)
      and E.season_tally(two_versions, {"v2": DONE}) == (1, 0))
check("an unavailable first version is skipped for the next available one",
      E.season_tally(season(1, ep(1, f("v1", False), f("v2"))), {"v2": DONE}) == (1, 1))

# ------------------------------------------------------------------ marks --
check("a finished season is a tick",
      E.season_mark(S1, {k: DONE for k in "abcd"}, selected=False)
      == (E.SEASON_MARK_COMPLETE, 0))
check("one in progress says how many are left",
      E.season_mark(S1, P1, selected=False) == (E.SEASON_MARK_LEFT, 2))
check("...and a never-started one counts all of them",
      E.season_mark(S1, {}, selected=False) == (E.SEASON_MARK_LEFT, 4))
check("the selected row is the dot, whatever its progress",
      E.season_mark(S1, P1, selected=True) == (E.SEASON_MARK_SELECTED, 0)
      and E.season_mark(S1, {k: DONE for k in "abcd"}, selected=True)
      == (E.SEASON_MARK_SELECTED, 0))

SPECIALS = season(0, *[ep(n) for n in range(1, 12)])     # Lioness S0: 11, no files
check("nothing in the library is the circled plus",
      E.season_mark(SPECIALS, {}, selected=False) == (E.SEASON_MARK_ADD, 0))
check("...and it keeps it when selected -- 'selected' is no news about a season you cannot play",
      E.season_mark(SPECIALS, {}, selected=True) == (E.SEASON_MARK_ADD, 0))
LOST = season(2, ep(1, f("g", False)), ep(2, f("h", False)))
check("files recorded but all gone is its own mark, selected or not",
      E.season_mark(LOST, {}, selected=False) == (E.SEASON_MARK_MISSING, 0)
      and E.season_mark(LOST, {}, selected=True) == (E.SEASON_MARK_MISSING, 0))
check("...and it is not the not-in-library mark",
      E.SEASON_MARK_MISSING != E.SEASON_MARK_ADD)
check("a shell makes no claim at all",
      E.season_mark({"season_number": 3}, {}, selected=False) == (E.SEASON_MARK_NONE, 0)
      and E.season_mark({"season_number": 3}, {}, selected=True) == (E.SEASON_MARK_NONE, 0))
PARTLY = season(1, ep(1, f("p")), ep(2))                 # one owned, one never had
check("everything you HAVE watched, with gaps in the library, is still a tick",
      E.season_mark(PARTLY, {"p": DONE}, selected=False) == (E.SEASON_MARK_COMPLETE, 0))

# ----------------------------------------------------------------- glyphs --
check("every glyph mark has a glyph and 'N left' has none",
      set(D._SEASON_MARK_GLYPH) == {E.SEASON_MARK_ADD, E.SEASON_MARK_MISSING,
                                    E.SEASON_MARK_COMPLETE, E.SEASON_MARK_SELECTED})
check("the glyphs are the ones read off the app",
      D._SEASON_MARK_GLYPH[E.SEASON_MARK_ADD] == G.CIRCLE_PLUS
      and D._SEASON_MARK_GLYPH[E.SEASON_MARK_COMPLETE] == G.CHECK
      and D._SEASON_MARK_GLYPH[E.SEASON_MARK_SELECTED] == G.DOT)
check("not-in-library and missing never share a glyph",
      D._SEASON_MARK_GLYPH[E.SEASON_MARK_ADD] != D._SEASON_MARK_GLYPH[E.SEASON_MARK_MISSING])

# --------------------------------------------------------- top-right line --
check("nothing to play reads 'No episodes'",
      D._season_watched_line(SPECIALS, 0, 0) == "<string 31128>")
check("...for a lost season too",
      D._season_watched_line(LOST, 0, 0) == "<string 31128>")
check("a finished season reads 'Season complete'",
      D._season_watched_line(S1, 4, 4) == "<string 31127>")
check("anything else is the running tally",
      D._season_watched_line(S1, 2, 4) == "2/4 watched")
check("finished means every PLAYABLE one, as the tick does",
      D._season_watched_line(PARTLY, 1, 1) == "<string 31127>")
PARTLY_3 = season(1, ep(1, f("a")), ep(2, f("b")), ep(3))   # two owned, one never had
check("a partial season's tally counts only what it can play (7.1)",
      D._season_watched_line(PARTLY_3, 1, 2) == "1/2 watched",
      D._season_watched_line(PARTLY_3, 1, 2))

# ------------------------------------------------------------------ cards --
future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
never = ep(1)
gone = ep(2, f("z", False))
coming = ep(3, air=future)
undated = {"episode_number": 4, "files": []}
check("an aired episode with no files is not in the library",
      D._not_in_library(never, None))
check("...and hands its badge over to the pill",
      D._unaired_label(never, None) == "")
check("recorded but unreachable is 'Unavailable', not the pill",
      not D._not_in_library(gone, None) and D._unaired_label(gone, None) == "Unavailable")
check("an episode still to come says when, not 'not in library'",
      not D._not_in_library(coming, None) and D._unaired_label(coming, None).startswith("Airs"))
check("no air date counts as aired, as the badge always has",
      D._not_in_library(undated, None))
check("a playable episode carries neither",
      not D._not_in_library(ep(5, f("q")), f("q")) and D._unaired_label(ep(5, f("q")), f("q")) == "")

# ------------------------------------------------------- one fetch for all --
SHOW = [SPECIALS, season(0, ep(12, f("s12"))), S1, LOST]
ids = D._playable_file_ids(SHOW)
check("the progress fetch covers Specials, which candidates leave out",
      "s12" in ids)
check("...one file per playable episode, the first available",
      ids == ["s12", "a", "b", "c", "d"], str(ids))


# ----------------------------------------------------------------- header --
class Fake:
    """The real header over the state it reads."""
    _render_season_header = DetailWindow._render_season_header
    _next_up_completed = DetailWindow._next_up_completed

    def __init__(self, nextup_season=None, nextup_ep=None, file_id=None, progress=None):
        self.props = {}
        self._next_up_season = nextup_season
        self._next_up_episode_number = nextup_ep
        self._next_up_file_id = file_id
        self._nextup_progress = progress or {}

    def setProperty(self, k, v):
        self.props[k] = v


w = Fake()
w._render_season_header(dict(SPECIALS, air_date="2023-01-10"))
check("the header carries the words the row no longer does",
      w.props["season_subtitle"].startswith("<string 31125>")
      and "11 episodes" in w.props["season_subtitle"], w.props["season_subtitle"])

S3 = dict(season(3, ep(1, f("e1")), ep(2, f("e2")), ep(3, f("e3"))), air_date="2026-01-01")
w = Fake(nextup_season=3, nextup_ep=3, file_id="e3", progress={"e3": HALF})
w._render_season_header(S3)
check("the season holding the next episode says Continue",
      w.props["season_subtitle"].endswith("<string 31130>"), w.props["season_subtitle"])
w = Fake(nextup_season=3, nextup_ep=3, file_id="e3", progress={"e3": DONE})
w._render_season_header(S3)
check("...but not once that episode is finished, as on a show watched to the end",
      "<string 31130>" not in w.props["season_subtitle"], w.props["season_subtitle"])
w = Fake(nextup_season=2, nextup_ep=1, file_id="x", progress={})
w._render_season_header(S3)
check("...and not on any other season",
      "<string 31130>" not in w.props["season_subtitle"])
w = Fake(nextup_season=0, nextup_ep=1, file_id="x", progress={})
w._render_season_header(SPECIALS)
check("...nor on one with nothing in the library",
      "<string 31130>" not in w.props["season_subtitle"])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
