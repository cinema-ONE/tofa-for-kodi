"""Cast & Crew headshots belong in the staging area; the rest of the CDN does not.

WHY THIS EXISTS. Measured on the cinema box 2026-08-22, cold: opening a
show's Cast & Crew made Kodi fetch every headshot from the metadata CDN and
push it through its OWN texture cache -- download, decode, resize,
re-encode, write to eMMC, INSERT into Textures14.db, four jobs at a time.
The downloads were quick (20-280ms each); the commit was not, and the panel
sat still for 1.8 seconds after the first four. Seven shows sampled at
random each added 6-11 NEW rows, so this is paid on every title opened.

Staged art skips all of it: 3821 staged files had produced 13 texture rows
in total, against 323 rows for headshots alone.

The carve-out has to be NARROW. Staging the whole CDN was tried once and
reverted -- discovery posters were then dragged over the internet on every
cold Home build, and two rows timed out mid batch. So these checks pin both
halves: headshots in, everything else on that host still out.
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
HEADSHOT = CDN + "/v1/metadata/assets/tmdb/people/00/5c/" + ("a" * 64) + ".jpg"
DISCOVERY = CDN + "/v1/metadata/assets/tmdb/discovery/01/b4/" + ("b" * 64) + ".jpg"
TITLE_ART = CDN + "/v1/metadata/assets/tmdb/title/02/15/" + ("c" * 64) + ".jpg"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


client = api.MediaServerClient(None, LAN, "tok", "dev")

# -- what is staged -------------------------------------------------------

check("a CDN headshot is stageable", client._stageable(HEADSHOT))
check("a CDN discovery poster is NOT", not client._stageable(DISCOVERY))
check("CDN title art is NOT", not client._stageable(TITLE_ART))
check("our own server still is", client._stageable(LAN + "/cache/images/posters/x.jpg"))
check("a relative path still is", client._stageable("images/posters/x.jpg"))

# -- stage_pair agrees with resolve_image_url ------------------------------
#
# They must, or a card stages the file and then draws the remote URL anyway,
# paying both costs. stage_pair is the batch side; resolve_image_url is what
# the card calls.

pair = client.stage_pair(HEADSHOT)
check("stage_pair yields a headshot pair", pair is not None)
if pair:
    url, key = pair
    check("the fetch URL is the CDN's, untokenised",
          url == HEADSHOT and "?st=" not in url, url)
    check("the staging key is the PATH, not the URL",
          key == "/v1/metadata/assets/tmdb/people/00/5c/" + ("a" * 64) + ".jpg", key)
    name = artcache.local_name(key)
    check("the flattened filename fits the 180-char cap and stays distinct",
          name.endswith(("a" * 64) + ".jpg") and len(name) <= 180, name)

check("stage_pair still declines a discovery poster",
      client.stage_pair(DISCOVERY) is None)

# -- batching over cast + crew --------------------------------------------
#
# ONE call over both lists, so a person credited in each is fetched once.
# stage_pairs deduplicates within a call and cannot across two.

OTHER = CDN + "/v1/metadata/assets/tmdb/people/11/22/" + ("d" * 64) + ".jpg"
cast = [{"profile_url": HEADSHOT}, {"profile_url": OTHER}]
crew = [{"profile_url": HEADSHOT}]                      # same person, both lists
pairs = client.stage_pairs(cast + crew, "profile_url")
check("cast+crew in one call fetches a shared person once",
      len(pairs) == 2, str(pairs))

check("a person with no photo is skipped, not queued as an empty fetch",
      client.stage_pairs([{"profile_url": None}, {"profile_url": ""}],
                         "profile_url") == [])

failed = [n for n, ok in RESULTS if not ok]
print("\nheadshot staging (%d checks)" % len(RESULTS))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
