# -*- coding: utf-8 -*-
"""A local staging area for artwork, so Kodi never sees a rotating URL.

WHY THIS EXISTS
===============

Kodi keys its texture cache on the **entire URL, query string included**, and
has no notion of "same picture, different credential". Our art URLs carry the
image token as `?st=<jwt>`, and that token lives one hour. So every rotation
changes every URL, and Kodi re-downloads, re-decodes, re-encodes and re-writes
artwork it already had. Measured on the development box 2026-08-07:
**11,489 texture rows for 2,520 distinct images** -- 4.6x duplication, with
the worst single poster stored **118 times**.

Three ways out were examined and two were ruled out by measurement:

- **A longer-lived token.** Would work, and is what plex-for-kodi relies on
  (`&X-Plex-Token=` is their full, long-lived ACCOUNT token). We are not
  asking tofa for it: their image token is deliberately narrow -- `purpose:
  media`, `scope: image`, profile-bound, 1h -- and Kodi writes the whole URL,
  credential and all, into Textures13.db in PLAINTEXT. A token pulled out of
  that database 15.8 days after it expired is what proved the expiry is
  enforced. Lengthening the TTL means a longer-lived credential sitting in a
  plaintext file on every client, which is the property tofa built this to
  avoid.
- **Moving the token into an HTTP header.** Does not help. Kodi's
  `url|Header=Value` suffix is PART OF THE CACHE KEY: loading one image three
  times, identical URL and token, differing only by a harmless
  `|X-Tofa-Probe=` suffix, produced three separate rows. A rotating
  credential churns the cache wherever it is put.
- **This.** Fetch each image ONCE with a short-lived token and hand Kodi a
  local path that never changes. The credential stops being part of the cache
  key because it stops being part of the reference.

THE NAME IS WRONG: THIS IS THE LIVE COPY, NOT A STAGING COPY
============================================================

This module used to argue that our file only had to survive until Kodi had
ingested it once, on the strength of a probe that loaded an image through
`image://` and found the picture still drawn after the file was deleted and
Kodi restarted. That probe was misleading. Forcing an `image://` reference
forces the CTextureCache route; the art we actually set on list items does
not take it.

Counted 2026-08-12, staged files against Kodi rows that reference them:

    4K CoreELEC box     2619 files    9 rows
    AM6B+ box            735 files    4 rows
    dev laptop          2261 files    2 rows

So for all but a handful, **Kodi holds no copy at all** -- it reads our file
off disk on every draw. (The handful is the same few poster hashes on both
boxes, consistent with items browsed through Kodi's own directory listing,
where its library thumb loader does the `image://` wrapping.)

That inverts how eviction has to work. Deleting a staged file is not free:
the next view re-downloads it, and if the re-stage does not land before the
card is built, `ref()` falls back to a tokenised URL and Kodi caches THAT --
recreating the very row this module exists to prevent. So the sweep below is
budget-driven and generous rather than eager, and it takes any matching Kodi
row with it (see `sweep`), so the two halves can never disagree about what
is still held.

A 0-byte file is a blank poster but NOT poison -- no row is written for a
failed load, and the next good write recovers it immediately, because Kodi
hashes a local file as `d{mtime}s{size}` and both change. We still write
temp-then-rename so a partial download is never visible under the real name;
`addon.py`, `service.py` and the window UI are three separate processes
sharing this directory.

THE FILENAME IS FREE
====================

The server's paths are already content-addressed --
`images/posters/4811731e7cc385af.jpg`, served with
`Cache-Control: private, max-age=31536000, immutable`. So the local name can
be derived straight from the path: stable forever, and different when the
artwork is different. No hashing of our own, and no staleness question to
answer.
"""
from __future__ import annotations

import os
import queue
import re
import threading
import time
import urllib.parse
from typing import Optional


