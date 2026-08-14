# -*- coding: utf-8 -*-
"""Return the viewer to the exact item they left from.

THE PROBLEM. Every screen in this add-on declares
`<defaultcontrol always="true">` -- main 3000, detail 5210, person 8000 --
and `always` means EVERY init, not the first. Kodi re-inits a window when
whatever was covering it closes, so opening a title and pressing Back put
focus on the nav bar, or on the Play pill, rather than on the card that was
clicked. The list underneath had kept its selection; the viewer just was not
standing on it any more, and the next Down started from somewhere else.

Fixed here rather than by dropping `always` from the XML: that attribute is
what guarantees a known starting focus for a window that hosts five sections
in one control tree, and a re-init is the one moment it is wrong.

WHY POSITION IS NOT ENOUGH. Continue Watching reorders itself after you
watch something -- which is exactly when you are coming back. Restoring
"position 3" then lands on a different title than the one you opened. So
the item's own identity is recorded too, and the position is only the hint
of where to start looking.

WHY ON CLICK, NOT ON FOCUS. The default-control refocus fires onFocus during
the re-init, so a focus-driven record overwrites itself with the very focus
being corrected. Measured: that version read the nav bar back and did
nothing.

WHEN THE ROW ITSELF IS GONE. Restoring focus is only half the job, because
the container can leave while the viewer is away -- finish the last thing in
Continue Watching and that row empties, and an empty row hides. Kodi does
NOT raise for that. `setFocusId` on a hidden control logs

    error: Control 4200 in window 13001 has been asked to focus, but it can't

and leaves focus NOWHERE -- `System.CurrentControlId` reads "". Measured
2026-08-09 by clearing the last Continue Watching entry while a Detail page
was open over Home: coming back, the whole screen was unfocused and the
viewer's next keypress was swallowed getting focus back, landing them on the
nav bar. So a `try/except RuntimeError` around setFocusId catches nothing;
the target has to be checked BEFORE asking, and there has to be somewhere
else to go. Hence focus_memory_neighbours() and FOCUS_MEMORY_LAST_RESORT.
"""
from __future__ import annotations


def _item_key(item) -> str:
    """A stable identity for a card, best available.

    media_id first because it is what every card that can open a Detail page
    carries; tmdb_id for a discovery card the server does not hold; the label
    last, which is weak but still beats a bare position for a reordered row.
    """
    if item is None:
        return ""
    for prop in ("media_id", "tmdb_id"):
        value = item.getProperty(prop)
        if value:
            return "{0}:{1}".format(prop, value)
    source = item.dataSource
    if isinstance(source, dict):
        for field in ("id", "media_id", "tmdb_id"):
            if source.get(field):
                return "{0}:{1}".format(field, source[field])
    try:
        return "label:{0}".format(item.getLabel())
    except Exception:
        return ""


