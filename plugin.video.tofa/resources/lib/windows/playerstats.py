# -*- coding: utf-8 -*-
"""What is actually playing, as the two readouts of TV-DESIGN 8.11.

Two sources of truth, and keeping them apart is the whole point of this
module. The *negotiation* says what the server decided to send -- delivery
method, container, the codecs it believes are in the file. Kodi's
`Player.Process(...)` says what this box is actually doing with it --
which decoder picked it up, at what size, in hardware or not. They can
disagree, and when they do that disagreement is the interesting reading:
a file the server called DirectPlay that landed on a software decoder is
exactly the case a viewer is trying to diagnose when they open this.

So SOURCE/STREAM come from the negotiation, VIDEO/AUDIO from Kodi, and
nothing here re-derives one from the other.

Missing values render as an em dash rather than vanishing. The panel's
geometry is fixed (see script-tofa-player.xml), so a hidden row would
leave a hole in the middle of a section -- and "Kodi does not report
this" is a real answer that a reader diagnosing a problem needs to be
able to see. The reference app does the same, showing `23.98 -> - fps`.

The reference's SYNC / PACING / HEALTH / NETWORK sections are absent
rather than dashed out: Kodi exposes no equivalent for A/V skew, render
jitter, frame drops or stream bitrate, so those would be four whole
sections of em dashes. See reference_kodi_player_infolabels for what was
probed and what came back empty.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import xbmc

from . import theme
from .. import regional, tracks
from ..playback import is_direct

MISSING = "—"  # em dash

# Modes, in the order the stats button cycles them.
OFF = ""
PILL = "pill"
PANEL = "panel"
CYCLE = (OFF, PILL, PANEL)

# Substrings that mean a decoder is running on dedicated silicon rather
# than on the CPU. Kodi names most decoders after the ffmpeg codec plus the
# hwaccel that took it -- "ff-h264-vaapi" on this desktop -- so the
# accelerator's own name is the signal and a bare "ff-h264" is software.
_HW_MARKERS = (
    "vaapi", "vdpau", "nvdec", "cuda", "dxva", "qsv",
    "v4l2", "amlogic", "mediacodec", "videotoolbox", "drmprime",
    "mmal", "rkmpp",
)

# ...but some platforms do not follow that pattern at all: they name the
# decoder after the SILICON, with no ffmpeg prefix and no accelerator
# suffix. Matched on the prefix rather than as a substring, because these
# are two and three characters long and a substring test for "am-" would
# fire on anything.
#
# `am-` is what cost us this: the CoreELEC box reports **`am-h264`**, and
# the list above only had "amlogic" and "aml-", so AMLogic's hardware
# decoder was labelled "sw" on the one box that matters. Measured on the
# box 2026-08-07, where the pill read "AVC sw" over `am-h264`.
_HW_PREFIXES = ("am-", "vtb-", "mmal-")

# Audio that is not decoded here AT ALL -- the bitstream goes to the AVR
# and it does the work. Kodi reports `pt-ac3`, `pt-dts`, `pt-eac3`. Calling
# that "sw" is wrong in a more interesting way than the am- bug was: there
# is no decoding on this box to be soft or hard about.
_PASSTHROUGH_PREFIX = "pt-"


def _label(name: str) -> str:
    """An infolabel, or "" if this Kodi has no such label.

    KODI ECHOES THE QUERY BACK when it cannot resolve one. Ask a stock build
    for `Player.Process(amlogic.displaymode)` and it answers with the string
    `"Player.Process(amlogic.displaymode)"`, not "". Measured on the
    development box 2026-08-07, where the panel duly printed
    `Display   Player.Process(amlogic.displaymode)`.

    That never mattered while every label we asked for existed everywhere.
    It matters now: the whole point of the PLATFORM class is that a box
    without the silicon shows no row, and an echoed query is a non-empty
    value that defeats the test. Normalised here rather than at each call
    site, so a future platform-specific label cannot reintroduce it."""
    try:
        value = (xbmc.getInfoLabel(name) or "").strip()
    except (RuntimeError, TypeError):
        return ""
    return "" if value == name else value


def _number(name: str) -> Optional[float]:
    """A Player.Process number, with Kodi's locale grouping removed.

    These come back display-formatted -- `1,920` for a width, `48,000` for
    a sample rate -- so they are text that happens to look numeric, and
    int() on them raises."""
    raw = _label(name).replace(",", "").replace(" ", "").replace(" ", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _colored(text: str, hex_rgb: str) -> str:
    """Kodi's inline colour markup. Alpha is always FF: these are opaque
    words inside a label whose own colour already carries the tier."""
    return f"[COLOR FF{hex_rgb}]{text}[/COLOR]" if text else text


def _join(*parts: str) -> str:
    """Values are middot-separated runs, and a missing run drops out of the
    join rather than leaving a dangling separator."""
    kept = [p for p in parts if p]
    return " · ".join(kept) if kept else MISSING


# --------------------------------------------------------------- delivery --


def _delivery(nego: dict[str, Any]) -> str:
    """How the server chose to send this, tinted only when it is degraded.

    The healthy case is left in ordinary body colour on purpose -- the
    spec's "keep healthy states quiet" -- so the amber means something when
    it does appear. This row is also the honest replacement for the
    transcode confirmation dialog that used to interrupt playback here;
    see player.py's _start_playback."""
    method = nego.get("play_method") or ""
    mode = nego.get("decision_mode") or ""
    if not method:
        return MISSING
    body = _join(method, mode)
    return body if is_direct(nego) else _colored(body, theme.STATUS_DEGRADED)


