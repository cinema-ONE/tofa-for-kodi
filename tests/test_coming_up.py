"""Coming Up's planner (app 2.1.0): pages, labels and how focus moves.

Run:  python3 test_coming_up.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import coming_up as cu
from resources.lib import discover, home_rows, textmetrics

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


def item(title, date, venue="episode", **release):
    return {"title": title, "type": "tv" if venue == "episode" else "movie", "tmdb_id": len(title),
            "genres": ["Mystery", "Drama", "Crime"], "content_rating": "TV-PG",
            "overview": "The show.", "release": dict({"date": date, "venue": venue}, **release)}


SHELF = {"key": "coming-up-shows", "form": "spotlight",
         "window": {"from": "2026-10-19", "to": "2026-11-01", "page_days": 7},
         "items": [item("Murdoch Mysteries", "2026-10-19", season_number=20, episode_number=3),
                   item("Brothers", "2026-10-20", season_number=1, episode_number=6),
                   item("VisionQuest", "2026-10-20", season_number=1, episode_number=3,
                        episode_number_last=4),
                   item("Late", "2026-10-30", season_number=2, episode_number=1),
                   item("Beyond", "2026-11-09", season_number=1, episode_number=1),
                   {"title": "Undated", "release": None}]}

pages = cu.pages(SHELF)
check("two pages of seven days from the window", [p["from"] for p in pages] == ["2026-10-19", "2026-10-26"])
check("entries land on their day, the undated and out-of-window ones nowhere",
      [len(d["entries"]) for d in pages[0]["days"]] == [1, 2, 0, 0, 0, 0, 0]
      and pages[1]["count"] == 1, str([len(d["entries"]) for d in pages[0]["days"]]))
check("something beyond the window keeps every page reachable",
      cu.last_page(pages, cu.beyond(cu.entries(SHELF), "2026-11-01") is not None) == 1)
check("...and nothing beyond stops at the last page with a release",
      cu.last_page([pages[0], dict(pages[1], count=0)], False) == 0)

check("Today, Tomorrow, in N days", [cu.relative(d, "2026-10-19") for d in
                                     ("2026-10-19", "2026-10-20", "2026-10-23", "2026-10-18")]
      == ["Today", "Tomorrow", "in 4 days", None])
check("weekends are told apart", cu.is_weekend("2026-10-24") and not cu.is_weekend("2026-10-23"))
check("an episode, a run of episodes, a film's venue",
      [cu.venue_label(r) for r in ({"venue": "episode", "season_number": 20, "episode_number": 3},
                                   {"venue": "episode", "season_number": 1, "episode_number": 3,
                                    "episode_number_last": 4},
                                   {"venue": "cinema"}, {"venue": "home"})]
      == ["S20 E3", "S1 E3–4", "In cinemas", "At home"])
check("the hero's line: what, when, how soon",
      cu.hero_meta({"venue": "episode", "season_number": 20, "episode_number": 3,
                    "date": "2026-10-19"}, "2026-10-19", lambda d: "Mon 19 Oct")
      == ["S20 E3", "Mon 19 Oct", "Today"])
check("two genres and the rating", cu.genre_line(SHELF["items"][0]) == "Mystery, Drama · TV-PG")
check("the episode's own story first",
      cu.overview({"item": {"overview": "show"}, "release": {"episode_overview": "ep"}}) == "ep")
check("an empty page points at the next release",
      cu.next_line({"item": {"title": "Dune"}, "release": {"date": "2026-12-04", "venue": "cinema"}},
                   lambda d: "Fri 4 Dec") == "Next: Dune in cinemas on Fri 4 Dec")

crowded = {"entries": list(range(16))}
check("a crowded day shows 14 and N more", cu.shown(crowded) == (list(range(14)), 2)
      and cu.stops(crowded) == 15)
check("fifteen still fit", cu.shown({"entries": list(range(15))})[1] == 0)

# Focus, as the web's planner moves it.
check("the first stop is the first day with something", cu.first_stop(pages, 0) == (0, 0, 0))
check("Down walks a day's rows, then stays",
      cu.move(pages, (0, 1, 0), "down", 1) == ("focus", (0, 1, 1))
      and cu.move(pages, (0, 1, 1), "down", 1) == ("stay",))
check("Up from the first row leaves for the pills", cu.move(pages, (0, 0, 0), "up", 1) == ("leave",))
check("Right keeps the row where it can", cu.move(pages, (0, 0, 0), "right", 1) == ("focus", (0, 1, 0)))
check("Left from row 2 lands on the last row of a shorter day",
      cu.move(pages, (0, 1, 1), "left", 1) == ("focus", (0, 0, 0)))
check("Right past the last day turns the page, skipping empty days",
      cu.move(pages, (0, 1, 0), "right", 1) == ("focus", (1, 4, 0)))
check("...but not past the last page", cu.move(pages, (1, 4, 0), "right", 1) == ("stay",))
check("Left at the first page stays", cu.move(pages, (0, 0, 0), "left", 1) == ("stay",))

check("titles wrap as the column allows",
      cu.wrap("Outlander: Blood of My Blood", 152, textmetrics.card_title_width)
      == ["Outlander:", "Blood of My", "Blood"],
      str(cu.wrap("Outlander: Blood of My Blood", 152, textmetrics.card_title_width)))
check("rows: the thumb's height, else the title's lines",
      [cu.row_height(n) for n in (1, 2, 3, 4)] == [81, 96, 124, 151],
      str([cu.row_height(n) for n in (1, 2, 3, 4)]))

grouped = discover.group_shelves({"shelves": [dict(SHELF, group="coming-up", items=[])]},
                                 home_rows.DISCOVER_TABS)
check("an empty planner view is kept: it says Nothing dated", len(grouped["coming-up"]) == 1)

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
