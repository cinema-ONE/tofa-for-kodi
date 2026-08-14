#!/usr/bin/env python3
"""Drive the local Kodi from a shell, for live-verifying the window UI.

Supports the Homebrew build on macOS and the flatpak on Linux; $KODI_DATA,
$KODI_LOG, $KODI_RPC and $KODI_SHOTS override the auto-detected paths.

Written after the 2026-08-01 player session, where several "verified" claims
turned out to be wrong. Every one of those checks drove the add-on's
*pluginsource* entry point, so what got screenshotted was Kodi's own Videos
window rather than the tofa window UI. The three rules this tool exists to
enforce:

1. **Launch through the script entry.** `launch` runs `RunScript(
   plugin.video.tofa)` via the companion `script.tofa.harness` add-on, which is
   the same door the Program add-ons tile uses. See harness.py for why a second
   add-on is needed at all.
2. **Assert the frontmost window before and after every step.** Kodi reports
   `System.CurrentWindow` as "System" for *every* Python WindowXML, so it can
   neither tell our screens apart nor tell them from Kodi's own System window.
   The signal that actually works is `Window.Property(tofa_window)`, set by
   `XMLBase.onInit` to the screen's class name: measured live, Kodi's own Home
   and Settings both leave it empty. `press` refuses to continue the moment it
   goes empty, because focus has escaped and whatever follows would be
   measuring the wrong screen.
3. **Prove Python is alive before trusting anything.** Kodi's Python engine can
   wedge on cold boot -- scripts log "start processing" and then hang forever,
   and *every* later invocation queues behind them. Kodi still answers
   JSON-RPC, still screenshots, still navigates its own UI, so nothing looks
   broken; the add-on simply never runs. `ready` round-trips a no-op through
   the harness and fails loudly instead.

Usage:
    kodictl.py ready [--timeout 60]     wait for RPC + a proven-live Python
    kodictl.py restart                  kill, relaunch, wait ready
    kodictl.py launch [--timeout 30]    open the tofa window UI, assert it stuck
    kodictl.py state                    frontmost window, focused control
    kodictl.py press left [--times 3]   navigate, asserting window before/after
    kodictl.py info System.CurrentWindow ...
    kodictl.py builtin 'ActivateWindow(Home)'
    kodictl.py shot [name]              screenshot, copied to a stable path
    kodictl.py log [--lines 40] [--grep tofa]
    kodictl.py stop
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RPC_URL = os.environ.get("KODI_RPC", "http://localhost:8080/jsonrpc")

# Kodi's data dir, log path, process name and launch command all depend on how
# it was installed. Dev moved from a Linux flatpak to a Homebrew build on macOS
# (2026-08-07); support both, and let $KODI_DATA / $KODI_LOG override for any
# third layout (a native Linux package, say). The bracket in each PKILL_PATTERN
# keeps pgrep/pkill from matching their own command line and killing the
# calling shell before they reach Kodi.
if sys.platform == "darwin":
    _DEFAULT_DATA = os.path.expanduser("~/Library/Application Support/Kodi")
    _DEFAULT_LOG = os.path.expanduser("~/Library/Logs/kodi.log")
    PKILL_PATTERN = r"[K]odi\.app/Contents/MacOS/Kodi"
    START_CMD = ["open", "-a", "Kodi"]
else:
    _DEFAULT_DATA = os.path.expanduser("~/.var/app/tv.kodi.Kodi/data")
    _DEFAULT_LOG = os.path.join(_DEFAULT_DATA, "temp/kodi.log")
    PKILL_PATTERN = r"[k]odi\.bin"
    START_CMD = ["setsid", "flatpak", "run", "tv.kodi.Kodi"]

KODI_DATA = os.environ.get("KODI_DATA", _DEFAULT_DATA)
KODI_LOG = os.environ.get("KODI_LOG", _DEFAULT_LOG)
ADDON_ID = "plugin.video.tofa"
HARNESS_ID = "script.tofa.harness"
SHOT_DIR = os.environ.get("KODI_SHOTS", "/tmp/kodi-tofa-shots")

# Kodi stops answering SIGTERM once its Python engine is wedged, which is
# exactly when a restart is most needed, so stop_kodi escalates to SIGKILL.


class Failed(Exception):
    """A precondition the caller must not paper over."""


# --------------------------------------------------------------------------- rpc


def rpc(method: str, params: dict | None = None, timeout: float = 10.0):
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    ).encode()
    req = urllib.request.Request(
        RPC_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    if "error" in body:
        raise Failed(f"{method}: {body['error']}")
    return body["result"]


def rpc_alive(timeout: float = 3.0) -> bool:
    try:
        return rpc("JSONRPC.Ping", timeout=timeout) == "pong"
    except (urllib.error.URLError, OSError, Failed, TimeoutError):
        return False


def info(*labels: str) -> dict[str, str]:
    """Read info labels, insisting on a usable answer.

    Kodi answers GetInfoLabels with a bare `null` while it is shutting down,
    and letting that through turns "Kodi is gone" into a TypeError several
    frames away from the cause -- which is exactly the kind of misleading
    failure this tool exists to stop."""
    try:
        result = rpc("XBMC.GetInfoLabels", {"labels": list(labels)})
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise Failed(f"Kodi stopped answering: {exc}") from None
    if not isinstance(result, dict):
        raise Failed(f"Kodi returned no info labels ({result!r}); it is probably shutting down")
    return result


# ----------------------------------------------------------------- kodi process


def kodi_pid() -> str | None:
    out = subprocess.run(
        ["pgrep", "-f", PKILL_PATTERN], capture_output=True, text=True
    ).stdout.split()
    return out[0] if out else None


def stop_kodi() -> None:
    if kodi_pid() is None:
        return
    subprocess.run(["pkill", "-f", PKILL_PATTERN])
    for _ in range(10):
        time.sleep(1)
        if kodi_pid() is None:
            return
    subprocess.run(["pkill", "-9", "-f", PKILL_PATTERN])
    for _ in range(10):
        time.sleep(1)
        if kodi_pid() is None:
            return
    raise Failed("Kodi would not die, even with SIGKILL")


def start_kodi() -> None:
    subprocess.Popen(
        START_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


# ------------------------------------------------------------------- harness


def _log_size() -> int:
    try:
        return os.path.getsize(KODI_LOG)
    except OSError:
        return 0


def _log_since(offset: int) -> str:
    try:
        with open(KODI_LOG, "rb") as fh:
            fh.seek(offset)
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def builtin(command: str, timeout: float = 20.0) -> None:
    """Run a Kodi builtin, and confirm the harness script actually reached it.

    Kodi's JSON-RPC answers "OK" the instant the request is queued -- long
    before, and regardless of whether, any Python runs. Waiting for the
    harness's own log line is the only honest confirmation.
    """
    offset = _log_size()
    rpc(
        "Addons.ExecuteAddon",
        {
            "addonid": HARNESS_ID,
            "params": {"builtin": urllib.parse.quote(command, safe="")},
        },
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if "TOFAHARNESS done" in _log_since(offset):
            return
        time.sleep(0.3)
    raise Failed(
        f"harness never ran {command!r} within {timeout:.0f}s.\n"
        "Kodi's Python engine is wedged: scripts log 'start processing' and "
        "hang, and every later invocation queues behind them. Run "
        "`kodictl.py restart`."
    )


def wait_ready(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not rpc_alive():
        time.sleep(1)
    if not rpc_alive():
        raise Failed(f"no JSON-RPC on {RPC_URL} after {timeout:.0f}s")
    # RPC binds several seconds before the Python engine is usable; a no-op
    # round trip through the harness is the actual readiness signal.
    builtin("NoOp", timeout=max(10.0, deadline - time.time()))


# --------------------------------------------------------------- window checks


def tofa_window() -> str:
    """The tofa screen class currently frontmost, or "" if none is.

    A tofa dialog counts. Kodi resolves Window.Property against the topmost
    window, so while one of our own pickers is up the screen underneath it
    reads as empty -- which is not focus escaping to Kodi, it is our own UI
    one layer further in, and treating it as an escape would make every step
    that opens a picker look like a failure."""
    labels = info("Window.Property(tofa_window)", "Window.Property(tofa_dialog)")
    return (labels["Window.Property(tofa_window)"]
            or labels["Window.Property(tofa_dialog)"])


def assert_tofa_window(when: str) -> str:
    screen = tofa_window()
    if not screen:
        kodi_window = info("System.CurrentWindow")["System.CurrentWindow"]
        raise Failed(
            f"{when}: no tofa screen is frontmost -- Kodi is showing its own "
            f"{kodi_window!r}. Anything measured from here would be measuring "
            "the wrong screen."
        )
    return screen


def wait_for_tofa_window(timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        screen = tofa_window()
        if screen:
            # Don't return on first sight: the plugin route lets Kodi's Videos
            # window finish navigating into plugin:// and take focus back a
            # moment later, which is exactly the failure this tool exists to
            # catch. Require the screen to still be there a second on.
            time.sleep(1.0)
            if tofa_window() == screen:
                return screen
        time.sleep(0.5)
    kodi_window = info("System.CurrentWindow")["System.CurrentWindow"]
    raise Failed(f"no tofa window after {timeout:.0f}s (Kodi shows {kodi_window!r})")


def state() -> dict[str, str]:
    labels = info(
        "System.CurrentWindow",
        "System.CurrentControlId",
        "System.CurrentControl",
        "Window.Property(tofa_window)",
        "Window.Property(tofa_dialog)",
        "Player.Filenameandpath",
    )
    screen = labels["Window.Property(tofa_window)"]
    if not screen and labels["Window.Property(tofa_dialog)"]:
        screen = "(under a tofa dialog)"
    out = {
        "screen": screen or f"(none -- Kodi's {labels['System.CurrentWindow']})",
        "control_id": labels["System.CurrentControlId"],
        "control": labels["System.CurrentControl"],
        "playing": labels["Player.Filenameandpath"] or "-",
    }
    # A dialog is a state OF a screen, not a screen -- a picker over the
    # player still means the player is what is up.
    if labels["Window.Property(tofa_dialog)"]:
        out["dialog"] = labels["Window.Property(tofa_dialog)"]
    return out


def notify(message: str, data: str | None = None, *,
           sender: str = ADDON_ID) -> dict:
    """Send the notification the add-on's own listeners answer.

    Kodi's JSON-RPC method list is compiled in, so an add-on cannot register
    a method of its own; `JSONRPC.NotifyAll` is the one channel that carries
    arbitrary add-on messages. Kodi prefixes the message with `Other.` on the
    way through, and hands `data` to the receiver as a JSON STRING -- both
    measured on a live Kodi, both surprising enough to be worth saying twice.

    `data` may be JSON (`'{"mode":"panel"}'`) or a bare word (`panel`), which
    is quoted into a JSON string for you -- the add-on accepts either.
    """
    payload: Any = None
    if data:
        try:
            payload = json.loads(data)
        except ValueError:
            payload = data          # a bare word; the receiver accepts it
    params: dict[str, Any] = {"sender": sender, "message": message}
    if payload is not None:
        params["data"] = payload
    rpc("JSONRPC.NotifyAll", params)
    return {"sent": params}


def focus(control_id: int, select: bool = False, settle: float = 0.4) -> dict:
    """Put focus straight on a control, instead of walking there with the d-pad.

    Written 2026-08-11, after a verification run on the episode drawer spent
    more presses missing the target than hitting it. **The player's chrome
    auto-hides in 4.0 seconds** (CHROME_AUTO_HIDE_S), and one `press` costs
    over a second of process start-up, so any target more than two hops away
    is a race you lose: the chrome goes down mid-walk, the next arrow means
    `quick_seek` on the bare surface instead of a move, and focus ends up
    somewhere unrelated. `seq` helps only if you already know the exact hop
    count -- and exploring to FIND that count is the part that keeps failing.

    `SetFocus(id)` sidesteps the walk entirely. Two things to know:

    - **The control must be visible.** Kodi refuses focus to a control in a
      group whose visibility condition is false, and says nothing about it --
      the same silent refusal behind the panel-focus bug in PR #30. So reveal
      the chrome first (`seq up`) when the target lives in it, and check the
      returned control_id rather than assuming.
    - **It targets the ACTIVE window**, which during playback is the player
      DIALOG, not the window under it.

    Returns the post-focus state, so a caller can assert on it."""
    builtin(f"SetFocus({control_id})")
    time.sleep(settle)
    landed = state()
    if landed.get("control_id") != str(control_id):
        raise Failed(
            f"focus did not land on {control_id} (it is on "
            f"{landed.get('control_id') or 'nothing'}). The usual cause is "
            f"that the control is not visible yet -- reveal its container "
            f"first; Kodi refuses focus to a hidden control silently.")
    if select:
        builtin("Action(select)")
        time.sleep(settle)
        landed = state()
    return landed


# ------------------------------------------------------------------ screenshot


def screenshot(name: str | None = None) -> str:
    try:
        raw = rpc("Settings.GetSettingValue", {"setting": "debug.screenshotpath"})
        shot_dir = raw["value"] if isinstance(raw, dict) else raw
    except Failed:
        shot_dir = None
    if not shot_dir or not os.path.isdir(shot_dir):
        raise Failed("Kodi's debug.screenshotpath is unset or missing")

    before = _newest(shot_dir)
    rpc("Input.ExecuteAction", {"action": "screenshot"})
    deadline = time.time() + 10
    while time.time() < deadline:
        newest = _newest(shot_dir)
        if newest and newest != before and _fully_written(newest):
            os.makedirs(SHOT_DIR, exist_ok=True)
            target = os.path.join(SHOT_DIR, f"{name or 'shot'}.png")
            shutil.copy2(newest, target)
            return target
        time.sleep(0.3)
    raise Failed("Kodi saved no new screenshot within 10s")


def _fully_written(path: str) -> bool:
    """The file appears the moment Kodi opens it, empty and still growing."""
    first = os.path.getsize(path)
    if first == 0:
        return False
    time.sleep(0.2)
    return os.path.getsize(path) == first


def _newest(directory: str) -> str | None:
    shots = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.startswith("screenshot") and f.endswith(".png")
    ]
    return max(shots, key=os.path.getmtime) if shots else None


# ----------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ready", help="wait for RPC and a proven-live Python")
    p.add_argument("--timeout", type=float, default=90)
    sub.add_parser("stop", help="stop Kodi")
    p = sub.add_parser("restart", help="stop, start, wait ready")
    p.add_argument("--timeout", type=float, default=90)
    p = sub.add_parser("launch", help="open the tofa window UI via the script entry")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--force", action="store_true", help="open even if one is up")
    sub.add_parser("state", help="frontmost window and focused control")
    p = sub.add_parser("press", help="send an input action, asserting the window")
    p.add_argument("action")
    p.add_argument("--times", type=int, default=1)
    p.add_argument("--settle", type=float, default=0.6)
    p.add_argument(
        "--any-window",
        action="store_true",
        help="skip the tofa-window assertion (for steps that leave it on purpose)",
    )
    p = sub.add_parser("seq", help="send several actions in one run, asserting each")
    p.add_argument("actions", nargs="+")
    p.add_argument("--settle", type=float, default=0.35)
    p.add_argument("--any-window", action="store_true")
    p = sub.add_parser("info", help="read info labels")
    p.add_argument("labels", nargs="+")
    p = sub.add_parser("builtin", help="run a Kodi builtin via the harness")
    p.add_argument("command")
    p = sub.add_parser(
        "notify", help="send a JSONRPC.NotifyAll the add-on listens for")
    p.add_argument("message", help='e.g. "stats"')
    p.add_argument("data", nargs="?",
                   help='JSON object, or a bare word: panel / pill / off / cycle')
    p.add_argument("--sender", default="plugin.video.tofa")
    p = sub.add_parser("focus", help="focus a control by id, no d-pad walking")
    p.add_argument("control_id", type=int)
    p.add_argument(
        "--select", action="store_true", help="press it once focus has landed")
    p.add_argument("--settle", type=float, default=0.4)
    p = sub.add_parser("shot", help="screenshot to a stable path")
    p.add_argument("name", nargs="?")
    p = sub.add_parser("log", help="tail kodi.log")
    p.add_argument("--lines", type=int, default=40)
    p.add_argument("--grep")

    args = parser.parse_args()

    try:
        if args.cmd == "ready":
            wait_ready(args.timeout)
            print("ready: RPC up, Python proven live")

        elif args.cmd == "stop":
            stop_kodi()
            print("stopped")

        elif args.cmd == "restart":
            was = kodi_pid()
            stop_kodi()
            start_kodi()
            wait_ready(args.timeout)
            now = kodi_pid()
            if now is None or now == was:
                raise Failed(
                    f"pid did not change ({was} -> {now}); you are driving the "
                    "old instance, and its windows still hold their cached XML"
                )
            print(f"restarted: pid {was} -> {now}, Python proven live")

        elif args.cmd == "launch":
            already = tofa_window()
            if already and not args.force:
                # Every launch builds a fresh window, and Kodi's add-on window
                # id pool is small and never reclaimed within a session --
                # exhausting it bricks the add-on until Kodi restarts, which is
                # what the reverted BackgroundWindow work ran into. Stacking a
                # second copy on top of a live one is never what a test wants.
                raise Failed(
                    f"{already} is already open; use `restart` for a clean "
                    "slate, or --force to stack another window on top"
                )
            builtin(f"RunScript({ADDON_ID})")
            wait_for_tofa_window(args.timeout)
            print(f"launched: {json.dumps(state())}")

        elif args.cmd == "state":
            print(json.dumps(state(), indent=2))

        elif args.cmd == "press":
            if not args.any_window:
                assert_tofa_window("before press")
            for n in range(args.times):
                rpc("Input.ExecuteAction", {"action": args.action})
                time.sleep(args.settle)
                if not args.any_window:
                    assert_tofa_window(f"after press {n + 1}/{args.times}")
            print(json.dumps(state()))

        elif args.cmd == "seq":
            # One process for the whole sequence. Per-press process startup
            # plus its RPC round trips costs over a second, which loses races
            # against anything on a timer -- the player's transport chrome
            # auto-hides after 4.0s, so a five-step walk across it never
            # finished when each step was its own invocation.
            for n, action in enumerate(args.actions):
                if not args.any_window:
                    assert_tofa_window(f"before {action} ({n + 1}/{len(args.actions)})")
                rpc("Input.ExecuteAction", {"action": action})
                time.sleep(args.settle)
            print(json.dumps(state()))

        elif args.cmd == "info":
            print(json.dumps(info(*args.labels), indent=2))

        elif args.cmd == "builtin":
            builtin(args.command)
            print(f"ran: {args.command}")

        elif args.cmd == "notify":
            print(json.dumps(notify(args.message, args.data, sender=args.sender)))

        elif args.cmd == "focus":
            print(json.dumps(focus(args.control_id, select=args.select,
                                   settle=args.settle)))

        elif args.cmd == "shot":
            print(screenshot(args.name))

        elif args.cmd == "log":
            text = _log_since(0).splitlines()
            if args.grep:
                text = [ln for ln in text if args.grep.lower() in ln.lower()]
            print("\n".join(text[-args.lines :]))

    except Failed as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
