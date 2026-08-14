"""What this box IS, for the server's client-identity headers.

Kodi answers some of this and not the rest, so the rules here are worth
stating once rather than rediscovering:

**Kodi does not expose the CPU or the hardware model.** `System.CpuModel`,
`System.CPUModel`, `System.CpuVendor`, `System.CpuHardware`,
`System.Hardware` and `System.DeviceModel` all return empty -- measured on a
live box, 2026-08-11. Kodi's own System Info window DOES show
"Amlogic S922X rev b", but it renders that in C++ straight from
`/proc/cpuinfo` without publishing an infolabel. So we read the same file.

**`System.OSVersionInfo` and `System.KernelVersion` are ASYNCHRONOUS.** They
carry exactly the string we want, and they answer `"Busy"` until Kodi's
worker has computed it -- measured on macOS as `Busy`, `Busy`, then the real
value on the third read several seconds later. The headers are built once
per process, so reading those would cache `"Busy"` about half the time.
`/etc/os-release` is the same information, synchronously.

Everything here is a file read or a stdlib call. No subprocesses: this runs
during start-up on a box whose whole job is to be quick.
"""
from __future__ import annotations

import os
import platform as _platform_mod
from typing import Optional

import xbmc

#: `/proc/cpuinfo` keys, in the order they make a name. On the AM6B+ (4.9
#: kernel) both are present -- "Amlogic S922X rev b" + "UGOOS AM6B". On the
#: cinema box (mainline) only `Hardware` is, giving "Dune/Homatics R 4K
#: Plus". So this joins what exists rather than assuming the pair.
_CPUINFO_KEYS = ("model name", "hardware")


def _read(path: str, limit: int = 8192) -> str:
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _cond(condition: str) -> bool:
    try:
        return bool(xbmc.getCondVisibility(condition))
    except Exception:                                       # noqa: BLE001
        return False


def _os_release() -> dict:
    """`/etc/os-release` as a dict. Empty off Linux."""
    fields = {}
    for line in _read("/etc/os-release").splitlines():
        key, _, value = line.partition("=")
        if key:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def device_name() -> str:
    """The box, without Kodi's wrapper: "MEDIA-BOX-3D", not "Kodi (MEDIA-BOX-3D)".

    `System.FriendlyName` is "Kodi (<hostname>)" until the owner sets a name
    of their own, at which point it is that name verbatim. Adrian asked for
    the bare name (2026-08-11) after first asking for it verbatim -- the
    server shows this beside the client name and the device model, where the
    "Kodi" adds nothing the other two do not already say.

    Only the exact shape Kodi generates is unwrapped. A name the owner chose
    that happens to contain brackets is their wording and is left alone.
    """
    try:
        name = (xbmc.getInfoLabel("System.FriendlyName") or "").strip()
    except Exception:                                       # noqa: BLE001
        return ""
    if name.startswith("Kodi (") and name.endswith(")"):
        inner = name[len("Kodi ("):-1].strip()
        if inner:
            return inner
    return name


def device_model() -> str:
    """The hardware, e.g. "Amlogic S922X rev b - UGOOS AM6B".

    From `/proc/cpuinfo`, which is where Kodi's own System Info gets it.
    Empty off Linux -- macOS would need a `sysctl` subprocess for
    "Apple M5" (`platform.processor()` only says "arm"), and that is the dev
    machine, not a device anybody watches on.

    Empty is a fine answer: the server treats a missing header as unknown,
    and the main tofa App sits in the same bucket.
    """
    found = {}
    for line in _read("/proc/cpuinfo").splitlines():
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if sep and key in _CPUINFO_KEYS and value.strip():
            found.setdefault(key, value.strip())
    parts = [found[k] for k in _CPUINFO_KEYS if k in found]
    return " - ".join(parts)


def platform_family() -> str:
    """The OS FAMILY, not the build: "CoreELEC", "macOS", "Android".

    Deliberately low-cardinality. The server's own platform vocabulary is
    short (android, iphone, ios, webos, tizen, chrome/safari/web), which is
    the shape of a grouping key -- put a build string here and every nightly
    becomes its own row in the analytics breakdown. Adrian's call, given that
    trade-off; the build travels in os_version instead.
    """
    if _cond("System.Platform.Android"):
        return "Android"
    if _cond("System.Platform.TVOS"):
        return "tvOS"
    if _cond("System.Platform.IOS"):
        return "iOS"
    if _cond("System.Platform.OSX"):
        return "macOS"
    if _cond("System.Platform.Windows"):
        return "Windows"
    if _cond("System.Platform.Linux"):
        # CoreELEC and LibreELEC both name themselves here, which is far more
        # use to a server owner than "Linux".
        return _os_release().get("NAME") or "Linux"
    return ""


def _kodi_build() -> str:
    """Kodi's own version -- the runtime this add-on is a guest in.

    There is no header for it, and it is the single most useful fact for
    diagnosing a client-side problem, so it rides along in os_version.
    `System.BuildVersion` is synchronous, unlike its OSVersionInfo neighbour.
    """
    try:
        return (xbmc.getInfoLabel("System.BuildVersion") or "").strip()
    except Exception:                                       # noqa: BLE001
        return ""


def os_version() -> str:
    """The OS build, plus the Kodi build, e.g.
    "CoreELEC 21.3-Omega_p3i_T4b_20260704001258 / Kodi 21.3-p3i".

    Separator is ASCII on purpose: header values are stripped to ASCII, and a
    "·" would be dropped, leaving a confusing double space.
    """
    fields = _os_release()
    if fields.get("NAME") and fields.get("VERSION"):
        os_part = f"{fields['NAME']} {fields['VERSION']}"
    elif _cond("System.Platform.OSX"):
        # mac_ver() gives "26.6.1" but no build number -- that needs sysctl,
        # and this is the dev machine.
        os_part = f"macOS {_platform_mod.mac_ver()[0]}".strip()
    else:
        os_part = ""
    kodi = _kodi_build()
    parts = [p for p in (os_part, f"Kodi {kodi}" if kodi else "") if p]
    return " / ".join(parts)
