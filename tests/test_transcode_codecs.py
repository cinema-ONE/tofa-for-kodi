"""What we let the server RE-ENCODE to (`transcode_video_codecs`, 0.9.32).

The parameter names the codecs this client can decode when the server has
already decided to re-encode the video. Omitting it means the server's legacy
H.264, which is what every release before this one got.

The trap this file guards is that it looks like a copy of
`direct_play_video_codecs` and must not be one. Those two answer different
questions, and getting the second wrong does not degrade quality, it hands
the box a stream it cannot keep up with. Measured on AM6B-BOX (CoreELEC 21.3,
Amlogic, kernel 4.9) on 2026-08-19 by playing single-codec streams and
reading `Player.Process(videodecoder)`:

    HEVC Main10 1080p60, fMP4 HLS   am-h265        hardware, kept real time
    AV1 1080p30, plain mp4          ff-libdav1d    SOFTWARE dav1d

Both codecs are on the DIRECT-PLAY list and that is right: accepting an AV1
source untouched still beats a transcode it never needed. Inviting the server
to re-encode INTO av1 would be the opposite -- a software decode of a stream
that could have arrived as HEVC.

Run:  python3 test_transcode_codecs.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities
from resources.lib.profile import (DEFAULT_TRANSCODE_VIDEO_CODECS,
                                   DEFAULT_VIDEO_CODECS, CapabilityProfile)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def codecs(value):
    return [c.strip() for c in (value or "").split(",") if c.strip()]


def run():
    # --- the list itself --------------------------------------------------
    wanted = codecs(DEFAULT_TRANSCODE_VIDEO_CODECS)
    check("hevc is asked for first",
          wanted[:1] == ["hevc"],
          "%r -- the parameter is ORDERED, so first means preferred" % (wanted,))
    check("h264 is named, not left to the server's default",
          "h264" in wanted,
          "%r -- 'omitted means legacy H.264' is a default we would rather "
          "state than inherit" % (wanted,))

    # A codec we would not accept as a SOURCE cannot be one we accept as the
    # output of a re-encode; the decoder is the same either way. Subset, not
    # equality -- the whole point is that this list is shorter.
    accepted = codecs(DEFAULT_VIDEO_CODECS)
    check("every transcode target is one we already decode",
          set(wanted) <= set(accepted),
          "%r not in %r" % (sorted(set(wanted) - set(accepted)), accepted))
    check("the transcode list is SHORTER than the direct-play list",
          len(wanted) < len(accepted),
          "%r vs %r -- if these ever match, the distinction has been lost"
          % (wanted, accepted))

    # The measured one. On Amlogic aml-4.9 AV1 falls to ff-libdav1d, so an
    # AV1 re-encode would be a software decode of a stream that could have
    # been HEVC. Keep it off until some box is measured decoding it in
    # hardware -- and then it is a per-box question, not this constant.
    check("av1 is NOT offered as a re-encode target",
          "av1" not in wanted,
          "%r -- AM6B-BOX decodes AV1 on ff-libdav1d (software), 2026-08-19"
          % (wanted,))
    for absent in ("vp9", "mpeg2video", "vc1"):
        check("%s is not a re-encode target either" % absent,
              absent not in wanted,
              "%r -- no server re-encodes to it" % (wanted,))

    check("no whitespace or empties in the CSV",
          DEFAULT_TRANSCODE_VIDEO_CODECS == ",".join(wanted),
          repr(DEFAULT_TRANSCODE_VIDEO_CODECS))
    check("all lower case, as the server spells them",
          DEFAULT_TRANSCODE_VIDEO_CODECS == DEFAULT_TRANSCODE_VIDEO_CODECS.lower(),
          repr(DEFAULT_TRANSCODE_VIDEO_CODECS))

    # --- what reaches the query string ------------------------------------
    q = CapabilityProfile().to_query_params()
    check("the bare profile sends it",
          q.get("transcode_video_codecs") == DEFAULT_TRANSCODE_VIDEO_CODECS,
          "%r -- addon.py's plain directory path uses the bare constructor, "
          "and deserves the same stream as the player window" % (q,))

    q = CapabilityProfile(transcode_video_codecs="hevc").to_query_params()
    check("a custom list travels verbatim",
          q.get("transcode_video_codecs") == "hevc", repr(q))

    # The documented opt-out. The server's rule is that an ABSENT parameter
    # means legacy H.264, so "" has to omit the parameter rather than send an
    # empty one -- that is the single edit that puts a box back on exactly
    # the pre-0.9.32 behaviour if HEVC ever turns out not to suit it.
    q = CapabilityProfile(transcode_video_codecs="").to_query_params()
    check("an empty list omits the parameter entirely",
          "transcode_video_codecs" not in q, repr(q))

    # --- it is NOT a per-box derivation, and must not become one silently --
    # for_device() fills in the audio fields from the output route because
    # Kodi publishes that route. It publishes no per-codec video decode
    # signal at all, so this rides the default and must still arrive.
    p = CapabilityProfile.for_device(max_bitrate=2000)
    check("for_device carries it too",
          p.to_query_params().get("transcode_video_codecs")
          == DEFAULT_TRANSCODE_VIDEO_CODECS,
          repr(p.to_query_params()))

    real = capabilities.audio

    def boom():
        raise RuntimeError("no settings")

    capabilities.audio = boom
    capabilities.invalidate()
    try:
        p = CapabilityProfile.for_device()
        check("a box that cannot answer still declares its transcode codecs",
              p.to_query_params().get("transcode_video_codecs")
              == DEFAULT_TRANSCODE_VIDEO_CODECS,
              repr(p.to_query_params()))
    finally:
        capabilities.audio = real
        capabilities.invalidate()

    # --- the neighbouring parameter we deliberately do not send -----------
    # codec_ceilings caps the SOURCE height we will direct-play per codec;
    # this one picks the codec of a re-encode already decided on. The spec
    # couples them nowhere, so a ceiling would not stop a 4K HEVC re-encode.
    # Sending none is the only state in which they provably cannot interact.
    q = CapabilityProfile().to_query_params()
    check("no codec_ceilings is declared",
          "codec_ceilings" not in q, repr(q))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("transcode codecs: we invite only what this box decodes in "
          "hardware (%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
