"""Live helpers: camera pose reset acceptance and scale calibration.

Usage (game focused, campaign map):

  # Hostile start → reset → verify (logs AABB)
  python scripts/accept_camera_pose_reset.py --hostile

  # Quiesce must refuse when timeout is tiny
  python scripts/accept_camera_pose_reset.py --short-quiesce

  # P6: print measured AABB width after reset (paste into config)
  python scripts/accept_camera_pose_reset.py --calibrate-scale

  # P7: try both sequences and print which leaves army centred + pose ok
  python scripts/accept_camera_pose_reset.py --sequence-probe
"""

from __future__ import annotations

import argparse
import sys
import time


def _game_and_director(*, quiesce_timeout: float | None = None):
    from comstar_game_ai.game_io.campaign.camera_pose import CameraPoseDirector
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings") or ["Rome"])
    if game is None:
        raise SystemExit("no game window")
    cam = dict((cfg.get("campaign") or {}).get("camera") or {})
    if quiesce_timeout is not None:
        cam = {
            **cam,
            "quiesce": {**(cam.get("quiesce") or {}), "timeout_s": quiesce_timeout},
        }
    ctrl = SendInputController()
    director = CameraPoseDirector(
        hwnd=game.hwnd,
        controller=ctrl,
        capture=lambda: grab_rgb_image(game.hwnd),
        sleep=time.sleep,
        config=cam,
    )
    return game, director, cam


def cmd_hostile(director) -> int:
    # Saturate zoom in + rotate to make a hostile start, then reset.
    for _ in range(10):
        director._tap("zoom_in", times=1)
    for _ in range(8):
        director._tap("rot_r", times=1)
    time.sleep(0.5)
    result = director.ensure_canonical(from_xy=None, already_located=False)
    print(result)
    return 0 if result.ok else 1


def cmd_short_quiesce(director) -> int:
    director._tap("zoom_in", times=3)
    settled = director.quiesce()
    print("quiesce_result", settled)
    return 0 if settled is None else 1  # expect timeout → None


def cmd_calibrate(director) -> int:
    result = director.ensure_canonical(from_xy=None, already_located=False)
    if not result.ok or result.measured is None:
        print("FAIL calibrate", result)
        return 1
    m = result.measured
    print(
        f"CALIB aabb_w={m.width:.2f} aabb_h={m.height:.2f} aspect={m.aspect:.3f} "
        f"— set campaign.camera.verify.expected_aabb_width_map: {m.width:.1f}"
    )
    print(
        "P6 scale: with army at known map xy after locate+reset, "
        "solve DEFAULT_ANCHOR_SCALE from one additional known client point; "
        "record pose + date beside the constant."
    )
    return 0


def cmd_sequence_probe(director, game) -> int:
    """P7: compare locate_then_reset vs reset_then_locate (army centre after both)."""
    from comstar_game_ai.game_io.campaign.march import MarchDirector

    # Without a full Lists locate here we only report reset+verify behaviour.
    # Full evidence needs accept_map_projection_march with both sequences.
    print(
        "P7 probe: run accept_map_projection_march twice with "
        "campaign.camera.reset_sequence set to locate_then_reset then "
        "reset_then_locate; keep the order that leaves frustum centre on "
        "from_xy AND pose verify ok. Record the winner in "
        "map-window-projection.md § Canonical camera pose."
    )
    result = director.ensure_canonical(from_xy=None, already_located=False)
    print("reset_only", result)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostile", action="store_true")
    parser.add_argument("--short-quiesce", action="store_true")
    parser.add_argument("--calibrate-scale", action="store_true")
    parser.add_argument("--sequence-probe", action="store_true")
    parser.add_argument("--countdown", type=int, default=3)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Windows required")
        return 1
    print(f"focus the game — starting in {args.countdown}s", flush=True)
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)
    if args.short_quiesce:
        _game, director, _cam = _game_and_director(quiesce_timeout=0.05)
        return cmd_short_quiesce(director)
    game, director, _cam = _game_and_director()
    if args.calibrate_scale:
        return cmd_calibrate(director)
    if args.sequence_probe:
        return cmd_sequence_probe(director, game)
    if args.hostile:
        return cmd_hostile(director)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
