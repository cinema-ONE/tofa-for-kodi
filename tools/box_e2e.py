#!/usr/bin/env python3
"""End-to-end check of the add-on on a real box, over JSON-RPC and ssh.

Walks every screen (Home, Browse and its views, Collections, sort menu,
Discover, Search, Settings, Who's watching, a title page, a person page),
asserts each one loaded, plays a title on a TEST profile only, and fails on
any error tofa wrote to kodi.log meanwhile. Changes no setting; playback
leaves a few seconds of progress on the test profile.

    python3 tools/box_e2e.py --host 192.168.1.50 --ssh mybox \
        [--play --test-profile "Test"]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HARNESS = "script.tofa.harness"
LOG = "/storage/.kodi/temp/kodi.log"


class Box:
    def __init__(self, host: str, ssh: str, auth: str | None):
        self.url = f"http://{host}:8080/jsonrpc"
        self.ssh = ssh
        self.headers = {"Content-Type": "application/json"}
        if auth:
            token = base64.b64encode(auth.encode()).decode()
            self.headers["Authorization"] = "Basic " + token

    def rpc(self, method: str, params: dict | None = None, timeout: float = 15):
        body = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params:
            body["params"] = params
        req = urllib.request.Request(self.url, json.dumps(body).encode(), self.headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp).get("result")

    def labels(self, *names: str) -> dict:
        try:
            return self.rpc("XBMC.GetInfoLabels", {"labels": list(names)}) or {}
        except Exception:                                    # noqa: BLE001
            return {}

    def label(self, name: str) -> str:
        return self.labels(name).get(name, "")

    def cond(self, name: str) -> bool:
        """An info bool; GetInfoLabels answers those with an empty string."""
        try:
            return bool((self.rpc("XBMC.GetInfoBooleans", {"booleans": [name]}) or {}).get(name))
        except Exception:                                    # noqa: BLE001
            return False

    def key(self, name: str, times: int = 1, pause: float = 0.35):
        for _ in range(times):
            self.rpc(f"Input.{name}")
            time.sleep(pause)

    def builtin(self, command: str):
        """A Kodi builtin through the harness add-on (JSON-RPC has none)."""
        self.rpc("Addons.ExecuteAddon", {"addonid": HARNESS, "params": {
            "builtin": urllib.parse.quote(command, safe="")}})

    def sh(self, command: str) -> str:
        out = subprocess.run(["ssh", "-o", "ConnectTimeout=8", self.ssh, command],
                             capture_output=True, text=True, timeout=60)
        return out.stdout

    def wait(self, predicate, timeout: float = 20, step: float = 0.5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                value = predicate()
            except Exception:                                # noqa: BLE001
                value = None
            if value:
                return value
            time.sleep(step)
        return None

    def select_if(self, condition: str) -> bool:
        """Select only while `condition` (an info bool) holds -- never on a
        guess, since a stray Select could sign out or touch the watchlist."""
        if self.cond(condition):
            self.key("Select")
            return True
        return False

    def back_if(self, condition: str, pause: float = 0.8) -> bool:
        """Back only where it closes something; at tofa's top level it asks
        to exit instead."""
        if self.cond(condition):
            self.key("Back", pause=pause)
            return True
        return False

    def dialog(self) -> str:
        return self.label("Window.Property(tofa_dialog)")

    def num_items(self, list_id: int) -> int:
        try:
            return int(self.label(f"Container({list_id}).NumItems") or 0)
        except ValueError:
            return 0


class Run:
    def __init__(self, box: Box, out: str):
        self.box, self.out, self.results = box, out, []

    def check(self, name: str, ok, detail: str = ""):
        self.results.append((name, bool(ok), detail))
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else "  -- " + detail),
              flush=True)
        return bool(ok)

    def shot(self, name: str):
        """A native screenshot, copied home. Best effort: a few screens give
        Kodi's screenshot a blank frame on these boxes."""
        b = self.box
        try:
            folder = b.rpc("Settings.GetSettingValue", {"setting": "debug.screenshotpath"})["value"]
            before = b.sh(f"ls -t {folder}*.png 2>/dev/null | head -1").strip()
            b.rpc("Input.ExecuteAction", {"action": "screenshot"})
            newest = b.wait(lambda: (lambda n: n if n and n != before else None)(
                b.sh(f"ls -t {folder}*.png 2>/dev/null | head -1").strip()), 10)
            if newest:
                subprocess.run(["scp", "-q", f"{b.ssh}:{newest}",
                                os.path.join(self.out, name + ".png")], timeout=60)
        except Exception as exc:                             # noqa: BLE001
            print("      (no screenshot: %s)" % exc)


