"""Capture a new show_cursorstat test session. Does not label the frames.

The camera is driven to each target. After every pan the cursor is placed
on the center of the 44-point cross and show_cursorstat is read. Those
reads steer the camera only. They are not the ground truth. Ground truth
is filled later from the glyphs, then locked, then scored once.

One countdown, then the script keeps the game focused. Console closed,
campaign map, no army selected. D pans east, A west, W north, S south.

    python scripts/capture_cursorstat_gate.py --session 20261003-gate2 --countdown 5

The old split (20261003-heldout) stays shut. A session directory that
already exists is refused.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"

# Same cross as the digit sweep. 23 points along x and 21 along y.
_MAP_X = (0.30, 0.70)
_MAP_Y = (0.26, 0.62)
_STEP = 0.018
# Where the two arms meet. The seek puts this client point on the target tile.
_CENTER = (0.50, 0.45)

# Centers the lock asks for. Neighbour digits come from the cross around each.
# 44 and 84 and 100 and 141 are exact components. x=44 is hundreds digit 0,
# y=100 and y=141 are hundreds digit 1, x=200 is hundreds digit 2.
_TARGETS = (
    (44, 44),
    (84, 84),
    (100, 100),
    (141, 141),
    (200, 55),
)

_MAX_STEPS = 80
_SETTLE_S = 0.35


def _bind_focus(shell, hwnd: int) -> None:
    import win32gui

    def focus_game() -> bool:
        for _ in range(8):
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as exc:
                print(f"focus: {exc}", flush=True)
                return False
            time.sleep(0.05)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        return False

    shell.focus_game = focus_game


class FocusLostError(RuntimeError):
    """Rome was not the foreground window. Capture stops."""


def _process_name(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return "unknown"
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return "unknown"
        return Path(buf.value).name
    finally:
        kernel.CloseHandle(handle)


def _foreground_desc() -> str:
    import win32gui
    import win32process

    fg = int(win32gui.GetForegroundWindow() or 0)
    if not fg:
        return "no foreground window"
    title = win32gui.GetWindowText(fg) or ""
    _thread, pid = win32process.GetWindowThreadProcessId(fg)
    return f"{title!r} process {_process_name(int(pid))} pid {pid}"


def _rome_in_front(hwnd: int) -> bool:
    import win32gui

    return int(win32gui.GetForegroundWindow() or 0) == int(hwnd)


def _save_focus_frame(hwnd: int, dump: Path | None) -> None:
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image

    if dump is None:
        return
    frame = grab_rgb_image(hwnd)
    if frame is None:
        return
    dump.mkdir(parents=True, exist_ok=True)
    frame.save(dump / "focus_fail.png")


def _require_focus(shell, hwnd: int, dump: Path | None) -> None:
    """Before a key press. One focus retry, then stop with the frame saved."""
    if _rome_in_front(hwnd):
        return
    print(f"focus lost; foreground {_foreground_desc()}", flush=True)
    _bind_focus(shell, hwnd)
    if shell.focus_game() and _rome_in_front(hwnd):
        return
    desc = _foreground_desc()
    _save_focus_frame(hwnd, dump)
    raise FocusLostError(
        f"Rome is not in front; foreground {desc}; saved focus_fail.png"
    )


def _sweep_points() -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    x = _MAP_X[0]
    while x <= _MAP_X[1] + 1e-9:
        points.append((round(x, 4), _CENTER[1]))
        x += _STEP
    y = _MAP_Y[0]
    while y <= _MAP_Y[1] + 1e-9:
        points.append((_CENTER[0], round(y, 4)))
        y += _STEP
    return points


def _client_screen(hwnd: int, client: tuple[float, float]) -> tuple[int, int] | None:
    from comstar_game_ai.game_io.campaign.combat import client_norm_to_screen

    return client_norm_to_screen(hwnd, client[0], client[1])


def _release_pan_keys(shell) -> None:
    controller = shell.input_controller
    if controller is None:
        return
    for key in ("a", "d", "w", "s"):
        controller._release_key(key)


class ConsoleOpenError(RuntimeError):
    """The console toggle did not produce an open console. Capture stops."""


def _console_bands(image) -> tuple[float, float]:
    """Mean gray of the console band and of the map just below it."""
    gray = image.convert("L")
    px = gray.load()

    def band(y0: int, y1: int) -> float:
        vals = [px[x, y] for y in range(y0, y1, 3) for x in range(250, 700, 6)]
        return sum(vals) / len(vals)

    return band(100, 135), band(170, 210)


# Every measured opening leaves the top band at about 0.3 of its closed
# brightness: Cilicia 0.30, northern forest 0.29, dark forest 0.31, and
# the gate20 failure 0.28. Half and double sit clear of that cluster.
# The open console also darkens the map below, by about the same
# fraction: Cilicia 0.89, northern forest 0.92, gate20 0.91, gate22 0.89.
# 0.8 to 1.25 stays outside that cluster. The pan check still uses a gap.
# A single dark side is not "too dark": the gate21 close went 8.8 to 27.8.
_TOP_OPEN_RATIO = 0.5
_TOP_CLOSED_RATIO = 2.0
_TOP_TOO_DARK = 10.0
_BELOW_RATIO_LOW = 0.8
_BELOW_RATIO_HIGH = 1.25
_BELOW_HOLD = 12.0
# Pan refusal, not a toggle. The brightest measured open top is 30.4
# (gate20) and closed Italy is about 43, so 38 sits between them. A closed
# picture can still have a wide gap (Italy, about 34), so the gap applies
# only under that top. The darkest measured closed top is about 26.
_PAN_OPEN_TOP = 38.0


def _toggle_verdict(
    before: tuple[float, float], after: tuple[float, float]
) -> str:
    """How one backtick changed the console.

    ``too_dark`` and ``ambiguous`` both stop the capture. Too dark means
    both sides are at or under 10. One dark side still uses the ratio.
    """
    if before[0] <= _TOP_TOO_DARK and after[0] <= _TOP_TOO_DARK:
        return "too_dark"
    if before[1] <= 0:
        return "ambiguous"
    below_ratio = after[1] / before[1]
    if below_ratio < _BELOW_RATIO_LOW or below_ratio > _BELOW_RATIO_HIGH:
        return "ambiguous"
    if before[0] <= 0:
        return "ambiguous"
    ratio = after[0] / before[0]
    if ratio < _TOP_OPEN_RATIO:
        return "open"
    if ratio > _TOP_CLOSED_RATIO:
        return "closed"
    return "ambiguous"


def _looks_open(top: float, below: float) -> bool:
    """Whether a single frame is an open console, for refusing a pan key."""
    if top <= _TOP_TOO_DARK:
        return True
    return top < _PAN_OPEN_TOP and (below - top) > _BELOW_HOLD


def _sync_console(shell, hwnd: int, want_open: bool, dump: Path | None = None) -> bool:
    """Press backtick and judge the console from the change, not the level.

    A clear change the wrong way gets one more backtick, then the new
    pair is judged. Both bands at 10 or less, or any other ambiguous
    change, saves both frames and stops the capture.
    """
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.game_focus import game_input_session

    def bands_text(image) -> str:
        if image is None:
            return "no frame"
        top, below = _console_bands(image)
        return f"top {top:.1f}, below {below:.1f}"

    def stop(before_image, after_image, reason: str) -> None:
        if dump is not None:
            dump.mkdir(parents=True, exist_ok=True)
            if before_image is not None:
                before_image.save(dump / "console_toggle_before.png")
            if after_image is not None:
                after_image.save(dump / "console_toggle_after.png")
        raise ConsoleOpenError(
            f"{reason} (before {bands_text(before_image)}; "
            f"after {bands_text(after_image)}); "
            "saved console_toggle_before.png and console_toggle_after.png"
        )

    wanted = "open" if want_open else "closed"
    _release_pan_keys(shell)
    with game_input_session(hwnd):
        before = grab_rgb_image(hwnd)
    if before is None:
        stop(None, None, "console toggle had no frame")
    after = None
    for _ in range(2):
        _require_focus(shell, hwnd, dump)
        with game_input_session(hwnd):
            shell.open_console()
        time.sleep(0.25)
        with game_input_session(hwnd):
            after = grab_rgb_image(hwnd)
        if after is None:
            stop(before, None, "console toggle had no frame after the backtick")
        verdict = _toggle_verdict(_console_bands(before), _console_bands(after))
        if verdict == "too_dark":
            stop(before, after, "console band was too dark to judge")
        if verdict == "ambiguous":
            stop(before, after, "console toggle was ambiguous")
        shell.console_open = verdict == "open"
        if verdict == wanted:
            return True
        pair = (before, after)
        before = after
    stop(pair[0], pair[1], f"console toggle did not reach {wanted}")


def _save_abstain(frame, dest: Path | None) -> None:
    if dest is None or frame is None:
        return
    dest.mkdir(parents=True, exist_ok=True)
    name = f"abstain_{len(list(dest.glob('abstain_*.png'))):02d}.png"
    frame.save(dest / name)


def _read_center(shell, hwnd: int, dump: Path | None = None) -> tuple[int, int] | None:
    """Map coordinate under the cross center, or None when the reader abstains."""
    from comstar_game_ai.game_io.campaign.console_cursorstat import read_console_cursorstat
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.game_focus import game_input_session

    screen = _client_screen(hwnd, _CENTER)
    if screen is None or shell.input_controller is None:
        print("FAIL: could not aim the cross center", flush=True)
        return None
    for attempt in range(3):
        _release_pan_keys(shell)
        if not _sync_console(shell, hwnd, True, dump):
            print("FAIL: console did not open for the cross center", flush=True)
            return None
        with game_input_session(hwnd):
            if not shell.input_controller.move_mouse(*screen):
                print("FAIL: mouse move to cross center", flush=True)
                return None
            time.sleep(0.5)
            _require_focus(shell, hwnd, dump)
            if not shell.send_command("show_cursorstat", open_console=True):
                print("FAIL: show_cursorstat at cross center", flush=True)
                return None
            frame = None
            reading = None
            for _ in range(8):
                time.sleep(0.2)
                frame = grab_rgb_image(hwnd)
                if frame is None:
                    continue
                reading = read_console_cursorstat(frame)
                if "glyph height" not in (reading.reason or ""):
                    break
        if frame is None or reading is None:
            print("FAIL: no frame at cross center", flush=True)
            return None
        if not _sync_console(shell, hwnd, False, dump):
            print("FAIL: console stayed open after the cross center read", flush=True)
            return None
        if reading.xy is not None:
            print(f"center {reading.xy[0]}, {reading.xy[1]}", flush=True)
            return reading.xy
        print(f"center abstain: {reading.reason}", flush=True)
        _save_abstain(frame, dump)
        if attempt == 2:
            break
    return None


def _pan(shell, hwnd: int, key: str, hold_s: float, dump: Path | None = None) -> bool:
    """Send a pan key only when the current picture does not look open.

    This does not press backtick. The read already closed the console.
    """
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.game_focus import game_input_session

    if shell.input_controller is None:
        return False
    _release_pan_keys(shell)
    with game_input_session(hwnd):
        frame = grab_rgb_image(hwnd)
    if frame is None:
        raise ConsoleOpenError(f"pan key {key} had no frame")
    top, below = _console_bands(frame)
    if _looks_open(top, below):
        if dump is not None:
            dump.mkdir(parents=True, exist_ok=True)
            frame.save(dump / "console_pan_blocked.png")
        raise ConsoleOpenError(
            f"console looked open before pan key {key} "
            f"(top {top:.1f}, below {below:.1f}); "
            "saved console_pan_blocked.png"
        )
    _require_focus(shell, hwnd, dump)
    dwell_ms = max(1, int(round(hold_s * 1000)))
    with game_input_session(hwnd):
        return bool(shell.input_controller.tap_key(key, dwell_ms=dwell_ms, hwnd=hwnd))


def _seek(
    shell, hwnd: int, target: tuple[int, int], dump: Path | None = None
) -> tuple[tuple[int, int] | None, list[dict[str, object]]]:
    from comstar_game_ai.game_io.campaign.camera_seek import choose_move, record_rate

    print(f"seek {target[0]}, {target[1]}", flush=True)
    rates: dict[str, tuple[float, float]] = {}
    measured: set[str] = set()
    boost: dict[str, float] = {}
    abstained = 0
    rejected: tuple[int, int] | None = None
    current = _read_center(shell, hwnd, dump)
    trace: list[dict[str, object]] = []
    for step in range(_MAX_STEPS):
        if current is None:
            abstained += 1
            if abstained > 5:
                print(f"seek {target[0]}, {target[1]} step {step}: no center read", flush=True)
                return None, trace
            current = _read_center(shell, hwnd, dump)
            if current is None:
                continue
        decision = choose_move(current, target, rates)
        trace.append(
            {
                "step": step,
                "xy": [current[0], current[1]],
                "kind": decision.kind,
                "key": decision.key,
                "hold_s": round(decision.hold_s, 3),
            }
        )
        if decision.kind == "done":
            print(
                f"seek {target[0]}, {target[1]} reached {current[0]}, {current[1]}",
                flush=True,
            )
            return current, trace
        if decision.kind == "stuck":
            print(f"seek {target[0]}, {target[1]} stuck at {current[0]}, {current[1]}", flush=True)
            return None, trace
        hold = decision.hold_s
        if decision.key in boost:
            hold = max(hold, boost.pop(decision.key))
        before = current
        print(
            f"seek {target[0]}, {target[1]} at {current[0]}, {current[1]} "
            f"key={decision.key} hold={hold:.2f}s",
            flush=True,
        )
        if not _pan(shell, hwnd, decision.key, hold, dump):
            print(f"FAIL: pan {decision.key}", flush=True)
            return None, trace
        time.sleep(_SETTLE_S)
        after = _read_center(shell, hwnd, dump)
        if after is None:
            # A missed read is not a position. Guessing one and panning
            # again walked off the east edge, and a guess inside the
            # close radius was reported as arrival. Stay on the last
            # real read and try the picture again.
            abstained += 1
            if abstained > 3:
                print(
                    f"seek {target[0]}, {target[1]} step {step}: no center read",
                    flush=True,
                )
                return None, trace
            current = before
            continue
        jump = max(abs(after[0] - before[0]), abs(after[1] - before[1]))
        # A truncated digit (163 read as 63) looks like a huge jump. One
        # such read is replaced by the estimate. If the next read is a
        # normal step from that rejected value, the camera really is there:
        # trust it. Chaining estimates and holding D walked off the east
        # edge into the black border.
        limit = hold * 70 + 4
        if jump > limit:
            if rejected is not None:
                step = max(abs(after[0] - rejected[0]), abs(after[1] - rejected[1]))
                if step <= limit:
                    print(
                        f"seek {target[0]}, {target[1]} trusted {after[0]}, {after[1]}",
                        flush=True,
                    )
                    rejected = None
                    current = after
                    abstained = 0
                    continue
            from comstar_game_ai.game_io.campaign.camera_seek import estimate_after

            est_x, est_y = estimate_after(decision.key, before, hold, rates)
            est_x = min(254, max(0, est_x))
            est_y = min(155, max(0, est_y))
            print(
                f"seek {target[0]}, {target[1]} ignored jump "
                f"{before[0]}, {before[1]} -> {after[0]}, {after[1]}; "
                f"estimated {est_x}, {est_y}",
                flush=True,
            )
            rejected = after
            current = (est_x, est_y)
            continue
        rejected = None
        abstained = 0
        if not record_rate(rates, measured, decision.key, before, after, hold):
            if hold >= 1.2:
                rates[decision.key] = (0.0, 0.0)
            else:
                boost[decision.key] = min(1.2, hold * 2)
        current = after
    print(f"seek {target[0]}, {target[1]} did not arrive in {_MAX_STEPS} steps", flush=True)
    return None, trace


def _grab(shell, hwnd: int, client: tuple[float, float], dest: Path) -> bool:
    from comstar_game_ai.game_io.campaign.console_cursorstat import read_console_cursorstat
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.game_focus import game_input_session

    screen = _client_screen(hwnd, client)
    if screen is None or shell.input_controller is None:
        print(f"FAIL: could not aim {dest.name}", flush=True)
        return False
    if not _sync_console(shell, hwnd, True, dest.parent):
        print(f"FAIL: console did not open for {dest.name}", flush=True)
        return False
    with game_input_session(hwnd):
        if not shell.input_controller.move_mouse(*screen):
            print(f"FAIL: mouse move {dest.name}", flush=True)
            return False
        time.sleep(0.5)
        _require_focus(shell, hwnd, dest.parent)
        if not shell.send_command("show_cursorstat", open_console=True):
            print(f"FAIL: show_cursorstat {dest.name}", flush=True)
            return False
        frame = None
        for _ in range(8):
            time.sleep(0.2)
            frame = grab_rgb_image(hwnd)
            if frame is None:
                continue
            if "glyph height" not in (read_console_cursorstat(frame).reason or ""):
                break
    if not _sync_console(shell, hwnd, False, dest.parent):
        print(f"FAIL: console stayed open after {dest.name}", flush=True)
        return False
    if frame is None:
        print(f"FAIL: no frame {dest.name}", flush=True)
        return False
    frame.save(dest)
    print(f"saved {dest.name} size={frame.size}", flush=True)
    return True


def _countdown(seconds: int, wait_for_enter: bool) -> None:
    print(
        "campaign map, console closed, nothing selected. "
        "Press Enter here, then click the game. The script pans from there.",
        flush=True,
    )
    if wait_for_enter:
        input("Press Enter here, then click the game.")
    for i in range(seconds, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--countdown", type=int, default=5)
    parser.add_argument(
        "--now",
        action="store_true",
        help="start without waiting for Enter; the game is already focused",
    )
    args = parser.parse_args(argv)

    from comstar_game_ai.game_io.console.romeshell import RomeShell
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    if sys.platform != "win32":
        print("FAIL: Windows required", flush=True)
        return 1
    out = SESSIONS / args.session
    if out.exists():
        print(f"FAIL: {out} already exists; sessions are not overwritten", flush=True)
        return 1

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found", flush=True)
        return 1

    points = _sweep_points()
    if len(points) != 44:
        print(f"FAIL: sample has {len(points)} points, expected 44", flush=True)
        return 1
    print(
        f"targets={list(_TARGETS)} sample={len(points)} step={_STEP}",
        flush=True,
    )
    shell = RomeShell(hwnd=game.hwnd)
    _bind_focus(shell, game.hwnd)
    out.mkdir(parents=True)
    _countdown(args.countdown, wait_for_enter=not args.now)

    labels: list[dict[str, object]] = []
    approaches: list[dict[str, object]] = []
    missed: list[list[int]] = []
    ok = True
    stop_code = 0
    try:
        for sweep, target in enumerate(_TARGETS):
            found, trace = _seek(shell, game.hwnd, target, out)
            approaches.append(
                {
                    "target": [target[0], target[1]],
                    "center": list(found) if found is not None else None,
                    "steps": trace,
                }
            )
            if found is None:
                missed.append([target[0], target[1]])
                continue
            for index, client in enumerate(points):
                name = f"sweep{sweep}_{index:02d}.png"
                dest = out / name
                if not _grab(shell, game.hwnd, client, dest):
                    ok = False
                    break
                labels.append(
                    {
                        "file": name,
                        "client": [client[0], client[1]],
                        "target": [target[0], target[1]],
                        "xy": None,
                        "label_source": "unlabeled",
                    }
                )
                time.sleep(0.25)
            if not ok:
                break
    except ConsoleOpenError as exc:
        stop_code = 4
        print(f"FAIL: {exc}; capture stopped", flush=True)
    except FocusLostError as exc:
        stop_code = 5
        print(f"FAIL: {exc}; capture stopped", flush=True)

    (out / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    (out / "approach.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
    print(
        f"session {out} frames={len(labels)} labeled=0 missed={missed}",
        flush=True,
    )
    if stop_code:
        return stop_code
    if not ok:
        return 1
    if missed:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
