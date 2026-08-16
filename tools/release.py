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
import ipaddress
import json
import os
import re
import shutil
import sys
import textwrap
import urllib.parse
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)
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
# Matched on the BASENAME, because these have no suffix to match on. The zip
# is built by walking the working tree, so UNTRACKED files ship as readily as
# tracked ones -- and `.DS_Store` is gitignored, so git will never warn about
# one. Opening a media folder in Finder once is enough to put a Mac's desktop
# database into a stranger's download.
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# --- the repository add-on -------------------------------------------------
# The one-time install. It carries no code, only the three URLs below, so its
# whole job is to tell Kodi where to look.
REPO_ID = "repository.tofa"
REPO_NAME = "tofa Add-on Repository"
# Bump when ANYTHING in the repository add-on changes -- Kodi re-downloads it
# only when this version moves, so an unbumped change reaches nobody who has
# already installed. That is the URLs below, and equally the name, summary,
# description, icon and any <dir> gating. It is NOT the add-on's own version:
# shipping code, fonts or artwork bumps plugin.video.tofa/addon.xml and leaves
# this alone, which is the ordinary case every release.
#
# For scale: Team Kodi's own repository.xbmc.org is at 3.5.0, plex-for-kodi's
# repository.dontpanic at 0.2.10 (pm4k.eu). Nobody freezes it.
#
# 1.0.0 -> 1.0.1 on 2026-08-15: 1.0.0 shipped `<checksum verify="sha256">`,
# which Kodi 21.3 refuses, so that build could never reach its own index. An
# install stuck on it cannot learn about this one either -- it has to be
# reinstalled by hand -- but the bump is what lets every install that CAN
# read the index replace 1.0.0 without being asked.
REPO_VERSION = "1.0.1"
REPO_SUMMARY = "Install and update the tofa add-on"
REPO_DESCRIPTION = (
    "The update channel for tofa's Kodi add-on. Installing this repository "
    "lets Kodi fetch the add-on and every later release on its own."
)
#: Where the tree below will be served from, no trailing slash.
#:
#: Settled 2026-08-12 (issue #5): the update channel is OURS, not a tofa.tv
#: URL -- tofa would rather not put their domain in front of a channel they
#: do not operate. The bits come from GitHub Pages out of this repo's `docs/`
#: folder; the hostname is only a DNS CNAME pointing at `cinema-one.github.io`.
#:
#: A domain we own rather than `cinema-one.github.io/tofa-for-kodi`, decided
#: 2026-08-15 before the first publish, and the reason is portability rather
#: than looks: this string is baked into every repository zip a box installs,
#: so a `github.io` URL would tie the channel to GitHub Pages permanently.
#: Behind a domain we control, the host can move by repointing DNS and no
#: install notices. It is the one part of this that cannot be retrofitted
#: cheaply. plex-for-kodi does the same thing with pm4k.eu.
#:
#: The cost is a renewal obligation: if the domain ever lapses, every install's
#: update channel dies and whoever registers it next can serve code to those
#: boxes. Keep it, and keep it verified on the GitHub account so a dangling
#: CNAME cannot be claimed by another user.
#:
#: Changing this later means every existing user has to remove and re-add the
#: repository, so bump REPO_VERSION with it (see the module docstring).
BASE_URL = "https://tofa.cinemaone.ch"
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


