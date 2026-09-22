"""Language pickers offer the server's curated list, as 6 asks.

The server serves 42 languages (metadata-options `languages`, Icelandic
included). The picker offers exactly those, written in the 639-2/T spelling
the other clients store, plus any saved code outside them -- so a preference
set elsewhere still shows.

Run:  python3 test_language_options_curated.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import settings_options as so

RESULTS = []
SERVED = ['en', 'fr', 'de', 'es', 'it', 'pt', 'nl', 'sv', 'no', 'da', 'fi', 'is', 'pl',
          'cs', 'sk', 'hu', 'ro', 'bg', 'el', 'tr', 'ru', 'uk', 'sr', 'hr', 'sl', 'et',
          'lv', 'lt', 'ja', 'ko', 'zh', 'hi', 'ta', 'te', 'ml', 'th', 'vi', 'id', 'ms',
          'ar', 'he', 'fa']


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def run():
    rows = so.language_options([], subtitles=False, served=SERVED)
    codes = [c for c, _n in rows]
    check("all 42 served languages are offered, audio too", len(rows) == 42, repr(len(rows)))
    check("Icelandic is among them, written isl", "isl" in codes, repr(codes[:5]))
    check("codes are written the way the other clients store them",
          "eng" in codes and "deu" in codes and "tam" in codes, repr(codes))
    names = [n.lower() for _c, n in rows]
    check("sorted by name", names == sorted(names))

    facet = [{"value": "gsw", "count": 3}, {"value": "ger", "count": 2880}]
    rows = so.language_options(facet, subtitles=True, served=SERVED)
    check("the library's own tags do not widen the shared list",
          "gsw" not in [c for c, _n in rows] and len(rows) == 42, repr(len(rows)))

    rows = so.language_options([], subtitles=True, served=SERVED, current=["xyz"])
    check("a saved code nobody knows is kept as a row", ("xyz" in [c for c, _n in rows]))

    rows = so.language_options([], subtitles=True, served=None)
    check("without the served list, subtitles fall back to the static nine", len(rows) == 9,
          repr(len(rows)))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("language pickers offer the curated list (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
