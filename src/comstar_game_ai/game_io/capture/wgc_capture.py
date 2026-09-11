"""Real Windows Graphics Capture (WGC) of a game hwnd.

Uses the ``windows-capture`` binding: ``window_hwnd`` targeting and
``draw_border=False`` (IsBorderRequired). Output is always the **client area**
in BGRA, matching ``client_screen_rect`` dimensions so SendInput norms stay valid.

Occlusion (verified): a foreign topmost window covering the game does **not**
appear in frames — WGC continues to yield the game's own content (or black if
minimised / unavailable), never the occluder. That is the point of §7.1.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any

import numpy as np

from comstar_game_ai.game_io.capture.window_capture import CaptureFrame, client_screen_rect

_LOGGER = logging.getLogger(__name__)

# Interior alpha must stay opaque. A few edge AA pixels are tolerated via the
# coverage threshold; a premultiplied/transparent frame fails well below it.
_ALPHA_OPAQUE_MIN = 250
_ALPHA_OPAQUE_COVERAGE = 0.999
_FIRST_FRAME_TIMEOUT_S = 5.0

_sessions: dict[int, "WgcCapture"] = {}
_sessions_lock = threading.Lock()


class CaptureContractError(RuntimeError):
    """Client size, alpha, or crop contract violated — fail loud, never silent."""


def client_crop_origin(hwnd: int, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """Map the live client rect into a WGC window frame.

    Recomputed from current Win32 geometry every call — never cached from startup.
    Horizontal extras are centred (WGC often omits DWM shadow that GetWindowRect
    includes). Vertical origin follows the title-bar fraction into the frame.
    """
    if sys.platform != "win32":
        raise CaptureContractError("WGC requires Windows")
    import win32gui

    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    cl, ct = win32gui.ClientToScreen(hwnd, (0, 0))
    _cl0, _ct0, cw, ch = win32gui.GetClientRect(hwnd)
    if cw < 2 or ch < 2:
        raise CaptureContractError(f"client rect too small: {cw}x{ch}")
    if frame_w < cw or frame_h < ch:
        raise CaptureContractError(
            f"WGC frame {frame_w}x{frame_h} smaller than client {cw}x{ch}"
        )

    ox = (frame_w - cw) // 2
    win_h = wb - wt
    if win_h <= 0:
        oy = 0
    else:
        oy = int(round((ct - wt) / win_h * frame_h))
    oy = max(0, min(frame_h - ch, oy))
    return ox, oy, cw, ch


def _assert_client_size(hwnd: int, width: int, height: int) -> None:
    rect = client_screen_rect(hwnd)
    if rect is None:
        raise CaptureContractError("client_screen_rect unavailable for size assert")
    expect_w = rect[2] - rect[0]
    expect_h = rect[3] - rect[1]
    if width != expect_w or height != expect_h:
        raise CaptureContractError(
            f"cropped frame {width}x{height} != client_screen_rect {expect_w}x{expect_h}"
        )


def _assert_opaque_bgra(bgra: np.ndarray) -> None:
    if bgra.ndim != 3 or bgra.shape[2] != 4:
        raise CaptureContractError(f"expected BGRA HxWx4, got shape {bgra.shape}")
    alpha = bgra[:, :, 3]
    if alpha.shape[0] > 4 and alpha.shape[1] > 4:
        alpha = alpha[2:-2, 2:-2]
    coverage = float((alpha >= _ALPHA_OPAQUE_MIN).mean())
    if coverage < _ALPHA_OPAQUE_COVERAGE:
        raise CaptureContractError(
            f"WGC alpha not opaque: coverage>={_ALPHA_OPAQUE_MIN} is {coverage:.4f} "
            f"(min={int(alpha.min())}, median={int(np.median(alpha))}); "
            "premultiplied or transparent frames corrupt RGB conversion"
        )


def _crop_client_bgra(hwnd: int, window_bgra: np.ndarray) -> np.ndarray:
    fh, fw = window_bgra.shape[:2]
    ox, oy, cw, ch = client_crop_origin(hwnd, fw, fh)
    cropped = np.ascontiguousarray(window_bgra[oy : oy + ch, ox : ox + cw])
    if cropped.shape[0] != ch or cropped.shape[1] != cw:
        raise CaptureContractError(
            f"crop produced {cropped.shape[1]}x{cropped.shape[0]}, expected {cw}x{ch}"
        )
    _assert_client_size(hwnd, cw, ch)
    _assert_opaque_bgra(cropped)
    return cropped


class WgcCapture:
    """Persistent WGC session for one hwnd; ``grab`` returns client-area BGRA."""

    def __init__(self, hwnd: int) -> None:
        if sys.platform != "win32":
            raise CaptureContractError("WGC requires Windows")
        if not hwnd:
            raise CaptureContractError("hwnd required")
        self.hwnd = int(hwnd)
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._control: Any = None
        self._capture: Any = None
        self.border_disabled = False
        self._start_session()

    def _start_session(self) -> None:
        from windows_capture import Frame, InternalCaptureControl, WindowsCapture

        # draw_border=False → GraphicsCaptureSession.IsBorderRequired = false
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=self.hwnd,
            minimum_update_interval=0,
        )
        self.border_disabled = True

        @capture.event
        def on_frame_arrived(frame: Frame, _control: InternalCaptureControl) -> None:
            # Copy out of the mapped buffer; the native mapping is only valid
            # for the duration of the callback.
            buf = np.ascontiguousarray(frame.frame_buffer)
            with self._lock:
                self._latest = buf

        @capture.event
        def on_closed() -> None:
            _LOGGER.debug("WGC session closed for hwnd=%s", self.hwnd)

        self._capture = capture
        self._control = capture.start_free_threaded()
        deadline = time.monotonic() + _FIRST_FRAME_TIMEOUT_S
        while time.monotonic() < deadline:
            with self._lock:
                if self._latest is not None:
                    return
            time.sleep(0.01)
        raise CaptureContractError(
            f"WGC produced no frame within {_FIRST_FRAME_TIMEOUT_S}s for hwnd={self.hwnd}"
        )

    def grab(self) -> CaptureFrame | None:
        with self._lock:
            latest = None if self._latest is None else self._latest.copy()
        if latest is None:
            return None
        try:
            cropped = _crop_client_bgra(self.hwnd, latest)
        except CaptureContractError:
            raise
        except Exception as exc:
            _LOGGER.debug("WGC crop failed: %s", exc)
            return None
        return CaptureFrame(
            data=cropped.tobytes(),
            width=int(cropped.shape[1]),
            height=int(cropped.shape[0]),
            backend="wgc",
        )

    def close(self) -> None:
        control = self._control
        self._control = None
        self._capture = None
        if control is not None:
            try:
                control.stop()
            except Exception:
                pass
            try:
                control.wait()
            except Exception:
                pass
        with self._lock:
            self._latest = None


def get_wgc_capture(hwnd: int) -> WgcCapture:
    """Shared session per hwnd so grab_rgb_image and CaptureLoop share one stream."""
    key = int(hwnd)
    with _sessions_lock:
        existing = _sessions.get(key)
        if existing is not None:
            return existing
        created = WgcCapture(key)
        _sessions[key] = created
        return created


def release_wgc_capture(hwnd: int | None = None) -> None:
    with _sessions_lock:
        if hwnd is None:
            items = list(_sessions.items())
            _sessions.clear()
        else:
            key = int(hwnd)
            cap = _sessions.pop(key, None)
            items = [(key, cap)] if cap is not None else []
    for _, cap in items:
        if cap is not None:
            cap.close()
