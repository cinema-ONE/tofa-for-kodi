# -*- coding: utf-8 -*-
"""The channel offers older versions, so a bad release has a way back.

Kodi's add-on browser has a "Versions" button listing every version a
repository declares. We published exactly one until 0.9.9, so it offered a
single entry and there was no route back: the publish rsync deletes the
previous zip from the channel, and the GitHub release pages for 0.9.8/0.9.9
carry no uploaded copy either -- the old zips survive only inside their tags'
trees, which no viewer can reach.

Kodi holds several versions as several <addon> elements with the same id in
ONE addons.xml. Nothing dedupes them (addonID is a non-unique index) and
their order in the file does not matter, because "newest" is decided by
comparing versions.

Run:  python3 test_publish_keeps_versions.py
"""
import io
import os
import pathlib
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import release  # noqa: E402  (tools/, not the add-on -- no Kodi stubs needed)

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if not ok:
        FAILED += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


ADDON_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.tofa" name="tofa for Kodi" version="{v}" provider-name="cinemaONE">
    <extension point="xbmc.addon.metadata">
        <summary>t</summary>
    </extension>
</addon>
"""


def make_published(tmp, versions, *, mislabel=None, corrupt=None):
    """A fake docs/ tree holding one zip per version."""
    folder = os.path.join(tmp, "docs", "plugin.video.tofa")
    os.makedirs(folder, exist_ok=True)
    for v in versions:
        path = os.path.join(folder, "plugin.video.tofa-%s.zip" % v)
        if corrupt and v in corrupt:
            with open(path, "wb") as fh:
                fh.write(b"not a zip at all")
            continue
        inside = mislabel.get(v, v) if mislabel else v
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("plugin.video.tofa/addon.xml", ADDON_XML.format(v=inside))
    return folder


def run(tmp, current, keep):
    """_carry_previous against a fake docs/, returning (entries, staged names)."""
    out = os.path.join(tmp, "out")
    os.makedirs(out, exist_ok=True)
    entries = release._carry_previous(out, current, keep)
    staged = sorted(os.listdir(os.path.join(out, "plugin.video.tofa"))
                    if os.path.isdir(os.path.join(out, "plugin.video.tofa")) else [])
    return entries, staged


# ------------------------------------------------------------------ ordering
with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs")
    make_published(tmp, ["0.9.7", "0.9.8", "0.9.9", "0.9.10"])
    got = release.previously_published("0.9.10")
    # KODI's order, not a string sort: 0.9.9 is BELOW 0.9.10 lexically but
    # above it as a version, so a lexical sort would drop the wrong one first.
    check("previous versions come back newest-first in Kodi's order",
          got == ["0.9.9", "0.9.8", "0.9.7"], str(got))
    check("the version being published is not listed as a previous one",
          "0.9.10" not in got, str(got))

# ------------------------------------------------------------------ retention
with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs")
    make_published(tmp, ["0.9.5", "0.9.6", "0.9.7", "0.9.8"])

    entries, staged = run(tmp, "0.9.9", 3)
    check("keep=3 carries the two behind the current one", len(entries) == 2,
          "%d entries" % len(entries))
    check("...and they are the NEWEST two",
          all(v in " ".join(entries) for v in ("0.9.8", "0.9.7"))
          and "0.9.6" not in " ".join(entries), str(staged))
    # Subset, not equality: the per-version changelog rides along too whenever
    # changelog.txt still carries that version's entry, and asserting the exact
    # listing would break the day an old entry is trimmed.
    check("...each zip is staged with its hash sidecar",
          all(n in staged for n in ("plugin.video.tofa-0.9.7.zip",
                                    "plugin.video.tofa-0.9.7.zip.sha256",
                                    "plugin.video.tofa-0.9.8.zip",
                                    "plugin.video.tofa-0.9.8.zip.sha256")),
          str(staged))
    check("...and nothing else's zip is dragged in",
          not any(n.endswith(".zip") and "0.9.7" not in n and "0.9.8" not in n
                  for n in staged), str(staged))

    entries, _ = run(tmp, "0.9.9", 1)
    check("keep=1 is the old behaviour: nothing carried", entries == [],
          str(entries))

    entries, _ = run(tmp, "0.9.9", None)
    check("keep=all carries every published version", len(entries) == 4,
          "%d entries" % len(entries))

# ------------------------------------------- an entry describes its OWN zip
with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs")
    make_published(tmp, ["0.9.8"])
    entries, _ = run(tmp, "0.9.9", 3)
    body = entries[0]
    check("the carried entry carries the OLD version, not today's",
          'version="0.9.8"' in body and 'version="0.9.9"' not in body, body[:120])
    check("...and points <path> at that version's own zip",
          "<path>plugin.video.tofa/plugin.video.tofa-0.9.8.zip</path>" in body,
          body[-160:])
    check("...with a <size> Kodi can use", "<size>" in body, body[-160:])

# --------------------------------------------------------------- the guards
with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs")
    # A zip NAMED 0.9.8 that actually contains 0.9.6 would have the channel
    # offer one version and hand over another.
    make_published(tmp, ["0.9.8"], mislabel={"0.9.8": "0.9.6"})
    entries, staged = run(tmp, "0.9.9", 3)
    check("a zip whose contents disagree with its name is refused",
          entries == [] and staged == [], "%s / %s" % (entries, staged))

with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs")
    make_published(tmp, ["0.9.7", "0.9.8"], corrupt={"0.9.8"})
    entries, _ = run(tmp, "0.9.9", 3)
    check("an unreadable zip is skipped, and the rest still carry",
          len(entries) == 1 and 'version="0.9.7"' in entries[0],
          "%d entries" % len(entries))

with tempfile.TemporaryDirectory() as tmp:
    release.PUBLISHED_DIR = os.path.join(tmp, "docs", "nothing-here")
    entries, _ = run(tmp, "0.9.9", 3)
    check("a first-ever publish (no channel yet) carries nothing",
          entries == [], str(entries))

print("\n" + "=" * 60)
print("FAILED %d of %d" % (FAILED, CHECKS) if FAILED
      else "all %d checks passed" % CHECKS)
raise SystemExit(1 if FAILED else 0)
