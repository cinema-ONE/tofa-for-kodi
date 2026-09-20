"""A server refusal is shown in the server's OWN words, where it has any.

8.7 is normative: `message` is written for viewers and the server can improve
it without a client release, so a client that substitutes its own sentence
freezes the wording at whatever it shipped with. We used to branch on the
HTTP STATUS and show one of three strings of our own; a viewer whose server
was busy converting read "The server couldn't start this file."

Our own sentence is kept for exactly the cases 8.7 names as having nothing
to quote, and for 404, where the server says the path is missing and ours
says what to do about it.

Run:  python3 test_viewer_message.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http

FALLBACK = "The server couldn't start this file."

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def err(status, error, message):
    return http.ApiError(status, error, message)


# 1. The two refusals 8.7 names: the server's sentence reaches the viewer.
# The sentences here are INVENTED, not the ones 8.7 tabulates. What is under
# test is that whatever the server said arrives unchanged; quoting the real
# copy would only pin a wording the server is free to improve without us --
# which is the whole argument for rendering it in the first place.
busy = err(503, "transcode_at_capacity", "Busy with other videos, one moment.")
check("a busy server speaks for itself",
      http.viewer_message(busy, FALLBACK) == busy.message,
      repr(http.viewer_message(busy, FALLBACK)))

slow = err(503, "transcode_realtime_unsupported", "Too slow to convert live.")
check("so does a server that cannot keep up",
      http.viewer_message(slow, FALLBACK) == slow.message)

# 2. No envelope: a bodyless rejection or an HTML gateway page. Useful in a
#    log, never on a television.
html = err(502, http.NO_ENVELOPE, "<html><head><title>502 Bad Gateway</title>")
check("an HTML gateway page never reaches the screen",
      http.viewer_message(html, FALLBACK) == FALLBACK,
      repr(http.viewer_message(html, FALLBACK)))
check("nor does a bodyless rejection",
      http.viewer_message(err(503, http.NO_ENVELOPE, ""), FALLBACK) == FALLBACK)

# 3. The discriminator echoed as the message is ABSENT, per 8.7 -- a machine
#    token must never be the sentence.
check("message == error is treated as absent",
      http.viewer_message(err(503, "transcode_at_capacity",
                              "transcode_at_capacity"), FALLBACK) == FALLBACK)
check("...including with whitespace around it",
      http.viewer_message(err(503, "transcode_at_capacity",
                              "  transcode_at_capacity  "), FALLBACK) == FALLBACK)

# 4. Nothing there at all.
for empty in ("", "   ", None):
    check(f"an empty message ({empty!r}) falls back",
          http.viewer_message(err(500, "internal", empty), FALLBACK) == FALLBACK)

# 5. An unfamiliar discriminator still gets its sentence through: we branch
#    on `error` only to decide affordances, never to decide whether the
#    viewer is allowed to read why.
odd = err(409, "some_error_we_have_never_seen",
          "The library is being rebuilt. Try again shortly.")
check("an error code we do not know still speaks",
      http.viewer_message(odd, FALLBACK) == odd.message)

# 6. Whitespace is trimmed but the sentence is otherwise untouched -- we do
#    not rewrite the server's copy, including its register.
spaced = err(503, "x", "  This server is busy.  ")
check("the sentence is passed through, trimmed",
      http.viewer_message(spaced, FALLBACK) == "This server is busy.",
      repr(http.viewer_message(spaced, FALLBACK)))

# 7. The status line is never the answer, whichever way it arrives.
for bad in ("Service Unavailable", "502 Bad Gateway"):
    e = err(503, http.NO_ENVELOPE, bad)
    check(f"{bad!r} never reaches the screen",
          http.viewer_message(e, FALLBACK) == FALLBACK)

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
