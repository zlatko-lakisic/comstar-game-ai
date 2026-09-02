"""SendInput wrapper with key normalization."""

from __future__ import annotations

import sys
import time
from typing import Iterable

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    import win32con
    import win32gui

    ULONG_PTR = wintypes.WPARAM

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    _VK_MAP: dict[str, int] = {
        "backtick": 0xC0,
        "`": 0xC0,
        "~": 0xC0,
        "grave": 0xC0,
        "enter": win32con.VK_RETURN,
        "return": win32con.VK_RETURN,
        "escape": win32con.VK_ESCAPE,
        "esc": win32con.VK_ESCAPE,
        "tab": win32con.VK_TAB,
        "space": win32con.VK_SPACE,
        "shift": win32con.VK_SHIFT,
        "ctrl": win32con.VK_CONTROL,
        "control": win32con.VK_CONTROL,
        "alt": win32con.VK_MENU,
        "left": win32con.VK_LEFT,
        "right": win32con.VK_RIGHT,
        "up": win32con.VK_UP,
        "down": win32con.VK_DOWN,
    }
    for i in range(10):
        _VK_MAP[str(i)] = 0x30 + i
    for offset, letter in enumerate("abcdefghijklmnopqrstuvwxyz"):
        _VK_MAP[letter] = 0x41 + offset
        _VK_MAP[letter.upper()] = 0x41 + offset
    for fn in range(1, 13):
        _VK_MAP[f"f{fn}"] = 0x6F + fn

else:
    win32gui = None  # type: ignore[assignment]
    _VK_MAP = {}

    for i in range(10):
        _VK_MAP[str(i)] = 0x30 + i


def normalize_key_name(key: str) -> str:
    return key.strip().lower()


def virtual_key_for(key: str) -> int | None:
    normalized = normalize_key_name(key)
    if normalized in _VK_MAP:
        return _VK_MAP[normalized]
    if len(normalized) == 1:
        return _VK_MAP.get(normalized)
    return None


if sys.platform == "win32":

    class SendInputController:
        """Low-level synthetic input with key-state normalization."""

        def __init__(self) -> None:
            self._user32 = ctypes.windll.user32

        def focus_window(self, hwnd: int) -> bool:
            try:
                win32gui.SetForegroundWindow(hwnd)
                return win32gui.GetForegroundWindow() == hwnd
            except Exception:
                return False

        def normalize_keyboard_state(self) -> None:
            for key in ("shift", "ctrl", "alt"):
                vk = virtual_key_for(key)
                if vk is not None:
                    self._key_up(vk)

        def tap_key(self, key: str, *, dwell_ms: int = 30) -> bool:
            vk = virtual_key_for(key)
            if vk is None:
                return False
            self.normalize_keyboard_state()
            if not self._key_down(vk):
                return False
            time.sleep(max(dwell_ms, 1) / 1000.0)
            return self._key_up(vk)

        def send_keys(self, keys: Iterable[str], *, dwell_ms: int = 30) -> bool:
            ok = True
            for key in keys:
                ok = self.tap_key(key, dwell_ms=dwell_ms) and ok
            return ok

        def type_text(self, text: str, *, dwell_ms: int = 15) -> bool:
            self.normalize_keyboard_state()
            for ch in text:
                if ch == "\n":
                    if not self.tap_key("enter", dwell_ms=dwell_ms):
                        return False
                    continue
                if not self._unicode_char(ch):
                    return False
                time.sleep(max(dwell_ms, 1) / 1000.0)
            return True

        def move_mouse(self, x: int, y: int) -> bool:
            screen_w = self._user32.GetSystemMetrics(0)
            screen_h = self._user32.GetSystemMetrics(1)
            abs_x = int(x * 65535 / max(screen_w - 1, 1))
            abs_y = int(y * 65535 / max(screen_h - 1, 1))
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.union.mi = MOUSEINPUT(
                dx=abs_x,
                dy=abs_y,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                time=0,
                dwExtraInfo=0,
            )
            return self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

        def click(self, x: int, y: int, *, dwell_ms: int = 30) -> bool:
            if not self.move_mouse(x, y):
                return False
            for flag in (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP):
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.union.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
                if self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
                    return False
                time.sleep(max(dwell_ms, 1) / 1000.0)
            return True

        def _key_down(self, vk: int) -> bool:
            return self._send_key(vk, key_up=False)

        def _key_up(self, vk: int) -> bool:
            return self._send_key(vk, key_up=True)

        def _send_key(self, vk: int, *, key_up: bool) -> bool:
            flags = KEYEVENTF_KEYUP if key_up else 0
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.union.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
            return self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

        def _unicode_char(self, ch: str) -> bool:
            code = ord(ch)
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.union.ki = KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)
            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.union.ki = KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
            if self._user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)) != 1:
                return False
            return self._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT)) == 1

else:

    class SendInputController:
        def focus_window(self, hwnd: int) -> bool:
            return False

        def normalize_keyboard_state(self) -> None:
            return None

        def tap_key(self, key: str, *, dwell_ms: int = 30) -> bool:
            return False

        def send_keys(self, keys: Iterable[str], *, dwell_ms: int = 30) -> bool:
            return False

        def type_text(self, text: str, *, dwell_ms: int = 15) -> bool:
            return False

        def move_mouse(self, x: int, y: int) -> bool:
            return False

        def click(self, x: int, y: int, *, dwell_ms: int = 30) -> bool:
            return False
