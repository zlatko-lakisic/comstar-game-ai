"""Window-targeted capture (WGC preferred; BitBlt fallback for dev)."""

from __future__ import annotations

import sys
from dataclasses import dataclass

if sys.platform == "win32":
    import win32gui
    import win32ui
    from ctypes import windll
else:
    win32gui = None  # type: ignore[assignment]


@dataclass
class CaptureFrame:
    data: bytes
    width: int
    height: int
    backend: str


class WindowCapture:
    """Capture game window client area. Uses PrintWindow/BitBlt until WGC backend wired."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def grab(self) -> CaptureFrame | None:
        if win32gui is None or not self.hwnd:
            return None
        try:
            left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                return None

            hwnd_dc = win32gui.GetWindowDC(self.hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)
            windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 2)
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwnd_dc)
            return CaptureFrame(data=bmpstr, width=width, height=height, backend="printwindow")
        except Exception:
            return None
