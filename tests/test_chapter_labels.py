"""A chapter title has to be judged by its SHAPE, not just by emptiness.

Some containers write the chapter's own start time into the title field --
"00:02:42.662" -- and 8.2's scrub readout puts the timecode beside the
chapter name, so such a title renders as "17:43 00:02:42.662": the position
twice, in two formats, neither of them a name.

The cases below are the two directions that matter: a title that is not a
name must fall back to the chapter number, and a title that IS one -- very
much including "Chapter 3" -- must survive untouched.

Pure label logic -- no Kodi, no window.  Run:  python3 test_chapter_labels.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.player import PlayerWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def label(title, index=0):
    return PlayerWindow._chapter_label({"title": title, "chapter_index": index})


# 1. The two cases that must fall back, and the one that must not.
check("an empty title falls back to the number", label("", 1) == "Chapter 02",
      repr(label("", 1)))
check("a null title falls back too", label(None, 1) == "Chapter 02",
      repr(label(None, 1)))
check("a timecode title falls back as well",
      label("00:02:42.662", 1) == "Chapter 02", repr(label("00:02:42.662", 1)))
check("an ordinary title is kept", label("The Bridge", 1) == "The Bridge",
      repr(label("The Bridge", 1)))

# 2. A title that already SAYS "Chapter 3" is a name, and passes through
#    untouched -- it must not be renumbered to its position.
check('"Chapter 3" passes through untouched', label("Chapter 3", 7) == "Chapter 3",
      repr(label("Chapter 3", 7)))

# 3. Timecode spellings. Hours may be one or two digits, and the fractional
#    part may be absent or carry either separator.
for title in ("00:02:42.662", "0:02:42", "00:02:42", "12:34:56,789",
              "01:00:00.0", "00:00:00.000"):
    check(f"timecode {title!r} is not a name", label(title) == "Chapter 01",
          repr(label(title)))

# 4. ...and whitespace around one does not smuggle it through, because the
#    title is stripped before it is judged.
check("a padded timecode is still a timecode",
      label("  00:02:42.662  ") == "Chapter 01", repr(label("  00:02:42.662  ")))

# 5. A bare chapter ordinal is the same defect in different dress: "17:43 7"
#    is no more a name than "17:43 00:02:42.662".
check('"7" falls back', label("7", 6) == "Chapter 07", repr(label("7", 6)))
check('"07" falls back', label("07", 6) == "Chapter 07", repr(label("07", 6)))

# 6. But the bound matters. A four-digit number is a year far more often
#    than it is a chapter ordinal, so it keeps its place as a name.
check('"1994" is kept as a name', label("1994") == "1994", repr(label("1994")))
check('"101" is kept as a name', label("101") == "101", repr(label("101")))

# 7. Shapes NOT matched, on purpose -- nothing in the library produced one,
#    and "9:11" could genuinely be what a chapter is called.
check('"9:11" keeps its name', label("9:11") == "9:11", repr(label("9:11")))
check('SMPTE "00:02:42:15" keeps its name',
      label("00:02:42:15") == "00:02:42:15", repr(label("00:02:42:15")))

# 8. Neighbours of the timecode shape that are plainly names.
for title in ("3. The Bridge", "Chapter 00:02:42", "00:02:42.662 Intro",
              "Act 2", "12:34:56 - Credits"):
    check(f"{title!r} keeps its name", label(title) == title, repr(label(title)))

# 9. The numbering itself: index is zero-based on the wire and one-based,
#    zero-padded, on screen.
check("index 0 shows as Chapter 01", label("", 0) == "Chapter 01")
check("index 11 shows as Chapter 12", label("", 11) == "Chapter 12")
check("index 99 shows as Chapter 100 without truncating",
      label("", 99) == "Chapter 100", repr(label("", 99)))

# 10. End to end through _load_chapters: the stored SHAPE is unchanged --
#     (start_ms, label) pairs sorted by start -- because two other readers
#     take only the start (_render_scrub_markers' ticks, chapter_seek's jump
#     targets) and would break on anything else.
class FakeWindow:
    _chapters: list = []
    _chapter_label = staticmethod(PlayerWindow._chapter_label)
    def _load(self, bundle):
        PlayerWindow._load_chapters(self, bundle)
        return self._chapters

TICKS_PER_MS = 10_000
w = FakeWindow()
stored = w._load({"chapters": [
    {"chapter_index": 0, "title": "", "start_ticks": 0},
    {"chapter_index": 2, "title": "The Bridge", "start_ticks": 600_000 * TICKS_PER_MS},
    {"chapter_index": 1, "title": "00:02:42.662", "start_ticks": 162_662 * TICKS_PER_MS},
]})
check("every entry is still a (start_ms, label) pair",
      all(isinstance(e, tuple) and len(e) == 2 and isinstance(e[0], int)
          and isinstance(e[1], str) for e in stored), repr(stored))
check("still sorted by start", [s for s, _ in stored] == [0, 162_662, 600_000],
      repr([s for s, _ in stored]))
check("the timecode chapter carries its number instead",
      stored[1][1] == "Chapter 02", repr(stored[1][1]))
check("the named chapter is untouched", stored[2][1] == "The Bridge",
      repr(stored[2][1]))
check("the blank chapter still falls back", stored[0][1] == "Chapter 01",
      repr(stored[0][1]))

# 11. And the readout reads what was stored.
check("_chapter_at picks the chapter in progress",
      PlayerWindow._chapter_at(w, 200_000) == "Chapter 02",
      repr(PlayerWindow._chapter_at(w, 200_000)))
check("...and shows no name before the first chapter starts",
      PlayerWindow._chapter_at(w, -1) == "",
      repr(PlayerWindow._chapter_at(w, -1)))

# 12. A file with no chapters at all stays empty rather than gaining one.
check("an empty bundle stores nothing", FakeWindow()._load({}) == [])
check("a null chapter list stores nothing",
      FakeWindow()._load({"chapters": None}) == [])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