def _xml_escape(text: str) -> str:
    """The three characters that cannot appear as themselves in element text.

    Ampersand FIRST, or the escapes escape each other."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def _xml_unescape(text: str) -> str:
    """The inverse. Ampersand LAST, for the same reason."""
    return (text.replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&"))


def _set_news(xml: str, news: str) -> str:
    """Replace <news> if present, otherwise add it before <assets>.

    The body is indented to sit under the tag rather than jammed against it,
    which is how every other block in this file is written.

    ESCAPED, because the changelog is prose and `<news>` is XML. A release note
    naming a settings page -- "Privacy & About", "Audio & Subtitles" -- carries
    a bare `&`, which makes addon.xml not well-formed. That is not a quiet
    failure (check_xml and every suite that parses addon.xml stop dead) but it
    IS a confusing one, because the bad character came from a text file nobody
    thinks of as markup. news_in_xml unescapes on the way back so the
    staleness comparison still sees the changelog's own text."""
    body = "\n" + "\n".join("      " + _xml_escape(line) if line else ""
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
    return _xml_unescape(textwrap.dedent(match.group(1).strip("\n")).strip())


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
#: The vault holds the vendored spec, and travels nowhere. In one tree that
#: is this checkout; after the split it is the sibling. None when there is no
#: vault to read -- which the public repo's CI legitimately is, so this is
#: reported rather than fatal. See spec_version().
_VAULT = checkouts.vault(ROOT)
SPEC_DIR = os.path.join(_VAULT, "internal-docs", "api") if _VAULT else None

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

    internal-docs/ is not in the public repository and never will be, so a
    missing spec is not an error. It is no longer SILENT, though: do_check
    says which of the two it did, because "floor checked against the spec"
    and "floor checked against nothing" printed the same line before, and the
    second is what a CI run without a vault actually does."""
    if not SPEC_DIR or not os.path.isdir(SPEC_DIR):
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


def repo_zip_problems() -> list[str]:
    """The install instructions must name the repository zip that exists.

    Both READMEs spell the filename out, because a reader is going to look for
    it in a list on a television. That makes it a version stated in prose, and
    prose does not follow a constant on its own: REPO_VERSION went to 1.0.1
    and both files still said 1.0.0, which would have sent every new installer
    hunting for a file that is not there. Same shape as the server floor,
    which drifted the same way earlier the same day.
    """
    wanted = "%s-%s.zip" % (REPO_ID, REPO_VERSION)
    stale = re.compile(re.escape(REPO_ID) + r"-\d+\.\d+\.\d+\.zip")
    problems = []
    for rel in ("README.md", os.path.join("plugin.video.tofa", "README.txt")):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf8") as handle:
            text = handle.read()
        named = set(stale.findall(text))
        if not named:
            continue
        wrong = sorted(n for n in named if n != wanted)
        if wrong:
            problems.append("%s names %s; REPO_VERSION is %s (%s)"
                            % (rel, ", ".join(wrong), REPO_VERSION, wanted))
    return problems


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
    problems.extend(repo_zip_problems())

    print("version %s" % version)
    floor = server_floor()
    if floor:
        spec = spec_version()
        if spec:
            note = "  (vendored spec %s)" % spec
        elif _VAULT:
            note = "  (no spec in the vault, floor NOT compared)"
        else:
            note = "  (no vault here, floor NOT compared against any spec)"
        print("server floor %s%s" % (floor, note))
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
            or os.path.basename(rel) in EXCLUDE_NAMES
            or rel.endswith(EXCLUDE_SUFFIXES))


def package_files() -> list[tuple[str, str]]:
    """(path on disk, path inside the zip) for everything that ships.

    Split out of do_package so a test can assert what WOULD ship without
    building a nine-megabyte zip to look inside it.
    """
    out = []
    for base, dirs, files in os.walk(ADDON_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in sorted(files):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ADDON_DIR)
            if _should_skip(rel):
                continue
            # Kodi requires everything to sit under a directory named for
            # the add-on id, NOT at the zip root.
            out.append((path, os.path.join("plugin.video.tofa", rel)))
    return out


def do_package() -> int:
    if do_check():
        print("not packaging a version that does not check out")
        return 1
    version = current_version()
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, "plugin.video.tofa-%s.zip" % version)

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in package_files():
            archive.write(path, arcname)
            count += 1
    size = os.path.getsize(target)
    print("%s  (%d files, %.1f MB)"
          % (os.path.relpath(target, ROOT), count, size / 1024.0 / 1024.0))
    return 0


# ---------------------------------------------------------------- publish --


def declared_assets(xml: str) -> list[tuple[str, str]]:
    """(source on disk, path relative to the add-on) for every <assets> entry.

    Which artwork exists is addon.xml's to say, not this file's to assume --
    the fanart moved from .jpg to .png once already, and a hardcoded name
    would have published the old one. So every child of <assets> travels,
    whatever Kodi adds next.

    The RELATIVE PATH is kept, not the basename. Kodi resolves a repository's
    artwork as `<datadir>/<addon-id>/<the path written in addon.xml>`, so a
    screenshot declared at `resources/screenshots/01-home.jpg` has to be
    staged at exactly that path; flattening it publishes a file Kodi will
    never ask for and an entry whose screenshots silently do not load. It
    went unnoticed while the only assets were `icon.png` and `fanart.png`,
    which sit at the root, where the basename IS the relative path.
    """
    block = re.search(r"<assets>(.*?)</assets>", xml, re.S)
    if not block:
        return []
    found = re.findall(r"<(\w+)>\s*([^<]+?)\s*</\1>", block.group(1))
    return [(os.path.join(ADDON_DIR, rel), rel) for _tag, rel in found]


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
    ships.

    NO `verify` ATTRIBUTE ON <checksum>, and this is not a style choice.
    Kodi 21.3 rejects `<checksum verify="sha256">` outright: the repository
    fails with "Could not connect to repository", and the log shows

        CRepository: failed read 'https://.../addons.xml.sha256'

    in the same millisecond the update job starts, with NO CurlFile::Open
    line -- it never makes the request. Removing the attribute and changing
    nothing else, the very next run fetches addons.xml.sha256 and then
    addons.xml, and the repository resolves.

    Kodi's OWN repository.xbmc.org ships `verify="sha256"` and works, which
    is what made this hard to believe and worth writing down. Whatever the
    difference is, it is not something a third-party repository can rely on.
    Diagnosed on a real install, 2026-08-15, by patching the installed
    manifest and ageing the `repo` row in Addons33.db to force a recheck.

    <hashes>sha256</hashes> STAYS -- that is about the digests beside the
    add-on zips, which we ship, and it is not what broke."""
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
        '      <checksum>{base}/addons.xml.{algo}</checksum>\n'
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
            destination = os.path.join(folder, target)
            # `target` can be nested now (screenshots live under
            # resources/), and Kodi asks for it at exactly that path.
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(source, "rb") as src, open(destination, "wb") as dst:
                dst.write(src.read())
    if changelog:
        with open(os.path.join(folder, "changelog-%s.txt" % current_version()),
                  "w", encoding="utf-8") as handle:
            handle.write(changelog)
    return "%s/%s" % (addon_id, name), os.path.getsize(zip_path)


#: The page a BROWSER gets at the channel root. Kodi never asks for it.
#:
#: Without one, Pages answers its own 404 to anyone who types the address --
#: which is what a viewer does with a URL they were told to "add as a source",
#: and what anyone does who finds the address in a log or a settings screen.
#: A 404 says "this is broken"; it is not, it is simply not a website.
#:
#: GENERATED, like CNAME and .nojekyll, for the same reason: `publish` rebuilds
#: this tree wholesale, so a hand-written file here would survive exactly until
#: the next release. It carries no external asset -- no font, no script, no
#: image -- so it renders the same on a phone in a hotel as it does here.
_INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>tofa for Kodi — add-on repository</title>
<style>
  :root {{ color-scheme: dark light; }}
  body {{ margin: 0; padding: 2.5rem 1.25rem; background: #0b1116; color: #e8eef2;
         font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
         Helvetica, Arial, sans-serif; }}
  main {{ max-width: 40rem; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; }}
  p.sub {{ color: #8fa3b0; margin: 0 0 2rem; }}
  code {{ background: #16212a; border-radius: 6px; padding: .15rem .4rem;
          font-size: .9em; word-break: break-all; }}
  pre {{ background: #16212a; border-radius: 10px; padding: 1rem;
         overflow-x: auto; }}
  ol {{ padding-left: 1.2rem; }} li {{ margin: .4rem 0; }}
  a {{ color: #35d6c3; }}
  footer {{ margin-top: 2.5rem; color: #8fa3b0; font-size: .9rem; }}
</style>
</head>
<body>
<main>
  <h1>tofa for Kodi</h1>
  <p class="sub">This address is an add-on repository for Kodi, not a website.
     Kodi reads it; a browser has nothing to show.</p>

  <p>To install, add this as a source in Kodi:</p>
  <pre><code>{base_url}</code></pre>

  <ol>
    <li>Settings → System → Add-ons → turn on <strong>Unknown sources</strong>.
        Kodi refuses to install from a zip without it, and only says so when
        you try.</li>
    <li>Settings → File manager → Add source → paste the address above. Kodi
        cannot guess a name for an <code>https</code> source and will not
        accept an empty one — call it <strong>tofa</strong>.</li>
    <li>Settings → Add-ons → Install from zip file → that source →
        <code>{repo_zip}</code></li>
    <li>Install from repository → tofa Add-on Repository → Video add-ons →
        <strong>tofa for Kodi</strong></li>
    <li>Start it from <strong>Program add-ons → tofa for Kodi</strong>. That is
        the television interface; the Videos entry is the plain directory
        listing, which works under any skin but is not the same thing.</li>
  </ol>

  <p>Kodi keeps the add-on updated from here afterwards. The current add-on
     version is <code>{version}</code>, and it needs a tofa server on
     <code>{floor}</code> or newer.</p>

  <p>Or download it directly:
     <a href="{repo_zip}">{repo_zip}</a></p>

  <!-- These two links are LOAD-BEARING, not decoration. Kodi's HTTP
       "directory" for this host is literally the <a href> list on this page,
       and CFile::Open consults g_directoryCache BEFORE it opens a socket:
       if the directory is cached and the file is not in that listing, the
       open fails instantly, with no request and no log line.

       Our own install steps have the user add this host as a Kodi source and
       browse it ("Install from zip file"), which caches exactly that listing.
       While these were missing, the repository could not read its own index
       afterwards -- "Could not connect to repository", until a Kodi restart
       cleared the cache. That was the first bug an outside user ever
       reported. See tests/test_channel_index_links.py. -->
  <p class="repo-files">The repository's own index, for Kodi:
     <a href="addons.xml">addons.xml</a> and
     <a href="addons.xml.sha256">addons.xml.sha256</a>.</p>

  <footer>
    Source, releases and issues:
    <a href="{project_url}">{project_label}</a>.
    Licensed GPL-2.0-only.
  </footer>
</main>
</body>
</html>
"""

#: Where a human goes from that page. Not derived from BASE_URL: the channel
#: and the source repository are different things and may not stay on one host.
PROJECT_URL = "https://github.com/cinema-ONE/tofa-for-kodi"


def _write_index(out_dir: str, base_url: str, version: str) -> None:
    floor = server_floor() or "the version in README.txt"
    html = _INDEX.format(
        base_url=base_url, repo_id=REPO_ID, repo_version=REPO_VERSION,
        repo_zip="%s-%s.zip" % (REPO_ID, REPO_VERSION),
        version=version, floor=floor, project_url=PROJECT_URL,
        project_label=PROJECT_URL.split("//", 1)[-1])
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)


def custom_domain(base_url: str) -> str | None:
    """The host to write into CNAME, or None if this tree must not carry one.

    GitHub Pages binds a hostname to a REPOSITORY by the `CNAME` file in the
    served tree, not by DNS. Every custom subdomain's DNS record points at the
    same `<user>.github.io`, because DNS has no notion of a path -- so the file
    is the only thing saying which repo answers for which host. Publish a tree
    without it and the domain silently unbinds: the channel goes down for every
    install, and nothing fails locally to tell you.

    Returns None for a `github.io` URL, which needs no file, and for a LAN test
    build (`--base-url http://<ip>:8000`), which must never claim a domain.
    """
    host = urllib.parse.urlsplit(base_url).hostname or ""
    if not host or host == "localhost" or host.endswith(".github.io"):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    return None


#: Where the built tree is committed and served from. `publish` writes to
#: dist/repo and that gets copied here, so this is "what is already public".
PUBLISHED_DIR = os.path.join(ROOT, "docs")


def republish_problems(version: str) -> list[str]:
    """Would this publish change an ALREADY-PUBLISHED version's contents?

    On 2026-08-15 plugin.video.tofa-0.9.3.zip went out three times with
    different bytes, because a doc fix inside the add-on shipped without the
    version moving. The differences were real but invisible: same name, same
    version, 848 files, one of them changed. Kodi decides whether to update
    by comparing VERSIONS, so nobody holding an earlier 0.9.3 would ever be
    offered a later one -- "0.9.3" quietly stops naming one thing.

    Compared by per-file CRC against the published zip rather than by
    building a second nine-megabyte archive and diffing bytes: zip CRCs are
    of the uncompressed content, which is exactly the question, and it avoids
    a false positive from compression or timestamps differing.

    THIS LIVES IN publish, NOT check. In `check` it would fail every change
    made after a release until somebody bumped, which is the opposite of how
    this project versions -- addon.xml carries the version being worked
    TOWARDS, and only publishing makes an artifact public.
    """
    zip_name = "plugin.video.tofa-%s.zip" % version
    published = os.path.join(PUBLISHED_DIR, "plugin.video.tofa", zip_name)
    if not os.path.exists(published):
        return []          # never published at this version: nothing to clash

    try:
        with zipfile.ZipFile(published) as archive:
            was = {i.filename: i.CRC for i in archive.infolist()}
    except (OSError, zipfile.BadZipFile) as exc:
        return ["cannot read the published %s (%s)" % (zip_name, exc)]

    now = {}
    for path, arcname in package_files():
        with open(path, "rb") as handle:
            now[arcname] = zlib.crc32(handle.read()) & 0xFFFFFFFF

    changed = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k))
    if not changed:
        return []
    shown = ", ".join(changed[:4]) + ("" if len(changed) <= 4 else
                                      " and %d more" % (len(changed) - 4))
    return ["%s is already published with DIFFERENT contents (%d file(s): %s). "
            "Bump the version, or pass --republish if replacing it is "
            "deliberate." % (zip_name, len(changed), shown)]


def do_publish(base_url: str | None, out_dir: str,
               republish: bool = False) -> int:
    base_url = (base_url or BASE_URL or "").rstrip("/")
    if not base_url:
        print("publish needs the URL this tree will be served from, e.g.\n"
              "    python3 tools/release.py publish --base-url "
              "https://tofa.cinemaone.ch\n"
              "It is baked into the repository add-on users install, so there "
              "is no safe default to guess. BASE_URL is normally set.")
        return 1
    if do_check():
        print("not publishing a version that does not check out")
        return 1

    version = current_version()
    if not republish:
        clash = republish_problems(version)
        for line in clash:
            print("PROBLEM: %s" % line)
        if clash:
            return 1
    addon_zip = os.path.join(DIST, "plugin.video.tofa-%s.zip" % version)
    # ALWAYS repackage. The version string does not move during development,
    # so `dist/` reliably holds a zip of this same name built at some earlier
    # point in the version's life -- and reusing it published a fresh mtime
    # over stale contents, with nothing in the output admitting it. Caught
    # 2026-08-15, hours before the first real publish: dist/ held a 0.9.2 from
    # before the uniform action row and the retaken screenshot landed, so the
    # update channel would have served an add-on that matched neither the
    # v0.9.2 tag nor the repo serving it. `dist/` is gitignored, so nothing
    # else was ever going to notice.
    if do_package():
        return 1

    os.makedirs(out_dir, exist_ok=True)
    entries = []

    art = declared_assets(read_addon_xml())
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

    # Emitted from BASE_URL rather than kept by hand in docs/, so the file and
    # the URL baked into the repository zip cannot drift apart -- and so a
    # rebuild that replaces the tree cannot quietly drop it.
    domain = custom_domain(base_url)
    if domain:
        with open(os.path.join(out_dir, "CNAME"), "w", encoding="utf-8") as fh:
            fh.write(domain + "\n")
    # Jekyll is Pages' default and would treat this as a site to build rather
    # than a tree to serve. Nothing here starts with `_` today, so it happens
    # to survive, but the add-on decides its own filenames and one underscore
    # would drop a file from the channel.
    with open(os.path.join(out_dir, ".nojekyll"), "w", encoding="utf-8") as fh:
        fh.write("")
    # A COPY of the repository zip at the root, which is the only thing a
    # person ever installs by hand. Kodi's "Install from zip file" browses an
    # HTTP source by parsing links out of whatever the server returns, and
    # Pages generates no directory index -- so a zip one level down is
    # unreachable: browsing INTO repository.tofa/ just gets Pages' 404.
    # Every working GitHub-Pages-hosted Kodi repo does it this way.
    #
    # The nested copy stays. addons.xml points Kodi at it by URL, and Kodi
    # fetches that itself rather than browsing to it.
    shutil.copy2(os.path.join(out_dir, REPO_ID,
                              "%s-%s.zip" % (REPO_ID, REPO_VERSION)),
                 os.path.join(out_dir, "%s-%s.zip" % (REPO_ID, REPO_VERSION)))
    _write_index(out_dir, base_url, version)

    problems = verify_repo(out_dir, base_url)
    for line in problems:
        print("PROBLEM: %s" % line)
    print("\n%s" % os.path.relpath(out_dir, ROOT))
    for base, _dirs, files in sorted(os.walk(out_dir)):
        for name in sorted(files):
            path = os.path.join(base, name)
            print("  %-58s %8.1f KB" % (os.path.relpath(path, out_dir),
                                        os.path.getsize(path) / 1024.0))
    print("\nserve that directory at %s" % base_url)
    print("users install %s/%s-%s.zip once; "
          "%s follows on its own."
          % (base_url, REPO_ID, REPO_VERSION, "plugin.video.tofa"))
    return 1 if problems else 0


def verify_repo(out_dir: str, base_url: str | None = None) -> list[str]:
    """Read the tree back the way Kodi will, and say what would break.

    Publishing is the one step with no feedback loop -- a wrong path or a
    stale hash looks fine locally and fails on a stranger's box, days later,
    as "could not connect to repository"."""
    problems = []

    domain = custom_domain(base_url) if base_url else None
    if domain:
        cname = os.path.join(out_dir, "CNAME")
        if not os.path.exists(cname):
            problems.append(
                "CNAME is missing, so serving this tree would unbind %s and "
                "take the channel down for every install" % domain)
        else:
            with open(cname, encoding="utf-8") as handle:
                written = handle.read().strip()
            if written != domain:
                problems.append("CNAME says %r but the tree is built for %s"
                                % (written, domain))
    index = os.path.join(out_dir, "addons.xml")
    if not os.path.exists(index):
        return problems + ["addons.xml is missing"]
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
    pub.add_argument("--republish", action="store_true",
                     help="replace an already-published version whose "
                          "contents have changed (normally refused)")
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
        return do_publish(args.base_url, args.out, args.republish)
    return do_check()


if __name__ == "__main__":
    sys.exit(main())
