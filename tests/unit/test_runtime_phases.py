"""Unit tests for runtime orchestration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from comstar_game_ai.agent.directive import neutral_directive, parse_directive
from comstar_game_ai.agent.runtime import AgentRuntime
from comstar_game_ai.game_io.battle.battle_driver import BattleDriver, BattleDriverConfig
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.hotkeys import parse_hotkey
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore


def test_parse_hotkey():
    mods, vk = parse_hotkey("ctrl+shift+end")
    assert vk != 0
    assert mods != 0


def test_directive_store_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "directive.json"
        store = DirectiveStore(path=path)
        d = parse_directive('{"intent":{"objective":"hold"},"valid_for_plies":2}')
        store.write("q1", d)
        stored = store.read()
        assert stored is not None
        assert stored.question_id == "q1"
        assert stored.to_directive().intent.objective == "hold"


def test_hardcoded_campaign_run_turns():
    driver = HardcodedCampaignDriver()
    result = driver.run_turns(3, require_ok=False)
    assert result["requested"] == 3


def test_battle_driver_mock_console():
    calls: list[str] = []

    def run_console(cmd: str) -> bool:
        calls.append(cmd)
        return True

    with tempfile.TemporaryDirectory() as td:
        pos_dir = Path(td) / "battle"
        pos_dir.mkdir()
        positions_file = pos_dir / "comstar_unit_positions.txt"
        positions_file.write_text(
            "alliance=0 army=0 unit=0 x=10 y=20 strength=100 facing=90\n",
            encoding="utf-8",
        )

        cfg = BattleDriverConfig(
            max_ticks=1,
            tick_seconds=0.0,
            positions_dir=pos_dir,
            prediction_log_path=Path(td) / "pred.jsonl",
        )
        driver = BattleDriver(run_console=run_console, config=cfg)
        result = driver.run()
        assert "toggle_game_update" in calls
        assert result["ticks"] >= 0


@pytest.mark.asyncio
async def test_agent_runtime_no_ao_campaign():
    runtime = AgentRuntime(turns=2)
    result = await runtime.run_campaign(turns=2, use_ao=False)
    assert result["ok"] is True
    assert result["turns"] == 2
    assert result["ao_calls"] == 0
