"""Posters are fetched at most POSTER_FETCH_W wide; other art at full size.

The server resizes /cache/ images on `w` (snapping to a bucket, never
enlarging). A clip library's "poster" can be a 1.1 MB 4K frame.

Run:  python3 test_poster_fetch_size.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import api  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


LAN = "http://192.168.1.50:33333"
client = api.MediaServerClient(None, LAN, "tok", "dev")
client.image_token = lambda: "TOKEN"
url = client.image_url_uncached
W = "&w=%d" % api.POSTER_FETCH_W

check("a poster asks for a width", url("images/posters/local-4546.png").endswith("?st=TOKEN" + W))
check("...also with the /cache/ prefix already there",
      url("/cache/images/posters/abc.jpg") == LAN + "/cache/images/posters/abc.jpg?st=TOKEN" + W)
check("...and on our own server's absolute URL",
      url(LAN + "/cache/images/posters/abc.jpg").endswith("?st=TOKEN" + W))
check("a backdrop stays full size", url("images/backdrops/x.jpg").endswith("?st=TOKEN"))
check("a logo stays full size", url("images/logos/x.png").endswith("?st=TOKEN"))
check("the cloud's CDN is left alone",
      url("https://api.tofa.tv/v1/metadata/assets/tmdb/discovery/x.jpg")
      == "https://api.tofa.tv/v1/metadata/assets/tmdb/discovery/x.jpg")
check("the width is a bucket the server keeps (720)", api.POSTER_FETCH_W == 720)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
