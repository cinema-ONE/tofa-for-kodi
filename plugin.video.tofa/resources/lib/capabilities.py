# -*- coding: utf-8 -*-
"""What THIS box can actually deliver, asked of Kodi itself.

The format badges describe the FILE. This module answers the different
question the "Plays as X" caveat needs: what will you actually hear and see
when you press Play here? Both answers come out of Kodi's own settings and
info labels, so they follow the box rather than being guessed or configured.

Measured on the two real devices (2026-08-01):

                                  desktop 21.3   cinema/CoreELEC 22.0b   apartment/Android 21.2
    audiooutput.channels          1 -> "2.0"     10 -> "7.1"             8 -> "5.1"
    audiooutput.passthrough       False          True                    False
    ac3/dts/truehd/dtshd          ABSENT         all True                present but master is off
    System.SupportedHdrTypes      ""             "HDR10, HLG, HDR10+,    "HDR10, HLG, HDR10+,
                                                  Dolby Vision up to      Dolby Vision"
                                                  4k60Hz"
    winsystem.ishdrdisplay        ABSENT         True                    True
    System.IsHDRDisplay (bool)    False          False (!)               False (!)
    videoplayer.allowedhdrformats [0, 1]         [0, 1]                  [0, 1]
      ^ "Allowed HDR dynamic metadata formats", Player/Videos/Processing
    winsystem.ishdrdisplay value  --             True                    True
      ^ "Adjust display HDR mode", Player/Videos/Playback -- the single
        HDR toggle; present only on an HDR-capable display
    videoplayer.adjustrefreshrate 0 (off)        3 (on start)            0 (off)
    videoscreen.whitelist         []             []                      16 modes (4K + 1080p)

    Kodi 21.2 publishes System.SupportedHdrTypes, so the desktop's "" is a
    real "no HDR here" rather than a missing label. It stays treated as
    unknown anyway: a build that doesn't implement it would look identical,
    and refusing to downgrade on silence is the safe direction either way.

Three things about Kodi's API that this module exists to encapsulate:

1. **`System.IsHDRDisplay` is current STATE, not capability.** It reads
   false on the DV-capable box, because the GUI is sitting in SDR. Same for
   `System.HdrType`. Capability lives in `winsystem.ishdrdisplay` and
   `System.SupportedHdrTypes`; asking the state pair instead reports "no
   HDR" on the one device that has it.

2. **A setting can be missing, and "missing" is platform-specific.**
   `winsystem.ishdrdisplay` doesn't exist on a non-HDR platform, and the
   per-codec passthrough settings don't exist on the desktop while
   `audiooutput.passthrough` is off -- both answer `Invalid params`. But the
   Android box publishes those same per-codec settings even with the master
   switch off (ac3passthrough True while passthrough False), so a present
   value doesn't mean it applies: everything here is ANDed with the master
   switch rather than trusted alone. `_setting()` returns None for a missing
   setting and every caller treats None as "no".

   Related trap: `Settings.GetSettings` OMITS settings whose visibility
   conditions aren't currently met, while `Settings.GetSettingValue` still
   reads them. `videoplayer.allowedhdrformats` is absent from the former and
   readable via the latter on two of the three devices. Enumerate to
   discover; read values one at a time to decide.

3. **Enum settings carry their own labels.** `audiooutput.channels`
   options come back already spelled "2.0"/"5.1"/"7.1" -- the same grammar
   the badges use -- so there is no hardcoded value->layout table here to
   drift out of date. Same trick reads the display's real mode list off
   `videoscreen.whitelist`'s options.
"""
from __future__ import annotations

import json
import re
import time

import xbmc

