# -*- coding: utf-8 -*-
"""No module-scope import of a platform-only stdlib module.

0.9.5 shipped `import fcntl` inside auth._refresh_lock. fcntl is POSIX-only,
so on Windows the add-on raised ModuleNotFoundError on the FIRST action of
every entry point -- `get_client()` -> `ensure_fresh()` -> the lock -- and
nothing ever drew. It reached a user before it reached us, because the boxes
are CoreELEC and Android and the dev rig is macOS: nothing in the loop runs
Windows.

An import that a `try/except ImportError` guards is fine -- that is how the
fix reaches msvcrt. What this catches is an UNGUARDED one, anywhere, at any
indent: the crash was inside a function body, which is exactly why nothing
caught it until a stranger ran it.

Parses the source rather than importing it: importing every module would
need the whole Kodi surface stubbed, and would only ever exercise the
platform running the test.
"""
import ast
import pathlib
import sys

ADDON = pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"

# Stdlib modules that do not exist on every platform Kodi runs on.
POSIX_ONLY = {"fcntl", "termios", "pwd", "grp", "crypt", "posix", "pty",
              "tty", "resource", "syslog", "spwd", "nis", "readline"}
WINDOWS_ONLY = {"msvcrt", "winreg", "winsound", "_winapi"}
PLATFORM_ONLY = POSIX_ONLY | WINDOWS_ONLY

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def _guarded_spans(tree):
    """Line ranges of every `try:` body whose handlers catch ImportError."""
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            names = []
            if isinstance(handler.type, ast.Name):
                names = [handler.type.id]
            elif isinstance(handler.type, ast.Tuple):
                names = [e.id for e in handler.type.elts if isinstance(e, ast.Name)]
            elif handler.type is None:
                names = ["ImportError"]           # bare except catches it too
            if {"ImportError", "ModuleNotFoundError", "Exception"} & set(names):
                for stmt in node.body:
                    spans.append((stmt.lineno, getattr(stmt, "end_lineno", stmt.lineno)))
                break
    return spans


def _unguarded_platform_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    spans = _guarded_spans(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        hits = [n for n in names if n in PLATFORM_ONLY]
        if not hits:
            continue
        if any(lo <= node.lineno <= hi for lo, hi in spans):
            continue
        found.append((node.lineno, hits))
    return found


def main():
    sources = sorted(ADDON.rglob("*.py"))
    check("there are add-on sources to scan", len(sources) > 20, str(len(sources)))

    offenders = []
    for path in sources:
        for lineno, hits in _unguarded_platform_imports(path):
            offenders.append("%s:%d imports %s"
                             % (path.relative_to(ADDON), lineno, ", ".join(hits)))
    check("no unguarded platform-only import anywhere in the add-on",
          not offenders, "; ".join(offenders[:4]))

    # The detector has to actually detect: prove it on the 0.9.5 shape, and
    # prove the guarded shape the fix uses is NOT flagged.
    import tempfile

    def scan(src):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(src)
            tmp = pathlib.Path(fh.name)
        try:
            return _unguarded_platform_imports(tmp)
        finally:
            tmp.unlink()

    check("...and the check would have caught the 0.9.5 crash",
          scan("def lock():\n    import fcntl\n    return fcntl\n"))
    check("...including one at module scope", scan("import termios\n"))
    check("...and from-imports", scan("from fcntl import flock\n"))
    check("a try/except ImportError guard is accepted",
          not scan("try:\n    import fcntl\nexcept ImportError:\n    fcntl = None\n"))
    check("a portable import is not flagged", not scan("import os\nimport json\n"))

    # The one real guarded use, spelled out so a future edit has to face it.
    auth = ADDON / "resources" / "lib" / "auth.py"
    src = auth.read_text(encoding="utf-8")
    check("auth.py still guards its fcntl import",
          "except ImportError:" in src and "import fcntl" in src)
    check("...and still carries the Windows path it falls back to",
          "msvcrt" in src and "_lock_exclusive" in src)

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("portable stdlib: no platform-only import goes unguarded (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
