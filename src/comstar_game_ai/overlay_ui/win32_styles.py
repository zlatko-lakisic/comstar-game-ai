"""Win32 extended styles for overlay windows."""

from __future__ import annotations

import sys
from ctypes import windll

if sys.platform == "win32":
    import win32con
    import win32gui

WDA_EXCLUDEFROMCAPTURE = 0x00000011
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008


def apply_overlay_styles(hwnd: int) -> None:
    if sys.platform != "win32":
        return
    ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOPMOST
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
    if not windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        pass  # best effort
