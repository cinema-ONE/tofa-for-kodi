# -*- coding: utf-8 -*-
"""What Settings' left column says about the focused row (app 2.0).

One entry per row: its title, a sentence or two on what it does, an
optional smaller note, and, for a row with a fixed set of choices, each
choice with a line of its own. The current value is read live by
windows/main.py, so nothing here goes stale when a setting changes.
"""
from __future__ import annotations

from typing import NamedTuple


class Info(NamedTuple):
    title: str
    body: str
    note: str = ""
    #: (label, description) per choice, in the row's own order.
    options: tuple = ()


_SEGMENT_OPTIONS = (
    ("Ask", "A Skip button appears when it starts."),
    ("Skip", "Jumps past it on its own."),
    ("Do nothing", "Plays through it like the rest."),
)

ROWS: dict[str, Info] = {
    # Account
    "switch_profile": Info(
        "Switch Profile",
        "Who is watching on this device. Each profile keeps its own history, "
        "Continue Watching and preferences."),
    "switch_server": Info(
        "Switch Server",
        "Choose which of your tofa servers this device plays from."),
    "sign_out": Info(
        "Sign Out",
        "Disconnects this device from your server. You will need to pair it "
        "again to watch."),
    "direct_only": Info(
        "Direct connections only",
        "Only ever reach your server directly, never through tofa's relay.",
        note="Applies to this device only."),
    "setup_device": Info(
        "Set up this device",
        "Adds tofa's fonts to the current skin and raises Kodi's image "
        "quality limit.",
        note="Kodi restarts to finish."),
    # Playback & Video
    "quality": Info(
        "Streaming quality",
        "How much of your connection playback may use.",
        options=(("Auto", "Adapts to your connection as it plays."),
                 ("Original", "Plays the file as it is whenever it can."))),
    "nextup": Info(
        "Play the next episode",
        "What happens when an episode ends.",
        options=(("Automatically", "Starts the next one after a countdown."),
                 ("Ask", "Shows Next Up and waits for you."),
                 ("Off", "Stops at the end of the episode."))),
    "nextupstyle": Info(
        "Next Up style",
        "How the next episode is offered as one ends, on this device.",
        options=(("Compact", "A card in the bottom corner."),
                 ("Minimal", "One slim bar; Play Next fills as it counts."),
                 ("Lower third", "A band along the bottom with the season."),
                 ("Full", "A column with a large still."))),
    "intro": Info("Intros", "The opening titles of an episode.",
                  options=_SEGMENT_OPTIONS),
    "recap": Info("Recaps", "The part that catches you up on earlier "
                  "episodes.", options=_SEGMENT_OPTIONS),
    "preview": Info("Previews", "Scenes from the next episode.",
                    options=_SEGMENT_OPTIONS),
    "outro": Info("Outros", "The end credits.", options=_SEGMENT_OPTIONS),
    "commercial": Info("Commercials", "Ad breaks, where a file has them "
                       "marked.", options=_SEGMENT_OPTIONS),
    # Audio & Subtitles
    "audio_lang": Info(
        "Audio language",
        "The soundtrack picked first whenever a title has it.",
        note="Otherwise the secondary language is tried."),
    "audio_lang2": Info(
        "Secondary audio language",
        "Used when a title has no soundtrack in your audio language."),
    "sub_lang": Info(
        "Subtitle language",
        "The subtitles picked first whenever a title has them."),
    "sub_lang2": Info(
        "Secondary subtitle language",
        "Used when a title has no subtitles in your subtitle language."),
    "always_subs": Info(
        "Always show subtitles",
        "Turns subtitles on as soon as playback starts."),
    # Appearance
    "fox": Info(
        "Fox accent",
        "Your fox sets the accent colour and logo across your tofa apps."),
    "rating": Info(
        "Rating badge",
        "Which score posters show in their corner.",
        options=(("Audience", "What viewers thought."),
                 ("Critics", "What the reviews said."),
                 ("Off", "No score on posters."))),
    "episodes_remaining": Info(
        "Episodes remaining",
        "Shows how many episodes you have left on a show's poster."),
    "watched_marks": Info(
        "Watched marks",
        "A tick on posters and episodes you have finished."),
    "hide_spoilers": Info(
        "Hide episode spoilers",
        "Hides the stills and synopses of episodes you have not seen yet."),
    "region": Info(
        "Region",
        "Where release dates and streaming availability come from."),
    # Home
    "spotlight": Info(
        "Featured spotlight",
        "The large banner at the top of Home."),
    "home_rows": Info(
        "Home rows",
        "Rows appear on Home in this order, and hiding one hides it on "
        "every tofa app your profile uses.",
        note="Select a row to move it, hide it or remove one you added."),
    "add_discover": Info(
        "Add a Discover row",
        "Puts one of Discover's lists, or a Home row you took off, at the end "
        "of Home."),
    "add_genre": Info(
        "Add a genre row",
        "Puts everything in your library from one genre at the end of Home."),
    # Privacy & About
    "licences": Info(
        "Open Source Notices",
        "Licences for the fonts and icons this add-on ships with."),
    "art_budget": Info(
        "Artwork storage limit",
        "How much space downloaded artwork may use on this device."),
    "art_clear": Info(
        "Clear artwork cache",
        "Frees the space now. Artwork downloads again as you browse."),
}


#: The tab-focused summary per page: (eyebrow, value key) pairs, the value
#: resolved by windows/main.py.
SUMMARIES: dict[str, tuple] = {
    "account": (("SERVER", "server"), ("CONNECTION", "connection")),
    "playback": (("STREAMING QUALITY", "quality"), ("NEXT EPISODE", "nextup"),
                 ("NEXT UP STYLE", "nextupstyle"), ("INTROS", "intro")),
    "audio": (("AUDIO", "audio_pair"), ("SUBTITLES", "sub_pair"),
              ("ALWAYS SHOW SUBTITLES", "always_subs")),
    "appearance": (("FOX", "fox"), ("RATING BADGE", "rating"),
                   ("EPISODES REMAINING", "episodes_remaining"),
                   ("REGION", "region")),
    "home": (("SHOWN ON HOME", "home_shown"), ("FIRST ROW", "home_first"),
             ("HIDDEN", "home_hidden"), ("FEATURED SPOTLIGHT", "spotlight")),
    "privacy": (("VERSION", "version"), ("ARTWORK STORAGE", "art_budget")),
}
MAX_SUMMARY = 4
MAX_OPTIONS = 4