#: tofa's AudioFormatKind -> the Kodi setting that decides whether that
#: family can leave the box untouched. Anything not listed here (aac, flac,
#: mp3, pcm, ...) is never bitstreamed, so it is always decoded.
_PASSTHROUGH_SETTING = {
    "dd": "audiooutput.ac3passthrough",
    "dd_plus": "audiooutput.eac3passthrough",
    "dts": "audiooutput.dtspassthrough",
    "dts_es": "audiooutput.dtspassthrough",
    "dts_hd_ma": "audiooutput.dtshdpassthrough",
    "dts_hd_hra": "audiooutput.dtshdpassthrough",
    "dts_x": "audiooutput.dtshdpassthrough",
    "true_hd": "audiooutput.truehdpassthrough",
}
#: videoplayer.allowedhdrformats is a list of enabled advanced HDR outputs.
#: Values come from the setting's own options: 0 = Dolby Vision, 1 = HDR10+.
_DV_HDR_FORMAT = 0

#: Atmos rides a carrier, and which carrier decides which setting applies.
_ATMOS_CARRIER_SETTING = {
    "TrueHD": "audiooutput.truehdpassthrough",
    "DD+": "audiooutput.eac3passthrough",
}


#: Both public queries need Kodi's whole settings tree, and a Detail render
#: asks for them per title. Cached briefly rather than once: these follow the
#: hardware, and someone who switches AVR input or turns passthrough on
#: should see the answer change without restarting the add-on.
_CACHE: dict = {}
_CACHE_TTL = 30.0


def _cached(key: str, build):
    now = time.time()
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < _CACHE_TTL:
        return hit[1]
    value = build()
    _CACHE[key] = (now, value)
    return value


def invalidate() -> None:
    """Drop the cache; for a caller that has just changed a setting itself."""
    _CACHE.clear()


def _all_settings() -> list:
    """Kodi's whole settings tree, fetched once per cache window. Both the
    enum-label lookup and the display-mode list need it, and it is by far the
    most expensive call here."""
    def build():
        resp = _rpc("Settings.GetSettings", {"level": "expert"})
        return resp.get("result", {}).get("settings", []) or []
    return _cached("settings", build)


def _rpc(method: str, params: dict):
    try:
        raw = xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1,
        }))
        return json.loads(raw)
    except Exception:
        return {}


def _setting(setting_id: str):
    """A setting's value, or None when Kodi doesn't have that setting at all
    -- which is how it reports "not applicable here" (see the module
    docstring). Never raises: a capability we can't read is one we don't
    claim."""
    resp = _rpc("Settings.GetSettingValue", {"setting": setting_id})
    if "result" not in resp:
        return None
    return resp["result"].get("value")


def _setting_label(setting_id: str):
    """An enum setting's currently-selected OPTION LABEL, e.g. "5.1" for
    audiooutput.channels. Kodi ships the labels with the options, so this
    never needs a value->text table of its own."""
    for entry in _all_settings():
        if entry.get("id") != setting_id:
            continue
        for option in entry.get("options") or []:
            if isinstance(option, dict) and option.get("value") == entry.get("value"):
                return option.get("label")
    return None


def audio() -> dict:
    """`{channels_label, passthrough, formats}` for the current output.

    `channels_label` is what a DECODED track gets re-mapped to; it is only
    meaningful when a format isn't bitstreamed, which is exactly the
    condition plays_as() applies it under.
    """
    def build():
        passthrough = bool(_setting("audiooutput.passthrough"))
        # DISTINCT setting ids: several formats share one (both DTS-HD
        # variants and DTS:X are one switch), and asking per format would
        # repeat the same RPC.
        ids = set(_PASSTHROUGH_SETTING.values()) | set(_ATMOS_CARRIER_SETTING.values())
        formats = {i: passthrough and bool(_setting(i)) for i in ids}
        # What a DECODED track leaves the box as. "Passthrough off" means the
        # AudioEngine decodes and ships linear PCM -- there is no third option
        # over HDMI or analog, so this is what it is rather than a guess. The
        # one exception is Kodi re-encoding multichannel to AC3 for a
        # stereo-only link, which is a different answer and worth naming.
        transcode = passthrough and bool(_setting("audiooutput.ac3transcode"))
        return {
            "channels_label": _setting_label("audiooutput.channels") or "",
            "passthrough": passthrough,
            "decoded_format": "DD" if transcode else "LPCM",
            "formats": formats,
        }
    return _cached("audio", build)


