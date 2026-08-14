# -*- coding: utf-8 -*-
"""Avatar presets are resolved from the server, not bundled.

The set changed under us once already -- twelve Fluent Emoji icons became
44 pixel-art ones, six ids retired, and the delivery changed from inline
SVG data URIs to PNG files, all in server 0.9.29. Bundling meant going
stale on every such change, so nothing is bundled now.
"""
import json
import pathlib

import kodi_stubs  # noqa: F401
import xbmcvfs

from resources.lib import avatar_presets

CHECKS = FAILED = 0
MEDIA = (pathlib.Path(__file__).resolve().parent.parent
         / "plugin.video.tofa/resources/skins/Main/media")

INDEX = '<html><script src="/assets/index-AAAA1111.js"></script></html>'
BUNDLE = ("junk{id:`knight`,label:`Knight`,src:`/assets/knight-B8.png`,"
          "pixel:!0},{id:`robot`,label:`Robot`,src:`/assets/robot-Bg.png`,"
          "pixel:!0}junk")


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))


class Response:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class Session:
    """Counts requests, because the whole caching design is about how many."""

    def __init__(self, index=INDEX, bundle=BUNDLE):
        self.index, self.bundle, self.urls = index, bundle, []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if url.endswith("/"):
            return Response(self.index)
        if url.endswith(".js"):
            return Response(self.bundle)
        return Response("", 404)


# No avatar art may ship. A stray file means someone re-bundled the set.
stray = sorted(p.name for p in MEDIA.glob("avatar-*.png")
               if p.name != "avatar-shadow.png")
check("no bundled avatar artwork", not stray, str(stray))
check("...but the nav drop shadow is still there, it is not a preset",
      (MEDIA / "avatar-shadow.png").exists())

avatar_presets.clear()
s = Session()
url = avatar_presets.url_for(s, "http://box:33333", "preset:knight")
check("a preset resolves to a URL on the server",
      url == "http://box:33333/assets/knight-B8.png", url)

# The point of the cache: a second lookup must not re-read anything.
before = len(s.urls)
avatar_presets.url_for(s, "http://box:33333", "preset:robot")
check("a second lookup costs no requests", len(s.urls) == before,
      str(s.urls[before:]))

# A NEW preset appearing server-side, which is the entire reason this
# module exists. It always arrives with a REBUILT web app, so the entry
# chunk's hash moves -- that is the signal, not the unknown id on its own.
s2 = Session(index='<html><script src="/assets/index-CCCC3333.js"></script></html>',
             bundle=BUNDLE.replace("junk{id:`knight`",
                                   "{id:`newface`,label:`New`,"
                                   "src:`/assets/newface-Z9.png`,pixel:!0},"
                                   "{id:`knight`"))
avatar_presets._memory["checked_at"] = 0        # allow a re-check
url = avatar_presets.url_for(s2, "http://box:33333", "preset:newface")
check("a rebuilt web app brings new presets with it",
      url == "http://box:33333/assets/newface-Z9.png", url)

# ...and the cheap case: an unknown id under the SAME build reads the index
# (5KB) but never the bundle. Same chunk as the cache now holds (CCCC3333),
# which is what "unchanged build" means.
s5 = Session(index='<html><script src="/assets/index-CCCC3333.js"></script></html>')
avatar_presets._memory["checked_at"] = 0
avatar_presets.url_for(s5, "http://box:33333", "preset:nonesuch")
check("an unknown id under an unchanged build costs only the index",
      all(not u.endswith(".js") for u in s5.urls), str(s5.urls))

# Everything that can go wrong falls through to the monogram rather than
# raising: a retired preset, an unreachable server, a non-preset ref.
avatar_presets.clear()
check("a retired preset falls through",
      avatar_presets.url_for(Session(), "http://box:33333",
                             "preset:octopus") == "")


class Dead:
    def get(self, url, timeout=None):
        raise OSError("no route to host")


avatar_presets.clear()
check("an unreachable server falls through, it does not raise",
      avatar_presets.url_for(Dead(), "http://box:33333", "preset:knight") == "")
check("a photo/None ref falls through",
      avatar_presets.url_for(Session(), "http://box:33333", None) == ""
      and avatar_presets.url_for(Session(), "http://box:33333",
                                 "https://x/pic.png") == "")
check("no server at all falls through",
      avatar_presets.url_for(Session(), None, "preset:knight") == "")

# tofa changed the bundle shape once. If it happens again, a working
# catalogue must survive rather than be wiped by an empty parse.
avatar_presets.clear()
s3 = Session()
avatar_presets.url_for(s3, "http://box:33333", "preset:knight")
avatar_presets._memory["checked_at"] = 0
s4 = Session(index='<html><script src="/assets/index-BBBB2222.js"></script></html>',
             bundle="totally different shape")
kept = avatar_presets.url_for(s4, "http://box:33333", "preset:knight")
check("a bundle we cannot parse keeps the previous catalogue",
      kept == "http://box:33333/assets/knight-B8.png", kept)

print("\n" + "=" * 60)
if FAILED:
    print(f"{FAILED} of {CHECKS} checks FAILED")
    raise SystemExit(1)
print(f"all {CHECKS} checks passed")
