"""Finishing an episode must move the WHOLE hero, not just the pill.

refresh_watch_progress re-derives next-up when the player above the page
closes, so a show that was offering S15 E7 now offers S15 E8. The pill and
the episode grid followed that move from the start; the hero's two other
per-episode blocks did not. The A/V badges describe the file that will play
and the synopsis describes the episode it belongs to -- both were painted
only by _load, so after watching an episode they stayed on the one just
finished. Reported from the box: the Details synopsis still described the
previous episode while the pill correctly read the next one.

Run:  python3 test_detail_refresh_hero.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def episode(number, *, overview, completed):
    fid = f"f{number}"
    return {
        "episode_number": number,
        "title": f"S15 E{number}",
        "overview": overview,
        "files": [{"id": fid, "available": True, "duration_ms": 1000, "format": {}}],
    }, (fid, completed)


class FakeClient:
    """Answers the one call the progress helpers make: a whole-show batch."""
    def __init__(self, completed_ids):
        self._completed = set(completed_ids)
    def media_progress_batch(self, ids):
        return {"items": [
            {"media_file_id": i, "completed": i in self._completed,
             "position_ms": 0}
            for i in ids]}


class FakeDetail:
    # The three methods under test, borrowed whole from the real window.
    refresh_watch_progress = DetailWindow.refresh_watch_progress
    _next_up_episode = DetailWindow._next_up_episode
    _remember_next_up = DetailWindow._remember_next_up
    _apply_episode_synopsis = DetailWindow._apply_episode_synopsis

    def __init__(self, media, client):
        self.media = media
        self.media_id = media.get("id")
        self._client = client
        self.is_playable = True
        self.prefer_file_id = None
        self._nextup_progress = {}
        self._next_up_season = None
        self._next_up_episode_number = None
        self._next_up_title = ""
        self._next_up_overview = ""
        self.play_file_id = None
        self.play_duration_ms = 0
        self._props = {}
        self.badges_rendered_for = []

    # -- Kodi property bag ------------------------------------------------
    def getProperty(self, key):
        return self._props.get(key, "")
    def setProperty(self, key, value):
        self._props[key] = value

    # -- collaborators the refresh path touches, stubbed to no-ops --------
    def _get_client(self):
        return self._client
    def _render_version_pill(self):
        pass
    def _render_format_badges(self, chosen_file):
        self.badges_rendered_for.append((chosen_file or {}).get("id"))
    def _layout_hero_stack(self):
        pass
    def _refresh_episode_progress(self, client):
        pass
    def _select_episode_by_file(self, client, seasons, file_id):
        pass
    def _is_dismissed(self, client, media_id, position_ms):
        return False
    def _apply_primary_progress(self, position_ms, completed):
        pass
    def _wire_pill_navigation(self):
        pass


def make(*, e7_overview="Bob's past comes back to haunt him.",
         e8_overview="A new episode.", show_overview="The show pitch."):
    e7, p7 = episode(7, overview=e7_overview, completed=True)
    e8, p8 = episode(8, overview=e8_overview, completed=False)
    media = {
        "id": "show-1",
        "media_type": "tv",
        "overview": show_overview,
        "seasons": [{"season_number": 15, "episodes": [e7, e8]}],
    }
    win = FakeDetail(media, FakeClient([p7[0]]))  # E7 completed, E8 not
    # The state _load leaves after the viewer opened on E7 and pressed play:
    # the pill, badges and synopsis all describe E7.
    win.is_tv = win.setProperty("is_tv", "1")
    win.play_file_id = "f7"
    win._next_up_overview = e7_overview
    win.setProperty("hero_synopsis", e7_overview)
    return win


# ---------------------------------------------------------------- the bug
win = make()
win.refresh_watch_progress()
check("next-up advanced to E8", win.play_file_id == "f8", win.play_file_id)
check("the synopsis follows to E8",
      win.getProperty("hero_synopsis") == "A new episode.",
      repr(win.getProperty("hero_synopsis")))
check("the A/V badges are repainted for E8's file",
      win.badges_rendered_for and win.badges_rendered_for[-1] == "f8",
      str(win.badges_rendered_for))

# -------------------------------------------------- the sparse-episode case
# The next episode carries no synopsis of its own. The hero must fall back to
# the SHOW's synopsis, never leave the FINISHED episode's text sitting there.
win = make(e8_overview="")
win.refresh_watch_progress()
check("an episode with no synopsis falls back to the show's",
      win.getProperty("hero_synopsis") == "The show pitch.",
      repr(win.getProperty("hero_synopsis")))

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"FAILED: {', '.join(failed)}" if failed
      else f"all {len(RESULTS)} checks passed")
raise SystemExit(1 if failed else 0)
