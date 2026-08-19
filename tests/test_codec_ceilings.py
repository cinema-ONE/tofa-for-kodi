"""The AV1 source-height ceiling (`codec_ceilings`, server 0.9.32).

`direct_play_video_codecs` promises `av1` unconditionally, on every box the
add-on runs on. On AM6B-BOX (CoreELEC 21.3, Amlogic, kernel 4.9) that promise
is kept in SOFTWARE -- measured 2026-08-19, `Player.Process(videodecoder)` on
a 1080p30 AV1 mp4 reads `ff-libdav1d`, there being no `am-av1` on that
silicon. It holds at 1080p. At 4K it would not, and the way it fails is a
stutter rather than an error: the source is direct-played because we said we
could take it, where declining would have got a transcode that plays.

Dropping `av1` from the direct-play list would be worse -- it would force a
transcode on every file that box handles perfectly well. A ceiling is the
instrument that separates the two cases.

The trap this file guards is generalising. "Amlogic has no AV1 decoder" is
FALSE: Kodi's own `am-av1` path exists (DVDVideoCodecAmlogic.cpp:269-275) and
is gated per platform on /sys/class/amstream/vcodec_profile. So the ceiling is
a READING of that file, and every box that cannot answer -- which is every
non-Amlogic platform, several of which have hardware AV1 -- must come away
with no ceiling at all rather than with this box's answer.

Run:  python3 test_codec_ceilings.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities
from resources.lib.profile import CapabilityProfile

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


#: Shaped after what Kodi's regex expects to find: one row per codec, the
#: hardware ones carrying a "compressed" capability. Kodi confines a match to
#: a single row by `.` not crossing a newline, so these must stay one-per-line.
WITH_AV1 = (
    "h264:4k;\n"
    "hevc:4k,compressed,8k;\n"
    "av1:4k,compressed,10bit;\n"
    "vp9:4k,compressed;\n"
)
WITHOUT_AV1 = (
    "h264:4k;\n"
    "hevc:4k,compressed,8k;\n"
    "vp9:4k,compressed;\n"
)
AV1_FRONT_BACK = "av1_fb:4k,compressed,10bit;\n"
#: The shape Kodi's negative lookahead exists to reject: the codec is listed
#: but the row is empty, which is a name without a capability behind it.
AV1_NAMED_BUT_EMPTY = "av1:;\n"


def run_with(text):
    """Read the ceiling with a fake vcodec_profile in place -- `None` for a
    platform that has no such file at all."""
    import builtins
    import io
    saved = builtins.open

    def fake_open(path, *a, **k):
        if path == capabilities._VCODEC_PROFILE:
            if text is None:
                raise IOError("No such file or directory")
            return io.StringIO(text)
        return saved(path, *a, **k)

    builtins.open = fake_open
    try:
        return capabilities.video_codec_ceilings()
    finally:
        builtins.open = saved


# --- the reading itself ------------------------------------------------
check("no vcodec_profile at all -> no ceiling (every non-Amlogic platform)",
      run_with(None) == "")
check("hardware AV1 present -> no ceiling",
      run_with(WITH_AV1) == "")
check("hardware AV1 absent -> av1 capped at 1080",
      run_with(WITHOUT_AV1) == "av1:1080",
      "got %r" % run_with(WITHOUT_AV1))
check("the front-back AV1 variant counts as hardware too",
      run_with(AV1_FRONT_BACK) == "")
check("an av1 row with no capability behind it is NOT hardware",
      run_with(AV1_NAMED_BUT_EMPTY) == "av1:1080",
      "got %r" % run_with(AV1_NAMED_BUT_EMPTY))
check("an empty file claims nothing rather than capping",
      run_with("") == "")
check("a file of whitespace claims nothing either",
      run_with("\n  \n") == "")

# `.` must not cross a newline, or "av1:" on one row would pair with
# "compressed" on the next and read as hardware that isn't there.
check("a match cannot span two rows",
      run_with("av1:;\nhevc:4k,compressed;\n") == "av1:1080",
      "got %r" % run_with("av1:;\nhevc:4k,compressed;\n"))

# Word boundaries: "av1" must not be found inside a longer codec name.
check("avs1 is not av1",
      run_with("avs1:4k,compressed;\n") == "av1:1080",
      "got %r" % run_with("avs1:4k,compressed;\n"))

# --- how it reaches the query --------------------------------------------
params = CapabilityProfile(codec_ceilings="av1:1080").to_query_params()
check("a ceiling is sent as codec_ceilings",
      params.get("codec_ceilings") == "av1:1080")

check("None omits the parameter entirely (pre-0.9.32 behaviour)",
      "codec_ceilings" not in CapabilityProfile().to_query_params())
check("empty string omits it too, so it is a real opt-out",
      "codec_ceilings" not in
      CapabilityProfile(codec_ceilings="").to_query_params())

# --- the axis confusion this must not become -----------------------------
prof = CapabilityProfile(codec_ceilings="av1:1080")
check("a ceiling does not touch the direct-play list",
      "av1" in prof.direct_play_video_codecs,
      "capping the height must not stop us accepting 1080p AV1 untouched")
check("a ceiling is not a transcode-target list",
      "av1" not in (prof.transcode_video_codecs or ""),
      "av1 must never be a codec we invite the server to re-encode INTO")

# --- for_device ----------------------------------------------------------
explicit = CapabilityProfile.for_device(codec_ceilings="hevc:2160")
check("an explicit ceiling is not overwritten by the reading",
      explicit.codec_ceilings == "hevc:2160")

# A box that cannot answer must still produce a usable profile.
import builtins  # noqa: E402
saved = builtins.open


def exploding_open(*a, **k):
    raise RuntimeError("this box cannot answer")


builtins.open = exploding_open
try:
    survived = CapabilityProfile.for_device()
    ok = True
except Exception:                                           # noqa: BLE001
    survived, ok = None, False
finally:
    builtins.open = saved
check("a box that cannot answer still yields a profile", ok)
check("...and that profile sends no ceiling",
      ok and not (survived.codec_ceilings or ""))

print("")
failed = [n for n, ok in RESULTS if not ok]
print("codec ceilings: AV1 capped only where the silicon says so (%d checks)"
      % len(RESULTS))
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
