# -*- coding: utf-8 -*-
"""Option lists for Settings that the tofa API does not expose.

REGIONS still cannot be fetched. LANGUAGES now can, and is: 0.9.28 added a
`languages` facet to `/media/facets`, so the audio picker is built from the
languages this library actually holds (see language_options()) and the list
below is the fallback for when that call fails. Checked properly before
hardcoding, 2026-08-03, and still true of regions: there is no `/regions` at
any level, and in the OpenAPI spec `region` never appears as a list.

So they are hardcoded here, exactly as the tofa web app hardcodes them --
lifted verbatim from app.tofa.tv's own `SettingsPage` bundle rather than
invented, so a value set on the TV is one the web UI also offers and both
clients show the same name for the same code. Re-extract the same way the
avatar presets were (see tools/gen_avatar_assets.py's docstring): fetch
app.tofa.tv, find the SettingsPage-*.js chunk, and read the arrays out of it.

The media SERVER's own bundled web UI is a different deployment and has none
of this -- no language picker, no region setting, no Appearance page. It only
normalises the playback preferences with its own ISO-639 alias table and
seeds a default from `navigator.language`. The settings UI the Apple TV app
mirrors is the CLOUD one.
"""
from __future__ import annotations

from . import langcodes

# `preferences.region`. ISO 3166-1 alpha-2; drives release dates for titles
# not in the library.
REGIONS: tuple[tuple[str, str], ...] = (
    ("US", "United States"), ("GB", "United Kingdom"), ("CA", "Canada"),
    ("AU", "Australia"), ("IE", "Ireland"), ("NZ", "New Zealand"),
    ("DE", "Germany"), ("FR", "France"), ("ES", "Spain"), ("IT", "Italy"),
    ("NL", "Netherlands"), ("BE", "Belgium"), ("SE", "Sweden"),
    ("NO", "Norway"), ("DK", "Denmark"), ("FI", "Finland"),
    ("PT", "Portugal"), ("PL", "Poland"), ("AT", "Austria"),
    ("CH", "Switzerland"), ("BR", "Brazil"), ("MX", "Mexico"),
    ("AR", "Argentina"), ("JP", "Japan"), ("KR", "South Korea"),
    ("IN", "India"), ("ZA", "South Africa"),
)

# `preferences.playback.preferred_audio_languages` /
# `preferred_subtitle_languages`. ISO 639-2/T. Nine, which is the web app's
# whole list -- deliberately not padded out with more, so the two clients
# offer the same thing.
#
# Since 0.9.28 this is the FALLBACK rather than the whole story: the audio
# picker prefers the `languages` facet, which is strictly better because it
# cannot offer a language the library has no audio for. This list is what a
# picker falls back to when that call fails, and it remains the base of the
# SUBTITLE picker -- see language_options() for why those two differ.
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("eng", "English"), ("jpn", "Japanese"), ("spa", "Spanish"),
    ("fra", "French"), ("deu", "German"), ("ita", "Italian"),
    ("por", "Portuguese"), ("rus", "Russian"), ("ara", "Arabic"),
)

# `preferences.playback.segment_actions.<key>`.
#
# The VALUES are `none` / `ask` / `skip` -- NOT `play`. The Apple TV app
# labels the first one "Play", which is what it does, but the stored value is
# `none` ("take no action"), and the server-side normaliser accepts only
# those three: anything else is dropped on the floor, so a `play` would write
# cleanly, read back as the old value, and look like the setting would not
# stick.
# Order and labels are the web and DESKTOP apps' own -- Ask first, then Skip,
# then "Do nothing". The Apple TV app words the last one "Play" and puts it
# first; it is also the client still showing only two of the five segment
# types, so it is behind rather than a second opinion, and the newer surfaces
# win. Confirmed against a macOS desktop-app screenshot 2026-08-03.
SEGMENT_ACTIONS: tuple[tuple[str, str], ...] = (
    ("ask", "Ask"), ("skip", "Skip"), ("none", "Do nothing"),
)

