"""Checks the card badge mapping, and that an UNKNOWN label still draws.

The failure this guards is silence. An audio label with no entry drew nothing
at all, and nothing said so -- which is how DTS:X, HLG and DTS-HD HRA went
unbadged until the live library was sampled (2026-08-05). The API gives no
enum for audio labels (`short_label` is a plain string whose description ends
"| ..."), so a new one can arrive in any server release.

So the cases that matter here are the INVENTED ones: labels no server has
sent yet must still produce a sensible badge.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)

#: The add-on tree, wherever it is. This tool stays in the vault when the
#: add-on moves to its own public repo, so it has to look next door.
ADDON = checkouts.addon_dir(ROOT)
if not ADDON:
    raise SystemExit("cannot find plugin.video.tofa/ -- check it out beside "
                     "this repo, or set TOFA_ADDON_REPO")

sys.path.insert(0, os.path.join(ADDON, "resources"))

from lib import badges  # noqa: E402


def item(audio=None, video=None, dr=None, is_4k=False):
    fmt = {"is_4k": is_4k}
    if audio is not None:
        fmt["audio"] = {"short_label": audio}
    if video is not None or dr is not None:
        fmt["video"] = {"label": video, "short_label": video, "dynamic_range": dr}
    return {"format": fmt}


def main() -> int:
    fails = []
    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r wanted %r" % (name, got, want))

    # --- every label the live library actually produces (sampled 1,200) ---
    for label, want in (("DTS-HD MA", "DTS-HD MA"), ("Atmos", "ATMOS"),
                        ("DD+", "DD+"), ("DD", "DD"), ("TrueHD", "TRUEHD"),
                        ("DTS", "DTS"), ("DTS:X", "DTS:X"),
                        ("DTS-HD HRA", "DTS-HD HRA")):
        check("audio %s" % label, badges.card_badges(item(audio=label)), [want])
    for dr, want in (("dolby_vision", "DV"), ("hdr10", "HDR10"),
                     ("hdr10_plus", "HDR10+"), ("hlg", "HLG"), ("hdr", "HDR")):
        check("range %s" % dr, badges.card_badges(item(dr=dr)), [want])

    # --- the non-badges -------------------------------------------------
    check("sdr is not a badge", badges.card_badges(item(dr="sdr")), [])
    check("unprobed range is not a badge", badges.card_badges(item(dr=None)), [])
    check("null audio is not a badge", badges.card_badges(item(audio=None)), [])
    check("show=False silences everything",
          badges.card_badges(item(audio="Atmos", dr="hdr10", is_4k=True), show=False), [])

    # --- ORDER and the cap ----------------------------------------------
    check("resolution, range, audio",
          badges.card_badges(item(audio="DTS:X", dr="hdr10", is_4k=True)),
          ["4K", "HDR10", "DTS:X"])
    check("never more than three",
          len(badges.card_badges(item(audio="Atmos", dr="dolby_vision", is_4k=True))), 3)

    # --- labels NO server has sent: the whole point ---------------------
    # Atmos names its carrier, and ATMOS is what the reference apps show.
    check("TrueHD Atmos -> ATMOS", badges.card_badges(item(audio="TrueHD Atmos")), ["ATMOS"])
    check("DD+ Atmos -> ATMOS", badges.card_badges(item(audio="DD+ Atmos")), ["ATMOS"])
    check("Dolby Atmos -> ATMOS", badges.card_badges(item(audio="Dolby Atmos")), ["ATMOS"])
    # Invented DTS variants degrade to the family, not to nothing.
    check("DTS-ES -> DTS", badges.card_badges(item(audio="DTS-ES")), ["DTS"])
    check("DTS-HD MA 7.1 -> DTS-HD MA",
          badges.card_badges(item(audio="DTS-HD MA 7.1")), ["DTS-HD MA"])
    check("a future DTS-HD flavour -> DTS-HD",
          badges.card_badges(item(audio="DTS-HD XYZ")), ["DTS-HD"])
    check("EAC3 -> DD+", badges.card_badges(item(audio="EAC3")), ["DD+"])
    check("AC3 -> DD", badges.card_badges(item(audio="AC3")), ["DD"])
    check("LPCM -> PCM", badges.card_badges(item(audio="LPCM 5.1")), ["PCM"])
    # Genuinely unrecognisable: nothing, but it was logged.
    check("unknown family -> nothing", badges.card_badges(item(audio="Wibble")), [])
    # A dynamic range added to the enum later must not lose the HDR badge.
    check("future range -> generic HDR",
          badges.card_badges(item(dr="hdr11_ultra", video=None)), ["HDR"])

    # --- the generator's contract ---------------------------------------
    # Every card badge must have SOMETHING that can produce it. _SHORTEN was
    # the only producer until 0.9.28 added two more: `stereo_3d` yields the
    # 3D chip and `picture_aspect_ratio` yields a projection ratio, neither
    # of which passes through the label-shortening table. Widening the check
    # rather than dropping it -- an unreachable badge is still art nothing
    # can ever draw, which is exactly what this catches.
    producible = (set(badges._SHORTEN.values())
                  | {"3D"}
                  | set(badges.ASPECT_BADGES.values()))
    missing = [b for b in badges.CARD_BADGES if b not in producible]
    check("every CARD_BADGE has a producer", missing, [])
    families = sorted({b for _n, b in badges._FAMILIES})
    unknown = [b for b in families if b not in badges.CARD_BADGES]
    check("every family badge has an asset", unknown, [])

    for f in fails:
        print("FAIL " + f)
    print("%d checks, %d failed" % (35, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
