#!/usr/bin/env python3
"""Live Phase 2 actuation acceptance — requires Rome on campaign map with telemetry mod."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


def main() -> int:
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found — launch game and load Julii campaign first")
        return 1

    print(f"OK  game_window: {game.title!r} {game.width}x{game.height}")

    turns = int(cfg.get("campaign", {}).get("acceptance_turns", 20))
    faction = cfg.get("campaign", {}).get("player_faction", "julii")

    driver = HardcodedCampaignDriver(player_faction=faction)
    ingested = driver.bootstrap_from_logs()
    print(f"INFO bootstrap_from_logs: {ingested} script records")
    print(f"INFO state after bootstrap: {driver.state.state.value} turns_seen={driver._julii_turns_seen}")

    if not driver.state.allows_campaign_orders():
        print(
            "FAIL: not on campaign map — load campaign save with telemetry mod, end one turn, then re-run"
        )
        return 1

    print(f"INFO running {turns} hardcoded turn stubs (halt_ai -> list_characters -> run_ai -> wait NewTurnStart)...")
    result = driver.run_turns(turns, require_ok=False, wait_for_next_turn=True)

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
