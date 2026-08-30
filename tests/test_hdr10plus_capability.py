"""HDR10+ is a capability, not just an allow-list entry.

Reported 2026-08-30 from the LibreELEC NUC, mid-episode of Lucky: the hero
said "Plays as ... HDR10+" on a panel that cannot do HDR10+.

Lucky is Dolby Vision profile 8.1 over an HDR10+ base. The NUC cannot do DV,
so dynamic_range_label correctly fell back to `base_layer_label` -- and then
stopped. Nothing asked whether the box could do the BASE either, so the
caveat row promised the one thing it exists to rule out.

What the NUC actually answers, read live over JSON-RPC while it was playing:

    System.SupportedHdrTypes        "HDR10, HLG"      <- no DV, no HDR10+
    videoplayer.allowedhdrformats   [0, 1]
    winsystem.ishdrdisplay          true

`allowedhdrformats` is an ALLOW-LIST, never a capability: it reads [0, 1] --
Dolby Vision and HDR10+ both permitted -- on a panel that supports neither.
Only SupportedHdrTypes answers what the display can do, which is why both
formats AND the two together.

The substring trap: "hdr10" is a prefix of "hdr10+", so a loose
`"hdr10" in types` is True on "HDR10, HLG" and would have promised dynamic
metadata on exactly the box that reported the bug. The test for HDR10+ has
to be for the literal "hdr10+".

The AM6B+ answers "HDR10, HLG, HDR10+, Dolby Vision" and must keep every
label it shows today -- this may not become a downgrade for boxes that are
genuinely capable.

Run:  python3 test_hdr10plus_capability.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# --- the real capability shapes, as the boxes report them ---------------
NUC = {"known": True, "hdr_capable": True, "dolby_vision": False,
       "hdr10_plus": False}
AM6B = {"known": True, "hdr_capable": True, "dolby_vision": True,
        "hdr10_plus": True}
NO_HDR = {"known": True, "hdr_capable": False, "dolby_vision": False,
          "hdr10_plus": False}
UNKNOWN = {"known": False, "hdr_capable": False, "dolby_vision": False,
           "hdr10_plus": False}

LUCKY = {"dynamic_range": "dolby_vision", "label": "Dolby Vision",
         "base_layer_label": "HDR10+"}
DV_OVER_HDR10 = {"dynamic_range": "dolby_vision", "label": "Dolby Vision",
                 "base_layer_label": "HDR10"}
PLAIN_HDR10_PLUS = {"dynamic_range": "hdr10_plus", "label": "HDR10+"}
PLAIN_HDR10 = {"dynamic_range": "hdr10", "label": "HDR10"}
SDR = {"dynamic_range": "sdr", "label": "SDR"}

drl = capabilities.dynamic_range_label

# --- the reported bug ---------------------------------------------------
check("Lucky on the NUC reads HDR10, not HDR10+",
      drl(LUCKY, NUC) == "HDR10", drl(LUCKY, NUC))
check("...and on the AM6B+ it keeps Dolby Vision",
      drl(LUCKY, AM6B) == "Dolby Vision", drl(LUCKY, AM6B))

# --- a plain HDR10+ file went past the check entirely before -------------
check("a plain HDR10+ file downgrades on the NUC",
      drl(PLAIN_HDR10_PLUS, NUC) == "HDR10", drl(PLAIN_HDR10_PLUS, NUC))
check("...and is untouched on a box that can do it",
      drl(PLAIN_HDR10_PLUS, AM6B) == "HDR10+", drl(PLAIN_HDR10_PLUS, AM6B))

# --- the DV path that already worked must not regress --------------------
check("DV over an HDR10 base still falls back to HDR10 on the NUC",
      drl(DV_OVER_HDR10, NUC) == "HDR10", drl(DV_OVER_HDR10, NUC))
check("DV over an HDR10 base is untouched on the AM6B+",
      drl(DV_OVER_HDR10, AM6B) == "Dolby Vision", drl(DV_OVER_HDR10, AM6B))

# --- things that must never change ---------------------------------------
check("a plain HDR10 file is untouched everywhere",
      drl(PLAIN_HDR10, NUC) == "HDR10" and drl(PLAIN_HDR10, AM6B) == "HDR10")
check("SDR is untouched", drl(SDR, NUC) == "SDR")
check("an empty format does not raise", drl({}, NUC) == "")
check("None does not raise", drl(None, NUC) == "")

# --- 'couldn't ask' keeps the file's own label ---------------------------
check("unknown caps keep Dolby Vision", drl(LUCKY, UNKNOWN) == "Dolby Vision")
check("unknown caps keep HDR10+", drl(PLAIN_HDR10_PLUS, UNKNOWN) == "HDR10+")

# --- a box with NO hdr path: plays_as says SDR for the whole row ---------
# dynamic_range_label must not invent "HDR10" there; the row-level SDR is
# the honest answer and it is applied by caveats(), not here.
check("no HDR path at all does not get an invented HDR10",
      drl(PLAIN_HDR10_PLUS, NO_HDR) == "HDR10+", drl(PLAIN_HDR10_PLUS, NO_HDR))

# --- the substring trap --------------------------------------------------
check('"hdr10" is a prefix of "hdr10+"', "HDR10, HLG".lower().find("hdr10") == 0)
check('...so a loose test would wrongly pass on the NUC',
      ("hdr10" in "HDR10, HLG".lower()) and not ("hdr10+" in "HDR10, HLG".lower()))

failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"all {len(RESULTS)} checks passed" if not failed
      else f"{len(failed)} of {len(RESULTS)} checks FAILED")
raise SystemExit(1 if failed else 0)
