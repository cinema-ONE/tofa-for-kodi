# -*- coding: utf-8 -*-
"""Shared appearance helpers: accent color and the matching fox-logo
variant, used via colordiffuse/texture everywhere either shows up (nav
pill fill/icon/label, progress bars, card focus borders, the logo image).

The real source of truth is the signed-in account's own `accent_color`
preference (`/api/v1/users/me`'s `preferences.accent_color`, one of 14
named presets or an arbitrary custom hex) -- the local `accent_color` Kodi
setting exists only as a fallback for when that's unreachable (signed out,
network down), not as an independent value to keep in sync by hand.
"""
from __future__ import annotations

from . import kodigui

DEFAULT_ACCENT = "2DD4BF"  # "Tofa Fox" teal, matches settings.xml's <default>

# Poster-card rating badge: which tofa score it shows, per the profile's
# `preferred_card_rating`. Lives here rather than in one window because
# every screen with a poster grid needs the same answer -- it was private to
# main.py until the person/filmography screen needed it and silently
# rendered no badges by reaching for a `tofa_rating` field that /media does
# not return.
CARD_RATING_FIELDS = {
    "rt": ("tofa_critics_rating", "tofa_audience_rating"),
    "rt_audience": ("tofa_audience_rating", "tofa_critics_rating"),
}
CARD_RATING_DEFAULT = "rt_audience"


def card_rating_text(item: dict, prefs: dict | None = None) -> str:
    """Badge text for a poster card: a bare tofa score 0-100, or "" to hide
    the badge. Honours show_card_ratings (the picker's "Off") and
    preferred_card_rating.

    No imdb_rating/vote_average fallback: 11 bans rating-source marks, and a
    bare 0-10 number in the same badge that elsewhere means a 0-100 tofa
    score is worse than the ban -- "7.4" and "74" are indistinguishable at
    3m. A title with no tofa score simply has no badge, which the badge's
    own visible gate already handles."""
    prefs = prefs or {}
    if not prefs.get("show_card_ratings", True):
        return ""
    primary, fallback = CARD_RATING_FIELDS.get(
        prefs.get("preferred_card_rating"), CARD_RATING_FIELDS[CARD_RATING_DEFAULT]
    )
    for field in (primary, fallback):
        value = item.get(field)
        if value is not None:
            try:
                return str(int(round(float(value))))
            except (TypeError, ValueError):
                pass
    return ""

# Text-tier white-alpha constants, measured by pixel-sampling real Apple TV
# reference captures (alpha = (rendered-bg)/(255-bg) against the measured
# local background), not copied from the design spec directly. Every
# `<textcolor>` in the app should reference one of these via a
# Window.Property (text_primary/text_secondary/text_tertiary, set in every
# window's own onFirstInit) rather than a raw hex literal.
TEXT_PRIMARY = "white"          # titles, names, section headers -- measured ~90-99%
TEXT_STRONG = "0xD4FFFFFF"      # see below -- 83%, ONE user: the pause card's "N min left"
TEXT_SECONDARY = "0x9EFFFFFF"   # roles, meta, body, captions -- measured ~53-60%, matches spec's 62%
TEXT_TERTIARY = "0x6BFFFFFF"    # eyebrows, "no art" placeholder glyphs -- measured ~42-49%, matches spec's 42%

# TEXT_STRONG is the FOURTH tier, added 2026-08-13, and it deliberately lands
# in the 80-82% gap the original 3-tier measurement found empty. That gap was
# real: it was where no value in the codebase and none in the reference shots
# sat. The pause card's time-left line is the first measured counter-example --
# 211 against its own clock's 251 (0.841) on the live Apple TV, i.e. ~83% --
# and under "the shipped app is the design source" a measured value outranks
# the tidiness of a 3-bucket split.
#
# Keep it to that one label until another is MEASURED into it. A tier that
# collects labels by eye is how the ~18 values this system replaced got here.

# ------------------------------------------------------- rating quality ramp --
# The single score->colour table shared by every tofa client. THIS is the "Kodi
# `ratings.tier`" the design spec names in its cross-client roster
# (web `tofaRatings.ts` / Apple `TofaRatingQuality` / ATV
# `TofaColors.ratingQuality` / tofa-tv `qualityTier`) -- it is not a Kodi
# facility, Kodi has no tier concept of its own. The spec is all-or-nothing
# here: these three values may only move together with the other clients,
# never unilaterally.
#
# Deliberately NOT the status triad (success/warning/error). The spec's own
# reasoning, quoted because it is the whole argument: "a score is a quality
# reading, not an alarm, so it stays softer" -- and retuning the status
# palette must never silently retune ratings.
_RATING_GOOD = "5FD38A"    # >= 75
_RATING_MIXED = "F2C14E"   # 60-74
_RATING_LOW = "F56B5C"     # <= 59