def _reason(nego: dict[str, Any]) -> str:
    """Why the server transcoded, on its own row.

    Its own row because the server writes these as whole sentences --
    "Transcoding to match selected quality (360p (750 kbps))" -- which
    appended to the delivery row overflowed the panel and truncated the one
    part a viewer actually opened this to read.

    Only when it actually transcoded. The server populates transcode_reasons
    on a DirectPlay decision too, describing what would have forced its hand
    had it gone the other way ("Audio codec 'dts' not playable for HLS"), and
    showing that in warning amber next to a healthy delivery reads as a fault
    on a stream that is playing perfectly.

    Empty rather than an em dash on a direct play: the row is PLATFORM class
    now, so "" removes it altogether and gives the slot back."""
    if is_direct(nego):
        return ""
    reasons = [str(r) for r in (nego.get("transcode_reasons") or []) if r]
    if not reasons:
        return MISSING
    return _colored("; ".join(reasons), theme.STATUS_DEGRADED)


def _delivery_short(nego: dict[str, Any]) -> str:
    """The pill's version: the method alone, tinted the same way.

    The panel spells out the decision mode and the transcode reasons beside
    it; repeating all of that in a one-line pill costs a third of its width
    to say what the panel is one keypress away from saying properly."""
    method = nego.get("play_method") or ""
    if not method:
        return MISSING
    return method if is_direct(nego) else _colored(method, theme.STATUS_DEGRADED)


def _quality(selection) -> str:
    """The ceiling WE asked for, not one the server reports back.

    max_bitrate is the only half of the pick that reaches the wire (as a
    capability-profile query param), so a tier name without it would
    describe a request the server never saw."""
    tag = getattr(selection, "quality_tag", None)
    kbps = getattr(selection, "max_bitrate", None)
    if not tag and not kbps:
        return "Original · no cap"
    cap = f"cap {regional.decimal(kbps / 1000.0, 1)} Mb/s" if kbps else ""
    return _join(tag or "Auto", cap)


# ------------------------------------------------------------------ video --


# Standard frame heights, with the macroblock padding h264/hevc add. Kodi
# reports what the DECODER allocated, and both codecs round the coded height
# up to a multiple of 16, so a 1080-line film is reported as 1088. Neither
# "1088" nor a silent rewrite to 1080 is right on its own: the first reads as
# a fault, the second hides a real number. So the padded value is snapped
# back to the standard tier it belongs to -- and only when it is within one
# macroblock of one, which leaves a genuinely odd size showing as itself.
_STANDARD_HEIGHTS = (2160, 1440, 1080, 720, 576, 480, 360)


def _unpad(height: Optional[float]) -> Optional[int]:
    if not height:
        return None
    for standard in _STANDARD_HEIGHTS:
        if standard <= height <= standard + 15:
            return standard
    return int(height)


def _resolution_label(height: Optional[float]) -> str:
    """`1080p` for the pill, from the unpadded height."""
    unpadded = _unpad(height)
    return f"{unpadded}p" if unpadded else ""


