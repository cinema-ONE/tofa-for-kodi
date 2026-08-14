"""Checks the Settings language picker's option list.

The bug this guards is a picker that offers the same language twice. On
0.9.29 `/media/facets` emits ISO 639-2/B and /T side by side -- this library
really does report `ger` 2880 AND `deu` 1828, `fre` 423 AND `fra` 144 -- so a
picker built straight off the facet lists German and French two ways each,
and picking "the wrong one" silently writes a spelling the other clients then
have to guess at.

The second bug is quieter: the facet is AUDIO languages, so building the
SUBTITLE picker from it alone withdraws choices the static list offers today.

Rows below are the real payload measured against the live server on
2026-08-13, trimmed to what each case needs.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

from lib import settings_options as so  # noqa: E402
from lib import langcodes as lc         # noqa: E402


# The head of the live facet, plus the tail entries that matter.
LIVE = [
    {"value": "eng", "count": 10877}, {"value": "ger", "count": 2880},
    {"value": "deu", "count": 1828}, {"value": "fre", "count": 423},
    {"value": "jpn", "count": 260}, {"value": "ita", "count": 254},
    {"value": "spa", "count": 164}, {"value": "fra", "count": 144},
    {"value": "zxx", "count": 49}, {"value": "mul", "count": 17},
    {"value": "de", "count": 5}, {"value": "en", "count": 5},
    {"value": "unknown", "count": 1},
]


RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r wanted %r" % (got, want)))


def main() -> int:

    folded = so.fold_language_facet(LIVE)
    codes = [code for code, _n, _c in folded]
    counts = {code: c for code, _n, c in folded}

    # --- the headline: one row per language, not one per spelling --------
    check("no duplicate languages", len(codes), len(set(codes)))
    check("German appears once",
          sum(1 for c in codes if lc.same(c, "ger")), 1)
    check("French appears once",
          sum(1 for c in codes if lc.same(c, "fre")), 1)

    # ger 2880 + deu 1828 + de 5. A picker that showed 2880 would be
    # under-reporting the library by a third.
    check("German counts summed", counts.get("deu"), 4713)
    check("French counts summed", counts.get("fra"), 567)
    check("English counts summed", counts.get("eng"), 10882)

    # --- the spelling we write is the one the web app writes -------------
    check("German is written /T", "deu" in codes, True)
    check("German is not written /B", "ger" in codes, False)
    check("French is written /T", "fra" in codes, True)

    # --- non-languages are not preferences -------------------------------
    for junk in ("zxx", "mul", "unknown"):
        check("%s is not offered" % junk,
              any(lc.same(c, junk) for c in codes), False)

    # --- ordered by what the library is mostly in ------------------------
    check("most-held language first", codes[0], "eng")
    check("second is German", codes[1], "deu")

    # --- names -----------------------------------------------------------
    names = {code: name for code, name, _c in folded}
    check("web app's name for German", names.get("deu"), "German")
    check("web app's name for French", names.get("fra"), "French")
    # No xbmc module in this harness, so an unnamed code must still degrade
    # to something pickable rather than raising.
    check("unknown code degrades to itself", so.language_name("qqq"), "QQQ")
    check("empty code is empty", so.language_name(""), "")

    # --- audio takes the facet alone -------------------------------------
    audio = so.language_options(LIVE, subtitles=False)
    acodes = [c for c, _n in audio]
    check("audio offers only what the library has audio in",
          sorted(acodes), sorted(codes))
    check("audio does not pad with the static list",
          any(lc.same(c, "ara") for c in acodes), False)

    # --- subtitles union the static list ---------------------------------
    subs = so.language_options(LIVE, subtitles=True)
    scodes = [c for c, _n in subs]
    check("subtitles keep a static language with no audio",
          any(lc.same(c, "ara") for c in scodes), True)
    check("subtitles still deduplicate German",
          sum(1 for c in scodes if lc.same(c, "ger")), 1)
    check("subtitles keep the facet's order at the front", scodes[0], "eng")

    # --- the fallbacks ---------------------------------------------------
    for label, rows in (("empty facet", []), ("None facet", None),
                        ("junk-only facet", [{"value": "zxx", "count": 9}])):
        got = [c for c, _n in so.language_options(rows, subtitles=False)]
        check("%s falls back to the static list" % label,
              got, [c for c, _n in so.LANGUAGES])

    # A row shape we have not seen, since this is fed straight from JSON.
    check("bare strings survive",
          [c for c, _n, _x in so.fold_language_facet(["eng", "ger"])],
          ["eng", "deu"])   # count 0 each, so the name breaks the tie:
                            # "English" before "German"

    # --- terminological() itself -----------------------------------------
    for b, t in (("ger", "deu"), ("fre", "fra"), ("dut", "nld"),
                 ("cze", "ces"), ("chi", "zho"), ("per", "fas")):
        check("%s -> %s" % (b, t), lc.terminological(b), t)
    check("a /T code is already /T", lc.terminological("deu"), "deu")
    check("a 639-1 code becomes /T", lc.terminological("de"), "deu")
    check("English has one form", lc.terminological("eng"), "eng")
    check("unknown is left alone", lc.terminological("qqq"), "qqq")

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("language picker: one row per language, from the library (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
