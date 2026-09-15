"""Capture campaign frames for YOLOX labeling (no overlay reticle).

Writes JPEGs under data/detection/raw/. With ``--auto-move``, pans/zooms
between grabs using campaign camera bindings (WASD / Z / X).

Usage::

    python scripts/detection/capture_frames.py --count 60 --auto-move
    python scripts/detection/capture_frames.py --count 20 --interval 2.0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Cycle of camera moves between frames (action, key presses).
_AUTO_MOVES: list[tuple[str, int]] = [
    ("pan_right", 8),
    ("pan_forward", 6),
    ("zoom_out", 2),
    ("pan_left", 10),
    ("pan_back", 6),
    ("zoom_in", 2),
    ("pan_right", 12),
    ("pan_forward", 8),
    ("zoom_out", 3),
    ("pan_left", 8),
    ("rot_l", 1),
    ("pan_back", 10),
    ("zoom_in", 3),
    ("rot_r", 1),
    ("pan_right", 6),
    ("pan_forward", 12),
]

# Stay at the user's zoom — small pans only (close settlement pass).
_PAN_ONLY_MOVES: list[tuple[str, int]] = [
    ("pan_right", 4),
    ("pan_forward", 3),
    ("pan_left", 5),
    ("pan_back", 3),
    ("pan_right", 3),
    ("pan_forward", 4),
    ("pan_left", 4),
    ("pan_back", 4),
    ("rot_l", 1),
    ("pan_right", 5),
    ("pan_forward", 3),
    ("rot_r", 1),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.5, help="Seconds after each move")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "detection" / "raw",
    )
    parser.add_argument(
        "--auto-move",
        action="store_true",
        help="Pan/zoom/rotate between grabs via campaign camera bindings",
    )
    parser.add_argument(
        "--pan-only",
        action="store_true",
        help="With --auto-move: small pans/rots only (no zoom) for close settlement passes",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=0,
        help="Seconds to wait after focus so you can aim at settlements",
    )
    args = parser.parse_args()

    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found", flush=True)
        return 2

    cam = (cfg.get("campaign") or {}).get("camera") or {}
    bindings = {str(k): str(v) for k, v in (cam.get("bindings") or {}).items()}

    args.out.mkdir(parents=True, exist_ok=True)
    controller = SendInputController()
    controller.focus_window(game.hwnd)
    time.sleep(0.3)

    if args.countdown > 0:
        print(
            f"\n>>> ZOOM IN ON SETTLEMENTS — capture starts in {args.countdown}s <<<\n",
            flush=True,
        )
        for i in range(args.countdown, 0, -1):
            print(f"  {i}...", flush=True)
            time.sleep(1)
        print("  CAPTURE START\n", flush=True)
        controller.focus_window(game.hwnd)
        time.sleep(0.2)

    def _tap_action(action: str, times: int) -> None:
        key = bindings.get(action)
        if not key:
            print(f"  skip move {action}: no binding", flush=True)
            return
        for _ in range(max(1, times)):
            controller.tap_key(key, dwell_ms=40, hwnd=game.hwnd)
            time.sleep(0.04)

    move_table = _PAN_ONLY_MOVES if args.pan_only else _AUTO_MOVES
    print(
        f"Capturing {args.count} frames -> {args.out} "
        f"(auto_move={args.auto_move} pan_only={args.pan_only})",
        flush=True,
    )
    for i in range(args.count):
        frame = grab_rgb_image(game.hwnd)
        if frame is None:
            print(f"FAIL: no frame at {i}", flush=True)
            return 3
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = args.out / f"{stamp}_{i:03d}.jpg"
        frame.convert("RGB").save(path, quality=92)
        print(f"  wrote {path.name} {frame.size}", flush=True)
        if i + 1 >= args.count:
            break
        if args.auto_move:
            action, times = move_table[i % len(move_table)]
            print(f"  move {action} x{times}", flush=True)
            controller.focus_window(game.hwnd)
            _tap_action(action, times)
        time.sleep(max(0.0, args.interval))
    print("Done. Next: auto_label_from_cv / automate_dataset", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
