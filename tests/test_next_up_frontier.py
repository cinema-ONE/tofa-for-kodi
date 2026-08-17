"""Which episode a show offers, when nothing is part-watched.

progress.next_up() answers this for BOTH the detail hero and the card
context menu, so a wrong answer here is wrong on two surfaces one keypress
apart -- which is the whole reason the rule was consolidated into one
function.

The case this suite exists for: a viewer who FINISHED a late season and left
nothing mid-flight. Scanning for the first not-completed episode from S1 E1
offers them S1 E1, because the earliest gap in a long show is almost never
where they are. Continue Watching promotes the episode after the last one
finished, and the hero has to agree with it.

Run:  python3 test_next_up_frontier.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import progress

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def ep(season, number):
    """One candidate in next_up's shape: (season, episode, item, file)."""
    fid = f"s{season}e{number}"
    return (season, number, {"id": fid, "title": f"S{season} E{number}"}, {"id": fid})


def label(chosen):
    return "none" if chosen is None else f"S{chosen[0]} E{chosen[1]}"


def done(*ids):
    return {i: {"completed": True} for i in ids}


# A three-season show, six episodes a season.
SHOW = [ep(s, n) for s in (1, 2, 3) for n in range(1, 7)]

# ---------------------------------------------------------------- the bug
# Finished S1 and S2 and the first three of S3. Nothing part-watched.
watched = done(*[f"s{s}e{n}" for s in (1, 2) for n in range(1, 7)],
               "s3e1", "s3e2", "s3e3")
chosen = progress.next_up(SHOW, watched)
# Unchanged by the frontier rule -- with no gaps the earliest one IS the next
# episode. Here so the fix cannot break the ordinary case while fixing the odd
# ones; the two checks below are the ones that fail without it.
check("a contiguous finished run still offers the next episode",
      (chosen[0], chosen[1]) == (3, 4), label(chosen))

# The same viewer, but with a gap left behind them on purpose: S2 E4 skipped.
skipped = dict(watched)
del skipped["s2e4"]
chosen = progress.next_up(SHOW, skipped)
check("a gap BEHIND the frontier stays skipped",
      (chosen[0], chosen[1]) == (3, 4), label(chosen))

# Only a late season watched, nothing at all before it.
late = done("s3e1", "s3e2")
chosen = progress.next_up(SHOW, late)
check("history in a late season alone still moves forward",
      (chosen[0], chosen[1]) == (3, 3), label(chosen))

# ------------------------------------------------- the other rules survive
# (1) A part-watched episode still wins over the frontier, and the MOST
# recently touched one when several are going at once.
part = dict(done(*[f"s{s}e{n}" for s in (1, 2) for n in range(1, 7)]))
part["s1e3"] = {"position_ms": 500, "updated_at": "2026-01-01"}
part["s3e2"] = {"position_ms": 900, "updated_at": "2026-06-01"}
chosen = progress.next_up(SHOW, part)
check("a part-watched episode still outranks the frontier",
      (chosen[0], chosen[1]) == (3, 2), label(chosen))

# (0) The caller's choice still wins over everything.
chosen = progress.next_up(SHOW, watched, prefer_file_id="s1e5")
check("the caller's episode still wins",
      (chosen[0], chosen[1]) == (1, 5), label(chosen))

# (3) No frontier at all -- nothing completed -- falls back to the top.
chosen = progress.next_up(SHOW, {})
check("a show never touched offers S1 E1",
      (chosen[0], chosen[1]) == (1, 1), label(chosen))

# (4) Everything completed is a rewatch, and starts at the beginning.
chosen = progress.next_up(SHOW, done(*[f"s{s}e{n}" for s in (1, 2, 3)
                                       for n in range(1, 7)]))
check("a fully watched show offers S1 E1",
      (chosen[0], chosen[1]) == (1, 1), label(chosen))

# next_up scans forward through `candidates`, so it only answers correctly
# for a list in season/episode order. That is episode_candidates' documented
# contract and it sorts to keep it -- checked here because the two are only
# safe together, and rule (3) has always depended on it too.
seasons = [
    {"season_number": 3, "episodes": [
        {"episode_number": 2, "files": [{"id": "s3e2", "available": True}]},
        {"episode_number": 1, "files": [{"id": "s3e1", "available": True}]}]},
    {"season_number": 0, "episodes": [
        {"episode_number": 1, "files": [{"id": "sp1", "available": True}]}]},
    {"season_number": 1, "episodes": [
        {"episode_number": 1, "files": [{"id": "s1e1", "available": True}]}]},
]
built = progress.episode_candidates(seasons)
check("episode_candidates sorts, which next_up relies on",
      [(c[0], c[1]) for c in built] == [(1, 1), (3, 1), (3, 2)],
      str([(c[0], c[1]) for c in built]))
chosen = progress.next_up(built, done("s1e1", "s3e1"))
check("and the frontier answer holds on what it produces",
      (chosen[0], chosen[1]) == (3, 2), label(chosen))

# No candidates at all stays None rather than raising.
check("no candidates answers None", progress.next_up([], {}) is None)


print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
