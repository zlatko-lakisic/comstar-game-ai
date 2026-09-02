"""Minimal overlay stub for capture-exclusion and click-through self-tests."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

if sys.platform != "win32":
    raise RuntimeError("overlay stub requires Windows")

import win32api
import win32con
import win32gui
from ctypes import windll


WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
LWA_ALPHA = 0x2


def set_display_affinity(hwnd: int, affinity: int) -> None:
    if not windll.user32.SetWindowDisplayAffinity(hwnd, affinity):
        raise OSError("SetWindowDisplayAffinity failed")


@dataclass
class OverlayStub:
    hwnd: int
    thread: threading.Thread

    @classmethod
    def create(cls, game_hwnd: int, test_pattern: bool = True) -> OverlayStub:
        done = threading.Event()
        holder: dict[str, int] = {}

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        def run() -> None:
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "ComstarOverlayStub"
            wc.lpfnWndProc = wndproc
            try:
                win32gui.RegisterClass(wc)
            except win32gui.error:
                pass

            left, top, right, bottom = win32gui.GetWindowRect(game_hwnd)
            w = right - left
            h = bottom - top
            hwnd = win32gui.CreateWindowEx(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
                "ComstarOverlayStub",
                "ComstarOverlayStub",
                win32con.WS_POPUP,
                left,
                top,
                w,
                h,
                0,
                0,
                0,
                None,
            )
            win32gui.SetLayeredWindowAttributes(hwnd, 0, 180 if test_pattern else 1, LWA_ALPHA)
            set_display_affinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            holder["hwnd"] = hwnd
            done.set()
            win32gui.PumpMessages()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        done.wait(timeout=5.0)
        if "hwnd" not in holder:
            raise RuntimeError("overlay stub failed to create window")
        return cls(hwnd=holder["hwnd"], thread=thread)

    def destroy(self) -> None:
        if not self.hwnd:
            return
        try:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
        self.hwnd = 0


def foreground_is(hwnd: int) -> bool:
    return win32gui.GetForegroundWindow() == hwnd
