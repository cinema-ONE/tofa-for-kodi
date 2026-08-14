"""The format badges a poster card carries, and the labels they can be.

The macOS app stacks up to three small pills under the rating chip -- 4K, DV,
ATMOS -- describing the file rather than the title. This is the card version
of Detail's badge row, and deliberately a SHORTER one: Detail says "1080p" and
"DTS-HD MA 7.1", a card says nothing about resolution unless it is 4K and
drops the channel count.

WHY THE LABELS ARE A CLOSED SET. Kodi cannot size a control to a list item's
own text -- width is fixed in an item layout -- so a pill that hugs "DV" and
one that hugs "DTS-HD MA" cannot be the same control with different text.
Each badge is therefore a PRE-RENDERED image (tools/gen_badge_assets.py) drawn
into a generous box with aspectratio=keep, and only labels in CARD_BADGES have
one. Anything else is dropped rather than drawn wrong.

That makes this module the single source of truth the generator imports, so
the asset set and the runtime set cannot drift apart.

The server's own MediaFormatInfo is the input, never re-derived ffprobe
fields -- see tracks.py and the API's "clients prefer it over re-deriving"
note. `audio.short_label` is what the server already computes as the compact
form, so the mapping below is presentation only.
"""
from __future__ import annotations

#: server label -> the card's shorter, uppercase form.
#:
#: Re-sampled 2026-08-05 against the live library, 1,200 titles (movies AND
#: tv), which turned up three labels the previous 300-title sample had
#: missed: DTS:X (5), HLG (6) and DTS-HD HRA (1). An unmapped label draws
#: NOTHING -- silently, since the runtime filters against CARD_BADGES -- so a
#: 4K Dolby Vision disc with a DTS:X track was showing no audio badge at all.
#: Rare labels are exactly the ones a sample misses and exactly the ones on
#: the discs whose format someone wants to see.
#:
#: Worth re-running after a server release that changes format detection:
#: 0.9.27's "second look at the audio" is what surfaces DTS:X and DTS-HD HRA
#: instead of reporting them as plain DTS.
_SHORTEN = {
    "dolby vision": "DV",
    "atmos": "ATMOS",
    "dts:x": "DTS:X",
    "truehd": "TRUEHD",
    "dts-hd ma": "DTS-HD MA",
    "dts-hd hra": "DTS-HD HRA",
    "dts-hd": "DTS-HD",
    "hdr10+": "HDR10+",
    "hdr10": "HDR10",
    "hlg": "HLG",
    "hdr": "HDR",
    "dd+": "DD+",
    "dd": "DD",
    "dts": "DTS",
    "aac": "AAC",
    "flac": "FLAC",
    "pcm": "PCM",
    "4k": "4K",
}

#: Every label an asset exists for. The generator walks this; the runtime
#: filters against it. Ordered so the generated files read sensibly: the
#: HDR family together, then audio best-first.
CARD_BADGES = ("4K", "3D", "DV", "HDR10+", "HDR10", "HLG", "HDR",
               "ATMOS", "DTS:X", "TRUEHD", "DTS-HD MA", "DTS-HD HRA",
               "DTS-HD", "DTS", "DD+", "DD", "AAC", "FLAC", "PCM",
               # Projection ratios. The server snaps picture_aspect_ratio to
               # this exact set when it lands within 2% of one, so it is
               # closed and small enough to draw. 1.78 is deliberately absent
               # from the CARD path (see card_badges) but its art exists for
               # anywhere that wants to state the shape outright.
               "2.39:1", "2.35:1", "1.85:1", "1.78:1", "1.66:1", "1.33:1")

#: picture_aspect_ratio -> chip. Keyed on the snapped value, so a float that
#: the server did NOT snap (an oddity outside 2% of any canonical ratio) gets
#: no chip rather than a spurious one.
ASPECT_BADGES = {
    2.39: "2.39:1", 2.35: "2.35:1", 1.85: "1.85:1",
    1.78: "1.78:1", 1.66: "1.66:1", 1.33: "1.33:1",
}


def aspect_badge(ratio) -> str:
    """The chip for a snapped projection ratio, or "" for anything else.

    Exact-matches the canonical set rather than rounding: the server has
    already decided whether this picture IS 2.39, and a client that rounds
    2.30 up to 2.35 would be inventing a verdict the server declined to
    make."""
    try:
        value = round(float(ratio), 2)
    except (TypeError, ValueError):
        return ""
    return ASPECT_BADGES.get(value, "")

#: How many fit down the left edge of a poster before they reach the caption.
MAX_CARD_BADGES = 3

#: DynamicRangeKind, which unlike the audio labels IS a declared enum in the
#: API -- so the video badge is keyed off it rather than off free text, and a
#: new flavour would arrive as a visible contract change instead of silently.
#: `sdr` is a real answer that is deliberately not a badge, exactly as on
#: Detail; `hdr` is the API's own legacy bucket for rows probed before the
#: flavour was recorded.
_DYNAMIC_RANGE = {
    "dolby_vision": "DV",
    "hdr10_plus": "HDR10+",
    "hdr10": "HDR10",
    "hlg": "HLG",
    "hdr": "HDR",
    "sdr": "",
}

