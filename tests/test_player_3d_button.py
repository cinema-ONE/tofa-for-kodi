"""3D is its own button in the utility capsule, not a stepper in Adjust.

The stepper it replaced applied each mode the moment it was stepped onto, so
comparing two modes four apart cost four HDMI renegotiations. The button
opens the SAME panel the start of a 3D film raises, and a panel commits once.

Exercises the REAL methods bound to a stand-in `self`, so the test cannot
drift from the implementation. Run:  python3 test_player_3d_button.py
"""
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player as player_mod
from resources.lib.windows.player import PlayerWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


P = PlayerWindow
_real_cond = player_mod.xbmc.getCondVisibility


def stereoscopic(on):
    player_mod.xbmc.getCondVisibility = (
        lambda label: on if label == "VideoPlayer.IsStereoscopic" else False)


class Capsule:
    """Only what _visible_utility_buttons reads."""
    SUBTITLES_ID, AUDIO_ID, STEREO_ID = P.SUBTITLES_ID, P.AUDIO_ID, P.STEREO_ID
    EPISODES_ID, QUALITY_ID = P.EPISODES_ID, P.QUALITY_ID
    ADJUST_ID, STATS_ID = P.ADJUST_ID, P.STATS_ID

    def __init__(self, *, subtitles=1, audio=2, episode=False):
        self._subtitle_tracks = [{}] * subtitles
        self._audio_tracks = [{}] * audio
        self._episode = episode

    def getProperty(self, key):
        return "1" if (key == "player_is_episode" and self._episode) else ""

    def buttons(self):
        return P._visible_utility_buttons(self)


# ---- the button appears only on a stereoscopic file ------------------------
stereoscopic(True)
on_3d = Capsule().buttons()
stereoscopic(False)
flat = Capsule().buttons()

check("3D appears on a stereoscopic file", P.STEREO_ID in on_3d)
check("3D is absent on everything else", P.STEREO_ID not in flat)
check("no other button moves when 3D appears",
      [b for b in on_3d if b != P.STEREO_ID] == flat,
      f"{on_3d} vs {flat}")

# Owner's placement: straight after Subtitles and Audio.
stereoscopic(True)
check("3D sits directly after Audio",
      on_3d.index(P.STEREO_ID) == on_3d.index(P.AUDIO_ID) + 1, str(on_3d))
check("3D sits before Episodes, Quality, Adjust and Stats",
      all(on_3d.index(P.STEREO_ID) < on_3d.index(later)
          for later in (P.QUALITY_ID, P.ADJUST_ID, P.STATS_ID)), str(on_3d))

# ...and it still lands right after Audio when Subtitles is absent, because
# the capsule is content-dependent and its slots are not fixed.
sparse = Capsule(subtitles=0).buttons()
check("3D follows Audio even with Subtitles hidden",
      sparse.index(P.STEREO_ID) == sparse.index(P.AUDIO_ID) + 1, str(sparse))

# A file with ONE audio track hides Audio too -- then 3D is the first button,
# which is the one the transport's right arrow has to be rewired into.
alone = Capsule(subtitles=0, audio=1).buttons()
check("3D can be the capsule's first button", alone[0] == P.STEREO_ID, str(alone))


# ---- Adjust no longer carries a 3D row ------------------------------------
class Adjust:
    _subtitle_offset = type("O", (), {"label": lambda s: "0 ms", "nudge": lambda s, f: None})()
    def _current_stream(self, subtitles=False): return (0, True)
    def _audio_sync_label(self): return "0 ms"
    def _nudge_audio_sync(self, forward): return None

stereoscopic(True)          # the condition the old row was gated on
rows = P._adjust_rows(Adjust())
labels = [r["label"] for r in rows]
check("Adjust has no 3D row on a stereoscopic file",
      not any("3D" in l for l in labels), str(labels))
check("Adjust still carries both sync rows",
      labels == ["Subtitle sync", "Audio sync"], str(labels))
check("the stepper helpers are gone with it",
      not hasattr(P, "_cycle_stereo_mode") and not hasattr(P, "_stereo_mode_label"))


# ---- the button opens the same panel, on the mode in force ----------------
class Panel:
    """Captures the _open_panel call the real code makes."""
    def __init__(self, current=None, modes=None):
        self.opened = None
        self._current = current
        self._modes = modes if modes is not None else [
            {"mode": "off", "label": "Disabled"},
            {"mode": "split_vertical", "label": "Side by side"},
            {"mode": "split_horizontal", "label": "Over / under"},
        ]
    def _open_panel(self, **kwargs):
        self.opened = kwargs
    def _stereo_panel_rows(self):
        return P._stereo_panel_rows(self)
    def _open_stereo_panel(self, **kwargs):
        return P._open_stereo_panel(self, **kwargs)


