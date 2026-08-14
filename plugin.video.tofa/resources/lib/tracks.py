# -*- coding: utf-8 -*-
"""Human labels for the stream/{id}/info track and quality-tier payloads.

Its own module rather than private helpers inside the options dialog: the
Edition picker and the dialog's own subtitle already render the same facts
from a different payload, and two independent spellings of "DTS-HD MA 7.1"
is exactly the kind of drift that makes a client look like it doesn't know
what it's playing.

Everything here degrades to "" rather than guessing. A missing field on this
server is common (Hugo's 4K file reports `profile: null` on a track ffprobe
calls DTS-HD MA), and an invented value is worse than a short label: the
whole point of this surface is that a viewer can trust it.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import xbmc

from . import regional

# Wire codec name -> what the format is actually called. Only entries where
# the raw name is wrong or unreadable on screen; anything absent falls
# through to .upper(), which is right for aac/flac/opus/ac3.
_AUDIO_CODEC = {
    "dts": "DTS",
    "dtshd": "DTS-HD",
    # Kodi's own decoder names carry the profile in the codec string where
    # the server carries it in a separate `profile` field, so these two only
    # ever arrive from VideoPlayer.AudioCodec (the player stats overlay).
    "dtshd_ma": "DTS-HD MA",
    "dtshd_hra": "DTS-HD HRA",
    "truehd": "TrueHD",
    "eac3": "Dolby Digital+",
    "ac3": "Dolby Digital",
    "mp2": "MP2",
    "mp3": "MP3",
    "pcm": "LPCM",
}

_SUBTITLE_CODEC = {
    "hdmv_pgs_subtitle": "PGS",
    "dvd_subtitle": "VobSub",
    "dvb_subtitle": "DVB",
    "subrip": "SRT",
    "ass": "ASS",
    "ssa": "SSA",
    "mov_text": "MP4",
    "webvtt": "WebVTT",
}


#: Codecs that are lossless by definition. `dts` is absent on purpose: the
#: family spans lossless (DTS-HD MA) and lossy (DTS, DTS-HD HRA) and only the
#: PROFILE tells them apart -- which is why is_lossless reads that too.
_LOSSLESS_CODECS = frozenset((
    "truehd", "flac", "pcm", "alac", "mlp", "wavpack", "dtshd_ma",
))

#: Profile strings that mean lossless whatever the codec says. The server
#: gives ffprobe's raw profile ("DTS-HD MA", "Dolby TrueHD + Dolby Atmos").
_LOSSLESS_PROFILE = re.compile(r"dts-hd\s*ma|master\s*audio|truehd", re.IGNORECASE)


def is_lossless(track: dict[str, Any]) -> bool:
    """Whether an audio track is a lossless one.

    Codec alone is not enough: the server reports DTS-HD MA as codec `dts`
    with profile `DTS-HD MA`, the same codec string a plain lossy DTS track
    carries. Mars Attacks!'s 4K disc has both.
    """
    if _LOSSLESS_PROFILE.search(str(track.get("profile") or "")):
        return True
    return str(track.get("codec") or "").strip().lower() in _LOSSLESS_CODECS


def audio_quality_key(track: dict[str, Any], playable: Optional[set] = None,
                      stereo_only: Optional[set] = None) -> tuple:
    """Sort key for choosing between audio tracks. LOWEST is best.

    Applied only AFTER language has been matched, so it never trades the
    viewer's language for a better-sounding track in another one.

    The order, and why:

    1. DIRECTLY PLAYABLE first. A codec this client cannot decode makes the
       server transcode the audio, which costs quality on the way through --
       so the best-sounding track we cannot play is not the best choice.
    2. LOSSLESS over lossy. DTS-HD MA over Dolby Digital, TrueHD over DD+.
    3. MORE CHANNELS. 5.1 over 2.0.
    4. The file's own order, so the result is stable rather than arbitrary
       between two equal tracks.

    `stereo_only` names codecs this client can only play in two channels; a
    track in one of those is ranked on what would actually come out, not on
    what the file holds, so a 5.1 track we would hear as stereo does not
    beat a real 5.1 track we can play properly.

    NOT YET CONSIDERED: the box's own channel ceiling. We do not send
    `audio_sink_channels`, so nothing here knows that this Kodi downmixes to
    LPCM 2.0 while the CoreELEC box passes 7.1 through. Ranking on the FILE's
    channels is right for the box that can play them and harmless for the one
    that cannot -- it downmixes either way -- but a real ceiling would let
    this prefer a 5.1 track over a 7.1 one it is about to fold down.
    """
    codec = str(track.get("codec") or "").strip().lower()
    channels = track.get("channels") or 0
    if stereo_only and codec in stereo_only:
        channels = min(channels, 2)
    return (
        0 if (playable is None or codec in playable) else 1,
        0 if is_lossless(track) else 1,
        -channels,
        track.get("index") if isinstance(track.get("index"), int) else 0,
    )


def choose_audio(track_list: list, languages: list,
                 playable: Optional[set] = None,
                 stereo_only: Optional[set] = None) -> Optional[dict]:
    """The audio track to play: preferred LANGUAGE first, best quality within it.

    Language is never traded for quality -- the languages are walked in the
    viewer's priority order and the first one present wins the decision, then
    audio_quality_key picks among that language's tracks.

    Used by the player to choose, and by Detail's Options panel to SHOW the
    choice, so the panel names the track that will actually play.
    """
    from . import langcodes

    for code in languages or []:
        candidates = langcodes.matching(track_list, code)
        if candidates:
            return min(candidates,
                       key=lambda t: audio_quality_key(t, playable, stereo_only))
    return None


def language_name(code: Optional[str]) -> str:
    """ISO code -> English name, via Kodi's own table rather than a map of
    our own. `und` is a real value here, not a missing one, and saying
    "Undetermined" is more honest than showing the raw code."""
    if not code:
        return ""
    if code in ("und", "unknown"):
        return "Undetermined"
    try:
        name = xbmc.convertLanguage(code, xbmc.ENGLISH_NAME)
    except Exception:
        name = ""
    return name or code.upper()


def bitrate_label(kbps: Optional[int]) -> str:
    """`91.7 Mbps` / `4 Mbps` / `750 kbps`.

    One decimal above a megabit and none below, because the second decimal
    of a stream bitrate is noise -- and no decimal at all when it would be
    `.0`, which is how the server writes its own tier labels ("720p (4
    Mbps)"). The two strings sit one dialog apart; they should agree."""
    if not kbps:
        return ""
    if kbps < 1000:
        return f"{int(kbps)} kbps"
    mbps = kbps / 1000.0
    text = regional.decimal(mbps, 1) if mbps < 100 else f"{mbps:.0f}"
    # The trailing ".0" test has to use the REGION's mark, or a German box
    # keeps the "4,0" this is meant to strip.
    zero_tail = regional.decimal_separator() + "0"
    if text.endswith(zero_tail):
        text = text[:-len(zero_tail)]
    return f"{text} Mbps"


