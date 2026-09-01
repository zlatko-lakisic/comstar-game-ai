"""WGC capture — uses window-targeted capture when available, else PrintWindow."""

from __future__ import annotations

from comstar_game_ai.game_io.capture.window_capture import CaptureFrame, WindowCapture


class WgcCapture:
    """Primary capture path. WGC via PrintWindow window-target until WinRT wired."""

    def __init__(self, hwnd: int) -> None:
        self._inner = WindowCapture(hwnd)

    def grab(self) -> CaptureFrame | None:
        frame = self._inner.grab()
        if frame is not None:
            frame.backend = "wgc-window"
        return frame
