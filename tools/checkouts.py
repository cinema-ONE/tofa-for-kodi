# -*- coding: utf-8 -*-
"""Find the OTHER checkout, once the add-on and the vault stop being one tree.

The plan (MANIFEST.md) is that `tofa-for-kodi` becomes the working repo and
`tofa-vault` (renamed from `tofa-kodi` on 2026-08-18) is demoted to an
internals vault checked out beside it. Two kinds of tool break the moment
that happens, in opposite directions:

* Tools that TRAVEL and need private material. `check_public_set` compares
  the public file set against tofa's confidential documents, and
  `release.py check` compares the server floor against the vendored OpenAPI
  spec. Neither document is in the public repo, by design -- so run from
  there, one gate goes silent and the other has nothing to read.
* Tools that STAY and need the add-on. Every live-box probe and bench reads
  or deploys `plugin.video.tofa/`, which will no longer be beside them.

Both are the same question -- "where is the sibling checkout that has X" --
so it is answered once, here.

WHY A MARKER FILE RATHER THAN A DIRECTORY NAME. The two clones happen to be
`~/code/tofa-vault` and `~/code/tofa-for-kodi` today, but a name is a
property of whoever ran `git clone`, not of the repository. A fresh clone
with a different name would silently resolve to nothing, and "silently" is
the failure mode this whole area keeps producing. Content is the honest test.

WHAT THIS DELIBERATELY DOES NOT DO: invent a fallback. Every caller here is
verifying something, and a resolver that quietly answers "no vault" turns a
gate into a decoration. This returns None and lets the caller decide how loud
to be -- `check_public_set` fails outright, `release.py` says so and carries
on, because its CI legitimately has no vault.
"""
from __future__ import annotations

import os
from typing import Optional

#: What identifies each checkout. Directories, not files, so a rename inside
#: them does not break resolution -- and see the module docstring for why not
#: the checkout's own name.
VAULT_MARKER = "internal-docs"
ADDON_MARKER = os.path.join("plugin.video.tofa", "addon.xml")

#: Overrides, for a layout this cannot guess: a vault somewhere other than
#: beside the working copy, or a CI job that mounts one.
VAULT_ENV = "TOFA_VAULT"
ADDON_ENV = "TOFA_ADDON_REPO"


def _has(root: str, marker: str) -> bool:
    return bool(root) and os.path.exists(os.path.join(root, marker))


def _siblings(root: str):
    """Immediate neighbours of `root`, sorted, excluding itself.

    One level only. A recursive search would eventually find a stale copy in
    someone's backup directory and use it without saying so.
    """
    parent = os.path.dirname(os.path.abspath(root.rstrip(os.sep)))
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return
    here = os.path.abspath(root)
    for name in names:
        path = os.path.join(parent, name)
        if os.path.isdir(path) and os.path.abspath(path) != here:
            yield path


def find(root: str, marker: str, env_var: str) -> Optional[str]:
    """The checkout holding `marker`: this one, an override, or a sibling.

    Order matters. The override wins so a deliberate answer is never
    second-guessed; then this checkout, because a tool run inside the tree
    that has the thing should never reach outside it; then the siblings.
    """
    override = os.environ.get(env_var)
    if override:
        # An override that is wrong is a typo worth hearing about, not a
        # reason to go looking elsewhere.
        return os.path.abspath(override) if _has(override, marker) else None
    if _has(root, marker):
        return os.path.abspath(root)
    for candidate in _siblings(root):
        if _has(candidate, marker):
            return candidate
    return None


def vault(root: str) -> Optional[str]:
    """Where tofa's confidential documents live, or None."""
    return find(root, VAULT_MARKER, VAULT_ENV)


def addon_repo(root: str) -> Optional[str]:
    """The checkout containing `plugin.video.tofa/`, or None."""
    return find(root, ADDON_MARKER, ADDON_ENV)


def addon_dir(root: str) -> Optional[str]:
    """`plugin.video.tofa/` itself, wherever it is."""
    found = addon_repo(root)
    return os.path.join(found, "plugin.video.tofa") if found else None


def describe(root: str, found: Optional[str], what: str) -> str:
    """One line saying where something came from, for a tool's output.

    Printed rather than assumed, because "the gate passed" and "the gate
    passed against a checkout you forgot you had" look identical otherwise.
    """
    if not found:
        return f"{what}: NOT FOUND (set {VAULT_ENV}/{ADDON_ENV} or check out beside this one)"
    if os.path.abspath(found) == os.path.abspath(root):
        return f"{what}: this checkout"
    return f"{what}: {found}"
