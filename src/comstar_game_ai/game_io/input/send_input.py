"""SendInput wrapper with key normalization."""

from __future__ import annotations

import sys
import time
from typing import Iterable

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    import win32api
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
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    #: Without this, absolute coordinates address the primary monitor only, so any
    #: window on a monitor left of or above it is unreachable.
    MOUSEEVENTF_VIRTUALDESK = 0x4000

    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

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
        # Camera bindings need these: descr_shortcuts.txt maps capital_zoom to Home
        # and point_to_north to PageUp, and without them both resolve to no key.
        "home": win32con.VK_HOME,
        "end": win32con.VK_END,
        "pageup": win32con.VK_PRIOR,
        "pagedown": win32con.VK_NEXT,
        "insert": win32con.VK_INSERT,
        "delete": win32con.VK_DELETE,
        "backspace": win32con.VK_BACK,
    }
    #: Keys the keyboard reports with an 0xE0 prefix. Sending their scancode without
    #: this flag delivers the numeric-keypad key of the same scancode instead.
    _EXTENDED_KEYS = frozenset(
        {"left", "right", "up", "down", "home", "end", "pageup", "pagedown",
         "insert", "delete"}
    )
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
                self._release_key(key)

        def scancode_for(self, key: str) -> tuple[int, bool] | None:
            """(scancode, is_extended) for a key name, or None if unmapped."""
            vk = virtual_key_for(key)
            if vk is None:
                return None
            scan = win32api.MapVirtualKey(vk, 0)
            if not scan:
                return None
            return scan, normalize_key_name(key) in _EXTENDED_KEYS

        def tap_key(self, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
            """Press and release a key as a scancode.

            Scancode rather than virtual key, because Rome reads the keyboard through
            DirectInput, which is driven by scancodes and ignores a virtual-key event
            that carries none. Such an event still succeeds at the API level and is
            still delivered to ordinary windows, so the failure is invisible from
            here: SendInput returns 1 and the game does nothing.
            """
            resolved = self.scancode_for(key)
            if resolved is None:
                return False
            scan, extended = resolved
            if hwnd is not None:
                self.focus_window(hwnd)
            self.normalize_keyboard_state()
            if not self._send_scancode(scan, key_up=False, extended=extended):
                return False
            time.sleep(max(dwell_ms, 1) / 1000.0)
            return self._send_scancode(scan, key_up=True, extended=extended)

        def _release_key(self, key: str) -> bool:
            resolved = self.scancode_for(key)
            if resolved is None:
                return False
            scan, extended = resolved
            return self._send_scancode(scan, key_up=True, extended=extended)

        def _send_scancode(self, scan: int, *, key_up: bool, extended: bool = False) -> bool:
            flags = KEYEVENTF_SCANCODE
            if key_up:
                flags |= KEYEVENTF_KEYUP
            if extended:
                flags |= KEYEVENTF_EXTENDEDKEY
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.union.ki = KEYBDINPUT(0, scan & 0xFFFF, flags, 0, 0)
            return self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

        def chord_scancode(self, modifier: str, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
            mod = self.scancode_for(modifier)
            target = self.scancode_for(key)
            if mod is None or target is None:
                return False
            mod_scan, mod_ext = mod
            key_scan, key_ext = target
            if hwnd is not None:
                self.focus_window(hwnd)
            self.normalize_keyboard_state()
            delay = max(dwell_ms, 1) / 1000.0
            if not self._send_scancode(mod_scan, key_up=False, extended=mod_ext):
                return False
            time.sleep(delay)
            if not self._send_scancode(key_scan, key_up=False, extended=key_ext):
                self._send_scancode(mod_scan, key_up=True, extended=mod_ext)
                return False
            time.sleep(delay)
            if not self._send_scancode(key_scan, key_up=True, extended=key_ext):
                self._send_scancode(mod_scan, key_up=True, extended=mod_ext)
                return False
            return self._send_scancode(mod_scan, key_up=True, extended=mod_ext)

        def click_client_norm(self, hwnd: int, x_norm: float, y_norm: float, *, dwell_ms: int = 30) -> bool:
            try:
                left, top, right, bottom = win32gui.GetClientRect(hwnd)
                w = max(right - left, 1)
                h = max(bottom - top, 1)
                cx = int(w * max(0.0, min(1.0, x_norm)))
                cy = int(h * max(0.0, min(1.0, y_norm)))
                sx, sy = win32gui.ClientToScreen(hwnd, (cx, cy))
                self.focus_window(hwnd)
                return self.click(sx, sy, dwell_ms=dwell_ms)
            except Exception:
                return False

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
            """Move to a virtual-desktop screen coordinate.

            Normalised against the virtual desktop rather than the primary monitor:
            the primary's origin is not the desktop origin on a multi-monitor setup,
            so scaling by primary width silently mis-aims every click on any other
            monitor -- and puts negative coordinates out of reach entirely.
            """
            origin_x = self._user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            origin_y = self._user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            desk_w = self._user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            desk_h = self._user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            abs_x = int((x - origin_x) * 65535 / max(desk_w - 1, 1))
            abs_y = int((y - origin_y) * 65535 / max(desk_h - 1, 1))
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.union.mi = MOUSEINPUT(
                dx=abs_x,
                dy=abs_y,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                time=0,
                dwExtraInfo=0,
            )
            return self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

        def click(self, x: int, y: int, *, dwell_ms: int = 80, settle_ms: int = 120) -> bool:
            """Click at a screen coordinate, letting the cursor arrive first.

            Rome reads the cursor position on its own frame tick, so a button event
            sent immediately after the move is attributed to wherever the cursor was
            before it. The symptom is specific and misleading: hover tooltips appear
            under the target, proving the aim is right, while the click does nothing.
            The move is re-asserted because a single absolute move can be coalesced
            with the button event in the same batch.
            """
            if not self.move_mouse(x, y):
                return False
            time.sleep(max(settle_ms, 1) / 1000.0)
            if not self.move_mouse(x, y):
                return False
            time.sleep(max(settle_ms, 1) / 1000.0)
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

        def tap_key(self, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
            return False

        def send_keys(self, keys: Iterable[str], *, dwell_ms: int = 30) -> bool:
            return False

        def type_text(self, text: str, *, dwell_ms: int = 15) -> bool:
            return False

        def click_client_norm(self, hwnd: int, x_norm: float, y_norm: float, *, dwell_ms: int = 30) -> bool:
            return False

        def chord_scancode(self, modifier: str, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
            return False

        def move_mouse(self, x: int, y: int) -> bool:
            return False

        def click(self, x: int, y: int, *, dwell_ms: int = 80, settle_ms: int = 120) -> bool:
            return False
