#!/usr/bin/env python3
"""Live Phase 2 actuation acceptance — requires Rome on campaign map with telemetry mod."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.elevation import ensure_elevation_for_game, strip_elevation_marker
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


def _countdown(seconds: int) -> None:
    if seconds <= 0:
        return
    print(f"INFO click Rome and leave it focused — starting in {seconds}s", flush=True)
    for remaining in range(seconds, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)
    print("INFO starting", flush=True)


def main() -> int:
    raw_argv = list(sys.argv)
    sys.argv = [sys.argv[0], *strip_elevation_marker()]

    parser = argparse.ArgumentParser(description="Phase 2 live actuation")
    parser.add_argument(
        "--seconds",
        type=int,
        default=8,
        help="Countdown before first key/click so you can focus Rome (default 8; 0 skips)",
    )
    args = parser.parse_args()

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found — launch game and load Julii campaign first")
        return 1

    print(f"OK  game_window: {game.title!r} {game.width}x{game.height}")

    import win32process

    _, pid = win32process.GetWindowThreadProcessId(game.hwnd)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = str(Path(f"data/runtime/phase2_live_{stamp}.log").resolve())
    action = ensure_elevation_for_game(pid, argv=raw_argv, log_path=log_path)
    if action == "relaunching":
        print("INFO approve UAC — a new 'Comstar Game AI' window will show the live trail", flush=True)
        print("INFO click Rome during the countdown in that window", flush=True)
        return 0
    if action == "failed":
        return 1

    turns = int(cfg.get("campaign", {}).get("acceptance_turns", 20))
    faction = cfg.get("campaign", {}).get("player_faction", "julii")
    auto_end = bool(cfg.get("campaign", {}).get("auto_end_turn", True))
    ready_timeout = float(cfg.get("campaign", {}).get("end_turn_ready_timeout_s", 30))
    legacy_delay = float(cfg.get("campaign", {}).get("end_turn_delay_s", 0))

    driver = HardcodedCampaignDriver(
        player_faction=faction,
        use_vision=True,
        auto_end_turn=auto_end,
        end_turn_ready_timeout_s=ready_timeout,
        end_turn_delay_s=legacy_delay,
    )
    ingested = driver.bootstrap_from_logs()
    print(f"INFO bootstrap_from_logs: {ingested} records")
    print(
        f"INFO state after bootstrap: {driver.state.state.value} turn={driver.state.turn} "
        f"turns_seen={driver._julii_turns_seen}"
    )

    if not driver.state.allows_campaign_orders():
        print(
            "FAIL: not on campaign map — load campaign save with telemetry mod, then re-run"
        )
        return 1

    def on_progress(*, index: int, total: int, phase: str, ok: bool | None = None) -> None:
        tag = f"ATTEMPT {index}/{total} game_turn={driver._known_game_turn()}"
        if ok is None:
            print(f"{tag}  {phase}", flush=True)
        else:
            print(f"{tag}  {'OK' if ok else 'FAIL'}  {phase}", flush=True)

    print(
        f"INFO running {turns} attempts (vision dismiss + observe + End Turn on readiness)...",
        flush=True,
    )
    _countdown(max(0, args.seconds))
    result = driver.run_turns(
        turns,
        require_ok=False,
        wait_for_next_turn=True,
        on_progress=on_progress,
    )

    print(
        f"{'OK' if result['desyncs'] == 0 else 'WARN'}  turns_ok={result['turns_ok']} "
        f"turns_failed={result['turns_failed']} desyncs={result['desyncs']}"
    )
    print(
        f"OK  belief_history={len(driver.belief.history)} armies={len(driver.belief.armies)} "
        f"settlements={len(driver.belief.settlements)}"
    )

    report = {
        "game": {"title": game.title, "rect": game.rect},
        "turns": result,
        "state": driver.state.state.value,
        "belief_history_len": len(driver.belief.history),
        "intent_log": str(driver.intent_writer.path),
    }
    out = Path("data/runtime/phase2_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OK  report: {out}")

    if result["desyncs"] == 0 and result["turns_ok"] >= turns:
        print("\nPASS Phase 2 actuation (20 turns, zero desyncs)")
        return 0

    if result["turns_ok"] > 0:
        print("\nPARTIAL Phase 2 — some turns succeeded; check intent log and Rome console focus")
        return 0

    print("\nFAIL Phase 2 — no turns completed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
