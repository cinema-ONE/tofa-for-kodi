# -*- coding: utf-8 -*-
"""Avatar presets come from the server's own catalogue, and are STAGED.

The set changed under us once already -- twelve Fluent Emoji icons became 44
pixel-art ones, six ids retired, and delivery changed from inline SVG data
URIs to PNG files, all in server 0.9.29. Bundling meant going stale on every
such change, so nothing is bundled.

0.9.30 finally gave us `GET /api/v1/profiles/avatars` and
`/api/v1/profiles/avatars/<id>.png`, replacing the scrape of the web app's JS
bundle. The subtle part, and what most of this file is about, is that the
PNG is only tokenless on a DIRECT connection -- measured 2026-08-15, the
cloud relay answers 401 without a bearer. Kodi's texture loader sends none of
our headers, so handing it the URL would work at home and break on the relay,
back to initials for every profile, silently. We fetch it ourselves and hand
Kodi a local path instead.

That is why "the request carried the token" is asserted here as hard as the
resolution itself: it is the difference between working everywhere and
working only where we happen to test.
"""
import json
import os
import pathlib

import kodi_stubs  # noqa: F401
import xbmcvfs  # noqa: F401

from resources.lib import avatar_presets

CHECKS = FAILED = 0
MEDIA = (pathlib.Path(__file__).resolve().parent.parent
         / "plugin.video.tofa/resources/skins/Main/media")

IDS = ["fox", "knight", "robot"]
TOKEN = "test-access-token"


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))


