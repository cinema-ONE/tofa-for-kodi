"""What we tell the server this box IS.

Adrian read Kodi's System Info > Summary/Hardware and asked whether the
add-on could report the same things. Mostly yes, but not from where you
would expect, and the two traps are what this locks:

1. **Kodi does not expose the CPU or hardware model at all.**
   System.CpuModel / CPUModel / CpuVendor / CpuHardware / Hardware /
   DeviceModel all answer empty -- measured live. Kodi's own System Info
   shows "Amlogic S922X rev b" because it reads /proc/cpuinfo in C++. So we
   read the same file, and the parsing is what is tested here.
2. **System.OSVersionInfo is asynchronous** -- it answers "Busy" until a
   worker fills it in (measured: Busy, Busy, then the value on the third
   read). Headers are built once per process, so we read /etc/os-release
   instead. Nothing here should ever reach for that infolabel.

The fixtures are the REAL files off both boxes, because the interesting
difference is between them: the 4.9-kernel AM6B+ has `model name` AND
`Hardware`, and the mainline cinema box has only `Hardware`.

Run:  python3 test_client_info.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import clientinfo

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# --- real /proc/cpuinfo tails, verbatim ----------------------------------
AM6B_CPUINFO = """processor\t: 3
CPU variant\t: 0x0
CPU part\t: 0xd09
CPU revision\t: 2

Serial\t\t: 290b4000011926000007303158354550
model name\t: Amlogic S922X rev b
Hardware\t: UGOOS AM6B
"""
# The mainline kernel drops `model name` entirely.
CINEMA_CPUINFO = """processor\t: 7
CPU revision\t: 4

Hardware\t: Dune/Homatics R 4K Plus
"""
AM6B_OS_RELEASE = 'NAME="CoreELEC"\nVERSION="21.3-Omega_p3i_T4b_20260704001258"\nID=coreelec\n'
CINEMA_OS_RELEASE = 'NAME="CoreELEC"\nVERSION="22.0-Piers_nightly_20260810"\nID=coreelec\n'


def with_box(cpuinfo="", os_release="", platform_linux=True, kodi=""):
    clientinfo._read = lambda p, limit=8192: (
        cpuinfo if "cpuinfo" in p else os_release if "os-release" in p else "")
    clientinfo._cond = lambda c: platform_linux and c == "System.Platform.Linux"
    clientinfo._kodi_build = lambda: kodi


# --- device_model: the whole point of reading cpuinfo --------------------
with_box(cpuinfo=AM6B_CPUINFO)
check("both keys join into one model",
      clientinfo.device_model() == "Amlogic S922X rev b - UGOOS AM6B",
      clientinfo.device_model())

with_box(cpuinfo=CINEMA_CPUINFO)
check("only Hardware present -> just that",
      clientinfo.device_model() == "Dune/Homatics R 4K Plus", clientinfo.device_model())

with_box(cpuinfo="processor\t: 0\nBogoMIPS\t: 48.00\n")
check("neither key -> empty, not a guess", clientinfo.device_model() == "",
      clientinfo.device_model())
with_box(cpuinfo="")
check("no /proc/cpuinfo at all (macOS) -> empty", clientinfo.device_model() == "")

# A `processor : 0` line must not be mistaken for the model. It is the FIRST
# line of the file and an earlier throwaway grep of mine matched exactly that
# and reported the CPU as "0".
with_box(cpuinfo="processor\t: 0\nmodel name\t: Amlogic S922X rev b\n")
check("a leading 'processor : 0' is not the model",
      clientinfo.device_model() == "Amlogic S922X rev b", clientinfo.device_model())

# Order is model-then-hardware regardless of file order.
with_box(cpuinfo="Hardware\t: UGOOS AM6B\nmodel name\t: Amlogic S922X rev b\n")
check("order is SoC then board, whatever the file says",
      clientinfo.device_model() == "Amlogic S922X rev b - UGOOS AM6B",
      clientinfo.device_model())


# --- platform_family: a GROUPING key, so low cardinality -----------------
with_box(os_release=AM6B_OS_RELEASE)
check("Linux reports its distro, not 'Linux'",
      clientinfo.platform_family() == "CoreELEC", clientinfo.platform_family())
with_box(os_release="")
check("Linux with no os-release falls back to Linux",
      clientinfo.platform_family() == "Linux", clientinfo.platform_family())

# The build must NOT leak into platform -- that is the whole reason this is
# split from os_version. Every nightly would become its own analytics row.
with_box(os_release=AM6B_OS_RELEASE)
check("no build string in platform",
      "21.3" not in clientinfo.platform_family(), clientinfo.platform_family())

clientinfo._cond = lambda c: c == "System.Platform.Android"
check("Android is named directly", clientinfo.platform_family() == "Android")
clientinfo._cond = lambda c: c == "System.Platform.OSX"
check("macOS is named directly", clientinfo.platform_family() == "macOS")
clientinfo._cond = lambda c: False
check("an unknown platform is empty, not a guess",
      clientinfo.platform_family() == "")


# --- os_version: OS build AND Kodi build ---------------------------------
with_box(os_release=AM6B_OS_RELEASE, kodi="21.3-p3i (21.3.0) Git:aml-4.9-21.3")
check("os_version carries both builds",
      clientinfo.os_version()
      == "CoreELEC 21.3-Omega_p3i_T4b_20260704001258 / Kodi 21.3-p3i (21.3.0) Git:aml-4.9-21.3",
      clientinfo.os_version())

with_box(os_release=CINEMA_OS_RELEASE, kodi="22.0-BETA1")
check("...on the other box too",
      clientinfo.os_version() == "CoreELEC 22.0-Piers_nightly_20260810 / Kodi 22.0-BETA1",
      clientinfo.os_version())

with_box(os_release=AM6B_OS_RELEASE, kodi="")
check("a missing Kodi build leaves no dangling separator",
      clientinfo.os_version() == "CoreELEC 21.3-Omega_p3i_T4b_20260704001258",
      clientinfo.os_version())
with_box(os_release="", kodi="21.3", platform_linux=False)
check("no OS info still reports Kodi", clientinfo.os_version() == "Kodi 21.3",
      clientinfo.os_version())
with_box()
check("nothing known -> empty", clientinfo.os_version() == "")

# ASCII, because header values are stripped to it -- a "." separator would be
# dropped and leave a confusing double space.
with_box(os_release=AM6B_OS_RELEASE, kodi="21.3")
check("the separator survives an ASCII strip",
      clientinfo.os_version().encode("ascii", "ignore").decode() == clientinfo.os_version(),
      clientinfo.os_version())


# --- device_name: Kodi's wrapper comes off -------------------------------
import xbmc
def with_friendly(name):
    xbmc.getInfoLabel = lambda label: name if label == "System.FriendlyName" else ""

with_friendly("Kodi (MEDIA-BOX-3D)")
check("Kodi (HOST) reports as HOST", clientinfo.device_name() == "MEDIA-BOX-3D",
      clientinfo.device_name())
with_friendly("Kodi (DEVBOX.local)")
check("...including a .local hostname", clientinfo.device_name() == "DEVBOX.local")
with_friendly("Adrian's Cinema (4K)")
check("a name the owner chose is untouched",
      clientinfo.device_name() == "Adrian's Cinema (4K)", clientinfo.device_name())
with_friendly("Kodi ()")
check("a degenerate wrapper is not unwrapped to nothing",
      clientinfo.device_name() == "Kodi ()", clientinfo.device_name())
with_friendly("")
check("no name -> empty", clientinfo.device_name() == "")

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
