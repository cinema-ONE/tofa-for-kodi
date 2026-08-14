"""After a server switch, nothing on screen may still describe the old one.

THE BUG THIS GUARDS, found by Adrian on the cinema box 2026-08-13. Switch
Server on an install with no cloud refresh token falls through to a full
re-pair; he paired, picked the media server, answered the profile gate with a PIN --
and came back to a Settings page still showing the username instead of the
account email, and a Switch Profile row with no profile name at all.

Two separate causes, both of them a cache that outlived the thing it
described:

  * `_settings_identity` (the cloud's GET /v1/me) was dropped by the
    sign-out path and NOT by this one, even though this one reaches the
    same pairing.
  * `_render_nav_avatar` REPOPULATES the profile cache, and it ran BEFORE
    `_settings_load`. At that moment the switch had cleared the profile
    (they are per-server) and the gate that picks the new one had not run
    yet -- so it cached "no profile" and every later read got that answer.

So this test is about ORDER as much as about state, which is why it records
the call sequence rather than just the final values.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "plugin.video.tofa", "resources"))

import kodi_stubs  # noqa: F401,E402
from lib.windows import main as main_window  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  -- " + detail) if detail and not ok else ""))


class FakeWindow:
    """Just enough MainWindow to run the teardown against."""

    def __init__(self):
        self.calls: list[str] = []
        # Everything the old server put here.
        self.client = "OLD CLIENT"
        self._preferences = {"old": True}
        self._settings_languages = ["de", "en"]
        self._settings_identity = {}          # the pre-pairing answer
        self._active_profile = "OLD PROFILE"
        self._active_profile_cached = True
        self._loaded_sections = {"settings", "home", "browse"}

    def _record(self, name):
        self.calls.append(name)

    def _settings_apply_theme(self):
        self._record("apply_theme")

    def _invalidate_profile_cache(self):
        self._record("invalidate_profile")
        self._active_profile = None
        self._active_profile_cached = False

    def _render_nav_avatar(self):
        self._record("render_avatar")
        # The real one re-reads (and re-caches) the profile here.
        self._active_profile_cached = True

    def _settings_load(self):
        self._record("settings_load")


class FakeModule:
    """Stand-in for signin / prefetch / theme, recording what is called."""

    def __init__(self, calls, **returns):
        self._calls = calls
        self._returns = returns

    def __getattr__(self, name):
        def fn(*a, **k):
            self._calls.append(name)
            return self._returns.get(name)
        return fn


def run_switch(switched: bool) -> FakeWindow:
    win = FakeWindow()
    real = (main_window.signin, main_window.prefetch, main_window.theme)
    main_window.signin = FakeModule(win.calls, interactive_switch_server=switched)
    main_window.prefetch = FakeModule(win.calls)
    main_window.theme = FakeModule(win.calls)
    try:
        main_window.MainWindow._settings_switch_server(win)
    finally:
        main_window.signin, main_window.prefetch, main_window.theme = real
    return win


def main() -> int:
    # --- the viewer backed out: nothing may be torn down ----------------
    win = run_switch(switched=False)
    check("cancelled: the window is left exactly as it was",
          win.client == "OLD CLIENT" and win._settings_identity == {}
          and "settings_load" not in win.calls, "calls=%r" % win.calls)

    # --- the switch happened --------------------------------------------
    win = run_switch(switched=True)
    check("the client is dropped", win.client is None)
    check("the preferences are dropped", win._preferences is None)
    check("the language facet is dropped, it is another library",
          win._settings_languages is None)
    check("the cloud identity is dropped -- THE EMAIL BUG",
          win._settings_identity is None,
          "left as %r" % (win._settings_identity,))
    check("every section but Settings reloads",
          win._loaded_sections == {"settings"}, "got %r" % (win._loaded_sections,))
    check("the prefetch is reset, not merely stripped of its client",
          "reset" in win.calls, "calls=%r" % win.calls)
    check("the theme cache is dropped", "reset_cache" in win.calls)

    # --- and the order, which is the other half of the bug --------------
    check("the profile cache is invalidated before anything reads it",
          win.calls.index("invalidate_profile") < win.calls.index("settings_load"))
    check("the page LOADS before the avatar draws -- THE PROFILE-ROW BUG",
          win.calls.index("settings_load") < win.calls.index("render_avatar"),
          "calls=%r" % win.calls)

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print("FAIL: %d of %d" % (len(failed), len(RESULTS)))
        return 1
    print("switch server: nothing cached survives the switch (%d checks)"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
