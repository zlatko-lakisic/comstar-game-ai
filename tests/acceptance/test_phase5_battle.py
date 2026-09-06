"""Acceptance: battle driver writes after-action (mock console)."""

import tempfile
from pathlib import Path

from comstar_game_ai.game_io.battle.battle_driver import BattleDriver, BattleDriverConfig


def test_battle_after_action_record():
    with tempfile.TemporaryDirectory() as td:
        pos_dir = Path(td) / "battle"
        pos_dir.mkdir()
        (pos_dir / "comstar_unit_positions.txt").write_text(
            "alliance=0 army=0 unit=0 x=1 y=2 strength=80 facing=0\n",
            encoding="utf-8",
        )
        cfg = BattleDriverConfig(
            max_ticks=1,
            tick_seconds=0.0,
            positions_dir=pos_dir,
            prediction_log_path=Path(td) / "pred.jsonl",
        )
        driver = BattleDriver(run_console=lambda _c: True, config=cfg)
        result = driver.run()
        assert "after_action" in result
        assert result["after_action"]["battle_id"]
