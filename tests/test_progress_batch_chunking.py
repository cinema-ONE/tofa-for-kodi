"""The progress batch endpoint takes at most 500 ids. Ask for more and the
whole read fails.

The incident (LibreELEC NUC, 2026-08-28, add-on 0.9.18): a show with 801
playable episodes. Opening its Detail page made `_next_up_episode` ask
`progress.fetch_many` about every one of them in a single request, and the
server answered

    HTTP 400 bad_request: Bad request: Maximum 500 media file IDs per batch
    request

so the page could not work out which episode to offer next, and with
`required=True` the exception came out through `refresh_watch_progress`. Any
show past 500 files was affected; nothing under it ever was, which is why it
took a big show to find.

The cap is NOT in the vendored spec -- `BatchProgressRequest` declares
`media_file_ids` with no `maxItems` -- so it is known only from the server's
error text.

Four properties are tested here:

  1. no request ever carries more than BATCH_LIMIT ids,
  2. every id is asked about exactly once, and the answers are merged,
  3. a set that fits still goes in ONE request (chunking must not undo the
     batching it exists to protect), and
  4. a failing chunk keeps the documented all-or-nothing contract: {} when
     the caller can live without an answer, a raise when it cannot.

Run:  python3 test_progress_batch_chunking.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import http, progress

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class Recorder:
    """A client that records the batches it was asked for and answers them.

    `fail_on` is the index of the call that raises, so a partial failure can
    be provoked at a chosen point rather than only at the first request.
    """

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def media_progress_batch(self, file_ids):
        self.calls.append(list(file_ids))
        if self.fail_on is not None and len(self.calls) - 1 == self.fail_on:
            raise http.ApiError(400, "bad_request",
                                "Maximum 500 media file IDs per batch request")
        return {"items": [{"media_file_id": f, "position_ms": 1000,
                           "completed": False} for f in file_ids]}


LIMIT = progress.BATCH_LIMIT
BIG = ["f%d" % i for i in range(801)]          # the show that found this

# --------------------------------------------------------------------------
# 1 + 2. Chunked, and complete
# --------------------------------------------------------------------------
rec = Recorder()
got = progress.fetch_many(rec, BIG)

check("the cap is the server's 500, not a tuned number", LIMIT == 500, str(LIMIT))
check("801 ids go in more than one request", len(rec.calls) > 1, str(len(rec.calls)))
check("no request exceeds the cap",
      all(len(c) <= LIMIT for c in rec.calls), str([len(c) for c in rec.calls]))
check("801 ids take exactly 2 requests at 500",
      [len(c) for c in rec.calls] == [500, 301], str([len(c) for c in rec.calls]))
check("every id was asked about, in order",
      [f for c in rec.calls for f in c] == BIG)
check("no id was asked about twice",
      len({f for c in rec.calls for f in c}) == len(BIG))
check("the answers from both chunks are merged",
      len(got) == len(BIG) and got["f0"]["position_ms"] == 1000
      and got["f800"]["position_ms"] == 1000, str(len(got)))

# --------------------------------------------------------------------------
# 3. Chunking must not undo the batching
# --------------------------------------------------------------------------
rec = Recorder()
progress.fetch_many(rec, ["a", "b", "c"])
check("a small set still goes in ONE request", len(rec.calls) == 1, str(len(rec.calls)))

rec = Recorder()
progress.fetch_many(rec, ["f%d" % i for i in range(LIMIT)])
check("exactly the cap still goes in ONE request", len(rec.calls) == 1,
      str([len(c) for c in rec.calls]))

rec = Recorder()
check("an empty list asks nothing at all",
      progress.fetch_many(rec, []) == {} and rec.calls == [])

rec = Recorder()
progress.fetch_many(rec, ["a", None, "a", "b", ""])
check("blanks and duplicates are dropped before chunking",
      rec.calls == [["a", "b"]], str(rec.calls))

# --------------------------------------------------------------------------
# 4. All-or-nothing survives chunking
# --------------------------------------------------------------------------
# The SECOND chunk fails, so the first one's answers are in hand and are
# deliberately thrown away: a partial map would read as "not watched" for
# every id in the failed chunk, which is the lie this contract exists to
# avoid -- see fetch_many's docstring.
rec = Recorder(fail_on=1)
check("a later chunk failing answers {}, not a partial map",
      progress.fetch_many(rec, BIG) == {})
check("...and it did get as far as the second chunk", len(rec.calls) == 2,
      str(len(rec.calls)))

rec = Recorder(fail_on=1)
try:
    progress.fetch_many(rec, BIG, required=True)
    check("required=True re-raises from a later chunk", False, "no raise")
except http.ApiError:
    check("required=True re-raises from a later chunk", True)

rec = Recorder(fail_on=0)
check("a first-chunk failure still answers {}", progress.fetch_many(rec, BIG) == {})

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
