"""Inside a collection, Unwatched/Filter narrow the members client-side.

A null on a member means not owned or unknown: it matches no filter.

Run:  python3 test_collection_member_filters.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import artcache  # noqa: E402
from lib.windows import main  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def member(title, *, watched=None, is_4k=None, rng=None, audio=None, year=2000):
    return {"title": title, "watched": watched, "is_4k": is_4k,
            "dynamic_range": rng, "audio_format": audio, "year": year, "genres": []}


SDR = member("sdr", watched=False, is_4k=False, audio="DTS-HD MA", year=1965)
DV = member("dv", watched=True, is_4k=True, rng="DV", audio="Atmos", year=2015)
HDR10 = member("hdr10", watched=False, is_4k=True, rng="HDR10", year=2008)
SDR4K = member("sdr4k", watched=False, is_4k=True, audio="Atmos", year=1997)
UNOWNED = member("unowned", year=2025)
NO_STATE = member("no state", is_4k=True, rng="HDR10+")   # watched null
MEMBERS = [SDR, DV, HDR10, SDR4K, UNOWNED, NO_STATE]


def titles(watched=None, quality=None, year_from=None, year_to=None):
    return [m["title"] for m in MEMBERS
            if main.collection_member_matches(m, watched, quality, year_from, year_to)]


# --- the predicate ------------------------------------------------------
check("no filter keeps every member", titles() == [m["title"] for m in MEMBERS])
check("Unwatched keeps watched=False only, never a null",
      titles(watched="unwatched") == ["sdr", "hdr10", "sdr4k"], str(titles(watched="unwatched")))
check("Watched keeps watched=True only", titles(watched="watched") == ["dv"])
check("4K keeps is_4k=True only", titles(quality="uhd4k") == ["dv", "hdr10", "sdr4k", "no state"])
check("4K HDR needs a dynamic range too",
      titles(quality="uhd4k_hdr") == ["dv", "hdr10", "no state"])
check("HDR counts Dolby Vision, as the server's filter does",
      titles(quality="hdr") == ["dv", "hdr10", "no state"])
check("Dolby Vision matches the DV label", titles(quality="dolby_vision") == ["dv"])
check("...and the enum spelling",
      main.collection_member_matches(member("x", rng="dolby_vision"), None, "dolby_vision", None, None))
check("Atmos reads audio_format", titles(quality="atmos") == ["dv", "sdr4k"])
check("a decade filter keeps that decade",
      titles(year_from=2000, year_to=2009) == ["hdr10", "no state"])
check("Before 1980 has no lower bound", titles(year_to=1979) == ["sdr"])
check("a member without a year fails a year filter",
      not main.collection_member_matches(member("x", year=None), None, None, None, 1979))
check("axes combine", titles(watched="unwatched", quality="uhd4k") == ["hdr10", "sdr4k"])


# --- the panel offers only what a member can answer ---------------------
class FakeGrid:
    def __init__(self):
        self.items = []

    def reset(self):
        self.items = []

    def addItems(self, items):
        self.items.extend(items)


class FakeClient:
    def stage_pairs(self, items, *fields, **kw):
        return []


W = main.MainWindow


class FakeWindow:
    """A stand-in `self` carrying the real browse methods it exercises."""

    def __init__(self, collection):
        self._browse_collection = collection
        self._server_capabilities = {"media.watched_played"}
        self._active_genre = W.ALL_GENRES
        self._browse_sort_idx = 1           # Title, so the order is stable
        self._browse_sort_reversed = False
        self._browse_reset_filters()
        self.grid_list = FakeGrid()
        self._sources, self._genres = [], []
        self.props, self.visible, self.loads = {}, {}, 0

    def setProperty(self, key, value):
        self.props[key] = value

    def getControl(self, cid):
        win = self

        class Chip:
            def setVisible(self, on):
                win.visible[cid] = on

            def setWidth(self, width):
                pass
        return Chip()

    def _browse_load_grid(self):
        self.loads += 1

    def _get_client(self):
        return FakeClient()

    def _discover_build_card(self, client, m):
        return m["title"]


for _name in ("BROWSE_WATCHED_OPTIONS_BASE", "BROWSE_QUALITY_OPTIONS", "BROWSE_YEAR_OPTIONS",
              "BROWSE_SORT_OPTIONS", "COLLECTION_ANSWERS", "ALL_GENRES", "GENRE_CHIP_IDS",
              "SORT_ID", "UNWATCHED_ID", "FILTER_ID",
              "_browse_watched_options", "_browse_quality_options", "_browse_collection_answerable",
              "_browse_unwatched_idx", "_browse_unwatched_clicked", "_browse_reset_filters",
              "_browse_render_collection_members", "_browse_sync_chips", "_browse_sort_glyph",
              "_browse_filter_label", "_browse_chip_width"):
    setattr(FakeWindow, _name, getattr(W, _name))

artcache.prefetch = lambda pairs, *a, **k: 0
library = FakeWindow(None)
inside = FakeWindow({"items": list(MEMBERS)})
values = lambda opts: [v for _label, v in opts]  # noqa: E731

check("a library still offers In Progress and Played",
      values(library._browse_watched_options()) == [None, "unwatched", "in_progress", "watched", "played"])
check("a collection offers All, Unwatched, Watched",
      values(inside._browse_watched_options()) == [None, "unwatched", "watched"])
check("a library still offers 1080p+", "hd1080" in values(library._browse_quality_options()))
check("a collection leaves 1080p+ out (a member only says 4K or not)",
      values(inside._browse_quality_options())
      == [None, "uhd4k", "uhd4k_hdr", "dolby_vision", "hdr", "atmos"])
check("the Unwatched chip still finds its option",
      inside._browse_watched_options()[inside._browse_unwatched_idx()][1] == "unwatched")

# --- and the grid follows the chosen options ----------------------------
inside._browse_render_collection_members()
check("unfiltered, every member is drawn", len(inside.grid_list.items) == len(MEMBERS))

inside._browse_watched_idx = inside._browse_unwatched_idx()
inside._browse_render_collection_members()
check("Unwatched draws only the unwatched members",
      inside.grid_list.items == ["hdr10", "sdr", "sdr4k"], str(inside.grid_list.items))

inside._browse_quality_idx = values(inside._browse_quality_options()).index("atmos")
inside._browse_render_collection_members()
check("Unwatched + Atmos draws their intersection",
      inside.grid_list.items == ["sdr4k"], str(inside.grid_list.items))

# --- a custom collection whose members never fill `watched` ------------
custom = FakeWindow({"items": [member("a", is_4k=True, rng="DV"), member("b", is_4k=False)]})
check("no member fills `watched`: Watch Status offers only All",
      values(custom._browse_watched_options()) == [None])
check("...nor Atmos when no member has an audio_format",
      values(custom._browse_quality_options()) == [None, "uhd4k", "uhd4k_hdr", "dolby_vision", "hdr"])
custom._browse_sync_chips()
check("...and the Unwatched chip is hidden",
      custom.visible.get(W.UNWATCHED_ID) is False and custom.visible.get(W.FILTER_ID) is True,
      str(custom.visible))
custom._browse_unwatched_clicked()
check("...and inert", custom._browse_watched_idx == 0 and custom.loads == 0)
inside._browse_sync_chips()
check("a collection that fills `watched` keeps the chip",
      inside.visible.get(W.UNWATCHED_ID) is True)

unowned = FakeWindow({"items": [UNOWNED]})
check("all unowned: Format offers only Any", values(unowned._browse_quality_options()) == [None])

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
