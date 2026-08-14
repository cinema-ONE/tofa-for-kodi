"""Version, changelog and packaging for the add-on.

Kodi decides an update exists by comparing ONE attribute -- addon.xml's
`version` -- and it does not compare it the way anyone assumes. It uses
DEBIAN versioning (xbmc/addons/AddonVersion.{h,cpp}), so:

  * numeric segments compare numerically: 1.00 == 1.0, and 1.01 == 1.1
  * depth counts: 1.0 < 1.0.0
  * `~` sorts BELOW everything, end-of-string included, which is what makes
    0.9.0~beta1 < 0.9.0 -- the only correct way to spell a pre-release
  * `-suffix` is a Debian REVISION, not a pre-release. It sorts ABOVE the
    plain version, so 0.9.0-beta1 is NEWER than 0.9.0 and anyone who
    installs it is never offered the real release. plex-for-kodi ships
    1.11.6-beta1 and has exactly this bug.

That last one is why this file implements Kodi's comparison rather than
trusting a version string to be sane: `set` REFUSES a version that does not
sort strictly above the current one, so the trap is caught here instead of
on a user's box where it is unfixable without a further bump.

Version lives in addon.xml and nowhere else -- addon.xml is what Kodi reads,
so making it generated output would add a second stale-render trap (see
project_skin_render_stale_hash) for no gain. changelog.txt owns the prose,
and `<news>` is DERIVED from its top entry, because Kodi shows `<news>` as
the changelog in the add-on browser and two hand-maintained copies of the
same text drift.

    python3 tools/release.py show               what is the version now
    python3 tools/release.py set 0.9.0          bump it (validates + syncs news)
    python3 tools/release.py sync               re-derive <news> from changelog
    python3 tools/release.py check              validate without changing anything
    python3 tools/release.py server 0.9.30      raise the server floor (code + README)
    python3 tools/release.py package            build dist/<id>-<version>.zip
    python3 tools/release.py publish            build dist/repo/, the update site

PUBLISH builds the Kodi REPOSITORY -- a different thing that shares the word.
Kodi installs and auto-updates add-ons from a static tree: an index of every
add-on's addon.xml, a checksum beside it, and the zips. A user adds the URL
once and every later release arrives on its own; without it, a zip is
installed by hand and never updates.

The tree's shape is not invented here. It follows what Kodi's own repository
(repository.xbmc.org, read out of the installed Kodi 21) actually serves, and
two details of that are worth stating because the folklore is out of date:

  * Each entry in addons.xml carries `<path>` (relative to `<datadir>`) and
    `<size>` inside its metadata extension. Kodi does NOT have to infer the
    zip's location from a naming convention -- every one of the official
    repo's 2287 entries states it.
  * `<hashes>` names an ALGORITHM. `true` still parses but resolves to md5,
    which current Kodi warns about in the log as broken. sha256 is what the
    official repo uses and what this writes.

Everything except the URLs is host-independent, so the tree can be built and
checked long before anyone decides where it goes. The URLs go into ONE file,
the repository add-on's own addon.xml, and they are baked into the zip a user
installs -- so changing the base URL later means every existing user has to
remove and re-add the repository. Decide it before handing out the link, and
bump REPO_VERSION whenever it does change so existing installs pick the new
one up while the old URL still resolves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(ROOT, "plugin.video.tofa")
ADDON_XML = os.path.join(ADDON_DIR, "addon.xml")
CHANGELOG = os.path.join(ADDON_DIR, "changelog.txt")
DIST = os.path.join(ROOT, "dist")

# Kodi's own whitelist, from CAddonVersion: a version ends up in FILE NAMES,
# so the accepted alphabet is deliberately narrow. `:` opens an epoch and `-`
# opens a revision, so both are structural rather than part of a component.
VALID_CHARS = set("abcdefghijklmnopqrstuvwxyz"
                  "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  "0123456789.+_@~")

# Files that must never reach a user's box. __pycache__ would ship one
# machine's bytecode; the skin's own render cache would ship a hash that
# disagrees with the XML next to it.
EXCLUDE_DIRS = {"__pycache__", ".git", ".tofa-probe"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".orig", ".rej")

# --- the repository add-on -------------------------------------------------
# The one-time install. It carries no code, only the three URLs below, so its
# whole job is to tell Kodi where to look.
REPO_ID = "repository.tofa"
REPO_NAME = "tofa Add-on Repository"
# Bump when the URLs change, and ONLY then. Existing installs update
# themselves from the old URL, so a URL change reaches them exactly once --
# if the version does not move, it never reaches them at all.
REPO_VERSION = "1.0.0"
REPO_SUMMARY = "Install and update the tofa add-on"
REPO_DESCRIPTION = (
    "The update channel for tofa's Kodi add-on. Installing this repository "
    "lets Kodi fetch the add-on and every later release on its own."
)
#: Where the tree below will be served from, no trailing slash.
#:
#: Settled 2026-08-12 (issue #5): the update channel is OUR GitHub Pages, not
#: a tofa.tv URL -- tofa would rather not put their domain in front of a
#: channel they do not operate. Pages lowercases the org, so `cinema-ONE`
#: serves at `cinema-one.github.io`; the repo is `tofa-for-kodi`, and the
#: tree below goes in its `docs/` folder, which Pages serves at this root.
#:
#: Changing this later means every existing user has to remove and re-add the
#: repository, so bump REPO_VERSION with it (see the module docstring).
BASE_URL = "https://cinema-one.github.io/tofa-for-kodi"
#: What Kodi hashes. `true` means md5, which current Kodi logs as broken.
HASH_ALGO = "sha256"
REPO_OUT = os.path.join(DIST, "repo")


# ----------------------------------------------------------------- version --

def _split(version: str) -> tuple[int, str, str]:
    """(epoch, upstream, revision), Kodi's own parse."""
    epoch, _, rest = version.partition(":")
    if not _:
        epoch, rest = "0", version
    try:
        epoch_n = int(epoch)
    except ValueError:
        raise ValueError("epoch %r is not a number" % epoch) from None
    upstream, _, revision = rest.partition("-")
    return epoch_n, upstream, revision


