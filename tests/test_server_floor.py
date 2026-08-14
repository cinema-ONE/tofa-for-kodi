# -*- coding: utf-8 -*-
"""The server floor is named in three places and must not drift.

release.py enforces this at package time, which is the backstop. Running it
here too means the drift fails on the commit that caused it rather than
weeks later when someone builds a zip.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import release  # noqa: E402  (tools/, not the add-on -- no Kodi stubs needed)

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))


floor = release.server_floor()
check("serverversion.py declares a floor", bool(floor), str(floor))
check("README.txt names the same one",
      release.readme_server_version() == floor,
      f"README {release.readme_server_version()} vs code {floor}")
check("no drift between any of the three", not release.server_problems(),
      "; ".join(release.server_problems()))

# The spec is allowed to LAG -- 0.9.29 shipped avatars and home rows with no
# spec update -- but never to LEAD, which would mean we vendored a contract
# the client does not claim to support.
spec = release.spec_version()
if spec:
    check("the vendored spec does not lead the floor",
          release.compare(spec, floor) <= 0, f"spec {spec} > floor {floor}")
else:
    print("SKIP  no vendored spec here (internal-docs/ is private)")

# The runtime check must agree with what release.py reads out of the file --
# a regex and a constant that disagree would make all of the above theatre.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kodi_stubs  # noqa: E402,F401
from resources.lib import serverversion  # noqa: E402

check("the regex reads the same tuple the client enforces",
      serverversion.format_version(serverversion.MIN_SERVER_VERSION) == floor,
      f"{serverversion.MIN_SERVER_VERSION} vs {floor}")
check("...and a server one patch older is refused",
      not serverversion.is_supported(
          "%s.%s.%d" % (serverversion.MIN_SERVER_VERSION[0],
                        serverversion.MIN_SERVER_VERSION[1],
                        serverversion.MIN_SERVER_VERSION[2] - 1)))

print("\n" + "=" * 60)
if FAILED:
    print(f"{FAILED} of {CHECKS} checks FAILED")
    raise SystemExit(1)
print(f"all {CHECKS} checks passed")
