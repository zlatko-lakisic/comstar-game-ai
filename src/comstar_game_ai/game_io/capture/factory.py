"""Capture backend selection.

Production runs use WGC only. MSS remains constructible for A/B scripts by
passing ``backend='mss'`` explicitly — never via ``capture.backend`` config
(that value fails startup preconditions).
"""

from __future__ import annotations

from typing import Protocol

from comstar_game_ai.game_io.capture.window_capture import CaptureFrame, WindowCapture
from comstar_game_ai.shared.config import load_config


class FrameGrabber(Protocol):
    def grab(self) -> CaptureFrame | None: ...


def configured_capture_backend(config: dict | None = None) -> str:
    cfg = config if config is not None else load_config()
    raw = (cfg.get("capture") or {}).get("backend") or "wgc"
    return str(raw).strip().lower() or "wgc"


def capture_for_hwnd(
    hwnd: int,
    *,
    backend: str | None = None,
) -> FrameGrabber:
    """Return a grabber for ``hwnd``.

    Default backend comes from config (must be ``wgc`` for Process A runs).
    Pass ``backend='mss'`` only from benchmark tooling to construct the
    unsupported region-capture path without going through config.
    """
    choice = (backend or configured_capture_backend()).lower()
    if choice == "wgc":
        from comstar_game_ai.game_io.capture.wgc_capture import get_wgc_capture

        return get_wgc_capture(hwnd)
    if choice == "mss":
        return WindowCapture(hwnd)
    raise ValueError(
        f"unknown capture backend {choice!r}; production supports 'wgc' only "
        "(construct WindowCapture / backend='mss' only from A/B tooling)"
    )


def grab_capture_frame(hwnd: int | None, *, backend: str | None = None) -> CaptureFrame | None:
    """One client-area frame with backend metadata (agent capture path)."""
    if not hwnd:
        return None
    return capture_for_hwnd(int(hwnd), backend=backend).grab()