def _log(level: str, msg: str) -> None:
    """Log lazily, because `log` imports xbmc at module scope.

    Everything above _cache_dir() is deliberately importable off-device so
    tools/check_artcache.py can exercise the filename contract without Kodi;
    a module-scope `from . import log` would break exactly that. A failure to
    log is never worth raising from an artwork path either.
    """
    try:
        from . import log as _l
        getattr(_l, level)(msg)
    except Exception:                                       # noqa: BLE001
        pass

#: Master switch. Switched ON 2026-08-07 after measuring on the CoreELEC
#: box, which was carrying 1436 texture rows for 290 distinct images -- 5.0x
#: duplication -- purely from the hourly token rotation.
#:
#: With it off, ref() returns the remote URL and nothing else here runs, so
#: the add-on behaves exactly as it did before this module existed. That
#: remains the fallback for any single image that has not been staged yet,
#: which is what makes this safe to leave on.
ENABLED = True

#: How much disk the staging directory may hold, in megabytes, when the
#: setting is unset. The PRIMARY control -- age does not bound the thing we
#: actually care about, and a 32GB eMMC box and a 1TB desktop should not
#: behave identically.
#:
#: Generous on purpose. Measured 2026-08-12 there is no pressure to relieve:
#: 305MB against 55GB free on the cinema box, 107MB against 113GB on the
#: AM6B. And since Kodi keeps no copy of its own (see the module docstring),
#: every eviction is a re-download rather than the free tidy-up the old
#: 7-day rule assumed. This is insurance against a big library over years,
#: not a fix for a problem anyone has today.
DEFAULT_BUDGET_MB = 1024

#: A backstop for the install that browses once and is left alone, so a
#: mostly-idle box does not sit on a directory forever. Long, for the same
#: reason the budget is generous: under the old 7-day rule a poster looked at
#: every week was still deleted and re-fetched, because mtime is set when the
#: file is WRITTEN and never touched again by a read.
MAX_AGE_S = 90 * 24 * 3600

#: How many fetches may be in flight. Small on purpose: this runs alongside
#: Kodi's own texture downloads, and the point is to be invisible, not fast.
WORKERS = 2

#: Beyond this, new work is dropped rather than queued. A dropped fetch is
#: not a failure -- that image simply stays on its remote URL and gets
#: another chance the next time the row is built.
QUEUE_MAX = 512

_DIRNAME = "artcache"
_TMP_SUFFIX = ".part"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")

_queue: "queue.Queue[tuple[str, str]] | None" = None
_inflight: set = set()
_lock = threading.Lock()

#: Set when the owning interpreter is tearing down (add-on exit via stop(), or
#: a Kodi shutdown caught in _worker). The persistent workers below otherwise
#: park in _queue.get() forever; a parked worker is a thread Kodi's
#: CPythonInvoker waits 5s for and then force-kills mid-park, which wedged
#: Kodi's quit on 2026-08-07 (the two WORKERS here were the "waiting on thread"
#: in the log). See _worker() and stop().
_stopped = threading.Event()


def _cache_dir() -> str:
    """The staging directory, created on demand.

    xbmc* is imported HERE rather than at module scope so the pure logic
    above can be exercised off-device by tools/check_artcache.py.
    """
    import xbmcaddon
    import xbmcvfs

    path = os.path.join(
        xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo("profile")), _DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


def local_name(server_path: str) -> str:
    """A stable, collision-free filename for a server-relative image path.

    The whole relative path is flattened rather than just its basename: the
    hashes make a collision between `posters/` and `stills/` essentially
    impossible, but "essentially" is not a good enough reason to throw the
    information away. Everything outside [A-Za-z0-9._-] is replaced, so a
    hostile or merely surprising path cannot escape the directory.
    """
    cleaned = (server_path or "").strip().lstrip("/")
    if cleaned.startswith("cache/"):
        cleaned = cleaned[len("cache/"):]
    cleaned = cleaned.split("?", 1)[0]
    name = _SAFE.sub("_", cleaned.replace("/", "_"))[:180]
    # Separators are already gone, so "../../etc/passwd" is the harmless
    # filename ".._.._etc_passwd". The one thing left that could still escape
    # is a name made ENTIRELY of dots -- "." or ".." join to the directory
    # itself or its parent. Refuse those rather than reason about what the
    # caller would then do with them.
    return "" if not name.strip(".") else name


