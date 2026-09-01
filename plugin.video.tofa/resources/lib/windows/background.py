# -*- coding: utf-8 -*-
"""Adapted from plex-for-kodi (https://github.com/plexinc/plex-for-kodi),
GPL-2.0 -- lib/windows/background.py, their persistent-backdrop window
used to host the always-on-screen background image/blur beneath every
other window. Ported 1:1 apart from `xmlFile`/`path` (tofa's own addon
id/skin) and the global-property namespace (prefixed with the tofa addon
id rather than hardcoded `background.*`).
"""
from __future__ import absolute_import

from . import kodigui

_PROP_PREFIX = kodigui.ADDON_ID

kodigui.setGlobalProperty('background.busy', '')
kodigui.setGlobalProperty('background.shutdown', '')
kodigui.setGlobalProperty('background.splash', '')


class BackgroundWindow(kodigui.BaseWindow):
    xmlFile = 'script-tofa-background.xml'
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    def __init__(self, *args, **kwargs):
        kodigui.BaseWindow.__init__(self, *args, **kwargs)
        self.function = kwargs.get('function')

    def _activate(self, *args, **kwargs):
        self.activate()

    def onFirstInit(self):
        # Upstream hooked a "background.activate" pub-sub signal here;
        # dropped since kodigui.MONITOR (a plain xbmc.Monitor) has no
        # pub-sub surface (see kodigui.py's header) and nothing here emits
        # it. Re-add via kodigui.APP.on(...)/.off(...) if a future window
        # needs it.
        if self.function:
            self.function()
        self.doClose()

    def doClose(self, **kwargs):
        super(BackgroundWindow, self).doClose(**kwargs)

    def onAction(self, action):
        pass


def setBusy(on=True):
    kodigui.setGlobalProperty('background.busy', on and '1' or '')


def setSplash(on=True):
    kodigui.setGlobalProperty('background.splash', on and '1' or '')


def setShutdown(on=True):
    kodigui.setGlobalProperty('background.shutdown', on and '1' or '')
