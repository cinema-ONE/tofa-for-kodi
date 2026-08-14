"""Checks the Settings pages' grouplist geometry.

Two invariants, both of which fail SILENTLY and look like something else.

1. **A group's content must fit the viewport.** Kodi's grouplist scrolls to
   reveal a focused CHILD in full; a child taller than the viewport cannot be
   revealed, and the symptom is focus appearing to stick or rows that cannot
   be reached (project_kodi_grouplist_scroll_limit). Only the CONTENT has to
   fit -- every group carries SETTINGS_GROUP_TRAIL of empty space at its
   bottom, and that pad may hang past the edge harmlessly. SETTINGS_FOX_GROUP_H
   is 6px over the viewport for exactly that reason and is fine.

2. **The trailing pad must replace the itemgap, not add to it.** Group
   boundaries are supposed to measure SETTINGS_GROUP_GAP: a group's own pad,
   plus the grouplist's itemgap, plus the next group's section lead-in. Get
   that wrong and every page's rhythm shifts by a few pixels, which is exactly
   the kind of change nobody notices in review and everybody notices on a TV.

The children are read out of the TEMPLATE rather than listed here, so a group
added later is checked automatically instead of being silently skipped.
"""
from __future__ import annotations
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

from lib.skin import tokens as T  # noqa: E402

TEMPLATE = os.path.join(ROOT, "plugin.video.tofa", "resources", "lib", "skin",
                        "templates", "main.xml.tpl")


def grouplist_children() -> dict:
    """{grouplist id: [height token, ...]} straight out of the template."""
    text = open(TEMPLATE, encoding="utf-8").read()
    found = {}
    for m in re.finditer(
            r'<control type="grouplist" id="(8\d90)">(.*?)\n                </control>',
            text, re.S):
        found[m.group(1)] = re.findall(
            r'<control type="group">\s*\n\s*<width>[^<]*</width>\s*\n'
            r'\s*<height>\{(\w+)\}</height>', m.group(2))
    return found


def main() -> int:
    fails = []
    children = grouplist_children()
    if not children:
        print("FAIL could not read any grouplist out of the template")
        return 1

    viewport = T.SETTINGS_GROUPLIST_H
    trail = T.SETTINGS_GROUP_TRAIL

    # 1. content fits
    checked = 0
    for gid, tokens in sorted(children.items()):
        if not tokens:
            fails.append("grouplist %s has no group children" % gid)
        for name in tokens:
            checked += 1
            height = getattr(T, name, None)
            if height is None:
                fails.append("%s is in the template but not in tokens.py" % name)
                continue
            content = height - trail
            if content > viewport:
                fails.append(
                    "%s content is %d, taller than the %d viewport -- it cannot "
                    "be scrolled to (pad excluded)" % (name, content, viewport))

    # 2. the pad replaces the itemgap
    boundary = trail + T.SETTINGS_GROUPLIST_ITEMGAP + T.SETTINGS_SECTION_LEAD
    if boundary != T.SETTINGS_GROUP_GAP:
        fails.append("group boundary measures %d, not SETTINGS_GROUP_GAP (%d): "
                     "trail %d + itemgap %d + section lead %d"
                     % (boundary, T.SETTINGS_GROUP_GAP, trail,
                        T.SETTINGS_GROUPLIST_ITEMGAP, T.SETTINGS_SECTION_LEAD))

    # 3. the region still reaches the screen edge
    if T.SETTINGS_GROUPLIST_Y + viewport != T.SCREEN_H:
        fails.append("the region ends at %d, not the screen edge (%d)"
                     % (T.SETTINGS_GROUPLIST_Y + viewport, T.SCREEN_H))

    for f in fails:
        print("FAIL " + f)
    print("checked %d groups across %d settings pages, %d problem(s)"
          % (checked, len(children), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
