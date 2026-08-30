"""Snapping a MEASURED picture ratio to a projection ratio we can name.

The numbers in here are not invented: they are the real distribution probed
across 114 films and 60 TV titles in the library on 2026-08-30, and every
design decision below was taken from that measurement rather than from a
list of ratios someone remembered.

Run:  python3 test_aspect_snapping.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import badges

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# --- the shape of the rule --------------------------------------------
check("every named ratio snaps to itself",
      all(badges.aspect_badge(r) == "{0:.2f}:1".format(r)
          for r in badges.ASPECT_RATIOS))

# NEAREST, not first-within-tolerance. The +/-1% windows around 2.35 and 2.39
# overlap (they are 1.7% apart), so a first-match walk over a widest-first
# tuple would sweep the whole 2.34-2.36 cluster into 2.39.
check("2.36 goes to 2.35, not to 2.39", badges.aspect_badge(2.36) == "2.35:1",
      badges.aspect_badge(2.36))
check("2.376 goes to 2.39", badges.aspect_badge(2.376) == "2.39:1",
      badges.aspect_badge(2.376))

# 2.39 and 2.40 are ONE chip. 1920/2.39 = 803.3, so an encoder crops to 802 or
# 804 rows where 2.40 crops to 800: the difference is pixel rows of crop, not
# a fact about the film. The measured cluster runs 2.388..2.418 with no gap.
for measured in (2.388, 2.394, 2.400, 2.405):
    check(f"{measured} is scope, one chip", badges.aspect_badge(measured) == "2.39:1",
          badges.aspect_badge(measured))

# --- real values off the library --------------------------------------
REAL = {
    (3840, 1392): "2.76:1",   # 28 Years Later (2025)
    (1920, 752):  "2.55:1",   # 20,000 Leagues Under the Sea (1954)
    (1920, 802):  "2.39:1",   # '71
    (1920, 800):  "2.39:1",   # (500) Days of Summer
    (1920, 816):  "2.35:1",   # the pre-1970 scope cluster
    (3840, 1744): "2.20:1",   # 2001: A Space Odyssey
    (3840, 1928): "2.00:1",   # 20th Century Women
    (1920, 960):  "2.00:1",   # The Deal (2025), and 14% of TV
    (1920, 1036): "1.85:1",   # The 'Burbs
    (1920, 1080): "1.78:1",
    (1792, 1080): "1.66:1",   # 10 Rillington Place, pillarboxed not letterboxed
    (1480, 1080): "1.37:1",   # 3 Godfathers (1948), Academy proper
    (1440, 1080): "1.33:1",   # Murder, She Wrote
}
for (w, h), want in REAL.items():
    got = badges.aspect_from_active(w, h)
    check(f"{w}x{h} -> {want}", got == want, got or "(nothing)")

# --- what must stay silent --------------------------------------------
# Silence means "the probe found a shape we cannot name". Printing the raw
# measurement instead would dress a bad frame up as a fact about the film.
check("3-D Rarities, 1882x1080, is not named",
      badges.aspect_from_active(1882, 1080) == "",
      badges.aspect_from_active(1882, 1080))
check("16 Blocks, 1920x794, is not named",
      badges.aspect_from_active(1920, 794) == "",
      badges.aspect_from_active(1920, 794))
check("an unprobed file is silent", badges.aspect_from_active(None, None) == "")
check("a zero dimension is silent, not a division error",
      badges.aspect_from_active(1920, 0) == "")
check("nonsense is silent", badges.aspect_from_active("wide", "ish") == "")
check("a negative is silent", badges.aspect_badge(-2.39) == "")

# --- the notes ---------------------------------------------------------
# They name a RATIO, never a camera. 28 Years Later measures 2.759 and was shot
# on iPhones with anamorphic adapters, so the process name is only honest
# because the ASPECT RATIO eyebrow above it scopes what is being named.
check("every chip we can draw has a note",
      all(badges.aspect_note("{0:.2f}:1".format(r)) for r in badges.ASPECT_RATIOS))
check("the 2.76 note names the ratio, not the camera",
      badges.aspect_note("2.76:1") == "Ultra Panavision 70",
      badges.aspect_note("2.76:1"))
# The fact slot is a single 660px label with no wrap. Measured against the
# longest value known to render whole, so a future edit cannot quietly clip.
from resources.lib import textmetrics as _tm
_BUDGET = _tm.text_width("Marvel Studios, Kevin Feige Productions")
for _r in badges.ASPECT_RATIOS:
    _chip = "{0:.2f}:1".format(_r)
    _val = f"{_chip} \u00b7 {badges.aspect_note(_chip)}"
    check(f"the {_chip} fact value fits its slot",
          _tm.text_width(_val) <= _BUDGET, f"{_tm.text_width(_val)} > {_BUDGET}: {_val}")
check("no chip, no note", badges.aspect_note("") == "")
check("an unknown chip has no note", badges.aspect_note("1.19:1") == "")

# ~1.33 arrives at the same number down two unrelated roads, and only the
# media type tells them apart: a 1948 feature is Academy, a 1980s series is
# 4:3, and calling the latter Academy is wrong about the world.
check("a film at 1.37 is Academy",
      "Academy" in badges.aspect_note("1.37:1", "movie"))
check("a series at 1.33 is 4:3, not Academy",
      badges.aspect_note("1.33:1", "tv") == "4:3, television",
      badges.aspect_note("1.33:1", "tv"))
check("a film at 1.33 is still Academy",
      "Academy" in badges.aspect_note("1.33:1", "movie"))
check("media type changes nothing above 1.66",
      badges.aspect_note("2.39:1", "tv") == badges.aspect_note("2.39:1", "movie"))

print("\n" + "=" * 60)
bad = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(bad)}" if bad else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if bad else 0)