def _compare_component(a: str, b: str) -> int:
    """Debian component comparison, as CAddonVersion::CompareComponent does.

    Runs of digits compare as numbers; everything else compares by character,
    except that `~` sorts below even the end of the string."""
    ia = ib = 0
    while ia < len(a) or ib < len(b):
        first_diff = 0
        # Non-digit run: compare character by character, with ~ special.
        while ((ia < len(a) and not a[ia].isdigit())
               or (ib < len(b) and not b[ib].isdigit())):
            ca = a[ia] if ia < len(a) else None
            cb = b[ib] if ib < len(b) else None
            oa = -1 if ca == "~" else (0 if ca is None else ord(ca))
            ob = -1 if cb == "~" else (0 if cb is None else ord(cb))
            if oa != ob:
                return -1 if oa < ob else 1
            ia += 1
            ib += 1
        # Digit run: leading zeros are not significant, so compare as ints.
        while ia < len(a) and a[ia] == "0":
            ia += 1
        while ib < len(b) and b[ib] == "0":
            ib += 1
        while ia < len(a) and a[ia].isdigit() and ib < len(b) and b[ib].isdigit():
            if not first_diff:
                first_diff = (ord(a[ia]) > ord(b[ib])) - (ord(a[ia]) < ord(b[ib]))
            ia += 1
            ib += 1
        if ia < len(a) and a[ia].isdigit():
            return 1
        if ib < len(b) and b[ib].isdigit():
            return -1
        if first_diff:
            return first_diff
    return 0


def compare(a: str, b: str) -> int:
    """-1 / 0 / 1, matching how Kodi orders two add-on versions."""
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    upstream = _compare_component(ua, ub)
    if upstream:
        return upstream
    return _compare_component(ra, rb)


def validate(version: str) -> list[str]:
    """Everything wrong with a version string, as messages."""
    problems = []
    if not version:
        return ["version is empty"]
    try:
        _, upstream, revision = _split(version)
    except ValueError as exc:
        return [str(exc)]
    if not upstream:
        problems.append("no version before the revision separator")
    for part, name in ((upstream, "version"), (revision, "revision")):
        bad = sorted({c for c in part if c not in VALID_CHARS})
        if bad:
            problems.append("%s contains characters Kodi rejects: %s"
                            % (name, " ".join(repr(c) for c in bad)))
    if revision:
        problems.append(
            "'-%s' is a Debian REVISION, which sorts ABOVE plain %s -- so this "
            "would be offered as newer than the final release. For a "
            "pre-release use '~' instead: %s~%s"
            % (revision, upstream, upstream, revision))
    if not upstream[0].isdigit():
        problems.append("version should start with a digit")
    return problems


