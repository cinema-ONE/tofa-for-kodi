"""Settings' left column has words for every row, and its choices match.

The marked choice is found by comparing the row's live label with the
panel's option labels, so the two lists must agree word for word.

Run:  python3 test_settings_info.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import settings_info, settings_options, settings_pages
from resources.lib.windows.main import MainWindow

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


segment_labels = {
    "rating": [l for l, _v in MainWindow.SETTINGS_RATING_SEGMENTS],
    "quality": [l for l, _v in MainWindow.SETTINGS_QUALITY_SEGMENTS],
    "nextup": [l for _v, l in settings_options.AUTO_PLAY_NEXT_ACTIONS],
    "nextupstyle": [l for _v, l in settings_options.NEXT_UP_STYLES],
}
for key, _lid, _p in settings_options.CHOICE_ROWS:
    info = settings_info.ROWS.get(key)
    check(f"{key}: has words", info is not None)
    if info is None:
        continue
    want = segment_labels.get(key) or [l for _v, l in settings_options.SEGMENT_ACTIONS]
    got = [l for l, _d in info.options]
    check(f"{key}: choices match the row's labels", got == want, f"{got} != {want}")
    check(f"{key}: no more choices than the panel draws",
          len(got) <= settings_info.MAX_OPTIONS)

for cid, key in MainWindow.SETTINGS_INFO_KEYS.items():
    check(f"{cid} ({key}) has words", key in settings_info.ROWS)

check("every tab has a summary",
      all(p.key in settings_info.SUMMARIES for p in settings_pages.PAGES))
check("no summary is longer than the panel draws",
      all(len(r) <= settings_info.MAX_SUMMARY for r in settings_info.SUMMARIES.values()))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"settings info: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
import sys
sys.exit(1 if failed else 0)
