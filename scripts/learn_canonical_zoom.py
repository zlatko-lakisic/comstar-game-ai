"""Learn max safe zoom-out (H) and pick fidelity-biased zoom_steps_from_max_in.

Policy (operator 2026-09-11): zoom out only enough for the job — do not push
toward H for reach. Canonical N stays well inside the banner / overlay hazard.

  python scripts/learn_canonical_zoom.py --countdown 4 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path


def _banner_score(rgb) -> float:
    """Warm fraction in the top-centre toast band (toggle-overlay banner)."""
    from comstar_game_ai.game_io.campaign.map_surface import _legend_warm_fraction

    return _legend_warm_fraction(rgb, (0.25, 0.02, 0.75, 0.10))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countdown", type=int, default=4)
    parser.add_argument("--max-out", type=int, default=55)
    parser.add_argument(
        "--fidelity-max-steps",
        type=int,
        default=14,
        help="Never zoom out more than this from max-in (fidelity bias)",
    )
    parser.add_argument(
        "--margin-from-h",
        type=int,
        default=8,
        help="Extra steps kept inside H even if fidelity_max would allow more",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write zoom_steps_from_max_in into config/default.yaml",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/runtime/learn_canonical_zoom"))
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Windows required")
        return 1

    from comstar_game_ai.game_io.campaign.camera_pose import CameraPoseDirector
    from comstar_game_ai.game_io.campaign.map_surface import check_map_surface
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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print("recover: Home + north", flush=True)
    director._tap("point_to_north", times=1, dwell_ms=40)
    ctrl.tap_key("home", dwell_ms=40, hwnd=game.hwnd)
    time.sleep(1.0)

    if not director.reset_zoom():
        print("FAIL: zoom_in saturate")
        return 1
    time.sleep(0.4)
    clean, clamp_stats = director.verify_in_clamp_surface()
    print(f"in_clamp_clean={clean} {clamp_stats}", flush=True)
    if not clean:
        print("FAIL: in-clamp is Map Overlay — stop")
        return 2

    h_banner: int | None = None
    h_overlay: int | None = None
    rows: list[dict] = []
    for press in range(0, args.max_out + 1):
        if press > 0:
            director._tap("zoom_out", times=1, dwell_ms=35)
            time.sleep(0.3)
        image = grab_rgb_image(game.hwnd)
        if image is None:
            print(f"FAIL: no frame at {press}")
            return 1
        surface = check_map_surface(image)
        banner = _banner_score(image)
        row = {
            "press": press,
            "banner_warm": round(banner, 4),
            **surface.as_log_dict(),
        }
        rows.append(row)
        image.save(out_dir / f"{press:02d}.jpg")
        print(
            f"press={press} banner={banner:.3f} overlay={surface.is_map_overlay} "
            f"legL={surface.stats.legend_warm_left:.3f} legR={surface.stats.legend_warm_right:.3f}",
            flush=True,
        )
        if h_banner is None and banner >= 0.08:
            h_banner = press
            print(f"H_banner = {press}", flush=True)
        if h_overlay is None and surface.is_map_overlay:
            h_overlay = press
            print(f"H_overlay = {press}", flush=True)
            break

    # Hazard for keyboard path: banner first, else overlay, else plateau.
    h = h_banner if h_banner is not None else h_overlay
    if h is None:
        # X often clamps with banner before overlay; treat last changing press.
        h = args.max_out
        print(f"WARN: no banner/overlay seen — using max_out={h} as soft H", flush=True)

    # Fidelity-first: never beyond fidelity_max_steps; also keep margin inside H.
    n = min(args.fidelity_max_steps, max(0, h - args.margin_from_h))
    # Near marches (Segesta) need only modest context after Lists-locate.
    report = {
        "window_client": {"width": size[0], "height": size[1]} if size else None,
        "in_clamp_stats": clamp_stats,
        "H_banner": h_banner,
        "H_overlay": h_overlay,
        "H_used": h,
        "fidelity_max_steps": args.fidelity_max_steps,
        "margin_from_h": args.margin_from_h,
        "zoom_steps_from_max_in": n,
        "policy": "fidelity_first_inside_H",
        "steps": rows,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "window_client", "H_banner", "H_overlay", "H_used", "zoom_steps_from_max_in"
    )}, indent=2))

    if args.apply:
        path = Path("config/default.yaml")
        text = path.read_text(encoding="utf-8")
        pattern = r"(zoom_steps_from_max_in:\s*)(?:null|\d+)"
        if not re.search(pattern, text):
            print("FAIL: could not find zoom_steps_from_max_in in config")
            return 1
        text = re.sub(pattern, rf"\g<1>{n}", text, count=1)
        path.write_text(text, encoding="utf-8")
        print(f"OK wrote config zoom_steps_from_max_in: {n}")

    print(f"OK report {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
