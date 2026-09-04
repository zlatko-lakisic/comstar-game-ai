"""Match host process elevation to Rome so SendInput is not blocked by UIPI."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Literal, Sequence

ELEVATION_MARKER = "--comstar-elevation-matched"

ElevationAction = Literal["ok", "relaunching", "failed"]


def is_current_elevated() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def process_is_elevated(pid: int) -> bool | None:
    """True/False if readable; None if token is inaccessible (often higher IL)."""
    if sys.platform != "win32":
        return False
    try:
        import win32api
        import win32con
        import win32security

        h_proc = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        token = win32security.OpenProcessToken(h_proc, win32con.TOKEN_QUERY)
        elevation = win32security.GetTokenInformation(token, win32security.TokenElevation)
        if hasattr(elevation, "TokenIsElevated"):
            return bool(elevation.TokenIsElevated)
        return bool(elevation)
    except Exception:
        return None


def needs_elevation_for_pid(pid: int) -> bool:
    """True when this process must elevate to match the game (lower → higher UIPI)."""
    we = is_current_elevated()
    they = process_is_elevated(pid)
    if they is True and not we:
        return True
    # Unreadable token from a non-admin host almost always means the target is elevated.
    if they is None and not we:
        return True
    return False


def strip_elevation_marker(argv: Sequence[str] | None = None) -> list[str]:
    args = list(sys.argv[1:] if argv is None else argv)
    return [a for a in args if a != ELEVATION_MARKER]


def relaunch_elevated(
    *,
    argv: Sequence[str] | None = None,
    cwd: str | None = None,
    log_path: str | None = None,
) -> int:
    """
    Re-launch this Python process with a UAC elevation prompt (runas).

    Returns ShellExecute result (>32 means request accepted). Caller should exit.
    When log_path is set, launches via cmd.exe so stdout/stderr append to that file
    (elevated child windows are otherwise invisible to the parent terminal).
    """
    if sys.platform != "win32":
        return 0
    import ctypes
    from pathlib import Path

    script = os.path.abspath(sys.argv[0])
    rest = strip_elevation_marker(argv)
    workdir = cwd or os.getcwd()
    py_args = subprocess.list2cmdline([sys.executable, "-u", script, ELEVATION_MARKER, *rest])
    workdir_q = subprocess.list2cmdline([workdir])

    # Visible elevated console. /k keeps it open after the run so the trail stays.
    # Never redirect to a file here — that made a blank cmd window.
    params = f'/k title Comstar Game AI && cd /d {workdir_q} && {py_args}'
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        "cmd.exe",
        params,
        workdir,
        1,  # SW_SHOWNORMAL
    )
    return int(rc)


def ensure_elevation_for_game(
    pid: int,
    *,
    argv: Sequence[str] | None = None,
    log_path: str | None = None,
) -> ElevationAction:
    """
    Ensure this process can SendInput into pid's windows.

    - ok: continue in this process
    - relaunching: UAC child started; parent should exit 0
    - failed: cannot elevate; caller should exit 1
    """
    if sys.platform != "win32":
        return "ok"

    argv_list = list(sys.argv if argv is None else argv)
    already = ELEVATION_MARKER in argv_list
    we = is_current_elevated()
    they = process_is_elevated(pid)

    print(
        f"INFO elevation: python_admin={we} game_elevated={they} matched_marker={already}",
        flush=True,
    )

    if not needs_elevation_for_pid(pid):
        if we and they is False:
            print(
                "WARN Python is elevated but Rome is not — OK for SendInput; "
                "prefer matching both non-admin long-term",
                flush=True,
            )
        return "ok"

    if already and we:
        print("INFO already elevated to match game", flush=True)
        return "ok"

    if already and not we:
        print(
            "FAIL UAC elevation was cancelled or failed — cannot match Rome integrity level",
            flush=True,
        )
        return "failed"

    print(
        "INFO Rome needs elevated access — requesting Administrator via UAC…",
        flush=True,
    )
    # Accept either full sys.argv or args-only lists.
    if argv is None:
        child_args = strip_elevation_marker(sys.argv[1:])
    else:
        args = list(argv_list)
        if args and (args[0] == sys.argv[0] or str(args[0]).lower().endswith((".py", ".pyw"))):
            args = args[1:]
        child_args = strip_elevation_marker(args)
    rc = relaunch_elevated(argv=child_args, log_path=log_path)
    if rc <= 32:
        print(f"FAIL ShellExecute runas failed (code={rc})", flush=True)
        return "failed"
    if log_path:
        print(f"INFO elevated child logging to {log_path}", flush=True)
    return "relaunching"