# ---------------------------------------------------------------------------

def focus_button(box: Box, label: str) -> bool:
    for key in ("Left",) * 3 + ("Right",) * 3:
        if box.label("System.CurrentControl") == label:
            return True
        box.key(key, pause=0.4)
    return box.label("System.CurrentControl") == label


def answer_dialogs(box: Box) -> str:
    """Kodi's own Yes/No prompts: tofa's font install (Install, then Kodi
    restarts) and CoreELEC's reboot offer (always No). Matched on text."""
    if not box.cond("Window.IsActive(yesnodialog)"):
        return ""
    text = box.label("Control.GetLabel(9)")
    if "reboot" in text.lower():
        if focus_button(box, "No") and box.select_if("Window.IsActive(yesnodialog)"):
            return "answered CoreELEC's reboot prompt: No"
    elif "tofa needs to make these changes" in text:
        if focus_button(box, "Install") and box.select_if("Window.IsActive(yesnodialog)"):
            time.sleep(15)
            box.wait(lambda: box.rpc("JSONRPC.Ping", timeout=4) == "pong", 180, 3)
            time.sleep(25)
            return "installed tofa's fonts (Kodi restarted)"
    return "left a Yes/No dialog alone: " + text[:80].replace("\n", " / ")


def in_exit_dialog(b: Box) -> bool:
    # Read the dialog's own list: tofa_dialog can outlive the dialog.
    return (b.label("System.CurrentControlId") == "100" and b.label("Container(100).ListItem.Label")
            in ("Exit tofa", "Minimize", "Cancel"))


def exit_tofa(b: Box) -> bool:
    """Back out to the "Exit tofa" confirmation and select it, by its text;
    a second Back would only cancel it."""
    for _ in range(6):
        if in_exit_dialog(b):
            b.wait(lambda: b.label("Container(100).ListItem.Label") == "Exit tofa"
                   or b.key("Up"), 4, 0.4)
            if not b.select_if("String.IsEqual(Container(100).ListItem.Label,Exit tofa)"):
                return False
            return bool(b.wait(lambda: b.label("Window.Property(tofa_window)") in ("", "SplashWindow")
                               and not in_exit_dialog(b), 15))
        # Favourites keeps reading a stale "SplashWindow" once tofa is gone.
        if b.label("Window.Property(tofa_window)") in ("", "SplashWindow"):
            return True
        b.key("Back", pause=1.8)
    return False


def launch(run: Run, switch_profile: str | None) -> bool:
    b = run.box
    if not exit_tofa(b):
        return run.check("tofa: a running copy exits first", False)
    print("      " + (answer_dialogs(b) or "no dialog at start"))
    window = None
    for _ in range(2):
        b.builtin("RunScript(plugin.video.tofa)")
        events = []
        window = b.wait(lambda: b.label("Window.Property(tofa_window)") not in ("", "SplashWindow")
                        and b.label("Window.Property(tofa_window)")
                        or b.dialog() == "ProfileDialog" and "ProfileDialog"
                        or events.append(answer_dialogs(b))
                        or any("restarted" in (e or "") for e in events) and "restarted", 120, 1)
        for event in filter(None, events):
            print("      " + event)
        if window != "restarted":
            break
    if window == "ProfileDialog":
        return pick_profile(run, switch_profile)
    return run.check("tofa opens on Home", window == "MainWindow", repr(window))


def pick_profile(run: Run, allowed: str) -> bool:
    """The gate at launch: only with --switch-profile, onto that profile."""
    b = run.box
    if not allowed:
        return run.check("tofa opens on Home", False,
                         "Who's watching came up; rerun with --switch-profile NAME")
    for _ in range(9):
        if b.label("System.CurrentControl") == allowed:
            b.key("Select")
            break
        b.key("Right")
    ok = b.wait(lambda: b.label("Window.Property(tofa_window)") == "MainWindow", 40)
    return run.check(f"tofa opens on Home as {allowed}", ok)


