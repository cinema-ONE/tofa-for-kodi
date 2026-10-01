"""Playing a split title: one clock over its parts, and no early finish.

The player keeps each part an ordinary file and session; the timeline, the
seeks and the hand-over between parts run on the title's own clock. A part
that is not the last is held short of the server's finish point, by the
player and by the service that reports progress, because finishing any part
finishes the whole title.

Run:  python3 test_split_playback.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import monitor, parts
from resources.lib.windows import player as P

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


P1 = {"id": "p1", "part_number": 1, "part_count": 2, "duration_ms": 3_185_184,
      "subtitle_tracks": [{"index": 3}]}
P2 = {"id": "p2", "part_number": 2, "part_count": 2, "duration_ms": 3_183_488,
      "subtitle_tracks": [{"index": 4}]}


class FakeUI:
    def stop(self):
        pass


class Fake:
    _set_parts = P.PlayerWindow._set_parts
    _publish_part_cap = P.PlayerWindow._publish_part_cap
    _on_last_part = P.PlayerWindow._on_last_part
    _part_start_ms = P.PlayerWindow._part_start_ms
    _title_position_ms = P.PlayerWindow._title_position_ms
    _title_duration_ms = P.PlayerWindow._title_duration_ms
    _seek_to_title = P.PlayerWindow._seek_to_title
    _switch_part = P.PlayerWindow._switch_part
    advance_part = P.PlayerWindow.advance_part
    STATE_OPENING = "opening"

    def __init__(self, file_id="p1", local_ms=0):
        self.file_id, self._local = file_id, local_ms
        self._parts, self._part_idx, self._duration_ms = [], 0, 3_185_184
        self.ui_player, self.seeks, self.starts, self.props = FakeUI(), [], [], {}
        self._restarting = False

    def _position_ms(self):
        return self._local

    def _seek_to(self, ms):
        self.seeks.append(ms)

    def _render_scrub_markers(self):
        pass

    def setProperty(self, key, value):
        self.props[key] = value

    def _start_playback(self):
        self.starts.append((self.file_id, self.resume_ms))


def cap():
    return monitor._progress_cap_ms("p1"), monitor._progress_cap_ms("p2")


def main():
    w = Fake("p1", local_ms=600_000)
    w._set_parts([P1, P2])
    check("the title lasts as long as both parts", w._title_duration_ms(), 6_368_672)
    check("in part 1 the title clock is the file clock", w._title_position_ms(), 600_000)
    check("part 1 is held short of its finish point", cap(),
          (parts.progress_cap_ms(3_185_184), None))
    w._seek_to_title(1_200_000)
    check("a seek inside the part stays a plain seek", (w.seeks, w.starts), ([1_200_000], []))
    w._seek_to_title(4_000_000)
    check("a seek into part 2 plays part 2 from there",
          (w.starts[-1], w._part_idx, w._restarting), (("p2", 814_816), 1, True))
    check("...with part 2's own subtitle tracks", w._file_subtitle_tracks, [{"index": 4}])

    w = Fake("p2", local_ms=60_000)
    w._set_parts([P1, P2])
    check("in part 2 the title clock runs on from part 1", w._title_position_ms(), 3_245_184)
    check("the last part is not held back", cap(), (None, None))
    check("its end is the title's end", w.advance_part(), False)

    w = Fake("p1")
    w._set_parts([P1, P2])
    check("the end of part 1 plays part 2 from its start",
          (w.advance_part(), w.starts[-1]), (True, ("p2", None)))

    calls = []

    class Client:
        def update_watched(self, fid, watched):
            calls.append(fid)

    w = Fake("p2")
    w._set_parts([P1, P2])
    w.client, w.finish_parts = Client(), P.PlayerWindow.finish_parts.__get__(w)
    w.finish_parts(2_000_000)
    check("leaving the last part early finishes nothing", calls, [])
    w.finish_parts(2_900_000)
    check("...past its finish point, every other part is finished too", calls, ["p1"])

    single = Fake("x")
    single._set_parts([])
    check("a title in one file is untouched",
          (single._title_duration_ms(), single.advance_part(), cap()), (3_185_184, False, (None, None)))

    monitor_checks()
    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


class RecordingClient:
    def __init__(self):
        self.progress, self.session, self.watched = [], [], []

    def report_progress(self, sid, stok, pos, paused, ended=False, timeout=None):
        self.session.append((pos, ended))

    def update_progress(self, fid, pos, ended=False, timeout=None):
        self.progress.append((pos, ended))

    def update_watched(self, fid, watched):
        self.watched.append(fid)

    def end_session(self, sid, stok):
        pass

    def report_stopped(self, sid, stok):
        pass


class FakeMonitor(monitor.TofaPlayer):
    def __init__(self, file_id):
        self.position_ms, self.client = 0, RecordingClient()
        super().__init__()
        self._session = {"session_id": "s", "session_token": "t", "file_id": file_id}

    def getTime(self):
        return self.position_ms / 1000.0

    def isPlayingVideo(self):
        return True

    def _client(self):
        return self.client

    def _telemetry(self, *a, **k):
        pass


def monitor_checks():
    held = parts.progress_cap_ms(3_185_184)
    monitor.publish_progress_cap("p1", held)
    m = FakeMonitor("p1")
    m.position_ms = 3_100_000
    m._report()
    check("the service holds part 1's heartbeat short of its finish",
          (m.client.progress[-1], m.client.session[-1]), ((held, False), (held, False)))
    m.onPlayBackEnded()
    check("...and part 1's end finishes nothing",
          (m.client.watched, m.client.progress[-1]), ([], (held, False)))
    monitor.publish_progress_cap(None, None)
    m = FakeMonitor("p2")
    m.position_ms = 3_183_000
    m.onPlayBackEnded()
    check("the last part ends the title as any file does",
          (m.client.watched, m.client.progress[-1][1]), (["p2"], True))


if __name__ == "__main__":
    main()