def audio_codec_name(codec: Optional[str]) -> str:
    """A bare wire codec name made readable -- `dtshd_ma` -> `DTS-HD MA`.

    Split out from audio_codec_label because the player stats overlay reads
    Kodi's VideoPlayer.AudioCodec, which is a plain string, not one of the
    server's track dicts."""
    codec = (codec or "").strip().lower()
    return _AUDIO_CODEC.get(codec, codec.upper())


def audio_codec_label(track: dict[str, Any]) -> str:
    """`DTS-HD MA` where the server knows the profile, `DTS` where it
    doesn't. The profile is the interesting half -- DTS-HD MA and plain DTS
    are a lossless/lossy difference -- so it wins when present rather than
    being appended to the codec name it already contains."""
    profile = (track.get("profile") or "").strip()
    if profile:
        return profile
    return audio_codec_name(track.get("codec"))


def bit_depth_label(track: dict[str, Any]) -> str:
    """`24-bit`, and only where it means something.

    Server 0.9.28's `bit_depth`, from ffprobe's `bits_per_raw_sample`, so it
    is `None` for every codec that does not report one -- which is most of
    the lossy ones. Shown only for LOSSLESS tracks: 24-bit against 16-bit is
    a real distinction on a FLAC or a TrueHD, and on a lossy stream the
    number describes the decoder's output word length rather than anything
    about the recording, so printing it there would be precise and
    meaningless."""
    depth = track.get("bit_depth")
    if not depth or not is_lossless(track):
        return ""
    try:
        return f"{int(depth)}-bit"
    except (TypeError, ValueError):
        return ""


# `Surround 7.1`, `5.1`, `Stereo`, `Mono` -- a track title that says nothing
# except how many channels the track has.
#
# ONE job now: deciding whether a title is redundant beside the detail
# column (see audio_track_label). It used to have a second, deriving a
# LAYOUT from the title inside channel_label, and that one is gone -- the
# server populates `channel_layout` since 0.9.28. Deleting the constant
# along with it was a NameError in audio_track_label, live on the Options
# dialog: `not title or bool(...)` short-circuits on an empty title, so it
# only fired on the tracks that actually have one, and no test had one.
_LAYOUT_IN_TITLE = re.compile(
    r"^(?:surround\s*)?(\d\.\d|\d\.\d\.\d|stereo|mono)$", re.I)