class Response:
    def __init__(self, status=200, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class Session:
    """Records every request, because the caching design is about how many."""

    def __init__(self, ids=None, png=b"\x89PNG-bytes", etag='"v1"',
                 png_status=200):
        self.ids = IDS if ids is None else ids
        self.png, self.etag, self.png_status = png, etag, png_status
        self.calls = []                       # (url, headers)

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if url.endswith("/profiles/avatars"):
            return Response(payload={"ids": self.ids})
        if url.endswith(".png"):
            if (headers or {}).get("If-None-Match") == self.etag:
                return Response(304)
            if self.png_status != 200:
                return Response(self.png_status)
            return Response(content=self.png, headers={"ETag": self.etag})
        return Response(404)

    def urls(self):
        return [u for u, _h in self.calls]

    def png_calls(self):
        return [u for u, _h in self.calls if u.endswith(".png")]


SERVER = "http://box:33333"
RELAY = "https://api.tofa.tv/servers/7d2a19c4/relay"

# --- nothing may ship. A stray file means someone re-bundled the set.
stray = sorted(p.name for p in MEDIA.glob("avatar-*.png")
               if p.name != "avatar-shadow.png")
check("no bundled avatar artwork", not stray, str(stray))
check("...but the nav drop shadow is still there, it is not a preset",
      (MEDIA / "avatar-shadow.png").exists())

# --- the resolution itself
avatar_presets.clear()
s = Session()
path = avatar_presets.url_for(s, SERVER, "preset:knight", TOKEN)
check("a preset resolves to a LOCAL path, not a URL",
      bool(path) and not path.startswith("http"), path)
check("...and the file is really on disk", bool(path) and os.path.exists(path))
check("...with the server's bytes in it",
      bool(path) and open(path, "rb").read() == b"\x89PNG-bytes")

# The EXACT paths, pinned against what a real 0.9.30 answered on 2026-08-15:
#   GET /api/v1/profiles/avatars          -> {"ids": [...44...]}
#   GET /api/v1/profiles/avatars/fox.png  -> 200 image/png
# A fake session will happily agree with whatever this module invents, so the
# one thing it cannot check for itself is written down here.
check("the catalogue path is the one the server serves",
      s.urls()[0] == SERVER + "/api/v1/profiles/avatars", s.urls()[0])
check("the PNG path is the one the server serves",
      s.png_calls() == [SERVER + "/api/v1/profiles/avatars/knight.png"],
      str(s.png_calls()))

# --- the relay case, which is the whole reason we stage
auth = [h.get("Authorization") for _u, h in s.calls]
check("every request carried the bearer token",
      auth and all(a == "Bearer " + TOKEN for a in auth), str(auth))

# Checked HERE, before anything calls clear(): the cache this asserts on is
# the one the lookup above built, and clear() legitimately drops it.
before = len(s.calls)
avatar_presets.url_for(s, SERVER, "preset:knight", TOKEN)
check("a repeat lookup costs no requests", len(s.calls) == before,
      str(s.urls()[before:]))

avatar_presets.clear()
s_relay = Session()
path_relay = avatar_presets.url_for(s_relay, RELAY, "preset:fox", TOKEN)
check("a relay connection resolves the same way",
      bool(path_relay) and os.path.exists(path_relay), path_relay)
check("...and asked the relay, not some other host",
      all(u.startswith(RELAY) for u in s_relay.urls()), str(s_relay.urls()))

# --- an id the server does not publish draws initials, and costs no PNG
avatar_presets.clear()
s2 = Session()
check("a retired preset falls through",
      avatar_presets.url_for(s2, SERVER, "preset:octopus", TOKEN) == "")
check("...without asking for its PNG", not s2.png_calls(), str(s2.png_calls()))

# --- a new preset appears once the catalogue is re-read
avatar_presets.clear()
s3 = Session()
avatar_presets.url_for(s3, SERVER, "preset:knight", TOKEN)
avatar_presets._memory["checked_at"] = 0          # allow a re-check
s4 = Session(ids=IDS + ["newface"])
fresh = avatar_presets.url_for(s4, SERVER, "preset:newface", TOKEN)
check("a new server-side preset is picked up", bool(fresh), fresh)

# --- revalidation keeps the staged file rather than re-downloading it
avatar_presets._memory["validated_at"]["knight"] = 0
s5 = Session()
again = avatar_presets.url_for(s5, SERVER, "preset:knight", TOKEN)
sent = [h.get("If-None-Match") for u, h in s5.calls if u.endswith(".png")]
check("a stale staged file is revalidated with If-None-Match",
      sent == ['"v1"'], str(sent))
check("...and a 304 keeps it", bool(again) and os.path.exists(again), again)

# --- everything that can go wrong draws the monogram instead of raising
class Dead:
    def get(self, url, headers=None, timeout=None):
        raise OSError("no route to host")


avatar_presets.clear()
check("an unreachable server falls through, it does not raise",
      avatar_presets.url_for(Dead(), SERVER, "preset:knight", TOKEN) == "")

avatar_presets.clear()
check("a photo/None ref is not this module's business",
      avatar_presets.url_for(Session(), SERVER, None, TOKEN) == ""
      and avatar_presets.url_for(Session(), SERVER,
                                 "https://x/pic.png", TOKEN) == "")
check("no server at all falls through",
      avatar_presets.url_for(Session(), None, "preset:knight", TOKEN) == "")

# --- a ref is a NAME, never a path. It comes from the server, but the file
# it would write is on this machine.
avatar_presets.clear()
escapes = [avatar_presets.url_for(Session(ids=["../../etc/passwd", ".", "a/b"]),
                                  SERVER, "preset:" + bad, TOKEN)
           for bad in ("../../etc/passwd", ".", "a/b")]
check("a ref that names a path is refused", escapes == ["", "", ""],
      str(escapes))

# --- a catalogue we cannot use must not wipe a working one
avatar_presets.clear()
s6 = Session()
good = avatar_presets.url_for(s6, SERVER, "preset:knight", TOKEN)
avatar_presets._memory["checked_at"] = 0
kept = avatar_presets.url_for(Session(ids=[]), SERVER, "preset:knight", TOKEN)
check("an empty catalogue keeps the previous one", kept == good,
      f"{kept!r} != {good!r}")

# --- clear() takes the staged art with it, or a server switch would show
# the previous household's avatars
staged = avatar_presets.url_for(Session(), SERVER, "preset:robot", TOKEN)
check("staged art exists before the clear", os.path.exists(staged))
avatar_presets.clear()
check("clear() removes the staged art too", not os.path.exists(staged))

print("\n" + "=" * 60)
if FAILED:
    print(f"{FAILED} of {CHECKS} checks FAILED")
    raise SystemExit(1)
print(f"all {CHECKS} checks passed")
