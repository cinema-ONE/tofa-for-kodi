"""The card menu as app 2.1.0 draws it: Play, a white Remove, filled set marks.

Run:  python3 test_card_menu_210.py
"""
import inspect
import os

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.skin import icon_glyphs
from resources.lib.windows import cardoptions as co

RESULTS = []
MEDIA = os.path.join(os.path.dirname(__file__), "..", "plugin.video.tofa", "resources",
                     "skins", "Main", "media")


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


check("Remove from Continue Watching is not drawn in red",
      co._CATALOG[co.REMOVE_FROM_CW][2] is False)
check("the menu has no Resume wording any more",
      "resume" not in inspect.signature(co.show).parameters
      and '"Resume"' not in inspect.getsource(co.CardOptionsDialog))
check("set marks wear the filled glyphs, unset ones the Lucide outlines",
      co._CATALOG[co.SEEN_REMOVE][1] == icon_glyphs.CIRCLE_CHECK_FILLED
      and co._CATALOG[co.NOT_INTERESTED_REMOVE][1] == icon_glyphs.THUMBS_DOWN_FILLED
      and co._CATALOG[co.SEEN_ADD][1] == icon_glyphs.CIRCLE_CHECK
      and co._CATALOG[co.NOT_INTERESTED_ADD][1] == icon_glyphs.THUMBS_DOWN)
GEN = open(os.path.join(os.path.dirname(__file__), "..", "tools", "gen_filled_glyphs.py")).read()
check("...glyphs the font generator puts where icon_glyphs looks",
      "0xF8E0" in GEN and "0xF8E1" in GEN
      and (icon_glyphs.CIRCLE_CHECK_FILLED, icon_glyphs.THUMBS_DOWN_FILLED) == (0xF8E0, 0xF8E1))
check("no bitmap icons: the glyphs are in the font",
      not any(f.startswith("icon-") and "filled" in f for f in os.listdir(MEDIA)))

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
