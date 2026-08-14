"""The capability profile sent as query params to GET /stream/{id}/info
(brief §4 -- "the critical module"). Values are the CoreELEC/Amlogic profile
Phase 0 confirmed reliably yields DirectPlay/DirectFile (brief §12).

`prefer_hdr10` has no field on purpose -- the brief says never send it.
`dolby_vision_supported` is left unset -- Phase 0 confirmed it's a no-op for
DirectFile on the target server, so there's nothing to gain by setting it
and one less moving part to reason about.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Optional

DEFAULT_VIDEO_CODECS = "hevc,h264,vp9,av1,mpeg2video,vc1"
DEFAULT_AUDIO_CODECS = "truehd,dts,dtshd,eac3,ac3,aac,flac,pcm,opus,mp3,mp2"
DEFAULT_CONTAINERS = "mkv,mp4,m2ts,ts,avi,mov,webm"

_BOOL_FIELDS = (
    "hdr_supported",
    "h264_10bit_supported",
    "deinterlacing_supported",
    "client_render_bitmap_subtitles",
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
    hdr_supported: Optional[bool] = True
    h264_10bit_supported: Optional[bool] = True
    deinterlacing_supported: Optional[bool] = True
    client_render_bitmap_subtitles: Optional[bool] = True
    stereo_only_audio_codecs: Optional[str] = None
    max_bitrate: Optional[int] = None
    include_native_subtitle_rendition: Optional[bool] = None
    dolby_vision_supported: Optional[bool] = None
    #: Only meaningful together. Absent, the server uses what its docs call
    #: "the legacy stereo-AAC pipeline" -- so a forced quality tier costs you
    #: surround. Set them from the OUTPUT ROUTE via for_device(), never by
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
