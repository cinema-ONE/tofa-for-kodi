# -*- coding: utf-8 -*-
"""The changelog is prose; `<news>` is XML. Something has to escape it.

`release.py sync` copies the newest changelog entry into `addon.xml`'s
`<news>`. The changelog is a plain text file nobody thinks of as markup, and
the add-on's own settings pages are called "Privacy & About" and "Audio &
Subtitles" -- so the moment a release note names one, a bare `&` lands in
addon.xml and the file stops being well-formed.

That is not a silent failure: check_xml stops dead, and so does every suite
that parses addon.xml. It is a CONFUSING one, because nothing about writing a
changelog line suggests you just broke the manifest. It happened on 0.9.3.

The round trip is what matters, not the escaping alone: `check` compares the
`<news>` body against the changelog to decide whether the file is stale, so
escaping on write without unescaping on read would report a freshly synced
file as drifted for ever.

Run:  python3 test_news_escaping.py
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import release  # noqa: E402

CHECKS = FAILED = 0


def check(name, ok, detail=""):
    global CHECKS, FAILED
    CHECKS += 1
    if ok:
        print("PASS  %s" % name)
    else:
        FAILED += 1
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


SHELL = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
         '<addon id="plugin.video.tofa" version="0.0.1">\n'
         '  <extension point="xbmc.addon.metadata">\n'
         '    <assets>\n      <icon>icon.png</icon>\n    </assets>\n'
         '  </extension>\n</addon>\n')

# Every character that cannot appear as itself, plus the real-world case.
HOSTILE = "\n".join([
    "- Settings -> Privacy & About now opens the issue tracker.",
    "- Audio & Subtitles: a <track> is picked by language & flags.",
    "- A > B, and 5 < 6.",
])


def main():
    written = release._set_news(SHELL, HOSTILE)

    # 1. The manifest must still parse. This is the failure that stopped a
    #    release: check_xml and every addon.xml-parsing suite died at once.
    try:
        ET.fromstring(written)
        parsed = True
    except ET.ParseError as exc:
        parsed = False
        print("      parse error: %s" % exc)
    check("addon.xml still parses with & < > in the changelog", parsed)

    check("the raw ampersand does not survive into the file",
          "& " not in written.split("<news>")[1].split("</news>")[0],
          "a bare & is still in <news>")

    # 2. ...and the round trip gives the changelog back unchanged, or `check`
    #    reports a freshly synced file as stale for ever.
    back = release.news_in_xml(written)
    check("what comes back equals what went in", back == HOSTILE,
          "%r != %r" % (back, HOSTILE))

    # 3. The escaper's own ordering trap: & must go first on the way out and
    #    last on the way back, or the escapes escape each other.
    check("&amp; does not become &amp;amp;",
          release._xml_escape("&amp;") == "&amp;amp;")
    check("...and unescapes back to what it was",
          release._xml_unescape(release._xml_escape("&amp;")) == "&amp;")
    check("a plain line is untouched",
          release._xml_escape("nothing special here") == "nothing special here")

    # 4. The real 0.9.3 entry, which is what actually broke.
    real = "- Report a problem now opens Settings -> Privacy & About."
    out = release._set_news(SHELL, real)
    try:
        ET.fromstring(out)
        ok = release.news_in_xml(out) == real
    except ET.ParseError:
        ok = False
    check("the 0.9.3 entry that broke this now survives the round trip", ok)

    print()
    if FAILED:
        print("FAIL: %d of %d" % (FAILED, CHECKS))
        return 1
    print("news escaping: prose survives becoming XML (%d checks)" % CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