# Discover's open card overrides the ramp: one step only, and at a threshold
# of its own -- see fragments/main's discover card. Not a variant of the above.
DISCOVER_CARD_SCORE_THRESHOLD = 70

# ------------------------------------------------------------- status triad --
# The semantic triad the ramp above is deliberately not. Spec values, and
# semantic ONLY: these say healthy/degraded/broken, never "this is nice".
#
# Its two usage rules come with it. Every status colour is paired with a text
# label -- the colour is emphasis on a word that already says the thing, so a
# reader who can't separate the hues loses nothing. And healthy states stay
# quiet: the player's stats overlay tints a degraded delivery amber but leaves
# a plain DirectPlay in ordinary body colour rather than lighting it green,
# which is why STATUS_HEALTHY has fewer callers than you would expect.
STATUS_HEALTHY = "6EE7B7"
STATUS_DEGRADED = "FCD34D"
STATUS_ERROR = "F87171"


def rating_tier(score) -> str:
    """"good" / "mixed" / "low" for a 0-100 score, or "" if there isn't one.

    Thresholds are the spec's, and every reference sample we have measured
    off the real Apple TV app fits them: 93/82/77 green, 74 and 66 amber."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return ""
    if value >= 75:
        return "good"
    if value >= 60:
        return "mixed"
    return "low"


def rating_tier_hex(score) -> str:
    """The ramp color as a bare RRGGBB (no 0x, no alpha) for inline [COLOR]
    markup, or "" when the score is missing/unparseable -- callers treat ""
    as "leave this text at its label's own color"."""
    return {
        "good": _RATING_GOOD,
        "mixed": _RATING_MIXED,
        "low": _RATING_LOW,
    }.get(rating_tier(score), "")


def rating_numeral(score) -> str:
    """A score formatted as the ramp-tinted numeral that goes in a rating
    readout: "[COLOR FF5FD38A]82[/COLOR]".

    The tint rides the NUMERAL ONLY. "Critics" and "Audience" keep the label
    control's own muted colour, which leaves the row reading as a single
    quiet line instead of two tinted words. Callers build the label themselves
    and drop this in.

    Returns "" for a missing score so a caller can test it directly."""
    tier_hex = rating_tier_hex(score)
    if not tier_hex:
        return ""
    return u"[COLOR FF{0}]{1}[/COLOR]".format(tier_hex, int(round(float(score))))

# (name, hex, logo filename) -- exact hex values from tofa's internal
# design spec. The fox logo can only ever be one of these 14 raster
# variants (resources/skins/Main/media/tofa-logo[-<name>].png) -- unlike
# the flat UI chrome, which can colordiffuse to any arbitrary accent hex,
# there's no way to tint the logo artwork itself at runtime. So
# default_logo() always snaps the current accent to whichever of these 14
# is nearest by RGB distance, even for a fully custom (non-preset) color.
PRESETS = (
    ("Tofa", "2DD4BF", "tofa-logo.png"),
    ("Sky", "38BDF8", "tofa-logo-sky.png"),
    ("Emerald", "34D399", "tofa-logo-emerald.png"),
    ("Indigo", "818CF8", "tofa-logo-indigo.png"),
    ("Violet", "A78BFA", "tofa-logo-violet.png"),
    ("Pink", "F472B6", "tofa-logo-pink.png"),
    ("Rose", "FB7185", "tofa-logo-rose.png"),
    ("Orange", "FB923C", "tofa-logo-orange.png"),
    ("Amber", "FBBF24", "tofa-logo-amber.png"),
    ("Crimson", "A31621", "tofa-logo-crimson.png"),
    ("Forest", "15803D", "tofa-logo-forest.png"),
    ("Ocean", "1E40AF", "tofa-logo-ocean.png"),
    ("Plum", "6B21A8", "tofa-logo-plum.png"),
    ("Snow", "F1EFE8", "tofa-logo-snow.png"),
)

# Cached for the lifetime of this process only -- most of this add-on's
# entry points (addon.py's plugin:// dispatch) are a fresh Python process per
# invocation anyway, so this just avoids 2-3 redundant whoami() round
# trips within a single window's own onFirstInit (accent_color,
# accent_pill_fill, logo_file all resolve the same underlying hex).
_SENTINEL = object()
_server_hex_cache = _SENTINEL


def reset_cache() -> None:
    """Forget the cached accent so the next read hits the server again.

    Needed exactly once, by the merged window's Settings section: switching
    profile changes `accent_color`, and that window is long-lived enough for
    the process-lifetime cache above to otherwise keep serving the previous
    profile's colour for the rest of the session."""
    global _server_hex_cache
    _server_hex_cache = _SENTINEL


