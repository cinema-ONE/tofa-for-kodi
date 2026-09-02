# Contributing

## Before you push

Four commands, all fast, none needing Kodi:

    python3 tests/run.py                        # every suite, each in its own process
    python3 tools/check_xml.py                  # every skin XML, generated and hand-written
    python3 tools/check_xml_comments.py         # the one XML rule Kodi will not tell you about
    python3 -m compileall -q plugin.video.tofa

And once per clone:

    git config core.hooksPath tools/hooks

That installs a pre-push hook running `check_public_set.py` in full -- about a
second and a half, and the only automatic home the QUOTE half has. CI cannot
run it: it compares this tree against tofa's confidential documents, which
must never reach a runner, so the workflow runs `--markers` alone. Without the
hook the quote gate is a manual check, and a manual check is one nobody runs
-- it went red from 2026-08-16 to 2026-08-29 with two comments quoting 13
tokens of the design document, which shipped in every release from 0.9.3 on.
Push is the last moment that prose is still ours; a public history is not
something a later edit can clean. `release.py publish` runs the same gate as
a backstop.

`check_xml.py` exists because each thing it catches is a SILENT failure: Kodi
does not reject them, log them, or draw anything that looks like an error --
it renders something subtly wrong, which is exactly what survives a
screenshot and reaches a box. `--` inside an XML comment is the recurring
one, and it is fatal: Kodi drops the whole file.

## The skin XML is generated

If you touched anything under `plugin.video.tofa/resources/lib/skin/`
(fragments, screens, templates, static, tokens), the XML in
`resources/skins/Main/1080i/` is an output and must be regenerated and
committed:

    cd plugin.video.tofa/resources && python3 -c \
      "import sys,os;sys.path.insert(0,os.getcwd());from lib.skin import build;build.render_all(force=True)"

Every generated file's `hash=` stamp digests all skin inputs, so ONE source
edit rotates the stamp in all of them. That is expected; `git diff | grep -v
'hash='` shows what actually changed. After merging two branches that both
regenerate XML, re-run the render and check `git status` is clean -- git can
merge the outputs textually without either side being current.

A running Kodi will not pick up a redeploy in a window it already has open.
Close the window, or restart Kodi, before believing a change did nothing.

## The design spec this follows

Comments across the code cite a design document by section ("9.4's fox tile")
and sometimes a reference capture (`internal-docs/atv-reference/*.png`).
**`internal-docs/` is a private sibling checkout and is not distributed.**
The tools that need it find that checkout by content rather than by name --
see `tools/checkouts.py`, and `TOFA_VAULT` if yours lives somewhere
unguessable. Without one, `check_public_set.py` refuses to pass rather than
reporting a clean run it never performed.
tofa's TV design document and our captures of the shipped apps are
confidential; the section numbers stay because they are what makes the code
navigable, and they are opaque on their own.

What may not travel is a private document's own prose -- the design document,
the vendored OpenAPI spec, or the API guide beside it.
`tools/check_public_set.py` enforces it: it indexes every 8-word run of each
source and slides the same window over everything in this repository, so a
comment that reproduces a sentence is caught rather than noticed. It sweeps
for private identifiers in the same pass -- hostnames, addresses, personal
details -- with IPv4 literals checked against an allowlist, since the address
that matters is the one nobody has typed yet.

Without the private checkout it has nothing to compare quotations against and
says so; the identifier half still runs, and is the half that matters here.

**Do not quote those documents, at any length.** Cite the section and say
what it requires in your own words: `8.4 caps the scroll at 460pt`, never
`8.4 says "max scroll 460pt"`. The checker's second half enforces it -- any
three-word phrase a comment puts in quotation marks that also appears in one
of tofa's documents fails the run. The eight-token half cannot see these; a
design instruction is four words and a number, which is how quoted spec
lines accumulated across the tree unnoticed until 2026-08-29.

Text the app puts on screen is not a quotation of theirs -- a comment has to
be able to name the row it is about -- and `QUOTED_ON_SCREEN` in the checker
lists those by name. Add to it deliberately, or not at all.

