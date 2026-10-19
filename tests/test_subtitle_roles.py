"""Server 0.12.0's subtitle `role` (full, forced, commentary) in pick and label.

Tracks are shaped like live ones: forced tracks titled
"Forced" with the container flag off, and per-language commentary tracks.

Run:  python3 test_subtitle_roles.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import langcodes, tracks

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def sub(index, language, title, role=None, forced=False, sdh=False):
    return {"index": index, "language": language, "title": title,
            "codec": "subrip", "forced": forced, "sdh": sdh, "role": role}


# Forced by role only, listed first: the old flag-only rank picked it.
FORCED_BY_ROLE = [sub(3, "eng", "Forced", role="forced"),
                  sub(4, "eng", "English", role="full")]
picked = langcodes.first_subtitle_by_language(FORCED_BY_ROLE, ["eng"])
check("subtitles on: a role-forced track loses to the full one",
      picked["index"] == 4, str(picked))
picked = langcodes.forced_subtitle_for(FORCED_BY_ROLE, "eng")
check("subtitles off: the role-forced track is the forced pick",
      picked["index"] == 3, str(picked))

# Commentary first in the list, as on some discs.
COMMENTARY = [sub(5, "eng", "Commentary 1", role="commentary"),
              sub(6, "eng", "English SDH", role="full", sdh=True)]
picked = langcodes.first_subtitle_by_language(COMMENTARY, ["eng"])
check("subtitles on: commentary loses even to SDH",
      picked["index"] == 6, str(picked))
ONLY_COMMENTARY = [sub(5, "eng", "Commentary 1", role="commentary")]
picked = langcodes.first_subtitle_by_language(ONLY_COMMENTARY, ["eng"])
check("...but is still returned when it is all there is",
      picked is not None and picked["index"] == 5, str(picked))

# A commentary track titled "Forced commentary" must not pass as forced.
picked = langcodes.forced_subtitle_for(
    [sub(7, "eng", "Forced commentary", role="commentary")], "eng")
check("subtitles off: a commentary track is never the forced pick",
      picked is None, str(picked))

# No role at all (older payloads): the flag still decides.
picked = langcodes.first_subtitle_by_language(
    [sub(8, "ger", "Deutsch Forced", forced=True), sub(9, "ger", "Deutsch")],
    ["ger"])
check("no role: the forced flag alone still demotes",
      picked["index"] == 9, str(picked))

label, _ = tracks.subtitle_track_label(sub(3, "eng", "", role="forced"))
check("label: a role-forced track says Forced", "(Forced)" in label, label)
label, _ = tracks.subtitle_track_label(
    sub(5, "eng", "", role="commentary", sdh=True))
check("label: a commentary track says so, after SDH",
      label.endswith("(SDH, Commentary)"), label)
label, _ = tracks.subtitle_track_label(sub(4, "eng", "", role="full"))
check("label: a full track carries no flag", "(" not in label, label)

print("\n" + "=" * 60)
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
if failed:
    raise SystemExit(1)