def _dynamic_range(nego: dict[str, Any]) -> str:
    """HDR10/HLG/Dolby Vision, preferring what Kodi made of the stream.

    Both readings describe the SOURCE. The old comment here claimed Kodi's
    was "the output" and that mistake escaped into the paired panel, where
    it put VideoPlayer.HdrType in the OUTPUT column and had a windowed
    desktop reporting Dolby Vision output. It is not an output reading: it
    is Kodi's view of the file, which is simply better informed than the
    negotiation's video_range (the server can only describe what it sent).

    What the display actually RECEIVED is a different question, and only
    CoreELEC answers it, via Player.Process(amlogic.eoft_gamut)."""
    hdr = _label("VideoPlayer.HdrType")
    if hdr:
        return hdr.upper()
    return (nego.get("video_range") or "SDR").upper()


def _decoder(name: str) -> tuple[str, str]:
    """(decoder, "hw" / "sw" / "passthrough").

    Empty name means playback has not started."""
    if not name:
        return "", ""
    lowered = name.lower()
    if lowered.startswith(_PASSTHROUGH_PREFIX):
        return name, "passthrough"
    if lowered.startswith(_HW_PREFIXES):
        return name, "hw"
    return name, "hw" if any(m in lowered for m in _HW_MARKERS) else "sw"


# ------------------------------------------------------------------ audio --


_CHANNEL_LAYOUTS = {
    1: "Mono", 2: "Stereo", 3: "2.1", 6: "5.1", 7: "6.1", 8: "7.1",
}


def _channels(layout: str) -> str:
    """`7.1 (FL, FR, FC, LFE, BL, BR, SL, SR)` from Kodi's raw layout.

    The layout string is what the decoder is OUTPUTTING, which on a box
    that downmixes is not the track's own channel count -- that difference
    is one of the things this overlay exists to make visible, so the
    speaker list is kept rather than collapsed to the count alone."""
    if not layout:
        return MISSING
    names = [c.strip() for c in layout.split(",") if c.strip()]
    if not names:
        return MISSING
    tier = _CHANNEL_LAYOUTS.get(len(names))
    return f"{tier} ({layout})" if tier else layout


# ------------------------------------------------------------------ build --


#: A row's availability class, which is the whole of the panel's
#: flexibility. See _columns.
#:
#: CORE   -- every platform could answer this, so a missing value is itself
#:           the answer and renders as an em dash. That was the original
#:           panel's rule for everything, and the comment in the skin
#:           defending it is right -- for these.
#: PLATFORM -- only some hardware has it at all. Shown when present, omitted
#:           entirely when not. An Intel box must not display four permanent
#:           dashes for AMLogic silicon it can never have, and a section
#:           whose rows are all absent disappears header and all.
CORE = "core"
PLATFORM = "platform"


def _row(key: str, value: str, kind: str = CORE):
    return (key, value, kind)


def _aspect(value) -> str:
    """A display aspect as the trade writes it: 2.39:1, 1.78:1.

    The server sends a float (presented width / presented height). Two
    decimals because that is what distinguishes the ratios anyone cares about
    -- 2.35 from 2.39, 1.85 from 1.78 -- and no more, because the third is
    encoder noise."""
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{ratio:.2f}:1" if ratio > 0 else ""


def _pair(key: str, source: str, output: str, kind: str = CORE, warn: bool = False):
    """One row of the paired panel: the same fact, twice.

    Left is what arrived, right is what this box did with it. Reading them
    on ONE line is the whole point -- "1920×1080 -> 3840×2160" answers a
    question that two numbers in separate columns only hint at."""
    return (key, source, output, kind, warn)


def _screen() -> tuple[str, str]:
    """(resolution, refresh) of the actual output, from ONE generic label.

    `System.ScreenResolution` answers on every platform, which matters --
    the CoreELEC-only `amlogic.displaymode` says the same thing but only on
    the box. Measured:

        box   "3840x2160 @ 25.00 Hz - Full screen"
        mac   "1920x1080 - Windowed"

    so the refresh half is present only when there is a mode to report, and
    a windowed desktop honestly has none."""
    raw = _label("System.ScreenResolution")
    if not raw:
        return "", ""
    size = re.match(r"\s*(\d+)\s*x\s*(\d+)", raw)
    resolution = f"{size.group(1)}×{size.group(2)}" if size else ""
    hz = re.search(r"@\s*([0-9.]+)", raw)
    return resolution, (f"{float(hz.group(1)):g} Hz" if hz else "")