Where this client knowingly does something other than the spec or the shipped
apps, record it in the private `internal-docs/DIVERGENCES.md` as well as at
the code. Three reasons recur and are worth naming: **Kodi cannot** (a
platform limit, not a choice), **measured against the app** (the spec is
stated at another density or predates the app, and the app wins), and
**approved** (agreed with tofa or the repo owner).

## For the tofa team: graphical assets

- **Icons are GLYPHS, not images.** All sixteen are drawn from
  `resource.font.tofa/resources/tofa_lucide-icons.ttf`, built by
  `tools/lucide_font_src/`, through the `tofa_font_icons_*` roles. A new icon
  is a request for a glyph in that font, not a PNG -- an image would be the
  only icon in the app that does not scale with its text.
- **Artwork is PNG at 2x.** It goes in
  `plugin.video.tofa/resources/skins/Main/media/`, following the naming
  already there. Whole-scaled art ships at twice its drawn size; a 9-patch
  cannot, because the border would scale with it.
- **Most of it is generated.** Before adding a file by hand, check whether a
  `tools/gen_*.py` already draws it -- if one does, change the generator, not
  its output. `python3 tools/gen_logo_assets.py` renders all fourteen logos
  from `art/logo-svgs/`, which is why those sources are here.
- **Licensing**: `plugin.video.tofa` is GPL-2.0-only. Anything contributed
  into it is licensed the same way. If that is a problem for specific assets,
  say so before the PR rather than after.

## Architecture: keep the plain listings working

The add-on's plain directory-provider entry point -- no `action` parameter,
or the `continue`/`browse`/`discover`/`watchlist`/`search` actions in
`addon.py` -- must stay independently functional and reachable on its own. It
is what any Kodi skin other than the bundled window UI relies on, and what
the window UI itself is layered on top of via the separate `*_window`
actions. Do not fold the plain-listing behaviour into the window UI code, or
make it depend on it.

## Driving a live Kodi

`tools/kodictl.py` drives a local Kodi so a change can be verified on screen.
Its subcommands (`ready`, `restart`, `launch`, `state`, `press`, `info`,
`builtin`, `shot`, `log`) are documented in the file's docstring; three
things are worth knowing first:

- **Launch through the script entry.** `Addons.ExecuteAddon` on
  `plugin.video.tofa` resolves to the *pluginsource* entry point, i.e. the
  plain directory listing, never the window UI. `launch` goes through the
  companion `tools/script.tofa.harness` add-on to reach
  `RunScript(plugin.video.tofa)` instead -- the same door the Program add-ons
  tile uses. That add-on symlinks into Kodi's `addons/` directory and needs
  enabling once (`Addons.SetAddonEnabled`); it is a dev tool and is never
  shipped inside `plugin.video.tofa`.
- **`System.CurrentWindow` cannot identify a tofa screen.** Kodi resolves it
  through a localised-string lookup on the window id, so our screens come
  back as `"System"`, or as unrelated text like `"Immediate HDD spindown"`.
  Assert on `Window.Property(tofa_window)` instead -- `XMLBase.onInit` sets
  it to the screen's class name, and Kodi's own windows leave it empty.
- **Kodi's Python engine can wedge on cold boot.** Scripts log `start
  processing` and hang forever, and every later invocation queues behind
  them, while JSON-RPC, screenshots and Kodi's own UI all keep working -- so
  nothing looks broken except that the add-on never runs. `ready` and
  `restart` prove Python is alive by round-tripping a no-op through the
  harness before returning.

## Numbers, dates and times

Anything numeric that reaches the screen goes through
`resources/lib/regional.py`, which follows Kodi's own regional settings.
`python3 tools/check_numbers.py` guards it: it flags a hardcoded `strftime`
format and a float formatted to fixed decimals, and leaves everything else to
review, because deciding whether an integer is a count or a year needs intent
rather than syntax.

The trap is OVER-application, not under: a year must never be grouped
(`2,026`), nor a resolution (`1,920x1,080`), nor an episode number. Format by
ROLE, not by type:

| role | use | example |
|---|---|---|
| count | `regional.number()` | `10,738` / `10'738` |
| decimal | `regional.decimal(v, places)` | `42.0 GB` / `42,0 GB` |
| full date | `regional.date(iso)` | `08/04/2026` / `04.08.2026` |
| month + day | `regional.day_and_month(iso)` | `Aug 4` / `4. Aug` |
| time of day | `regional.clock()` | `11:09 AM` / `23:09` |
| year, resolution, episode no., % | leave alone | `2026`, `1920x1080` |