def audio_delivery() -> dict:
    """What to ask the server to DELIVER when it has to transcode.

    `{"audio_sink_channels": int|None, "audio_fidelity": str|None}`, ready to
    go straight into the capability profile.

    WHY THIS EXISTS. Without `audio_fidelity` the server uses what its own
    API docs call "the legacy stereo-AAC pipeline", and that is not a
    footnote -- measured against Hugo (DTS-HD MA 7.1 + AC3 5.1) on
    2026-08-12, forcing any quality below Original delivered:

        CODECS="avc1.640020,mp4a.40.2"   CHANNELS="2"    stereo AAC

    and the same request with the two parameters below delivered, at the
    identical 4192000 bandwidth:

        CODECS="avc1.640020,ec-3"        CHANNELS="6"    E-AC-3 5.1

    So every forced-quality playback was throwing away surround for nothing.

    WHAT WE ASK FOR IS MATCHED TO WHAT THIS BOX CAN TAKE, which is the whole
    point -- asking for a rendition the player cannot handle would turn a
    stereo downgrade into silence:

    - **E-AC-3 bitstreamed** (`audiooutput.eac3passthrough` on): the AVR gets
      the stream untouched. The best case, and what both boxes here do.
    - **Decoded to multichannel** (sink > 2 channels): Kodi decodes E-AC-3 to
      LPCM and the sink still carries 5.1.
    - **Neither**: a genuinely stereo route that cannot bitstream. Ask for
      nothing and let the server send stereo AAC -- that IS the right answer
      here, and it is the behaviour we have always had.

    The DECODE case deliberately does not consult the global
    `audiooutput.passthrough` flag, which a test caught: passthrough being on
    for OTHER formats does not stop Kodi decoding E-AC-3. With
    `eac3passthrough` off and a 7.1 sink the box decodes happily, so gating
    on the global flag would have refused surround on a route that supports
    it.

    `"atmos"` rather than `"lossless"` on purpose. Both select the same
    E-AC-3 rung on the full-transcode path (verified -- identical playlists),
    but `lossless` prefers a FLAC lane on the copy-video path, and FLAC in
    fMP4 HLS is the rendition the server's docs specifically scope to
    AVPlayer-verified clients. E-AC-3 is the one this box can also pass
    through untouched, so it is the honest ask.
    """
    def build():
        caps = audio()
        channels = channel_count(caps.get("channels_label") or "")
        eac3 = bool((caps.get("formats") or {}).get("audiooutput.eac3passthrough"))
        fidelity = "atmos" if (eac3 or channels > 2) else None
        return {"audio_sink_channels": channels or None,
                "audio_fidelity": fidelity}
    return _cached("audio_delivery", build)


def channel_count(label: str) -> int:
    """"7.1" -> 8, "5.1" -> 6, "2.0" -> 2, "Mono" -> 1. A real COUNT.

    Not to be confused with _channel_count(), which returns 7.1 as the float
    7.1 for SORTING layouts. Using that as a channel count would say a 7.1
    sink carries seven channels, and would compare 5.1 against 2.0 as if the
    ".1" were a fraction. Kodi spells these labels itself (see the module
    docstring), so parsing them is reading its answer, not guessing.
    """
    text = (label or "").strip().lower()
    if text == "mono":
        return 1
    if "." not in text:
        return 0
    try:
        main, lfe = text.split(".", 1)
        return int(main) + int(lfe)
    except (TypeError, ValueError):
        return 0


