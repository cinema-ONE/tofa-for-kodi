"""8.9's toast is our own surface, and its two copies cannot drift.

Every toast used to be `xbmcgui.Dialog().notification()`, drawn by the HOST
skin -- the same objection 9.2 raises against a modal for a wrong PIN, and
the reason 8.9's "all toasts fade <300ms" was unreachable: no animation we
write can reach a control we do not own.

The player's copy of the block is HAND-WRITTEN, because script-tofa-player
is a static screen and cannot call a fragment. So the contract between the
two is asserted here instead of trusted.

Run:  python3 test_toast_surface.py
"""
import pathlib
import re

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import toast
from resources.lib.skin import fragments

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, bool(ok), detail))


ROOT = pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"
RENDERED = ROOT / "resources" / "skins" / "Main" / "1080i"
PLAYER = (ROOT / "resources" / "lib" / "skin" / "static"
          / "script-tofa-player.xml").read_text()
FRAGMENT = fragments.toast()


# 1. The Python helper and the XML must name the SAME property, or the
#    message is written where nothing reads it -- which looks exactly like
#    "the toast never fires".
check("toast.py and the fragment agree on the property name",
      toast.PROPERTY == fragments.TOAST_PROPERTY,
      f"{toast.PROPERTY} vs {fragments.TOAST_PROPERTY}")


# 2. Both copies must read window 10000 EXPLICITLY. An unqualified
#    Window.Property() resolves against whatever is topmost, so a toast
#    raised by the background service during playback would be looked up on
#    the player dialog rather than the store the service wrote to.
qualified = f"Window(10000).Property({toast.PROPERTY})"
check("the fragment reads window 10000 explicitly", qualified in FRAGMENT)
check("the player's copy reads window 10000 explicitly", qualified in PLAYER)
check("neither copy uses an unqualified lookup",
      f"Window.Property({toast.PROPERTY})" not in FRAGMENT
      and f"Window.Property({toast.PROPERTY})" not in PLAYER)


# 3. 8.9: "all toasts fade <300ms". Both directions, both copies.
def toast_block(xml):
    """The toast's own group. Anchored on the FIRST mention of the property,
    which is the group's <visible>, not the label 20 lines below it."""
    at = xml.find(qualified)
    return xml[max(0, at - 200):at + 1400]


BLOCKS = {"fragment": toast_block(FRAGMENT), "player": toast_block(PLAYER)}

for name, block in BLOCKS.items():
    times = [int(t) for t in re.findall(r'effect="fade"[^>]*time="(\d+)"', block)]
    check(f"{name}: has both a Visible and a Hidden fade", len(times) >= 2, str(times))
    check(f"{name}: every fade is under 8.9's 300ms",
          times and all(t < 300 for t in times), str(times))


# 4. Geometry and art must match between the two copies, or the toast moves
#    when the viewer crosses from Detail into the player.
for field, value in (("posx", fragments.TOAST_X), ("posy", fragments.TOAST_Y),
                     ("width", fragments.TOAST_W), ("height", fragments.TOAST_H)):
    check(f"the player's copy uses the fragment's {field} ({value})",
          f"<{field}>{value}</{field}>" in PLAYER)

capsule = f'capsule-h{fragments.TOAST_H}.png'
check("both copies use the same capsule",
      capsule in FRAGMENT and capsule in PLAYER, capsule)

# feedback_capsule_ninepatch_rule: the 9-patch border must be HALF the
# height, because gen_capsule_pill_assets bakes the radius at that figure.
# A mismatch ships visibly pinched caps.
border = fragments.TOAST_H // 2
check("the capsule's border is half its height, as the generator requires",
      f'border="{border}">{capsule}' in FRAGMENT
      and f'border="{border}">{capsule}' in PLAYER, str(border))


# 5. Adrian's accepted divergence: fixed width, and long text marquees
#    rather than truncating. Server error text has no known length.
for name, block in BLOCKS.items():
    check(f"{name}: long text marquees rather than truncating",
          "<scroll>true</scroll>" in block)
    # EM SPACES (U+2003), never ASCII. Kodi discards a text node that is only
    # ordinary whitespace, so a plain-space suffix arrives EMPTY and the
    # marquee's end runs straight into its own beginning. This shipped wrong
    # once in poster_card and again here, in the hand-written player copy.
    suffix = re.search(r"<scrollsuffix>(.*?)</scrollsuffix>", block)
    check(f"{name}: the marquee gap is EM SPACES, not ASCII",
          bool(suffix) and suffix.group(1).strip(" \t") != "" ,
          repr(suffix.group(1)) if suffix else "no scrollsuffix")


# 6. The windows that CALL toast.show must be the windows that render it.
#    A message raised by a window with no toast block sets a property
#    nobody draws, which is indistinguishable from a broken toast.
#    MainWindow carries it too, though nothing there raises one yet: a
#    message with no window to draw it is indistinguishable from a broken
#    toast, and Home/Browse/Discover/Search/Settings are where a viewer
#    spends most of their time.
for screen in ("main", "detail", "player"):
    rendered = (RENDERED / "script-tofa-{}.xml".format(screen)).read_text()
    check("the rendered {} window carries the toast".format(screen),
          qualified in rendered)

for module in ("windows/detail.py", "monitor.py"):
    src = (ROOT / "resources" / "lib" / module).read_text()
    check(f"{module} raises toasts through toast.show", "toast.show(" in src)
    check(f"{module} no longer raises a host notification",
          "Dialog().notification(" not in src)


# 7. The three sites that must KEEP Kodi's notification. Each fires when no
#    window of ours is up to draw anything: sign-in as its window closes,
#    switch_profile before any dialog exists, and kodigui's "Possibly broken
#    XML file", which fires precisely when our skin failed to load.
for module in ("signin.py", "windows/profile_select.py", "windows/kodigui.py"):
    src = (ROOT / "resources" / "lib" / module).read_text()
    check(f"{module} still falls back to Kodi's own notification",
          "notification(" in src)


print()
for label, ok, detail in RESULTS:
    print(("PASS  " if ok else "FAIL  ") + label + (f"   [{detail}]" if detail and not ok else ""))
failed = [r for r in RESULTS if not r[1]]
print()
print("=" * 60)
print(f"all {len(RESULTS)} checks passed" if not failed
      else f"{len(failed)} of {len(RESULTS)} checks FAILED")
raise SystemExit(1 if failed else 0)
