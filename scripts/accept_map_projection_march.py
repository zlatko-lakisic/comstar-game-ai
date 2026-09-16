"""Live acceptance: Flavius march via map projection (right-click).

Requires Rome Remastered focused on the Julii campaign map.

Defaults target a short west step from the live Arretium frustum
(``from≈67.5,88.7`` → ``62,88.7``) — the Z7 landed case.

For Segesta from Arretium, pass belief Segesta coords; the director must take
the **far / radar-frame** path (live dist > 12) or refuse
``belief_from_mismatch`` if belief Flavius is still stale at (89,82)::

    python scripts/accept_map_projection_march.py \\
        --from-x 67.5 --from-y 88.7 --to-x 83 --to-y 84 --label Segesta

Usage (from repo root, game running)::

    python scripts/accept_map_projection_march.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Live 2026-09-11: Flavius is Faction Leader at Arretium; belief (89,82)/
    # Segesta near-case is stale. Defaults are the landed Z7 short west march.
    parser.add_argument("--from-x", type=float, default=67.5)
    parser.add_argument("--from-y", type=float, default=88.7)
    parser.add_argument("--to-x", type=float, default=62.0)
    parser.add_argument("--to-y", type=float, default=88.7)
    parser.add_argument("--character", default="Flavius Julius")
    parser.add_argument("--label", default="near-west")
    parser.add_argument(
        "--wrong-row",
        nargs=2,
        type=float,
        default=(0.30, 0.42),
        metavar=("X", "Y"),
        help="Preferred Military Forces row (Flavius ~0.30 0.42 this save)",
    )
    parser.add_argument(
        "--park-home",
        action="store_true",
        help="Press Home first so the camera is away from Segesta",
    )
    args = parser.parse_args()

    from comstar_game_ai.game_io.campaign.march import MarchDirector
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("ACCEPT FAIL: Rome window not found", flush=True)
        return 2

    hwnd = game.hwnd
    controller = SendInputController()
    controller.focus_window(hwnd)
    if args.park_home:
        print("ACCEPT: parking camera with Home", flush=True)
        controller.tap_key("home", dwell_ms=50, hwnd=hwnd)
        time.sleep(2.0)

    debug = ROOT / "data" / "runtime" / "map_projection_debug"
    director = MarchDirector(
        hwnd=hwnd,
        controller=controller,
        use_map_projection=True,
        allow_legacy_geometry=False,
        locate_target=None,
        debug_frame_dir=debug,
        hover_dwell_s=1.4,
        order_settle_s=3.0,
    )

    wrong = (float(args.wrong_row[0]), float(args.wrong_row[1]))
    print(
        f"ACCEPT: march {args.character} -> {args.label} "
        f"from=({args.from_x},{args.from_y}) to=({args.to_x},{args.to_y}) "
        f"preferred_wrong_row={wrong}",
        flush=True,
    )
    outcome = director.march(
        from_x=args.from_x,
        from_y=args.from_y,
        to_x=args.to_x,
        to_y=args.to_y,
        lists_row=wrong,
        character_name=args.character,
        target_label=args.label,
    )
    print(
        f"ACCEPT: ordered={outcome.ordered} reason={outcome.reason} "
        f"button={outcome.button} calib={outcome.calib_mode} "
        f"click={outcome.click_norm} glyph={outcome.cursor_changed} "
        f"who={outcome.selected_character}",
        flush=True,
    )
    if not outcome.ordered:
        return 1
    if outcome.button != "right":
        print("ACCEPT FAIL: expected right-click", flush=True)
        return 1
    if not outcome.cursor_changed:
        print("ACCEPT FAIL: expected cursor glyph before click", flush=True)
        return 1
    print("ACCEPT OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
