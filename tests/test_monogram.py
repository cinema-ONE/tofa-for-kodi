"""A profile's monogram disc is the colour every other tofa client gives it.

The colour is not stored anywhere: each client derives it from the profile id.
So "correct" here does not mean "looks nice", it means "the same entry tofa
lands on" -- and the only way to hold that is to pin the palette, the hash and
real (id -> colour) pairs measured from tofa's own clients.

Where the vectors come from (2026-09-18): the palette and hash were read out of
tofa's web client; the result was then checked against their iPhone app, where
one profile's disc fits `#B68BFF -> #7B51D6` against entry 2 (worst channel
3/255), and against their Apple TV app, where three profiles wear the three
colours this table predicts from their ids -- green, teal, purple.

The four ids below are those four profiles, as the API sends them. They are
opaque and carry no names; they are the evidence, so they stay.

NOT to be confused with the profile's `avatar_color` field, which no tofa
client reads: every profile on that server carries the same value while the
apps draw four different colours.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import monogram  # noqa: E402

MEDIA = os.path.join(ROOT, "plugin.video.tofa", "resources", "skins",
                     "Main", "media")

#: (profile id, label for the failure message, expected index). Labelled
#: rather than named: this repo is public and a household's profile names are
#: not ours to publish -- the ids are opaque and carry the evidence by
#: themselves.
VECTORS = (
    ("6642dc5d-88df-47b3-8be1-af3c8191c894", "profile A", 5),
    ("4996287e-3245-41c7-865f-fba7bdf00d61", "profile B", 0),
    ("0768eb9d-ce77-45d9-9909-8e0e478f491d", "profile C", 6),
    ("18df279a-e25e-43c3-b604-46076fef55cd", "profile D", 2),
)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def main() -> int:
    # --- the measured pairs, which are the whole point
    for pid, name, want in VECTORS:
        got = monogram.index_for(pid)
        check("%s lands on entry %d" % (name, want), got == want, str(got))
    check("profile D is the purple one",
          monogram.PALETTE[monogram.index_for(VECTORS[3][0])]
          == ("#B98CFF", "#7A4FD6"))

    # --- the palette is a CONTRACT: the index comes from a hash, so reordering
    # these repaints every profile in every household.
    check("palette has 8 entries", len(monogram.PALETTE) == 8,
          str(len(monogram.PALETTE)))
    check("palette order is pinned", monogram.PALETTE == (
        ("#3FD0C9", "#1E9FB8"), ("#5C6BF2", "#2A2F66"),
        ("#B98CFF", "#7A4FD6"), ("#FFB24C", "#FF6B3D"),
        ("#FF7A8A", "#E03E63"), ("#54D98B", "#1F9E6A"),
        ("#48D6F0", "#1F86C8"), ("#7C83FF", "#4A53D6")))

    # --- nothing is normalised before hashing: a changed spelling is a
    # different colour, which is why ids are passed through untouched.
    pid = VECTORS[0][0]
    for variant, label in ((pid.upper(), "upper-cased"),
                           (pid.replace("-", ""), "hyphens stripped"),
                           (pid + " ", "trailing space")):
        check("%s hashes differently" % label,
              monogram._hash(variant) != monogram._hash(pid))

    # --- an astral character is a surrogate PAIR, as it is in JavaScript.
    # Getting this wrong only shows up on a profile named with an emoji, which
    # is exactly when nobody is looking.
    check("astral char counts as two code units",
          monogram._hash("\U0001F600") == monogram._hash("😀"))
    check("...and differs from the BMP char alone",
          monogram._hash("\U0001F600") != monogram._hash("\ud83d"))

    # --- an empty seed is their literal fallback, not entry 0 by accident
    check("empty seed falls back to 'tofa'",
          monogram.index_for("") == monogram.index_for("tofa"))
    check("...which is not simply entry 0",
          monogram.index_for("") == monogram._hash("tofa") % 8)

    # --- every texture the client can name must actually ship
    missing = [monogram.texture_for(pid) for pid, _n, _i in VECTORS
               if not os.path.exists(os.path.join(MEDIA, monogram.texture_for(pid)))]
    check("the four profiles' textures exist", not missing, str(missing))
    absent = [i for i in range(len(monogram.PALETTE))
              if not os.path.exists(os.path.join(MEDIA, "monogram-%d.png" % i))]
    check("all 8 discs are in media/", not absent, str(absent))

    # --- and the skin actually asks for them, in all three places
    def rendered(name):
        with open(os.path.join(ROOT, "plugin.video.tofa", "resources", "skins",
                               "Main", "1080i", name), encoding="utf-8") as fh:
            return fh.read()
    profile_xml = rendered("script-tofa-profile.xml")
    main_xml = rendered("script-tofa-main.xml")
    check("picker tiles draw the disc",
          profile_xml.count("ListItem.Property(monogram_texture)") == 10,
          str(profile_xml.count("ListItem.Property(monogram_texture)")))
    check("the PIN screen draws it too",
          "Window.Property(pin_avatar_monogram)" in profile_xml)
    check("the nav marker draws it",
          "Window.Property(nav_avatar_monogram)" in main_xml)
    check("the settings card draws it",
          "Window.Property(settings_avatar_monogram)" in main_xml)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("monogram: the disc matches what tofa's own clients draw (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