def channel_label(track: dict[str, Any]) -> str:
    """`7.1`, from the layout the server probed, or the channel count.

    `channel_layout` arrives as ffmpeg spells it, which includes variants
    like `5.1(side)`; the parenthetical names which physical channels carry
    the surrounds and has no bearing on what a viewer is choosing between,
    so it is dropped.

    There used to be a THIRD source between these two: the track's own
    title, parsed for "Surround 7.1" and the like. It existed for one file,
    Hugo's 4K remux, which reported `channels: 8` with
    `channel_layout: null` -- so the count would have said `8ch`, a true
    statement that reads like a different one. Server 0.9.28 populates that
    file correctly (issue #7), and a sweep of 3080 audio tracks across 616
    titles found **zero** whose label the title parse still changes, so it
    is gone.

    The count is NOT gone, and is not dead code: 43 of those 3080 still
    report no layout -- PCM stereo tracks, mostly. It is the only step here
    that is inference rather than transcription (8 channels could in
    principle be 7.1(wide)), so it stays a count and never becomes a
    layout."""
    layout = (track.get("channel_layout") or "").strip()
    if layout:
        return layout.split("(")[0].strip()
    channels = track.get("channels")
    if not channels:
        return ""
    return {1: "Mono", 2: "Stereo"}.get(channels, f"{channels}ch")



# Wire codec name -> what the release naming and the library's own filenames
# call it. Not a display of the ffprobe string: "h264" on screen beside
# "HEVC" would look like two different kinds of fact.
_VIDEO_CODEC = {
    "h264": "AVC",
    "hevc": "HEVC",
    "mpeg2video": "MPEG-2",
    "vc1": "VC-1",
    "mpeg4": "MPEG-4",
    "vp9": "VP9",
    "av1": "AV1",
}


def video_codec_label(codec: Optional[str]) -> str:
    codec = (codec or "").strip().lower()
    return _VIDEO_CODEC.get(codec, codec.upper())


def file_size_label(size_bytes: Optional[int]) -> str:
    """`42.0 GB`, 7.7's "size GB (1 decimal)".

    DECIMAL gigabytes (10^9), not gibibytes. This is the one number here a
    viewer might cross-check against something else, and the two conventions
    differ by 7% -- 42.0 GB is 39.1 GiB for the same file. SI is what "GB"
    means and what the spec's own wording asks for; Plex and Radarr label
    gibibytes as GB, so a viewer comparing the two WILL see different
    numbers for one file. Worth knowing before assuming a bug.

    Below a gigabyte it drops to MB rather than showing "0.0 GB", which is
    what a TV extra or a short would otherwise read as."""
    if not size_bytes:
        return ""
    gb = size_bytes / 1_000_000_000
    if gb < 1:
        # Whole megabytes, and below a gigabyte by definition, so there is
        # nothing here to group or to point.
        return f"{size_bytes / 1_000_000:.0f} MB"
    # The decimal MARK is regional: 42.0 GB in the US, 42,0 GB in Germany.
    return f"{regional.decimal(gb, 1)} GB"


# Where a track title may be cut so the remainder still reads as a phrase.
# Ordered by how clean the break is.
_CLAUSE_BREAKS = (", ", " (", " [", " \u2014 ", " - ", "; ")

# Characters of title the widest row can show beside a language prefix,
# derived from the real font rather than guessed: the label column is 739px
# in tofa_font_row_title (inter_tight_semibold 26), which averages ~12.3px
# per character on this kind of text. Deliberately a CHARACTER budget and
# not a pixel measurement -- textmetrics.py only carries advances for
# tofa_font_metadata, and a second table for one string would have to be
# regenerated every time that font changed. Kodi still ellipsizes whatever
# overruns, so a wrong guess here degrades to today's behaviour rather than
# to a broken row.
_TITLE_BUDGET = 50


def shorten_title(title: str, budget: int = _TITLE_BUDGET) -> str:
    """Cut an overlong track title at a clause boundary, marked with an
    ellipsis.

    Disc commentary titles are sentences, not names: Hugo's 4K file carries
    "Audio Commentary by filmmaker and writer Jon Spira, publisher of \"The
    Lost Autobiography of Georges Méliès\" (2023)" -- 1490px in the row
    font, which no dialog on a 1920 screen can show. Something has to give,
    and where the cut LANDS is the whole difference: Kodi's own truncation
    produced "English · Audio Commentar...", which loses even "a commentary,
    by whom", while cutting at the first clause keeps the part that
    identifies the track.

    The ellipsis is not decoration. Stopping at a comma without one would
    present a shortened title as the whole title, which is the kind of quiet
    lie this panel exists to avoid."""
    title = (title or "").strip()
    if len(title) <= budget:
        return title
    # Search to budget + len(break), not to budget: a break that STARTS on
    # the last allowed character is still usable, and missing it by one cost
    # Hugo's commentary its surname ("...writer Jon..." instead of
    # "...writer Jon Spira...").
    cut = max(title.rfind(b, 0, budget + len(b)) for b in _CLAUSE_BREAKS)
    if cut < budget // 3:
        # No clause break early enough to be worth using -- a single long
        # phrase. Fall back to a word boundary, and to a hard cut if the
        # title has no spaces at all.
        cut = title.rfind(" ", 0, budget)
    if cut < budget // 3:
        cut = budget
    return title[:cut].rstrip(" ,;-") + "\u2026"