# ---------------------------------------------------------------- addon.xml --

def read_addon_xml() -> str:
    with open(ADDON_XML, "r", encoding="utf-8") as handle:
        return handle.read()


def current_version(xml: str | None = None) -> str:
    xml = read_addon_xml() if xml is None else xml
    match = re.search(r'(<addon\b[^>]*?\bversion=")([^"]*)(")', xml, re.S)
    if not match:
        raise SystemExit("addon.xml: no version attribute on <addon>")
    return match.group(2)


def _set_version(xml: str, version: str) -> str:
    return re.sub(r'(<addon\b[^>]*?\bversion=")([^"]*)(")',
                  lambda m: m.group(1) + version + m.group(3), xml, count=1, flags=re.S)


def _set_news(xml: str, news: str) -> str:
    """Replace <news> if present, otherwise add it before <assets>.

    The body is indented to sit under the tag rather than jammed against it,
    which is how every other block in this file is written."""
    body = "\n" + "\n".join("      " + line if line else ""
                            for line in news.splitlines()) + "\n    "
    if re.search(r"<news>.*?</news>", xml, re.S):
        return re.sub(r"<news>.*?</news>", lambda m: "<news>" + body + "</news>",
                      xml, count=1, flags=re.S)
    return xml.replace("    <assets>",
                       "    <news>" + body + "</news>\n    <assets>", 1)


# --------------------------------------------------------------- changelog --

ENTRY_RE = re.compile(r"^v?([0-9][^\s]*)\s*$", re.M)


def changelog_entries() -> list[tuple[str, str]]:
    """[(version, body)] newest first, from changelog.txt.

    The format is deliberately plain -- a bare version on its own line, then
    its notes -- so the file reads as a changelog rather than as tool input."""
    if not os.path.exists(CHANGELOG):
        return []
    with open(CHANGELOG, "r", encoding="utf-8") as handle:
        text = handle.read()
    marks = list(ENTRY_RE.finditer(text))
    entries = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        entries.append((mark.group(1), text[mark.end():end].strip("\n")))
    return entries


def news_for(version: str) -> str | None:
    for entry_version, body in changelog_entries():
        if entry_version == version:
            return body.strip()
    return None


def news_in_xml(xml: str) -> str | None:
    """<news>'s body with the XML indentation taken back off.

    _set_news indents the block to sit under its tag, so the raw text never
    equals the changelog it came from -- comparing them directly reported a
    freshly synced file as stale."""
    match = re.search(r"<news>(.*?)</news>", xml, re.S)
    if not match:
        return None
    return textwrap.dedent(match.group(1).strip("\n")).strip()


# ------------------------------------------------------------------ actions --

# --- server compatibility -----------------------------------------------
#
# THREE places name the server version we target, and they drift silently
# because nothing fails when they disagree: the constant the client actually
# enforces, the line a user reads in README.txt, and the OpenAPI spec we
# vendored to code against. The constant is the source of truth; the others
# are checked against it here, so a package cannot ship a README promising
# one thing and a client enforcing another.
#
# Read by REGEX rather than import: serverversion imports xbmcgui, which
# does not exist off-device.
SERVERVERSION_PY = os.path.join(
    ADDON_DIR, "resources", "lib", "serverversion.py")
README = os.path.join(ADDON_DIR, "README.txt")
SPEC_DIR = os.path.join(ROOT, "internal-docs", "api")

_FLOOR_RE = re.compile(
    r"^MIN_SERVER_VERSION.*?=\s*\((\d+),\s*(\d+),\s*(\d+)\)", re.M)
_README_RE = re.compile(
    r"^Built against tofa media server (\d+\.\d+\.\d+)\.", re.M)


def server_floor() -> str | None:
    """The version the client enforces, as a dotted string."""
    try:
        with open(SERVERVERSION_PY, encoding="utf8") as handle:
            found = _FLOOR_RE.search(handle.read())
    except OSError:
        return None
    return ".".join(found.groups()) if found else None


