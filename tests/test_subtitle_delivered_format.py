"""A subtitle's format column says what ARRIVES, not what is in the file.

`codec` is the track's format in the container. It is not what this client
fetches. `representations` is a MENU of what the server can serve a track
as -- measured across 40 files on a 0.10.0 server: `subrip` offers `vtt`
alone, PGS offers `pgs`, a VobSub sidecar offers `vobsub`, and an `ass`
track offers **both** `ass` and `vtt`.

The choice is ours, and PlayerWindow._external_subtitle_url makes it: `.vtt`
for anything that is not a VobSub sidecar, deliberately, because ASS carries
styling the skin has no say over. So an ASS track is taken as plain text ON
PURPOSE -- and that is invisible to a viewer, which is why it belongs in the
stats panel.

Contract 2 (`subtitle_contract_version=2`) adds `representations[]`, whose
`format` is the delivered one. It is purely additive -- same tracks, same
order, no existing value changed -- so an older server simply sends none and
everything here falls back to the codec, exactly as it behaved before.

Run:  python3 test_subtitle_delivered_format.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import tracks
from resources.lib.profile import CapabilityProfile

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def track(codec, fmts=None, **kw):
    t = {"index": 2, "language": "eng", "codec": codec}
    if fmts is not None:
        if isinstance(fmts, str):
            fmts = [fmts]
        t["representations"] = [{"format": f, "schema": "x", "state": "ready"}
                                for f in fmts]
    t.update(kw)
    return t


# 1. The parameter is sent, and it is 2. Contract 1 is identical to sending
#    nothing, so 2 is the only value worth asking for.
params = CapabilityProfile.for_device().to_query_params()
check("the profile asks for subtitle contract 2",
      params.get("subtitle_contract_version") == 2,
      repr(params.get("subtitle_contract_version")))

# 2. The PICKER keeps naming the source codec -- the name the viewer knows
#    their file by. Nothing is lost converting SRT to WebVTT, so trading a
#    familiar name for a transport detail on 316 rows out of 320 would be a
#    worse column, not a truer one.
for codec, fmts, want in (
        ("subrip",            ["vtt"],        "SRT"),
        ("ass",               ["ass", "vtt"], "ASS"),
        ("hdmv_pgs_subtitle", ["pgs"],        "PGS"),
        ("dvd_subtitle",      ["vobsub"],     "VobSub")):
    _, detail = tracks.subtitle_track_label(track(codec, fmts))
    check(f"the picker still calls {codec} {want}", detail == want, repr(detail))

# 3. What we will actually FETCH is a separate question, answered for the
#    stats panel alone. `representations` is a MENU: an ass track offers both
#    renditions and the choice is ours, made in _external_subtitle_url.
for codec, fmts, want in (
        ("subrip",            ["vtt"],        "WebVTT"),
        ("hdmv_pgs_subtitle", ["pgs"],        "PGS"),
        ("dvd_subtitle",      ["vobsub"],     "VobSub"),
        ("ass",               ["ass", "vtt"], "WebVTT"),
        # Order in the menu must not decide it -- the rule is ours.
        ("ass",               ["vtt", "ass"], "WebVTT"),
        # Offered ONLY as ass, we would have to take it as ass.
        ("ass",               ["ass"],        "ASS")):
    check(f"{codec} offered {fmts} is fetched as {want}",
          tracks.delivered_format(track(codec, fmts)) == want,
          repr(tracks.delivered_format(track(codec, fmts))))

# 4. An older server sends no representations: the source codec comes back,
#    which is what the column said before any of this.
for codec, want in (("ass", "ASS"), ("subrip", "SRT"),
                    ("hdmv_pgs_subtitle", "PGS"), ("dvd_subtitle", "VobSub")):
    _, detail = tracks.subtitle_track_label(track(codec))
    check(f"no representations: the picker still says {want}",
          detail == want, repr(detail))
    check(f"...and nothing claims to know what {codec} is fetched as",
          tracks.delivered_format(track(codec)) == "")

# 5. Junk in the representation must not reach the screen.
for fmt in ("", "sup", "weird"):
    check(f"an unknown representation {fmt!r} is not a fetch format",
          tracks.delivered_format(track("subrip", [fmt])) == "",
          repr(tracks.delivered_format(track("subrip", [fmt]))))

# 6. External still rides on the end, and the delivered format leads it.
_, detail = tracks.subtitle_track_label(track("subrip", ["vtt"], external=True))
check("an external sidecar still says so", detail == "SRT · External", repr(detail))

# 7. The stats panel's warning is a real DOWNGRADE, not merely a difference.
#    Every SRT arrives as WebVTT and loses nothing; a styled track flattened
#    to plain text loses what the author wrote.
check("styling offered and we take vtt IS a loss",
      tracks.subtitle_style_lost(track("ass", ["ass", "vtt"])))
check("ssa the same", tracks.subtitle_style_lost(track("ssa", ["ssa", "vtt"])))
check("offered ONLY as ass, nothing is lost",
      not tracks.subtitle_style_lost(track("ass", ["ass"])))
check("srt is not styled to begin with",
      not tracks.subtitle_style_lost(track("subrip", ["vtt"])))
check("pgs is a picture, nothing to flatten",
      not tracks.subtitle_style_lost(track("hdmv_pgs_subtitle", ["pgs"])))
check("no representations is NOT", not tracks.subtitle_style_lost(track("ass")))
check("an empty track is NOT", not tracks.subtitle_style_lost({}))

# 8. The panel row itself: source beside delivered, and pruned when there is
#    nothing to say.
from resources.lib.windows import playerstats
check("no subtitle gives no pair", playerstats._subtitle_pair(None) == ("", ""))
check("an old server gives no pair", playerstats._subtitle_pair(track("ass")) == ("", ""))
check("an ASS track pairs ASS with WebVTT",
      playerstats._subtitle_pair(track("ass", ["ass", "vtt"])) == ("ASS", "WebVTT"),
      repr(playerstats._subtitle_pair(track("ass", ["ass", "vtt"]))))
check("a PGS pairs with itself",
      playerstats._subtitle_pair(track("hdmv_pgs_subtitle", ["pgs"])) == ("PGS", "PGS"),
      repr(playerstats._subtitle_pair(track("hdmv_pgs_subtitle", ["pgs"]))))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
