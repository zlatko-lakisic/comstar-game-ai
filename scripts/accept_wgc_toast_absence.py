"""Acceptance: foreign topmost window over the game is absent from WGC frames.

Creates a bright coloured top-level window owned by this process, places it over
the Rome client, grabs via the agent WGC path, and asserts the colour is absent.
MSS region capture would see it; window capture must not.

Usage:
  python scripts/accept_wgc_toast_absence.py
"""

from __future__ import annotations

import sys
import time

import numpy as np

TOAST_RGB = (0, 255, 0)  # pure green — not a Rome UI colour


def main() -> int:
    if sys.platform != "win32":
        print("Windows required")
        return 1

    import win32con
    import win32gui

    from comstar_game_ai.game_io.campaign.ui_mode import _bgra_to_rgb_image
    from comstar_game_ai.game_io.capture.factory import grab_capture_frame
    from comstar_game_ai.game_io.capture.window_capture import client_screen_rect
    from comstar_game_ai.game_io.capture.wgc_capture import release_wgc_capture
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings") or ["Rome"])
    if game is None:
        print("FAIL  no game window")
        return 1

    rect = client_screen_rect(game.hwnd)
    if rect is None:
        print("FAIL  no client rect")
        return 1
    left, top, right, bottom = rect
    tw, th = 200, 120
    tx = left + (right - left - tw) // 2
    ty = top + (bottom - top - th) // 2

    # COLORREF is 0x00BBGGRR
    colorref = TOAST_RGB[0] | (TOAST_RGB[1] << 8) | (TOAST_RGB[2] << 16)
    brush = win32gui.CreateSolidBrush(colorref)

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = win32gui.DefWindowProc
    wc.lpszClassName = "ComstarWgcToastProbe"
    wc.hbrBackground = brush
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass

    hwnd = win32gui.CreateWindowEx(
        win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
        wc.lpszClassName,
        "wgc-toast-probe",
        win32con.WS_POPUP | win32con.WS_VISIBLE,
        tx,
        ty,
        tw,
        th,
        0,
        0,
        0,
        None,
    )
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        tx,
        ty,
        tw,
        th,
        win32con.SWP_SHOWWINDOW,
    )
    win32gui.UpdateWindow(hwnd)
    time.sleep(0.4)

    try:
        frame = grab_capture_frame(game.hwnd)
        if frame is None:
            print("FAIL  WGC grab returned nothing")
            return 1
        if frame.backend != "wgc":
            print(f"FAIL  backend={frame.backend!r} (need wgc)")
            return 1
        rgb = _bgra_to_rgb_image(frame)
        arr = np.asarray(rgb.convert("RGB"), dtype=np.int16)
        target = np.asarray(TOAST_RGB, dtype=np.int16)
        count = int(np.all(np.abs(arr - target) <= 30, axis=2).sum())
        total = frame.width * frame.height
        print(f"backend={frame.backend} size={frame.width}x{frame.height}")
        print(f"toast_rgb={TOAST_RGB} matching_pixels={count} of {total}")
        if count > 64:
            print("FAIL  foreign window leaked into WGC frame (still region capture?)")
            rgb.save("data/runtime/wgc-toast-leak.png")
            return 1
        print("PASS  foreign topmost window absent from WGC frame")
        return 0
    finally:
        try:
            win32gui.DestroyWindow(hwnd)
        except Exception:
            pass
        release_wgc_capture(game.hwnd)


if __name__ == "__main__":
    raise SystemExit(main())