# All five segment types the server stores, with the web/desktop apps' own
# labels and hints verbatim. The Apple TV app surfaces only intro and outro;
# every other tofa client offers the lot, so this does too.
#: The settings rows whose options are individually focusable pills, as the
#: reference app draws them. Each entry is
#: (key, group id, (segment ids...), window-property prefix).
#:
#: The 89xx block, because 84xx is Playback & Video's and 85xx is Audio &
#: Subtitles'; check_xml.py catches a collision but only after it has
#: silently broken a row, so the block was picked from a scan of what is
#: actually free.
#:
#: EIGHT rows, not five: the five skip kinds below PLUS streaming quality,
#: play-the-next-episode and the rating badge.
SEGMENTED_GROUPS: tuple[tuple[str, int, tuple[int, ...], str], ...] = (
    ("rating",  8900, (8901, 8902, 8903), "segrow_rating"),
    ("quality", 8910, (8911, 8912),       "segrow_quality"),
    ("nextup",  8920, (8921, 8922, 8923), "segrow_nextup"),
    ("intro",      8930, (8931, 8932, 8933), "segrow_intro"),
    ("recap",      8940, (8941, 8942, 8943), "segrow_recap"),
    ("preview",    8950, (8951, 8952, 8953), "segrow_preview"),
    ("outro",      8960, (8961, 8962, 8963), "segrow_outro"),
    ("commercial", 8970, (8971, 8972, 8973), "segrow_commercial"),
)

SEGMENTED_BY_ID: dict[int, tuple[str, int]] = {
    sid: (key, i)
    for key, _g, sids, _p in SEGMENTED_GROUPS
    for i, sid in enumerate(sids)
}


SEGMENT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("intro", "Intro", "Opening sequence before the episode/movie starts."),
    ("recap", "Recap", "Previously-on summary segments."),
    ("preview", "Preview", "Preview of upcoming episodes/content."),
    ("outro", "Outro", "Credits or ending segment near the end."),
    ("commercial", "Commercial", "Ad-break markers when available."),
)


# preferences.playback.auto_play_next (server 0.9.27). Labels are the web
# app's own wording for the same three choices. The server rejects anything
# outside this enum with 400, and a MISSING key means "auto" -- so a viewer
# who has never touched it sees Auto selected, which is what they get.
AUTO_PLAY_NEXT_ACTIONS: tuple[tuple[str, str], ...] = (
    ("auto", "Automatically"), ("ask", "Ask"), ("none", "Off"),
)

#: Label and summary as the web/desktop apps word them. Their row carries a
#: three-sentence description explaining all three choices; ours is one
#: ellipsised line, so it takes the app's SECTION description instead --
#: still their words, at the level that fits. The option labels then say the
#: rest themselves, which is what they are for.
AUTO_PLAY_NEXT_ROW = (
    "Play the next episode",
    "What happens when an episode finishes.",
)


def region_name(code: str) -> str:
    for value, name in REGIONS:
        if value == code:
            return name
    return code or ""


def language_name(code: str) -> str:
    """A viewer-facing name for one language code, in three tries.

    The web app's own wording wins where we have it, so the nine languages
    both clients offer read identically on both. Kodi's LangCodeExpander
    covers everything else, which matters now that the list comes from a
    library that may hold Korean or Persian. A code neither knows is shown
    as itself rather than dropped -- an unnamed row a viewer can still pick
    beats a language silently missing from the picker."""
    if not code:
        return ""
    canon = langcodes.canonical(code)
    for value, name in LANGUAGES:
        if langcodes.canonical(value) == canon:
            return name
    try:
        import xbmc
        name = xbmc.convertLanguage(str(code), xbmc.ENGLISH_NAME)
        if name:
            return name
    except Exception:                                        # noqa: BLE001
        pass
    return str(code).upper()


#: Kept as the old name because it reads better at the call site that shows
#: the CURRENT value of a setting; identical behaviour.
language_label = language_name


