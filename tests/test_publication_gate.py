# -*- coding: utf-8 -*-
"""Nothing becomes public except through a gate that read it first.

`check_public_set.py` has always read the working TREE, and the tree is not
the only thing this repository publishes. On 2026-09-20 that cost something:
the tree gate caught two of tofa's sentences, they were paraphrased, and the
commit was re-made with `git commit --amend --no-edit` -- which keeps the
ORIGINAL message. Both sentences were still in it, the gate passed twice
because it never looked at a message, and they were pushed and merged.

Rewriting afterwards did not take them back. GitHub went on serving the
orphaned commit by SHA and `refs/pull/N/head` went on rendering it. That is
why these are tests and not a note in CONTRIBUTING: the only cheap moment is
before the write, so every surface has to be checked before it, every time.

The surfaces, and who covers them:

    working tree ......... scan_quotes          (tree gate, since the start)
    commit messages ...... scan_messages        (this file's reason to exist)
    annotated tag messages scan_messages
    PR title / body ...... scan_text  <- gh_gate.py
    issue / comment ...... scan_text  <- gh_gate.py
    squash commit message  gh_gate.squash_message, which composes it LOCALLY
                           so GitHub never builds one out of text nobody read

Nothing here reads tofa's real documents. A synthetic private source is
written to a temp directory and the module is pointed at it, so this suite
proves the MECHANISM and runs anywhere -- including CI, which has no vault
and must never have one.

Run:  python3 test_publication_gate.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import check_public_set as gate  # noqa: E402
import gh_gate  # noqa: E402

CHECKS = FAILED = 0

#: Plain English, long enough to be prose rather than a coincidence, and made
#: of nothing that appears in this repository.
SECRET = ("The lantern keeper counted seventeen herons on the estuary before "
          "the tide turned and the marsh birds rose together in one sheet.")
INNOCENT = "A perfectly ordinary sentence about nothing that anyone owns."


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def git(repo, *args, **kw):
    return subprocess.run(("git",) + args, cwd=repo, capture_output=True,
                          text=True, check=True, **kw).stdout


with tempfile.TemporaryDirectory(prefix="gate-") as base:
    # --- a private source that is ours, so the suite carries no secrets ----
    vault = os.path.join(base, "vault")
    os.makedirs(os.path.join(vault, "internal-docs"))
    source = os.path.join("internal-docs", "TV-DESIGN.md")
    with open(os.path.join(vault, source), "w") as fh:
        fh.write("# not the real one\n\n" + SECRET + "\n")

    repo = os.path.join(base, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "Test")
    pathlib.Path(repo, "a.txt").write_text("hello\n")
    git(repo, "add", "a.txt")

    gate.VAULT = vault
    gate.ROOT = repo
    gate.PRIVATE_SOURCES = [(source, "tofa", "the design document")]

    def messages(rev_range=None, count=50):
        return [h for h in gate.scan_messages(gate.DEFAULT_N, count, rev_range)
                if h[5]]

    # --- 1. the failure of 2026-09-20, reproduced exactly -----------------
    git(repo, "commit", "-q", "-m", "a clean subject\n\n" + SECRET)
    check("a quoting commit MESSAGE is caught", len(messages()) == 1)

    pathlib.Path(repo, "a.txt").write_text("paraphrased\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "--amend", "--no-edit")
    check("`--amend --no-edit` does NOT clear it -- the whole incident",
          len(messages()) == 1,
          "amending the tree left the message, and the gate must still see it")

    git(repo, "commit", "-q", "--amend", "-m", "a clean subject\n\nown words")
    check("rewording the message clears it", messages() == [])

    # --- 2. the tree gate still does its own job --------------------------
    pathlib.Path(repo, "b.py").write_text("# " + SECRET + "\n")
    git(repo, "add", "b.py")
    git(repo, "commit", "-q", "-m", "add b")
    gate.candidates = lambda: [os.path.join(repo, "b.py")]
    hits, missing = gate.scan_quotes(gate.DEFAULT_N)
    check("a quoting COMMENT is caught by the tree gate",
          [h for h in hits if h[5]] != [] and missing == [])

    # --- 3. annotated tags, which go out with --tags and nobody checks ----
    git(repo, "tag", "-a", "v9.9.9", "-m", "release\n\n" + SECRET)
    check("a quoting annotated TAG message is caught",
          any(h[2].startswith("tag ") for h in messages()))
    git(repo, "tag", "-d", "v9.9.9")

    # --- 4. --range covers exactly what is being pushed -------------------
    first = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    git(repo, "commit", "-q", "--allow-empty", "-m", "later\n\n" + SECRET)
    head = git(repo, "rev-parse", "HEAD").strip()
    check("--range finds a hit inside the range",
          len(messages(rev_range=["-1", head])) == 1)
    check("--range excludes what the remote already has",
          messages(rev_range=[head, "^" + head]) == [])
    check("a range naming only older commits does not see the new one",
          messages(rev_range=["-1", first]) == [])

    # --- 5. arbitrary candidate text: PR bodies, issues, release notes ----
    dirty = os.path.join(base, "dirty.md")
    clean = os.path.join(base, "clean.md")
    pathlib.Path(dirty).write_text("intro\n\n" + SECRET + "\n")
    pathlib.Path(clean).write_text(INNOCENT + "\n")
    check("scan_text catches a quoting PR body",
          len([h for h in gate.scan_text([dirty], gate.DEFAULT_N) if h[5]]) == 1)
    check("scan_text passes text of our own",
          gate.scan_text([clean], gate.DEFAULT_N) == [])

    # --- 6. gh_gate pulls the text out of every shape of gh command -------
    def harvested(argv):
        return sorted(flag for flag, _text in gh_gate.harvest(argv)[1])

    check("gh_gate harvests --title and --body",
          harvested(["pr", "create", "--title", "t", "--body", "b"])
          == ["--body", "--title"])
    check("gh_gate harvests --flag=value as well as --flag value",
          harvested(["pr", "create", "--title=t"]) == ["--title"])
    check("gh_gate harvests a --body-file's CONTENTS",
          gh_gate.harvest(["pr", "create", "--body-file", dirty])[1][0][1]
          .strip().endswith(SECRET))
    check("gh_gate harvests gh's short aliases",
          harvested(["issue", "comment", "1", "-b", "x", "-F", clean])
          == ["-F", "-b"])
    check("gh_gate leaves a command with no text alone",
          harvested(["pr", "view", "189", "--json", "title"]) == [])

    # --- 7. the squash merge, which has no text in its command line -------
    argv = ["pr", "merge", "12", "--squash"]
    check("a squash merge carries no text of its own, which is the trap",
          harvested(argv) == [],
          "so gh_gate must compose the message rather than let GitHub do it")

print()
if FAILED:
    print("FAIL: %d of %d" % (FAILED, CHECKS))
    raise SystemExit(1)
print("publication gate: every public surface is read before it is written "
      "(%d checks)" % CHECKS)