def to_section(b: Box, name: str) -> bool:
    """Up to the top bar, then along it to `name` ("Home" ... "Settings").
    Back only closes an open Browse view; at the top level it asks to exit."""
    order = ["Home", "Browse", "Discover", "Search", "Settings"]
    for _ in range(16):
        here = b.label("System.CurrentControl")
        # browse_collections names the loaded source, not an open view.
        if b.label("Window.Property(browse_view)"):
            b.key("Back", pause=1.2)
        elif b.cond("Control.HasFocus(3000)") and here in order:
            if here == name:
                return True
            b.key("Right" if order.index(name) > order.index(here) else "Left", pause=0.8)
        else:
            b.key("Up", pause=0.6)
    return b.cond("Control.HasFocus(3000)") and b.label("System.CurrentControl") == name


def test_home(run: Run):
    b = run.box
    # tofa reopens on the last section of this Kodi run, not always Home.
    run.check("Home: reached", to_section(b, "Home"))
    ok = b.wait(lambda: b.label("Window.Property(row0_title)"), 40)
    run.check("Home: the first row loaded", ok, repr(ok))
    run.shot("01-home")


def into_tiles(b: Box) -> bool:
    """Down from the top bar once the landing has its tiles (slow at first)."""
    b.wait(lambda: b.num_items(6020) > 0, 30)
    return bool(b.wait(lambda: b.cond("Control.HasFocus(6020)") or b.key("Down", pause=1), 8, 0.5))


def walk_tiles(b: Box):
    """Every landing tile in order, as (label, wall mode): top-left first,
    four to a row, focus left on the last tile."""
    b.wait(lambda: b.cond("Control.HasFocus(6020)"), 5)
    b.key("Left", times=4, pause=0.3)
    if int(b.label("Container(6020).CurrentItem") or 1) > 4:
        b.key("Up")
    seen = []
    for row in range(3):
        for col in range(4):
            label = b.label("System.CurrentControl")
            if label in [t for t, _ in seen]:
                return seen
            seen.append((label, b.wait(lambda: b.label("Window.Property(browse_wall)"), 12) or ""))
            if col < 3:
                b.key("Right", pause=0.8)
        b.key("Down", pause=0.6)
        b.key("Left", times=3, pause=0.3)
    return seen


def go_to_tile(b: Box, name: str) -> bool:
    b.key("Left", times=4, pause=0.3)
    b.key("Up") if int(b.label("Container(6020).CurrentItem") or 1) > 4 else None
    for _ in range(2):
        for _ in range(4):
            if b.label("System.CurrentControl") == name:
                return True
            b.key("Right", pause=0.4)
        b.key("Down", pause=0.4)
        b.key("Left", times=3, pause=0.3)
    return b.label("System.CurrentControl") == name


def test_browse(run: Run):
    b = run.box
    run.check("Browse: reached from the top bar", to_section(b, "Browse"))
    if not run.check("Browse: the landing's tiles have focus", into_tiles(b),
                     b.label("System.CurrentControl")):
        return
    walls = dict(walk_tiles(b))
    first = next(iter(walls), "")
    run.check("Browse: a library tile shows the tilted wall", walls.get(first) == "tilt", repr(walls))
    run.check("Browse: Watchlist and History show a poster row",
              walls.get("Watchlist") in ("row", "") and walls.get("History") == "row", repr(walls))
    run.check("Browse: Collections features a collection", walls.get("Collections") == "feature", repr(walls))
    run.check("Browse: Surprise me shows the blurred wall", walls.get("Surprise me") == "tilt", repr(walls))
    run.shot("02-browse-landing")
    # The first tile's view.
    go_to_tile(b, first)
    b.select_if("Control.HasFocus(6020)")
    run.check("Browse: a library view opens", b.wait(lambda: b.label("Window.Property(browse_view)") == "1", 10))
    run.check("Browse: its grid fills", b.wait(lambda: b.num_items(6200) > 0, 30), str(b.num_items(6200)))
    run.shot("03-browse-grid")
    # The sort menu over the view.
    b.wait(lambda: b.cond("Control.HasFocus(6110)") or b.key("Up"), 8, 0.4)
    b.select_if("Control.HasFocus(6110)")
    run.check("Browse: the sort menu opens", b.wait(lambda: b.label("Window.Property(browse_sort_open)") == "1", 5))
    run.check("Browse: it lists the sorts", b.wait(lambda: b.num_items(6230) >= 3, 5), str(b.num_items(6230)))
    b.back_if("!String.IsEmpty(Window.Property(browse_sort_open))")
    run.check("Browse: Back closes the sort menu", b.wait(lambda: not b.label("Window.Property(browse_sort_open)"), 5))
    b.back_if("!String.IsEmpty(Window.Property(browse_view))")
    run.check("Browse: Back returns to the tiles", b.wait(lambda: not b.label("Window.Property(browse_view)"), 5))