def bitstreams(audio_format: dict, caps: dict | None = None) -> bool:
    """True when this track leaves the box untouched, i.e. what you hear IS
    what the badge promises.

    `audio_format` is the server's AudioFormatInfo (its `format` enum and,
    for Atmos, its `carrier`)."""
    caps = caps if caps is not None else audio()
    if not caps["passthrough"]:
        return False
    kind = (audio_format or {}).get("format") or ""
    if kind == "atmos":
        setting_id = _ATMOS_CARRIER_SETTING.get((audio_format or {}).get("carrier") or "")
    else:
        setting_id = _PASSTHROUGH_SETTING.get(kind)
    if not setting_id:
        return False        # aac/flac/pcm/... are never bitstreamed
    return bool(caps["formats"].get(setting_id))


def plays_as(audio_format: dict, caps: dict | None = None) -> str:
    """The channel layout you will actually HEAR, or "" when the file plays
    as promised and there is nothing to caveat.

    The trigger is whether the format can be bitstreamed, NOT whether the
    channel counts differ. The real Apple TV app shows "Plays as 2.0" on a
    DTS-HD MA **2.0** title, where the count already matches: the point is
    that the box can't carry DTS-HD MA, so the badge's promise is broken
    even though the layout survives.

    Only ever reports a DOWNGRADE. `audiooutput.config` is "optimized" on
    both real devices, meaning Kodi adapts its output to the source rather
    than forcing the configured layout -- so a 2.0 source on a 7.1 box stays
    2.0, and claiming "Plays as 7.1" there would be an invention.
    """
    if not audio_format:
        return ""
    caps = caps if caps is not None else audio()
    if bitstreams(audio_format, caps):
        return ""
    out = caps["channels_label"]
    source = audio_format.get("channels_label") or ""
    if not out:
        return ""
    if source and _channel_count(source) <= _channel_count(out):
        # Kodi won't upmix past the source, so there is no downgrade to warn
        # about -- the layout survives even though the codec doesn't.
        return source
    return out


def _channel_count(label: str) -> float:
    """"7.1" -> 7.1, "Mono" -> 1.0. Sorts layouts; not a channel count to
    do arithmetic with."""
    if label.strip().lower() == "mono":
        return 1.0
    try:
        return float(label)
    except (TypeError, ValueError):
        return 0.0


def video() -> dict:
    """`{hdr_types, dolby_vision, modes, max_height, switches_modes}`.

    `hdr_types` is Kodi's free-text list ("HDR10, HLG, HDR10+, Dolby Vision
    up to 4k60Hz"), so membership is a substring test, not equality.

    The reliable signal is `winsystem.ishdrdisplay`, NOT `hdr_types`:

      absent        Kodi never registered an "Adjust display HDR mode"
                    switch, so it has no way to put this display into HDR.
                    Nothing HDR gets out, whatever else is set. This is a
                    real answer, not a gap -- Nobara/Linux reports exactly
                    this while happily answering 327 other settings, and
                    `videoplayer.allowedhdrformats` still reads its
                    cross-platform default [0, 1] there, which means nothing
                    on a box that cannot switch the display at all.
      present+False the switch exists and the user turned it off.
      present+True  HDR is possible; then the display's own type list, the
                    metadata allow-list and CoreELEC's hard-off decide.

    `known` is the only real unknown left: False when Kodi answered nothing
    at all, i.e. we couldn't ask rather than got a "no".

    CAVEAT, measured: these signals follow the live HDMI link. Put the TV to
    sleep and the Android box drops the setting AND empties the type list --
    the same shape a no-HDR platform gives. That is why the capability is
    remembered upgrade-only in `_BEST`; without it, a screensaver could
    silently rewrite a Dolby Vision badge to its base layer. A box that has
    never once reported HDR still reads as no-HDR, which is right for Linux
    and harmless for a TV that has been asleep the whole time -- nobody is
    reading the screen in that case.
    """
    return _cached("video", _build_video)


#: Best HDR capability ever observed this session. The HDR signals track the
#: live HDMI/EDID link, NOT the hardware: with the TV asleep the Android box
#: drops winsystem.ishdrdisplay entirely and reports an empty type list,
#: which is indistinguishable from a platform that has no HDR at all
#: (measured with `adb shell dumpsys display` showing mScreenState=OFF).
#: Capability doesn't come and go with a screensaver, so it only ever
#: upgrades here -- a sleeping display can't talk us out of what the box
#: already proved it could do.
_BEST: dict = {"hdr_types": "", "dolby_vision": False, "hdr_capable": False}


