"""Window-targeted capture (MSS/dxcam preferred; PrintWindow fallback)."""

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


def _grab_mss(rect: tuple[int, int, int, int]) -> CaptureFrame | None:
    """Capture screen region via mss (works with DirectX games)."""
    try:
        import mss
        import mss.tools
        left, top, right, bottom = rect
        monitor = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        with mss.mss() as sct:
            shot = sct.grab(monitor)
        # mss returns BGRA; convert to BGRX-compatible bytes (replace A with 0xFF)
        import ctypes
        buf = bytearray(shot.raw)
        # Already BGRA, PIL can read as BGRX if we swap alpha
        return CaptureFrame(
            data=bytes(buf),
            width=shot.width,
            height=shot.height,
            backend="mss",
        )
    except Exception:
        return None


def _grab_printwindow(hwnd: int) -> CaptureFrame | None:
    """Fallback: PrintWindow (fails on exclusive-fullscreen DirectX games)."""
    if win32gui is None:
        return None
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)
        windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        bmpstr = bitmap.GetBitmapBits(True)
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        return CaptureFrame(data=bmpstr, width=width, height=height, backend="printwindow")
    except Exception:
        return None


def client_screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Client area in screen coords.

    Capture must cover exactly the client area, because every click derived from a
    frame goes through ClientToScreen. Grabbing the window rect instead shifts all
    vision coordinates down by the title bar (31 px) and right by the border (8 px),
    which is enough to miss small controls like a panel close button.
    """
    if win32gui is None:
        return None
    try:
        cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (cl, ct))
        right, bottom = win32gui.ClientToScreen(hwnd, (cr, cb))
        if right - left < 2 or bottom - top < 2:
            return None
        return left, top, right, bottom
    except Exception:
        return None


class WindowCapture:
    """Capture game client area. Tries MSS (works with DirectX) then PrintWindow fallback."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def grab(self) -> CaptureFrame | None:
        if not self.hwnd:
            return None
        if win32gui is not None:
            rect = client_screen_rect(self.hwnd)
            if rect is None:
                try:
                    rect = win32gui.GetWindowRect(self.hwnd)
                except Exception:
                    rect = None
            if rect is not None:
                frame = _grab_mss(rect)
                if frame is not None and not _is_black(frame):
                    return frame
        # Fallback
        return _grab_printwindow(self.hwnd)


def _is_black(frame: CaptureFrame) -> bool:
    """Return True if the frame is mostly black (capture failed)."""
    if not frame.data or frame.width < 2 or frame.height < 2:
        return True
    sample = frame.data[: min(len(frame.data), 4096)]
    nonzero = sum(1 for b in sample if b > 8)
    return nonzero < len(sample) * 0.02
