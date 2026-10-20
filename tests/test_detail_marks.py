"""Seen it and Not interested as pills on a title the library does not hold (app 2.1.0).

Run:  python3 test_detail_marks.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib.windows.detail import DetailWindow

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))


class Client:
    def __init__(self):
        self.calls = []

    def set_seen(self, media_type, tmdb_id, on):
        self.calls.append(("seen", media_type, tmdb_id, on))

    def set_not_interested(self, media_type, tmdb_id, on):
        self.calls.append(("not_interested", media_type, tmdb_id, on))


class Fake:
    _sync_mark_pills = DetailWindow._sync_mark_pills
    _toggle_mark = DetailWindow._toggle_mark
    PILL_SEEN, PILL_NOT_INTERESTED = DetailWindow.PILL_SEEN, DetailWindow.PILL_NOT_INTERESTED

    def __init__(self, marks):
        self._marks, self.props, self.client = marks, {}, Client()
        self.content_media_type, self.tmdb_id = "movie", 42

    def setProperty(self, k, v):
        self.props[k] = v

    def getProperty(self, k):
        return self.props.get(k, "")

    def _get_client(self):
        return self.client


w = Fake({"seen": False, "not_interested": False})
w._sync_mark_pills()
check("both pills show when the server says where the title stands",
      w.props["show_seen"] == "1" and w.props["show_not_interested"] == "1")
check("unset, in the app's words", (w.props["seen_label"], w.props["not_interested_label"])
      == ("Seen it", "Not interested"))
w._toggle_mark(True)
check("Seen it marks the title by TMDB id", w.client.calls == [("seen", "movie", 42, True)],
      str(w.client.calls))
check("...and the pill reads Seen, with the filled glyph",
      w.props["seen_label"] == "Seen" and w.props["seen_glyph"] == chr(0xF8E0))
w._toggle_mark(True)
check("choosing it again clears it", w.client.calls[-1] == ("seen", "movie", 42, False)
      and w.props["seen_label"] == "Seen it")
w._toggle_mark(False)
check("Not interested reads Hidden from suggestions once set",
      w.client.calls[-1] == ("not_interested", "movie", 42, True)
      and w.props["not_interested_label"] == "Hidden from suggestions")

quiet = Fake({})
quiet._sync_mark_pills()
check("no flags from the server, no pills", quiet.props["show_seen"] == ""
      and quiet.props["show_not_interested"] == "")
check("the two pills are packed with the others",
      {DetailWindow.PILL_SEEN, DetailWindow.PILL_NOT_INTERESTED} <= set(DetailWindow.PILL_LAYOUT))

failed = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
raise SystemExit(1 if failed else 0)
