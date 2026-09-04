"""Focus Rome and deliver input while thread-input is attached."""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from collections.abc import Iterator, Callable
from typing import TypeVar

if sys.platform != "win32":
    raise NotImplementedError("game focus requires win32")

import ctypes
import win32api
import win32con
import win32gui
import win32process

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _client_center_screen(hwnd: int) -> tuple[int, int] | None:
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w = max(right - left, 1)
        h = max(bottom - top, 1)
        return win32gui.ClientToScreen(hwnd, (w // 2, h // 2))
    except Exception:
        return None


def activate_client_click(hwnd: int) -> bool:
    """Click game client center so keyboard input is accepted."""
    pt = _client_center_screen(hwnd)
    if pt is None:
        return False
    sx, sy = pt
    try:
        from comstar_game_ai.game_io.input.directinput import click_screen

        return click_screen(sx, sy)
    except Exception:
        from comstar_game_ai.game_io.input.send_input import SendInputController

        return SendInputController().click(sx, sy, dwell_ms=50)


def post_vk_key(hwnd: int, vk: int) -> bool:
    """Post WM_KEYDOWN/UP to hwnd (some games accept message-based input)."""
    try:
        scan = win32api.MapVirtualKey(vk, 0) & 0xFF
        lparam_down = 1 | (scan << 16)
        lparam_up = 1 | (scan << 16) | (1 << 30) | (1 << 31)
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, lparam_up)
        return True
    except Exception as exc:
        _LOGGER.warning("PostMessage key failed: %s", exc)
        return False


@contextlib.contextmanager
def game_input_session(hwnd: int) -> Iterator[None]:
    """
    Attach to the game's input thread and keep attachment for the whole block.

    Detaching before SendInput (the old focus_window bug) drops keys on the floor.
    """
    user32 = ctypes.windll.user32
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        user32.AllowSetForegroundWindow(pid)
    except Exception:
        pass

    fg = win32gui.GetForegroundWindow()
    fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
    cur_thread = win32api.GetCurrentThreadId()
    pairs: list[tuple[int, int]] = []

    try:
        if fg_thread and fg_thread != target_thread:
            try:
                win32process.AttachThreadInput(fg_thread, target_thread, True)
                pairs.append((fg_thread, target_thread))
            except Exception as exc:
                _LOGGER.debug("AttachThreadInput fg failed: %s", exc)
        if cur_thread != target_thread:
            try:
                win32process.AttachThreadInput(cur_thread, target_thread, True)
                pairs.append((cur_thread, target_thread))
            except Exception as exc:
                _LOGGER.debug("AttachThreadInput cur failed: %s", exc)

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            _LOGGER.debug("SetForegroundWindow failed: %s", exc)
        time.sleep(0.08)
        yield
    finally:
        for a, b in reversed(pairs):
            try:
                win32process.AttachThreadInput(a, b, False)
            except Exception:
                pass


def with_game_input(hwnd: int, fn: Callable[[], T], *, activate_click: bool = True) -> T:
    with game_input_session(hwnd):
        if activate_click:
            activate_client_click(hwnd)
            time.sleep(0.1)
        return fn()
