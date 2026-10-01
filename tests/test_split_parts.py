"""A film or episode split across files plays as one title.

Members of a multi-part set (server 0.11.0 numbers them) are grouped, timed
and resumed as one; a part that is not the last is never reported as far as
the server's finish point, which would finish the whole title.

Run:  python3 test_split_parts.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import parts

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


P1 = {"id": "p1", "part_number": 1, "part_count": 2, "duration_ms": 3185184}
P2 = {"id": "p2", "part_number": 2, "part_count": 2, "duration_ms": 3183488}
HD = {"id": "hd", "duration_ms": 6000000}


def main():
    check("two parts are one set, in order, beside a plain file",
          [[f["id"] for f in g] for g in parts.sets([P2, HD, P1])], [["p1", "p2"], ["hd"]])
    check("a set with a part missing falls apart into its members",
          [[f["id"] for f in g] for g in parts.sets([P2])], [["p2"]])
    other = dict(P1, id="x1", edition="Director's Cut")
    check("another edition's parts are another set",
          len(parts.sets([P1, P2, other, dict(P2, id="x2", edition="Director's Cut")])), 2)
    group = parts.set_of([HD, P1, P2], "p2")
    check("a part finds its set", [f["id"] for f in group], ["p1", "p2"])
    check("a plain file has none", parts.set_of([HD, P1, P2], "hd"), [])
    check("the title lasts as long as its parts", parts.duration_ms(group), 6368672)
    check("part 2 starts where part 1 ends", parts.start_ms(group, 1), 3185184)
    check("a title position finds its part", parts.locate(group, 3200000), (1, 14816))
    check("...and the very end stays in the last part",
          parts.locate(group, 9_000_000), (1, 3183488))
    check("a 53-minute part is held short of 90%",
          parts.progress_cap_ms(3185184), 2861665)
    check("a 20-minute part short of 5 minutes left", parts.progress_cap_ms(1_200_000), 895_000)
    check("resume in part 2 where it was left",
          parts.resume_point(group, {"p1": {"position_ms": 0, "completed": False, "updated_at": "1"},
                                     "p2": {"position_ms": 600000, "updated_at": "2"}}), (1, 600000))
    check("...the part written last wins, not the later part",
          parts.resume_point(group, {"p1": {"position_ms": 2800000, "updated_at": "2026-10-01T08:46"},
                                     "p2": {"position_ms": 2, "updated_at": "2026-10-01T08:12"}}),
          (0, 2800000))
    check("...an empty record written in the same second does not win",
          parts.resume_point(group, {"p1": {"position_ms": 2700000, "updated_at": "11:16:31"},
                                     "p2": {"position_ms": 0, "completed": False,
                                            "updated_at": "11:16:31"}}), (0, 2700000))
    check("...at part 2's start after a finished part 1",
          parts.resume_point(group, {"p1": {"position_ms": 0, "completed": True}}), (1, 0))
    check("...and from the top with nothing recorded", parts.resume_point(group, {}), (0, 0))
    check("a set is labelled by its parts", (parts.label(group), parts.label([HD])),
          ("2 parts", None))

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
