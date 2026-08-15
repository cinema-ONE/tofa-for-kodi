# -*- coding: utf-8 -*-
"""Finding the other checkout, once the add-on and the vault are two trees.

`tofa-for-kodi` becomes the working repo and `tofa-kodi` is demoted to an
internals vault beside it. Tools break in both directions: the ones that
travel need tofa's confidential documents (check_public_set, release.py
check), and the ones that stay need the add-on (every live-box probe).

Two properties matter more than the resolution itself.

  1. A checkout is identified by CONTENT, never by its directory name. The
     clones happen to be `kodi-client-for-tofa` and `tofa-for-kodi` today,
     but a name belongs to whoever ran `git clone`.
  2. Not finding one answers None. Every caller is verifying something, and
     a resolver that invents a fallback turns a gate into a decoration --
     which is the exact failure this whole area keeps producing.

Run:  python3 test_checkouts.py
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import checkouts  # noqa: E402

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def make(base, name, *markers):
    """A checkout called `name` holding each marker path."""
    root = os.path.join(base, name)
    for marker in markers:
        path = os.path.join(root, marker)
        os.makedirs(os.path.dirname(path) if os.path.splitext(marker)[1]
                    else path, exist_ok=True)
        if os.path.splitext(marker)[1]:
            open(path, "w").close()
    os.makedirs(root, exist_ok=True)
    return root


def clear_env():
    for var in (checkouts.VAULT_ENV, checkouts.ADDON_ENV):
        os.environ.pop(var, None)


with tempfile.TemporaryDirectory() as tmp:
    clear_env()
    # Deliberately unhelpful names: nothing here is called "vault" or
    # "tofa-for-kodi", so only content can answer.
    vault = make(tmp, "aardvark", checkouts.VAULT_MARKER)
    addon = make(tmp, "zebra", checkouts.ADDON_MARKER)
    neither = make(tmp, "middle", "README.md")

    check("a vault is found by content, from a sibling",
          checkouts.vault(addon) == vault, str(checkouts.vault(addon)))
    check("an add-on repo is found by content, from a sibling",
          checkouts.addon_repo(vault) == addon, str(checkouts.addon_repo(vault)))
    check("...and addon_dir points INTO it",
          checkouts.addon_dir(vault) == os.path.join(addon,
                                                     "plugin.video.tofa"))

    # One tree holding both is the situation today, and must not go looking
    # outside itself.
    both = make(tmp, "onetree", checkouts.VAULT_MARKER, checkouts.ADDON_MARKER)
    check("a checkout holding both resolves to ITSELF, not a sibling",
          checkouts.vault(both) == both and checkouts.addon_repo(both) == both,
          f"{checkouts.vault(both)} / {checkouts.addon_repo(both)}")

    # --- nothing anywhere
    with tempfile.TemporaryDirectory() as empty:
        alone = make(empty, "solo", "README.md")
        check("no vault anywhere answers None", checkouts.vault(alone) is None,
              str(checkouts.vault(alone)))
        check("no add-on anywhere answers None",
              checkouts.addon_repo(alone) is None,
              str(checkouts.addon_repo(alone)))
        check("...and addon_dir answers None rather than a broken path",
              checkouts.addon_dir(alone) is None)

    # --- the override wins, and a WRONG override is not routed around
    os.environ[checkouts.VAULT_ENV] = vault
    check("an override is honoured", checkouts.vault(neither) == vault)
    os.environ[checkouts.VAULT_ENV] = os.path.join(tmp, "does-not-exist")
    check("a WRONG override answers None instead of quietly finding another",
          checkouts.vault(neither) is None, str(checkouts.vault(neither)))
    clear_env()

    # --- the search does not wander
    deep = os.path.join(tmp, "middle", "nested", "deeper")
    os.makedirs(os.path.join(deep, checkouts.VAULT_MARKER), exist_ok=True)
    found = checkouts.vault(make(tmp, "searcher", "x.txt"))
    check("only IMMEDIATE siblings are searched, never a nested tree",
          found == vault, str(found))

    # --- what a tool prints, since a silent pass is the thing to avoid
    check("describe() names the sibling it used",
          vault in checkouts.describe(addon, vault, "private sources"))
    check("describe() says so when the answer is this checkout",
          "this checkout" in checkouts.describe(both, both, "private sources"))
    check("describe() is loud about not finding one",
          "NOT FOUND" in checkouts.describe(addon, None, "private sources"))

print()
if FAILED:
    print("FAIL: %d of %d" % (FAILED, CHECKS))
    raise SystemExit(1)
print("checkouts: the other tree is found by content (%d checks)" % CHECKS)
