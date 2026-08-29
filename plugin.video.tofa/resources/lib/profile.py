"""The capability profile sent as query params to GET /stream/{id}/info
(brief §4 -- "the critical module"). Values are the CoreELEC/Amlogic profile
Phase 0 confirmed reliably yields DirectPlay/DirectFile (brief §12).

`prefer_hdr10` has no field on purpose -- the brief says never send it.
`dolby_vision_supported` is left unset -- Phase 0 confirmed it's a no-op for
DirectFile on the target server, so there's nothing to gain by setting it
and one less moving part to reason about.

`codec_ceilings` is left unset too, and it is NOT the same axis as
`transcode_video_codecs` below however similar they read. A ceiling caps the
SOURCE height we are willing to direct-play per codec ("hevc:1080" means
"anything taller, re-encode it for me"); `transcode_video_codecs` names the
codec of a re-encode the server has already decided on. Nothing in the 0.9.32
spec says the server consults one while applying the other, so a ceiling
would NOT protect this box from a 4K HEVC re-encode -- if we ever declare
one, that has to be measured against a server rather than assumed. Declaring
no ceiling, as we do, is also the only state in which the two provably cannot
interact.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Optional

DEFAULT_VIDEO_CODECS = "hevc,h264,vp9,av1,mpeg2video,vc1"
DEFAULT_AUDIO_CODECS = "truehd,dts,dtshd,eac3,ac3,aac,flac,pcm,opus,mp3,mp2"
DEFAULT_CONTAINERS = "mkv,mp4,m2ts,ts,avi,mov,webm"

#: Ordered codecs we can take when the server RE-ENCODES the video (server
#: 0.9.32+). Deliberately a SHORTER list than DEFAULT_VIDEO_CODECS, which
#: answers a different question: that one says which source bitstreams may
#: reach this box untouched, and a box is right to accept a codec it decodes
#: only adequately there, because the alternative is a transcode the file did
#: not need. Here the alternative is a codec the server would have picked
#: instead, so anything this box cannot decode WELL has no business on the
#: list.
#:
#: Measured on AM6B-BOX (CoreELEC 21.3, Amlogic, kernel 4.9) 2026-08-19 by
#: playing an HEVC-only fMP4 HLS media playlist -- the packaging a re-encode
#: actually arrives in, which DirectPlay of an HEVC FILE never exercises:
#:
#:     HEVC Main10 1080p60, fMP4 HLS   Player.Process(videodecoder) = am-h265
#:                                     hardware, and it kept real time
#:     AV1 1080p30, plain mp4          ff-libdav1d -- SOFTWARE. There is no
#:                                     am-av1 on this silicon.
#:
#: which is why `av1` is on the direct-play list and not on this one:
#: inviting an AV1 re-encode would hand that box a dav1d software decode of a
#: stream it never had to be sent. vp9/mpeg2video/vc1 are off for the same
#: reason, and because no server re-encodes TO them.
#:
#: `h264` stays as the last rung rather than being left to the server's
#: "omitted means legacy H.264" default, so the fallback is something we said
#: rather than something we were handed. Setting this to "" reproduces the
#: pre-0.9.32 behaviour exactly, which is the escape hatch if a box ever
#: turns out not to cope.
DEFAULT_TRANSCODE_VIDEO_CODECS = "hevc,h264"

_BOOL_FIELDS = (
    "hdr_supported",
    "h264_10bit_supported",
    "deinterlacing_supported",
    "client_render_bitmap_subtitles",
    "client_render_vobsub_subtitles",
    "client_render_embedded_vobsub_subtitles",
    "include_native_subtitle_rendition",
    "dolby_vision_supported",
)


def _bool_param(value: Optional[bool]) -> Optional[str]:
    return None if value is None else ("true" if value else "false")


@dataclasses.dataclass
class CapabilityProfile:
    direct_play_video_codecs: str = DEFAULT_VIDEO_CODECS
    direct_play_audio_codecs: str = DEFAULT_AUDIO_CODECS
    direct_play_containers: str = DEFAULT_CONTAINERS
    #: See DEFAULT_TRANSCODE_VIDEO_CODECS. A module-level constant and NOT
    #: derived per box in for_device(), unlike the audio fields below, and
    #: the difference is what Kodi will answer rather than a style choice:
    #: it publishes the audio OUTPUT ROUTE (audiooutput.channels, a
    #: passthrough switch per format), so audio_fidelity is a reading. It
    #: publishes nothing of the kind for video decode. Its hardware-decode
    #: settings are per-API -- usedxva2 / usevtb / usemediacodec / usevaapi
    #: -- never per codec, and the only per-codec ones anywhere are
    #: CoreELEC's useamcodec{h264,mpeg2,mpeg4,vc1}, which has no HEVC entry
    #: at all (all 378 settings enumerated on AM6B-BOX, 2026-08-19).
    #: Deriving this would be inventing an answer Kodi never gave, which is
    #: the failure capabilities.py exists to avoid.
    transcode_video_codecs: str = DEFAULT_TRANSCODE_VIDEO_CODECS
    hdr_supported: Optional[bool] = True
    h264_10bit_supported: Optional[bool] = True
    deinterlacing_supported: Optional[bool] = True
    client_render_bitmap_subtitles: Optional[bool] = True
    #: Server 0.9.32. Without it, a disc rip whose subtitles live in a
    #: sidecar `.idx`/`.sub` pair gets them routed to
    #: `burn_in_subtitle_tracks` -- a burn-in transcode, or nothing at all.
    #: With it they arrive in `subtitle_tracks` as `render: bitmap` and are
    #: fetched from the `full.idx` route, which Kodi's own VobSub demuxer
    #: reads (see PlayerWindow._external_subtitle_url).
    client_render_vobsub_subtitles: Optional[bool] = True
    #: Server 0.9.33, and a different promise from the sidecar flag above:
    #: there is no server extraction route for VobSub INSIDE the container,
    #: so this one never yields a fetchable URL. It only moves embedded
    #: `dvd_subtitle` out of `burn_in_subtitle_tracks` into `subtitle_tracks`
    #: on DirectPlay, where Kodi demuxes the container itself and selects
    #: the stream natively (`external` unset, so _is_vobsub_sidecar stays
    #: False and nothing asks the 400-answering routes for it). Under a
    #: transcode the tracks stay burn-in-only, exactly as before.
    client_render_embedded_vobsub_subtitles: Optional[bool] = True
    stereo_only_audio_codecs: Optional[str] = None
    max_bitrate: Optional[int] = None
    include_native_subtitle_rendition: Optional[bool] = None
    dolby_vision_supported: Optional[bool] = None
    #: Only meaningful together. Absent, the server falls back to its older
    #: stereo AAC path -- so a forced quality tier costs you surround. Set them from the OUTPUT ROUTE via for_device(), never by
    #: hand: asking for a rendition this player cannot take would turn a
    #: stereo downgrade into silence. See capabilities.audio_delivery.
    audio_fidelity: Optional[str] = None
    audio_sink_channels: Optional[int] = None
    #: How the viewer arrived at this quality, when the bitrate alone cannot
    #: say. `"original"` means they explicitly CHOSE Original -- which is
    #: otherwise indistinguishable from never having been asked, since both
    #: send no `max_bitrate`. Without it the server falls back on its own
    #: banding and re-decides a band the viewer has already picked. It caps
    #: nothing by itself. (`"auto"` is for a bitrate that came from a
    #: connection-speed probe; this add-on does not probe, so it never sends
    #: it.)
    quality_mode: Optional[str] = None

    def to_query_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "direct_play_video_codecs": self.direct_play_video_codecs,
            "direct_play_audio_codecs": self.direct_play_audio_codecs,
            "direct_play_containers": self.direct_play_containers,
        }
        # Sent only when set, so "" is a real opt-out rather than a codec
        # list nobody can satisfy: the server's own rule is that an omitted
        # parameter means legacy H.264, which is precisely the behaviour
        # every release before this one had.
        #
        # This DECLARES what we can take; it does not ask for it. HEVC output
        # is a server-side setting and off by default, so until an operator
        # turns it on the decision is the same one we get today. That is the
        # spec's contract rather than something measured here -- no server
        # with HEVC output enabled was available to negotiate against.
        if self.transcode_video_codecs:
            params["transcode_video_codecs"] = self.transcode_video_codecs
        for name in _BOOL_FIELDS:
            v = _bool_param(getattr(self, name))
            if v is not None:
                params[name] = v
        if self.stereo_only_audio_codecs:
            params["stereo_only_audio_codecs"] = self.stereo_only_audio_codecs
        if self.max_bitrate is not None:
            params["max_bitrate"] = self.max_bitrate
        # The server only READS audio_sink_channels when audio_fidelity is
        # set, so sending the channel count alone is noise. Kept together
        # here rather than trusting each caller to remember that.
        if self.audio_fidelity:
            params["audio_fidelity"] = self.audio_fidelity
            if self.audio_sink_channels:
                params["audio_sink_channels"] = self.audio_sink_channels
        if self.quality_mode:
            params["quality_mode"] = self.quality_mode
        return params

    @classmethod
    def for_device(cls, **kwargs) -> "CapabilityProfile":
        """The profile for THIS box, with the audio delivery fields filled in.

        Every caller that asks the server to make a playback decision should
        use this rather than the bare constructor, so a transcode gets the
        best audio the output route can actually take. Capabilities are read
        lazily and inside a try: this describes hardware, and a box that
        cannot answer should still play -- it just gets the old stereo-AAC
        behaviour, which is exactly the fallback we already had.
        """
        if "audio_fidelity" not in kwargs:
            try:
                from . import capabilities
                kwargs.update(capabilities.audio_delivery())
            except Exception:                               # noqa: BLE001
                pass
        return cls(**kwargs)
