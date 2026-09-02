"""Reach connection config builder."""

from __future__ import annotations

from typing import Any

from ao_reach.connection_config import ReachConnectionConfig

from comstar_game_ai.agent.reach.client import reach_mtls_config
from comstar_game_ai.shared.config import load_config

CLIENT_AGENT_IDS = (
    "client.battle_director",
    "client.campaign_director",
    "client.opponent_modeler",
    "client.narrator",
    "client.consolidator",
    "client.doctrine_ingestor",
    "client.post_mortem",
)


def build_connection_config(config: dict[str, Any] | None = None) -> ReachConnectionConfig:
    """Build ReachConnectionConfig from comstar YAML config."""
    cfg = config or load_config()
    ao = cfg["ao"]
    return ReachConnectionConfig(
        base_url=str(ao["base_url"]),
        app_id=str(ao["app_id"]),
        mtls=reach_mtls_config(cfg),
        ttl_seconds=3600,
        question_id_prefix="cga",
        dynamic_planning=False,
        default_run_mode="dynamic",
        allowed_agent_provider_ids=list(CLIENT_AGENT_IDS),
        allowed_mcp_provider_ids=[],
        allowed_skill_ids=[],
        deploy_to_ao_sandbox=False,
    )
