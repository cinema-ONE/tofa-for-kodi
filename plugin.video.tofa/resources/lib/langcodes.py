# -*- coding: utf-8 -*-
"""Decide whether two language codes mean the same language.

WHY THIS EXISTS. A viewer's preferred languages and a file's audio/subtitle
tracks are both tagged with ISO 639 codes, but not necessarily the SAME
spelling of them, and comparing the strings directly makes a track that does
match look like one that does not.

Three spellings are in circulation for one language:

  639-1    two letters                     de
  639-2/T  three letters, "terminological" deu
  639-2/B  three letters, "bibliographic"  ger

Twenty languages have a B form that differs from the T form, and they are
exactly the ones a European library trips over: German, French, Dutch,
Czech, Greek, Icelandic, Romanian, Slovak, Albanian, Welsh... The profile on
this server stores `preferred_audio_languages: ["eng"]`, i.e. 639-2/B, while
a file muxed elsewhere may well be tagged `de` or `deu` where the preference
says `ger`.

The failure is quiet and looks like the opposite of what it is: no match is
found for the viewer's first language, so the next one is used -- usually
English -- and it appears as though the preference was ignored rather than
mis-spelled. tofa fixed the same bug server-side in 0.9.27 for its own
pre-play picker; this is the client's half, since we choose tracks
ourselves once the stream is running.

WHAT IS DELIBERATELY NOT DONE. A region suffix is dropped for matching
(`pt-BR` matches `por`), because a preference of "Portuguese" should find a
Portuguese track rather than nothing. Callers that care about the difference
between pt-BR and pt-PT must prefer an exact hit first -- which is what
player.py's `_first_by_language` does, checking exact before equivalent, so
this only ever ADDS a match where there was none.
"""
from __future__ import annotations

import re
from typing import Optional

#: Every group is one language. The first entry is the canonical form used
#: internally; which one it is does not matter, only that the group is
#: closed. 639-2/B is listed before /T because that is what this server
#: stores.
_GROUPS: tuple[tuple[str, ...], ...] = (
    # --- the twenty where 639-2/B and 639-2/T disagree ------------------
    ("alb", "sqi", "sq"),        # Albanian
    ("arm", "hye", "hy"),        # Armenian
    ("baq", "eus", "eu"),        # Basque
    ("bur", "mya", "my"),        # Burmese
    ("chi", "zho", "zh"),        # Chinese
    ("cze", "ces", "cs"),        # Czech
    ("dut", "nld", "nl"),        # Dutch
    ("fre", "fra", "fr"),        # French
    ("geo", "kat", "ka"),        # Georgian
    ("ger", "deu", "de"),        # German
    ("gre", "ell", "el"),        # Greek
    ("ice", "isl", "is"),        # Icelandic
    ("mac", "mkd", "mk"),        # Macedonian
    ("mao", "mri", "mi"),        # Maori
    ("may", "msa", "ms"),        # Malay
    ("per", "fas", "fa"),        # Persian
    ("rum", "ron", "ro"),        # Romanian
    ("slo", "slk", "sk"),        # Slovak
    ("tib", "bod", "bo"),        # Tibetan
    ("wel", "cym", "cy"),        # Welsh
    # --- languages with one three-letter form, but a two-letter one too;
    # the 639-1/639-2 pairing still has to be known or `en` never matches
    # `eng`. Limited to what actually turns up in media files.
    ("eng", "en"), ("spa", "es"), ("por", "pt"), ("ita", "it"),
    ("rus", "ru"), ("pol", "pl"), ("swe", "sv"), ("nor", "no"),
    ("dan", "da"), ("fin", "fi"), ("hun", "hu"), ("tur", "tr"),
    ("heb", "he"), ("ara", "ar"), ("hin", "hi"), ("tha", "th"),
    ("ukr", "uk"), ("jpn", "ja"), ("kor", "ko"), ("vie", "vi"),
    ("bul", "bg"), ("hrv", "hr"), ("srp", "sr"), ("slv", "sl"),
    ("est", "et"), ("lav", "lv"), ("lit", "lt"), ("cat", "ca"),
    ("ind", "id"), ("lat", "la"),
)

_CANON: dict[str, str] = {
    code: group[0] for group in _GROUPS for code in group
}


def canonical(code: Optional[str]) -> str:
    """One agreed spelling for `code`, or "" if there is nothing to compare.

    Case, surrounding space and any region suffix (`pt-BR`, `zh_Hans`) are
    removed before the lookup. An unknown code is returned as-is rather than
    discarded, so two files tagged with the same unusual code still match
    each other.
    """
    if not code:
        return ""
    text = str(code).strip().lower().replace("_", "-")
    base = text.split("-", 1)[0]
    if not base:
        return ""
    return _CANON.get(base, base)