def open_panel(*, start_on_current, current=None, pending=True, via_button=False):
    win = Panel(current=current)
    win._stereo_pending = pending
    player_mod.stereoscopic.modes = lambda: win._modes
    player_mod.stereoscopic.preferred_label = lambda: "Same as movie"
    player_mod.stereoscopic.current_mode = lambda: (
        {"mode": win._current, "label": win._current} if win._current else None)
    if via_button:
        P.open_stereo_panel(win)
    else:
        P._open_stereo_panel(win, start_on_current=start_on_current)
    return win


_saved = (player_mod.stereoscopic.modes,
          player_mod.stereoscopic.preferred_label,
          player_mod.stereoscopic.current_mode)

start = open_panel(start_on_current=False)
check("the start-of-playback panel offers Preferred first",
      start.opened["rows"][0][0] == "Preferred mode", str(start.opened["rows"][0]))
check("the start-of-playback panel starts on Preferred",
      start.opened["selected"] == 0, str(start.opened["selected"]))

button = open_panel(start_on_current=True, current="split_horizontal", via_button=True)
check("the button opens the same panel", button.opened["title"] == "3D")
check("the button starts on the mode in force",
      button.opened["selected"] == 3, str(button.opened["selected"]))
check("both carry the glasses mark, not layers",
      start.opened["glyph"] == button.opened["glyph"] == "",
      repr(start.opened["glyph"]))

# An unknown mode must not raise or land on a wrong row.
odd = open_panel(start_on_current=True, current="anaglyph_green_magenta")
check("an unrecognised mode falls back to the first row",
      odd.opened["selected"] == 0, str(odd.opened["selected"]))

# `None` means Preferred, which IS in picks -- it must not be matched by a
# missing current mode, or every fresh file would preselect Preferred by
# accident rather than by the rule above.
nothing = open_panel(start_on_current=True, current=None)
check("no current mode starts at the first row",
      nothing.opened["selected"] == 0, str(nothing.opened["selected"]))

# offer_stereo_mode is still one-shot: it is armed by playback starting.
spent = open_panel(start_on_current=False, pending=False)
spent.opened = None
spent._stereo_pending = False
P.offer_stereo_mode(spent)
check("offer_stereo_mode does nothing unarmed", spent.opened is None)

(player_mod.stereoscopic.modes,
 player_mod.stereoscopic.preferred_label,
 player_mod.stereoscopic.current_mode) = _saved


# ---- onClick routes the button --------------------------------------------
class Clicks:
    STEREO_ID = P.STEREO_ID
    def __init__(self): self.opened = self.anchored = False
    def open_stereo_panel(self): self.opened = True
    # onClick keeps the chrome up after any button; not our concern here,
    # but it has to exist or the branch we care about never returns.
    def anchor_chrome(self): self.anchored = True
    def __getattr__(self, name):
        # Every other *_ID the branch chain tests before reaching ours; a
        # sentinel per name so none of them can accidentally equal STEREO_ID.
        if name.endswith("_ID"):
            return object()
        raise AttributeError(name)

clicked = Clicks()
P.onClick(clicked, P.STEREO_ID)
check("onClick opens the 3D panel", clicked.opened)


# ---- the XML actually carries every control the layout code places --------
XML = "../plugin.video.tofa/resources/skins/Main/1080i/script-tofa-player.xml"
xml = open(XML, encoding="utf-8").read()
ids = re.findall(r'id="(\d+)"', xml)
base = P.UTILITY_VISUAL_BASE[P.STEREO_ID]
wanted = [base + i for i in range(6)] + [P.STEREO_ID]
check("every 3D control exists in the RENDERED xml",
      all(str(cid) in ids for cid in wanted),
      str([cid for cid in wanted if str(cid) not in ids]))
# Kodi resolves a duplicate id by silently returning the FIRST control with
# it, so a collision here is invisible until something focuses the wrong one.
check("none of them collides with an existing id",
      all(ids.count(str(cid)) == 1 for cid in wanted),
      str([cid for cid in wanted if ids.count(str(cid)) != 1]))
check("the glasses codepoint is what those labels draw",
      xml.count("&#xE20D;") == 3, str(xml.count("&#xE20D;")))
# The visual bases must stay disjoint, six apart -- _layout_utility_capsule
# walks base..base+5 for every button and would silently move a neighbour's
# control if two blocks overlapped.
blocks = sorted(P.UTILITY_VISUAL_BASE.values())
check("no visual block overlaps another",
      all(b - a >= 6 for a, b in zip(blocks, blocks[1:])), str(blocks))
check("no visual block collides with a button id",
      not ({b + i for b in blocks for i in range(6)} & set(P.UTILITY_IDS)))

player_mod.xbmc.getCondVisibility = _real_cond

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
