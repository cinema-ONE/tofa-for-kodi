"""The Home hero's year follows the EPISODE, not the series.

A Continue Watching item carries the SERIES' `year` and, since server
0.10.0, the episode's own `air_date` (vault #161). The hero composes its
title from the series title plus the episode title and its synopsis from the
episode's `overview` -- so the year between them has to be the episode's too,
or the line reads as three facts about two different things: a 2025 episode
of a show that began in 2023, labelled 2023.

Cards are NOT affected and must stay as they are: `_card_meta_left` puts
"S1 E1" in that slot for an episode and never reaches the year at all.

Pure helper logic -- no Kodi window.  Run:  python3 test_hero_cw_year.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.main import _item_year, _card_meta_left

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# A Continue Watching episode as the server actually sends it: the series'
# year, the episode's air date, the episode's overview.
CW_EPISODE = {
    "media_type": "tv", "title": "Lioness", "year": 2023,
    "episode_number": 4, "season_number": 2, "episode_title": "Cruz",
    "air_date": "2025-11-09", "overview": "Things go awry for Joe's team.",
}
MOVIE = {"media_type": "movie", "title": "Heat", "year": 1995,
         "release_date": "1995-12-15"}

# 1. The hero case: the episode's own year wins.
check("an episode hero shows the EPISODE's year",
      _item_year(CW_EPISODE, episode=True) == "2025",
      repr(_item_year(CW_EPISODE, episode=True)))
check("...and without the flag it is still the series year",
      _item_year(CW_EPISODE) == "2023", repr(_item_year(CW_EPISODE)))

# 2. A movie is untouched either way -- there is no episode to prefer.
check("a movie keeps its year", _item_year(MOVIE) == "1995", repr(_item_year(MOVIE)))
check("...even if the flag is passed", _item_year(MOVIE, episode=True) == "1995",
      repr(_item_year(MOVIE, episode=True)))

# 3. An older server sends no air_date. The series year comes back: wrong in
#    the way it always was, rather than blank, which is the point of warning
#    about the server version instead of blocking on it.
OLD = dict(CW_EPISODE); OLD.pop("air_date")
check("no air_date falls back to the series year",
      _item_year(OLD, episode=True) == "2023", repr(_item_year(OLD, episode=True)))

# 4. Junk in air_date must not reach the screen.
for bad in ("", None, "n/a", "20", "not-a-date"):
    item = dict(CW_EPISODE); item["air_date"] = bad
    check(f"air_date {bad!r} falls back rather than printing junk",
          _item_year(item, episode=True) == "2023",
          repr(_item_year(item, episode=True)))

# 5. An episode with NO series year and a good air_date still reads.
NOYEAR = dict(CW_EPISODE); NOYEAR.pop("year")
check("no series year, air_date carries it",
      _item_year(NOYEAR, episode=True) == "2025", repr(_item_year(NOYEAR, episode=True)))

# 6. Nothing at all is blank, not a crash and not a stray dot.
check("an empty item is blank", _item_year({}, episode=True) == "")

# 7. The CARD slot is unchanged: an episode gets its number, never a year.
left = _card_meta_left(CW_EPISODE)
check("a card still leads with the episode number, not a year",
      "2025" not in left and "2023" not in left, repr(left))
check("a movie card still leads with its year", _card_meta_left(MOVIE) == "1995",
      repr(_card_meta_left(MOVIE)))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
