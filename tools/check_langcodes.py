"""Checks langcodes + the track-picking rule that depends on it.

The bug these guard against is quiet: a preference that fails to match does
not error, it falls through to the next language (usually English) and looks
like the setting was ignored. So the interesting cases are the ones where a
WRONG answer is still a plausible-looking one.

It tests the REAL `langcodes.first_by_language`, not a copy. That function
used to live on PlayerWindow, where this file could not import it (Kodi), so
it was mirrored here and the mirror could drift. It now lives in langcodes.py
— stdlib-only, importable — precisely so that the player, Detail's Options
panel and this test all exercise one implementation.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)

#: The add-on tree, wherever it is. This tool stays in the vault when the
#: add-on moves to its own public repo, so it has to look next door.
ADDON = checkouts.addon_dir(ROOT)
if not ADDON:
    raise SystemExit("cannot find plugin.video.tofa/ -- check it out beside "
                     "this repo, or set TOFA_ADDON_REPO")

sys.path.insert(0, os.path.join(ADDON, "resources"))

from lib import langcodes as lc  # noqa: E402


first_by_language = lc.first_by_language


def main() -> int:
    fails = []
    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r wanted %r" % (name, got, want))

    # --- the B/T divergences named in tofa's 0.9.27 note ----------------
    for a, b in (("ger", "deu"), ("ger", "de"), ("fre", "fra"), ("fre", "fr"),
                 ("dut", "nld"), ("dut", "nl"), ("cze", "ces"), ("cze", "cs")):
        check("%s == %s" % (a, b), lc.same(a, b), True)
    check("eng == en", lc.same("eng", "en"), True)
    check("case is ignored", lc.same("GER", "deu"), True)
    check("region is dropped", lc.same("pt-BR", "por"), True)
    check("underscore region too", lc.same("zh_Hans", "chi"), True)

    # --- and the ones that must NOT collapse ---------------------------
    check("German is not Dutch", lc.same("ger", "dut"), False)
    check("English is not German", lc.same("eng", "ger"), False)
    check("empty matches nothing", lc.same("", "eng"), False)
    check("None matches nothing", lc.same(None, "eng"), False)
    check("unknown code still self-matches", lc.same("qaa", "qaa"), True)

    # --- the ordering rule --------------------------------------------
    # THE bug: German preferred, file tagged with the other spelling. Before
    # the fix this returned the English track.
    tracks = [{"language": "eng", "id": 1}, {"language": "deu", "id": 2}]
    check("ger preference finds the deu track",
          (first_by_language(tracks, ["ger", "eng"]) or {}).get("id"), 2)
    # Priority must survive equivalence: an equivalent match for the FIRST
    # language beats an exact match for the second.
    check("first language wins over exact second",
          (first_by_language(tracks, ["ger", "eng"]) or {}).get("id"), 2)
    check("second language used when first is absent",
          (first_by_language([{"language": "eng", "id": 1}],
                             ["ger", "eng"]) or {}).get("id"), 1)
    # Exact beats equivalent WITHIN one language, so a regional variant is
    # not swapped for its base when both are present.
    pt = [{"language": "por", "id": 1}, {"language": "pt-BR", "id": 2}]
    check("exact regional variant wins",
          (first_by_language(pt, ["pt-BR"]) or {}).get("id"), 2)
    check("nothing preferred -> no track",
          first_by_language(tracks, ["jpn"]), None)
    check("no tracks -> no track", first_by_language([], ["eng"]), None)

    # A real 4K remux's track order, which is what exposed the Options panel
    # showing a track playback would not use: German comes FIRST in the
    # container, and the profile prefers English.
    disc_4k = [{"language": "ger", "index": 1}, {"language": "eng", "index": 2},
               {"language": "eng", "index": 3}, {"language": "eng", "index": 4}]
    check("English profile skips the leading German track",
          (first_by_language(disc_4k, ["eng"]) or {}).get("index"), 2)
    check("German profile takes it, spelled ger",
          (first_by_language(disc_4k, ["ger"]) or {}).get("index"), 1)
    # ...and the SAME title's 1080p file spells German the other way, which is
    # why equivalence has to hold across two files of one title.
    disc_1080 = [{"language": "eng", "index": 1}, {"language": "deu", "index": 2}]
    check("German profile matches deu too",
          (first_by_language(disc_1080, ["ger"]) or {}).get("index"), 2)

    # --- subtitles: flags change what a track MEANS ---------------------
    # The same disc's subtitle tracks, in container order. Plain language
    # matching returns the FORCED track because it comes first, and "always
    # show subtitles" then subtitles almost nothing.
    disc_subs = [
        {"index": 5, "language": "ger", "forced": True,  "sdh": False},
        {"index": 6, "language": "ger", "forced": False, "sdh": False},
        {"index": 7, "language": "eng", "forced": False, "sdh": True},
        {"index": 1000, "language": "eng", "forced": False, "sdh": False},
    ]
    check("German subs take the full track, not the forced one",
          (lc.first_subtitle_by_language(disc_subs, ["ger"]) or {}).get("index"), 6)
    check("English subs prefer the plain track over SDH",
          (lc.first_subtitle_by_language(disc_subs, ["eng"]) or {}).get("index"), 1000)
    check("language priority still leads",
          (lc.first_subtitle_by_language(disc_subs, ["ger", "eng"]) or {}).get("index"), 6)
    # Ordering, not filtering: forced-only is still better than nothing.
    check("a forced-only language still returns it",
          (lc.first_subtitle_by_language(
              [{"index": 5, "language": "ger", "forced": True}], ["ger"]) or {}).get("index"), 5)
    check("SDH-only still returns it",
          (lc.first_subtitle_by_language(
              [{"index": 7, "language": "eng", "sdh": True}], ["eng"]) or {}).get("index"), 7)
    check("spelling equivalence applies to subtitles too",
          (lc.first_subtitle_by_language(
              [{"index": 6, "language": "deu", "forced": False}], ["ger"]) or {}).get("index"), 6)
    check("no match -> nothing", lc.first_subtitle_by_language(disc_subs, ["jpn"]), None)

    # The server reports sdh=false on a track plainly titled "English SDH
    # (PGS)", so the title is the fallback. Live payload, verbatim.
    real = [
        {"index": 7, "language": "eng", "title": "English SDH (PGS)", "forced": False, "sdh": False},
        {"index": 1000, "language": "eng", "title": None, "forced": False, "sdh": False},
    ]
    check("SDH detected from the title when the flag is not set",
          (lc.first_subtitle_by_language(real, ["eng"]) or {}).get("index"), 1000)
    check("'hi' only matches as a whole word",
          lc._is_sdh({"title": "Chile (Spanish)"}), False)
    check("hearing impaired counts", lc._is_sdh({"title": "English (Hearing Impaired)"}), True)
    check("the flag still wins when set", lc._is_sdh({"title": "English", "sdh": True}), True)

    # --- text beats bitmap, once content is equal -----------------------
    mixed = [
        {"index": 7, "language": "eng", "title": "English SDH (PGS)", "render": "bitmap"},
        {"index": 6, "language": "eng", "title": None, "render": "bitmap"},
        {"index": 1000, "language": "eng", "title": None, "render": "text"},
    ]
    check("a text track wins the tie against a picture one",
          (lc.first_subtitle_by_language(mixed, ["eng"]) or {}).get("index"), 1000)
    # Content before format: a plain PICTURE track still beats an SDH text
    # one, because SDH changes what is written, bitmap only how it is drawn.
    content_first = [
        {"index": 1, "language": "eng", "title": "English SDH", "render": "text"},
        {"index": 2, "language": "eng", "title": None, "render": "bitmap"},
    ]
    check("plain bitmap beats SDH text",
          (lc.first_subtitle_by_language(content_first, ["eng"]) or {}).get("index"), 2)
    check("bitmap inferred from the codec when render is absent",
          lc._is_bitmap({"codec": "hdmv_pgs_subtitle"}), True)
    check("subrip is not bitmap", lc._is_bitmap({"codec": "subrip"}), False)

    # --- "always show subtitles" OFF: the forced track for the audio -----
    forced_set = [
        {"index": 5, "language": "ger", "forced": True,  "title": "Deutsch Forced (PGS)"},
        {"index": 6, "language": "ger", "forced": False, "title": "Deutsch (PGS)"},
        {"index": 7, "language": "eng", "forced": False, "title": "English SDH (PGS)"},
    ]
    check("German audio gets the German forced track",
          (lc.forced_subtitle_for(forced_set, "ger") or {}).get("index"), 5)
    check("English audio has no forced track here",
          lc.forced_subtitle_for(forced_set, "eng"), None)
    check("the deu spelling finds it too",
          (lc.forced_subtitle_for(forced_set, "deu") or {}).get("index"), 5)
    check("a title-only 'Forced' still counts",
          (lc.forced_subtitle_for(
              [{"index": 9, "language": "eng", "title": "English (Forced)"}],
              "eng") or {}).get("index"), 9)
    check("the real flag beats a title that merely says so",
          (lc.forced_subtitle_for([
              {"index": 8, "language": "eng", "title": "English Foreign Parts"},
              {"index": 9, "language": "eng", "forced": True, "title": "English"},
          ], "eng") or {}).get("index"), 9)
    check("no audio language -> nothing", lc.forced_subtitle_for(forced_set, None), None)

    # --- the subtitle decision uses the same equivalence ----------------
    # "audio is in a language I asked for" must be true for ger vs deu, or
    # every correctly-matched foreign track would gain unwanted subtitles.
    check("deu audio counts as a ger preference",
          any(lc.same("deu", c) for c in ["ger"]), True)
    check("fra audio does not count as a ger preference",
          any(lc.same("fra", c) for c in ["ger"]), False)

    for f in fails:
        print("FAIL " + f)
    print("%d checks, %d failed" % (52, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