def open_tile(b: Box, name: str) -> bool:
    return go_to_tile(b, name) and b.select_if("Control.HasFocus(6020)")


def test_collections(run: Run):
    b = run.box
    run.check("Collections: tile found", open_tile(b, "Collections"))
    run.check("Collections: the view opens", b.wait(lambda: b.label("Window.Property(browse_collections)") == "1", 15))
    run.check("Collections: film series load", b.wait(lambda: b.num_items(6210) > 0, 30), str(b.num_items(6210)))
    run.shot("04-collections")
    b.wait(lambda: b.cond("Control.HasFocus(6210)") or b.key("Down"), 6, 0.6)
    b.select_if("Control.HasFocus(6210)")
    run.check("Collections: a series opens its films",
              b.wait(lambda: not b.label("Window.Property(browse_collections)") and b.num_items(6200) > 0, 20),
              str(b.num_items(6200)))
    b.back_if("!String.IsEmpty(Window.Property(browse_view))")
    run.check("Collections: Back returns to the series",
              b.wait(lambda: b.label("Window.Property(browse_collections)") == "1", 10))
    b.back_if("!String.IsEmpty(Window.Property(browse_view))")
    b.wait(lambda: not b.label("Window.Property(browse_view)"), 5)


def test_history(run: Run):
    b = run.box
    run.check("History: tile found", open_tile(b, "History"))
    run.check("History: the grid fills", b.wait(lambda: b.num_items(6200) > 0, 20), str(b.num_items(6200)))
    run.check("History: sorted by Last Watched",
              "Last Watched" in b.label("Window.Property(browse_chip_6110_label)"),
              b.label("Window.Property(browse_chip_6110_label)"))
    b.back_if("!String.IsEmpty(Window.Property(browse_view))")
    b.wait(lambda: not b.label("Window.Property(browse_view)"), 5)


def test_discover(run: Run):
    b = run.box
    run.check("Discover: reached", to_section(b, "Discover"))
    ok = b.wait(lambda: b.label("Window.Property(discover_row0_title)"), 40)
    run.check("Discover: the first shelf loaded", ok, repr(ok))
    run.shot("05-discover")


def test_search(run: Run):
    b = run.box
    run.check("Search: reached", to_section(b, "Search"))
    b.builtin("SetFocus(6701)")
    time.sleep(1)
    b.rpc("Input.SendText", {"text": "babylon", "done": False})
    time.sleep(0.5)
    b.key("Left")  # tofa reads the field on a key, and SendText sends none
    ok = b.wait(lambda: b.num_items(6805) > 0 or b.num_items(6830) > 0, 20)
    run.check("Search: results for a typed query", ok,
              f"top={b.num_items(6805)} shows={b.num_items(6830)}")
    run.shot("06-search")


def test_settings(run: Run) -> str:
    b = run.box
    run.check("Settings: reached", to_section(b, "Settings"))
    b.wait(lambda: b.cond("Control.HasFocus(8000)") or b.key("Down", pause=1), 8, 0.5)
    b.key("Left", times=6, pause=0.5)
    pages = []
    for _ in range(6):
        pages.append(b.wait(lambda: b.label("Window.Property(settings_page)"), 5) or "")
        b.key("Right", pause=0.8)
    run.check("Settings: all six tabs open",
              pages == ["account", "playback", "audio", "appearance", "home", "privacy"], repr(pages))
    b.key("Left", times=6, pause=0.5)
    profile = b.label("Window.Property(settings_profile_name)")
    run.check("Settings: the account names the profile", profile, repr(profile))
    run.shot("07-settings-account")
    # Who's watching from Switch Profile, then Cancel.
    b.key("Down", pause=0.8)
    if b.label("System.CurrentControl") != "Switch Profile":
        run.check("Who's watching: Switch Profile under the tabs", False, b.label("System.CurrentControl"))
        return profile
    b.key("Select")
    opened = b.wait(lambda: b.dialog() == "ProfileDialog", 15)
    run.check("Who's watching: opens", opened)
    run.check("Who's watching: lists the profiles", b.wait(lambda: b.num_items(800) > 0, 10),
              str(b.num_items(800)))
    run.shot("08-whos-watching")
    b.back_if("String.IsEqual(Window.Property(tofa_dialog),ProfileDialog)"
              " + Integer.IsGreater(Container(800).NumItems,0)")
    run.check("Who's watching: Back closes it", b.wait(lambda: not b.dialog(), 10))
    return profile


