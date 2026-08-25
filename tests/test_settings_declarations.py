"""settings.xml must be well-formed, and an empty default needs allowempty.

Both halves are here because both got through on 2026-08-25 and were caught
by a BOX, not by anything in this repo.

1. Two new string settings were declared with `<default></default>` and no
   constraints. Kodi refuses that outright:

       error <CSettingString>: error reading the default value of "fonts_declined_skins"
       warning <CSettingGroup>: unable to read setting "fonts_declined_skins"

   The setting then never registers, `getSetting` answers nothing, and the
   per-skin decline it backs silently forgets itself. Nothing raises in
   Python -- the add-on runs, it just quietly loses the value.

2. Fixing (1) introduced a `--` inside an XML comment, which is illegal and
   made the whole file unparseable. `check_settings_layout.py` passed anyway
   (it does not parse strictly) and `check_xml.py` only covers skin files, so
   a broken settings.xml had no gate at all.

Run:  python3 test_settings_declarations.py
"""
from __future__ import annotations
import os, sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, "plugin.video.tofa", "resources", "settings.xml")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


raw = open(SETTINGS, encoding="utf-8").read()

try:
    tree = ET.fromstring(raw)
    check("settings.xml is well-formed XML", True)
except ET.ParseError as exc:
    check("settings.xml is well-formed XML", False, str(exc))
    print("\n0/1 passed")
    sys.exit(1)

# `--` is illegal inside an XML comment. Python's parser rejects the file
# outright, but say WHICH rule broke rather than leaving a column number.
check("no '--' inside an XML comment",
      all("--" not in c for c in
          __import__("re").findall(r"<!--(.*?)-->", raw, __import__("re").S)),
      "an em-dash pair in a comment makes the whole file unparseable")

settings = tree.findall(".//setting")
check("settings are found at all", len(settings) > 5, f"{len(settings)} found")

offenders = []
for s in settings:
    if s.get("type") != "string":
        continue
    default = s.find("default")
    # An absent <default> is fine; an EMPTY one is what needs the constraint.
    if default is None or (default.text or "").strip():
        continue
    allowempty = s.find("./constraints/allowempty")
    if allowempty is None or (allowempty.text or "").strip().lower() != "true":
        offenders.append(s.get("id"))

check("every empty-default string setting allows empty",
      not offenders,
      "Kodi refuses these and they never register: %s" % ", ".join(offenders))

# The two the bug was about, named so a rename cannot quietly drop the cover.
ids = {s.get("id") for s in settings}
for sid in ("fonts_declined_skins", "seekbar_declined_skins"):
    check(f"{sid} is declared", sid in ids,
          "hostsetup reads this; an undeclared setting silently returns nothing")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)
