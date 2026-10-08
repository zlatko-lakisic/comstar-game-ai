"""Sample show_cursorstat for a homography, at one zoom notch.

Run from your own terminal, campaign map, console closed. This does not fit
anything. The held-out indices are written before the first probe.

    python scripts/capture_homography_session.py --session zoom0 --zoom-notch 0 --countdown 5

Then scroll once and zoom one notch when asked. Those two probes measure drift.
Repeat with a new --session at two other zoom notches.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSIONS = ROOT / "data" / "runtime" / "homography_sessions"

# Inside the map viewport, clear of the parchment and the radar.
_XS = (0.14, 0.28, 0.42, 0.56, 0.70)
_YS = (0.16, 0.26, 0.36, 0.46, 0.54)


def _grid() -> list[tuple[float, float]]:
    return [(x, y) for y in _YS for x in _XS]


def _bind_focus(shell, hwnd: int) -> None:
    import win32gui

    def focus_game() -> bool:
        for _ in range(8):
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as exc:
                print(f"focus: {exc}", flush=True)
                return False
            time.sleep(0.05)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        return False

    shell.focus_game = focus_game


def _probe(shell, hwnd: int, client: tuple[float, float] | None, dest: Path) -> dict:
    from PIL import Image

    from comstar_game_ai.game_io.campaign.combat import client_norm_to_screen
    from comstar_game_ai.game_io.campaign.console_cursorstat import read_console_cursorstat
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.game_focus import game_input_session

    started = time.perf_counter()
    screen = None
    if client is not None:
        screen = client_norm_to_screen(hwnd, client[0], client[1])
        if screen is None or shell.input_controller is None:
            return {"ok": False, "reason": "aim"}
    with game_input_session(hwnd):
        if screen is not None:
            if not shell.input_controller.move_mouse(*screen):
                return {"ok": False, "reason": "move"}
            time.sleep(0.5)
        if not shell.send_command("show_cursorstat", open_console=True):
            return {"ok": False, "reason": "command"}
        time.sleep(0.55)
        frame = grab_rgb_image(hwnd)
        shell.close_console()
    seconds = time.perf_counter() - started
    if frame is None:
        return {"ok": False, "reason": "frame", "seconds": seconds}
    frame.save(dest)
    reading = read_console_cursorstat(Image.open(dest))
    xy = list(reading.xy) if reading.xy is not None else None
    print(
        f"saved {dest.name} xy={xy} {seconds:.2f}s",
        flush=True,
    )
    return {"ok": True, "xy": xy, "seconds": round(seconds, 3), "reason": reading.reason}


def _settlement_targets(faction: str) -> list[tuple[str, list[int] | None]]:
    from comstar_game_ai.game_io.campaign.start_position import (
        load_start_position,
        strat_faction_name,
    )

    start = load_start_position()
    names = ["Segesta"]
    if start is not None:
        own = start.factions.get(strat_faction_name(faction))
        if own is not None:
            for entry in own.settlements:
                region = start.regions.get(str(entry.get("region") or ""))
                if region is not None and region.settlement:
                    names.append(region.settlement)
    found: list[tuple[str, list[int] | None]] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        expected = None
        if start is not None:
            region = start.region_of_settlement(name)
            if region is not None and region.x is not None and region.y is not None:
                expected = [int(region.x), int(region.y)]
        found.append((name, expected))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--zoom-notch", type=int, required=True)
    parser.add_argument("--countdown", type=int, default=5)
    parser.add_argument("--faction", default="julii")
    args = parser.parse_args(argv)

    from comstar_game_ai.game_io.campaign.map_homography import GRID_HELD_OUT
    from comstar_game_ai.game_io.console.romeshell import RomeShell
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    if sys.platform != "win32":
        print("FAIL: Windows required", flush=True)
        return 1
    out = SESSIONS / args.session
    if out.exists():
        print(f"FAIL: {out} already exists", flush=True)
        return 1
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found", flush=True)
        return 1

    out.mkdir(parents=True)
    split = {
        "held_out": list(GRID_HELD_OUT),
        "locked_before_fit": True,
        "zoom_notch": args.zoom_notch,
    }
    (out / "split.json").write_text(json.dumps(split, indent=2), encoding="utf-8")
    print(
        f"focus the game, zoom notch {args.zoom_notch}, console closed — "
        f"starting in {args.countdown}s",
        flush=True,
    )
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)

    shell = RomeShell(hwnd=game.hwnd)
    _bind_focus(shell, game.hwnd)
    points = []
    for index, client in enumerate(_grid()):
        dest = out / f"grid_{index:02d}.png"
        probed = _probe(shell, game.hwnd, client, dest)
        points.append(
            {
                "index": index,
                "client": [round(client[0], 4), round(client[1], 4)],
                "xy": probed.get("xy"),
                "seconds": probed.get("seconds"),
                "file": dest.name,
            }
        )
        time.sleep(0.2)

    settlements = []
    for name, expected in _settlement_targets(args.faction):
        print(
            f"Hover the ground of {name} (not the name plaque). "
            "Press Enter here, then click the game and hold.",
            flush=True,
        )
        try:
            input()
        except EOFError:
            break
        for i in range(args.countdown, 0, -1):
            print(f"  {i}...", flush=True)
            time.sleep(1)
        dest = out / f"settlement_{name.lower()}.png"
        probed = _probe(shell, game.hwnd, None, dest)
        settlements.append(
            {
                "name": name,
                "expected": expected,
                "xy": probed.get("xy"),
                "file": dest.name,
            }
        )

    drift_client = (0.42, 0.36)
    print("Drift probe, camera still.", flush=True)
    before = _probe(shell, game.hwnd, drift_client, out / "drift_before.png")
    print("Scroll the camera a short distance. Press Enter, then click the game.", flush=True)
    try:
        input()
    except EOFError:
        pass
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)
    after_scroll = _probe(shell, game.hwnd, drift_client, out / "drift_scroll.png")
    print("Zoom one notch. Press Enter, then click the game.", flush=True)
    try:
        input()
    except EOFError:
        pass
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)
    after_zoom = _probe(shell, game.hwnd, drift_client, out / "drift_zoom.png")

    payload = {
        "zoom_notch": args.zoom_notch,
        "width": 1280,
        "height": 720,
        "points": points,
        "settlements": settlements,
        "drift": {
            "client": [drift_client[0], drift_client[1]],
            "before": before.get("xy"),
            "after_scroll": after_scroll.get("xy"),
            "after_zoom": after_zoom.get("xy"),
        },
        "cycle_seconds": [point["seconds"] for point in points if point["seconds"] is not None],
    }
    (out / "samples.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"session {out} points={len(points)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