#: ISO 639-2 codes that are not a language, so cannot be a language
#: PREFERENCE. Measured on this library: `zxx` is the big one at 49 titles
#: (silent films, music-only tracks), `mul` at 17, and `unknown` is not a
#: code at all but does turn up.
#:
#: Deliberately NOT filtered: 639-2 collective codes for language families
#: (`ine`, `nai`, `phi` each appear once here) and mis-tagged names like
#: `gujarati`. Both read oddly in a picker, but there are ~60 collective
#: codes and no way to spot them without listing them, and any heuristic
#: sharp enough to catch `ine` also catches real three-letter languages.
#: They sort to the bottom of a count-ordered list, which is enough.
_NOT_A_LANGUAGE = frozenset(("zxx", "und", "mis", "mul", "unknown"))


def fold_language_facet(rows) -> list[tuple[str, str, int]]:
    """`[{value, count}]` from /media/facets -> [(code, name, count)].

    Two things happen here, both required by what the facet actually sends.

    It mixes ISO 639-2/B and /T on 0.9.29, so the SAME language arrives
    twice -- `ger` 2880 alongside `deu` 1827, `fre` alongside `fra` -- and a
    picker built straight off it lists German and French two ways each. They
    are folded into one entry per language with the counts summed. tofa fold
    server-side from the release after 0.9.29 (emitting /T), at which point
    this becomes a no-op rather than wrong: folding an already-folded list
    changes nothing.

    Order is by count, descending: the whole advantage of the facet over a
    static list is that it knows what this library is mostly in, and burying
    that under an alphabetical sort throws it away. Ties break on name so the
    order is stable between openings.
    """
    totals: dict[str, int] = {}
    for row in rows or []:
        if isinstance(row, dict):
            value, count = row.get("value"), row.get("count") or 0
        else:
            value, count = row, 0
        canon = langcodes.canonical(value)
        if not canon or canon in _NOT_A_LANGUAGE:
            continue
        totals[canon] = totals.get(canon, 0) + int(count)
    out = [(langcodes.terminological(canon), language_name(canon), count)
           for canon, count in totals.items()]
    out.sort(key=lambda row: (-row[2], row[1]))
    return out


def language_options(facet_rows, *, subtitles: bool) -> list[tuple[str, str]]:
    """The rows a language picker should offer, as [(code, name)].

    **Audio takes the facet alone.** It lists the languages the library has
    audio in, so offering anything else would be offering a preference that
    can never match -- which is exactly the improvement the facet buys.

    **Subtitles take the facet PLUS the static list.** The facet is audio
    languages only (tofa: "audio languages per title, `und` dropped"), and a
    library routinely carries subtitles in languages it has no audio in --
    German subtitles over English audio being the ordinary case here. Using
    the audio facet alone would quietly withdraw choices this picker offers
    today, so the two are unioned instead.

    Either way an empty or failed facet leaves the static list, so the picker
    is never emptier than it was before the facet existed.
    """
    seen: dict[str, tuple[str, str]] = {}
    for code, name, _count in fold_language_facet(facet_rows):
        seen.setdefault(langcodes.canonical(code), (code, name))
    if subtitles or not seen:
        for code, name in LANGUAGES:
            seen.setdefault(langcodes.canonical(code), (code, name))
    return list(seen.values())

# `artcache_budget_mb`. NOT from the app -- Apple TV has no equivalent,
# because it is not a Kodi add-on writing artwork into a shared profile
# directory. Ours to choose, so the list is short and the units are the ones
# a person reading a "This Device" page thinks in.
#
# 1 GB is the default (artcache.DEFAULT_BUDGET_MB) and is deliberately
# generous: Kodi keeps no copy of most staged files, so every eviction is a
# re-download rather than a free tidy-up. The small options exist for a box
# with a crowded eMMC, not because anything is wrong at 1 GB.
ARTCACHE_BUDGETS: tuple[tuple[int, str], ...] = (
    (256, "256 MB"),
    (512, "512 MB"),
    (1024, "1 GB"),
    (2048, "2 GB"),
    (4096, "4 GB"),
)
