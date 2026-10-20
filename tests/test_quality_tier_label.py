"""Quality rows as the app titles them: the height, then the rate it delivers.

Run:  python3 test_quality_tier_label.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import tracks

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


capped = {"tag": "1080p-18m", "label": "1080p · 16 Mbps", "height": 1080, "bitrate_kbps": 16956}
check("a capped tier is titled by its height, not its nominal tag",
      tracks.quality_tier_label(capped)[0] == "1080p", str(tracks.quality_tier_label(capped)))
check("...and its detail is the rate the server will send, as its label says it",
      tracks.quality_tier_label(capped)[1] == "16 Mbps", str(tracks.quality_tier_label(capped)))
# Measured off a 0.12.0 server's labels, 2026-10-20.
SERVER = {18000: "18 Mbps", 16956: "16 Mbps", 11972: "11 Mbps", 7778: "7.8 Mbps",
          4940: "4.9 Mbps", 2170: "2.2 Mbps", 6996: "7.0 Mbps", 8000: "8 Mbps",
          101122: "101 Mbps", 750: "750 kbps"}
ours = {k: tracks.tier_rate_label(k) for k in SERVER}
check("rates read as the server's own labels write them", ours == SERVER,
      str({k: v for k, v in ours.items() if v != SERVER[k]}))
original = {"tag": "original", "height": 2160, "bitrate_kbps": 101122, "is_original": True}
check("Original keeps its height and rate on the second line",
      tracks.quality_tier_label(original)[0] == "Original"
      and tracks.quality_tier_label(original)[1].startswith("2160p"), str(tracks.quality_tier_label(original)))
check("no height falls back to the tag",
      tracks.quality_tier_label({"tag": "540p", "bitrate_kbps": 2200})[0] == "540p")

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
