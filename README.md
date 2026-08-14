# tofa for Kodi

An unofficial Kodi client for the [tofa](https://tofa.tv) media server, in
two parts.

Under **Programs**, `tofa` opens a complete television interface: Home,
Browse, Discover, Search, title detail with cast and episodes, its own player
chrome, and Settings. Under **Video add-ons**, the same library appears as a
browsable source, so it also works in widgets, favourites and Kodi's own
containers. Both play through Kodi's native VideoPlayer, negotiating
DirectPlay/DirectFile so Dolby Vision, TrueHD/DTS-HD passthrough and
refresh-rate matching reach it untouched.

Unofficial means it is not a tofa product and carries no guarantee from them,
though it is built with the tofa team and against their design.

## Install

Add the repository once and Kodi keeps the add-on updated on its own:

1. Settings → File manager → Add source
   `https://cinema-one.github.io/tofa-for-kodi`
2. Settings → Add-ons → Install from zip file → that source →
   `repository.tofa/repository.tofa-1.0.0.zip`
3. Install from repository → tofa Add-on Repository → Video add-ons → tofa

A zip installed by hand works too and never updates itself, which is the
whole reason the repository exists.

**Requirements.** A tofa media server at **0.9.29** or newer -- older servers
are not refused, but this add-on carries no backward-compatibility paths, so
some screens will be missing or wrong rather than degrading gracefully. It
says so once per session when it sees one. `addon.xml` declares
`xbmc.python` 3.0.0, i.e. Kodi 19 and later; development and testing happen
on Kodi 21 and 22.

Everything a user needs to know beyond that -- transcoded audio, where
artwork is cached, what the add-on changes outside itself and why -- is in
[`plugin.video.tofa/README.txt`](plugin.video.tofa/README.txt), which ships
with the add-on.

## Layout

| | |
|---|---|
| `plugin.video.tofa/` | the add-on: everything that ships |
| `plugin.video.tofa/resources/lib/windows/` | the screen controllers |
| `plugin.video.tofa/resources/lib/skin/` | the skin **sources**; the XML under `resources/skins/Main/1080i/` is generated from them |
| `tests/` | every suite, each in its own process, no Kodi needed |
| `tools/` | asset generators, the release/publish tool, the checkers, and `kodictl.py` for driving a live Kodi |
| `art/logo-svgs/` | tofa's own fox logo sources, from which every shipped logo PNG is rendered |

Two things are worth knowing before reading much of it.

**The skin XML is generated.** Anything under
`plugin.video.tofa/resources/skins/Main/1080i/` is output. Edit
`resources/lib/skin/` and re-render; the `hash=` stamp at the top of each
generated file digests every skin input, so one source edit rotates the stamp
in all of them.

**`internal-docs/` is not here.** Comments across the code cite a design spec
by section ("9.4's fox tile") and occasionally an
`internal-docs/atv-reference/*.png` capture. Those are pointers into tofa's
internal TV design document and our reference captures, which are
confidential and live in a private sibling checkout. The section numbers are
kept because they are what makes the code navigable; nothing quoted from that
document survives in this repository, and `tools/check_public_set.py` is
what keeps it that way.

## Development

    pip install -r requirements-dev.txt
    python3 tests/run.py                        # every suite
    python3 tools/check_xml.py                  # every skin XML
    python3 -m compileall -q plugin.video.tofa

`CONTRIBUTING.md` has the rest: how to regenerate the skin, how to drive a
live Kodi from the shell, the numeric-formatting rules, and how a release is
cut and published.

## Licence and credits

GPL-2.0-only -- see [`LICENSE`](LICENSE). That licence is a condition of the
ported code credited below, not an independent choice.

This add-on owes a large debt to
[plex-for-kodi](https://github.com/plexinc/plex-for-kodi) (GPL-2.0) and to
pannal's [fork](https://github.com/pannal/plex-for-kodi). Kodi gives a Python
add-on no window framework of its own, and plex-for-kodi is the project that
solved that first; `resources/lib/windows/kodigui.py`, `background.py` and
`windowutils.py` are adapted from it, and each file's header records exactly
what was kept and what was dropped.

Icons are drawn from [Lucide](https://lucide.dev)'s own icon font (ISC, with
a subset under MIT). Inter Tight and Roboto Mono ship under the SIL Open Font
License. The full notices travel with the files they cover, under
`plugin.video.tofa/resources/skins/Main/`.

The fox marks and the tofa name are tofa's, used with their agreement.

This project is written with AI assistance, and says so rather than leaving
it to be inferred.
