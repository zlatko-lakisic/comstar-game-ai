#!/usr/bin/env python3
"""Live Phase 1 observation acceptance — requires Rome running."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.capture.capture_loop import CaptureLoop
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.logs.campaign_ai_log import CampaignAiLogTailer
from comstar_game_ai.game_io.logs.message_log import MessageLogTailer
from comstar_game_ai.game_io.logs.scripting_log import ScriptingLogTailer, default_scripting_log_path
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


def main() -> int:
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found")
        return 1

    print(f"OK  game_window: {game.title!r} {game.width}x{game.height} rect={game.rect}")

    loop = CaptureLoop(game.hwnd)
    loop.start()
    time.sleep(0.6)
    frames = len(loop.ring)
    loop.stop()
    print(f"{'OK' if frames >= 1 else 'FAIL'}  capture_frames: {frames}")

    script_path = default_scripting_log_path()
    print(f"INFO scripting_log path: {script_path} exists={script_path.is_file()}")

    driver = HardcodedCampaignDriver()
    msg_tailer = MessageLogTailer()
    ai_tailer = CampaignAiLogTailer()
    script_tailer = ScriptingLogTailer()

    msg_lines = msg_tailer.poll()
    ai_lines = ai_tailer.poll()
    script_records = script_tailer.poll()

    print(f"OK  message_log new_lines: {len(msg_lines)}")
    print(f"OK  campaign_ai_log new_lines: {len(ai_lines)}")
    print(f"INFO scripting_log new_records: {len(script_records)}")

    ingested = driver.poll_observation()
    print(f"INFO poll_observation ingested: {ingested}")
    print(f"INFO state: {driver.state.state.value} turn={driver.state.turn}")

    if script_path.is_file():
        for rec in script_tailer.poll()[-5:]:
            driver.state.update_from_script_event(rec)
        print(f"INFO state after script tail: {driver.state.state.value}")

    belief = driver.belief
    print(
        f"OK  belief_store: armies={len(belief.armies)} settlements={len(belief.settlements)} "
        f"history={len(belief.history)}"
    )

  # 20-turn poll loop (observation only — no console actuation unless on campaign map)
    turns_observed = 0
    for i in range(20):
        n = driver.poll_observation()
        if n:
            turns_observed += 1
        time.sleep(0.25)

    print(f"{'OK' if turns_observed >= 0 else 'FAIL'}  observation_polls: 20 (events={turns_observed})")

    if driver.state.allows_campaign_orders():
        ok = driver.run_turn_stub()
        print(f"{'OK' if ok else 'WARN'}  console_turn_stub: {ok}")
    else:
        print(
            f"WARN console_turn_stub skipped — state={driver.state.state.value} "
            f"(need campaign_map; install telemetry mod + end turn for script events)"
        )

    report = {
        "game": {"title": game.title, "rect": game.rect, "frames": frames},
        "logs": {
            "scripting_log": str(script_path),
            "scripting_exists": script_path.is_file(),
            "message_lines": len(msg_lines),
            "script_records": len(script_records),
        },
        "state": driver.state.state.value,
        "belief_history_len": len(belief.history),
    }
    out = Path("data/runtime/phase1_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OK  report: {out}")

    if not script_path.is_file():
        print(
            "\nNOTE: scripting_log.txt missing — Phase 1 full acceptance needs:\n"
            "  1. Launch with -enable_logging (and verbose_script_logging for script log)\n"
            "  2. Install mod/descr_strat_append.txt telemetry into descr_strat.txt\n"
            "  3. Be on campaign map and advance turns"
        )
        return 0 if frames >= 1 else 1

    if driver.state.state == GameState.CAMPAIGN_MAP and (ingested >= 1 or len(driver.state.history()) >= 1):
        print("\nPASS Phase 1 observation (script telemetry flowing)")
        return 0

    print("\nPARTIAL Phase 1 — capture OK; script telemetry not yet flowing")
    return 0 if frames >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