def audio_track_label(track: dict[str, Any]) -> tuple[str, str]:
    """(label, detail) for one audio track.

    Label leads with the LANGUAGE, because that is what a viewer is choosing
    between; the server's own `title` ("Surround 7.1") is redundant with the
    detail column when it's a channel description, and irreplaceable when
    it isn't ("Audio Commentary by ..."), so it is kept only in the second
    case. Commentary tracks are the reason this list exists at all on most
    discs, and truncating them to "English" would make the two English rows
    indistinguishable."""
    language = language_name(track.get("language"))
    title = (track.get("title") or "").strip()
    codec = audio_codec_label(track)
    channels = channel_label(track)
    # A title that just restates the layout ("Surround 7.1", "Stereo") adds
    # nothing beside the detail column; anything else is descriptive and kept.
    # Matched against the SHAPE of a channel description rather than against
    # `channels`, so it still holds when the two are spelled differently --
    # which is exactly the case that produced "Surround 7.1 | DTS 8ch".
    generic = not title or bool(_LAYOUT_IN_TITLE.match(title))
    parts = [p for p in (language, "" if generic else shorten_title(title)) if p]
    label = " · ".join(parts) or (codec or "Audio")
    if track.get("atmos"):
        codec = f"{codec} Atmos".strip()
    # Middle dots, not spaces. "DTS-HD MA 7.1 24-bit" reads as one run of
    # tokens where "DTS-HD MA . 7.1 . 24-bit" reads as three facts, which is
    # what they are -- and it is the separator the rest of the app already
    # uses for exactly this (Detail's meta line, the poster caption).
    detail = u" \u00b7 ".join(
        p for p in (codec, channels, bit_depth_label(track)) if p)
    return label, detail


def subtitle_track_label(track: dict[str, Any]) -> tuple[str, str]:
    """(label, detail) for one subtitle track. Forced and SDH are flags a
    viewer picks ON, so they belong in the label, not the codec column."""
    language = language_name(track.get("language"))
    title = (track.get("title") or "").strip()
    flags = []
    if track.get("forced"):
        flags.append("Forced")
    if track.get("sdh"):
        flags.append("SDH")
    parts = [p for p in (language, shorten_title(title)) if p]
    label = " · ".join(parts) or "Subtitle"
    if flags:
        label = f"{label} ({', '.join(flags)})"
    codec = (track.get("codec") or "").strip().lower()
    detail = _SUBTITLE_CODEC.get(codec, codec.upper())
    if track.get("external"):
        detail = " · ".join(p for p in (detail, "External") if p)
    return label, detail


def disambiguate(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Number rows whose (label, detail) pair is identical to another's.

    Hugo's 3D file carries two English PGS tracks with no title, no forced
    flag and no SDH flag between them -- genuinely indistinguishable in the
    payload. Presenting two identical rows and silently applying whichever
    the cursor happened to be on is the worst of the options; numbering them
    at least says the choice is real and which one was taken."""
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        counts[row] = counts.get(row, 0) + 1
    seen: dict[tuple[str, str], int] = {}
    out = []
    for label, detail in rows:
        key = (label, detail)
        if counts[key] > 1:
            seen[key] = seen.get(key, 0) + 1
            label = f"{label} ({seen[key]})"
        out.append((label, detail))
    return out


def quality_tier_label(tier: dict[str, Any]) -> tuple[str, str]:
    """(label, detail) for one quality tier.

    The server's own `label` packs everything into one string ("Original
    (1080p, 44 Mbps)"), which reads fine in a web dropdown and badly in a
    two-column TV row. Rebuilt from the numeric fields rather than parsed
    back apart. Transcode tiers report `width: 0` -- height is the only
    dimension they commit to -- so the resolution is expressed as a height
    throughout, including for the original, where quoting `1920x1080` beside
    a bare `720p` would imply a difference in kind that isn't there."""
    height = tier.get("height") or 0
    rate = bitrate_label(tier.get("bitrate_kbps"))
    if tier.get("is_original"):
        return "Original", " · ".join(p for p in (f"{height}p" if height else "", rate) if p)
    return (tier.get("tag") or (f"{height}p" if height else "")).strip() or "Quality", rate
