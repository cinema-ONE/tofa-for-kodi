"""An episode with no neighbours gets the seek pair, not two dead buttons.

8.1 decides the outer transport slots by what is playing: seek for a movie,
previous/next for an episode that has somewhere to go. Where an episode has
nowhere to go in either direction, the slots revert to seek -- the point
being that neither slot is ever occupied by something that does nothing.

We dimmed both episode glyphs and left them there. Reachable on a
single-episode series, and on any episode whose siblings all lack a playable
file.

The subtlety pinned here is that the fallback is the TRANSPORT's alone. The
utility capsule keeps its episodes button, because the drawer lists the
whole season including the episodes that have no file -- which is exactly
what someone in this position wants to see.

Run:  python3 test_lone_episode_transport.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import player as P

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Fake:
    def __init__(self, prev=None, nxt=None):
        self._prev_episode, self._next_up = prev, nxt
        self.props = {}
        self.capsule_relaid = 0
    def setProperty(self, k, v): self.props[k] = v
    def getProperty(self, k): return self.props.get(k, "")
    def _layout_utility_capsule(self): self.capsule_relaid += 1
    _apply_transport_mode = P.PlayerWindow._apply_transport_mode

EP = ("season", "episode")


def mode(prev=None, nxt=None, episode=True):
    f = Fake(prev, nxt)
    f._apply_transport_mode(episode=episode)
    return f


# 1. A movie is unchanged: the seek pair, both live.
f = mode(episode=False)
check("a movie shows the seek pair", f.getProperty("transport_prev_glyph") == P._GLYPH_SEEK_BACK)
check("...and it is not an episode transport", f.getProperty("transport_is_episode") == "")
check("...and both buttons are live",
      f.getProperty("transport_prev_color") != P._TRANSPORT_DISABLED
      and f.getProperty("transport_next_color") != P._TRANSPORT_DISABLED)

# 2. An episode with neighbours both ways: the episode pair, both live.
f = mode(prev=EP, nxt=EP)
check("an episode with neighbours shows the episode pair",
      f.getProperty("transport_next_glyph") == P._GLYPH_NEXT_EPISODE)
check("...and both are live",
      f.getProperty("transport_prev_color") != P._TRANSPORT_DISABLED
      and f.getProperty("transport_next_color") != P._TRANSPORT_DISABLED)

# 3. One neighbour: still the episode pair, and the dead side is DIMMED
#    rather than dropped. 8.1 and our own docstring agree on why, and
#    reached it separately: take a button away and the row re-centres, so
#    Play/Pause moves out from under whatever the viewer had focused.
f = mode(prev=None, nxt=EP)
check("a first episode still shows the episode pair",
      f.getProperty("transport_next_glyph") == P._GLYPH_NEXT_EPISODE)
check("...with previous dimmed, not gone",
      f.getProperty("transport_prev_color") == P._TRANSPORT_DISABLED)
f = mode(prev=EP, nxt=None)
check("a finale keeps the pair too",
      f.getProperty("transport_prev_glyph") == P._GLYPH_PREV_EPISODE)
check("...with next dimmed", f.getProperty("transport_next_color") == P._TRANSPORT_DISABLED)

# 4. THE FIX: no neighbour either way falls back to seek, both live.
f = mode(prev=None, nxt=None)
check("a lone episode falls back to the seek pair",
      f.getProperty("transport_prev_glyph") == P._GLYPH_SEEK_BACK
      and f.getProperty("transport_next_glyph") == P._GLYPH_SEEK_FWD,
      f"{f.getProperty('transport_prev_glyph')!r} {f.getProperty('transport_next_glyph')!r}")
check("...and neither button is dead",
      f.getProperty("transport_prev_color") != P._TRANSPORT_DISABLED
      and f.getProperty("transport_next_color") != P._TRANSPORT_DISABLED)
check("...so the buttons will SEEK, matching their glyphs",
      f.getProperty("transport_is_episode") == "")

# 5. ...but it is still an episode, so the capsule keeps its drawer button.
check("a lone episode is still an episode",
      f.getProperty("player_is_episode") == "1")
check("...and a movie is still not", mode(episode=False).getProperty("player_is_episode") == "")

# 6. The capsule is relaid out every time, since the episodes button hangs
#    off the same fact.
check("the capsule is relaid out", mode(prev=EP, nxt=EP).capsule_relaid == 1)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
