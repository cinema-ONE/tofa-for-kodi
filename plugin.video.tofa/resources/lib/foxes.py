# -*- coding: utf-8 -*-
"""The 14 fox presets, kept free of Kodi imports so the skin renderer can
read them too (windows/theme.py re-exports them as theme.PRESETS)."""
from __future__ import annotations

# (name, hex, logo filename) in the apps' order. The logo cannot be tinted at
# runtime, so theme.default_logo() snaps any accent to the nearest of these.
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
