"""Universes (server 0.12.0) and the Continue the saga row, as the apps read them.

Run:  python3 test_universe.py
"""
import struct
import zlib

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import api, http, universe as U

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def movie(n, **kw):
    return dict(dict(type="movie", tmdb_id=n, title=f"Film {n}", year=2000 + n,
                     in_library=True, watched=False, local_media_id=f"m{n}",
                     backdrop_path=f"images/backdrops/{n}.jpg"), **kw)


def show(n, **kw):
    return dict(dict(type="tv", tmdb_id=n, title=f"Show {n}", in_library=True,
                     local_media_id=f"s{n}", episode_count=10, watched_episode_count=0,
                     unwatched_episode_count=10, next_episode={"season_number": 1,
                     "episode_number": 1}), **kw)


SAGA = {"id": "mcu", "kind": "curated", "name": "Saga", "backdrop_url": "u.jpg", "items": [
    movie(1, watched=True, chapter="Origins"),
    movie(2, watched=True, chapter="Origins"),
    movie(3, in_library=False, chapter="Assemble"),
    movie(4, chapter="Assemble", progress_percent=10),
    show(5, chapter="Assemble"),
    movie(6, upcoming=True, in_library=False, release_date="2027-05-01"),
]}
u = U.build(SAGA)
check("up next is the first held title not watched",
      u["next_up"]["item"]["tmdb_id"] == 4, str(u["next_up"]))
check("watched counts out of every member", U.card_line(u) == "2 of 6 watched", U.card_line(u))
check("a film up next reads 'position · title'", U.card_title(u) == "4 · Film 4", U.card_title(u))
check("chapters run in story order", u["chapters"] == [("Origins", 0, 1), ("Assemble", 2, 4)],
      str(u["chapters"]))
check("an upcoming title is neither held nor watched",
      u["members"][5]["state"] == "upcoming" and not u["members"][5]["owned"])
check("in progress, so it continues", U.continues(u))
check("the hero is the title up next, the art its backdrop",
      U.hero_item(u)["tmdb_id"] == 4 and U.card_art(u) == "images/backdrops/4.jpg")

series = U.build({"id": "t", "kind": "curated", "name": "Trek", "items": [
    movie(1, watched=True), show(2, watched_episode_count=3)]})
check("a show up next reads its episode", U.card_title(series) == "Show 2 S1 E1",
      U.card_title(series))
check("...and its episodes join the line",
      U.card_line(series) == "1 of 2 watched · 3 of 10 episodes", U.card_line(series))

fresh = U.build({"id": "f", "kind": "curated", "name": "New", "items": [movie(1), movie(2)]})
check("nothing watched yet: not on the row", not U.continues(fresh))
caught_up = U.build({"id": "c", "kind": "curated", "name": "Done", "items": [
    movie(1, watched=True), movie(2, upcoming=True, in_library=False, release_date="2099-12-18")]})
check("caught up with more to come: on the row",
      U.continues(caught_up) and U.card_title(caught_up).startswith("Up next: Film 2 · Coming ")
      and "18" in U.card_title(caught_up) and "2099" in U.card_title(caught_up),
      U.card_title(caught_up))
check("no backdrop on the title: the universe's",
      U.card_art(U.build({"id": "x", "kind": "curated", "name": "X", "backdrop_url": "u.jpg",
                          "items": [movie(1, watched=True), movie(2, backdrop_path=None)]})) == "u.jpg")


def pixels(png):
    """(width, height, rows of RGBA tuples) from our own unfiltered PNG."""
    width, height = struct.unpack(">II", png[16:24])
    raw = zlib.decompress(png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8])
    stride = 1 + 4 * width
    return width, height, [[tuple(raw[y * stride + 1 + 4 * x:y * stride + 5 + 4 * x])
                            for x in range(width)] for y in range(height)]


w, h, rows = pixels(U.strip_png(u, 120, 4))
seg = 120 // 6
check("one segment per member, white once watched", rows[0][5] == (255, 255, 255, 255))
check("a gap between segments", rows[0][seg - 1][3] == 0, str(rows[0][seg - 1]))
check("missing is faint, held is half-lit",
      rows[0][2 * seg + 5][3] == 28 and rows[0][4 * seg + 5][3] == 92)
check("up next is left out of the strip...", rows[0][3 * seg + 5][3] == 0)
_, _, nxt = pixels(U.strip_png(u, 120, 4, up_next=True))
check("...and drawn alone in white, for the accent to tint",
      nxt[0][3 * seg + 5] == (255, 255, 255, 255) and nxt[0][5][3] == 0)
_, _, round_rows = pixels(U.strip_png(u, 120, 4, radius=8))
check("rounded: the bottom corner is cut, past the curve is not",
      round_rows[3][0][3] == 0 and 0 < round_rows[3][5][3] < 255
      and round_rows[3][9][3] == 255, str(round_rows[3][:10]))
