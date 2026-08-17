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

### Install a version directly

A last resort, for when the repository can't be reached at all, or when you
need one specific version.

1. Download `plugin.video.tofa-<version>.zip` from https://tofa.cinemaone.ch
2. **Settings** → **System** → **Add-ons** → turn on **Unknown sources**.
   Kodi refuses to install from a zip without it, and only says so when you try
3. **Settings** → **Add-ons** → **Install from zip file** → choose the file

An add-on installed this way is pinned: Kodi only auto-updates add-ons it knows
came from a repository, so this copy will not update itself again. Reinstall it
from the repository when you want updates to resume.

## What doesn't work

These are the things worth trying first, and none of them help:

- **Restarting Kodi, or rebooting.** The time of the next check is stored in
  Kodi's database and survives both.
- **Disabling and re-enabling the tofa repository.** Kodi re-reads the same
  stored time and waits exactly as long as it was going to.
- **Uninstalling the add-on and reinstalling it from the repository.** Kodi
  installs from its *cached* copy of the add-on list, so you get the same
  version back. Refresh the repository first, with either of the first two
  methods above.
- **Changing the Updates setting and changing it back.**
