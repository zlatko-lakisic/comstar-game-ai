"""Capture loop feeding ring buffer."""

from __future__ import annotations

import threading
import time
from typing import Callable

from comstar_game_ai.game_io.capture.factory import capture_for_hwnd, configured_capture_backend
from comstar_game_ai.game_io.capture.ring_buffer import RingBuffer
from comstar_game_ai.shared.config import load_config


class CaptureLoop:
    def __init__(
        self,
        hwnd: int,
        ring: RingBuffer | None = None,
        on_frame: Callable[[bytes, int, int], None] | None = None,
    ) -> None:
        cfg = load_config()
        cap_cfg = cfg.get("capture") or {}
        backend = configured_capture_backend(cfg)
        if backend != "wgc":
            raise RuntimeError(
                f"CaptureLoop requires capture.backend=wgc (got {backend!r}); "
                "mss is A/B-only and fails startup preconditions"
            )
        self._capture = capture_for_hwnd(hwnd, backend="wgc")
        self._hwnd = hwnd
        self._ring = ring or RingBuffer(max_seconds=float(cap_cfg.get("ring_buffer_seconds", 5)))
        self._fps = float(cap_cfg.get("target_fps", 30))
        self._on_frame = on_frame
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.measured_fps: float = 0.0

    @property
    def ring(self) -> RingBuffer:
        return self._ring

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        from comstar_game_ai.game_io.capture.wgc_capture import release_wgc_capture

        release_wgc_capture(self._hwnd)

    def _run(self) -> None:
        interval = 1.0 / max(self._fps, 1.0)
        got = 0
        t_origin = time.monotonic()
        while not self._stop.is_set():
            t0 = time.monotonic()
            frame = self._capture.grab()
            if frame and frame.data:
                self._ring.push(frame.data, frame.width, frame.height)
                got += 1
                elapsed_total = time.monotonic() - t_origin
                if elapsed_total > 0:
                    self.measured_fps = got / elapsed_total
                if self._on_frame:
                    self._on_frame(frame.data, frame.width, frame.height)
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))
