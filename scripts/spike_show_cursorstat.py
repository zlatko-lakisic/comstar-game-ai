#!/usr/bin/env python3
"""Spike: is show_cursorstat machine-readable for map↔client calibration?

With Rome focused on the campaign map, samples several client points, runs
show_cursorstat, and fits an affine transform. Writes
data/runtime/cursorstat_spike.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from comstar_game_ai.game_io.campaign.combat import client_norm_to_screen
from comstar_game_ai.game_io.campaign.cursorstat import parse_cursorstat_text
from comstar_game_ai.game_io.campaign.map_projection import (
    MapClientSample,
    calibrate_affine,
    fit_residual_rms,
)
from comstar_game_ai.game_io.console.romeshell import RomeShell
from comstar_game_ai.game_io.logs.message_log import default_message_log_path
from comstar_game_ai.game_io.logs.scripting_log import default_scripting_log_path
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


def _tail_after(path: Path, offset: int) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return data[offset:].decode("utf-8", errors="replace")


def main() -> int:
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found")
        return 1

    msg_path = default_message_log_path()
    scr_path = default_scripting_log_path()
    msg_off = msg_path.stat().st_size if msg_path.is_file() else 0
    scr_off = scr_path.stat().st_size if scr_path.is_file() else 0

    shell = RomeShell(hwnd=game.hwnd)
    if not shell.focus_game():
        print("FAIL: could not focus Rome")
        return 1

    if shell.console_open:
        shell.close_console()

    probes = [(0.35, 0.40), (0.55, 0.45), (0.45, 0.60), (0.65, 0.35)]
    samples: list[MapClientSample] = []
    raw_chunks: list[str] = []

    for i, (cx, cy) in enumerate(probes):
        screen = client_norm_to_screen(game.hwnd, cx, cy)
        if screen is None:
            print(f"FAIL: no screen for probe {i}")
            return 1
        assert shell.input_controller is not None
        shell.input_controller.move_mouse(*screen)
        time.sleep(0.35)
        ok = shell.send_command("show_cursorstat", open_console=True)
        time.sleep(0.4)
        shell.close_console()
        time.sleep(0.25)
        chunk = _tail_after(msg_path, msg_off) + "\n" + _tail_after(scr_path, scr_off)
        msg_off = msg_path.stat().st_size if msg_path.is_file() else msg_off
        scr_off = scr_path.stat().st_size if scr_path.is_file() else scr_off
        raw_chunks.append(chunk)
        parsed = parse_cursorstat_text(chunk)
        print(
            f"probe {i} client=({cx:.2f},{cy:.2f}) send_ok={ok} "
            f"parsed={parsed} new_bytes={len(chunk)}"
        )
        if parsed is not None:
            samples.append(MapClientSample(client_xy=(cx, cy), map_xy=parsed))

    transform = None
    residual = None
    if len(samples) >= 3:
        transform = calibrate_affine(samples)
        residual = fit_residual_rms(transform, samples) if transform else None

    out = {
        "ok": transform is not None,
        "sample_count": len(samples),
        "samples": [
            {"client": list(s.client_xy), "map": list(s.map_xy)} for s in samples
        ],
        "residual_rms_client_norm": residual,
        "raw_tail_preview": [c[-400:] for c in raw_chunks],
    }
    path = Path("data/runtime/cursorstat_spike.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {path} ok={out['ok']} residual={residual}")
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
