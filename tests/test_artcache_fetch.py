"""Artwork downloads go through the add-on's own HTTP session.

They used to use a bare `urllib.request.urlopen`, which is the one HTTP call
in the add-on that bypassed `http.new_session()`. That cost two things:

  - the **User-Agent**. It exists because Cloudflare in front of api.tofa.tv
    403s anything with "python" in it (error 1010) -- and urlopen sends
    exactly that.
  - the **X-Tofa-* identity headers**.

Neither bites while artwork comes off a LAN server, which is why it went
unnoticed for so long; both would bite the day it comes from behind
Cloudflare, and it would present as "posters are blank" rather than as
anything to do with a header.

Also locked here: two properties that are easy to break by accident while
editing this file, and that nothing else would catch.

Run:  python3 test_artcache_fetch.py
"""
import os
import sys
import tempfile
import threading

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import artcache

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeResponse:
    def __init__(self, content=b"PNGDATA", status=200):
        self.content = content
        self._status = status
    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")


class FakeSession:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or FakeResponse()
        self.headers = {}
    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        return self.response


def with_session(session):
    artcache._session = lambda: session


# --- it goes through a session, and it is a GET with a timeout -----------
tmpdir = tempfile.mkdtemp()
session = FakeSession()
with_session(session)
target = os.path.join(tmpdir, "poster.png")
artcache._fetch("http://server/art/poster.png", target)
check("the fetch goes through the session", len(session.calls) == 1, str(session.calls))
check("...to the url it was given", session.calls[0][0] == "http://server/art/poster.png")
check("...with a timeout, so a dead host cannot park a worker for ever",
      session.calls[0][1] == 30, str(session.calls[0][1]))
check("the bytes land at the target path",
      open(target, "rb").read() == b"PNGDATA")

# --- atomic: nothing is left half-written under the real name ------------
check("no .part file survives a success",
      not [f for f in os.listdir(tmpdir) if f.endswith(artcache._TMP_SUFFIX)],
      str(os.listdir(tmpdir)))

# An existing file is never refetched -- this is the cache, after all.
session.calls.clear()
artcache._fetch("http://server/art/poster.png", target)
check("an existing file is not refetched", session.calls == [], str(session.calls))

# An empty body must NOT be written: a zero-byte poster would be cached for
# ever, because the next visit sees the path exist.
session2 = FakeSession(FakeResponse(content=b""))
with_session(session2)
empty_target = os.path.join(tmpdir, "empty.png")
try:
    artcache._fetch("http://server/art/empty.png", empty_target)
    raised = False
except ValueError:
    raised = True
check("an empty body raises instead of caching nothing", raised)
check("...and leaves no file behind", not os.path.exists(empty_target))

# An HTTP error likewise: raise_for_status must be consulted, or a 404 body
# would be cached as the poster.
session3 = FakeSession(FakeResponse(content=b"<html>404</html>", status=404))
with_session(session3)
err_target = os.path.join(tmpdir, "missing.png")
try:
    artcache._fetch("http://server/art/missing.png", err_target)
    raised = False
except RuntimeError:
    raised = True
check("an HTTP error raises rather than caching the error page", raised)
check("...and leaves no file behind", not os.path.exists(err_target))


# --- the real _session(): per thread, and carrying the identity ----------
import importlib
importlib.reload(artcache)

seen = {}
def grab(name):
    seen[name] = artcache._session()

t1 = threading.Thread(target=grab, args=("a",)); t1.start(); t1.join()
t2 = threading.Thread(target=grab, args=("b",)); t2.start(); t2.join()
check("each thread gets its own session", seen["a"] is not seen["b"])
check("...and a thread reuses its own", artcache._session() is artcache._session())
check("the session carries the identity headers",
      seen["a"].headers.get("X-Tofa-Client") == "tofa for Kodi",
      str(dict(seen["a"].headers)))
check("...and the Cloudflare-safe User-Agent, which urlopen could not send",
      "python" not in seen["a"].headers.get("User-Agent", "").lower(),
      seen["a"].headers.get("User-Agent"))


# --- artcache must stay importable WITHOUT Kodi --------------------------
# `http` reaches xbmc through clientinfo, so importing it at module scope
# here would break this. The module says so; this proves it.
source = open(os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa",
                           "resources", "lib", "artcache.py")).read()
module_level = [ln for ln in source.splitlines()
                if ln.startswith("import ") or ln.startswith("from ")]
check("http is NOT imported at module scope",
      not any("import http" in ln or "from . import http" in ln for ln in module_level),
      str([ln for ln in module_level if "http" in ln]))
check("xbmc is NOT imported at module scope",
      not any(ln.strip().startswith("import xbmc") for ln in module_level),
      str([ln for ln in module_level if "xbmc" in ln]))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