def _build_video() -> dict:
    hdr_types = xbmc.getInfoLabel("System.SupportedHdrTypes") or ""
    # Two independent ways for a DV-capable display to still not GET DV:
    #
    #  - videoplayer.allowedhdrformats, an allow-list of the advanced HDR
    #    formats Kodi may output (0 = Dolby Vision, 1 = HDR10+, read off the
    #    setting's own option labels). Present on all three real devices.
    #    Absent -> unrestricted.
    #  - coreelec.amlogic.disabledolbyvision, CoreELEC-only, a hard off.
    allowed = _setting("videoplayer.allowedhdrformats")
    dv_allowed = True if allowed is None else (_DV_HDR_FORMAT in allowed)
    dv_disabled = bool(_setting("coreelec.amlogic.disabledolbyvision"))
    # "Adjust display HDR mode" (Settings / Player / Videos / Playback). Its
    # PRESENCE means the display is HDR-capable -- Kodi only registers it
    # there -- and its VALUE means Kodi will actually switch the display into
    # HDR. Off, nothing HDR gets out, DV included. Screenshotted on the
    # Android box over ADB to be sure which switch this is: it sits directly
    # under "Adjust display refresh rate", and is NOT the separate "Allowed
    # HDR dynamic metadata formats" list further down under Processing.
    hdr_switching = _setting("winsystem.ishdrdisplay")
    modes = _display_modes()
    screen = xbmc.getInfoLabel("System.ScreenResolution") or ""   # "1920x1080 - Windowed"
    screen_w, screen_h = _parse_mode(screen)
    hdr_capable = hdr_switching is not None or bool(hdr_types)
    dolby_vision = (("dolby vision" in hdr_types.lower())
                    and bool(hdr_switching) and dv_allowed and not dv_disabled)
    # Upgrade-only: keep the best answer this box has given us.
    if hdr_capable:
        _BEST["hdr_capable"] = True
    if hdr_types:
        _BEST["hdr_types"] = hdr_types
    if dolby_vision:
        _BEST["dolby_vision"] = True
    return {
        # False only when Kodi answered nothing at all -- the difference
        # between "no" and "couldn't ask".
        "known": bool(_all_settings()),
        "hdr_types": hdr_types,
        # Capable (the display can) vs enabled (Kodi will). Both are the
        # best seen, so a sleeping display doesn't retract them.
        "hdr_capable": _BEST["hdr_capable"] or hdr_capable,
        "hdr_enabled": bool(hdr_switching),
        "dolby_vision": _BEST["dolby_vision"] or dolby_vision,
        "modes": modes,
        "max_height": max((m[1] for m in modes), default=0),
        # What the screen is showing RIGHT NOW. With mode switching off this
        # is also what a video gets scaled to, whatever its own resolution.
        "screen_width": screen_w,
        "screen_height": screen_h,
        "refresh_rates": sorted({m[2] for m in modes}),
        "whitelist_modes": _whitelist_modes(),
        # Empty whitelist + switching enabled = free choice of any mode the
        # display reports. A populated whitelist restricts it to the closest
        # entry, so the reachable set is the whitelist itself.
        "switches_modes": (_setting("videoplayer.adjustrefreshrate") or 0) != 0,
    }


def _display_modes() -> list:
    """Every (width, height, hz) the DISPLAY reports, read off the option
    list Kodi builds for videoscreen.whitelist. That option list is the
    EDID mode list, whatever the whitelist itself is set to."""
    for entry in _all_settings():
        if entry.get("id") != "videoscreen.whitelist":
            continue
        out = []
        for option in entry.get("options") or []:
            mode = _parse_mode_option((option or {}).get("label") or "")
            if mode:
                out.append(mode)
        return out
    return []


