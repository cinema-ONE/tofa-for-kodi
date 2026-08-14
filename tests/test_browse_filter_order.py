"""Browse's Filter panel is positional in three places. Keep them in step.

`playoptions.show_sections` returns "the chosen index per section, in order",
so `_browse_filter_clicked` unpacks its result POSITIONALLY:

    sections = [watched, quality, year]
    watched_choice, quality_choice, year_choice = picked

Reorder the sections without moving the unpacking and nothing raises. The
panel simply writes the Year choice into the Format filter and vice versa --
a wrong grid, no traceback, no log line. The third place is
`_browse_filter_label`, which promises the pill lists axes "in the order the
dialog asks about them"; if it drifts, a truncated line drops the wrong end.

Checked statically, by reading main.py: the real thing needs a Kodi window,
and what is worth guarding here is the correspondence between three literal
orderings, which is exactly what source reading can see.

Run:  python3 test_browse_filter_order.py
"""
import pathlib
import re

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


SRC = (pathlib.Path(__file__).resolve().parent.parent
       / "plugin.video.tofa" / "resources" / "lib" / "windows" / "main.py").read_text()


def _body(func_name):
    """The source of one method, up to the next def at the same indent."""
    m = re.search(r"\n    def %s\(.*?\n(.*?)(?=\n    def )" % re.escape(func_name),
                  SRC, re.S)
    return m.group(1) if m else ""


open_filter = _body("_browse_filter_clicked")
label = _body("_browse_filter_label")

check("_browse_filter_clicked was found in main.py", bool(open_filter))
check("_browse_filter_label was found in main.py", bool(label))

# 1. The section list, in the order the panel shows them.
section_keys = re.findall(r'\{"key": "(\w+)", "title": "([^"]+)"', open_filter)
keys = [k for k, _t in section_keys]
titles = {k: t for k, t in section_keys}
check("three sections are declared", len(keys) == 3, str(keys))

# 2. The positional unpacking of show_sections' result.
unpack = re.search(r"\n\s*(\w+_choice,\s*\w+_choice,\s*\w+_choice)\s*=\s*picked", open_filter)
check("the result is unpacked positionally", bool(unpack))
unpacked = [v.strip().removesuffix("_choice") for v in unpack.group(1).split(",")] if unpack else []

# The one that matters: sections[i] must be what choice[i] is stored into.
# Guarded against passing VACUOUSLY -- if either regex stops matching (a
# rename, a reformat), [] == [] would otherwise read as agreement, which is
# the failure mode a static check is most prone to.
check("THE SWAP GUARD: unpacking order == section order",
      bool(keys) and bool(unpacked) and unpacked == keys,
      f"sections={keys} unpack={unpacked}")

# 3. The pill's own ordering, read off which index each branch tests.
IDX_TO_KEY = {"_browse_watched_idx": "watched",
              "_browse_quality_idx": "quality",
              "_browse_year_idx": "year"}
label_order = [IDX_TO_KEY[m] for m in re.findall(r"self\.(_browse_\w+_idx) != 0", label)
               if m in IDX_TO_KEY]
check("the pill names every axis the panel asks about",
      sorted(label_order) == sorted(keys), f"label={label_order} sections={keys}")
check("the pill lists them in the panel's order (its docstring promises this)",
      label_order == keys, f"label={label_order} sections={keys}")

# 4. The rename that started this, so it cannot quietly regress.
check('the format axis is TITLED "Format" (the player already owns "Quality")',
      titles.get("quality") == "Format", str(titles))
check("...while still sending the server's own `quality` field",
      "quality" in keys and 'params["quality"]' in SRC, str(keys))

# 5. The agreed order itself.
check("order is Watch Status, Format, Year",
      keys == ["watched", "quality", "year"], str(keys))

# 6. The value-less pills name themselves rather than showing a bare "All".
check('unfiltered Filter reads "Filter"', 'else "Filter"' in label)
check('unpicked Genre reads "Genre"', 'else "Genre"' in _body("_browse_genre_label"))

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
