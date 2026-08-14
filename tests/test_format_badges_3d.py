"""The hero badge row surfaces the server's 3D label.

Until server 0.9.28 the API carried NOTHING about 3D -- no layout, no flag --
which is why project_player_native_settings_gap listed it as a gap and why the
player's 3D work had to rely on Kodi's own container detection. VideoFormatInfo
now carries `stereo_3d` and a ready-made `stereo_3d_label`, rendered verbatim
like every other label here.

Run:  python3 test_format_badges_3d.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")

L = DetailWindow._format_badge_labels

def f(video=None, audio=None, res="1080p"):
    return {"format": {"resolution_label": res, "video": video or {}, "audio": audio}}

# 2D: null is the 2D case and must add nothing.
check("no 3D label adds no badge", L(f()) == ["1080p"], str(L(f())))
check("an explicit null adds nothing",
      L(f({"stereo_3d": None, "stereo_3d_label": None})) == ["1080p"])

# 3D, verbatim.
out = L(f({"stereo_3d": "frame_packed", "stereo_3d_label": "3D Frame-Packed"}))
check("frame-packed is badged verbatim", out == ["1080p", "3D Frame-Packed"], str(out))
out = L(f({"stereo_3d": "side_by_side", "stereo_3d_label": "3D Side-by-Side"}))
check("side-by-side is badged verbatim", out == ["1080p", "3D Side-by-Side"], str(out))

# Order: 3D is a fact about the picture, so it sits with the resolution and
# before the colour badges.
out = L(f({"stereo_3d_label": "3D Frame-Packed", "dynamic_range": "dolby_vision",
           "label": "Dolby Vision"}, res="4K"))
check("3D precedes dynamic range",
      out == ["4K", "3D Frame-Packed", "Dolby Vision"], str(out))

# It must not disturb what was already there.
out = L(f({"dynamic_range": "hdr10", "label": "HDR10"},
          audio={"label": "TrueHD Atmos", "channels_label": "7.1"}, res="4K"))
check("a 2D file is unchanged", out == ["4K", "HDR10", "TrueHD Atmos 7.1"], str(out))

# A server predating MediaFormatInfo still falls back.
check("no format block still falls back",
      L({"height": 2160}) == ["4K"], str(L({"height": 2160})))


# --- projection ratio on the hero -------------------------------------
# 16:9 IS shown here, unlike on a card: the hero has room, and on a detail
# page "1.78:1" is a fact rather than clutter.
out = L(f({}, res="1080p")) ; out2 = L({"format": {"resolution_label": "1080p",
        "video": {}, "picture_aspect_ratio": 1.78, "audio": None}})
check("16:9 is stated on the hero", out2 == ["1080p", "1.78:1"], str(out2))
scope = {"format": {"resolution_label": "4K", "video": {}, "audio": None,
                    "picture_aspect_ratio": 2.39}}
check("scope reads 2.39:1", L(scope) == ["4K", "2.39:1"], str(L(scope)))
odd = {"format": {"resolution_label": "4K", "video": {}, "audio": None,
                  "picture_aspect_ratio": 2.30}}
check("an unsnapped ratio is silent", L(odd) == ["4K"], str(L(odd)))
full = {"format": {"resolution_label": "4K", "audio": None,
                   "video": {"stereo_3d_label": "3D Frame-Packed"},
                   "picture_aspect_ratio": 2.39}}
check("3D then aspect, both after resolution",
      L(full) == ["4K", "3D Frame-Packed", "2.39:1"], str(L(full)))


# --- bit depth on the hero's audio badge -------------------------------
# Only for LOSSLESS, and joined back to the raw track through track_index --
# the depth lives on AudioTrack, not on AudioFormatInfo.
def audio_case(audio, tracks):
    return {"format": {"resolution_label": "1080p", "video": {}, "audio": audio},
            "audio_tracks": tracks}
LOSSLESS = {"label": "DTS-HD MA", "channels_label": "7.1", "lossless": True,
            "track_index": 1}
check("lossless badge carries the depth",
      L(audio_case(LOSSLESS, [{"index": 1, "bit_depth": 24}]))[-1]
      == "DTS-HD MA 7.1 24-bit",
      str(L(audio_case(LOSSLESS, [{"index": 1, "bit_depth": 24}]))))
check("no depth reported means no suffix",
      L(audio_case(LOSSLESS, [{"index": 1}]))[-1] == "DTS-HD MA 7.1")
# track_index is a CONTAINER STREAM INDEX, not a list position. A track list
# that does not contain it must not be indexed into by accident.
check("an index that matches nothing is silent",
      L(audio_case(LOSSLESS, [{"index": 9, "bit_depth": 24}]))[-1] == "DTS-HD MA 7.1")
check("a rollup with no track_index is silent",
      L(audio_case({"label": "TrueHD Atmos", "channels_label": "7.1",
                    "lossless": True, "track_index": None},
                   [{"index": 0, "bit_depth": 24}]))[-1] == "TrueHD Atmos 7.1")
check("a LOSSY track never shows depth",
      L(audio_case({"label": "Dolby Digital", "channels_label": "5.1",
                    "lossless": False, "track_index": 0},
                   [{"index": 0, "bit_depth": 24}]))[-1] == "Dolby Digital 5.1")

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
