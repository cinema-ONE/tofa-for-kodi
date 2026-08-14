# -*- coding: utf-8 -*-
"""Reading the profile preferences blob without being caught by its types.

`GET /api/v1/users/me`'s `preferences` is not uniformly typed, and the two
halves disagree in the one way that silently breaks a boolean check:

    show_card_ratings            True      <- a real JSON bool
    show_format_badges           True      <- a real JSON bool
    layout.spoilerBlurEpisodes   'false'   <- a STRING
    parental.enabled             'false'   <- a STRING
    playback.autoPlayNext        'true'    <- a STRING

The dotted keys are strings, and `'false'` is truthy in Python. So the
obvious `prefs.get("layout.spoilerBlurEpisodes", True)` reads a preference
the user has explicitly switched OFF as ON, with nothing to show for it but
a feature that will not turn off. Probed live 2026-08-02; the plain
`show_*` keys really are bools, so a reader has to handle both.
"""
from __future__ import annotations

from typing import Any

_FALSE_WORDS = ("false", "0", "no", "off", "")


def as_bool(prefs: dict | None, key: str, default: bool) -> bool:
    """A preference as a real bool, whichever way the server spelled it.

    Anything unrecognised falls back to `default` rather than to False: an
    unexpected value means we do not know what the user wants, and the
    feature's own default is a better answer than "off"."""
    if not prefs or key not in prefs:
        return default
    value: Any = prefs[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _FALSE_WORDS:
            return False
        if text in ("true", "1", "yes", "on"):
            return True
    return default
