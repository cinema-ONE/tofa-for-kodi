#!/usr/bin/env python3
"""Run `gh`, but never publish text that quotes a private document.

    python3 tools/gh_gate.py pr create --title "..." --body-file body.md
    python3 tools/gh_gate.py pr merge 189 --squash --delete-branch
    python3 tools/gh_gate.py issue comment 161 --body-file evidence.md

Everything after the script name is passed to `gh` unchanged. What happens
first is that every piece of TEXT in that command line is pulled out and put
through `check_public_set.py`, and a hit stops the command before anything
reaches GitHub.

WHY THIS EXISTS. `check_public_set.py` gates the working tree, and since
2026-09-20 it gates commit and tag messages too. Between them they cover
everything that arrives at GitHub through `git`. They cover none of what
arrives through the API: a pull request's title and body, an issue, a
comment, a release note. Those are as public as any file, they are indexed,
and -- this is the part that cost something -- **a rewrite does not take them
back**. On 2026-09-20 a quoted run was force-pushed out of `main` and GitHub
carried on serving it from the orphaned commit and from `refs/pull/N/head`.
The only cheap moment is before the write.

So the rule is one sentence: **nothing becomes public except through a tool
that gated it.** This is that tool for the GitHub half; `git push` is covered
by `tools/hooks/pre-push`.

WHAT GETS GATED. The value of every text-bearing flag, whether inline or from
a file: --title, --body, --body-file, --subject, --notes, --notes-file,
--message. `-F` and `-b` are handled as the aliases `gh` treats them as. A
`--body-file -` reads standard input, gates it, and hands the same bytes on,
so the pipe is not consumed twice.

THE ONE SPECIAL CASE: `pr merge --squash`. There is no text in that command
line at all -- GitHub composes the commit message on the server from the
branch's commits, or from the pull request title, and publishes it without
anything local ever seeing it. That is precisely the shape of the 2026-09-20
failure, one layer up. So this composes the message itself, from the same
ingredients GitHub would use, gates it, and passes it back with --subject and
--body, which makes the server compose nothing. The message that is published
is the message that was checked.

EXIT STATUS is the gate's when the gate refuses, and `gh`'s otherwise.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "tools", "check_public_set.py")

#: Flags whose value is text a human wrote, and which `gh` publishes as-is.
INLINE = {"--title", "-t", "--body", "-b", "--subject", "--notes", "--message",
          "-m"}
#: The same, but the value names a file (or `-` for stdin).
FROM_FILE = {"--body-file", "-F", "--notes-file"}


def gate(blobs: list[tuple[str, str]]) -> None:
    """Refuse the whole command if any blob quotes a private document.

    Blobs are (label, text). They go to the checker as real files because
    that is the interface it already has, and because the label it prints
    then says which flag the run came from.
    """
    if not blobs:
        return
    with tempfile.TemporaryDirectory(prefix="gh-gate-") as tmp:
        paths = []
        for label, text in blobs:
            safe = label.lstrip("-").replace("/", "_") or "text"
            path = os.path.join(tmp, safe + ".txt")
            with open(path, "w") as fh:
                fh.write(text)
            paths.append(path)
        done = subprocess.run([sys.executable, CHECKER, "--quotes", "--text"]
                              + paths)
    if done.returncode:
        sys.stderr.write(
            "\ngh_gate: NOT running `gh` -- the text above quotes a private\n"
            "document, or the gate had nothing to compare it against.\n\n"
            "Say it in our own words. A section pointer is fine; the\n"
            "document's own wording is not. Once this is posted it is public\n"
            "permanently -- editing it afterwards does not unpublish it.\n")
        sys.exit(done.returncode)


def harvest(argv: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Pull every text value out of a `gh` command line.

    Returns the argv to actually run -- identical apart from a `--body-file -`
    whose stdin has been read and written to a real file, since stdin cannot
    be consumed twice -- and the blobs to gate.
    """
    argv = list(argv)
    blobs: list[tuple[str, str]] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        flag, _, inline_value = arg.partition("=")
        has_inline = bool(_)
        value = inline_value if has_inline else (
            argv[i + 1] if i + 1 < len(argv) else "")
        if flag in INLINE and value:
            blobs.append((flag, value))
        elif flag in FROM_FILE and value:
            if value == "-":
                text = sys.stdin.read()
                fh = tempfile.NamedTemporaryFile("w", suffix=".md",
                                                 delete=False)
                fh.write(text)
                fh.close()
                if has_inline:
                    argv[i] = "%s=%s" % (flag, fh.name)
                else:
                    argv[i + 1] = fh.name
                blobs.append((flag, text))
            else:
                try:
                    with open(value) as fh:
                        blobs.append((flag, fh.read()))
                except OSError as exc:
                    sys.exit("gh_gate: cannot read %s: %s" % (value, exc))
        i += 1 if has_inline or flag not in (INLINE | FROM_FILE) else 2
    return argv, blobs


