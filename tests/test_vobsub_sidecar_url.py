"""A VobSub sidecar has to be asked for as `.idx`, and the token has to be
in the QUERY STRING when it is.

Both halves matter, and the second one is the subtle one.

Server 0.9.32 delivers a sidecar VobSub track as two files -- `full.idx` and
a companion `full.sub`. We only ever ask for the `.idx`; Kodi derives the
`.sub` on its own (`CVideoPlayer::AddSubtitleFile` -> `CUtil::
GetVobSubSubFromIdx` -> `URIUtils::ReplaceExtension`). Our URLs carry the
scoped session token as `?st=`, and that derivation only survives it because
ReplaceExtension routes a URL through `CURL`, which holds the query string
apart from the filename. So the extension MUST be the last thing before the
`?`: `full.idx?st=<token>` becomes `full.sub?st=<token>`, where anything that
put the extension elsewhere would produce a 404 or a 401.

Measured on Kodi 21.3 against a mock of the two routes that 401s without the
token: GET full.idx?st=..., HEAD full.sub?st=..., then range reads of both,
and the cues rendered.

The third check is the one that keeps this honest. An EMBEDDED `dvd_subtitle`
-- an old disc rip muxed into the container -- reaches the same code path
whenever the server is transcoding, because Kodi then has no subtitle stream
to select. The `full.idx` route answers 400 for anything that is not a paired
sidecar, so asking for `.idx` there would turn a track that merely does not
appear into an error.

Run:  python3 test_vobsub_sidecar_url.py
"""
import urllib.parse

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import tracks
from resources.lib.profile import CapabilityProfile
from resources.lib.windows.player import PlayerWindow

RESULTS = []

TOKEN = "tok-with/slash+plus"
SESSION = "11111111-2222-3333-4444-555555555555"

VOBSUB = {"index": 1000, "codec": "dvd_subtitle", "language": "ger",
          "external": True, "render": "bitmap"}
SRT = {"index": 1001, "codec": "subrip", "language": "eng",
       "external": True, "render": "text"}
EMBEDDED_VOBSUB = {"index": 3, "codec": "dvd_subtitle", "language": "eng",
                   "external": False, "render": "bitmap"}


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeClient:
    base = "http://box.local:33333"

    def resolve_url(self, path):
        return self.base + path


class Fake:
    """Only what _external_subtitle_url actually reaches."""
    _external_subtitle_url = PlayerWindow._external_subtitle_url
    _is_vobsub_sidecar = staticmethod(PlayerWindow._is_vobsub_sidecar)

    def __init__(self, tracks_):
        self._subtitle_tracks = list(tracks_)
        self._nego = {"session_id": SESSION, "session_token": TOKEN}
        self.client = FakeClient()


def run():
    win = Fake([VOBSUB, SRT, EMBEDDED_VOBSUB])

    # 1. The sidecar is asked for as .idx.
    url = win._external_subtitle_url(1000)
    path, _, query = url.partition("?")
    check("an external dvd_subtitle is fetched as full.idx",
          path.endswith("/subtitles/1000/full.idx"), url)

    # 2. ...and the token is in the QUERY, so Kodi's .sub derivation keeps it.
    check("the session token rides in the query string, not the filename",
          query == "st=" + urllib.parse.quote(TOKEN), url)
    companion = path[:-len(".idx")] + ".sub" + "?" + query
    check("the companion Kodi derives is full.sub with the token intact",
          companion.endswith("/subtitles/1000/full.sub?st="
                             + urllib.parse.quote(TOKEN)), companion)

    # 3. An EMBEDDED dvd_subtitle is NOT a sidecar; the route would 400.
    url = win._external_subtitle_url(3)
    check("an embedded dvd_subtitle is left on full.vtt",
          url.partition("?")[0].endswith("/subtitles/3/full.vtt"), url)

    # 4. Text tracks are untouched by any of this.
    url = win._external_subtitle_url(1001)
    check("a text sidecar still asks for full.vtt",
          url.partition("?")[0].endswith("/subtitles/1001/full.vtt"), url)

    # 5. A track the negotiation never described falls back to .vtt rather
    #    than raising -- the same shape the method had before.
    url = win._external_subtitle_url(4242)
    check("an unknown index degrades to full.vtt",
          url.partition("?")[0].endswith("/subtitles/4242/full.vtt"), url)

    # 6. Without the capability the server routes these to burn-in, so the
    #    flag has to be ON the wire, not merely on the dataclass.
    params = CapabilityProfile().to_query_params()
    check("the profile tells the server we can render VobSub",
          params.get("client_render_vobsub_subtitles") == "true",
          repr(params.get("client_render_vobsub_subtitles")))

    # 7. The picker has to name the format, or the row reads as a mystery.
    label, detail = tracks.subtitle_track_label(VOBSUB)
    check("the picker row says VobSub, and says it is external",
          detail == "VobSub · External", repr(detail))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("vobsub sidecars: .idx asked for, token kept in the query (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
