"""Is the file set that goes public actually safe to publish?

Two questions, one gate, run over exactly the files that would be copied into
`tofa-for-kodi` (see public-release/MANIFEST.md):

  QUOTES  -- does any comment reproduce a private document's own prose?
  MARKERS -- does any file still name our network, our boxes or us?

Neither is a judgement call at the point of use, which is the point: both
were answered once by reading, and reading does not survive the next hundred
comments. Exit status is 1 while anything is outstanding, so this can gate a
release.

    python3 tools/check_public_set.py             both checks
    python3 tools/check_public_set.py --quotes    quotations only
    python3 tools/check_public_set.py --markers   identifiers only
    python3 tools/check_public_set.py --all       include the shared-data runs
    python3 tools/check_public_set.py -n 6        tighter quote window, more noise


QUOTES
------

The public-release decision (GitHub issue #5, signed off 2026-08-12) is
deliberately narrow: spec SECTION NUMBERS stay -- all ~200 of them, plus the
`internal-docs/...` paths -- because they are opaque pointers and they are
what makes the code navigable. What may not travel is a private document's
PROSE. A comment that says "see 9.4" is a reference; one that reproduces the
sentence 9.4 is made of is a quotation.

Nothing here judges intent. It normalises both sides to lowercase token
sequences, indexes every N-gram of each private source, and slides the same
window over each candidate file. Eight tokens in a row is past coincidence
for English prose; below that, two people describing the same button land on
the same phrasing often enough to drown the signal.

The sources are ranked, and only tofa's GATE. Theirs are the reason this
check exists: TV-DESIGN.md, the vendored OpenAPI spec and the API brief are
documents we were shown, and their sentences are not ours to republish.

Ours are reported under `--ours` and never fail the run, because the match
usually runs the other way. `internal-docs/ANIMATION.md` is an audit of our
own skin XML and quotes it at length, so nearly every hit against it is the
DOCUMENT copying the code -- 564 of them, all pointing at generated XML that
was there first. Gating on that would mean deleting the audit or ignoring the
tool, and the tool would lose.

Runs made of the same DATA on both sides -- hex palettes, icon-name lists,
gradient stops, an API's own field names -- are reported as `data` and not
counted. The spec lists `snow f1efe8` and so does the generator that draws
it; that is the value doing its job, not a copied sentence.


MARKERS
-------

Every IPv4 literal, box hostname, server name and personal identifier that
has ever been in this tree, as patterns rather than as a memory of which
files were fixed. IPs are checked against an ALLOWLIST rather than a
denylist: a new address typed into a docstring next year is the case that
matters, and it cannot be on a list of the ones we already knew about.

A private source of OURS that is not in this checkout is not an error. One of
TOFA's is: the run then compared the public set against nothing, and a pass
would mean "nothing was compared" rather than "nothing was quoted". So QUOTES
fails in the public checkout, by design -- every private document is absent
there. Run the quote gate from the vault (this repo), where the sources live;
run `--markers` anywhere, since its patterns are in this file and need no
sources at all. That split is why CI on the public repo runs `--markers`.

That distinction is not academic. It went unnoticed until 2026-08-14, when the
same command exited 0 in both checkouts -- having actually checked in one and
checked nothing in the other.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkouts  # noqa: E402  (sibling module in tools/)

#: Where tofa's confidential documents are. This checkout while the add-on
#: and the vault are one tree; the sibling vault once they are not. None when
#: there is no vault anywhere, which is a FAILURE rather than a skip -- see
#: the CANNOT VERIFY path in main().
VAULT = checkouts.vault(ROOT)

#: A run this long is a quotation rather than two people phrasing the same
#: constraint the same way.
DEFAULT_N = 8

#: (path, whose it is, why it must not be quoted). Order is severity.
PRIVATE_SOURCES = [
    (os.path.join("internal-docs", "TV-DESIGN.md"), "tofa",
     "tofa's internal TV design document"),
    (os.path.join("internal-docs", "api", "tofa-media-server-api.yaml"), "tofa",
     "the vendored OpenAPI spec, which tofa considers internal"),
    # The guide tofa writes for AI consumers. It arrived as `.txt` and was
    # renamed to `.md` at 0.9.30. A RENAME is the quietest way this list stops
    # gating: the new name is simply not here, and the old one goes absent.
    # MOVE the entry, never keep both -- an absent source is a hard failure
    # now ("CANNOT VERIFY"), so a stale spelling left behind fails every run.
    (os.path.join("internal-docs", "api", "tofa-media-server-api.md"), "tofa",
     "the API guide that ships beside the spec"),
    # OURS despite the name: the brief is our own living reference, and most
    # of its prose was written by reading this code -- so a match against it
    # is almost always the brief quoting a comment, not the reverse. It stays
    # private because of what it documents, not because of who wrote it.
    ("addon-tofa-brief.md", "ours",
     "our reference for tofa's API behaviour; private for what it documents"),
    (os.path.join("tofa UX", "styleguide.md"), "ours",
     "derived from the screenshot folders, which cannot travel"),
    (os.path.join("internal-docs", "ANIMATION.md"), "ours",
     "our own motion audit; private, so quoting it publishes it"),
    (os.path.join("internal-docs", "DIVERGENCES.md"), "ours",
     "our own divergence register; same reason"),
]

#: The tools that travel. The probes and benches stay private, so their
#: comments and their hostnames are not this check's business.
CURATED_TOOLS = {
    "release.py", "check_xml.py", "check_xml_comments.py",
    "check_settings_layout.py", "check_public_set.py", "kodictl.py",
    # Generator OUTPUT. Both pages travel by decision (2026-08-14), and a
    # page carries the same prose its generator does, so a quotation
    # scrubbed from one has to leave the other with it.
    "design_language.html", "icon_reference.html",
}
CURATED_TOOL_DIRS = ("lucide_font_src", "script.tofa.harness",
                     "icon_reference_fonts")
#: Copied wholesale. `public-release/` is included because those files BECOME
#: the new repository's top level.
CURATED_TREES = ("plugin.video.tofa", "tests", "public-release")
#: Where tofa's fox SVGs are, in whichever checkout this is running in --
#: `art/logo-svgs/` in the public repo, beside the APK captures here. Same
#: pair, and for the same reason, as gen_logo_assets._svg_dir().
CURATED_ART = (os.path.join("art", "logo-svgs"),
               os.path.join("tofa UX", "android-tv", "logo-svgs"))
#: `.yml` is here for the CI workflow, which travels as `.github/workflows/`
#: and is as capable of naming a box as any comment is.
TEXT_SUFFIXES = (".py", ".xml", ".txt", ".md", ".html", ".svg", ".json",
                 ".yml")

#: The only IPv4 literals allowed to appear. Everything else is reported,
#: including addresses nobody has seen yet -- which is the case a denylist of
#: our own boxes would sail straight past.
ALLOWED_IPS = {
    "192.168.1.50",   # the documentation LAN address, several docstrings
    "10.0.0.5",       # a second private address, test_direct_only only
    "0.0.0.0", "127.0.0.1", "255.255.255.255",
}
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

#: Hostnames on a private domain that are deliberately public, checked the
#: same allowlist way as the addresses above: a new subdomain has to be named
#: here to travel, so it is a decision rather than an oversight.
#:
#: `tofa.cinemaone.ch` is the add-on's update channel, settled 2026-08-15. The
#: domain it sits on is also the personal email domain below, so the marker
#: rule still has to fire on `adrian.betschart@cinemaone.ch` and on any other
#: host -- only these exact names are exempt.
ALLOWED_HOSTS = {
    "tofa.cinemaone.ch",
}
#: A private-domain hit is only ever allowed as part of one of those names.
ALLOWED_HOST_RE = re.compile(
    r"\b(?:%s)\b" % "|".join(re.escape(h) for h in sorted(ALLOWED_HOSTS)),
    re.I)

#: (pattern, what it is). Hardware MODEL names are deliberately absent --
#: "UGOOS AM6B" is a product, and naming the box a measurement was taken on
#: is what makes the measurement worth anything.
MARKER_PATTERNS = [
    (re.compile(r"\bCINEMAONE-BOX\b", re.I), "a box hostname"),
    (re.compile(r"\bMACBOT\b", re.I), "a box hostname"),
    (re.compile(r"\bKODIBOT\b", re.I), "a box hostname"),
    (re.compile(r"\bPETABOT\b", re.I), "a server name"),
    (re.compile(r"feste ?TESTE", re.I), "a server name"),
    (re.compile(r"\bbetschart\b", re.I), "a surname"),
    (re.compile(r"cinemaone\.ch", re.I), "a personal email domain"),
    (re.compile(r"\bbe6a8725\b|\b9f34e13d\b", re.I), "a real server uuid"),
    (re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I), "a MAC address"),
    # Case-SENSITIVE, and the only one that is: `/Users/adrian` is a macOS
    # home directory, `/users/me` is the API endpoint half this add-on's
    # docstrings mention.
    (re.compile(r"/Users/[a-z]+"), "a path on someone's machine"),
]

#: Lines where a marker is the subject rather than a leak.
MARKER_EXEMPT = re.compile(
    r"MARKER_PATTERNS|ALLOWED_IPS|a box hostname|a server name|a surname"
    r"|a personal email domain|a real server uuid|a MAC address"
    r"|a path on someone's machine")


# ------------------------------------------------------------- shared bits --

#: A dotted or slashed identifier is ONE token, not the four words it is
#: spelled with: `speaker.wave.2.fill` is an SF Symbol name, `media.progress`
#: is an endpoint, and a comment listing eight of them beside the document's
#: own table of the same eight is naming an API, not reciting a sentence.
#: Section numbers collapse the same way, which is what makes `7.9.4` a
#: citation rather than three words. The dot only binds when a digit or
#: letter follows, so a full stop still ends a sentence.
WORD_RE = re.compile(r"[a-z0-9]+(?:[./][a-z0-9]+)*")


def words_with_lines(text: str) -> tuple[list[str], list[int]]:
    """Lowercase token sequence, and the 1-based line each token came from."""
    tokens, lines = [], []
    for line_no, line in enumerate(text.splitlines(), 1):
        for token in WORD_RE.findall(line.lower()):
            tokens.append(token)
            lines.append(line_no)
    return tokens, lines


#: Never scanned, in either layout: build output, caches, local settings, and
#: the published update channel (which is a COPY of the add-on, so scanning it
#: reports every finding twice).
SKIP_DIRS = {".git", "__pycache__", "dist", ".claude", "docs", ".venv",
             "node_modules"}


def _whole_repo() -> list[str]:
    """Every text file in this checkout.

    What "the public set" means once the copy has happened: this repository
    IS the published set, so there is no curated subset to keep in step. The
    curated lists below only ever described what to COPY, and copying is over.

    This exists because the lists drifted the first time they were asked to
    hold something new. Four static linters were moved here and the gate
    reported a clean run over a file set that did not include them -- a pass
    that had checked nothing, which is the exact failure this tool is built
    to refuse.
    """
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        found += [os.path.join(base, n) for n in files
                  if n.endswith(TEXT_SUFFIXES)]
    return sorted(set(found))


def candidates() -> list[str]:
    """Every file that is public.

    In a checkout holding `internal-docs/`, that is the curated subset the
    lists below describe -- the tool is being run somewhere that also holds
    material which must NOT travel, so it has to know the difference.
    Anywhere else, everything here is public by construction.
    """
    if not os.path.isdir(os.path.join(ROOT, "internal-docs")):
        return _whole_repo()

    found = []
    for top in CURATED_TREES:
        for base, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            found += [os.path.join(base, n) for n in files
                      if n.endswith(TEXT_SUFFIXES)]
    tools = os.path.join(ROOT, "tools")
    found += [os.path.join(tools, n) for n in sorted(os.listdir(tools))
              if n in CURATED_TOOLS or n.startswith("gen_")]
    for sub in CURATED_TOOL_DIRS:
        for base, dirs, files in os.walk(os.path.join(tools, sub)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            found += [os.path.join(base, n) for n in files
                      if n.endswith(TEXT_SUFFIXES)]
    for rel in CURATED_ART:
        art = os.path.join(ROOT, rel)
        if os.path.isdir(art):
            found += [os.path.join(art, n) for n in sorted(os.listdir(art))
                      if n.endswith(TEXT_SUFFIXES)]
            break
    return sorted(set(found))


def read(path: str) -> str | None:
    try:
        with open(path, encoding="utf8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------- quotes --

#: What an ENUM never has and a sentence always does. `atmos dts-x truehd
#: dts-hd-ma` and `trending-movies popular-tv top-rated-movies` are both long
#: runs of real words with not one of these in them; eight words of English
#: without a single function word is close to impossible.
FUNCTION_WORDS = frozenset("""
a an the this that these those it its is are was were be been being has have
had do does did will would can could should may might must not no nor and or
but so because since if then than as at by for from in into of off on onto out
over to under up with within without when where which who whom whose while
""".split())


def is_prose(run: list[str]) -> bool:
    """True when the run is sentences rather than shared values.

    Two tests, because either alone is wrong. A hex triplet, a `2` in
    `speaker-wave-2` and a gradient stop are digits or two-letter fragments,
    so prose is mostly real words -- but so is a list of codec names or of
    an API's own enum values, and those are the same DATA on both sides
    rather than a copied sentence. The function words are what tell them
    apart."""
    real = sum(1 for token in run if len(token) >= 3 and token.isalpha())
    glue = sum(1 for token in run if token in FUNCTION_WORDS)
    return real >= 0.6 * len(run) and glue >= 2


def scan_quotes(n: int) -> tuple[list[tuple], list[str]]:
    """(hits, sources that were not here to check against).

    A hit is (source label, whose, relative path, line, run, is_prose)."""
    files = candidates()
    loaded = []
    for rel, whose, _why in PRIVATE_SOURCES:
        # From the VAULT, not from ROOT. Once the add-on moves to its own
        # public repo, this tool travels with it and the documents do not --
        # so it has to look next door. Resolving to None here is not a pass:
        # `missing` below turns it into the CANNOT VERIFY failure.
        text = read(os.path.join(VAULT, rel)) if VAULT else None
        if text is None:
            continue
        tokens, _ = words_with_lines(text)
        loaded.append((rel, whose,
                       {tuple(tokens[i:i + n])
                        for i in range(len(tokens) - n + 1)}))
    missing = [(rel, whose) for rel, whose, _why in PRIVATE_SOURCES
               if not any(rel == got for got, _, _ in loaded)]

    hits = []
    for path in files:
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue  # this file quotes the reasoning, not the sources
        text = read(path)
        if text is None:
            continue
        tokens, lines = words_with_lines(text)
        for rel, whose, grams in loaded:
            matched = [tuple(tokens[i:i + n]) in grams
                       for i in range(len(tokens) - n + 1)]
            i = 0
            while i < len(matched):
                if not matched[i]:
                    i += 1
                    continue
                j = i
                while j + 1 < len(matched) and matched[j + 1]:
                    j += 1
                run = tokens[i:j + n]
                hits.append((rel, whose, os.path.relpath(path, ROOT),
                             lines[i], run, is_prose(run)))
                i = j + 1
    hits.sort(key=lambda h: (h[1] != "tofa", not h[5], -len(h[4]), h[2]))
    return hits, missing


# --------------------------------------------------------------- markers --

def scan_markers() -> list[tuple[str, int, str, str]]:
    """(relative path, line, what was found, why it is flagged)."""
    found = []
    for path in candidates():
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue  # the patterns themselves live here
        text = read(path)
        if text is None:
            continue
        rel = os.path.relpath(path, ROOT)
        for line_no, line in enumerate(text.splitlines(), 1):
            if MARKER_EXEMPT.search(line):
                continue
            for address in IPV4_RE.findall(line):
                if address not in ALLOWED_IPS:
                    found.append((rel, line_no, address,
                                  "an IPv4 address not on the allowlist"))
            # A hit that falls INSIDE an allowed hostname is that hostname,
            # not a leak -- `tofa.cinemaone.ch` contains the private domain by
            # construction. Matched by span rather than by substring so that
            # `adrian.betschart@cinemaone.ch` on the same line still fires.
            allowed = [m.span() for m in ALLOWED_HOST_RE.finditer(line)]
            for pattern, why in MARKER_PATTERNS:
                for match in pattern.finditer(line):
                    start, end = match.span()
                    if any(a <= start and end <= b for a, b in allowed):
                        continue
                    found.append((rel, line_no, match.group(0), why))
    return found


# ------------------------------------------------------------------ main --

#: Phrases that may appear in quotation marks even though tofa's documents
#: also contain them, because they are NOT tofa's prose: they are text this
#: app puts on a screen, or a value the server sends on the wire. The design
#: document contains "Mark as Watched" for the same reason our code does --
#: it is the label a viewer reads -- and a comment that cannot name the row
#: it is about is not a comment. An ALLOWLIST rather than a pattern, for the
#: same reason ALLOWED_IPS is one: the phrase that matters is the one nobody
#: has typed yet, and it should have to be added on purpose.
QUOTED_ON_SCREEN = {
    "0 min left", "n min left", "nn min left", "min left",
    "3d frame packed", "3d side by side", "a z then",
    "add to library", "director s cut", "dolby truehd dolby atmos",
    "dts hd m", "go to details", "in your library", "mark as watched",
    "more like this", "not in library", "not in your library",
    "pair this tv", "play if in library", "remove from continue watching",
    "tofa for kodi", "who s watching",
}

#: A quotation of three words or more is a quotation. The 8-token PROSE gate
#: above cannot see these -- it looks for long runs of borrowed sentences,
#: and a design instruction is four words and a number. That gap is what let
#: quoted spec lines accumulate across the tree until 2026-08-29, every one
#: of them under the threshold and none of them ever failing a run.
QUOTED_MIN_WORDS = 3
_QUOTED = re.compile(r'"([^"\n]{10,140})"')


def scan_quoted_phrases() -> list[tuple[str, int, str, str]]:
    """Double-quoted phrases in COMMENTS that appear verbatim in a tofa
    source. Comments only: a string literal in the code is text the add-on
    uses, not a citation, and QUOTED_ON_SCREEN covers the labels a comment
    legitimately names."""
    sources = {}
    for rel, whose, _why in PRIVATE_SOURCES:
        if whose != "tofa" or VAULT is None:
            continue
        body = read(os.path.join(VAULT, rel))
        if body is not None:
            sources[rel] = " ".join(words_with_lines(body)[0])
    found = []
    for path in candidates():
        if not path.endswith(".py"):
            continue
        body = read(os.path.join(ROOT, path))
        if body is None:
            continue
        for number, line in enumerate(body.split("\n"), 1):
            if not line.strip().startswith("#"):
                continue
            for match in _QUOTED.finditer(line):
                raw = match.group(1)
                phrase = " ".join(words_with_lines(raw)[0])
                if len(phrase.split()) < QUOTED_MIN_WORDS:
                    continue
                if phrase in QUOTED_ON_SCREEN:
                    continue
                for rel, text in sources.items():
                    if phrase in text:
                        found.append((os.path.relpath(path, ROOT)
                                      if os.path.isabs(path) else path,
                                      number, raw, rel))
                        break
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", type=int, default=DEFAULT_N,
                        help="run length that counts as a quotation")
    parser.add_argument("--all", action="store_true",
                        help="show shared-data runs as well as prose")
    parser.add_argument("--quotes", action="store_true", help="quotes only")
    parser.add_argument("--markers", action="store_true", help="markers only")
    parser.add_argument("--ours", action="store_true",
                        help="also list hits against OUR private documents, "
                             "which never fail the run")
    args = parser.parse_args()
    do_quotes = args.quotes or not args.markers
    do_markers = args.markers or not args.quotes

    problems = 0
    files = candidates()
    print("checking the %d file(s) in the public set" % len(files))
    if do_quotes:
        # Said out loud on every run. "The gate passed" and "the gate passed
        # against a checkout you had forgotten was there" are otherwise the
        # same output, and the second one is how a stale vault would quietly
        # verify nothing for months.
        print(checkouts.describe(ROOT, VAULT, "private sources"))
    print()

    if do_quotes:
        hits, missing = scan_quotes(args.n)
        shown = [h for h in hits if h[1] == "tofa" or args.ours]
        prose = [h for h in shown if h[5]]
        gating = [h for h in prose if h[1] == "tofa"]
        for rel, whose, path, line, run, is_p in shown:
            if is_p or args.all:
                print("%s:%d  (%d tokens, %s)\n    quotes %s [%s]\n    %s"
                      % (path, line, len(run), "PROSE" if is_p else "data",
                         rel, whose, " ".join(run)))
        by_source = {}
        for rel, _whose, _p, _l, _r, is_p in shown:
            if is_p:
                by_source[rel] = by_source.get(rel, 0) + 1
        print("QUOTES: %d verbatim prose run(s) of >=%d tokens%s"
              % (len(prose), args.n,
                 "" if args.all else "  (%d shared-data run(s) hidden; --all)"
                 % (len(shown) - len(prose))))
        for rel, count in sorted(by_source.items()):
            print("    %-52s %d" % (rel, count))
        if not args.ours:
            ours = sum(1 for h in hits if h[1] == "ours" and h[5])
            print("    %d hit(s) against OUR OWN private documents, which do "
                  "not gate (--ours)" % ours)
        for rel, whose in missing:
            print("    not in the vault, so unchecked: %s%s"
                  % (rel, "  <-- CANNOT VERIFY" if whose == "tofa" else ""))
        problems += len(gating)

        # A source that is not here was not checked, and a run that checked
        # nothing must not report success. Only tofa's gate, for the same
        # reason they are the only ones that gate a hit: ours are informational.
        # This is what makes `--quotes` refuse to pass in the PUBLIC checkout,
        # where every private document is absent by design -- run it from the
        # vault, or run `--markers`, which needs no sources and is what CI uses.
        blind = [rel for rel, whose in missing if whose == "tofa"]
        if blind:
            print("\n    CANNOT VERIFY QUOTATIONS: %d of tofa's %d source(s) "
                  "are absent." % (len(blind), sum(1 for _r, w, _y
                                                   in PRIVATE_SOURCES
                                                   if w == "tofa")))
            print("    A pass here would mean 'nothing was compared', not "
                  "'nothing was quoted'.")
        problems += len(blind)

    if do_quotes:
        quoted = scan_quoted_phrases()
        for path, line, raw, rel in quoted:
            print("%s:%d  quotes %s\n    \"%s\"" % (path, line, rel, raw))
        print("\nQUOTED PHRASES: %d comment(s) quoting a tofa source" % len(quoted))
        if quoted:
            print("    Say it in our own words. The section pointer stays --"
                  " that is what makes\n    the code navigable -- but the"
                  " document's wording does not travel.")
        problems += len(quoted)

    if do_markers:
        found = scan_markers()
        for rel, line, hit, why in found:
            print("%s:%d  %s -- %s" % (rel, line, hit, why))
        print("\nMARKERS: %d private identifier(s)" % len(found))
        problems += len(found)

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