def _fetch_server_accent_hex():
    """Best-effort fetch of the signed-in account's own accent_color
    preference. Returns None on any failure (signed out, network down,
    malformed response) -- this must never block a window from opening,
    so callers always fall back to the local `accent_color` setting.

    An account with NO accent set is not a failure, and must not be treated
    as one: it answers DEFAULT_ACCENT. Both used to come back None, so the
    local setting won -- and the local setting is the LAST account's colour.
    Measured 2026-08-14 on tofa's demo server, whose account sets no accent:
    the whole app, fox included, wore the amber left behind by a different
    server on a different network. A colour that survives a re-pair to an
    unrelated account is not a fallback, it is a leak."""
    try:
        from .. import api, auth, http
        session = http.new_session()
        tok = auth.ensure_fresh(session)
        # Deliberately NOT calling profile_select.ensure_profile_selected
        # here -- this function must never block a window from opening
        # (see docstring), and that can open an interactive PIN dialog.
        # Use whatever profile is already resolved on disk, if any; if
        # none is yet, this 403s and falls back below like any other
        # best-effort failure (network down, signed out, ...).
        client = api.client_for(session, tok)
        me = client.whoami()
        if me is None:
            return None
        value = (me or {}).get("preferences", {}).get("accent_color")
        if isinstance(value, str) and value:
            return value
        # Answered, and the answer is "no preference" -> the default fox.
        return DEFAULT_ACCENT
    except Exception:
        return None


def _server_accent_hex():
    global _server_hex_cache
    if _server_hex_cache is _SENTINEL:
        _server_hex_cache = _fetch_server_accent_hex()
        _persist_accent(_server_hex_cache)
    return _server_hex_cache


def _persist_accent(value) -> None:
    """Write a freshly-learned accent into the local `accent_color` setting.

    That setting was already "the offline fallback"; this makes it also the
    LAST KNOWN accent, which is what the startup splash wears. The splash runs
    before anything is resolved -- launch_home raises it before MainWindow is
    even imported, with no network and no profile -- so the only colour it can
    possibly know is one written down on a previous run. See
    windows/splash.py and 7.10's fox.

    Writing here rather than at the fox picker alone is the whole point: the
    picker only fires when someone CHANGES the accent, so a profile whose fox
    was set on another client never reached this file. Now every successful
    resolve keeps it current, which also makes the offline fallback honest for
    the profile actually in use rather than for whoever last used the picker.

    Best-effort and silent: a splash wearing yesterday's fox is a cosmetic
    miss, and nothing here may cost the caller an exception."""
    if not isinstance(value, str) or not value:
        return
    clean = value.lstrip("#").upper()
    if len(clean) == 8:
        clean = clean[2:]
    if len(clean) != 6:
        return
    try:
        if kodigui.ADDON.getSettingString("accent_color").lstrip("#").upper() != clean:
            kodigui.ADDON.setSettingString("accent_color", clean)
    except Exception:                                   # noqa: BLE001
        pass


def remember_accent() -> None:
    """Resolve the accent now and write it down, for a caller about to hand
    the screen to something that cannot resolve it itself.

    The profile switch needs this. It clears the cache (the new viewer has
    their own fox), then tears the window down so the launcher can rebuild it
    behind the splash -- and that splash is the FIRST thing the new profile
    sees. Without a resolve here it would wear the outgoing profile's fox,
    since the only thing on disk is what the previous one wrote."""
    _accent_rgb()


def _local_accent_hex() -> str:
    try:
        return kodigui.ADDON.getSettingString("accent_color") or DEFAULT_ACCENT
    except Exception:
        return DEFAULT_ACCENT


def _accent_rgb() -> str:
    """Bare 6-digit RGB hex (no "#", no alpha, no "0x") for the current
    accent -- the signed-in account's own server-side preference when
    reachable, else the local Kodi setting."""
    value = _server_accent_hex() or _local_accent_hex()
    value = value.lstrip("#").upper()
    if len(value) == 8:
        value = value[2:]  # drop a pre-existing alpha, callers add their own
    return value


