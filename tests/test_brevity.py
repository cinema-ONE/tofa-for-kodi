"""Commit messages and new comments stay short (tools/check_brevity.py).

Run:  python3 test_brevity.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import check_brevity as B  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def diff(path, *added):
    return f"+++ b/{path}\n@@ -1,0 +1,{len(added)} @@\n" + "\n".join("+" + a for a in added)


TRAILER = "\n\nCo-Authored-By: Someone <x@example.com>"
check("a short message passes",
      B.message_problems("a" * 40, "fix: short\n\nOne line of why." + TRAILER) == [])
check("a 66-char subject fails", len(B.message_problems("s", "x" * 66)) == 1)
check("a 9-line body fails",
      len(B.message_problems("s", "ok\n\n" + "\n".join(["line"] * 9))) == 1)
check("blank lines and trailers do not count",
      B.message_problems("s", "ok\n\n" + "\n\n".join(["line"] * 8) + TRAILER) == [])
check("a 4-line comment passes",
      B.comment_problems("s", diff("a.py", *["# why"] * 4, "x = 1")) == [])
check("a 5-line comment fails",
      len(B.comment_problems("s", diff("a.py", *["# why"] * 5))) == 1)
check("an XML comment counts its lines",
      len(B.comment_problems("s", diff("t.tpl", "<!-- a", "b", "c", "d", "e -->"))) == 1)
check("rendered skin XML is not checked",
      B.comment_problems("s", diff(B.GENERATED + "x.xml", *["<!-- a -->"] * 9)) == [])
check("a shebang and coding line are not comments",
      B.comment_problems("s", diff("a.py", "#!/usr/bin/env python3", "# -*- coding: utf-8 -*-",
                                   "# a", "# b", "# c", "# d")) == [])

check("a \"<!--\" inside Python code does not open a comment",
      B.comment_problems("s", diff("a.py", 'if "<!--" in text:', *["x = 1"] * 6)) == [])

print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
raise SystemExit(0 if all(RESULTS) else 1)