def same(left: Optional[str], right: Optional[str]) -> bool:
    """Do these two codes name the same language?"""
    canon = canonical(left)
    return bool(canon) and canon == canonical(right)


#: canonical (639-2/B) -> the 639-2/T spelling of the same language. Built by
#: taking the LAST three-letter member of each group, which is /T wherever
#: the two differ (`ger` -> `deu`) and the only three-letter form otherwise
#: (`eng` -> `eng`), given that every group is written B, T, 1.
_TERMINOLOGICAL: dict[str, str] = {
    group[0]: ([c for c in group if len(c) == 3] or [group[0]])[-1]
    for group in _GROUPS
}


def terminological(code: Optional[str]) -> str:
    """The 639-2/T spelling of `code`, which is what to WRITE.

    Both spellings mean the same language and this client matches either
    (`same()`), but the two surfaces a viewer sees do not: tofa's web app
    stores /T (`deu`, `fra`), and from the release after 0.9.29 the
    `languages` facet emits /T too. Writing /T therefore keeps a preference
    set on the TV looking identical to one set on the web.

    An unknown code comes back canonicalised rather than dropped, on the same
    reasoning as canonical()."""
    canon = canonical(code)
    return _TERMINOLOGICAL.get(canon, canon)


def first_by_language(track_list: list, languages: list) -> Optional[dict]:
    """The first track matching the highest-priority language available.

    THE ONE PLACE THIS RULE LIVES. The player applies it to choose what to
    play, and Detail's Options panel applies it to show what WILL play; when
    those were separate the panel offered "German · Deutsch Dolby Digital
    5.1" on an English profile for a disc whose German track happens to come
    first, while playback correctly picked English. A viewer reading that
    either disbelieves the app or "corrects" it into a choice they did not
    need to make.

    `languages` is a LIST in priority order, so this walks the LANGUAGES
    outer and the tracks inner -- the other way round would return the file's
    first track that matches anything, which is the file's opinion of
    priority rather than the viewer's.

    Within ONE language, an exact spelling wins over an equivalent one before
    the next language is considered at all. Both halves matter:

    - equivalence is needed because the profile stores 639-2/B (`ger`) while
      files are often tagged `de` or `deu`. Mars Attacks! carries BOTH
      spellings across its two files -- `ger` on the 4K, `deu` on the 1080p --
      so this is not hypothetical;
    - exactness is needed FIRST because dropping to the next language on a
      spelling difference is precisely the failure, so `de` must be resolved
      against every track before `en` is tried at all. Equivalence as a
      second pass over the whole language list would reintroduce it.

    Exact-before-equivalent also keeps a regional variant honest: with
    `pt-BR` preferred and both `pt-BR` and `por` tracks present, the exact
    one is returned.
    """
    for code in languages or []:
        for track in matching(track_list, code):
            return track
    return None


def matching(track_list: list, code) -> list:
    """Tracks whose language is `code`, exact spellings first."""
    wanted = str(code).strip().lower()
    exact, equivalent = [], []
    for track in track_list or []:
        lang = str(track.get("language") or "").strip().lower()
        if lang == wanted:
            exact.append(track)
        elif same(lang, code):
            equivalent.append(track)
    return exact + equivalent


def first_subtitle_by_language(track_list: list, languages: list) -> Optional[dict]:
    """The subtitle track to turn on for a viewer who wants subtitles.

    Same language priority as first_by_language, but a subtitle track has
    flags that change what it MEANS, and picking by language alone gets it
    wrong. Mars Attacks!'s 4K disc offers three:

        index 5  ger  forced=True   "Deutsch Forced (PGS)"
        index 6  ger  forced=False  "Deutsch (PGS)"
        index 7  eng  sdh           "English SDH (PGS)"

    Plain language matching returns index 5, because it comes first. A FORCED
    track only subtitles foreign-language dialogue -- a handful of lines in
    the whole film -- so "Always show subtitles" appeared to do nothing.
    Measured that way before this existed.

    Within the matched language, then:

    - a FORCED track is the last resort. It is not "subtitles on", it is the
      narrow case of translating the odd alien or foreign line for someone
      already hearing their own language.
    - an SDH track loses to a plain one. SDH adds sound description for deaf
      and hard-of-hearing viewers; it is the right answer when it is all
      there is, and the wrong default when a plain track sits beside it.
      tofa's own settings offer no SDH preference to read, so the plain
      track is the honest default.

    Ordering, not filtering: a language with only a forced track still
    returns it, because showing something the viewer asked for beats showing
    nothing.
    """
    for code in languages or []:
        candidates = matching(track_list, code)
        if not candidates:
            continue
        return min(candidates, key=_subtitle_rank)
    return None


