"""Older ao_reach SessionBridge rejects response_format / json_schema."""

from __future__ import annotations

import asyncio
from typing import Any

from comstar_game_ai.agent.reach import director as agent_director
from comstar_game_ai.agent.reach.director import call_directive_agent


class StrictBridge:
    """Mirrors installed ao_reach: fixed kwargs, no response_format."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def direct_agent(
        self,
        *,
        agent_provider_id: str,
        text: str,
        context: str = "",
        question_id: str | None = None,
        priority: str | int | None = None,
        mcp_provider_ids: list[str] | None = None,
        images: list[dict[str, Any]] | None = None,
        on_status: Any = None,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "agent_provider_id": agent_provider_id,
                "text": text,
                "context": context,
                "question_id": question_id,
                "priority": priority,
                "mcp_provider_ids": mcp_provider_ids,
                "images": images,
                "timeout": timeout,
            }
        )
        return {
            "text": '{"objective":"besiege","because":"Segesta is open","actor":"gen_flavius_julius","target":"set_segesta"}'
        }

    async def cancel(self, question_id: str) -> None:
        return None


class StrictSession:
    def __init__(self) -> None:
        self.bridge = StrictBridge()

    @property
    def available_mcp_ids(self) -> tuple[str, ...]:
        return ()


def test_directive_call_survives_bridge_without_response_format(caplog):
    agent_director._logged_direct_agent_strip.clear()
    session = StrictSession()

    directive = asyncio.run(
        call_directive_agent(
            session,
            agent_provider_id="client.campaign_director",
            text="turn 4",
            question_id="campaign-4-fix",
            response_format={"type": "json_object"},
            json_schema={"type": "object"},
        )
    )

    assert directive.intent.objective == "besiege"
    assert len(session.bridge.calls) == 1
    assert "response_format" not in session.bridge.calls[0]
    assert "json_schema" not in session.bridge.calls[0]
    assert "does not accept" in caplog.text
