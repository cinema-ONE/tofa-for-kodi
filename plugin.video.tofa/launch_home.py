#!/usr/bin/env python3
"""Script entry point for the window UI (brief §2, §9).

Registered as a second `xbmc.python.script` extension point in addon.xml,
alongside the primary `xbmc.python.pluginsource` one. Mirrors how
plex-for-kodi (script.plexmod) actually launches its window UI: a
dedicated Program/Script extension point that opens the main window
directly, with no plugin:// directory-listing step involved -- that's
the piece the ported window framework didn't bring with it, which is why
launching the add-on normally (Program/Video add-ons) previously only
ever reached the plain directory listing (brief §9's guardrail -- still
true and unaffected by this: that route stays the default, this is a
separate, additional door into the window UI, not a replacement of it).

The plugin:// ?action=home_window route (addon.py:action_home_window)
still exists too, for anything that wants to link directly into the
window UI (e.g. a Favourite) without going through this script entry.
"""
from __future__ import annotations

from resources.lib import artcache, http, prefetch, stereoscopic
from resources.lib.windows import splash

# The splash goes up FIRST, before the heavy imports below. main.py is the
# largest module in the add-on and importing it (plus cards, theme, kodigui,
# navbar, settings_pages...) is real time on the box: measured on a cold
# launch, Kodi's own Favourites window was still on screen 1.4s after the
# keypress, and that was the import, not the animation. Nothing can cover
# that gap except getting the splash up before paying for it.
#
# Whenever one is not already up -- see splash.py. NOT once per Kodi run: the
# splash is what covers the window build, and the second launch of a Kodi run
# needs covering exactly as much as the first.
splash.ensure_up()

from resources.lib.windows.main import MainWindow

# The splash returns AT ONCE, so the fetching below runs while its animation
# plays instead of after it; wait_out() then lets the animation finish before
# the real window covers it. Opening MainWindow before that would cut the
# wipe off mid-frame.
prefetch.warm()
splash.wait_out()
splash.hand_over()

# hand_over(), NOT dismiss(). Opening MainWindow is itself what takes the
# splash down -- Kodi deinits it and pushes the new window into its place --
# so there is nothing to close and no gap. dismiss() here instead closed the
# splash while the window was still being built, which put Kodi's own menu
# back on screen. Measured cold on the box: splash gone 3.94s, Favourites
# visible again 4.75s, MainWindow 4.99s. That ~0.8s IS the reported flash.
#
# Closing it AFTER open() is not the answer either -- that closes whatever is
# current, i.e. the app (see splash.dismiss()'s docstring, and
# project_kodi_double_close_trap).

# Still-playing video outranks any remembered section. Kodi's Home button
# does not CLOSE our player, it activates another window over it: the player
# stays alive, parked in its modal wait with all its state. So coming back
# into the add-on raises that window again rather than building a new one.
# Kodi's own menu has a button for this too; this makes relaunching the
# add-on do the same thing.
#
# Imported HERE, not at module scope: player.py is the heaviest window in
# the add-on and every launch would pay for it, including the overwhelming
# majority that go straight to a browsing screen.
from resources.lib.windows.player import PlayerWindow

# `finally`, for the launch that never gets far enough for Kodi to replace the
# splash: not signed in, profile gate cancelled, or an outright throw. Being
# stuck behind a splash that swallows Back is far worse than the flash this
# change removes. A no-op on every normal launch, since hand_over() has
# already given up the reference.
try:
    if PlayerWindow.reactivate_if_backgrounded():
        pass
    else:
        # Come back where you left off. Pressing Kodi's Home button mid-browse and
        # relaunching used to land on the Home section regardless of where you
        # were; the section is remembered for the life of this Kodi run
        # (MainWindow.LAST_SECTION_PROPERTY). A fresh Kodi start has nothing
        # remembered and opens on Home as before.
        target = MainWindow.remembered_target()
        MainWindow.open(start_target=target) if target else MainWindow.open()

        # A profile switch closes the window and asks for a new one, rather
        # than trying to make the old one forget the previous viewer (see
        # MainWindow.request_restart). Looped here rather than respawned as
        # a fresh RunScript: Kodi serialises script invocations, so a script
        # that relaunches itself queues behind its own exit.
        #
        while MainWindow.take_restart_request():
            # The splash beneath is what covers this, and it is beneath
            # because ensure_up() put one there on EVERY launch, not only the
            # first of a Kodi run. That is the whole fix: closing the window
            # walks Kodi back to the splash rather than to its own Home.
            #
            # arm_for_restart() is what stops that walk-back being read as
            # "the app exited" -- _settings_switch_profile has already called
            # it, and calling it again keeps this loop true whatever asked for
            # the restart. ensure_up() then covers the case where the splash
            # somehow is not there after all (a launch whose show failed), and
            # is a no-op in the normal one.
            splash.arm_for_restart()
            splash.ensure_up()
            prefetch.warm()
            # Let the wipe finish, exactly as the cold path does. Without it
            # the new window opened the moment the fetching was done and cut
            # the animation off mid-sweep -- on a warm switch that is well
            # under a second, so the splash appeared, twitched, and vanished.
            splash.wait_out()
            splash.hand_over()
            # No remembered target: a switch lands on Home, deliberately.
            MainWindow.open()
finally:
    # A no-op on the normal path (hand_over cleared it); this only
    # fires if the open above threw before Kodi could replace the
    # splash, where an unclosable splash would be the worse failure.
    splash.dismiss()
    # A playback that never closed cleanly (a crash, a force-quit) can
    # leave Kodi's stereoscopic prompt suppressed for good. Put it back.
    stereoscopic.restore_stale()
    # ...and forget any splash this process owned. Kodi destroys the windows
    # an interpreter created when that interpreter is torn down, so once this
    # script ends there is no splash anywhere -- whatever the flag says. Not
    # doing this is what left every profile switch rebuilding the app over
    # Kodi's own Home; see splash.release().
    splash.release()
    # The window has closed, so the script is about to end. Tell artcache's
    # background workers to stop parking in their queue: an idle worker is a
    # thread Kodi's CPythonInvoker waits 5s for and then force-kills, which is
    # what wedged Kodi's quit on 2026-08-07. A Kodi shutdown is caught by the
    # workers themselves; this is the clean exit for a plain add-on close.
    artcache.stop()
    # Hand the pooled connections back too. A session has no destructor that
    # does it, and this interpreter is torn down inside a kodi.bin that goes
    # on running for days -- so a socket the server has since FIN'd sits in
    # CLOSE_WAIT until Kodi itself exits. See http.close_all().
    http.close_all()
