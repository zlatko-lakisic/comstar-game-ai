#!/usr/bin/env python3
"""Verify synthetic keyboard/mouse input — Notepad baseline, Rome probes (hands-free)."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable

if sys.platform != "win32":
    print("FAIL: Windows only")
    raise SystemExit(1)

import win32api
import win32gui
import win32process

from comstar_game_ai.game_io.campaign.end_turn import end_turn_campaign
from comstar_game_ai.game_io.elevation import ensure_elevation_for_game, strip_elevation_marker
from comstar_game_ai.game_io.input.directinput import directinput_available, tap_key as pdi_tap
from comstar_game_ai.game_io.input.game_focus import game_input_session, post_vk_key, with_game_input
from comstar_game_ai.game_io.input.send_input import SendInputController, virtual_key_for
from comstar_game_ai.game_io.logs.turn_boundary import message_log_snapshot
from comstar_game_ai.game_io.window import find_game_window, process_elevation_matches
from comstar_game_ai.shared.config import load_config


def _find_notepad() -> int | None:
    result: list[int] = []

    def enum_handler(hwnd: int, _: int) -> None:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "Notepad":
            result.append(hwnd)

    win32gui.EnumWindows(enum_handler, 0)
    return result[0] if result else None


def _fg_title() -> str:
    return win32gui.GetWindowText(win32gui.GetForegroundWindow())


def _countdown(seconds: int, label: str) -> None:
    print(f"INFO {label} ({seconds}s)")
    for remaining in range(seconds, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)


def _client_points(hwnd: int) -> list[tuple[int, int]]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    w = max(right - left, 1)
    h = max(bottom - top, 1)
    norms = [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75), (0.5, 0.5)]
    pts: list[tuple[int, int]] = []
    for xn, yn in norms:
        pts.append(win32gui.ClientToScreen(hwnd, (int(w * xn), int(h * yn))))
    return pts


def _probe_mouse(hwnd: int, ctrl: SendInputController) -> None:
    """Sweep mouse across Rome so user can SEE whether injection works."""
    pts = _client_points(hwnd)
    print("INFO === mouse sweep — watch the cursor on Rome (no terminal clicks) ===")

    def sweep_sendinput() -> None:
        for sx, sy in pts:
            ctrl.move_mouse(sx, sy)
            time.sleep(0.35)

    def sweep_pdi() -> None:
        if not directinput_available():
            return
        import pydirectinput as pdi

        for sx, sy in pts:
            pdi.moveTo(sx, sy)
            time.sleep(0.35)

    with_game_input(hwnd, sweep_sendinput, activate_click=False)
    _countdown(2, "SendInput mouse sweep done")
    if directinput_available():
        print("INFO === pydirectinput mouse sweep ===")
        with_game_input(hwnd, sweep_pdi, activate_click=False)
        _countdown(2, "pydirectinput mouse sweep done")


def _probe_console_methods(hwnd: int, ctrl: SendInputController, *, gap_s: int = 4) -> int:
    """
    Hands-free probe: mouse first (visible), then key methods with gaps.
    No terminal prompts — leave Rome focused; report results in chat.
    """
    print("INFO leave Rome focused — do NOT click this terminal until DONE")
    print("INFO first check: can YOU open RomeShell with ` (or Shift+`) on the real keyboard?")
    print("INFO if physical ` does nothing: Feral launcher → Advanced → Enable console (RomeShell)")
    time.sleep(0.3)
    with game_input_session(hwnd):
        print(f"INFO foreground={_fg_title()!r}")

    _probe_mouse(hwnd, ctrl)

    methods: list[tuple[str, Callable[[], None]]] = []

    def scancode_grave() -> None:
        ctrl.tap_key("`", dwell_ms=100, hwnd=hwnd)

    methods.append(("scancode_grave", scancode_grave))

    def shift_grave() -> None:
        ctrl.chord_scancode("shift", "`", dwell_ms=100, hwnd=hwnd)

    methods.append(("shift+grave", shift_grave))

    if directinput_available():

        def pdi_grave() -> None:
            with_game_input(hwnd, lambda: pdi_tap("`"))

        methods.append(("pydirectinput_grave", pdi_grave))

        def pdi_shift_grave() -> None:
            def _run() -> bool:
                import pydirectinput as pdi

                pdi.keyDown("shiftleft")
                time.sleep(0.08)
                pdi.press("`")
                time.sleep(0.08)
                pdi.keyUp("shiftleft")
                return True

            with_game_input(hwnd, _run)

        methods.append(("pydirectinput_shift+grave", pdi_shift_grave))

    vk = virtual_key_for("`")
    if vk is not None:

        def post_msg() -> None:
            with_game_input(hwnd, lambda: post_vk_key(hwnd, vk), activate_click=True)

        methods.append(("postmessage", post_msg))

    names = [n for n, _ in methods]
    print(f"INFO will try {len(methods)} key methods: {', '.join(names)}")
    print("INFO watch Rome — note which attempt (if any) opens the console")

    for i, (name, fn) in enumerate(methods, start=1):
        if i > 1:
            ctrl.tap_key("`", dwell_ms=80, hwnd=hwnd)
            _countdown(gap_s, "next method soon — keep Rome focused")
        print(f"INFO === [{i}/{len(methods)}] {name} — sending NOW ===")
        fn()
        _countdown(gap_s, f"watching for console after {name}")

    print("DONE probe finished — you can look at the terminal again")
    print(f"INFO methods tried: {', '.join(names)}")
    print("INFO reply in chat with:")
    print("     1) did the mouse cursor move on Rome during the sweep?")
    print("     2) does physical ` / Shift+` open RomeShell for you?")
    print("     3) which synthetic method (if any) opened console?")
    return 0


def main() -> int:
    # Preserve elevation marker for ensure_*, but hide it from argparse.
    raw_argv = list(sys.argv)
    sys.argv = [sys.argv[0], *strip_elevation_marker()]

    parser = argparse.ArgumentParser(description="Test keyboard input (Notepad or Rome End Turn)")
    parser.add_argument("--seconds", type=int, default=5, help="Countdown before actuation")
    parser.add_argument("--rome", action="store_true", help="End Turn on Rome (must be your turn on campaign map)")
    parser.add_argument(
        "--probe-console",
        action="store_true",
        help="Hands-free mouse+key probe (no y/n prompts; leave Rome focused)",
    )
    parser.add_argument("--gap", type=int, default=4, help="Seconds between probe methods (default 4)")
    args = parser.parse_args()

    ctrl = SendInputController()

    if args.rome:
        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
        game = find_game_window(subs)
        if game is None:
            print("FAIL: Rome window not found")
            return 1
        hwnd = game.hwnd
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        elev_ok = process_elevation_matches(pid)
        print(f"OK  Rome hwnd={hwnd} title={game.title!r} elevation_match={elev_ok}")

        action = ensure_elevation_for_game(pid, argv=raw_argv)
        if action == "relaunching":
            return 0
        if action == "failed":
            return 1

        print("INFO be on campaign map, your Julii turn, End Turn button visible")
    else:
        subprocess.Popen(["notepad.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)
        hwnd = _find_notepad()
        if hwnd is None:
            print("FAIL: could not find Notepad")
            return 1
        print(f"OK  Notepad hwnd={hwnd}")

    _countdown(args.seconds, "click target window and leave it focused")

    with game_input_session(hwnd):
        print(f"INFO foreground={_fg_title()!r}")

    if args.rome and args.probe_console:
        return _probe_console_methods(hwnd, ctrl, gap_s=max(args.gap, 1))

    if args.rome:
        before_size, _ = message_log_snapshot()
        ok, method = end_turn_campaign(
            hwnd=hwnd,
            input_controller=ctrl,
            console_open=False,
            dwell_ms=80,
        )
        print(f"INFO end_turn ok={ok} method={method}")
        if ok:
            print("PASS Rome turn ended (message_log saw turn boundary)")
            return 0
        print("FAIL End Turn did not register")
        print("HINT: must be YOUR Julii turn (End Turn button active, not greyed out)")
        print("HINT: probe keyboard: python scripts/test_keypress.py --rome --probe-console")
        print("HINT: calibrate click: campaign.end_turn_click_norm: [0.XX, 0.YY] in config/local.yaml")
        print(f"     message_log grew: {message_log_snapshot()[0] > before_size}")
        return 1

    r1 = ctrl.tap_key("a", dwell_ms=50)
    r2 = ctrl.type_text(" comstar", dwell_ms=20)
    time.sleep(0.5)
    with game_input_session(hwnd):
        pass
    r3 = ctrl.chord_scancode("shift", "enter", dwell_ms=80)
    print(f"INFO notepad keys ok={r1 and r2 and r3}")
    if r1 and r2 and r3:
        print("PASS Notepad shows 'a comstar' and a new line")
        return 0
    print("FAIL Notepad key test failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
