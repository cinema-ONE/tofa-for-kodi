"""What we ask the server to DELIVER on a transcode, matched to the route.

Without `audio_fidelity` the server uses what its own API docs call "the
legacy stereo-AAC pipeline". Measured against Hugo (DTS-HD MA 7.1 + AC3 5.1)
on 2026-08-12, forcing any quality below Original delivered

    CODECS="avc1.640020,mp4a.40.2"   CHANNELS="2"     stereo AAC

and the same request with these two parameters delivered, at the identical
4192000 bandwidth,

    CODECS="avc1.640020,ec-3"        CHANNELS="6"     E-AC-3 5.1

The risk this file guards is the opposite of the bug: asking for a rendition
the player CANNOT take would turn a stereo downgrade into silence. So the ask
is derived from the output route, and the rule is

    bitstream E-AC-3          -> ask (the AVR gets it untouched)
    decode to multichannel    -> ask (Kodi decodes, sink still carries 5.1)
    stereo route, no passthru -> ask for NOTHING; stereo AAC is correct there

Run:  python3 test_audio_delivery.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities
from resources.lib.profile import CapabilityProfile

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def fake_audio(channels_label, passthrough, eac3):
    def build():
        return {"channels_label": channels_label,
                "passthrough": passthrough,
                "decoded_format": "LPCM",
                "formats": {"audiooutput.eac3passthrough": eac3}}
    return build


def delivery(channels_label, passthrough, eac3):
    capabilities.invalidate()
    real = capabilities.audio
    capabilities.audio = fake_audio(channels_label, passthrough, eac3)
    try:
        capabilities.invalidate()
        return capabilities.audio_delivery()
    finally:
        capabilities.audio = real
        capabilities.invalidate()


def run():
    # --- the channel COUNT, which is not the layout label ----------------
    for label, want in (("7.1", 8), ("5.1", 6), ("2.0", 2), ("3.1", 4),
                        ("Mono", 1), ("", 0), (None, 0)):
        check("channel_count(%r) == %s" % (label, want),
              capabilities.channel_count(label) == want,
              repr(capabilities.channel_count(label)))

    # --- the matching rule ----------------------------------------------
    d = delivery("7.1", passthrough=True, eac3=True)
    check("E-AC-3 bitstreamed -> ask, 8 channels",
          d == {"audio_fidelity": "atmos", "audio_sink_channels": 8}, repr(d))

    d = delivery("5.1", passthrough=False, eac3=False)
    check("no passthrough but a 5.1 sink -> ask, Kodi decodes",
          d == {"audio_fidelity": "atmos", "audio_sink_channels": 6}, repr(d))

    d = delivery("2.0", passthrough=False, eac3=False)
    check("stereo route, no passthrough -> ask for NOTHING",
          d["audio_fidelity"] is None,
          "%r -- asking here risks silence for no gain" % (d,))

    d = delivery("2.0", passthrough=True, eac3=True)
    check("stereo route WITH E-AC-3 passthrough -> still ask",
          d == {"audio_fidelity": "atmos", "audio_sink_channels": 2},
          "%r -- a soundbar/ARC sink carries surround only as a bitstream" % (d,))

    d = delivery("7.1", passthrough=True, eac3=False)
    check("passthrough on but E-AC-3 off, 7.1 sink -> ask",
          d["audio_fidelity"] == "atmos", repr(d))

    # --- what actually reaches the query string --------------------------
    p = CapabilityProfile(audio_fidelity="atmos", audio_sink_channels=6)
    q = p.to_query_params()
    check("both fields reach the query string",
          q.get("audio_fidelity") == "atmos" and q.get("audio_sink_channels") == 6,
          repr(q))

    # The server only READS the channel count when fidelity is set, so it
    # must never travel alone -- that would be noise on every request.
    p = CapabilityProfile(audio_sink_channels=6)
    q = p.to_query_params()
    check("the channel count never travels without the fidelity",
          "audio_sink_channels" not in q, repr(q))

    p = CapabilityProfile()
    q = p.to_query_params()
    check("neither is sent by default (today's behaviour)",
          "audio_fidelity" not in q and "audio_sink_channels" not in q, repr(q))

    # --- quality_mode: a chosen Original is not the same as no choice -----
    q = CapabilityProfile(quality_mode="original").to_query_params()
    check("a chosen Original says so",
          q.get("quality_mode") == "original" and "max_bitrate" not in q,
          "%r -- and it must carry no cap of its own" % (q,))
    q = CapabilityProfile().to_query_params()
    check("no choice expressed sends nothing",
          "quality_mode" not in q, repr(q))
    q = CapabilityProfile(max_bitrate=4000).to_query_params()
    check("a real tier is expressed by the ceiling alone",
          q.get("max_bitrate") == 4000 and "quality_mode" not in q, repr(q))

    # --- for_device must never be able to break playback -----------------
    real = capabilities.audio
    def boom():
        raise RuntimeError("no settings")
    capabilities.audio = boom
    capabilities.invalidate()
    try:
        p = CapabilityProfile.for_device(max_bitrate=2000)
        check("a box that cannot answer still gets a usable profile",
              p.max_bitrate == 2000 and p.audio_fidelity is None,
              repr(p.to_query_params()))
    finally:
        capabilities.audio = real
        capabilities.invalidate()

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("audio delivery: we ask only for what the route can take "
          "(%d checks)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
