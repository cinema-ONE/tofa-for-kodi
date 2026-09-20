"""The viewer's tofa subtitle SIZE reaches Kodi; the other nine do not.

tofa syncs ten subtitle appearance preferences per profile. Only
`subtitles.sizePercent` is honoured here, and the reasoning is in
subtitlesize.py: the colours have no Kodi target at all, and the vertical
offset only LOOKS like `subtitles.marginvertical` -- tofa's default of 5
means "the normal inset" where Kodi's value was 0.6 on a 0..50 range, so
mapping one to the other would move subtitles for someone who never asked.

What is pinned here is the arithmetic and, more importantly, the
NEUTRALITY: at 100, at an unreadable value, and where Kodi's own bounds make
the change a no-op, nothing is written and no marker is left. That matters
because `subtitles.fontsize` is a GLOBAL Kodi setting.

Run:  python3 test_subtitle_size_pref.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import subtitlesize as S

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# 1. Reading the preference. The blob stores dotted keys as STRINGS.
check("a string percent parses", S.wanted_percent({"subtitles.sizePercent": "150"}) == 150)
check("an int percent parses too", S.wanted_percent({"subtitles.sizePercent": 150}) == 150)
check("the neutral default reads as 100",
      S.wanted_percent({"subtitles.sizePercent": "100"}) == 100)
check("a nested shape is read as well",
      S.wanted_percent({"subtitles": {"sizePercent": "125"}}) == 125)

# 2. Anything we cannot read is ABSENT, never a licence to resize.
for bad in (None, "", "abc", "12.5", {}, [], "0", "-50", "5", "999"):
    prefs = {} if bad is None else {"subtitles.sizePercent": bad}
    check(f"{bad!r} reads as absent", S.wanted_percent(prefs) is None,
          repr(S.wanted_percent(prefs)))
check("no prefs at all is absent", S.wanted_percent(None) is None)
check("a non-dict is absent", S.wanted_percent("nonsense") is None)

# 3. The arithmetic, inside Kodi's own bounds (12..74).
for base, pct, want in ((22, 100, 22), (22, 150, 33), (22, 50, 11 if 11 >= S.MIN_SIZE else 12),
                        (22, 200, 44), (22, 10, 12), (60, 200, 74), (74, 150, 74),
                        (12, 50, 12), (30, 125, 38)):
    got = S.scaled(base, pct)
    expect = max(S.MIN_SIZE, min(S.MAX_SIZE, round(base * pct / 100.0)))
    check(f"{base} at {pct}% -> {expect}", got == expect, repr(got))

check("never below Kodi's floor", all(S.scaled(b, p) >= S.MIN_SIZE
                                      for b in (12, 22, 74) for p in (10, 50, 100, 400)))
check("never above Kodi's ceiling", all(S.scaled(b, p) <= S.MAX_SIZE
                                        for b in (12, 22, 74) for p in (10, 50, 100, 400)))

# 4. Neutrality: what apply() must NOT do. The Kodi read/write and the
#    on-disk marker are swapped for recorders, so "nothing was written" is
#    checkable rather than assumed. That matters: `subtitles.fontsize` is a
#    GLOBAL Kodi setting, and the common case must leave it alone.
class Fake:
    def __init__(self, current=22, saved=None):
        self.current, self.saved, self.writes = current, saved, []
    def install(self):
        S._get = lambda: self.current
        S._read_saved = lambda: self.saved
        S._write_saved = lambda v: setattr(self, "saved", v)
        S._clear_saved = lambda: setattr(self, "saved", None)
        def _set(v):
            self.writes.append((S.SETTING, v)); self.current = v; return True
        S._set = _set
        return self

def writes_for(prefs, current=22, saved=None):
    f = Fake(current, saved).install()
    S.apply(prefs)
    return f

f = writes_for({"subtitles.sizePercent": "100"})
check("100% writes nothing", f.writes == [], repr(f.writes))
check("...and leaves no marker behind", f.saved is None, repr(f.saved))
check("an absent preference writes nothing", writes_for({}).writes == [])
check("an unreadable preference writes nothing",
      writes_for({"subtitles.sizePercent": "nonsense"}).writes == [])
f = writes_for({"subtitles.sizePercent": "101"}, current=22)
check("a size that rounds to the same value writes nothing", f.writes == [],
      repr(f.writes))

# 5. ...and what it must do, exactly once, to exactly one setting.
f = writes_for({"subtitles.sizePercent": "150"}, current=22)
check("150% on a base of 22 writes 33", f.writes == [(S.SETTING, 33)], repr(f.writes))
check("...and parks the viewer's own 22 for restoring", f.saved == 22, repr(f.saved))

# 6. A neutral preference UNDOES an earlier one rather than leaving it.
#    Someone who sets 150% and then puts it back to 100 gets their own size
#    back at the next playback, not the one we applied.
f = Fake(current=33, saved=22).install()
S.apply({"subtitles.sizePercent": "100"})
check("back to 100% restores the parked size", f.writes == [(S.SETTING, 22)],
      repr(f.writes))
check("...and clears the marker", f.saved is None, repr(f.saved))

# 7. restore() is a no-op when we never changed anything -- so a player that
#    closes without ever applying cannot write a global setting.
f = Fake(current=22, saved=None).install()
S.restore()
check("restore with no marker writes nothing", f.writes == [], repr(f.writes))

# 8. restore_stale() is the crash path: a marker left by a run that died.
f = Fake(current=33, saved=22).install()
S.restore_stale()
check("a stale marker is put back at launch", f.writes == [(S.SETTING, 22)],
      repr(f.writes))
check("...and cleared", f.saved is None)
f = Fake(current=22, saved=None).install()
S.restore_stale()
check("no stale marker, nothing happens", f.writes == [], repr(f.writes))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