def _judders(fps: Optional[float], refresh: str) -> bool:
    """Would this frame rate need uneven pulldown at this refresh?

    Clean when the display runs at an integer multiple of the source: 25 in
    50 is every frame twice, 24 in 24 is one for one. 23.976 in 59.94 is
    2.5, which cannot be done evenly -- so frames are held for two intervals
    then three, and that is the judder a viewer opens this panel to explain.

    Only THIS earns amber. A 1080p file on a 4K panel is upscaling, which is
    normal and says nothing; flagging it would train the eye to ignore the
    colour."""
    if not fps or fps <= 0 or not refresh:
        return False
    try:
        hz = float(refresh.split()[0])
    except (ValueError, IndexError):
        return False
    if hz <= 0:
        return False
    ratio = hz / fps
    if ratio < 0.99:            # display slower than the source: not pulldown
        return True
    return abs(ratio - round(ratio)) > 0.02


def _channel_count(layout: str) -> int:
    return len([c for c in layout.split(",") if c.strip()]) if layout else 0


def _amlogic(name: str) -> str:
    """A CoreELEC-only readout. Empty everywhere else, which is exactly what
    makes it PLATFORM class.

    These are the most valuable numbers on the panel and the reason it was
    rebuilt: they describe what the box is ACTUALLY putting on the wire --
    output mode, bit depth and chroma, transfer and gamut -- rather than what
    the file claims. CoreELEC's own Estuary reads them; stock Kodi has no
    such labels."""
    return _label(f"Player.Process(amlogic.{name})")


def _cpu() -> str:
    """Per-core percentages collapsed to one average, plus temperature.

    System.CpuUsage reports "#0: 2.4% #1:  12% #2: 7.7% #3: 9.6%", which is
    four facts too many for a row that has to fit beside a label."""
    raw = _label("System.CpuUsage")
    pcts = [float(m) for m in re.findall(r"([0-9.]+)%", raw)] if raw else []
    parts = []
    if pcts:
        parts.append("%d%%" % round(sum(pcts) / len(pcts)))
    # "Not available" is what a platform without a sensor answers, and it is
    # not empty, so it sailed through into the row as a fact. Require a digit.
    temp = _label("System.CPUTemperature")
    if temp and any(c.isdigit() for c in temp):
        parts.append(temp)
    return _join(*parts)


def _deint() -> str:
    """The deinterlacer, when there is one doing something."""
    method = _label("Player.Process(deintmethod)")
    return "" if method.lower() in ("", "none") else method


def _memory() -> str:
    used = _label("System.Memory(used.percent)")
    return used if used else ""


