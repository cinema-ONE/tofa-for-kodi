"""Detail's hero meta line describes the EPISODE the Play pill would start.

The synopsis already did (see _apply_episode_synopsis); the year and runtime
did not, so Silo read "2023 - TV-MA - 50 min" -- the series' first year and
its average runtime -- above the synopsis of a 2026 episode running 46
minutes. The reference app has the same split, captured 2026-09-17.

Rating and genres stay the SHOW's: TMDB carries neither per episode.

Run:  python3 test_detail_episode_meta.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


SHOW = {"title": "Silo", "release_date": "2023-05-04", "content_rating": "TV-MA",
        "runtime_minutes": 50, "genres": ["Sci-Fi & Fantasy", "Drama", "Thriller"],
        "overview": "Men and women live in a giant silo underground."}

EPISODE = {"title": "Who Are You?", "air_date": "2026-07-02",
           "runtime_minutes": None, "overview": "New mayor Juliette can't remember."}

FILE = {"id": "f1", "duration_ms": 2_760_000}          # 46 min


class Fake:
    """The real methods over the state they read."""

    _apply_episode_meta_line = DetailWindow._apply_episode_meta_line
    _remember_next_up = DetailWindow._remember_next_up

    def __init__(self, media):
        self.media = media
        self.props = {}
        self._hero_meta_base = ""
        self._next_up_season = None
        self._next_up_episode_number = None
        self._next_up_title = ""
        self._next_up_overview = ""
        self._next_up_year = ""
        self._next_up_runtime = 0

    def setProperty(self, key, value):
        self.props[key] = value

    def line(self):
        return self.props.get("hero_meta_line", "")


def show_hero(media=SHOW):
    """What _render_hero writes before any episode is known."""
    f = Fake(media)
    f._hero_meta_base = u" • ".join(
        [str(media["release_date"][:4]), media["content_rating"], "50 min"]
        + media["genres"][:2])
    f.setProperty("hero_meta_line", f._hero_meta_base)
    return f


# ---- the reported case ---------------------------------------------------
f = show_hero()
check("before the episode resolves, the show's own line stands",
      f.line() == u"2023 • TV-MA • 50 min • Sci-Fi & Fantasy • Drama", f.line())

f._remember_next_up(3, 1, EPISODE, FILE)
f._apply_episode_meta_line()
check("episode year and runtime replace the show's",
      f.line() == u"Who Are You? • 2026 • TV-MA • 46 min • Sci-Fi & Fantasy • Drama",
      f.line())

# ---- the parts that stay the show's --------------------------------------
check("rating and both genres are still the show's",
      "TV-MA" in f.line() and "Sci-Fi & Fantasy" in f.line() and "Drama" in f.line())
check("a third genre is still not listed", "Thriller" not in f.line())

# ---- fallbacks -----------------------------------------------------------
f = show_hero()
f._remember_next_up(3, 1, dict(EPISODE, air_date=None), FILE)
f._apply_episode_meta_line()
check("an episode with no air date falls back to the show's year",
      f.line() == u"Who Are You? • 2023 • TV-MA • 46 min • Sci-Fi & Fantasy • Drama",
      f.line())

f = show_hero()
f._remember_next_up(3, 1, dict(EPISODE, runtime_minutes=52), None)
f._apply_episode_meta_line()
check("with no file, TMDB's episode runtime is used, not the show's 50",
      "52 min" in f.line() and "50 min" not in f.line(), f.line())

f = show_hero()
f._remember_next_up(3, 1, dict(EPISODE, runtime_minutes=None), None)
f._apply_episode_meta_line()
check("an episode with neither file nor runtime falls back to the show's",
      "50 min" in f.line(), f.line())

# ---- a movie, and a show whose next-up never resolved --------------------
f = show_hero({"title": "Hokum", "release_date": "2026-01-01", "content_rating": "R",
               "runtime_minutes": 108, "genres": ["Horror"]})
before = f.line()
f._apply_episode_meta_line()
check("a movie's line is untouched", f.line() == before, f.line())

# ---- the refresh path ----------------------------------------------------
f = show_hero()
f._remember_next_up(3, 1, EPISODE, FILE)
f._apply_episode_meta_line()
once = f.line()
f._apply_episode_meta_line()
check("running twice does not stack a second title", f.line() == once, f.line())

f._remember_next_up(3, 2, dict(EPISODE, title="The Engineer", air_date="2026-07-09"), FILE)
f._apply_episode_meta_line()
check("moving to the next episode replaces the line, not prepends",
      f.line() == u"The Engineer • 2026 • TV-MA • 46 min • Sci-Fi & Fantasy • Drama",
      f.line())

print("\n" + "=" * 60)
FAILED = sum(1 for _, ok in RESULTS if not ok)
if FAILED:
    print(f"{FAILED} of {len(RESULTS)} checks FAILED")
    raise SystemExit(1)
print(f"the hero meta line follows the episode ({len(RESULTS)} checks)")