def readme_server_version() -> str | None:
    try:
        with open(README, encoding="utf8") as handle:
            found = _README_RE.search(handle.read())
    except OSError:
        return None
    return found.group(1) if found else None


def spec_version() -> str | None:
    """The vendored OpenAPI spec's own version, if it is here at all.

    It legitimately LAGS the server -- 0.9.29 shipped avatars and home rows
    with no spec update -- so a spec older than the floor is normal and not
    reported. A spec NEWER than the floor is the interesting case: it means
    we vendored a contract we have not declared support for.

    internal-docs/ is not in the public repository, so a missing spec is
    fine and silent."""
    if not os.path.isdir(SPEC_DIR):
        return None
    for name in sorted(os.listdir(SPEC_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(SPEC_DIR, name), encoding="utf8") as handle:
                return (json.load(handle).get("info") or {}).get("version")
        except (OSError, ValueError):
            return None
    return None


def server_problems() -> list[str]:
    problems = []
    floor = server_floor()
    if not floor:
        return ["serverversion.py: cannot read MIN_SERVER_VERSION"]
    readme = readme_server_version()
    if readme is None:
        problems.append(
            "README.txt has no 'Built against tofa media server X.Y.Z.' line")
    elif readme != floor:
        problems.append(
            "README.txt says server %s, serverversion.py enforces %s "
            "(run: release.py server %s)" % (readme, floor, floor))
    spec = spec_version()
    if spec and compare(spec, floor) > 0:
        problems.append(
            "the vendored API spec is %s but the client only claims %s -- "
            "adopt it and raise MIN_SERVER_VERSION, or vendor the older spec"
            % (spec, floor))
    return problems


def do_server(version: str) -> int:
    """Set the server floor in BOTH places at once."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        print("server version must be X.Y.Z, got %r" % version)
        return 1
    parts = version.split(".")
    with open(SERVERVERSION_PY, encoding="utf8") as handle:
        code = handle.read()
    updated = _FLOOR_RE.sub(
        "MIN_SERVER_VERSION: Tuple[int, int, int] = (%s, %s, %s)" % tuple(parts),
        code, count=1)
    if updated == code:
        print("serverversion.py: MIN_SERVER_VERSION not found or unchanged")
        return 1
    with open(SERVERVERSION_PY, "w", encoding="utf8") as handle:
        handle.write(updated)
    with open(README, encoding="utf8") as handle:
        readme = handle.read()
    with open(README, "w", encoding="utf8") as handle:
        handle.write(_README_RE.sub(
            "Built against tofa media server %s." % version, readme, count=1))
    print("server floor set to %s in serverversion.py and README.txt" % version)
    print("Remember the changelog: a floor bump is a user-visible change.")
    return 0


def do_check() -> int:
    xml = read_addon_xml()
    version = current_version(xml)
    problems = validate(version)

    entries = changelog_entries()
    if not entries:
        problems.append("changelog.txt has no entries")
    else:
        if entries[0][0] != version:
            problems.append("changelog.txt's newest entry is %s, addon.xml says %s"
                            % (entries[0][0], version))
        # A changelog that is not in descending order means the "newest entry"
        # rule above is silently reading the wrong one.
        for newer, older in zip(entries, entries[1:]):
            if compare(newer[0], older[0]) <= 0:
                problems.append("changelog.txt: %s is not newer than %s"
                                % (newer[0], older[0]))

    news = news_for(version)
    if news is None:
        problems.append("changelog.txt has no entry for %s" % version)
    else:
        in_xml = news_in_xml(xml)
        if in_xml is None:
            problems.append("addon.xml has no <news> (run: release.py sync)")
        elif in_xml != news:
            problems.append("addon.xml's <news> is stale (run: release.py sync)")

    problems.extend(server_problems())

    print("version %s" % version)
    floor = server_floor()
    if floor:
        spec = spec_version()
        print("server floor %s%s"
              % (floor, "  (vendored spec %s)" % spec if spec else ""))
    for problem in problems:
        print("    " + problem)
    print("%d problem(s)" % len(problems))
    return 1 if problems else 0


def do_sync() -> int:
    xml = read_addon_xml()
    version = current_version(xml)
    news = news_for(version)
    if news is None:
        print("changelog.txt has no entry for %s -- add one first" % version)
        return 1
    updated = _set_news(xml, news)
    if updated == xml:
        print("<news> already current for %s" % version)
        return 0
    with open(ADDON_XML, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print("synced <news> from changelog.txt entry %s" % version)
    return 0


def do_set(version: str) -> int:
    xml = read_addon_xml()
    old = current_version(xml)

    problems = validate(version)
    if compare(version, old) <= 0:
        problems.append(
            "%s does not sort above the current %s, so Kodi would never offer "
            "it as an update" % (version, old))
    if problems:
        print("refusing to set version %s:" % version)
        for problem in problems:
            print("    " + problem)
        return 1

    if news_for(version) is None:
        print("add a changelog.txt entry for %s first -- <news> is derived "
              "from it" % version)
        return 1

    with open(ADDON_XML, "w", encoding="utf-8") as handle:
        handle.write(_set_version(xml, version))
    print("version %s -> %s" % (old, version))
    return do_sync()


def _should_skip(rel: str) -> bool:
    parts = rel.split(os.sep)
    return (any(p in EXCLUDE_DIRS for p in parts)
            or rel.endswith(EXCLUDE_SUFFIXES))


def do_package() -> int:
    if do_check():
        print("not packaging a version that does not check out")
        return 1
    version = current_version()
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, "plugin.video.tofa-%s.zip" % version)

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for base, dirs, files in os.walk(ADDON_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in sorted(files):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, ADDON_DIR)
                if _should_skip(rel):
                    continue
                # Kodi requires everything to sit under a directory named for
                # the add-on id, NOT at the zip root.
                archive.write(path, os.path.join("plugin.video.tofa", rel))
                count += 1
    size = os.path.getsize(target)
    print("%s  (%d files, %.1f MB)"
          % (os.path.relpath(target, ROOT), count, size / 1024.0 / 1024.0))
    return 0


# ---------------------------------------------------------------- publish --


def _digest(path: str) -> str:
    """The hex digest Kodi will compare against, for a file on disk."""
    h = hashlib.new(HASH_ALGO)
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write_with_digest(path: str, data: bytes) -> None:
    """Write a file and the sidecar hash Kodi fetches for it.

    Kodi asks the web server for the hash in an HTTP header first and only
    falls back to `<url>.<algo>`, so the sidecar is what makes this work on a
    plain static host that sets no such header."""
    with open(path, "wb") as handle:
        handle.write(data)
    with open(path + "." + HASH_ALGO, "w", encoding="utf-8") as handle:
        handle.write(_digest(path))


def _repository_addon_xml(base_url: str) -> bytes:
    """The repository add-on's own addon.xml, with the URLs filled in.

    Generated rather than kept as a file with a placeholder in it: a
    half-configured addon.xml sitting in the tree is one somebody eventually
    ships."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<addon id="{id}" name="{name}" version="{version}" '
        'provider-name="cinemaONE">\n'
        '  <requires>\n'
        '    <import addon="xbmc.addon" version="12.0.0"/>\n'
        '  </requires>\n'
        '  <extension point="xbmc.addon.repository" name="tofa">\n'
        '    <dir>\n'
        '      <info>{base}/addons.xml</info>\n'
        '      <checksum verify="{algo}">{base}/addons.xml.{algo}</checksum>\n'
        '      <datadir>{base}</datadir>\n'
        '      <artdir>{base}</artdir>\n'
        '      <hashes>{algo}</hashes>\n'
        '    </dir>\n'
        '  </extension>\n'
        '  <extension point="xbmc.addon.metadata">\n'
        '    <platform>all</platform>\n'
        '    <license>GPL-2.0-only</license>\n'
        '    <summary lang="en_GB">{summary}</summary>\n'
        '    <description lang="en_GB">{description}</description>\n'
        '    <assets>\n'
        '      <icon>icon.png</icon>\n'
        '    </assets>\n'
        '  </extension>\n'
        '</addon>\n'
    ).format(id=REPO_ID, name=REPO_NAME, version=REPO_VERSION, base=base_url,
             algo=HASH_ALGO, summary=REPO_SUMMARY,
             description=REPO_DESCRIPTION).encode("utf-8")


