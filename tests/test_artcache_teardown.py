"""Artwork workers let go of their threads and their sockets.

WHY. `artcache.stop()` was called from `launch_home.py` and nowhere else,
and launch_home is only ONE of the two doors into the add-on. Everything
that arrives through `addon.py` -- the directory listing, `?action=play`,
the profile picker, every `?action=*_window` route -- started the same two
workers and left them parked in `_queue.get()` for ever. Kodi waits 5s for
each on the way out and then force-kills it mid-park, taking whatever socket
its session held with it.

Measured on the cinema box 2026-08-22, driving fifteen Detail windows
through the router: 83 threads, 37 sockets to the media server in
CLOSE_WAIT, RSS 267MB -> 1365MB. An ordinary day's browsing showed the same
leak in miniature -- four CLOSE_WAIT sockets, one per profile-picker open.

Two properties are locked here:

  1. stop() makes a parked worker RETURN, rather than merely stopping it
     picking up new work -- a thread that never returns is the thing Kodi
     force-kills.
  2. A finished thread CLOSES its session, so the connection goes back at a
     moment we choose instead of whenever the garbage collector gets to it.

Run:  python3 test_artcache_teardown.py
"""
import os
import sys
import tempfile
import threading
import time

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import artcache

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeResponse:
    content = b"PNGDATA"
    def raise_for_status(self):
        pass


class FakeSession:
    """Counts its own close(), which is the whole point of these checks."""
    def __init__(self):
        self.closed = 0
        self.headers = {}
    def get(self, url, timeout=None):
        return FakeResponse()
    def close(self):
        self.closed += 1


# -- a worker that is told to stop RETURNS, and closes its session --------
#
# Driven directly rather than through _submit(), so the check is about
# _worker's own exit and not about how it was started.

artcache._stopped.clear()
made = []


def fake_new_session():
    s = FakeSession()
    made.append(s)
    return s


artcache._sessions = threading.local()


def fake_session():
    """artcache._session, with FakeSession in place of a real one.

    Kept thread-local like the real thing: _close_session reads and clears
    the same slot, and a shared session would make "did the thread close its
    own?" unanswerable.
    """
    session = getattr(artcache._sessions, "session", None)
    if session is None:
        session = artcache._sessions.session = fake_new_session()
    return session


artcache._session = fake_session

tmpdir = tempfile.mkdtemp()
artcache._queue = artcache.queue.Queue(maxsize=8)
artcache._queue.put(("http://server/a.jpg", os.path.join(tmpdir, "a.jpg")))

worker = threading.Thread(target=artcache._worker, name="test-worker")
worker.start()
time.sleep(0.3)
check("the worker is parked, not finished", worker.is_alive())

artcache.stop()
worker.join(timeout=4.0)
check("stop() makes a parked worker return", not worker.is_alive(),
      "still alive 4s after stop()")
check("...having fetched the queued image",
      os.path.exists(os.path.join(tmpdir, "a.jpg")))
check("...and closed its session on the way out",
      bool(made) and all(s.closed == 1 for s in made),
      "sessions=%d closed=%s" % (len(made), [s.closed for s in made]))

# -- a prefetch thread closes its session too ----------------------------
#
# prefetch() spawns a fresh set of threads per batch, so a session that is
# not closed here leaks once per batch rather than once per process.

made.clear()
artcache._stopped.clear()
tmpdir2 = tempfile.mkdtemp()
artcache._cache_dir = lambda: tmpdir2
staged = artcache.prefetch([("http://server/b.jpg", "images/posters/b.jpg"),
                            ("http://server/c.jpg", "images/posters/c.jpg")])
check("prefetch staged both images", staged == 2, str(staged))
check("every prefetch thread closed its session",
      bool(made) and all(s.closed == 1 for s in made),
      "sessions=%d closed=%s" % (len(made), [s.closed for s in made]))
check("no prefetch thread outlives the call",
      not [t for t in threading.enumerate() if t.name == "tofa-artcache-pre"])

# -- and the API client's own session is handed back too -----------------
#
# The workers were only half of it. Seven sockets to the media server were
# still in CLOSE_WAIT on the box after they were fixed, and they belonged to
# the session every window and every plugin action builds for itself.

from resources.lib import http  # noqa: E402

a, b = http.new_session(), http.new_session()
http.close_all()
check("close_all closes every session this process made",
      a.closed == 1 and b.closed == 1,
      "a=%d b=%d" % (a.closed, b.closed))
check("...and calling it a second time is harmless",
      (http.close_all() or True) and a.closed == 2)

failed = [n for n, ok in RESULTS if not ok]
print("\nartcache teardown (%d checks)" % len(RESULTS))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