def local_path(server_path: str) -> Optional[str]:
    name = local_name(server_path)
    if not name:
        return None
    return os.path.join(_cache_dir(), name)


def ref(remote_url: Optional[str], server_path: Optional[str]) -> Optional[str]:
    """What to hand Kodi for this image.

    The local file when we have it -- a reference that never changes, so
    Kodi caches the picture once and keeps it. Otherwise TODAY'S REMOTE URL,
    with a fetch queued behind it, so the poster still paints immediately and
    the only cost of a miss is that this one image is cached under a URL that
    will rotate. That fallback is what makes this safe to switch on: the
    worst case is exactly the behaviour we have now.
    """
    if not ENABLED or not remote_url or not server_path:
        return remote_url
    try:
        path = local_path(server_path)
        if not path:
            return remote_url
        if os.path.exists(path):
            return path
        _submit(remote_url, path)
    except Exception as exc:                                # noqa: BLE001
        # Artwork is never worth breaking a screen over.
        _log("debug", f"artcache: falling back to the remote URL ({exc!r})")
    return remote_url


#: How long prefetch() may block a caller. Generous relative to what it
#: actually costs -- a full Home row of 21 posters (1.9 MB) staged in 0.13s
#: at four workers on the LAN, 0.28s at two, measured 2026-08-07. The
#: deadline is there for the bad network, not the normal one.
PREFETCH_TIMEOUT_S = 3.0

#: How many threads a batch is spread over. FOUR, AND MEASURED -- swept on
#: the cinema box 2026-08-23 against live Discover artwork on the CDN, four
#: runs per arm with disjoint URLs so no arm warmed another:
#:
#:      workers    batch 10   batch 20   batch 40      CPU (batch 20)
#:            1       298ms      513ms         --               251ms
#:            2       201ms      336ms      574ms               328ms
#:            4       209ms      302ms      529ms               449ms
#:            8       268ms      391ms      608ms               736ms
#:           16          --      555ms      795ms              1259ms
#:
#: It gets WORSE above four, and the CPU column says why: prefetch() spawns
#: fresh threads per batch and each builds its own session, so every extra
#: worker is another TLS handshake -- about 65ms of CPU each -- on a box with
#: exactly four cores. Past that they contend for those cores and the
#: handshakes cost more than the concurrency saves.
#:
#: Raising this was proposed and is WRONG. The number that suggested it
#: compared eight-at-once against SERIAL (746ms -> 225ms), which says
#: parallelism helps, not that more of it helps. Against four it does not.
#:
#: Not a setting, deliberately: there is one right answer per device, and the
#: one to tune for is the constrained one -- the cinema box draws 4K on
#: littler cores than anything else here, so a value that suits it cannot
#: hurt a desktop. Re-run the sweep (the vault's tools/probe_cdn.py) if the
#: hardware changes; do not guess.
PREFETCH_WORKERS = 4


