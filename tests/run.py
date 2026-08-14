#!/usr/bin/env python3
"""Run every test_*.py beside this file, each in its own process.

Separate processes on purpose: kodi_stubs installs modules into sys.modules
and the suites monkey-patch http.request_json, so sharing an interpreter
would let one suite's stubbing leak into the next.

    python3 tests/run.py
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    suites = sorted(HERE.glob("test_*.py"))
    if not suites:
        print("no test_*.py found")
        return 1
    failed = []
    for suite in suites:
        print(f"\n=== {suite.name} " + "=" * (60 - len(suite.name)), flush=True)
        result = subprocess.run([sys.executable, str(suite)], cwd=HERE)
        if result.returncode:
            failed.append(suite.name)
    print("\n" + "=" * 64)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(suites)} suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
