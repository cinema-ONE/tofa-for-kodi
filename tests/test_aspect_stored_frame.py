"""The aspect chip falls back to the STORED FRAME when the probe has not run.

Reported 2026-08-30: Lucky and Lioness showed no ratio on Detail while our own
stats overlay showed one. Detail read only `active_width`/`active_height`; the
overlay has always fallen back to `display_aspect_ratio`.

Both shows are stored already matted -- Lucky at 3840x1606 (2.39) and Lioness
at 3840x1920 (2.00) -- so the coded frame IS the picture and there is nothing
for the probe to discount. It had simply never run on them: 10.7% of the
library is unprobed, measured over all 49,672 files.

The fallback is guarded twice, and BOTH guards earn their place from the sweep:

  square pixels     `resolution` must agree with `display_aspect_ratio`.
                    Doctor Who (1963) stores 704x528 (1.333 coded) with a
                    display ratio of 1.36-1.38 where the picture is really
                    1.33 -- anamorphic, and the display ratio there is a PAR
                    calculation, not a measurement.

  not a container   1.78 is the true picture only 54.5% of the time across
                    39,989 probed files; 1.33 is 96.1% across 3,849. A 2.39
                    film in a 16:9 remux reports 1.78, which is the exact
                    error the probe exists to correct.

WHAT THIS IS NOT. It is inference. Every probed file in the library has a
container-shaped display ratio and every scope-shaped one is unprobed, so the
populations do not overlap and there is no labelled case to score the rule
against. Sibling episodes do not stand in: Away stores 3840x1744 -- exactly
its 2.20 -- next to a sibling that probes 2.39, so the show changes shape and
the disagreement is not the rule's fault.

Run:  python3 test_aspect_stored_frame.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import badges

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def f(resolution, dar, aw=None, ah=None):
    return {"resolution": resolution, "display_aspect_ratio": dar,
            "active_width": aw, "active_height": ah}


# --- the two reported titles ------------------------------------------
lucky = f("3840x1606", 2.391033623910336)
lioness = f("3840x1920", 2.0)
check("Lucky, stored matted at 2.39, gets its chip",
      badges.aspect_from_file(lucky) == "2.39:1", badges.aspect_from_file(lucky))
check("Lioness is 2.00, NOT 2.39",
      badges.aspect_from_file(lioness) == "2.00:1", badges.aspect_from_file(lioness))

# --- the probe still wins whenever it has run -------------------------
# Lioness's own two full-frame files: 3840x2160 coded, picture 3840x1920.
# The display ratio LIES here (1.778); the probe must take precedence.
probed = f("3840x2160", 1.778, aw=3840, ah=1920)
check("a probed file uses the probe, not the stored frame",
      badges.aspect_from_file(probed) == "2.00:1", badges.aspect_from_file(probed))
check("...and the stored frame alone would have said 1.78",
      badges.aspect_badge(1.778) == "1.78:1")

# --- guard 1: container shapes are the box, not the picture -----------
for res, dar, why in (("1920x1080", 1.778, "16:9 remux"),
                      ("3840x2160", 1.778, "4K 16:9 remux"),
                      ("640x480", 1.333, "4:3 box")):
    check(f"no chip from a container shape ({why})",
          badges.aspect_from_file(f(res, dar)) == "",
          repr(badges.aspect_from_file(f(res, dar))))

# --- guard 2: anamorphic files are not ours to name -------------------
who = f("704x528", 1.382)
check("anamorphic 4:3 (Doctor Who 704x528 @ 1.382) gets nothing",
      badges.aspect_from_file(who) == "", badges.aspect_from_file(who))
check("...because the coded frame disagrees with the display ratio",
      abs(704 / 528 - 1.382) / 1.382 > badges.ASPECT_TOLERANCE)

# --- the shapes the fallback actually adds ----------------------------
for res, dar, want in (("3840x1920", 2.0, "2.00:1"),
                       ("3840x1606", 2.391, "2.39:1"),
                       ("3840x1744", 2.2018, "2.20:1"),
                       ("1920x1038", 1.85, "1.85:1"),
                       ("1920x816", 2.3529, "2.35:1")):
    got = badges.aspect_from_file(f(res, dar))
    check(f"{res} at {dar} -> {want}", got == want, got)

# --- junk in, silence out ---------------------------------------------
for bad in (f(None, None), f("", 2.39), f("3840x1606", None),
            f("notaresolution", 2.39), f("3840x0", 2.39), f("3840x1606", 0)):
    check(f"no chip and no raise from {bad['resolution']!r}/{bad['display_aspect_ratio']!r}",
          badges.aspect_from_file(bad) == "")

# --- an unnameable shape stays silent ---------------------------------
check("a shape we cannot name gets nothing, not a raw number",
      badges.aspect_from_file(f("1000x437", 2.288)) == "",
      badges.aspect_from_file(f("1000x437", 2.288)))

failed = [n for n, ok in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"all {len(RESULTS)} checks passed" if not failed
      else f"{len(failed)} of {len(RESULTS)} checks FAILED")
raise SystemExit(1 if failed else 0)
