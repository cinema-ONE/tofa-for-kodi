Reference copy of Lucide's own prebuilt icon-font codepoint map, from the
`lucide-static` npm package (published artifact, not committed to Lucide's
own git repo -- generated at their publish time), fetched via jsDelivr:

    https://cdn.jsdelivr.net/npm/lucide-static@1.27.0/font/codepoints.json
    https://cdn.jsdelivr.net/npm/lucide-static@1.27.0/font/lucide.ttf

Pinned to **1.27.0** for reproducibility -- don't fetch `@latest`, codepoint
assignments can shift between releases as icons are added/removed.

The actual font file used at runtime lives at
`plugin.video.tofa/resources/skins/Main/fonts/lucide-icons.ttf` (shipped
with the add-on, registered via `resources/lib/fontinstall.py`). This
`codepoints.json` is dev-reference only, for looking up a new icon's
codepoint when adding one -- see `resources/lib/skin/icon_glyphs.py` for
the small subset actually wired into the UI.

License: ISC (see `plugin.video.tofa/resources/skins/Main/media/
LUCIDE_LICENSE.txt`), same as the SVG-derived PNG icons in
`tools/lucide_src/`.
