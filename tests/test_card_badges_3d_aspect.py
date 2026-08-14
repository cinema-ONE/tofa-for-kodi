"""Card chips for 3D and for projection ratio (server 0.9.28).

A card has three slots, so what goes in them is a ranking decision, not just
a mapping. 3D sits second because it is the most distinctive thing a poster
can say and because it changes whether the title is watchable at all on a 2D
setup. Aspect sits last and never for 16:9: "1.78:1" on nine cards in ten is
noise that would push a genuinely rare DTS:X chip off the card.

Run:  python3 test_card_badges_3d_aspect.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import badges

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")

def item(**fmt):
    return {"format": fmt}

# --- 3D ---------------------------------------------------------------
out = badges.card_badges(item(is_4k=True, video={"stereo_3d": "frame_packed"}))
check("3D is badged, right after 4K", out == ["4K", "3D"], str(out))
check("a 2D file gets no 3D chip",
      badges.card_badges(item(is_4k=True, video={"stereo_3d": None})) == ["4K"])
check("the chip says THAT it is 3D, not which layout",
      "3D" in badges.card_badges(item(video={"stereo_3d": "side_by_side"})))

# --- projection ratio -------------------------------------------------
check("scope gets a chip", badges.aspect_badge(2.39) == "2.39:1")
check("2.35 is its own chip", badges.aspect_badge(2.35) == "2.35:1")
check("academy gets a chip", badges.aspect_badge(1.33) == "1.33:1")
check("an unsnapped ratio gets nothing", badges.aspect_badge(2.30) == "",
      badges.aspect_badge(2.30))
check("missing gets nothing", badges.aspect_badge(None) == "")

out = badges.card_badges(item(is_4k=True, picture_aspect_ratio=2.39))
check("scope reaches the card", out == ["4K", "2.39:1"], str(out))
out = badges.card_badges(item(is_4k=True, picture_aspect_ratio=1.78))
check("16:9 is deliberately silent", out == ["4K"], str(out))

# --- the three slots are contested ------------------------------------
out = badges.card_badges(item(
    is_4k=True, video={"stereo_3d": "frame_packed", "dynamic_range": "dolby_vision"},
    audio={"short_label": "Atmos"}, picture_aspect_ratio=2.39))
check("a card still shows only three", len(out) == 3, str(out))
check("...and aspect is the one dropped", out == ["4K", "3D", "DV"], str(out))

# Every chip a card can emit must have art.
for label in ("3D", "2.39:1", "2.35:1", "1.85:1", "1.78:1", "1.66:1", "1.33:1"):
    check(f"{label} is in CARD_BADGES", label in badges.CARD_BADGES)

# --- channel_label after the title fallback came out ---------------------
# There used to be a third source between the layout and the count: the
# track's own title, parsed for "Surround 7.1". It existed for ONE file,
# Hugo's 4K remux, which reported channels 8 with channel_layout null.
# Server 0.9.28 populates that file (issue #7), and a sweep of 3080 audio
# tracks across 616 titles found zero whose label the parse still changed.
from resources.lib.tracks import channel_label

check("the probed layout wins", channel_label({"channel_layout": "7.1"}) == "7.1")
check("ffmpeg's parenthetical is dropped",
      channel_label({"channel_layout": "5.1(side)"}) == "5.1")
# The count is NOT dead code -- 43 of those 3080 still report no layout,
# PCM stereo tracks mostly.
check("no layout falls back to the count",
      channel_label({"channel_layout": None, "channels": 2}) == "Stereo")
check("...and an odd count stays a COUNT, never a guessed layout",
      channel_label({"channel_layout": None, "channels": 10}) == "10ch")
# The deliberate behaviour change: a title is no longer read. Nothing in the
# library hits this any more, and inventing "7.1" from prose was the part
# that had to go.
check("a layout in the TITLE is ignored now",
      channel_label({"channel_layout": None, "channels": 8,
                     "title": "Surround 7.1"}) == "8ch")
check("no data at all is empty, not a guess", channel_label({}) == "")

# --- the label builders, exercised WITH a title --------------------------
# The gap that shipped a NameError: `generic = not title or bool(RE.match(
# title))` short-circuits when the title is empty, so deleting RE broke only
# the tracks that HAVE a title -- and no test had one. The Options dialog
# stopped opening. Every check below passes a real title on purpose.
from resources.lib.tracks import audio_track_label, subtitle_track_label

label, detail = audio_track_label(
    {"language": "eng", "title": "Surround 7.1", "codec": "dts",
     "profile": "DTS-HD MA", "channel_layout": "7.1", "bit_depth": 24})
check("a title that just restates the layout is dropped",
      "7.1" not in label, label)
check("...and the detail column still carries it",
      detail == "DTS-HD MA \u00b7 7.1 \u00b7 24-bit", detail)

label, _ = audio_track_label(
    {"language": "eng", "title": "Audio Commentary by Jon Spira",
     "codec": "ac3", "channel_layout": "5.1(side)"})
check("a DESCRIPTIVE title is kept -- it is why the list exists",
      "Audio Commentary by Jon Spira" in label, label)

label, _ = audio_track_label({"language": "eng", "codec": "ac3",
                              "channels": 2})
check("no title at all still builds a label", bool(label), label)

# subtitle_track_label takes the same title path.
label, _ = subtitle_track_label(
    {"language": "tur", "title": "T\u00fcrk\u00e7e (Forced)", "forced": True})
check("the subtitle label builds with a title too", bool(label), label)
# Decided 2026-08-10: the doubling is correct by construction. The track's
# own title ends in "(Forced)" AND its forced flag is separately True, so
# the two have two different sources. Pinned so it is not "fixed" later.
check("...and the two (Forced)s are BOTH kept, on purpose",
      label.count("Forced") == 2, label)

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
