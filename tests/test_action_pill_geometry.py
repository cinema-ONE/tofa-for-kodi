"""Every Detail action pill lays its contents out the same way.

Checked against the RENDERED XML, not against the layout function, because
the bug this exists for lived in neither: `glass_pill(width=...)` and the
`action_pill_content(width, ...)` that fills it are separate arguments at
separate call sites, and one of them was left at the old 244 while the pill
itself became 325. The function was right, the pill was right, and the
contents were laid out for a pill 81px narrower than the one they were in.

Nothing about that is visible in either call on its own. It IS visible in
the output -- the label box stopped 81px short of where every other pill's
ended -- and Adrian saw it on screen before any test did ("watchlist still
looks different"). So the invariant is asserted where the mistake shows up.

The invariant, from fragments.action_pill_layout:

  * the icon is at ACTION_PILL_INSET, in every pill
  * a chevron, where there is one, ends at width - INSET
  * otherwise the LABEL ends there
  * so every pill's contents span exactly INSET .. width - INSET
"""
from __future__ import annotations
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.skin import fragments as F  # noqa: E402

XML = os.path.join(ROOT, "plugin.video.tofa", "resources", "skins", "Main",
                   "1080i", "script-tofa-detail.xml")

#: group id -> (name, pill width, has a trailing chevron)
PILLS = {
    5226: ("Options", F.ACTION_PILL_W, True),
    5221: ("Rewatch", F.ACTION_PILL_W, False),
    5231: ("Watchlist", F.ACTION_PILL_W, False),
    5241: ("Edition", F.ACTION_PILL_W, True),
    5251: ("Cancel request", F.ACTION_PILL_W, False),
}

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


def group_body(xml: str, gid: int) -> str:
    """One <control type="group" id="N"> ... </control>, balanced."""
    start = xml.find('<control type="group" id="%d">' % gid)
    if start < 0:
        return ""
    depth, at = 0, start
    while True:
        m = re.compile(r"<control\b|</control>").search(xml, at)
        if not m:
            return xml[start:]
        if m.group(0) == "</control>":
            depth -= 1
            if depth == 0:
                return xml[start:m.end()]
        else:
            depth += 1
        at = m.end()


def labels(body: str):
    """(posx, width) for each label control, in document order."""
    found = re.findall(
        r'<control type="label">\s*(?:<visible>[^<]*</visible>\s*)?'
        r'<posx>(\d+)</posx>\s*(?:<align>center</align>\s*)?'
        r'<posy>0</posy>\s*(?:<align>center</align>\s*)?<width>(\d+)</width>',
        body)
    return [(int(x), int(w)) for x, w in found]


def main() -> int:
    with open(XML, encoding="utf8") as handle:
        xml = handle.read()

    inset, icon_w = F.ACTION_PILL_INSET, F.ACTION_ICON_W
    icon_positions = set()
    for gid, (name, width, trailing) in sorted(PILLS.items()):
        body = group_body(xml, gid)
        got = labels(body)
        if not got:
            check("%s: found in the rendered XML" % name, False, "no labels")
            continue
        icon_x, icon_width = got[0]
        icon_positions.add(icon_x)
        check("%s: icon at the inset" % name,
              (icon_x, icon_width) == (inset, icon_w), str(got[0]))
        last_x, last_w = got[-1]
        if trailing:
            check("%s: the chevron ends at width - inset" % name,
                  last_w == icon_w and last_x + last_w == width - inset,
                  "ends at %d, expected %d" % (last_x + last_w, width - inset))
            label_boxes = got[1:-1]
        else:
            check("%s: no chevron follows the label" % name,
                  last_w > icon_w, str(got[-1]))
            label_boxes = got[1:]
        # The label box is CENTRED on the pill, chevron or not: it reserves
        # as much on the right as the icon takes on the left. Without that,
        # a chevronless pill's text sat ~19px right of centre, which is what
        # Adrian saw ("looks too far to the right instead of really
        # centered").
        lx, lw = label_boxes[0]
        check("%s: the label box is centred on the pill" % name,
              abs((lx + lw / 2) - width / 2) < 1,
              "box centre %.1f, pill centre %.1f" % (lx + lw / 2, width / 2))
        check("%s: every label copy shares one box" % name,
              len(set(label_boxes)) == 1, str(label_boxes))

    check("every pill puts its icon in the same place",
          len(icon_positions) == 1, str(icon_positions))

    # The marqueeing pill is the only one with two label copies, and they
    # must be the pair -- one gated on focus, one on its complement.
    # Counting bare gate strings would count the pill's own focus fill and
    # rim too, so look for the LABEL pair specifically: same property, one
    # copy per focus state, and the scroll on exactly the focused one.
    edition = group_body(xml, 5241)
    copies = re.findall(
        r'<control type="label">\s*<visible>(!?)Control\.HasFocus\(5240\)</visible>'
        r'(.*?)</control>', edition, re.S)
    version_copies = [(neg, body) for neg, body in copies
                      if "version_label" in body]
    check("the edition label is drawn once per focus state",
          sorted(neg for neg, _b in version_copies) == ["", "!"],
          str([neg for neg, _b in version_copies]))
    check("...and only the focused copy scrolls",
          [("<scroll>true</scroll>" in b) for neg, b in version_copies
           if neg == ""] == [True]
          and all("<scroll>" not in b for neg, b in version_copies if neg == "!"))
    for gid, (name, _w, _t) in PILLS.items():
        if gid == 5241:
            continue
        check("%s does not marquee" % name,
              "<scroll>true</scroll>" not in group_body(xml, gid))

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("action pills: contents span inset..width-inset, every one (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
