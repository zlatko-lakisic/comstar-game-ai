"""Global hotkey registration for kill / takeover / handback."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Callable

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    import win32con
    import win32gui

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000

    _MOD_MAP = {
        "alt": MOD_ALT,
        "ctrl": MOD_CONTROL,
        "control": MOD_CONTROL,
        "shift": MOD_SHIFT,
    }

    _VK_MAP = {
        "end": win32con.VK_END,
        "home": win32con.VK_HOME,
        "pause": win32con.VK_PAUSE,
        "break": win32con.VK_PAUSE,
    }

_LOGGER = logging.getLogger(__name__)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+end' into (modifiers, vk)."""
    if sys.platform != "win32":
        return 0, 0
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    mods = 0
    key = parts[-1] if parts else ""
    for part in parts[:-1]:
        mods |= _MOD_MAP.get(part, 0)
    vk = _VK_MAP.get(key)
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        raise ValueError(f"unsupported hotkey key: {key!r} in {spec!r}")
    return mods | MOD_NOREPEAT, vk


@dataclass
class HotkeyBinding:
    hotkey_id: int
    spec: str
    callback: Callable[[], None]


if sys.platform == "win32":

    class HotkeyManager:
        """RegisterHotKey loop on a hidden message-only window."""

        WM_HOTKEY = 0x0312

        def __init__(self) -> None:
            self._bindings: dict[int, HotkeyBinding] = {}
            self._hwnd: int | None = None
            self._thread: threading.Thread | None = None
            self._stop = threading.Event()

        def register(self, hotkey_id: int, spec: str, callback: Callable[[], None]) -> None:
            mods, vk = parse_hotkey(spec)
            if self._hwnd is None:
                self._ensure_window()
            assert self._hwnd is not None
            if not ctypes.windll.user32.RegisterHotKey(self._hwnd, hotkey_id, mods, vk):
                raise OSError(f"RegisterHotKey failed for {spec!r}")
            self._bindings[hotkey_id] = HotkeyBinding(hotkey_id, spec, callback)

        def unregister_all(self) -> None:
            if self._hwnd is not None:
                for hid in list(self._bindings):
                    ctypes.windll.user32.UnregisterHotKey(self._hwnd, hid)
            self._bindings.clear()

        def start(self) -> None:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._message_loop, daemon=True)
            self._thread.start()

        def stop(self) -> None:
            self._stop.set()
            if self._hwnd is not None:
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            if self._thread:
                self._thread.join(timeout=2.0)
            self.unregister_all()

        def _ensure_window(self) -> None:
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "ComstarHotkeyWindow"
            wc.lpfnWndProc = self._wnd_proc
            class_atom = win32gui.RegisterClass(wc)
            self._hwnd = win32gui.CreateWindow(
                class_atom,
                "ComstarHotkeys",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                wc.hInstance,
                None,
            )

        def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == self.WM_HOTKEY:
                binding = self._bindings.get(int(wparam))
                if binding:
                    try:
                        binding.callback()
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception("hotkey callback failed: %s", binding.spec)
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        def _message_loop(self) -> None:
            self._ensure_window()
            assert self._hwnd is not None
            while not self._stop.is_set():
                try:
                    b_msg, _ = win32gui.GetMessage(None, 0, 0)
                    if b_msg:
                        win32gui.TranslateMessage(b_msg)
                        win32gui.DispatchMessage(b_msg)
                except Exception:  # noqa: BLE001
                    if self._stop.is_set():
                        break
                    _LOGGER.debug("hotkey message loop", exc_info=True)

else:

    class HotkeyManager:
        def register(self, hotkey_id: int, spec: str, callback: Callable[[], None]) -> None:
            _ = (hotkey_id, spec, callback)

        def unregister_all(self) -> None:
            return None

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None
