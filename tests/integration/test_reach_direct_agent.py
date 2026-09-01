"""Integration: direct_agent against ada (requires overlay registered)."""

from __future__ import annotations

import pytest

from comstar_game_ai.agent.reach.connection import build_connection_config
from comstar_game_ai.shared.config import load_config

pytestmark = pytest.mark.integration_ada


def test_connection_config_builds():
    cfg = build_connection_config(load_config())
    assert cfg.app_id == "comstar-game-ai"
    assert cfg.dynamic_planning is False
    assert "client.battle_director" in (cfg.allowed_agent_provider_ids or [])
