"""The paired stats panel: source on the left, what this box did on the right.

Values here are REAL readings taken from the two platforms on 2026-08-08, so
a change that breaks the box shows up as a failing test rather than as a
panel full of em dashes on the one machine that matters.

Run:  python3 test_playerstats.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import playerstats as ps

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def with_label(value):
    """Point _screen() at a given System.ScreenResolution reading."""
    ps._label = lambda name: value if name == "System.ScreenResolution" else ""


# ---- _screen: one generic label carries resolution AND refresh -------------
_real_label = ps._label

with_label("3840x2160 @ 25.00 Hz - Full screen")        # measured on the box
check("box: resolution parsed", ps._screen()[0] == "3840×2160", ps._screen()[0])
check("box: refresh parsed", ps._screen()[1] == "25 Hz", ps._screen()[1])

with_label("1920x1080 - Windowed")                       # measured on the Mac
check("windowed: resolution parsed", ps._screen()[0] == "1920×1080", ps._screen()[0])
check("windowed: no refresh claimed", ps._screen()[1] == "", repr(ps._screen()[1]))

with_label("")
check("no reading at all is not a crash", ps._screen() == ("", ""))
ps._label = _real_label

# ---- _judders: only UNEVEN pulldown earns amber ---------------------------
check("25 fps at 25 Hz is clean", not ps._judders(25, "25 Hz"))
check("25 fps at 50 Hz is clean (every frame twice)", not ps._judders(25, "50 Hz"))
check("24 fps at 48 Hz is clean", not ps._judders(24, "48 Hz"))
check("23.976 at 24 Hz is clean (within tolerance)", not ps._judders(23.976, "24 Hz"))
check("23.976 at 59.94 Hz JUDDERS (2.5x)", ps._judders(23.976, "59.94 Hz"))
check("24 fps at 60 Hz JUDDERS (2.5x)", ps._judders(24, "60 Hz"))
check("50 fps at 25 Hz JUDDERS (display too slow)", ps._judders(50, "25 Hz"))
check("no refresh reading never judders", not ps._judders(23.976, ""))
check("no fps reading never judders", not ps._judders(None, "60 Hz"))

# ---- upscaling is NOT flagged --------------------------------------------
# 1080p on a 4K panel is the single most common difference on the box, and
# colouring it would train the eye straight past the rows that matter.
check("resolution differing is not a judder concern", not ps._judders(25, "25 Hz"))

# ---- _channel_count / downmix --------------------------------------------
check("5.1 counts six channels",
      ps._channel_count("FL, FR, FC, LFE, SL, SR") == 6)
check("stereo counts two", ps._channel_count("FL, FR") == 2)
check("nothing counts zero", ps._channel_count("") == 0)
check("box case: 5.1 source into a stereo sink is a downmix",
      ps._channel_count("FL, FR") < ps._channel_count("FL, FR, FC, LFE, SL, SR"))
check("stereo into stereo is NOT a downmix",
      not ps._channel_count("FL, FR") < ps._channel_count("FL, FR"))

# ---- passthrough is NOT a downmix ----------------------------------------
# Measured on the box: a 5.1 E-AC-3 Atmos track bitstreamed to the AVR
# reports six source channels against a two-channel sink. That is Kodi
# describing a PCM sink it is not using, not a downmix, and flagging it
# would tell the viewer their Atmos had been crushed to stereo.
BOX_5_1 = "FL, FR, FC, LFE, BL, BR"
BOX_SINK = "FL, FR"

def downmixed(source_count, sink, decoder):
    passthrough = decoder.lower().startswith(ps._PASSTHROUGH_PREFIX)
    return bool(not passthrough and sink and source_count
                and ps._channel_count(sink) < source_count)

check("the box's Atmos passthrough is NOT called a downmix",
      not downmixed(ps._channel_count(BOX_5_1), BOX_SINK, "pt-eac3"))
check("the same channels DECODED here IS a downmix",
      downmixed(ps._channel_count(BOX_5_1), BOX_SINK, "ff-eac3"))
check("stereo decoded to stereo is not a downmix",
      not downmixed(2, "FL, FR", "ff-eac3"))
check("no sink reading is not a downmix",
      not downmixed(ps._channel_count(BOX_5_1), "", "ff-eac3"))

# ---- passthrough inflates the engine's layout to the IEC carrier ----------
# REAL readings, 2026-08-17, ONE DTS-HD MA 5.1 film played on both machines.
# The box bitstreams it, and the audio engine then describes the 8-channel
# IEC 61937 frame the bitstream rides inside rather than the programme; the
# Mac decodes the same file and reports the true six. Nothing is upmixing
# anything. `VideoPlayer.AudioChannels` is the demuxer's count for the stream
# actually playing and says 6 on BOTH, which is why the source cell reads it.
# Reported from the box as "it says 7.1 and the film is 5.1".
BOX_PT_LAYOUT = "FL, FR, FC, LFE, BL, BR, SL, SR"     # pt-dtshd, 8 names
MAC_DEC_LAYOUT = "FL, FR, FC, LFE, SL, SR"            # ff-dca, 6 names

check("box passthrough: a 5.1 film does NOT read 7.1",
      ps._source_channels(BOX_PT_LAYOUT, 6, True) == "5.1",
      ps._source_channels(BOX_PT_LAYOUT, 6, True))
check("box passthrough: the carrier's speaker names are not printed",
      "SL" not in ps._source_channels(BOX_PT_LAYOUT, 6, True))
check("decoded here: the speaker list survives",
      ps._source_channels(MAC_DEC_LAYOUT, 6, False)
      == "5.1 (FL, FR, FC, LFE, SL, SR)",
      ps._source_channels(MAC_DEC_LAYOUT, 6, False))
check("a real 7.1 track passed through still reads 7.1",
      ps._source_channels(BOX_PT_LAYOUT, 8, True) == "7.1",
      ps._source_channels(BOX_PT_LAYOUT, 8, True))
check("stereo passed through reads stereo",
      ps._source_channels("FL, FR", 2, True) == "Stereo")
check("a count with no named tier still says something",
      ps._source_channels("", 5, True) == "5ch",
      ps._source_channels("", 5, True))
# No demuxer count: the engine is all there is. Honest while decoding, and
# describing the carrier while passing through.
check("no count, decoding: the engine's layout is used",
      ps._source_channels(MAC_DEC_LAYOUT, 0, False)
      == "5.1 (FL, FR, FC, LFE, SL, SR)")
check("no count, passthrough: an em dash beats the carrier's 7.1",
      ps._source_channels(BOX_PT_LAYOUT, 0, True) == ps.MISSING,
      ps._source_channels(BOX_PT_LAYOUT, 0, True))
# A layout disagreeing with the demuxer describes something else, so its
# names must not be hung off the demuxer's count.
check("layout disagreeing with the count loses its names",
      ps._source_channels(BOX_PT_LAYOUT, 6, False) == "5.1",
      ps._source_channels(BOX_PT_LAYOUT, 6, False))

# ---- _prune_pairs ---------------------------------------------------------
H = ("VIDEO", None)
rows = ps._prune_pairs([
    H,
    ps._pair("Resolution", "1920×1080", "3840×2160"),
    ps._pair("Ghost", "", "", ps.PLATFORM),          # nothing on either side
    ("EMPTY", None),                                  # heading with no rows
])
keys = [r[0] for r in rows]
check("a PLATFORM row with both sides empty is dropped", "Ghost" not in keys, str(keys))
check("a heading left with no rows is dropped", "EMPTY" not in keys, str(keys))
check("a real row survives", "Resolution" in keys, str(keys))

# One-sidedness is NORMAL here and must not be mistaken for absence.
rows = ps._prune_pairs([
    H,
    ps._pair("Container", "mkv", "", ps.PLATFORM),   # DELIVERY has no output
    ps._pair("Buffer", "", "99%", ps.PLATFORM),      # SYSTEM has no source
])
keys = [r[0] for r in rows]
check("a source-only PLATFORM row is kept", "Container" in keys, str(keys))
check("an output-only PLATFORM row is kept", "Buffer" in keys, str(keys))

# ---- the row tuple the skin depends on ------------------------------------
row = ps._pair("Frame rate", "23.976 fps", "59.94 Hz", warn=True)
check("a row carries key, source, output, kind, warn", len(row) == 5, str(row))
check("warn rides on the row", row[4] is True)
check("a heading is still a 2-tuple", len(H) == 2)


# ---- Picture aspect: the server's alone -----------------------------------
# `picture_aspect_ratio` is the ACTIVE image with any baked-in matte
# discounted, so a 2.39 film in a 1.78 container reads 2.39 from the server
# and 1.78 from the box. Kodi cannot derive it; it sees the coded rectangle.
check("scope reads 2.39:1", ps._aspect(2.39) == "2.39:1", ps._aspect(2.39))
check("16:9 rounds to 1.78:1", ps._aspect(1.7777) == "1.78:1", ps._aspect(1.7777))
check("flat reads 1.85:1", ps._aspect(1.85) == "1.85:1", ps._aspect(1.85))
check("a missing ratio is blank, not 0.00:1", ps._aspect(None) == "")
check("a zero ratio is blank", ps._aspect(0) == "")
check("a string ratio still parses", ps._aspect("2.39") == "2.39:1")

# ...and the decimal mark is the REGION's, not a point. Every check above
# passes in a point region whether or not that is true, so on their own they
# would go on passing the day a hardcoded "%.2f" came back. `_region()`
# answers (thousands, grouping, decimal) and caches it in `_cached`.
from resources.lib import regional  # noqa: E402

_was = regional._cached
try:
    regional._cached = (".", (3,), ",")
    check("a comma region writes 2,39:1", ps._aspect(2.39) == "2,39:1",
          ps._aspect(2.39))
    check("...and rounds there too", ps._aspect(1.7777) == "1,78:1",
          ps._aspect(1.7777))
    check("blank stays blank whatever the region", ps._aspect(0) == "")
    regional._cached = ("'", (3,), ".")
    check("a point region with another thousands mark is unaffected",
          ps._aspect(2.39) == "2.39:1", ps._aspect(2.39))
finally:
    regional._cached = _was

# ---- the Channels ROW, wired end to end -----------------------------------
# The checks above pin _source_channels; this one pins that the panel
# actually CALLS it. Unwiring it -- putting Player.Process(audiochannels)
# back in the source cell -- leaves every check above green while the box
# goes on saying 7.1, which is exactly how this shipped.
#
# Every reading below was taken off the two machines on 2026-08-17 during
# the same DTS-HD MA 5.1 film.
BOX_LABELS = {
    "Player.Process(audiodecoder)": "pt-dtshd",
    "Player.Process(audiochannels)": BOX_PT_LAYOUT,
    "Player.Process(audiochannelssink)": BOX_PT_LAYOUT,
    "VideoPlayer.AudioChannels": "6",
    "VideoPlayer.AudioCodec": "dtshd_ma",
    "Player.Process(audiosamplerate)": "48,000",
    "VideoPlayer.AudioBitrate": "3166",
}
MAC_LABELS = {
    "Player.Process(audiodecoder)": "ff-dca",
    "Player.Process(audiochannels)": MAC_DEC_LAYOUT,
    "Player.Process(audiochannelssink)": "",
    "VideoPlayer.AudioChannels": "6",
    "VideoPlayer.AudioCodec": "dtshd_ma",
    "Player.Process(audiosamplerate)": "48,000",
}
NEGO = {"play_method": "DirectPlay", "decision_mode": "direct",
        "audio_codec": "dts", "video_codec": "h264"}


def channels_row(labels):
    """(source, output) of the AUDIO Channels row, as the panel builds it."""
    was = ps._label
    ps._label = lambda name: labels.get(name, "")
    try:
        for row in ps.rows(NEGO, None, "00:10:00"):
            if len(row) == 5 and row[0] == "Channels":
                return row[1], row[2]
    finally:
        ps._label = was
    return None, None


src, out = channels_row(BOX_LABELS)
check("box row: the source cell says 5.1, not 7.1", src == "5.1", repr(src))
check("box row: the sink cell stays an em dash under passthrough",
      out == ps.MISSING, repr(out))

src, out = channels_row(MAC_LABELS)
check("mac row: 5.1 with its speaker list",
      src == "5.1 (FL, FR, FC, LFE, SL, SR)", repr(src))
check("mac row: no sink reading is an em dash", out == ps.MISSING, repr(out))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
