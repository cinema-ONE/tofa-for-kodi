"""One consent dialog for every change tofa makes OUTSIDE its own add-on.

There are three such changes, and they have the same shape: each is needed for
our screens to look right, each edits something we do not own, each is
idempotent, and each only takes effect after a Kodi restart.

  * fontinstall.py -- copies our fonts into the ACTIVE SKIN and patches that
    skin's Font.xml (Kodi's GUIFontManager loads fonts from the active skin
    and nowhere else).
  * hostconfig.py -- raises `<imageres>` in the user's advancedsettings.xml,
    because Kodi otherwise caps every cached texture at 720px tall and our
    1920x1080 backdrops are stored, and drawn, as 1280x720.
  * seekbarpatch.py -- adds one `<visible>` condition to the active skin's
    DialogSeekBar.xml, so the skin's seek bar does not slide in over our
    player's own transport. Nothing short of editing the skin works; the
    module's docstring records what else was measured and rejected.

Fonts and imageres were nearly built as two separate prompts, on the theory
that fonts are mandatory while imageres is an optional 4K nicety. Both halves
of that were wrong: measured on a 1080p GUI, backdrops are degraded there too,
so imageres is not optional; and editing a third-party SKIN is if anything the
more invasive of the two -- a skin update can wipe our injection, and on
CoreELEC we clone the whole skin into userdata to get around a read-only
squashfs, whereas advancedsettings.xml is a file Kodi ships expressly to be
edited.

So: ONE dialog, listing whichever changes are actually outstanding. One
decline record per concern, though, so that each can ask again on its own
terms (a new font set re-asks; a user who removed `<imageres>` by hand is not
nagged about it) without ever costing more than one dialog. That is what
_CONCERNS is -- adding a fourth means adding a row, not another 2^n branch
through the message strings.

Checked from the same two places fontinstall used to be, both calling the
cheap idempotent ensure_host_setup(): service.py at Kodi startup, and every
window's open()/create() choke point in windows/kodigui.py. The latter
catches an in-place add-on update that bumps FONT_SET_VERSION without a full
Kodi restart.
"""
from __future__ import annotations

from typing import Callable, NamedTuple

import xbmc
import xbmcaddon
import xbmcgui

from . import fontinstall, hostconfig, log, seekbarpatch

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
_ = ADDON.getLocalizedString

HOSTCONFIG_DECLINED_SETTING = "hostconfig_declined_version"

#: Bump when what hostconfig.py writes changes, so a user who declined the
#: previous expectation is asked again. Same contract as FONT_SET_VERSION.
HOSTCONFIG_VERSION = 1


class _Concern(NamedTuple):
    """One thing we change outside the add-on. `clause` is the string id of
    a short phrase naming the change, listed in the consent dialog only when
    that change is actually outstanding -- the dialog must never claim to be
    about to do something it has already done.

    `skin_setting` names the per-skin decline store, and is set for the
    concerns that edit the ACTIVE SKIN rather than something global. For
    those, a decline only ever means "not on this skin": see
    _declined_version.
    """
    declined_setting: str
    version: int
    needed: Callable[[], bool]
    apply: Callable[[], bool]
    clause: int
    skin_setting: str = ""


_CONCERNS = (
    _Concern(fontinstall.DECLINED_SETTING, fontinstall.FONT_SET_VERSION,
             fontinstall.fonts_needed, fontinstall.apply_fonts, 31109,
             fontinstall.SKIN_DECLINED_SETTING),
    # advancedsettings.xml is per-PROFILE, not per-skin, so this one keeps a
    # bare version int: declining it means declining it everywhere.
    _Concern(HOSTCONFIG_DECLINED_SETTING, HOSTCONFIG_VERSION,
             hostconfig.imageres_needed, hostconfig.apply_imageres, 31110),
    _Concern(seekbarpatch.DECLINED_SETTING, seekbarpatch.SEEKBAR_PATCH_VERSION,
             seekbarpatch.patch_needed, seekbarpatch.apply_patch, 31111,
             seekbarpatch.SKIN_DECLINED_SETTING),
)

#: The fonts are the only concern that INSTALLS anything, so they alone
#: decide whether the confirm button reads "Install" or "Apply".
_FONTS = _CONCERNS[0]


def _skin_id() -> str:
    try:
        return xbmc.getSkinDir() or ""
    except Exception:
        return ""


def _parse_skin_map(raw: str) -> dict[str, int]:
    """`skin.estuary=25|skin.confluence=24` -> {"skin.estuary": 25, ...}.

    Deliberately forgiving: an unparseable chunk is dropped rather than
    raising, because the worst case of forgetting a decline is one extra
    dialog, and the worst case of raising here is no host setup at all.
    """
    parsed: dict[str, int] = {}
    for chunk in raw.split("|"):
        skin, _sep, version = chunk.partition("=")
        if skin and version.isdigit():
            parsed[skin] = int(version)
    return parsed


def _format_skin_map(declines: dict[str, int]) -> str:
    return "|".join(f"{skin}={version}" for skin, version in sorted(declines.items()))


def _read_skin_map(concern: _Concern) -> dict[str, int]:
    """The per-skin declines, migrating the pre-0.9.15 bare int on first read.

    MIGRATION. Before this, a decline was one integer with no skin attached,
    so an existing "no" cannot be attributed to a skin by inspection. It is
    credited to whatever skin is active the first time this runs, which is
    the skin the user was almost certainly looking at when they declined --
    and crucially it is not credited to any OTHER skin, so switching still
    asks. The legacy int is zeroed in the same breath so this happens once;
    leaving it set would re-credit it to a different skin later.
    """
    try:
        raw = ADDON.getSetting(concern.skin_setting) or ""
    except (TypeError, ValueError):
        raw = ""
    declines = _parse_skin_map(raw)
    if declines:
        return declines

    legacy = _declined_int(concern.declined_setting)
    if legacy <= 0:
        return {}
    skin = _skin_id()
    if not skin:
        return {}
    declines = {skin: legacy}
    _write_skin_map(concern, declines)
    ADDON.setSettingInt(concern.declined_setting, 0)
    log.debug(f"hostsetup: migrated {concern.declined_setting}={legacy} onto {skin}")
    return declines


