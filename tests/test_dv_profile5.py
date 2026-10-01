"""A box without a Dolby Vision decoder asks for Profile 5 files converted.

Profile 5 has no HDR10 base layer, so Kodi without the Dolby Vision reshaping
(Windows, Xbox, Linux PCs, macOS) shows it in wrong colours. Server 0.11.0
converts it to SDR when the stream request says Profile 5 is unsupported.

Run:  python3 test_dv_profile5.py
"""
import kodi_stubs  # noqa: F401  -- installs the Kodi stubs
from resources.lib import capabilities
from resources.lib.profile import CapabilityProfile

RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        "" if ok else "  -- got %r, want %r" % (got, want)))


def flag(**caps):
    capabilities.video = lambda: caps
    capabilities.audio_delivery = lambda: {}
    return CapabilityProfile.for_device().to_query_params().get(
        "dolby_vision_profile_5_supported")


def main():
    check("a box with a Dolby Vision decoder says nothing, so DirectPlay stays",
          flag(known=True, dv_profile5=True), None)
    check("a box without one asks for the conversion",
          flag(known=True, dv_profile5=False), "false")
    check("a box that could not be asked says nothing",
          flag(known=False, dv_profile5=False), None)
    check("an explicit value from the caller wins",
          CapabilityProfile.for_device(dolby_vision_profile_5_supported=True)
          .to_query_params().get("dolby_vision_profile_5_supported"), "true")

    failed = [n for n, ok in RESULTS if not ok]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