def test_title_and_person(run: Run):
    b = run.box
    run.check("Title page: from the TV library", to_section(b, "Browse") and into_tiles(b))
    if not run.check("Title page: the TV Shows tile", go_to_tile(b, "TV Shows"),
                     b.label("System.CurrentControl")):
        return
    b.select_if("Control.HasFocus(6020)")
    b.wait(lambda: b.num_items(6200) > 0, 30)
    b.wait(lambda: b.cond("Control.HasFocus(6200)") or b.key("Down"), 6, 0.6)
    b.select_if("Control.HasFocus(6200)")
    ok = b.wait(lambda: b.label("Window.Property(tofa_window)") == "DetailWindow", 20)
    run.check("Title page: opens", ok)
    run.shot("09-title")
    b.key("Down", pause=1.5)
    run.check("Title page: episodes load", b.wait(lambda: b.num_items(6410) > 0, 20), str(b.num_items(6410)))
    b.wait(lambda: b.cond("Control.HasFocus(6200)") or b.key("Down"), 8, 1.0)
    run.check("Title page: cast loads", b.wait(lambda: b.num_items(6200) > 0, 10), str(b.num_items(6200)))
    b.select_if("Control.HasFocus(6200)")
    ok = b.wait(lambda: b.label("Window.Property(tofa_window)") == "PersonWindow", 20)
    run.check("Person page: opens", ok)
    credits = b.wait(lambda: b.label("Window.Property(person_credits)"), 30)
    run.check("Person page: credits counted", credits, repr(credits))
    run.shot("10-person")
    b.wait(lambda: b.cond("Control.HasFocus(8020)") or b.key("Left"), 5, 0.5)
    b.select_if("Control.HasFocus(8020)")
    run.check("Person page: Filmography opens",
              b.wait(lambda: b.label("Window.Property(person_film_open)") == "1", 5))
    b.back_if("!String.IsEmpty(Window.Property(person_film_open))")
    b.back_if("String.IsEqual(Window.Property(tofa_window),PersonWindow)", pause=1.5)
    run.check("Person page: Back returns to the title page",
              b.wait(lambda: b.label("Window.Property(tofa_window)") == "DetailWindow", 10))
    b.back_if("String.IsEqual(Window.Property(tofa_window),DetailWindow)", pause=1.5)
    b.back_if("String.IsEqual(Window.Property(tofa_window),DetailWindow)", pause=1.5)