def _index_entry(addon_xml: str, rel_zip: str, size: int) -> str:
    """One add-on's addon.xml, as it appears inside addons.xml.

    Kodi's index is every addon.xml concatenated, with two facts added that
    only the publisher knows: WHERE the zip is, relative to <datadir>, and how
    big it is. Both go inside the metadata extension, which is where Kodi's
    own repository puts them -- all 2287 entries of it."""
    body = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", addon_xml)
    extra = "<size>%d</size><path>%s</path>" % (size, rel_zip)
    updated, count = re.subn(
        r"(<extension\s+point=\"xbmc\.addon\.metadata\".*?)(</extension>)",
        lambda m: m.group(1) + extra + m.group(2), body, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(
            "%s has no <extension point=\"xbmc.addon.metadata\"> to carry "
            "<path>/<size>; Kodi would list the add-on and then be unable to "
            "download it." % rel_zip)
    return updated.strip()


def _stage(out_dir: str, addon_id: str, zip_path: str,
           art: list[tuple[str, str]], changelog: str | None) -> tuple[str, int]:
    """Put one add-on's zip, hash, artwork and changelog in place.

    Returns (path relative to datadir, size) for the index. Artwork and the
    changelog sit beside the zip so Kodi's add-on browser can show the entry
    without downloading it."""
    folder = os.path.join(out_dir, addon_id)
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(zip_path)
    with open(zip_path, "rb") as handle:
        _write_with_digest(os.path.join(folder, name), handle.read())
    for source, target in art:
        if os.path.exists(source):
            with open(source, "rb") as src, \
                    open(os.path.join(folder, target), "wb") as dst:
                dst.write(src.read())
    if changelog:
        with open(os.path.join(folder, "changelog-%s.txt" % current_version()),
                  "w", encoding="utf-8") as handle:
            handle.write(changelog)
    return "%s/%s" % (addon_id, name), os.path.getsize(zip_path)


def do_publish(base_url: str | None, out_dir: str) -> int:
    base_url = (base_url or BASE_URL or "").rstrip("/")
    if not base_url:
        print("publish needs the URL this tree will be served from, e.g.\n"
              "    python3 tools/release.py publish --base-url "
              "https://cinema-one.github.io/tofa-for-kodi\n"
              "It is baked into the repository add-on users install, so there "
              "is no safe default to guess. BASE_URL is normally set.")
        return 1
    if do_check():
        print("not publishing a version that does not check out")
        return 1

    version = current_version()
    addon_zip = os.path.join(DIST, "plugin.video.tofa-%s.zip" % version)
    if not os.path.exists(addon_zip) and do_package():
        return 1

    os.makedirs(out_dir, exist_ok=True)
    entries = []

    # The add-on itself. Which artwork exists is addon.xml's <assets> to say,
    # not this file's to assume -- the fanart moved from .jpg to .png once
    # already, and a hardcoded name would have published the old one.
    art = [(os.path.join(ADDON_DIR, name), os.path.basename(name))
           for name in re.findall(r"<(?:icon|fanart)>([^<]+)</(?:icon|fanart)>",
                                  read_addon_xml())]
    if not art:
        print("addon.xml declares no <assets>; the repository entry will have "
              "no icon in Kodi's browser")
    news = news_for(version) or ""
    rel, size = _stage(out_dir, "plugin.video.tofa", addon_zip, art, news)
    entries.append(_index_entry(read_addon_xml(), rel, size))

    # The repository add-on, built from scratch each time so its URLs cannot
    # drift from what this run was told.
    repo_xml = _repository_addon_xml(base_url)
    repo_zip = os.path.join(DIST, "%s-%s.zip" % (REPO_ID, REPO_VERSION))
    with zipfile.ZipFile(repo_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("%s/addon.xml" % REPO_ID, repo_xml)
        icon = os.path.join(ADDON_DIR, "icon.png")
        if os.path.exists(icon):
            archive.write(icon, "%s/icon.png" % REPO_ID)
    rel, size = _stage(out_dir, REPO_ID, repo_zip,
                       [(os.path.join(ADDON_DIR, "icon.png"), "icon.png")],
                       None)
    entries.append(_index_entry(repo_xml.decode("utf-8"), rel, size))

    index = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
             '<addons>\n%s\n</addons>\n' % "\n".join(entries))
    _write_with_digest(os.path.join(out_dir, "addons.xml"),
                       index.encode("utf-8"))

    problems = verify_repo(out_dir)
    for line in problems:
        print("PROBLEM: %s" % line)
    print("\n%s" % os.path.relpath(out_dir, ROOT))
    for base, _dirs, files in sorted(os.walk(out_dir)):
        for name in sorted(files):
            path = os.path.join(base, name)
            print("  %-58s %8.1f KB" % (os.path.relpath(path, out_dir),
                                        os.path.getsize(path) / 1024.0))
    print("\nserve that directory at %s" % base_url)
    print("users install %s/%s/%s-%s.zip once; "
          "%s follows on its own."
          % (base_url, REPO_ID, REPO_ID, REPO_VERSION, "plugin.video.tofa"))
    return 1 if problems else 0


def verify_repo(out_dir: str) -> list[str]:
    """Read the tree back the way Kodi will, and say what would break.

    Publishing is the one step with no feedback loop -- a wrong path or a
    stale hash looks fine locally and fails on a stranger's box, days later,
    as "could not connect to repository"."""
    problems = []
    index = os.path.join(out_dir, "addons.xml")
    if not os.path.exists(index):
        return ["addons.xml is missing"]
    with open(index, "rb") as handle:
        raw = handle.read()

    sidecar = index + "." + HASH_ALGO
    if not os.path.exists(sidecar):
        problems.append("addons.xml.%s is missing" % HASH_ALGO)
    else:
        with open(sidecar, encoding="utf-8") as handle:
            if handle.read().strip() != hashlib.new(HASH_ALGO, raw).hexdigest():
                problems.append("addons.xml.%s does not match addons.xml"
                                % HASH_ALGO)

    entries = re.findall(r'<addon id="([^"]+)"', raw.decode("utf-8"))
    paths = re.findall(r"<path>([^<]+)</path>", raw.decode("utf-8"))
    sizes = [int(n) for n in re.findall(r"<size>(\d+)</size>",
                                        raw.decode("utf-8"))]
    if not (len(entries) == len(paths) == len(sizes)):
        return problems + ["addons.xml: %d entries but %d paths and %d sizes"
                           % (len(entries), len(paths), len(sizes))]

    for addon_id, rel, size in zip(entries, paths, sizes):
        target = os.path.join(out_dir, rel)
        if not os.path.exists(target):
            problems.append("%s: <path>%s</path> is not in the tree"
                            % (addon_id, rel))
            continue
        if os.path.getsize(target) != size:
            problems.append("%s: <size> says %d, the zip is %d"
                            % (addon_id, size, os.path.getsize(target)))
        sidecar = target + "." + HASH_ALGO
        if not os.path.exists(sidecar):
            problems.append("%s: no %s beside the zip" % (addon_id, HASH_ALGO))
        elif open(sidecar, encoding="utf-8").read().strip() != _digest(target):
            problems.append("%s: %s sidecar does not match the zip"
                            % (addon_id, HASH_ALGO))
        with zipfile.ZipFile(target) as archive:
            roots = {name.split("/")[0] for name in archive.namelist()}
            if roots != {addon_id}:
                problems.append(
                    "%s: the zip's top level is %s, but Kodi extracts by the "
                    "add-on id and would install it to the wrong folder"
                    % (addon_id, sorted(roots)))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("show", help="print the current version")
    sub.add_parser("check", help="validate version, changelog and <news>")
    sub.add_parser("sync", help="re-derive <news> from changelog.txt")
    sub.add_parser("package", help="build dist/<id>-<version>.zip")
    pub = sub.add_parser("publish", help="build dist/repo/, the update site")
    pub.add_argument("--base-url", default=None,
                     help="URL the tree will be served from, no trailing slash")
    pub.add_argument("--out", default=REPO_OUT, help="output directory")
    setter = sub.add_parser("set", help="set the version")
    setter.add_argument("version")
    server = sub.add_parser(
        "server", help="set the minimum server version (code + README)")
    server.add_argument("version")
    args = parser.parse_args()

    if args.command == "show":
        print(current_version())
        return 0
    if args.command == "set":
        return do_set(args.version)
    if args.command == "server":
        return do_server(args.version)
    if args.command == "sync":
        return do_sync()
    if args.command == "package":
        return do_package()
    if args.command == "publish":
        return do_publish(args.base_url, args.out)
    return do_check()


if __name__ == "__main__":
    sys.exit(main())