def prefetch(pairs, timeout_s: float = PREFETCH_TIMEOUT_S) -> int:
    """Stage a batch of images NOW, blocking until they land or `timeout_s`.

    `pairs` is [(remote_url, server_path), ...].

    WHY BLOCK, when ref() is happy to fall back to the remote URL: because
    the fallback costs a duplicate. On a cold install every image is a miss,
    so it gets cached once under the rotating URL for that first paint and
    again under the local path afterwards -- one orphaned row per image,
    which is exactly the litter this module exists to remove. Staging the
    batch FIRST means Kodi only ever sees the stable reference.

    Blocking is affordable only because it is batched: 21 images cost 1.02s
    fetched one at a time and 0.13s at four workers. Call it once per row,
    never once per image.

    Best effort. Whatever has not arrived by the deadline simply stays on its
    remote URL, which is the behaviour we would have had anyway -- so a slow
    or dead network makes this a no-op rather than a stall.
    """
    if not ENABLED:
        return 0
    todo = []
    try:
        for remote_url, server_path in pairs:
            if not remote_url or not server_path:
                continue
            path = local_path(server_path)
            if path and not os.path.exists(path):
                todo.append((remote_url, path))
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"artcache: prefetch skipped ({exc!r})")
        return 0
    if not todo:
        return 0

    import threading as _t

    work = list(todo)
    lock = _t.Lock()
    done = []
    deadline = time.time() + timeout_s

    def run():
        while time.time() < deadline:
            with lock:
                if not work:
                    return
                remote_url, path = work.pop()
            try:
                _fetch(remote_url, path)
                with lock:
                    done.append(path)
            except Exception as exc:                        # noqa: BLE001
                _log("debug",
                     f"artcache: prefetch missed {os.path.basename(path)}: {exc!r}")

    def run_and_close():
        try:
            run()
        finally:
            # A prefetch thread is born and dies inside this call, so its
            # session has no second use -- see _close_session.
            _close_session()

    threads = [_t.Thread(target=run_and_close, name="tofa-artcache-pre", daemon=True)
               for _ in range(min(PREFETCH_WORKERS, len(todo)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(max(0.0, deadline - time.time()))
    _log("debug", "artcache: prefetched %d/%d" % (len(done), len(todo)))
    return len(done)


def _submit(remote_url: str, path: str) -> None:
    global _queue
    if _stopped.is_set():
        # Tearing down: don't spawn workers or queue work that would only
        # outlive the interpreter.
        return
    with _lock:
        if path in _inflight:
            return
        if _queue is None:
            _queue = queue.Queue(maxsize=QUEUE_MAX)
            for i in range(WORKERS):
                threading.Thread(target=_worker, name=f"tofa-artcache-{i}",
                                 daemon=True).start()
        _inflight.add(path)
    try:
        _queue.put_nowait((remote_url, path))
    except queue.Full:
        with _lock:
            _inflight.discard(path)


def _worker() -> None:
    # xbmc imported HERE, not at module scope, like _cache_dir/_log -- the
    # module stays importable without Kodi. abortRequested() catches what
    # stop() cannot: a Kodi SHUTDOWN, where every interpreter is told to quit
    # and this thread must not still be blocked in _queue.get(). The 1s get
    # timeout is what makes both checks reachable -- a parked worker re-tests
    # them each second and exits well inside Kodi's 5s teardown window instead
    # of being force-killed mid-park.
    import xbmc
    monitor = xbmc.Monitor()
    while not _stopped.is_set() and not monitor.abortRequested():
        try:
            remote_url, path = _queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            _fetch(remote_url, path)
        except Exception as exc:                            # noqa: BLE001
            _log("debug",
                 f"artcache: fetch failed for {os.path.basename(path)}: {exc!r}")
        finally:
            with _lock:
                _inflight.discard(path)
            _queue.task_done()
    _close_session()


def stop() -> None:
    """Tell the background workers to finish, so a script exit is not held up.

    Idempotent, and safe to call from an interpreter that never started a
    worker -- it only sets a flag. The window UI calls this as it tears down
    (launch_home.py); a Kodi shutdown reaches the same workers through their
    own abortRequested() check, which covers every other entry point too. The
    workers notice within their 1s get timeout, so no join is needed here.
    """
    _stopped.set()


#: A requests session PER THREAD, not one shared between them. `requests`
#: does not promise a Session is thread-safe, and these run several workers
#: at once; a session each keeps connection reuse (the whole point of not
#: going back to urlopen) without needing that promise. Threads here are
#: either long-lived queue workers or a handful of short prefetch threads, so
#: the count stays small.
_sessions = threading.local()


def _session():
    """This thread's session, carrying the add-on's identity headers.

    `http` is imported HERE rather than at module scope, like `xbmc` in
    _worker and `log` in _log: it reaches xbmc through clientinfo, and this
    module is deliberately importable without Kodi.
    """
    session = getattr(_sessions, "session", None)
    if session is None:
        from . import http
        session = _sessions.session = http.new_session()
    return session


def _close_session():
    """Hand back this thread's pooled connections as the thread ends.

    Every thread here is finite -- a queue worker that has been told to stop,
    or one of the handful prefetch() spawns per batch -- and each holds a
    keep-alive connection to the media server. Dropping the reference alone
    is not enough in practice: the server FINs its end at its own keep-alive
    timeout, and a socket nobody reads sits in CLOSE_WAIT until the process
    exits. Thirty-seven of them were counted on the cinema box in one
    session (see addon.py's teardown for the whole measurement).

    Never fatal: this runs on the way out of a thread, where raising achieves
    nothing and hides whatever the thread was actually doing.
    """
    session = getattr(_sessions, "session", None)
    if session is None:
        return
    _sessions.session = None
    try:
        session.close()
    except Exception:                                       # noqa: BLE001
        pass


def _fetch(remote_url: str, path: str) -> None:
    """Download to a temp name and rename into place.

    ATOMIC ON PURPOSE. A half-written file under the real name is a blank
    poster that nothing would ever correct, because the next visit would see
    the path exist and use it. The rename also makes concurrent writers from
    the three add-on processes harmless: they write different temp files and
    the last rename wins, with identical bytes either way.

    Through the shared session since 2026-08-11, not a bare
    `urllib.request.urlopen`. Two things that call cost us: the add-on's
    User-Agent -- which exists because Cloudflare in front of api.tofa.tv
    403s anything with "python" in it (error 1010), and urlopen sends exactly
    that -- and the X-Tofa-* identity headers. Neither bites while artwork
    comes from a LAN server, which is why it went unnoticed; both would bite
    the day it comes from behind Cloudflare, and the failure would look like
    "posters are blank" rather than anything about a header.
    """
    if os.path.exists(path):
        return
    tmp = "%s.%d%s" % (path, os.getpid(), _TMP_SUFFIX)
    resp = _session().get(remote_url, timeout=30)
    resp.raise_for_status()
    data = resp.content
    if not data:
        raise ValueError("empty response")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def budget_bytes() -> int:
    """The configured disk budget, in bytes.

    Read fresh each sweep rather than cached, so changing it in Settings
    takes effect at the next sweep instead of the next Kodi start.
    """
    try:
        import xbmcaddon
        chosen = xbmcaddon.Addon().getSettingInt("artcache_budget_mb")
    except Exception:                                       # noqa: BLE001
        chosen = 0
    return (chosen or DEFAULT_BUDGET_MB) * 1024 * 1024


def sweep(max_bytes: Optional[int] = None,
          max_age_s: int = MAX_AGE_S) -> tuple[int, int]:
    """Bring the staging directory back inside its budget.

    Returns `(files removed, bytes freed)`.

    Two passes, in this order. First anything past `max_age_s`, which is the
    backstop for artwork the server has replaced -- its path is content
    addressed, so a new poster is a NEW file and the old one is simply never
    referenced again. Then oldest-first until the total is under budget.

    Oldest by mtime, which is write time: a read never touches it, so this is
    insertion order rather than least-recently-used. That is the right
    trade here anyway -- tracking real use would mean writing to this
    directory from three processes on every card build to save a re-download
    that costs about 50ms on the LAN.

    **Every file removed takes its Kodi texture row with it.** Kodi holds no
    copy of most of these, but for the few it does, leaving the row behind
    would keep a second copy of a picture we have just decided not to keep,
    under a source path that no longer exists. `texturedb.forget` is scoped
    to rows referencing this directory and cannot touch anyone else's.
    """
    removed, freed, names = 0, 0, []
    try:
        directory = _cache_dir()
        entries = []
        for name in os.listdir(directory):
            if name.endswith(_TMP_SUFFIX):
                continue                                    # a fetch in flight
            full = os.path.join(directory, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, name, full))

        budget = budget_bytes() if max_bytes is None else max_bytes
        total = sum(size for _m, size, _n, _f in entries)
        cutoff = time.time() - max_age_s
        entries.sort()                                      # oldest first

        for mtime, size, name, full in entries:
            if mtime >= cutoff and total <= budget:
                break
            try:
                os.remove(full)
            except OSError:
                continue
            removed += 1
            freed += size
            total -= size
            names.append(name)
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"artcache: sweep skipped ({exc!r})")
        return removed, freed

    if removed:
        _log("info", "artcache: swept %d file(s), freed %.1f MB"
                     % (removed, freed / 1e6))
        _forget_rows(names, directory)
    return removed, freed


def _forget_rows(names, directory: str) -> None:
    """Drop the Kodi rows for files we have just deleted. Never fatal."""
    try:
        from . import texturedb
        dropped = texturedb.forget(names, directory)
        if dropped:
            _log("info", "artcache: dropped %d matching texture row(s)" % dropped)
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"artcache: could not sync the texture cache ({exc!r})")


