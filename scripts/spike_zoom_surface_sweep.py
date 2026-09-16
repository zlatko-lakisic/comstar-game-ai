"""Z1 in-clamp verify + Z2 zoom/surface sweep (live).

Usage (game focused on campaign map):

  python scripts/spike_zoom_surface_sweep.py --countdown 5

Saturates zoom_in, checks Z3 at max-in, then zooms out one press at a time
recording surface stats and a feature-scale proxy. Stops after reporting H and Q.
Does **not** lock zoom_steps_from_max_in or re-derive anchor_scale.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countdown", type=int, default=5)
    parser.add_argument("--max-out-presses", type=int, default=50)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/runtime/zoom_surface_sweep"),
    )
    parser.add_argument("--q-px-low", type=float, default=15.0)
    parser.add_argument("--q-px-high", type=float, default=20.0)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Windows required")
        return 1

    from comstar_game_ai.game_io.campaign.camera_pose import CameraPoseDirector
    from comstar_game_ai.game_io.campaign.map_surface import (
        check_map_surface,
        estimate_feature_scale_px,
    )
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.campaign.combat import client_size
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings") or ["Rome"])
    if game is None:
        print("FAIL: no game window")
        return 1

    cam = dict((cfg.get("campaign") or {}).get("camera") or {})
    # Sweep stays at max-in after saturate; steps not locked.
    pose = dict(cam.get("canonical_pose") or {})
    pose["zoom_steps_from_max_in"] = None
    cam["canonical_pose"] = pose

    ctrl = SendInputController()
    director = CameraPoseDirector(
        hwnd=game.hwnd,
        controller=ctrl,
        capture=lambda: grab_rgb_image(game.hwnd),
        sleep=time.sleep,
        config=cam,
    )

    print(f"focus the game — starting in {args.countdown}s", flush=True)
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1.0)

    size = client_size(game.hwnd)
    window_size = {"width": size[0], "height": size[1]} if size else None
    print(f"window_client={window_size}", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # Recover camera to a known campaign framing before measuring.
    print("pre-recover: Home (capital_zoom) + point_to_north + zoom_out x8", flush=True)
    director._tap("point_to_north", times=1, dwell_ms=40)
    ctrl.tap_key("home", dwell_ms=40, hwnd=game.hwnd)
    time.sleep(1.0)
    director._tap("zoom_out", times=8, dwell_ms=35)
    director._tap("point_to_north", times=1, dwell_ms=40)
    time.sleep(0.5)
    recover = grab_rgb_image(game.hwnd)
    if recover is not None:
        recover.save(out_dir / "00_recovered.jpg")

    # Z1: saturate in, verify surface clean.
    if not director.reset_zoom():
        print("FAIL: zoom_in saturate failed")
        return 1
    time.sleep(0.4)
    clean, clamp_stats = director.verify_in_clamp_surface()
    print(f"Z1 in_clamp_clean={clean} stats={clamp_stats}", flush=True)
    frame0 = grab_rgb_image(game.hwnd)
    if frame0 is not None:
        frame0.save(out_dir / "00_max_in.jpg")
    if not clean:
        print(
            "WARN: maximum zoom-in failed Z3 clean check — continuing sweep for H/Q; "
            "operator must confirm 00_max_in.jpg is usable 3D map.",
            flush=True,
        )

    rows: list[dict] = []
    h_press: int | None = None
    q_press: int | None = None
    map_stats_at_zero = clamp_stats
    overlay_stats = None
    overlay_streak = 0
    sustain = 3
    last_var: float | None = None
    plateau = 0
    mode = "key_x"

    def _wheel_zoom_out() -> None:
        if size is None:
            director._tap("zoom_out", times=1, dwell_ms=35)
            return
        # Aim at map centre (client → screen).
        import win32gui

        left, top, right, bottom = win32gui.GetClientRect(game.hwnd)
        cx = int((right - left) * 0.50)
        cy = int((bottom - top) * 0.40)
        sx, sy = win32gui.ClientToScreen(game.hwnd, (cx, cy))
        ctrl.mouse_wheel(sx, sy, notches=-1)

    for press in range(0, args.max_out_presses + 1):
        if press > 0:
            if mode == "key_x":
                director._tap("zoom_out", times=1, dwell_ms=35)
            else:
                _wheel_zoom_out()
            time.sleep(0.35)
        image = grab_rgb_image(game.hwnd)
        if image is None:
            print(f"FAIL: no frame at press={press}")
            return 1
        check = check_map_surface(image)
        feat = estimate_feature_scale_px(image)
        row = {
            "presses_from_max_in": press,
            "zoom_mode": mode,
            "feature_scale_px": round(feat, 2),
            **check.as_log_dict(),
        }
        rows.append(row)
        image.save(out_dir / f"{press:02d}_{mode}_out.jpg")
        print(
            f"press={press} mode={mode} overlay={check.is_map_overlay} "
            f"var={check.stats.variance:.5f} sat={check.stats.saturation_mean:.3f} "
            f"edges={check.stats.edge_density:.3f} luma={check.stats.mean_luma:.3f} "
            f"feat_px≈{feat:.1f}",
            flush=True,
        )
        if q_press is None and args.q_px_low <= feat <= args.q_px_high:
            q_press = press
            print(f"Q candidate at press={press} (feature_scale_px≈{feat:.1f})", flush=True)
        if last_var is not None and abs(check.stats.variance - last_var) < 1e-5:
            plateau += 1
        else:
            plateau = 0
        last_var = check.stats.variance
        # Keyboard zoom often clamps before scroll-to-overlay; switch to wheel.
        if mode == "key_x" and plateau >= 4 and h_press is None:
            mode = "wheel"
            plateau = 0
            print("INFO: X zoom plateau — continuing with mouse wheel toward overlay", flush=True)
        if check.is_map_overlay:
            overlay_streak += 1
        else:
            overlay_streak = 0
        if h_press is None and overlay_streak >= sustain:
            h_press = press - sustain + 1
            overlay_stats = check.as_log_dict()
            print(
                f"H = {h_press} (Z3 map_overlay sustained {sustain}; mode={mode})",
                flush=True,
            )
            break

    # Calibration fallback: open Map Overlay via Tab so both surfaces are recorded.
    tab_overlay_stats = None
    if h_press is None:
        print("INFO: H not found via zoom — Tab toggle for overlay calibration frame", flush=True)
        ctrl.tap_key("tab", dwell_ms=40, hwnd=game.hwnd)
        time.sleep(0.8)
        tab_im = grab_rgb_image(game.hwnd)
        if tab_im is not None:
            tab_im.save(out_dir / "tab_overlay.jpg")
            tab_check = check_map_surface(tab_im)
            tab_overlay_stats = tab_check.as_log_dict()
            print(f"tab_overlay stats={tab_overlay_stats}", flush=True)
            # Leave overlay so the operator is not stuck.
            ctrl.tap_key("tab", dwell_ms=40, hwnd=game.hwnd)
            time.sleep(0.4)

    report = {
        "window_client": window_size,
        "in_clamp_clean": clean,
        "in_clamp_stats": map_stats_at_zero,
        "H": h_press,
        "Q": q_press,
        "H_minus_Q": (None if h_press is None or q_press is None else h_press - q_press),
        "q_binding": (
            None
            if h_press is None or q_press is None
            else ("slack" if (h_press - q_press) > 8 else "binding_or_tight")
        ),
        "overlay_stats_at_H": overlay_stats,
        "tab_overlay_stats": tab_overlay_stats,
        "steps": rows,
        "note": (
            "Do not lock zoom_steps_from_max_in or re-derive anchor_scale from this report. "
            "Choose margin against H−Q; Q from feature_scale_px is a proxy — confirm on frames. "
            "If H is null, keyboard X clamped without Map Overlay; see wheel/tab notes."
        ),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "window_client", "H", "Q", "H_minus_Q", "q_binding", "in_clamp_stats", "overlay_stats_at_H"
    )}, indent=2))
    print(f"OK wrote {out_dir / 'report.json'}")
    return 0 if h_press is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