def current_accent_hex() -> str:
    """The live accent as a bare uppercase 6-digit RGB hex, for comparing
    against PRESETS.

    A public read of `_accent_rgb()`, added for 9.4's fox picker: it has to
    ask "which of the 14 IS the current accent", which is a different question
    from every other caller's "give me something I can paint with". May not
    match any preset at all -- a custom hex is legal, and the picker shows
    nothing selected in that case rather than lying about the nearest."""
    return _accent_rgb()


def default_accent() -> str:
    """Kodi colordiffuse hex for the current accent, opaque, e.g.
    "0xFF2DD4BF" -- the common case (progress bars, focus borders)."""
    return accent_with_alpha("FF")


def accent_in_accent(text: str) -> str:
    """`text` wrapped in the current accent, as Kodi inline label markup.

    For the odd word inside a label whose own <textcolor> is something else
    -- a Continue Watching card's "S1 E1", which the real app tints while the
    rest of that caption line stays tertiary. A second control just for the
    accent run would have to be positioned and kept in sync with the first;
    markup rides along with the text."""
    return "[COLOR FF{0}]{1}[/COLOR]".format(_accent_rgb(), text) if text else ""


def accent_with_alpha(alpha: str) -> str:
    """Kodi colordiffuse hex for the current accent at a given alpha,
    e.g. accent_with_alpha("3D") -> "0x3D2DD4BF". For translucent uses
    (the nav pill's fill) where the opaque `default_accent()` would be
    too strong."""
    return "0x{0}{1}".format(alpha.upper(), _accent_rgb())


def _relative_luminance(rgb_hex: str) -> float:
    """WCAG relative luminance (0=black, 1=white) of a bare 6-digit hex."""
    def channel(c: str) -> float:
        v = int(c, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(rgb_hex[0:2]) + 0.7152 * channel(rgb_hex[2:4]) + 0.0722 * channel(rgb_hex[4:6])


def on_accent_text() -> str:
    """Kodi colordiffuse/textcolor hex for text or a glyph drawn on TOP OF
    a solid accent-colored fill (the Primary CTA pill, Done button,
    watchlist-added badge, watched checkmark, PickerDialog's "selected"
    row) -- picked by real WCAG contrast against the current accent, not a
    fixed literal. The dark navy `0xFF04211E` used for this against the
    default teal reads fine against most of the 14 presets, but 4 of them
    (Crimson, Forest, Ocean, Plum) score only 1.9-3.4:1 against it -- below
    usable -- while scoring 5.0-8.7:1 against white; every other preset is
    the reverse. Picks whichever wins for the CURRENT accent, so it also
    generalizes to a fully custom (non-preset) hex, unlike default_logo()'s
    preset-distance snapping."""
    accent_lum = _relative_luminance(_accent_rgb())
    dark_lum = _relative_luminance("04211E")
    light_lum = 1.0  # pure white
    lighter, darker = max(accent_lum, dark_lum), min(accent_lum, dark_lum)
    dark_contrast = (lighter + 0.05) / (darker + 0.05)
    light_contrast = (light_lum + 0.05) / (accent_lum + 0.05)
    return "0xFF04211E" if dark_contrast >= light_contrast else "0xFFFFFFFF"


def _nearest_preset(rgb: str):
    """The preset row closest to a bare RRGGBB, by RGB distance."""
    r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)

    def distance(preset) -> int:
        pr, pg, pb = int(preset[1][0:2], 16), int(preset[1][2:4], 16), int(preset[1][4:6], 16)
        return (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2

    return min(PRESETS, key=distance)


def default_logo() -> str:
    """Filename (under resources/skins/Main/media/) of the fox logo
    matching the current accent -- always one of the 14 presets, snapped
    to whichever is nearest by RGB distance."""
    return _nearest_preset(_accent_rgb())[2]


def fox_slug(rgb: str | None = None) -> str:
    """Which of the 14 foxes an accent wears, lowercased (`amber`).

    The same snap-to-nearest as default_logo, because it is the same
    constraint: the fox is ARTWORK, and only 14 of it exist. A custom accent
    (the web UI can set one; the TV apps only offer the 14) therefore paints
    the chrome exactly and borrows the closest fox, which is what every tofa
    client does with the logo already.

    `rgb` is a bare RRGGBB; None asks the live accent, which costs a
    server round-trip on the first call of a process. The splash passes the
    stored one precisely to avoid that."""
    return _nearest_preset((rgb or _accent_rgb()).lstrip("#").upper())[0].lower()
