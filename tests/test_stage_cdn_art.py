"""Two questions about a CDN image, and they have different answers.

  1. MAY a local copy exist?            -- `_stageable`
  2. May a batch prefetch WAIT for it?  -- `stage_pair`, LAN-only by default

Keeping them apart is the whole safety argument. Staging the tofa cloud's
metadata CDN was tried once as a SINGLE rule and reverted: a cold Home then
waited on every discovery poster over the internet, and two rows timed out
mid batch.

WHY STAGE IT AT ALL. The CDN's URLs carry no token and are already stable, so
Kodi caches each exactly once -- and that once is not free. It goes download
-> decode -> resize -> re-encode -> write to eMMC -> INSERT into
Textures14.db, four jobs at a time, and the commit is what costs. Measured on
the cinema box 2026-08-22: a cold Cast & Crew sat still for 1.8s after
eleven downloads that had each landed in 20-280ms, and a cold Discover tab
took 20.6 SECONDS to show fifteen images while our own LAN batches beside it
staged 22, 19 and 27 files without a pause. 3821 staged files had produced 13
texture rows in total, against 405 for CDN art alone.

Run:  python3 test_stage_cdn_art.py
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib import api, artcache  # noqa: E402

LAN = "http://192.168.1.50:33333"
CDN = "https://api.tofa.tv"
ASSET = CDN + "/v1/metadata/assets/tmdb/%s/00/5c/" + ("a" * 64) + ".jpg"
HEADSHOT = ASSET % "people"
DISCOVERY = ASSET % "discovery"
TITLE_ART = ASSET % "title"
COLLECTION = ASSET % "collection"
AVATAR = CDN + "/v1/avatars/19f9e580-c570-4246-a80c-fad148f1a37a"
ELSEWHERE = "https://images.example.com/poster.jpg"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


client = api.MediaServerClient(None, LAN, "tok", "dev")
# Our own server's URLs are tokenised on the way out, and fetching a real
# image token would need a real session. The token's VALUE is irrelevant
# here -- what these checks are about is which images get a pair at all.
client.image_token = lambda: "TOKEN"

# -- Q1: what may be staged at all --------------------------------------

for kind, url in (("headshot", HEADSHOT), ("discovery poster", DISCOVERY),
                  ("title art", TITLE_ART), ("collection art", COLLECTION)):
    check("a CDN %s may be staged" % kind, client._stageable(url))
check("our own server may be", client._stageable(LAN + "/cache/images/posters/x.jpg"))
check("a relative path may be", client._stageable("images/posters/x.jpg"))

# Matched on PATH, so the same host's non-asset URLs are untouched: avatars
# have their own resolution path, and nothing else on that host is artwork.
check("an avatar on the same host is NOT staged", not client._stageable(AVATAR))
check("a third-party host is NOT staged", not client._stageable(ELSEWHERE))

# -- Q2: what a batch may block on --------------------------------------

check("a batch does not wait for CDN art by default",
      client.stage_pair(DISCOVERY) is None)
check("...nor for a headshot", client.stage_pair(HEADSHOT) is None)
check("a batch does wait for our own server",
      client.stage_pair(LAN + "/cache/images/posters/x.jpg") is not None)
check("...and for a relative path", client.stage_pair("images/posters/x.jpg") is not None)

pair = client.stage_pair(DISCOVERY, include_cdn=True)
check("include_cdn opts a caller in", pair is not None)
if pair:
    url, key = pair
    check("the fetch URL is the CDN's, untokenised",
          url == DISCOVERY and "?st=" not in url, url)
    check("the staging key is the PATH, not the URL",
          key.startswith("/v1/metadata/assets/tmdb/discovery/"), key)
    name = artcache.local_name(key)
    check("the flattened filename fits the 180-char cap and stays distinct",
          name.endswith(("a" * 64) + ".jpg") and len(name) <= 180, name)

# HOME'S ROW BUILD IS THE ONE THAT MUST NOT CHANGE. It calls stage_pairs with
# no flag, and a discovery row's posters are CDN -- so it must still get an
# empty list and fall back to ref()'s background queue, exactly as today.
home_row = [{"poster_path": DISCOVERY}, {"poster_path": TITLE_ART}]
check("a discovery row still gives Home's blocking pass nothing to wait for",
      client.stage_pairs(home_row, "poster_path") == [],
      str(client.stage_pairs(home_row, "poster_path")))
check("...while the opted-in form gets both",
      len(client.stage_pairs(home_row, "poster_path", include_cdn=True)) == 2)

# -- batching over two lists in one call ---------------------------------

OTHER = CDN + "/v1/metadata/assets/tmdb/people/11/22/" + ("d" * 64) + ".jpg"
cast = [{"profile_url": HEADSHOT}, {"profile_url": OTHER}]
crew = [{"profile_url": HEADSHOT}]                      # same person, both lists
check("cast+crew in one call fetches a shared person once",
      len(client.stage_pairs(cast + crew, "profile_url", include_cdn=True)) == 2)
check("a person with no photo is skipped, not queued as an empty fetch",
      client.stage_pairs([{"profile_url": None}, {"profile_url": ""}],
                         "profile_url", include_cdn=True) == [])

failed = [n for n, ok in RESULTS if not ok]
print("\nCDN art staging (%d checks)" % len(RESULTS))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