def test_playback(run: Run):
    """Play the first film in the Movies grid for a while, pause, and see the
    pause screen arrive (its default is on); then stop."""
    b = run.box
    to_section(b, "Browse")
    into_tiles(b)
    if not run.check("Playback: the Movies tile", open_tile(b, "Movies")):
        return
    b.wait(lambda: b.num_items(6200) > 0, 30)
    b.wait(lambda: b.cond("Control.HasFocus(6200)") or b.key("Down"), 6, 0.6)
    b.select_if("Control.HasFocus(6200)")
    b.wait(lambda: b.label("Window.Property(tofa_window)") == "DetailWindow", 20)
    if not run.check("Playback: Play has focus on the title page",
                     b.wait(lambda: b.cond("Control.HasFocus(5210)"), 10)):
        return
    b.key("Select")
    playing = b.wait(lambda: b.rpc("Player.GetActivePlayers"), 45, 1)
    if not run.check("Playback: starts", playing):
        return
    time.sleep(12)
    t0 = b.rpc("Player.GetProperties", {"playerid": 1, "properties": ["time"]})["time"]
    time.sleep(5)
    t1 = b.rpc("Player.GetProperties", {"playerid": 1, "properties": ["time"]})["time"]
    secs = lambda t: t["hours"] * 3600 + t["minutes"] * 60 + t["seconds"]  # noqa: E731
    run.check("Playback: time advances", secs(t1) - secs(t0) >= 3, f"{secs(t0)} -> {secs(t1)}")
    run.shot("11-playing")
    b.rpc("Player.PlayPause", {"playerid": 1, "play": False})
    run.check("Playback: pauses", b.wait(lambda: b.label("Window.Property(player_state)") == "paused", 5))
    card = b.wait(lambda: b.label("Window.Property(player_pause_card)") == "1", 20)
    run.check("Playback: the pause screen arrives", card)
    run.shot("12-pause-screen")
    b.rpc("Player.PlayPause", {"playerid": 1, "play": True})
    run.check("Playback: resumes", b.wait(lambda: b.label("Window.Property(player_state)") == "playing", 5))
    b.rpc("Player.Stop", {"playerid": 1})
    run.check("Playback: stops back to the title page",
              b.wait(lambda: not b.rpc("Player.GetActivePlayers")
                     and b.label("Window.Property(tofa_window)") == "DetailWindow", 30))
    b.back_if("String.IsEqual(Window.Property(tofa_window),DetailWindow)", pause=1.5)
    b.back_if("String.IsEqual(Window.Property(tofa_window),DetailWindow)", pause=1.5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", required=True)
    ap.add_argument("--ssh", required=True, help="ssh host alias, for kodi.log and screenshots")
    ap.add_argument("--auth", help="user:password for JSON-RPC")
    ap.add_argument("--test-profile", action="append", default=[],
                    help="a profile playback may run on (repeatable)")
    ap.add_argument("--play", action="store_true", help="play a title, on a --test-profile only")
    ap.add_argument("--switch-profile", metavar="NAME",
                    help="at a Who's watching gate, pick this profile")
    ap.add_argument("--out", default="/tmp/tofa-e2e")
    ap.add_argument("--exit", action="store_true", help="only exit a running tofa (before a deploy)")
    args = ap.parse_args()
    if args.exit:
        return 0 if exit_tofa(Box(args.host, args.ssh, args.auth)) else 1
    out = os.path.join(args.out, args.host)
    os.makedirs(out, exist_ok=True)
    box = Box(args.host, args.ssh, args.auth)
    run = Run(box, out)
    started = time.time()
    log_from = int(box.sh(f"stat -c %s {LOG}").strip() or 0)
    version = box.sh("grep -m1 -o 'version=\"[0-9.]*\"' /storage/.kodi/addons/plugin.video.tofa/addon.xml")
    print(f"box {args.host}: Kodi {box.label('System.BuildVersion')}, add-on {version.strip()}")

    if launch(run, args.switch_profile):
        for step in (test_home, test_browse, test_collections, test_history, test_discover,
                     test_search):
            try:
                step(run)
            except Exception as exc:                         # noqa: BLE001
                run.check(f"{step.__name__}: ran to the end", False, repr(exc))
        profile = ""
        try:
            profile = test_settings(run)
            test_title_and_person(run)
        except Exception as exc:                             # noqa: BLE001
            run.check("settings/title: ran to the end", False, repr(exc))
        if args.play and profile in args.test_profile:
            try:
                test_playback(run)
            except Exception as exc:                         # noqa: BLE001
                run.check("playback: ran to the end", False, repr(exc))
        elif args.play:
            print(f"      skipped playback: {profile!r} is not a test profile")

    tail = box.sh(f"tail -c +{log_from + 1} {LOG}")
    errors = [line for line in tail.splitlines()
              if ("error <general>" in line.lower() or "Traceback" in line)
              and ("tofa" in line.lower() or "Traceback" in line)]
    run.check("kodi.log: no error from tofa during the run", not errors, "\n      ".join(errors[:8]))
    rss = box.sh("grep VmRSS /proc/$(pidof kodi.bin)/status").strip()
    failed = [r for r in run.results if not r[1]]
    print(f"\n{len(run.results) - len(failed)}/{len(run.results)} passed in "
          f"{time.time() - started:.0f}s; {rss}; screenshots in {out}")
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump({"results": run.results, "log_errors": errors, "rss": rss}, fh, indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
