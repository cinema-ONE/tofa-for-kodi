"""The region picker offers what the SERVER serves, and survives it not answering.

Until today this client shipped 27 regions copied out of the web app's bundle,
because vault #124 had checked `/regions`, `/media/regions` and
`/system/regions` and found nothing. The list was there the whole time, one
endpoint over: `GET /system/metadata-options` -> `regions`, 47 codes on
0.9.36. Every one of our 27 is in it; the 20 it adds are IS CZ SK HU RO GR TR
RU UA CN TW HK TH VN ID MY SG IL SA AE.

Two things have to hold for that switch to be an improvement rather than a
trade. The list must be ordered by NAME: the server groups its 47 by market,
which is meaningful to whoever curated it and invisible to someone holding a
remote, so the rows are sorted here instead (Adrian's call, 2026-09-18, after
seeing the served order on a TV). And a server that cannot answer must leave
the picker exactly as full as it was before -- sorted the same way, because a
fallback that is also a re-ordering is the kind of difference a viewer
notices and cannot explain.

The names stay ours either way: the endpoint sends bare codes, so an unnamed
region would otherwise be drawn at a viewer as "AE".
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import settings_options  # noqa: E402

#: The live response from server 0.9.36, in its own order.
SERVED = ["US", "GB", "CA", "AU", "NZ", "IE", "DE", "AT", "CH", "FR", "BE",
          "NL", "ES", "MX", "AR", "BR", "PT", "IT", "SE", "NO", "DK", "FI",
          "IS", "PL", "CZ", "SK", "HU", "RO", "GR", "TR", "RU", "UA", "JP",
          "KR", "CN", "TW", "HK", "IN", "TH", "VN", "ID", "MY", "SG", "IL",
          "SA", "AE", "ZA"]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def main() -> int:
    opts = settings_options.region_options

    served = opts(SERVED)
    check("all 47 offered", len(served) == 47, str(len(served)))
    names = [n for _c, n in served]
    check("sorted by NAME", names == sorted(names, key=str.lower), str(names[:6]))
    check("not the served order",
          [c for c, _n in served] != SERVED)
    check("first is Argentina, last is Vietnam",
          (served[0][1], served[-1][1]) == ("Argentina", "Vietnam"),
          str((served[0], served[-1])))
    check("same set as served, nothing lost",
          sorted(c for c, _n in served) == sorted(SERVED))

    names = dict(served)
    check("web-app name wins", names.get("US") == "United States", names.get("US"))
    check("switzerland named", names.get("CH") == "Switzerland", names.get("CH"))
    check("added region named", names.get("AE") == "United Arab Emirates", names.get("AE"))
    check("every served region has a NAME, not a code",
          all(n and n != c for c, n in served),
          str([c for c, n in served if not n or n == c]))

    # A failure or an empty answer must not empty the picker.
    for empty in ([], None, ()):
        fallback = opts(empty)
        check("%r falls back to the static list" % (empty,),
              sorted(c for c, _n in fallback)
              == sorted(c for c, _n in settings_options.REGIONS),
              str(len(fallback)))
        fb_names = [n for _c, n in fallback]
        check("%r fallback is sorted too" % (empty,),
              fb_names == sorted(fb_names, key=str.lower), str(fb_names[:4]))

    # The fallback must remain a strict subset, or switching lists would drop
    # a region a viewer may already have stored.
    check("static list is a subset of the served one",
          all(c in SERVED for c, _n in settings_options.REGIONS),
          str([c for c, _n in settings_options.REGIONS if c not in SERVED]))

    # Junk in the response is tolerated rather than rendered.
    messy = opts(["us", " gb ", "US", "", None, "ZZ"])
    check("cased and padded codes normalise",
          sorted(c for c, _n in messy) == ["GB", "US", "ZZ"], str(messy))
    # An unnamed code is offered in capitals; case-insensitive sorting files
    # it by its letters instead of ahead of every named region.
    check("an unnamed code sorts by its letters, not its case",
          [c for c, _n in messy] == ["GB", "US", "ZZ"], str(messy))
    check("an unknown code is offered as itself",
          dict(messy).get("ZZ") == "ZZ", str(dict(messy).get("ZZ")))

    # region_name is what the ROW under the picker reads.
    check("region_name knows an added one",
          settings_options.region_name("SG") == "Singapore",
          settings_options.region_name("SG"))
    check("region_name passes an unknown code through",
          settings_options.region_name("ZZ") == "ZZ")
    check("region_name of nothing is empty",
          settings_options.region_name("") == "")

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("regions: served list wins, static list catches a failure (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
