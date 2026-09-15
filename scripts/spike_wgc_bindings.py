"""Spike: compare WGC bindings for hwnd capture (plan §1).

Winner: windows-capture (window_hwnd + draw_border=False).
dxcam winrt is monitor/region — disqualified (still captures foreign overlays).
"""

from __future__ import annotations

import statistics
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class SpikeResult:
    name: str
    ok: bool
    detail: str
    fps: float = 0.0
    convert_us: float = 0.0
    frame_wh: tuple[int, int] | None = None
    client_wh: tuple[int, int] | None = None
    window_wh: tuple[int, int] | None = None
    alpha_min: int | None = None
    border_api: str = ""


def _game():
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    return find_game_window(subs)


def _client_window_sizes(hwnd: int):
    import win32gui

    cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    return {
        "client_wh": (cr - cl, cb - ct),
        "window_wh": (wr - wl, wb - wt),
    }


def spike_windows_capture(hwnd: int, seconds: float = 2.0) -> SpikeResult:
    from windows_capture import Frame, InternalCaptureControl, WindowsCapture

    sizes = _client_window_sizes(hwnd)
    converts: list[float] = []
    frames = 0
    sample = None
    lock = threading.Lock()

    capture = WindowsCapture(
        cursor_capture=False,
        draw_border=False,
        window_hwnd=hwnd,
        minimum_update_interval=0,
    )
    stop_at = time.perf_counter() + seconds

    @capture.event
    def on_frame_arrived(frame: Frame, control: InternalCaptureControl):
        nonlocal frames, sample
        t0 = time.perf_counter()
        bgra = np.ascontiguousarray(frame.frame_buffer)
        _ = bgra.tobytes()
        converts.append((time.perf_counter() - t0) * 1e6)
        with lock:
            sample = bgra
            frames += 1
            if time.perf_counter() >= stop_at:
                control.stop()

    @capture.event
    def on_closed():
        pass

    t0 = time.perf_counter()
    control = capture.start_free_threaded()
    while time.perf_counter() < stop_at + 0.5:
        with lock:
            if frames > 0 and time.perf_counter() >= stop_at:
                break
        time.sleep(0.01)
    try:
        control.stop()
        control.wait()
    except Exception:
        pass
    elapsed = time.perf_counter() - t0

    if sample is None:
        return SpikeResult(
            "windows-capture",
            False,
            "no frames",
            border_api="draw_border=False",
            client_wh=sizes["client_wh"],
            window_wh=sizes["window_wh"],
        )

    h, w = sample.shape[:2]
    alpha_min = int(sample[:, :, 3].min())
    return SpikeResult(
        name="windows-capture",
        ok=True,
        detail=f"frames={frames} elapsed={elapsed:.3f}s",
        fps=frames / max(elapsed, 1e-6),
        convert_us=statistics.median(converts) if converts else 0.0,
        frame_wh=(w, h),
        client_wh=sizes["client_wh"],
        window_wh=sizes["window_wh"],
        alpha_min=alpha_min,
        border_api="draw_border=False",
    )


def spike_dxcam_winrt(hwnd: int, seconds: float = 1.0) -> SpikeResult:
    sizes = _client_window_sizes(hwnd)
    return SpikeResult(
        name="dxcam-winrt",
        ok=False,
        detail="DQ: monitor/region only — not hwnd-keyed; foreign overlays still captured",
        border_api="none",
        client_wh=sizes["client_wh"],
        window_wh=sizes["window_wh"],
    )


def main() -> int:
    if sys.platform != "win32":
        print("Windows required")
        return 1
    game = _game()
    if game is None:
        print("no game window")
        return 1
    print(f"hwnd={game.hwnd} title={game.title!r}", flush=True)
    results = [spike_windows_capture(game.hwnd), spike_dxcam_winrt(game.hwnd)]
    for r in results:
        print("---", flush=True)
        print(f"{r.name}: {'OK' if r.ok else 'FAIL/DQ'} — {r.detail}", flush=True)
        print(f"  fps={r.fps:.1f} convert_us_med={r.convert_us:.0f}", flush=True)
        print(
            f"  frame_wh={r.frame_wh} client_wh={r.client_wh} window_wh={r.window_wh}",
            flush=True,
        )
        print(f"  alpha_min={r.alpha_min} border={r.border_api}", flush=True)
    winner = next((r for r in results if r.ok), None)
    print("---", flush=True)
    print(f"winner: {winner.name if winner else 'NONE'}", flush=True)
    return 0 if winner else 1


if __name__ == "__main__":
    raise SystemExit(main())
