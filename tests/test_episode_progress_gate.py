"""Detail's episode rows only get repainted when they actually changed.

This is the invariant that lets the grid builder hand its rows to Kodi with
offscreen=True (issue #11). Every ListItem setter takes Kodi's frame-move
guard, so a write on a busy 4K screen can wait a whole frame; repainting all
22 rows of a season to change three properties on one of them is what the
gate exists to stop. If this suite fails, the offscreen build is no longer
safe -- the two go together.

Run:  python3 test_episode_progress_gate.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeItem:
    """ManagedListItem's contract for this code: getProperty reads a local
    dict and takes no lock, setProperty is the expensive one. Counted."""

    def __init__(self):
        self.properties = {}
        self.writes = 0

    def getProperty(self, key):
        return self.properties.get(key, "")

    def setProperty(self, key, value):
        self.properties[key] = value
        self.writes += 1


class FakeDetail:
    """Just enough of DetailWindow for the two functions under test."""
    _progress_pct = staticmethod(
        lambda prog, f: float((prog or {}).get("pct") or 0.0))
    _format_badge_labels = staticmethod(lambda f: ["4K", "Atmos"])

    _episode_progress_props = DetailWindow._episode_progress_props
    _apply_episode_progress = DetailWindow._apply_episode_progress


win = FakeDetail()
EP = {"episode_number": 5, "runtime_minutes": 42}
FILE = {"id": "f5", "duration_ms": 42 * 60_000}


# ---- a fresh row writes everything ----------------------------------------

item = FakeItem()
wrote = win._apply_episode_progress(item, EP, FILE, {"pct": 0.5})
check("first paint reports a write", wrote is True)
# Two, not three: `watched` computes to "" on an unwatched episode and
# getProperty answers "" for a key that was never set, so the gate correctly
# skips it. An unset property and an empty one are the same thing to every
# <visible> condition in the XML -- so this is a saving, not a gap.
check("first paint writes only the non-empty properties",
      item.writes == 2, str(item.writes))
check("capsule is set mid-episode",
      item.getProperty("progress_fill").startswith("episode-progress/"),
      item.getProperty("progress_fill"))


# ---- the same data again writes NOTHING ----------------------------------

before = item.writes
wrote = win._apply_episode_progress(item, EP, FILE, {"pct": 0.5})
check("unchanged row reports no write", wrote is False)
check("unchanged row writes nothing", item.writes == before,
      f"{item.writes - before} extra writes")


# ---- a real change writes only what moved --------------------------------

before = item.writes
wrote = win._apply_episode_progress(item, EP, FILE, {"pct": 0.75})
check("changed progress reports a write", wrote is True)
check("changed progress writes fill AND caption",
      item.writes - before == 2, f"{item.writes - before} writes")
check("the capsule moved to the new step",
      item.getProperty("progress_fill") == "episode-progress/76.png",
      item.getProperty("progress_fill"))
check("the caption carries the new time left",     # 42 * 0.25 = 10.5 -> 10
      "10m left" in item.getProperty("caption"), item.getProperty("caption"))

# Completing it clears the capsule and sets the tick: all three move.
before = item.writes
wrote = win._apply_episode_progress(item, EP, FILE, {"completed": True})
check("completion reports a write", wrote is True)
check("completed row shows the tick", item.getProperty("watched") == "1")
check("completed row drops the capsule", item.getProperty("progress_fill") == "")


# ---- the shape the box actually sees -------------------------------------
# One episode watched out of a 22-row season: 21 rows must stay untouched.

rows = []
for number in range(1, 23):
    row = FakeItem()
    win._apply_episode_progress(row, {"episode_number": number}, FILE, None)
    row.writes = 0                      # built; now measure only the refresh
    rows.append(row)

for number, row in enumerate(rows, start=1):
    record = {"completed": True} if number == 3 else None
    win._apply_episode_progress(row, {"episode_number": number}, FILE, record)

touched = [i + 1 for i, r in enumerate(rows) if r.writes]
check("a 22-row season repaints exactly one row", touched == [3], str(touched))
check("and that row takes ONE write", rows[2].writes == 1, str(rows[2].writes))
check("total locked writes are 1, not 66",
      sum(r.writes for r in rows) == 1, str(sum(r.writes for r in rows)))


print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
