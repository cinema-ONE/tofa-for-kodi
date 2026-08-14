"""We tell the server who we are, and we do it from ONE definition.

Adrian, looking at the server's Analytics page: our calls bucketed as
"other" beside "tofa App" / "tofa Web" / "tofa Android TV". We were sending
none of the six `X-Tofa-*` identity headers the server's middleware reads --
they are not in the OpenAPI spec, and were found by reading the server
binary (see reference_tofa_client_identity_headers).

Two properties worth locking:

1. The add-on's NAME has exactly one definition, `addon.xml`. It had already
   drifted once -- addon.xml said "tofa" while ABOUT's card said "tofa for
   Kodi" -- which is what a second copy always does eventually.
2. A header value can never take out an unrelated request. Device names are
   whatever the owner typed into Kodi, so a non-ASCII one would make
   `requests` raise while BUILDING every call, not just a call about names.

Run:  python3 test_client_identity.py
"""
import xml.etree.ElementTree as ET

import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import branding, http

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


# --- one definition ------------------------------------------------------
declared = ET.parse(branding.ADDON_XML).getroot().attrib
check("branding reads the name straight from addon.xml",
      branding.app_name() == declared["name"], branding.app_name())
check("...and the version too",
      branding.app_version() == declared["version"], branding.app_version())
check("the name is the one Adrian gave", branding.app_name() == "tofa for Kodi",
      branding.app_name())

# ABOUT's card is RENDERED from that same call, so the shipped XML has to
# carry it. This is the drift that already happened once.
import pathlib
rendered = (pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"
            / "resources" / "skins" / "Main" / "1080i" / "script-tofa-main.xml").read_text()
check("the rendered ABOUT card shows that same name",
      branding.app_name() in rendered)

# The rename must invalidate the render, or the card shows the old name for
# ever -- addon.xml is in build._SOURCE_FILES for exactly this.
from resources.lib.skin import build
check("addon.xml is hashed into the render",
      any(p.endswith("addon.xml") for p in build._SOURCE_FILES),
      str(build._SOURCE_FILES[-1]))


# --- the headers ---------------------------------------------------------
# Stood up as a real box would answer, so this exercises the actual
# detection rather than the stubs' silence. What each value should BE is
# tested in test_client_info.py; this is about what reaches the wire.
from resources.lib import clientinfo
clientinfo._read = lambda path, limit=8192: (
    "model name\t: Amlogic S922X rev b\nHardware\t: UGOOS AM6B\n"
    if "cpuinfo" in path else 'NAME="CoreELEC"\nVERSION="21.3-Omega"\n')
clientinfo._cond = lambda c: c == "System.Platform.Linux"
clientinfo._kodi_build = lambda: "21.3-p3i"
import xbmc
xbmc.getInfoLabel = lambda label: (
    "Kodi (MEDIA-BOX-3D)" if label == "System.FriendlyName" else "")

http._CLIENT_HEADERS = None
headers = http.client_headers()
check("the client names itself", headers.get("X-Tofa-Client") == "tofa for Kodi",
      str(headers))
check("...with its version", headers.get("X-Tofa-Client-Version") == branding.app_version(),
      str(headers))
check("...the platform family", headers.get("X-Tofa-Platform") == "CoreELEC", str(headers))
check("...the hardware", headers.get("X-Tofa-Device-Model") == "Amlogic S922X rev b - UGOOS AM6B",
      str(headers))
check("...the box name, unwrapped", headers.get("X-Tofa-Device-Name") == "MEDIA-BOX-3D",
      str(headers))
check("...and both builds in one os_version",
      headers.get("X-Tofa-OS-Version") == "CoreELEC 21.3-Omega / Kodi 21.3-p3i", str(headers))

# Empty values are dropped rather than sent blank: the server treats a
# missing header as unknown, which is honest, while "" is noise.
http._CLIENT_HEADERS = None
check("empty values are omitted, not sent blank",
      all(v for v in http.client_headers().values()), str(http.client_headers()))


# --- a header can never break an unrelated request -----------------------
check("non-ASCII is stripped", http._ascii("Wohnzimmer-Fernseher überall") ==
      "Wohnzimmer-Fernseher berall", http._ascii("Wohnzimmer-Fernseher überall"))
check("newlines cannot be injected", "\n" not in http._ascii("a\nb: c"),
      http._ascii("a\nb: c"))
check("a header value stays bounded", len(http._ascii("x" * 500)) <= 64)
check("everything survives being encoded as a header",
      all(v.encode("latin-1") for v in http.client_headers().values()))

# The device name goes VERBATIM: whatever Kodi reports is what the server
# gets. Adrian's call -- "MEDIA-BOX-3D is the DEVICE name" -- and it removes a
# whole class of second-guessing about names an owner may have set himself.
check("a device name is passed through untouched",
      http._ascii("Kodi (MEDIA-BOX-3D)") == "Kodi (MEDIA-BOX-3D)",
      http._ascii("Kodi (MEDIA-BOX-3D)"))
check("...including one the owner chose",
      http._ascii("Adrian's Cinema (4K)") == "Adrian's Cinema (4K)",
      http._ascii("Adrian's Cinema (4K)"))

# The session carries them, so every call this add-on makes is identified --
# including ones added later by someone who never read http.py.
session = http.new_session()
check("new_session() carries the identity headers",
      session.headers.get("X-Tofa-Client") == "tofa for Kodi",
      str(dict(session.headers)))
check("...and still the Cloudflare-safe User-Agent",
      session.headers.get("User-Agent") == http.USER_AGENT
      and "python" not in session.headers.get("User-Agent", "").lower())

print()
failed = [n for n, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
