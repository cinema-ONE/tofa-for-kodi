"""The options panel over sections it did NOT build.

Callers may hand the panel their own section model, and their keys are their
own namespace. Browse's Filter legitimately titles a section "Quality" and
keyed it "quality", which is also this module's QUALITY constant -- so the
panel ran its transcode branch over option dicts that carry only a label,
raised KeyError 'is_original' one line before the collapse, and left that
one section stuck open while its neighbours closed.

Run:  python3 test_playoptions_sections.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows import playoptions
from resources.lib.windows.playoptions import PlaybackOptionsDialog

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


class FakeList(list):
    """The handful of ManagedControlList calls _rebuild makes."""
    def __init__(self):
        super().__init__()
        self.selected = 0

    def reset(self):
        del self[:]

    def addItems(self, items):
        self.extend(items)

    def selectItem(self, pos):
        self.selected = pos

    def getSelectedPosition(self):
        return self.selected


class FakeDialog(PlaybackOptionsDialog):
    """Drives onClick/_rebuild without Kodi: the real methods, stub chrome."""
    def __init__(self, sections=None, info=None):
        self._title = "t"
        self._subtitle = ""
        self._info = info or {}
        self.selection = playoptions.Selection()
        self._flat_rows = None
        self._flat_selected = 0
        self._custom_sections = sections
        self._hint_text = "caller hint"
        self._audio_languages = None
        self.picked_idx = None
        self._sections = sections if sections is not None else playoptions.build_sections(
            self._info, self.selection, None)
        self.sections = self._sections
        self._derived_sections = (self._flat_rows is None
                                  and self._custom_sections is None)
        self._expanded = None
        self._model = []
        self.props = {}
        self.option_list = FakeList()

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, "")

    def _resize(self, row_count):
        pass

    def click_row(self, index):
        self.option_list.selected = index
        self.onClick(playoptions.LIST_ID)


FILTER_SECTIONS = [
    {"key": "watched", "title": "Watch Status",
     "options": [{"label": "All", "detail": ""}, {"label": "Unwatched", "detail": ""}],
     "selected": 0},
    {"key": "quality", "title": "Quality",
     "options": [{"label": "Any", "detail": ""}, {"label": "4K", "detail": ""}],
     "selected": 0},
]

INFO = {
    "quality_tiers": [
        {"tag": None, "bitrate_kbps": 0, "is_original": True},
        {"tag": "1080p", "bitrate_kbps": 8000, "is_original": False},
    ],
    "play_method": "DirectPlay",
}


def collapses(section_key, sections=None, info=None):
    """Expand `section_key`, pick its second option, report whether the
    panel collapsed back to headers."""
    d = FakeDialog(sections=sections, info=info)
    d._rebuild()
    header_row = d._model.index((section_key, None))
    d.click_row(header_row)                       # expand
    expanded_ok = d._expanded == section_key
    option_row = d._model.index((section_key, 1))
    d.click_row(option_row)                       # pick
    return expanded_ok, d._expanded is None, d._sections


# --- caller-supplied sections: keys are the caller's, not ours -------------
opened, closed, secs = collapses("quality", sections=FILTER_SECTIONS)
check("caller's 'quality' section expands", opened)
check("caller's 'quality' section COLLAPSES on pick", closed)
check("caller's pick is recorded for read-back",
      secs[1]["selected"] == 1, f"selected={secs[1]['selected']}")

opened, closed, _ = collapses("watched", sections=FILTER_SECTIONS)
check("caller's other sections still collapse", opened and closed)

d = FakeDialog(sections=FILTER_SECTIONS)
d._rebuild()
check("caller's own hint text is kept",
      d.getProperty("options_hint") == "caller hint",
      repr(d.getProperty("options_hint")))

# --- the real, info-derived panel still applies its Selection --------------
d = FakeDialog(info=INFO)
d._rebuild()
d.click_row(d._model.index((playoptions.QUALITY, None)))
d.click_row(d._model.index((playoptions.QUALITY, 1)))
check("derived quality section collapses", d._expanded is None)
check("derived quality section applies the tier",
      d.selection.quality_tag == "1080p" and d.selection.max_bitrate == 8000,
      repr(d.selection))
check("derived panel derives its own hint",
      d.getProperty("options_hint").startswith("Transcoded to"),
      repr(d.getProperty("options_hint")))

d = FakeDialog(info=INFO)
d._rebuild()
d.click_row(d._model.index((playoptions.QUALITY, None)))
d.click_row(d._model.index((playoptions.QUALITY, 0)))
check("Original clears the constraint",
      d.selection.quality_tag is None and d.selection.max_bitrate is None,
      repr(d.selection))

print(f"\n{sum(1 for _, ok in RESULTS if ok)}/{len(RESULTS)} passed")
raise SystemExit(0 if all(ok for _, ok in RESULTS) else 1)