#: Coarser badge for an audio label we do not have an exact asset for.
#:
#: There is NO enum for audio labels -- the API types `short_label` as a plain
#: string and its description ends in "| ...", i.e. openly extensible -- so a
#: new one can appear in any server release and, before this, drew nothing at
#: all. A family badge is less precise but TRUE: DTS:X is a DTS format, and
#: saying DTS beats saying nothing about a disc someone chose for its sound.
#:
#: Order is most specific first, and Atmos leads deliberately: the label names
#: its carrier ("TrueHD Atmos", "DD+ Atmos") and ATMOS is what the reference
#: apps show for those. `eac3` precedes `ac3` because it contains it.
_FAMILIES = (
    ("atmos", "ATMOS"),
    ("dts-hd ma", "DTS-HD MA"),
    ("dts-hd", "DTS-HD"),
    ("dts", "DTS"),
    ("truehd", "TRUEHD"),
    ("dd+", "DD+"), ("eac3", "DD+"), ("e-ac3", "DD+"),
    ("ac3", "DD"), ("dd", "DD"),
    ("aac", "AAC"), ("flac", "FLAC"), ("pcm", "PCM"),
)

#: Labels already reported, so a shelf of 50 cards logs a new one once.
_UNMAPPED_SEEN: set = set()


def _short(label) -> str:
    text = str(label or "").strip()
    return _SHORTEN.get(text.lower(), "")


def _family(label) -> str:
    """The nearest coarser badge for an unrecognised label, or ""."""
    text = str(label or "").strip().lower()
    for needle, badge in _FAMILIES:
        if needle in text:
            return badge
    return ""


def _note_unmapped(kind: str, value) -> None:
    """Say once, in the log, that the server used a label we do not know.

    The whole failure mode this guards is silence: an unknown label was
    filtered out by CARD_BADGES and nothing said so, which is why DTS:X went
    unbadged until someone sampled the library. Even with the family fallback
    the exact badge is still worth adding, and this is what says so.

    `log` is imported lazily and its failure ignored on purpose: this module
    is also imported standalone, outside Kodi, by tools/gen_badge_assets.py,
    and it must stay importable there.
    """
    key = (kind, str(value))
    if key in _UNMAPPED_SEEN:
        return
    _UNMAPPED_SEEN.add(key)
    try:
        from . import log
    except ImportError:
        return
    log.info("badges: no exact badge for {0} {1!r}; "
             "add it to _SHORTEN and CARD_BADGES".format(kind, value))


def card_badges(item: dict, show: bool = True) -> list[str]:
    """Up to MAX_CARD_BADGES labels for one card, most distinctive first.

    `show` is the profile's own `show_format_badges`; False returns nothing,
    the same switch Detail's row honours. Order is resolution, then dynamic
    range, then audio -- what the macOS app stacks top to bottom.
    """
    if not show:
        return []
    fmt = (item or {}).get("format") or {}
    out: list[str] = []

    if fmt.get("is_4k"):
        out.append("4K")

    video_early = fmt.get("video") or {}
    # 3D ranks straight after 4K: it is the most distinctive thing a card can
    # say, and unlike the audio badges it changes whether the viewer can play
    # the title at all on a 2D setup. Server 0.9.28's `stereo_3d`; the exact
    # layout is Detail's job, a card only has room to say THAT it is 3D.
    if video_early.get("stereo_3d"):
        out.append("3D")

    video = fmt.get("video") or {}
    # Off the DynamicRangeKind enum, not the free-text label: it is the one
    # part of MediaFormatInfo with a declared closed set. `null` means
    # unprobed and gets nothing, as before; `sdr` maps to "" because it is a
    # real answer that is not a badge.
    kind = video.get("dynamic_range")
    if kind:
        label = _DYNAMIC_RANGE.get(str(kind).lower())
        if label is None:
            # A flavour added to the enum since this shipped. Anything that
            # is not sdr is high dynamic range, so the generic badge is
            # honest, and better than a 4K HDR disc showing no HDR badge.
            label = _short(video.get("short_label") or video.get("label")) or "HDR"
            _note_unmapped("dynamic_range", kind)
        if label:
            out.append(label)

    audio = fmt.get("audio") or {}
    # short_label is the server's own compact form. `audio == null` means
    # "do not badge" rather than "unknown" (project_server_format_badges).
    raw = audio.get("short_label") or audio.get("label")
    if raw:
        label = _short(raw)
        if not label:
            # No enum exists for these, so an unknown one is expected rather
            # than exceptional -- fall back to the family and say so.
            label = _family(raw)
            _note_unmapped("audio", raw)
        if label:
            out.append(label)

    # Aspect goes LAST, and never for 16:9. A projection ratio is worth
    # saying when it is unusual; "1.78:1" on nine cards out of ten is noise
    # that would push a genuinely rare DTS:X or HDR10+ chip off a card with
    # only MAX_CARD_BADGES slots.
    aspect = aspect_badge(fmt.get("picture_aspect_ratio"))
    if aspect and aspect != "1.78:1":
        out.append(aspect)

    return [b for b in out if b in CARD_BADGES][:MAX_CARD_BADGES]


def apply(mli, item: dict, show: bool = True) -> None:
    """Set a card ListItem's badge_fmt_N properties.

    ONE call site's worth of work, offered as a helper because the card
    family has seven independent builders across three files and no shared
    constructor -- the `rating` property is already set seven separate times.
    Anything that sets `rating` should set these too, or a screen quietly
    ships cards without badges (project_card_fragment_drift).

    Always writes all MAX_CARD_BADGES properties, including the empty ones:
    ManagedListItem reuses items as a list scrolls, so a slot left unset
    keeps whatever the previous title put there.
    """
    labels = card_badges(item, show)
    for index in range(MAX_CARD_BADGES):
        value = ""
        if index < len(labels):
            value = "badge-fmt-%s.png" % (
                labels[index].lower().replace("+", "plus").replace(" ", "-"))
        mli.setProperty("badge_fmt_%d" % (index + 1), value)
