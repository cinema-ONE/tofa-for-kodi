"""Under a minute in, a title has not been started.

It's Always Sunny on a test profile offered "Resume S18 E2" for a 6 ms
record. Run:  python3 test_resume_floor.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import parts, progress

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


check("6 ms is not a resume point", progress.position_of({"position_ms": 6}) == (0, False))
check("59 s is not either", progress.position_of({"position_ms": 59_999})[0] == 0)
check("a minute is", progress.position_of({"position_ms": 60_000})[0] == 60_000)
check("completed survives the floor",
      progress.position_of({"position_ms": 5, "completed": True}) == (0, True))


def cand(n, fid):
    return (1, n, {"episode_number": n}, {"id": fid})


cands = [cand(1, "a"), cand(2, "b"), cand(3, "c")]
pmap = {"a": {"completed": True}, "b": {"position_ms": 6, "updated_at": "2"}}
chosen = progress.next_up(cands, pmap)
check("a 6 ms record does not count as started, but E2 is still next",
      chosen[1] == 2, repr(chosen[1]))
pmap = {"a": {"completed": True}, "c": {"position_ms": 6, "updated_at": "9"}}
chosen = progress.next_up(cands, pmap)
check("...so it cannot pull next-up past the real frontier", chosen[1] == 2, repr(chosen[1]))

group = [{"id": "p1"}, {"id": "p2"}]
check("a split part opened for a moment does not take over",
      parts.resume_point(group, {"p1": {"position_ms": 1_200_000, "updated_at": "1"},
                                 "p2": {"position_ms": 4, "updated_at": "2"}}) == (0, 1_200_000))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"resume floor: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
