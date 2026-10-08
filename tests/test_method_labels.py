"""The stats panel's Method row names the delivery as tofa's apps do.

Run:  python3 test_method_labels.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import playerstats as ps

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def method(play, mode):
    return ps._delivery({"play_method": play, "decision_mode": mode})


direct = method("DirectPlay", "DirectFile")
check("a direct play reads in words", direct == "Direct Play · whole file", direct)
check("...and is not tinted", "[COLOR" not in direct, direct)

remux = method("DirectStream", "HlsRemux")
check("a remux names both halves", "Direct Stream · repackaged" in remux, remux)

full = method("Transcode", "HlsFullTranscode")
check("a transcode says what was converted",
      "Transcode · video and audio converted" in full, full)
check("...tinted as degraded", full.startswith("[COLOR"), full)

audio = method("Transcode", "HlsCopyVideoTranscodeAudio")
check("an audio-only conversion says so", "audio converted" in audio, audio)

unknown = method("SomethingNew", "AlsoNew")
check("an unknown value is shown as sent, not dropped",
      "SomethingNew" in unknown and "AlsoNew" in unknown, unknown)
check("no method at all is a dash", ps._delivery({}) == ps.MISSING)

check("the stats button cycles off and panel only", ps.CYCLE == (ps.OFF, ps.PANEL))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"method labels: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
