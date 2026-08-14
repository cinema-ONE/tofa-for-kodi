"""Preset avatars resolve even when the server does not serve the web app.

There is no catalogue endpoint for the 44 preset avatars (issue #7 asks for
one), so this client reads the list out of the web app's own JS bundle. It
read it from the CONNECTED SERVER, which serves the web app at its root --
true for a direct connection, and false for the cloud proxy, whose root is a
bare 404 because it forwards the API and nothing else.

The visible symptom, on tofa's demo server 2026-08-14: every profile drew
its initials instead of its avatar, with nothing in the log, because a
non-200 was swallowed silently on the way.

So the catalogue now falls back to tofa's own web app host, and the cache
remembers WHICH root it came from -- the URLs are only valid against that
one.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import avatar_presets  # noqa: E402

SERVER = "http://192.168.1.50:33333"
PROXY = "https://api.tofa.tv/servers/7d2a19c4-5e83-4b17-9f60-2c1ab84de905/relay"
WEB = avatar_presets._WEB_APP_BASE

INDEX = '<!doctype html><script type="module" src="/assets/index-D9OGVee9.js"></script>'
BUNDLE = ('...{id:`ghost`,label:`Ghost`,src:`/assets/ghost-DVNiHUwi.png`,pixel:!0},'
          '{id:`knight`,label:`Knight`,src:`/assets/knight-B8YibGO5.png`,pixel:!0}...')

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class _Web:
    """Which roots serve the web app. Everything else answers nothing."""
    def __init__(self, serving):
        self.serving = list(serving)
        self.asked = []

    def __enter__(self):
        self._real = avatar_presets._fetch

        def fake(session, url):
            self.asked.append(url)
            for root in self.serving:
                if url == root + "/":
                    return INDEX
                if url.startswith(root + "/assets/index-"):
                    return BUNDLE
            return None
        avatar_presets._fetch = fake
        avatar_presets._memory = {}
        return self

    def __exit__(self, *exc):
        avatar_presets._fetch = self._real
        avatar_presets._memory = {}


def main() -> int:
    # A direct server serves its own copy -- no internet needed, and the URL
    # must point back at the box rather than out to the cloud.
    with _Web([SERVER]) as web:
        url = avatar_presets.url_for(None, SERVER, "preset:ghost")
        check("direct server: resolved against the server itself",
              url == SERVER + "/assets/ghost-DVNiHUwi.png", url)
        check("...and the web app host was never asked",
              not any(u.startswith(WEB) for u in web.asked), str(web.asked))

    # The proxy's root 404s, so the catalogue has to come from tofa's own
    # web app -- and the URL with it.
    with _Web([WEB]) as web:
        url = avatar_presets.url_for(None, PROXY, "preset:ghost")
        check("proxy: falls back to the web app host",
              url == WEB + "/assets/ghost-DVNiHUwi.png", url)
        check("...having tried the server first",
              web.asked and web.asked[0] == PROXY + "/", str(web.asked[:2]))

    # An id nobody publishes still draws the monogram, which is what every
    # caller expects and what tofa's own clients show.
    with _Web([WEB]):
        check("an unknown preset resolves to nothing",
              avatar_presets.url_for(None, PROXY, "preset:not-a-real-one") == "")

    # Nothing anywhere: no catalogue, no crash, monogram.
    with _Web([]):
        check("no web app anywhere: empty, not an exception",
              avatar_presets.url_for(None, PROXY, "preset:ghost") == "")

    # Not a preset at all.
    with _Web([WEB]):
        check("an uploaded avatar_image_url is not this module's business",
              avatar_presets.url_for(None, PROXY, "https://example/x.png") == "")
        check("and neither is None", avatar_presets.url_for(None, PROXY, None) == "")

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("avatar presets: the catalogue is found wherever it lives (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
