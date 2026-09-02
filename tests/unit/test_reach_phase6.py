"""Unit tests for Phase 6 Reach wiring."""

from ao_reach.overlay_packer import OverlayPacker

from comstar_game_ai.agent.reach.connection import CLIENT_AGENT_IDS, build_connection_config
from comstar_game_ai.agent.reach.context_builder import ObservableContext, build_observable_brief
from comstar_game_ai.shared.config import load_config, repo_root


def test_build_connection_config():
    cfg = build_connection_config(load_config())
    assert cfg.app_id == "comstar-game-ai"
    assert cfg.dynamic_planning is False
    assert cfg.question_id_prefix == "cga"
    assert cfg.allowed_agent_provider_ids == list(CLIENT_AGENT_IDS)
    assert cfg.deploy_to_ao_sandbox is False


def test_overlay_packs_seven_agents():
    root = repo_root() / "overlay"
    pack = OverlayPacker().pack(root)
    assert len(pack.agents) == 7
    assert all(a["model"] == "llama3.1:8b" for a in pack.agents)
    battle = next(a for a in pack.agents if a["id"] == "client.battle_director")
    assert battle.get("skills") == ["client.battle_doctrine"]
    assert "Battle doctrine" in str(battle.get("backstory") or "")


def test_observable_brief_json():
    brief = build_observable_brief(
        ObservableContext(phase="battle", battle_id="b1", summary="contact"),
    )
    assert "battle" in brief
    assert "contact" in brief