#: Language values that mean "nobody said". ISO 639-2 reserves `und` for
#: undetermined, and an empty/missing field says the same thing without
#: the vocabulary.
_UNTAGGED = ("", "und")


def first_untagged_subtitle(track_list: list) -> Optional[dict]:
    """The best track carrying no language at all, or None.

    The last rung of the auto-enable chain (server 0.9.33's own order:
    preferred language, then the audio's language, then this). An untagged
    track is more often the file's only real subtitle than a wrong-language
    one -- a labelled track in a language the viewer did not ask for is
    exactly what this chain exists to avoid turning on, so anything tagged
    is out, and the untagged candidates rank the same way a language's
    do."""
    candidates = [t for t in track_list or []
                  if str(t.get("language") or "").strip().lower() in _UNTAGGED]
    if not candidates:
        return None
    return min(candidates, key=_subtitle_rank)


#: Bitmap subtitle codecs, for payloads that carry no `render` field.
_BITMAP_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "pgs"}


def _is_bitmap(track: dict) -> bool:
    """A picture subtitle (PGS/VobSub/DVB) rather than a text one."""
    render = str(track.get("render") or "").strip().lower()
    if render:
        return render == "bitmap"
    return str(track.get("codec") or "").strip().lower() in _BITMAP_CODECS


def _subtitle_rank(track: dict) -> tuple:
    """Sort key for one language's candidates. LOWEST wins.

    Ordered by how much each property changes what the viewer gets:

    1. FORCED -- not "subtitles on" at all, just the odd translated line.
       Wrong content, so it loses to everything.
    2. SDH -- the right dialogue plus sound description. Right content in a
       fuller form than most viewers asked for.
    3. BITMAP -- the same content, drawn as pictures. Kodi renders PGS fine,
       but a text track scales with the viewer's subtitle size, restyles,
       and costs nothing to draw, so it wins the tie.

    Content before format, deliberately: an SDH text track and a plain PGS
    one both exist on Mars Attacks!, and the plain one is the better answer
    even though it is the picture one.
    """
    return (bool(track.get("forced")), _is_sdh(track), _is_bitmap(track))


def forced_subtitle_for(track_list: list, audio_language) -> Optional[dict]:
    """The FORCED track that belongs with the audio being played, or None.

    This is what "always show subtitles" being OFF means -- not silence.
    A disc's forced track subtitles the lines the audio does not cover: the
    Martian speech in an English dub, a scene in another language. Someone
    listening in English still wants those, and every other tofa client turns
    them on. Matched to the AUDIO's language, not to any subtitle preference,
    because that is the pairing that makes sense.

    Prefers a real `forced` flag over a title that merely says so, since the
    flag is the container's own answer. Mirrors the web app's own rule.
    """
    best, best_rank = None, 0
    for track in matching(track_list, audio_language):
        flagged = bool(track.get("forced"))
        titled = _has_word(track.get("title"), _FORCED_WORDS)
        rank = 2 if flagged else (1 if titled else 0)
        if rank > best_rank:
            best, best_rank = track, rank
    return best


#: "SDH", "HI" or "hearing impaired" as whole words in a track title.
_SDH_TITLE_RE = re.compile(r"\b(sdh|hi|hearing[ -]?impaired)\b", re.IGNORECASE)

#: Titles that say a track only covers part of the dialogue. The same set
#: the web app uses for its own forced-track detection.
_FORCED_WORDS = frozenset(("forced", "foreign", "partial"))


def _has_word(title, words) -> bool:
    """Whole-word match against a track title, case-insensitively."""
    return any(w in words for w in re.split(r"[^a-z0-9]+", str(title or "").lower()))


def _is_sdh(track: dict) -> bool:
    """Whether a subtitle track is the deaf/hard-of-hearing variant.

    Prefers the server's `sdh` flag, and falls back to the TITLE because that
    flag is not always derived from it. Mars Attacks!'s 4K disc, live:

        {"index": 7, "language": "eng", "title": "English SDH (PGS)",
         "forced": false, "sdh": false, ...}

    -- plainly SDH by name, `false` by flag. Without the fallback a viewer
    asking for English subtitles gets the SDH track over the plain one
    sitting beside it.

    Whole-word matching, so a title like "Chile" or "Shipping" cannot trip
    the "hi" alternative.
    """
    if track.get("sdh"):
        return True
    return bool(_SDH_TITLE_RE.search(str(track.get("title") or "")))