_, _, wide = pixels(U.strip_png(u, 1112, 1))
first = [p[3] for p in wide[0][:1112 // 6]]
check("gaps scale with the picture: 4px at the skin's 2x",
      first[-4:] == [0, 0, 0, 0] and first[-5] == 255, str(first[-6:]))


moved = U.build(dict(SAGA, items=[dict(i) for i in SAGA["items"]]))
moved["members"][3]["watched"], moved["members"][3]["state"] = True, "watched"
moved["next_up"] = moved["members"][4]
check("a strip's name follows what it shows: same state, same key",
      U.strip_key(u) == U.strip_key(U.build(SAGA)))
check("...a watched title or a new up next, a new one", U.strip_key(u) != U.strip_key(moved))


class FakeClient:
    def __init__(self, details, fail=()):
        self.details, self.fail, self.asked = details, set(fail), []

    def collections(self, curated=None):
        return {"collections": [{"id": cid, "kind": d.get("kind", "curated")}
                                for cid, d in self.details.items()]
                + [{"id": "123", "kind": "franchise"}]}

    def collection(self, cid):
        self.asked.append(cid)
        if cid in self.fail:
            raise http.ApiError(500, "boom", "boom")
        return self.details[cid]


client = FakeClient({"a": SAGA, "b": dict(SAGA, id="b", name="B"), "f": dict(
    {"id": "f", "kind": "curated", "name": "New", "items": [movie(1)]})}, fail=("b",))
got = U.continuing(client)
check("only curated collections are asked for", sorted(client.asked) == ["a", "b", "f"],
      str(client.asked))
check("the row keeps universes that continue, in the server's order, past a failure",
      [x["id"] for x in got] == ["mcu"], str([x["id"] for x in got]))

class Wire:
    def _get(self, path, params=None):
        self.sent = (path, params)


wire = Wire()
api.MediaServerClient.collections(wire, curated=True)
check("curated goes on the wire as `true`, the only spelling the server reads",
      wire.sent == ("/api/v1/collections", {"curated": "true"}), str(wire.sent))
api.MediaServerClient.collections(wire)
check("...and is left off when not asked", wire.sent[1] == {}, str(wire.sent))

check("a title is found by its library id",
      [m["key"] for m in U.entries(u, media_id="m4")] == [u["members"][3]["key"]])
check("...or by TMDB id and kind, a show matching tv/series alike",
      len(U.entries(u, tmdb_id=5, media_type="series")) == 1
      and not U.entries(u, tmdb_id=5, media_type="movie"))
U.forget()
calls = FakeClient({"a": SAGA})
U.everything(calls); U.everything(calls)
check("the universes are fetched once a minute, not per call", calls.asked == ["a"], str(calls.asked))
U.forget()
U.everything(calls)
check("...and again once forgotten", calls.asked == ["a", "a"], str(calls.asked))
U.forget()

from resources.lib.windows import universepage as P   # noqa: E402

check("Continue names the position and the title",
      P.play_label(u) == "Continue · 4 Film 4", P.play_label(u))
check("...or the show and its episode", P.play_label(series) == "Continue · Show 2 S1 E1",
      P.play_label(series))
check("caught up: no Continue pill", P.play_label(caught_up) == "")
check("nothing started yet: Play, as tofa's apps word it",
      P.play_label(fresh) == "Play · 1 Film 1", P.play_label(fresh))
check("the Universes tab's line counts every title",
      U.grid_line(u) == "4 of 6 in your library · 2 watched", U.grid_line(u))
_, _, dotted = pixels(U.dot_strip_png(u, 120, 4, 4, 4))
check("the Universes strip: a dot above up next, the strip under it",
      len(dotted) == 12 and dotted[1][3 * 20 + 9][3] > 0 and dotted[1][5][3] == 0
      and dotted[10][5] == (255, 255, 255, 255), str(dotted[1][60:72]))
check("release order says so", P.summary(u, P.RELEASE).startswith("6 titles in release order"),
      P.summary(u, P.RELEASE))
check("a poster's meta line: year and status",
      P.member_meta(u["members"][3], u["next_up"]["key"]) == "2004 · Up next, in progress",
      P.member_meta(u["members"][3], u["next_up"]["key"]))
long = " ".join(["word"] * 200)
cut = P.two_lines(long).split("[CR]")
check("a long overview is two lines, the second ending in an ellipsis",
      len(cut) == 2 and cut[1].endswith("\u2026"), str(cut))
check("a short one is left alone", P.two_lines("A short line.") == "A short line.")
blocks = P.grid_blocks(u, P.STORY)
check("the grid has a block per chapter, in story order",
      [(n, [m["position"] for m in ms]) for n, ms in blocks]
      == [("Origins", [1, 2]), ("Assemble", [3, 4, 5]), ("", [6])], str(blocks))
check("release order is one block", len(P.grid_blocks(u, P.RELEASE)) == 1)
check("a season says so in the grid",
      P.grid_status(dict(u["members"][4], item=dict(u["members"][4]["item"], season_number=1)),
                    None).startswith("Season 1 · "))
check("a pill with an icon is wider than its text by the pads and the icon",
      P.pill_width("Play", True) - P.pill_width("Play", False) == 56)

from resources.lib.skin import build   # noqa: E402

xml = """<control type="list" id="1">
    <onup condition="A">2</onup>
    <onup condition="!A">3</onup>
    <ondown>4</ondown>
</control>"""
out, _n = build._stop_wraps(xml, "test.xml")
check("the wrap stop leaves conditional-only targets alone",
      "<onup>" not in out and "<onleft>" in out and "<ondown>4</ondown>" in out, out)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