def _rows(nego: dict[str, Any], selection, position: str,
             buffer_pct: Optional[float]):
    """The panel's rows: each fact as it ARRIVED and as it came OUT.

    That split is not decoration. Nearly every playback question here turns
    out to be "is the difference server-side or box-side" -- a transcode we
    did not want, a decode falling back to software, HDR not actually
    reaching the panel. Putting the two readings of one fact on ONE line is
    what turns that from a comparison the reader has to make into one the
    panel has already made: `1920×1080 -> 3840×2160` is a sentence.
    """
    width, height = _number("Player.Process(videowidth)"), _number("Player.Process(videoheight)")
    fps = _number("Player.Process(videofps)")
    decoder, engine = _decoder(_label("Player.Process(videodecoder)"))
    audio_decoder, audio_engine = _decoder(_label("Player.Process(audiodecoder)"))
    rate = _number("Player.Process(audiosamplerate)")
    bits = _number("Player.Process(audiobitspersample)")

    frame = f"{int(width)}×{_unpad(height)}" if width and height else ""

    buffer_row = MISSING
    if buffer_pct is not None:
        text = f"{int(buffer_pct)}%"
        # Amber below a fifth: at that point a stall is a live possibility
        # and the reader is probably here because they just saw one.
        buffer_row = _colored(text, theme.STATUS_DEGRADED) if buffer_pct < 20 else text

    interlaced = _label("Player.Process(videoscantype)").lower() == "i"
    dar = _label("Player.Process(videodar)")
    sink = _label("Player.Process(audiochannelssink)")
    vbitrate = _label("VideoPlayer.VideoBitrate")
    abitrate = _label("VideoPlayer.AudioBitrate")

    out_resolution, out_refresh = _screen()
    channels = _label("Player.Process(audiochannels)")
    # PASSTHROUGH BREAKS THE SINK READING, and this was very nearly shipped
    # as a false alarm. On the box, a 5.1 E-AC-3 Atmos track bitstreamed to
    # the AVR reports audiochannels "FL, FR, FC, LFE, BL, BR" against a sink
    # of "FL, FR" -- which looks exactly like a downmix and is not one. The
    # box decodes nothing; the AVR gets the stream whole. Kodi is describing
    # a PCM sink it is not using.
    #
    # So on passthrough the sink is not reported at all (an em dash: what the
    # AVR did with it is not visible from here) and nothing is flagged.
    # Telling a viewer their Atmos had been crushed to stereo would be the
    # worst kind of wrong: confident, prominent, and backwards.
    passthrough = _label("Player.Process(audiodecoder)").lower().startswith(
        _PASSTHROUGH_PREFIX)
    downmixed = bool(not passthrough and sink and channels
                     and _channel_count(sink) < _channel_count(channels))

    # Not every fact HAS an opposite number, and inventing one is worse than
    # leaving the cell empty: pairing "Container" with a bitrate would put two
    # unrelated readings on one line and imply they answer each other. So the
    # sections that are inherently one-sided stay one-sided -- DELIVERY is all
    # server, SYSTEM is all box -- and only the rows where the same fact
    # exists twice are actually paired.
    rows = [
        ("VIDEO", None),
        # Aspect rides with the resolution, where it belongs: it describes
        # the same rectangle. Interlacing gets the standard "1080i" suffix
        # rather than a word, and only when it IS interlaced -- nearly
        # everything is progressive, so saying so on every row is noise that
        # crowds out the number next to it.
        _pair("Resolution",
              _join(f"{int(width)}×{_unpad(height)}{'i' if interlaced else ''}"
                    if width and height else "", dar),
              out_resolution or MISSING),
        # PICTURE aspect, which is the server's and ONLY the server's: it is
        # the active image with any baked-in matte discounted, so a 2.39:1
        # film in a 1.78:1 container reads 2.39 here and 1.78 on the box.
        # Kodi cannot derive it -- it sees the coded rectangle, mattes and
        # all. Server 0.9.28 (`picture_aspect_ratio`); PLATFORM, so a server
        # that does not send it loses the row rather than showing a dash.
        _pair("Picture",
              # Server side: the picture inside the frame. Falls back to the
              # coded frame's DAR, because the contract is explicit that
              # an absent value means nobody has detected one yet, and is
              # never a finding that the picture fills its frame -- it is
              # filled lazily, so the first
              # play of a file has no answer and the next one does.
              (_aspect(nego.get("picture_aspect_ratio"))
               or _aspect(nego.get("display_aspect_ratio"))),
              # Box side: what Kodi thinks it is drawing. `videodar`, NOT the
              # server's own display_aspect_ratio -- an earlier version of
              # this row put a SERVER number in the box column, which is the
              # one thing this panel exists not to do.
              dar or MISSING,
              kind=PLATFORM),
        _pair("Frame rate",
              f"{fps:g} fps" if fps else MISSING,
              out_refresh or MISSING,
              warn=_judders(fps, out_refresh)),
        # ONLY the AMLogic gamut readout may sit in the output cell.
        # VideoPlayer.HdrType describes the STREAM, not what reached the
        # panel, so using it as a fallback here put a source reading in the
        # output column and announced "DOLBYVISION" output on a windowed
        # desktop that was doing nothing of the kind. Caught on sight by the
        # owner, 2026-08-08. An em dash is the honest answer where no label
        # can say what the display actually received.
        _pair("Dynamic range", _dynamic_range(nego),
              _amlogic("eoft_gamut") or MISSING),
        _pair("Codec",
              tracks.video_codec_label(nego.get("video_codec")) or MISSING,
              _join(decoder, engine)),
        # Output only. What the box puts on the wire (bit depth, chroma, and
        # any deinterlacing) is worth knowing; the negotiation carries no
        # counterpart to set against it, since bit_depth lives on the media
        # record rather than in the stream info. Scan and aspect used to fill
        # this cell, but they describe the RECTANGLE, not the pixels, and
        # have moved up to Resolution where they read properly.
        #
        # _deint() drops "none", Kodi's answer for a progressive source that
        # needs no deinterlacing, which is the normal case and not worth a
        # word.
        _pair("Pixels", "", _join(_amlogic("pixformat"), _deint()), PLATFORM),
        ("AUDIO", None),
        _pair("Codec",
              tracks.audio_codec_name(
                  _label("VideoPlayer.AudioCodec") or nego.get("audio_codec")) or MISSING,
              _join(audio_decoder, audio_engine)),
        _pair("Channels", _channels(channels),
              MISSING if (passthrough or not sink) else _channels(sink),
              CORE, warn=downmixed),
        _pair("Format",
              _join(f"{rate / 1000:g} kHz" if rate else "",
                    f"{int(bits)} bit" if bits else "",
                    f"{abitrate} kbps" if abitrate else ""),
              ""),
        ("DELIVERY", None),
        _pair("Method", _delivery(nego), ""),
        # PLATFORM so a DirectPlay loses the row entirely rather than showing
        # an em dash against a question that does not apply -- and so the
        # panel gets the slot back for the sections that do.
        _pair("Reason", _reason(nego), "", PLATFORM),
        _pair("Container", nego.get("container") or MISSING, ""),
        _pair("Quality", _quality(selection),
              f"{vbitrate} kbps" if vbitrate else "", PLATFORM),
        ("SYSTEM", None),
        _pair("Buffer", "", buffer_row),
        _pair("Load", "", _join(_cpu(), _memory()), PLATFORM),
        _pair("Position", "", position or MISSING),
    ]
    return _prune_pairs(rows)


