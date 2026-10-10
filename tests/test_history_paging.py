"""History pages back through the server's play log for enough titles.

/watch/history logs every play and serves at most 200 a page, so one binge
filled a page with one show: 200 plays were 14 titles (measured 2026-10-10).

Run:  python3 test_history_paging.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import http  # noqa: E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeClient:
    """A play log, newest first, served 200 a page by keyset, as the server."""

    def __init__(self, plays, fail_page=None):
        self.plays = plays
        self.calls = []
        self.fail_page = fail_page

    def watch_history(self, limit=None, before=None, before_id=None):
        self.calls.append((limit, before, before_id))
        if self.fail_page == len(self.calls):
            raise http.ApiError(503, "unavailable", "boom")
        start = 0
        if before_id:
            start = next(i for i, p in enumerate(self.plays) if p["id"] == before_id) + 1
        page = self.plays[start:start + min(limit, 200)]
        return {"items": page, "has_more": start + len(page) < len(self.plays)}


def log(titles_per_page, pages):
    """`pages` pages of 200 plays; each page cycles its own titles."""
    plays = []
    for p in range(pages):
        for n in range(200):
            t = "p%d-t%d" % (p, n % titles_per_page)
            plays.append({"id": "play-%d-%d" % (p, n), "media_id": t,
                          "started_at": "2026-10-%02dT%03d" % (28 - p, 999 - n)})
    return plays


# A binge: every page is 3 shows, so 100 titles are never reached.
binge = FakeClient(log(3, 9))
got = main.history_titles(binge)
check("a binge reads five pages, no more", len(binge.calls) == main.HISTORY_PAGES,
      str(len(binge.calls)))
check("...and keeps every title it found, once", len(got) == 15 and len({g["media_id"] for g in got}) == 15)
check("each title keeps its newest play", got[0]["id"] == "play-0-0")
check("the next page is asked after the last play",
      binge.calls[1] == (200, "2026-10-28T800", "play-0-199"), str(binge.calls[1]))

# A wide log: 100 titles on the first page are enough.
wide = FakeClient(log(150, 3))
got = main.history_titles(wide)
check("enough titles stop the paging", len(wide.calls) == 1 and len(got) == 100)

# A short log ends on has_more.
short = FakeClient(log(5, 1)[:40])
got = main.history_titles(short)
check("the end of the log stops the paging", len(short.calls) == 1 and len(got) == 5)

# The landing's row wants only a few.
row = FakeClient(log(3, 9))
got = main.history_titles(row, 4)
check("a smaller want stops early and is cut to it", len(row.calls) == 2 and len(got) == 4,
      "%d calls, %d titles" % (len(row.calls), len(got)))

# A show on page one is not repeated from page two.
repeat = FakeClient(log(3, 2))
for p in repeat.plays[200:]:
    p["media_id"] = "p0-t0"
got = main.history_titles(repeat)
check("a title already seen is not added again", [g["media_id"] for g in got] == ["p0-t0", "p0-t1", "p0-t2"])

# A title gone from the library: no media_id on any of its plays.
gone = FakeClient(log(3, 1))
for p in gone.plays[:6]:
    p.update(media_id=None, title="Gone", media_type="movie")
gone.plays[6].update(media_id=None, title=None)
got = main.history_titles(gone)
check("a gone title's plays make one card, by name",
      sum(1 for g in got if g.get("title") == "Gone") == 1 and got[0]["title"] == "Gone")
check("...and a play with neither id nor name stays on its own",
      sum(1 for g in got if not g.get("media_id") and not g.get("title")) == 1)

# A later page that fails keeps the first.
flaky = FakeClient(log(3, 9), fail_page=2)
got = main.history_titles(flaky)
check("a failed later page keeps what came first", len(got) == 3)
try:
    main.history_titles(FakeClient(log(3, 2), fail_page=1))
    check("a failed first page is the caller's to report", False)
except http.ApiError:
    check("a failed first page is the caller's to report", True)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