def squash_message(number: str) -> tuple[str, str]:
    """The message we will publish for a squash merge, composed HERE.

    GitHub would build this on the server from the repository's
    `squash_merge_commit_*` settings, which means a PR title nobody gated can
    become a permanent public commit subject. Composing it locally costs two
    API calls and makes the published message identical to the checked one.

    One commit: its own subject and body, which is what the author wrote and
    what the pre-push gate already read. More than one: the pull request
    title, and the commit messages under it the way GitHub lists them.

    FULL messages, from the REST endpoint. `gh pr view --json commits` hands
    back GraphQL's `messageHeadline`, which GitHub TRUNCATES at about seventy
    characters with an ellipsis and carries on in `messageBody` -- so #191
    shipped as "...as the Apple TV app now… (#191)" with a body opening
    "… does". The text was all there and split in the wrong place.
    """
    title = subprocess.run(
        ["gh", "pr", "view", number, "--json", "title", "--jq", ".title"],
        cwd=ROOT, capture_output=True, text=True)
    raw = subprocess.run(
        ["gh", "api", "repos/{owner}/{repo}/pulls/%s/commits" % number,
         "--paginate", "--jq", "[.[].commit.message]"],
        cwd=ROOT, capture_output=True, text=True)
    if title.returncode or raw.returncode:
        sys.exit("gh_gate: cannot read pull request %s:\n%s"
                 % (number, (title.stderr or raw.stderr).strip()))
    messages = []
    for chunk in raw.stdout.split("\n"):          # --paginate: one array per page
        chunk = chunk.strip()
        if chunk:
            messages += json.loads(chunk)
    return compose_squash(number, title.stdout.strip(), messages)


def compose_squash(number: str, pr_title: str, messages: list) -> tuple[str, str]:
    """(subject, body) from FULL commit messages -- pure, so it is testable."""
    def split(message: str) -> tuple[str, str]:
        head, _, body = (message or "").strip().partition("\n")
        return head.strip(), body.strip()

    if len(messages) == 1:
        head, body = split(messages[0])
    else:
        head = pr_title
        parts = []
        for message in messages:
            h, b = split(message)
            parts.append("* " + h + (("\n\n" + b) if b else ""))
        body = "\n\n".join(parts)
    return "%s (#%s)" % (head, number), body


def main(argv: list[str]) -> int:
    if not argv:
        sys.exit(__doc__.strip().splitlines()[0])

    argv, blobs = harvest(argv)

    # The special case: a squash merge carries no text, so the text it will
    # publish has to be built before it can be gated.
    if argv[:2] == ["pr", "merge"] and "--squash" in argv:
        has_own = any(a.split("=")[0] in ("--subject", "--body", "--body-file")
                      for a in argv)
        number = next((a for a in argv[2:] if a.isdigit()), None)
        if not has_own and number:
            subject, body = squash_message(number)
            argv += ["--subject", subject, "--body", body]
            blobs += [("--subject", subject), ("--body", body)]

    # A PR title becomes the squash subject when there are several commits.
    long = [v for f, v in blobs if f in ("--title", "-t") and len(v) > 65]
    if long:
        sys.exit("gh_gate: title is %d chars (max 65, see check_brevity.py)"
                 % len(long[0]))
    gate(blobs)
    return subprocess.run(["gh"] + argv, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