class FocusMemory(object):
    """Mixin. `remember_focus()` on click, `restore_focus()` on re-init.

    A window opts in by calling both and by implementing
    `focus_memory_list()` so the mixin can find the container behind a
    control id. A window with no lists can skip that and still get its
    focused CONTROL back, which is all a pill row needs.
    """

    #: Controls not worth returning to. A nav bar is where Kodi's own default
    #: already puts you, so remembering it is a no-op that only costs a call.
    FOCUS_MEMORY_IGNORE: tuple = ()

    #: Where to put focus when nothing else will take it. Not a nicety: with
    #: no focusable target Kodi leaves the window with focus on NOTHING, and
    #: the viewer spends a keypress getting it back. A window that names one
    #: control here can never strand them.
    FOCUS_MEMORY_LAST_RESORT = None

    def focus_memory_list(self, control_id):
        """The ManagedControlList behind `control_id`, or None if this
        control is not a list (or the window does not track it)."""
        return None

    def focus_memory_neighbours(self, control_id) -> tuple:
        """The controls `control_id` sits among, in VISUAL order, including
        itself -- the rows of its section, the shelves of its tab.

        Consulted only when the remembered control cannot take focus. The
        mixin picks the nearest one that can, preferring the direction the
        list was collapsing towards (down first, since that is where the
        content the row was hiding now sits).

        Default is "no neighbourhood", which degrades to the last resort.
        """
        return ()

    def _focus_memory_can_take(self, control_id) -> bool:
        """Whether asking for focus here would actually land.

        Only lists can be judged, and for them emptiness is the test: Home
        and Discover both hide a row whose list came back empty, which is
        exactly when its control stops being focusable. Anything not tracked
        as a list is assumed focusable -- a pill or a rail is always there.
        """
        mcl = self.focus_memory_list(control_id)
        # `is not None`: a ManagedControlList is falsy when empty, which is
        # the very case being tested (feedback_managedcontrollist_truthiness).
        return mcl is None or bool(len(mcl))

    def remember_focus(self, control_id):
        """Record where the viewer is, before opening anything over us."""
        key, position = "", -1
        mcl = self.focus_memory_list(control_id)
        # `is not None`: a ManagedControlList is falsy when EMPTY, and an
        # empty list is a perfectly real answer here (feedback_
        # managedcontrollist_truthiness).
        if mcl is not None and len(mcl):
            position = mcl.getSelectedPosition()
            key = _item_key(mcl.getSelectedItem())
        self._focus_memory = (control_id, key, position)

    def restore_focus(self):
        """Put the viewer back. Safe to call on every re-init."""
        record = getattr(self, "_focus_memory", None)
        if not record:
            return
        control_id, key, position = record
        if control_id in self.FOCUS_MEMORY_IGNORE:
            return
        if self._restore_to(control_id, key, position):
            return
        # The row they left from is gone -- emptied out and hidden while they
        # were away. Land them as close to it as the screen still allows,
        # looking DOWN first: the rows below have moved up into the space it
        # left, so the nearest one below is now where it used to be.
        for candidate in self._focus_memory_ladder(control_id):
            if self._restore_to(candidate, "", -1):
                return

    def _focus_memory_ladder(self, control_id) -> list:
        """Where to try next, nearest first, after `control_id` refused."""
        ladder = []
        neighbours = list(self.focus_memory_neighbours(control_id))
        if control_id in neighbours:
            here = neighbours.index(control_id)
            below = neighbours[here + 1:]
            above = list(reversed(neighbours[:here]))
            # Interleaved rather than "all of below, then all of above": with
            # one row left directly above and five empty ones below, walking
            # the whole tail first is a long way to travel for a worse
            # answer. Nearest wins, ties going down.
            for step in range(max(len(below), len(above))):
                if step < len(below):
                    ladder.append(below[step])
                if step < len(above):
                    ladder.append(above[step])
        else:
            ladder.extend(n for n in neighbours if n != control_id)
        if self.FOCUS_MEMORY_LAST_RESORT is not None:
            ladder.append(self.FOCUS_MEMORY_LAST_RESORT)
        return ladder

    def _restore_to(self, control_id, key, position) -> bool:
        """Focus `control_id`, and (given a key) stand on the right item.

        Returns whether focus actually went there -- checked BEFORE asking,
        because Kodi answers an impossible setFocusId with a log line rather
        than an exception, and leaves the window focusing nothing at all.
        """
        if not self._focus_memory_can_take(control_id):
            return False
        try:
            self.setFocusId(control_id)
        except RuntimeError:
            return False
        if not key or position < 0:
            # A fallback row keeps whatever selection it already had, which
            # is where this viewer last stood in it. Only the row they
            # actually came from gets its item re-found.
            return True
        mcl = self.focus_memory_list(control_id)
        if mcl is None or not len(mcl):
            return True
        target = position if position < len(mcl) else len(mcl) - 1
        if _item_key(mcl[target]) != key:
            # The list was rebuilt or reordered underneath us. Find the item
            # itself; if it is genuinely gone (unwatchlisted, filtered out,
            # watched off a Continue Watching row) keep the clamped position
            # rather than snapping to the top.
            for idx in range(len(mcl)):
                if _item_key(mcl[idx]) == key:
                    target = idx
                    break
        try:
            mcl.selectItem(target)
        except Exception:
            pass
        return True