def _prune_pairs(rows):
    """Drop absent PLATFORM rows, then any section header left with nothing
    under it.

    The second half matters as much as the first: a VIDEO header over four
    removed rows is worse than the dashes this replaced.

    A PLATFORM row goes only when BOTH sides are empty. One-sided is normal
    here -- DELIVERY has no output, SYSTEM has no source -- so a blank cell
    is not evidence that the row has nothing to say."""
    kept = []
    for entry in rows:
        if len(entry) == 2:                    # a section header
            kept.append(entry)
            continue
        key, source, output, kind, warn = entry
        if kind == PLATFORM and not (source or "").strip() and not (output or "").strip():
            continue
        kept.append((key, source or "", output or "", kind, warn))

    out = []
    for i, entry in enumerate(kept):
        if len(entry) == 2:
            following = kept[i + 1:]
            has_rows = bool(following) and len(following[0]) != 2
            if not has_rows:
                continue
        out.append(entry)
    return out


def build(nego: dict[str, Any], selection, position: str) -> dict[str, str]:
    """Window properties for the PILL only, in one pass with the panel's
    columns so the two can never disagree -- they are two views of the same
    reading, and the panel is what a viewer opens after the pill showed them
    something surprising.

    The panel's own rows are NOT properties any more; they are list items,
    because their number varies by platform. See columns()."""
    buffer_pct = _number("Player.CacheLevel")

    height = _number("Player.Process(videoheight)")
    fps = _number("Player.Process(videofps)")
    decoder, engine = _decoder(_label("Player.Process(videodecoder)"))
    return {
        "stats_pill": _join(
            _delivery_short(nego),
            _join(_resolution_label(height), _dynamic_range(nego)).replace(" · ", "·"),
            # Codec and engine are one phrase ("AVC hw"), not two facts, so
            # they get a space where every other run gets a middot.
            " ".join(p for p in (tracks.video_codec_label(nego.get("video_codec")),
                                 engine) if p),
            f"{fps:g} fps" if fps else "",
            f"buffer {int(buffer_pct)}%" if buffer_pct is not None else "",
        ),
    }


def rows(nego: dict[str, Any], selection, position: str):
    """The panel's row list.

    Each entry is either `(HEADING, None)` or
    `(key, source, output, kind, warn)`. The caller turns them into list
    items; nothing here knows about Kodi controls."""
    return _rows(nego, selection, position, _number("Player.CacheLevel"))