Kodi does not expose the separators to add-ons at all -- `regional.py`'s
docstring explains where it digs them out of and why `locale` cannot be used.

## Cutting a release

`tools/release.py` owns the version, the changelog, the zip and the update
site:

```
python3 tools/release.py show      # current version
python3 tools/release.py check     # version valid? changelog and <news> agree?
python3 tools/release.py set X.Y.Z # bump (validates, then syncs <news>)
python3 tools/release.py package   # dist/plugin.video.tofa-X.Y.Z.zip
python3 tools/release.py publish   # dist/repo/, the tree Kodi updates from
```

The version lives in `plugin.video.tofa/addon.xml` and nowhere else -- it is
the one thing Kodi compares to decide an update exists. `changelog.txt` owns
the prose, and `addon.xml`'s `<news>` (what Kodi shows as the changelog) is
derived from its newest entry, so write the entry *before* bumping.

**Kodi compares versions with Debian rules, not semver.** The trap worth
knowing: `0.9.0-beta1` is a Debian *revision* and sorts **above** `0.9.0`, so
a beta tagged that way is never superseded by the real release. A
pre-release is spelled `0.9.0~beta1` -- `~` sorts below everything, including
end-of-string. `set` refuses anything that does not sort strictly above the
current version, so this is caught before it ships rather than on a user's
box.

### Publishing

`publish` builds `dist/repo/` and reads it back the way Kodi will, reporting
what would break. Copy that tree into `docs/` on `main` and GitHub Pages
serves it at `https://tofa.cinemaone.ch`, which is `release.py`'s `BASE_URL`.

**`rm -rf dist/repo` first.** `publish` creates its output directory but
never clears it, so the previous version's zip is still sitting there from
the last release. Sync that as-is and the channel serves a 9MB orphan
alongside the current version, carried in git for good. Caught on 0.9.4, one
step before it shipped.

**Leave `repository.tofa`'s zip alone unless its version moved.** Rebuilding
it produces entries that are byte-for-byte identical -- every CRC matches --
with different embedded timestamps, so committing it changes the bytes of an
already-published version for nothing. Restore both copies and the `.sha256`
from `HEAD` before committing. This is the same rule `publish` enforces for
the add-on when it refuses to republish a version whose contents changed.

That hostname is a DNS `CNAME` onto `cinema-one.github.io`; the bits still
come from Pages out of `docs/`. What binds the name to THIS repository is the
`CNAME` file in the served tree, which `publish` writes from `BASE_URL` --
Pages cannot tell repos apart by DNS, since every custom subdomain points at
the same `cinema-one.github.io`. Publishing a tree without that file unbinds
the domain and takes the channel down for every install, so `publish` refuses
to call a tree good if it is missing or names another host.

That URL is baked into the repository add-on users install, so changing it
means every existing user has to remove and re-add the repository. If it ever
does change, bump `REPO_VERSION` in the same commit: existing installs update
themselves from the OLD url, so a URL change reaches them exactly once, and
only if the version moved.

### Development increments vs versions that ship

Only the second kind gets a tag.

**Working towards a release.** Commit freely on a branch. Bump `addon.xml` as
soon as you know which version the work is heading for -- from then on the
number just means "working towards 0.9.0". Nothing is tagged; the version in
`addon.xml` is a destination, not a claim.

**A version that could ship.** Merge to `main`, then tag `v<version>` on the
resulting `main` commit -- the one whose tree the zip is actually built from.
Not the commit that bumps `addon.xml`: that is where the number changed, not
where the release is. 0.9.0's bump landed three commits before its branch was
done, so a tag there would have pointed at a tree missing a third of it.

