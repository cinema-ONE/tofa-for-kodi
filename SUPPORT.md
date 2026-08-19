# Support

Problems, questions and bug reports all go to the
[issue tracker](https://github.com/cinema-ONE/tofa-for-kodi/issues). Please say
which version of the add-on and of Kodi you are on, and which platform -- the
add-on version is under Settings → Add-ons → My add-ons → Video add-ons →
**tofa for Kodi**.

## Getting a new release

Kodi checks its repositories on a timer, not when you open the add-on, so a
newly published version does not appear the moment it goes out. Our channel
asks to be re-checked once a day; Kodi's own repository asks more often, and
whenever either one falls due Kodi checks them all. In practice a new release
is usually picked up within a few hours, and at worst within a day.

The wait is recorded in Kodi's database rather than in memory, which is why
the obvious remedies below do nothing.

### Check for updates

The quickest way, and it changes no settings.

1. **Settings** → **Add-ons** → **My add-ons** → **Add-on repository**
2. Highlight **tofa Add-on Repository**. Highlight it -- don't open it, or the
   menu item won't be the one you want
3. Open the context menu: `C` on a keyboard, the Menu button on a remote, or
   press and hold on a touchscreen
4. Choose **Check for updates**

Kodi fetches the add-on list straight away. If Updates is set to "Install
updates automatically", which is the default, the new version installs itself
within a few seconds and the add-on restarts.

If updates are set to notify, or not to install, finish the job by hand:
**Settings** → **Add-ons** → **My add-ons** → **Video add-ons** →
**tofa for Kodi** → **Update**.

### Reinstall the repository

Use this if the step above finds nothing when you are certain there is
something to find. Uninstalling the repository discards the stored check time
along with Kodi's cached copy of the add-on list, so the reinstall starts over.

1. **Settings** → **Add-ons** → **My add-ons** → **Add-on repository** →
   **tofa Add-on Repository**
2. **Uninstall**, and confirm
3. Install it again from https://tofa.cinemaone.ch, as in the README's install
   steps

This removes only the repository, not the add-on: your sign-in and settings are
untouched, and tofa for Kodi keeps working throughout.

### Go back to an earlier version

The repository carries the **three most recent versions** -- the current one
and the two before it -- so you can go back without hunting for a zip.

1. **Settings** → **Add-ons** → **My add-ons** → **Video add-ons** → **tofa**
2. Choose **Versions**, and pick the one you want

Two things to know about that button. It is **hidden while an update is
waiting**: Kodi shows **Update** in its place, so install or dismiss the update
first if you cannot see it. And going back this way keeps the add-on's
**Origin** as the repository, so Kodi will offer to update it again later --
unlike installing a zip by hand, which pins it.

Once a version is four releases old it leaves the repository. If you need one
older than that, every release from 0.9.2 onwards has its zip attached at
https://github.com/cinema-ONE/tofa-for-kodi/releases -- install that with
**Install from zip file** below.

### Install a version directly

A last resort, for when the repository can't be reached at all, or when you
need one specific version.

1. Download `plugin.video.tofa-<version>.zip` from https://tofa.cinemaone.ch
2. **Settings** → **System** → **Add-ons** → turn on **Unknown sources**.
   Kodi refuses to install from a zip without it, and only says so when you try
3. **Settings** → **Add-ons** → **Install from zip file** → choose the file

An add-on installed this way is pinned: Kodi only auto-updates add-ons it knows
came from a repository, so this copy will not update itself again. Reinstall it
from the repository when you want updates to resume. You can tell the two apart
at a glance -- the add-on's information page shows **Origin: Manual** for a zip
install, and **Origin: tofa Add-on Repository** for one Kodi is keeping current.

**Keep a repository installed even if you install by hand.** The zip does not
bundle the Python modules the add-on needs -- `requests`, and the `certifi`,
`chardet`, `idna` and `urllib3` modules beneath it -- so Kodi fetches those from
a repository as it installs. With no repository available and nothing in Kodi's
package cache, the install fails on its dependencies.

## What doesn't work

These are the things worth trying first, and none of them help:

- **Restarting Kodi, or rebooting.** The time of the next check is stored in
  Kodi's database and survives both.
- **Disabling and re-enabling the tofa repository.** Kodi re-reads the same
  stored time and waits exactly as long as it was going to.
- **Uninstalling the add-on and reinstalling it from the repository.** Kodi
  installs from its *cached* copy of the add-on list, so you get the same
  version back. Refresh the repository first, with either of the first two
  methods above -- and see below before uninstalling anything.
- **Changing the Updates setting and changing it back.**

## Reinstalling without losing your sign-in

Everything the add-on stores -- your server pairing, the selected profile and
your settings -- lives in Kodi's `addon_data` folder, separately from the add-on
itself. So it survives a reinstall, with one exception worth knowing about.

**To move to a new version by hand, install the new zip straight over the old
one.** There is no need to uninstall first. Kodi treats it as an update, asks
nothing, and nothing is lost.

**If you do uninstall, Kodi asks a second question** after "Are you sure?":

> Would you also like to remove all related data (e.g. settings) of this add-on?

Answer **No** -- which is what it offers by default -- and everything is kept;
reinstalling picks your sign-in and settings straight back up. Answer **Yes**
and that folder is deleted: despite the wording mentioning only settings, your
server pairing and profile go with it, and the next install starts as a new
device that has to be paired again.

Uninstalling also removes the shared Python modules described above, as nothing
else is using them any more. They come back with the next install, provided a
repository is still available to supply them.
