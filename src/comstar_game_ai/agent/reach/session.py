"""Reach session overlay registration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ao_reach.mcp_bootstrap import SessionMcpBootstrap
from ao_reach.session_bridge import SessionBridge

from comstar_game_ai.agent.reach.connection import build_connection_config
from comstar_game_ai.agent.reach.mcp_game_query import GameQueryMcpBootstrap
from comstar_game_ai.shared.config import repo_root

_LOGGER = logging.getLogger(__name__)


def overlay_root() -> Path:
    return repo_root() / "overlay"


class ReachSession:
    """Process B Reach session: overlay register and bridge lifecycle."""

    def __init__(self, *, bridge: SessionBridge | None = None) -> None:
        self.bridge = bridge or SessionBridge()
        self._mcp_bootstrap: SessionMcpBootstrap = GameQueryMcpBootstrap()

    @property
    def is_active(self) -> bool:
        return self.bridge.is_active

    async def start(self, config: dict[str, Any] | None = None) -> None:
        reach_cfg = build_connection_config(config)
        await self.bridge.start(
            config=reach_cfg,
            overlay_root=str(overlay_root()),
            mcp_bootstrap=self._mcp_bootstrap,
        )
        _LOGGER.info(
            "Reach session active: agents=%s mcps=%s",
            self.bridge.registered_agent_ids,
            self.bridge.registered_mcp_ids,
        )

    async def refresh_overlay(self) -> None:
        await self.bridge.refresh_overlay()

    async def stop(self, *, clear_remote: bool = True) -> None:
        await self.bridge.stop(clear_remote=clear_remote)
