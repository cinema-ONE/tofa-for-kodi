# -*- coding: utf-8 -*-
"""Adapted from plex-for-kodi (https://github.com/plexinc/plex-for-kodi), GPL-2.0.

Source: lib/windows/windowutils.py. Ported: GoHomeMixin, UtilMixin (minus
`openItem`), shutdownHome().

Dropped two pieces as genuinely Plex-domain, not framework:
- `getNextShowEp` (up-next episode picker + its resume/play-from-beginning
  dropdown prompt) -- Plex playlist/episode object logic. Port later
  alongside episode browsing if/when this add-on grows a custom episodes
  window.
- `UtilMixin.openItem` -- routed through plex-for-kodi's `opener.py`, which
  dispatches on `obj.TYPE` (`movie`/`show`/`episode`/`playlist`/...) against
  `plexnet` model objects fetched straight from a PMS. That's deep coupling
  to Plex's data layer, not a cosmetic reference, so it isn't ported; the
  MVP window controller (home.py) opens plugin:// URLs via
  `xbmc.executebuiltin('ActivateWindow(...))` / `Container.Update` instead,
  same as the existing directory-provider add-on already does. Kept
  `openWindow` since it only needs the local `kodigui`/`opener`-free
  MultiWindow machinery -- trimmed to not require `opener` either, see
  below.
"""
from __future__ import absolute_import

from . import kodigui

HOME = None


class GoHomeMixin(object):
    def goHome(self, section=None, with_root=False):
        HOME.go_root = with_root

        if section:
            self.closeWithCommand('HOME:{0}'.format(section))
        else:
            self.closeWithCommand('HOME')

        HOME.show()

    def goHomeRoot(self, *args, **kwargs):
        HOME.go_root = True
        self.closeWithCommand('HOME')
        HOME.show()


class UtilMixin(GoHomeMixin):
    def __init__(self):
        self.exitCommand = None

    def processCommand(self, command):
        if command and command.startswith('HOME'):
            self.exitCommand = command
            self.doClose()
        elif command and command == "NODATA":
            raise kodigui.NoDataException

    def closeWithCommand(self, command):
        self.exitCommand = command
        self.doClose()


def shutdownHome():
    global HOME
    if HOME:
        HOME.shutdown()
    del HOME
    HOME = None