def server_hosts():
    """The media server's addresses, or None if we are not signed in.

    Read from the stored tokens rather than passed in, so the sweep can run
    from the service without building a client. None is a meaningful answer:
    texturedb refuses to identify a tokenised row without it, which is the
    safe direction -- rows stay rather than the wrong ones going.
    """
    try:
        from . import auth
        tok = auth.load()
        hosts = {urllib.parse.urlparse(u).netloc
                 for u in (tok.server, tok.server_fallback) if u}
        return {h for h in hosts if h} or None
    except Exception:                                       # noqa: BLE001
        return None


def sweep_texture_rows() -> int:
    """Drop the Kodi rows cached under a rotating image token.

    These are what `ref()` leaves behind on a MISS: it hands Kodi today's
    tokenised URL so the picture paints now, and an hour later that URL is
    dead while the row and its re-encoded copy live on. Kodi 22 collects them
    itself after 30 days; Kodi 21 never does, and three of the four devices
    here are on 21.

    Batching removed most of the misses (see MediaServerClient.stage_pairs),
    but not all: HERO art -- the backdrop and logo behind the focused card --
    is shown one item at a time, so there is no batch to stage it in, and
    prefetching every row's heroes was measured at 10.09s on a cold Home and
    abandoned. A handful of rows a day is the residue, and this is what
    collects it.

    Deleting a row for artwork still on screen is harmless: Kodi re-fetches
    it once. That is why this does not try to spare recent ones.
    """
    hosts = server_hosts()
    if not hosts:
        return 0
    try:
        from . import texturedb
        directory = _cache_dir()
        gone = 0
        for textureid, url, _kind in texturedb.rows(
                directory, hosts, kinds=(texturedb.LEGACY,)):
            gone += texturedb.remove(textureid, url, directory, hosts)
        if gone:
            _log("info", "artcache: dropped %d tokenised texture row(s)" % gone)
        return gone
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"artcache: could not sweep texture rows ({exc!r})")
        return 0


def purge(hosts=None) -> tuple[int, int]:
    """Delete the whole staging area and every texture row that is ours.

    Behind the explicit Settings action. Returns `(files removed, bytes
    freed)`; the row count is logged rather than returned, since what the
    action reports is disk.

    `hosts` are the media server's addresses. With them, the legacy rows
    cached under a rotating `?st=` URL go too -- the ones nothing on a Kodi
    21 device will ever collect. Without them only our staged rows are
    touched, because a tokenised URL cannot be attributed to us on its shape
    alone. See texturedb.classify.
    """
    removed, freed = sweep(max_bytes=0, max_age_s=0)
    _purge_rows(hosts)
    return removed, freed


def _purge_rows(hosts) -> int:
    try:
        from . import texturedb
        return texturedb.purge(_cache_dir(), hosts)
    except Exception as exc:                                # noqa: BLE001
        _log("debug", f"artcache: could not purge the texture cache ({exc!r})")
        return 0