def _write_skin_map(concern: _Concern, declines: dict[str, int]) -> None:
    ADDON.setSetting(concern.skin_setting, _format_skin_map(declines))


def _declined_int(setting: str) -> int:
    try:
        return ADDON.getSettingInt(setting)
    except (TypeError, ValueError):
        return 0


def _declined_version(concern: _Concern) -> int:
    """The version of this concern the user last said no to, HERE.

    For a concern that edits the active skin, a decline is remembered
    against that skin's id. Declining tofa's fonts on Estuary said nothing
    about a skin the user had not switched to yet, and the fonts genuinely
    are missing over there -- a global "no" left tofa's screens on fallback
    fonts with no way back except a FONT_SET_VERSION bump.
    """
    if not concern.skin_setting:
        return _declined_int(concern.declined_setting)
    skin = _skin_id()
    if not skin:
        # No active skin to attribute a decline to. Answering 0 means "not
        # declined", which at worst asks once more; it never writes.
        return 0
    return _read_skin_map(concern).get(skin, 0)


def _remember_declined(concern: _Concern) -> None:
    if not concern.skin_setting:
        ADDON.setSettingInt(concern.declined_setting, concern.version)
        return
    skin = _skin_id()
    if not skin:
        return
    declines = _read_skin_map(concern)
    declines[skin] = concern.version
    _write_skin_map(concern, declines)


def _clear_declined(concern: _Concern) -> None:
    """A previous decline is spent once the concern is applied: leaving it
    set would suppress the prompt for the NEXT version of this concern."""
    if not concern.skin_setting:
        ADDON.setSettingInt(concern.declined_setting, 0)
        return
    skin = _skin_id()
    if not skin:
        return
    declines = _read_skin_map(concern)
    if declines.pop(skin, None) is not None:
        _write_skin_map(concern, declines)


def will_auto_restart() -> bool:
    """CoreELEC/LibreELEC run Kodi under systemd with `Restart=always` --
    `Quit` comes back on its own there, no different builtin needed.
    Anywhere else (desktop installs) `Quit` just exits and stays exited,
    so the user needs telling."""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            os_release = f.read()
    except OSError:
        return False
    return any(f'ID="{distro}"' in os_release or f"ID={distro}" in os_release
               for distro in ("coreelec", "libreelec"))


def _ask_consent(wanted: list[_Concern]) -> bool:
    """Asked BEFORE anything is written, and it names what it will touch.

    (fontinstall used to ask AFTERWARDS, which made the dialog a lie three
    ways over: the work was already done, "no" only postponed the restart
    rather than declining anything, and the marker it had already written
    short-circuited every later check so the question never came back.)"""
    # Kodi's yesno body does not wrap: a line wider than the dialog is
    # CLIPPED, and measured live it clipped from the LEFT, so an over-long
    # lead-in silently loses its opening words. Every string used here has
    # to fit on one line -- around 50 characters in Estuary at 1080p.
    tail = _(31037) if will_auto_restart() else _(31038)
    body = "\n".join([_(31108)] + [f"- {_(c.clause)}" for c in wanted] + ["", tail])
    # "Install" only reads correctly when something is being installed. When
    # the fonts are already in, nothing is, so the button says "Apply".
    yeslabel = _(31039) if _FONTS in wanted else _(31106)
    return bool(xbmcgui.Dialog().yesno(ADDON_NAME, body, yeslabel=yeslabel, nolabel=_(31042)))


def _outstanding(forced: bool) -> list[_Concern]:
    """The concerns that still need doing AND that we may still ask about.

    A decline is remembered per concern, so the prompt does not come back
    every time a window opens; `forced` (the Settings row) ignores that."""
    wanted = [c for c in _CONCERNS if c.needed()]
    if forced:
        return wanted
    return [c for c in wanted if _declined_version(c) < c.version]


def ensure_host_setup(forced: bool = False) -> bool:
    """Best-effort: a failure here is a missed cosmetic upgrade, never a
    reason to block whatever screen called this. Returns True only if a
    restart was just triggered, in which case callers should stop rather
    than continue with stale state.

    `forced` is the Settings row, which asks again after a decline."""
    try:
        wanted = _outstanding(forced)
        if not wanted:
            return False

        if not _ask_consent(wanted):
            for concern in wanted:
                _remember_declined(concern)
            log.debug("hostsetup: declined, nothing written")
            return False

        changed = False
        for concern in wanted:
            if concern.apply():
                _clear_declined(concern)
                changed = True

        if not changed:
            return False
        xbmc.executebuiltin("Quit")
        return True
    except Exception as exc:
        log.warning(f"hostsetup: failed, continuing unconfigured: {exc}")
        return False


def setup_interactive() -> None:
    """The Settings > This Device row (addon.py:action_install_fonts).

    The way back in after declining, since a decline is otherwise remembered
    until the relevant version changes. Says so plainly when there is nothing
    to do, rather than appearing to have ignored the button."""
    try:
        if not _outstanding(forced=True):
            xbmcgui.Dialog().ok(ADDON_NAME, _(31043))
            return
    except Exception as exc:
        log.warning(f"hostsetup: could not inspect the host: {exc}")
    ensure_host_setup(forced=True)