def _parse_mode_option(label: str):
    """"3840x2160p  23.98Hz" -> (3840, 2160, 23.98), or None."""
    try:
        size, _, rest = label.partition("p")
        width, _, height = size.partition("x")
        return (int(width), int(height), float(rest.replace("Hz", "").strip()))
    except (TypeError, ValueError):
        return None


def _decode_mode_id(value: str):
    """Decode a whitelist entry id into (w, h, hz).

    Format, confirmed against every real entry on the Android box:

        0384002160060.00000pstd  ->  3840 x 2160 @ 60.00
        0192001080023.97602pstd  ->  1920 x 1080 @ 23.97602

    Six digits of width times ten, four of height, then the refresh rate.

    Decoded rather than looked up in the setting's option labels, because
    those come and go: Settings.GetSettings had 35 option rows for the cinema
    box earlier today and none an hour later, with the display still awake
    and the stored value unchanged. The VALUE is a stored preference and
    always readable, so parsing it is the dependable path.
    """
    try:
        return (int(value[0:6]) // 10, int(value[6:10]), float(value[10:19]))
    except (TypeError, ValueError, IndexError):
        return None


def _whitelist_modes() -> list:
    """The modes the user has actually whitelisted, as (w, h, hz)."""
    value = _setting("videoscreen.whitelist") or []
    out = []
    for entry in value:
        mode = _decode_mode_id(entry if isinstance(entry, str) else "")
        if mode:
            out.append(mode)
    return out


def dynamic_range_label(video_format: dict, caps: dict | None = None) -> str:
    """The badge for a file's dynamic range, as THIS display will show it.

    A Dolby Vision file on a display that can't do DV plays its BASE LAYER,
    so promising "Dolby Vision" there is a promise the screen can't keep --
    and the server hands us the right answer for that case in
    `base_layer_label`: a 4K disc carries its DV encode over an HDR10+ base,
    and a detail surface is meant to show that base as well.

    Downgrades whenever we could ASK and the answer was no -- which
    includes a box with no HDR path at all, like Kodi on Linux. The only
    case that keeps the file's own label is `known` False, meaning Kodi
    answered nothing and we are guessing.
    """
    label = (video_format or {}).get("label") or ""
    if (video_format or {}).get("dynamic_range") != "dolby_vision":
        return label
    caps = caps if caps is not None else video()
    if not caps.get("known", True) or caps.get("dolby_vision"):
        return label
    return video_format.get("base_layer_label") or label


#: The shorthand is only honest for the EXACT mode. 1920x1080 is "1080p";
#: 1366x768 is 1366x768, because calling that "720p" would be a lie about
#: both axes. Deliberately p-notation rather than the server's "4K", since
#: this names a DISPLAY MODE, not a marketing tier for a file.
_MODE_LABEL = {
    (1280, 720): "720p",
    (1920, 1080): "1080p",
    (3840, 2160): "2160p",
    (7680, 4320): "4320p",
}


def _parse_mode(text: str) -> tuple:
    """(width, height) out of System.ScreenResolution. Kodi spells it three
    different ways across the real devices and all three must parse:

        "1920x1080 - Windowed"                  desktop
        "3840x2160 @ 23.98 Hz - Full screen"    CoreELEC
        "3840x2160 @ 59.94 Hz - Full screen"    Android
    """
    try:
        left, _, right = (text or "").partition("x")
        return (int(left.strip()), int(right.split()[0].split("-")[0]))
    except (IndexError, ValueError):
        return (0, 0)


def _mode_label(width: int, height: int) -> str:
    if not height:
        return ""
    exact = _MODE_LABEL.get((width, height))
    if exact:
        return exact
    return "{0}x{1}".format(width, height) if width else "{0}p".format(height)


def _reachable_modes(caps: dict) -> list:
    """The modes Kodi may actually switch INTO.

    An empty whitelist does NOT mean "any mode the display supports", which
    is the natural reading and the wrong one. Kodi builds itself a default
    whitelist of the modes matching the CURRENT resolution -- i.e. its
    refresh-rate variants -- so with an empty whitelist the RESOLUTION never
    changes and only the refresh rate does. That is why the wiki tells people
    to populate the whitelist to get resolution switching at all.
    """
    cur = (caps.get("screen_width") or 0, caps.get("screen_height") or 0)
    if not caps.get("switches_modes"):
        return [(cur[0], cur[1], 0.0)]
    whitelisted = caps.get("whitelist_modes") or []
    if whitelisted:
        return whitelisted
    same = [m for m in (caps.get("modes") or []) if (m[0], m[1]) == cur]
    return same or [(cur[0], cur[1], 0.0)]


def _output_mode(file_height: int, caps: dict) -> tuple:
    """The (width, height) this file will actually be shown at.

    Kodi switches to a mode matching the VIDEO when one is reachable, and
    otherwise stays where it is -- it does not hunt for the nearest size. So
    a 4K file with only 1080p whitelisted plays at whatever the screen is
    already showing, which is the honest thing to report.
    """
    if not file_height:
        return (0, 0)
    cur = (caps.get("screen_width") or 0, caps.get("screen_height") or file_height)
    for width, height, _hz in _reachable_modes(caps):
        if height == file_height:
            return (width, height)
    return cur


def _output_refresh(fps, caps: dict) -> float:
    """The refresh rate the file will be shown at, or 0.0 when unknown.

    Returns 0.0 whenever `fps` is missing, which today is ALWAYS: the server
    carries `display_frame_rate` ("frame rate a display should switch to")
    but leaves it null on every file measured (144/144, 2026-08-01). The
    logic is here and inert so it lights up the day the field is populated,
    and every caller drops the axis on 0.0.
    """
    try:
        fps = float(fps or 0)
    except (TypeError, ValueError):
        return 0.0
    if fps <= 0:
        return 0.0
    rates = caps.get("refresh_rates") or []
    if not caps.get("switches_modes") or not rates:
        # No switching: whatever the screen already runs at. We know the mode
        # list but not which one is current, so only report a mismatch we can
        # actually prove -- see delivery().
        return 0.0
    # Kodi prefers an exact multiple (24 -> 24/48/72), else the closest.
    best = min(rates, key=lambda r: min(abs(r - fps * n) for n in (1, 2, 3)))
    return best


#: Where the Amlogic kernel publishes its own decoder table, and the ONE
#: place a PER-CODEC video answer can be had on this hardware. Kodi settings
#: cannot give one: its hardware-decode switches are per-API (usedxva2 /
#: usevtb / usemediacodec / usevaapi) and the only per-codec ones anywhere
#: are CoreELEC's useamcodec{h264,mpeg2,mpeg4,vc1}, which has no AV1 entry
#: (all 378 settings enumerated on AM6B-BOX, 2026-08-19).
#:
#: This is the same file Kodi itself reads to decide whether to use the
#: hardware AV1 path -- `aml_support_av1()` in xbmc/utils/AMLUtils.cpp:238,
#: which calls `aml_support_vcodec_profile()` at :146 on exactly this path.
#: Absent on every non-Amlogic platform, which is why absence claims nothing.
_VCODEC_PROFILE = "/sys/class/amstream/vcodec_profile"

#: Ported from AMLUtils.cpp:243 rather than written fresh, so that what we
#: believe about this box is what Kodi believes about it. Kodi's literal is
#: "(\\bav1\\b|\\bav1_fb\\b):(?!\\;).*compressed" -- the escaped
#: semicolon is just a semicolon, and `.` not crossing newlines is what
#: confines a match to one codec's row, in PCRE and in `re` alike.
_AV1_HARDWARE = re.compile(r"(\bav1\b|\bav1_fb\b):(?!;).*compressed")

#: The height an AV1 source may reach before we would rather the server
#: re-encoded it. 1080 because 1080p30 AV1 was MEASURED to decode and keep
#: real time on AM6B-BOX (2026-08-19, Player.Process(videodecoder) =
#: ff-libdav1d -- software dav1d, there being no am-av1 on that silicon).
#: The 4K case that this ceiling exists to refuse was NOT measured; see the
#: comment on CapabilityProfile.codec_ceilings.
#:
#: 1080 is OUR number, not the kernel's, and it is the one part of this that
#: is not a reading. The table does carry sizes -- Kodi reads "4k"/"8k" out of
#: it for hevc (AMLUtils.cpp:177-187) -- but those describe the HARDWARE
#: decoder's reach, and the whole point here is that AV1 never touches it.
#: Nothing in the file says how far software dav1d gets on this CPU.
_AV1_SOFTWARE_CEILING = "av1:1080"


def video_codec_ceilings() -> str:
    """Per-codec source-height ceilings for THIS box, as the CSV the server
    wants, or `""` for "no ceiling" -- which is what every release before
    this one sent.

    Only AV1 has an entry, and only when the platform says it has no
    hardware AV1 decoder. A software dav1d decode is fine at 1080p and is
    not fine at 4K, so the honest answer differs per box: the S922X in
    AM6B-BOX has no AV1 block, while newer Amlogic parts do -- Kodi's own
    `am-av1` path exists and is gated on precisely this reading
    (DVDVideoCodecAmlogic.cpp:269-275), so "Amlogic" is NOT the question and
    generalising from one box would be the invention this module exists to
    avoid.

    Silence is the safe direction and the default: a platform with no such
    file (everything that is not Amlogic -- Windows, Android, macOS, generic
    Linux, all of which may well have a hardware AV1 decoder we cannot see
    from here) claims no ceiling and behaves exactly as it does today.
    """
    try:
        with open(_VCODEC_PROFILE, "r") as handle:
            table = handle.read()
    except (IOError, OSError):
        return ""
    if not table.strip():
        return ""
    # Hardware AV1: nothing to cap, this box decodes it like any other codec.
    if _AV1_HARDWARE.search(table):
        return ""
    return _AV1_SOFTWARE_CEILING


def delivery(file_format: dict, video_caps: dict | None = None,
             audio_caps: dict | None = None, file_height: int = 0,
             fps=None) -> list:
    """The axes on which playback here will DIFFER from what the file
    carries, as short phrases: `["1080p", "SDR", "2.0"]`.

    Empty when nothing differs, which is the point -- the caveat line only
    appears when there is something to say, so on a box that delivers the
    file intact the hero stays clean.

    Badges describe the FILE (all of it: a DV-over-HDR10 disc shows both
    layers). This describes the BOX. Keeping the two separate is what lets
    each be simply true, instead of one row trying to be both and lying in
    whichever direction the hardware isn't.
    """
    file_format = file_format or {}
    vcaps = video_caps if video_caps is not None else video()
    acaps = audio_caps if audio_caps is not None else audio()
    parts = []

    out_w, out_h = _output_mode(file_height, vcaps)
    if file_height and out_h and out_h < file_height:
        parts.append(_mode_label(out_w, out_h))

    out_hz = _output_refresh(fps, vcaps)
    if out_hz and fps and abs(out_hz - float(fps)) > 0.05:
        parts.append("{0:g}Hz".format(out_hz))

    video_fmt = file_format.get("video") or {}
    shown = dynamic_range_label(video_fmt, vcaps)
    if video_fmt.get("dynamic_range") not in (None, "sdr"):
        if not vcaps.get("hdr_capable"):
            parts.append("SDR")
        elif shown != (video_fmt.get("label") or ""):
            parts.append(shown)

    layout = plays_as(file_format.get("audio"), acaps)
    if layout:
        # Name the format it arrives as, not just the layout: "LPCM 2.0"
        # answers "what am I actually getting" where a bare "2.0" only
        # answers half of it.
        parts.append(u"{0} {1}".format(acaps.get("decoded_format") or "LPCM", layout))
    return parts