Tagging is cheap and does not promise anything shipped. Tag when a version is
*potentially* shippable; if hardware testing then turns up a problem, fix it
and release 0.9.1.

**If a version was published more than once, tag what shipped LAST.** A tag
should identify the tree users actually ran. 0.9.3 went out four times in one
day under the same version string with different bytes each time, so the
publish PR's merge points at a zip nobody ended up with. Find the right
commit with:

```
git log -- docs/plugin.video.tofa/plugin.video.tofa-<version>.zip
```

`publish` now refuses to republish a version whose contents changed, so this
should not recur -- but the tags from before that guard need reading this way.

### The server version floor

`tools/release.py server <v>` sets `MIN_SERVER_VERSION` and the requirement
line in `plugin.video.tofa/README.txt` together, and `release.py check`
compares both against the vendored OpenAPI spec next door. The rule the check
enforces: **the vendored spec may LAG the floor but never LEAD it** -- a spec
newer than the version the client claims means holding a contract we do not
say we support, and `do_package()` refuses to build while it fails.

**The tool does NOT touch the top-level `README.md`**, which states the same
requirement in prose, and `check` does not compare it either -- so it drifts
silently. Update it by hand after every bump.

Bump the floor **with the feature that needs it, in the same commit**, and
remember the changelog: a floor bump is user-visible.

### Reissuing a published version

Sometimes a shipped version needs replacing without a new number -- 0.9.10 went
out with wording in its notes that had to go. `publish` refuses that by
default, and says so precisely:

```
PROBLEM: plugin.video.tofa-0.9.10.zip is already published with DIFFERENT
contents (16 file(s): ...). Bump the version, or pass --republish if
replacing it is deliberate.
```

It names every changed file before doing anything, which is worth reading --
if the list is longer than you expected, the reissue is not what you thought
it was. `--republish` is the deliberate override.

**Decide first whether it is worth it, because a reissue does not reach anyone
already on that version.** Kodi will not reinstall an unchanged version
string, so a reissue fixes new installs and the channel only. If the change
matters for people who already have it, burn the next version number instead.

The rest of the publish procedure is unchanged, plus three things:

1. **Only that version's artefacts may move.** Check `git status docs/` before
   committing: the zip, its `.sha256`, its `changelog-<v>.txt` and
   `addons.xml`. The other versions carried forward must come back untouched.
2. **Move the tag to the reissue's publish merge.** Same rule as `v0.9.3`
   above -- a republished version's tag points at what shipped LAST.
   `git tag -f -a v<v> <merge> && git push --force origin v<v>`.
3. **Replace the release asset**, or the page still offers the old bytes:
   `gh release upload v<v> docs/plugin.video.tofa/plugin.video.tofa-<v>.zip --clobber`.

Then verify over the wire as usual. The served zip's sha256 will have changed;
that is the point.

**A GitHub Release is titled with the bare version** (`0.9.4`), not
`tofa for Kodi 0.9.4`: the page already shows the repository name above the
list and the tag beside each row. Nothing reads the title -- Kodi installs
from `addons.xml` and never sees the releases page.

**Attach the add-on zip to every release.** The channel only serves the
handful of versions `publish` keeps (`--keep`, default 3), so the releases
page is the archive of record for everything older, and the only copy anyone
outside the project can reach. Create the release with the zip in the same
command, so it cannot be forgotten:

```
gh release create v<version> --verify-tag --title "<version>" \
    --notes-file <notes> docs/plugin.video.tofa/plugin.video.tofa-<version>.zip
```

This was not done consistently: of the first eight releases only three
carried the zip, and the five that did not included the two most recent --
exactly the ones a rollback would want. They were backfilled on 2026-08-18
from each tag's own tree, every one matching the sha256 recorded when it was
published. Attach only the add-on zip; `repository.tofa`'s is identical on
every release and would just repeat itself.

Merges to `main` keep their history (`--ff-only`, or `--no-ff` if `main` has
moved on). Do not squash: the commit messages here carry reasoning that is
recorded nowhere else, and squashing throws it away.

## For everyone else

Open an issue or a PR. There is no formal process beyond that yet.
