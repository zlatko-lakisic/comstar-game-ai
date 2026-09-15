"""Measure sustained WGC grab rate against capture.target_fps.

Usage:
  python scripts/measure_wgc_fps.py --seconds 3
"""

from __future__ import annotations

import argparse
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("Windows required")
        return 1

    from comstar_game_ai.game_io.capture.capture_loop import CaptureLoop
    from comstar_game_ai.game_io.capture.wgc_capture import release_wgc_capture
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    target = float((cfg.get("capture") or {}).get("target_fps", 30))
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings") or ["Rome"])
    if game is None:
        print("FAIL  no game window")
        return 1

    loop = CaptureLoop(game.hwnd)
    try:
        loop.start()
        time.sleep(max(0.5, args.seconds))
        measured = loop.measured_fps
        print(f"target_fps={target} measured_fps={measured:.1f} ring_len={len(loop.ring)}")
        # Allow some slack: WGC is event-driven; hitting >= 50% of target is the floor.
        if measured < target * 0.5:
            print(f"FAIL  measured FPS {measured:.1f} < half of target {target}")
            return 1
        print("PASS  measured FPS within acceptance band")
        return 0
    finally:
        loop.stop()
        release_wgc_capture(game.hwnd)


if __name__ == "__main__":
    raise SystemExit(main())
