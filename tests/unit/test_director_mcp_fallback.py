"""Asking AO for an unregistered MCP provider is a rejection, not a degraded call.

The 261 BC run proved the cost: game_query's stdio server never started, so every
campaign_director call was refused by the engine with `unknown catalog id
'client.game_query'` and turned into a neutral directive. Twenty-one of them.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from comstar_game_ai.agent.reach.director import GAME_QUERY_MCP, call_directive_agent


class FakeBridge:
    def __init__(self, registered: list[str]):
        self.registered_mcp_ids = registered
        self.calls: list[dict[str, Any]] = []

    async def direct_agent(self, **kwargs) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"text": '{"objective": "besiege", "because": "set_14 is open", "actor": "gen_01", "target": "set_14"}'}

    async def cancel(self, question_id: str) -> None:  # pragma: no cover - unused here
        return None


class FakeSession:
    def __init__(self, registered: list[str]):
        self.bridge = FakeBridge(registered)

    @property
    def available_mcp_ids(self) -> tuple[str, ...]:
        return tuple(self.bridge.registered_mcp_ids)


def _call(session, **kwargs):
    return asyncio.run(
        call_directive_agent(
            session,
            agent_provider_id="client.campaign_director",
            text="turn 4",
            question_id="campaign-4-abc",
            **kwargs,
        )
    )


def test_a_registered_provider_is_requested():
    session = FakeSession([GAME_QUERY_MCP])

    directive = _call(session)

    assert session.bridge.calls[0]["mcp_provider_ids"] == [GAME_QUERY_MCP]
    assert directive.intent.objective == "besiege"


def test_an_unregistered_provider_is_not_requested():
    """The model still answers; it just answers without belief tools."""
    session = FakeSession([])

    directive = _call(session)

    assert session.bridge.calls[0]["mcp_provider_ids"] == []
    assert directive.intent.objective == "besiege"


def test_an_explicit_list_still_wins():
    session = FakeSession([GAME_QUERY_MCP])

    _call(session, mcp_provider_ids=[])

    assert session.bridge.calls[0]["mcp_provider_ids"] == []


def test_the_skip_is_logged_so_a_silent_downgrade_is_visible(caplog):
    session = FakeSession([])

    with caplog.at_level("WARNING"):
        _call(session)

    assert GAME_QUERY_MCP in caplog.text


@pytest.mark.parametrize("registered", [[], [GAME_QUERY_MCP]])
def test_the_call_is_never_refused_locally(registered):
    """Whatever the tool state, a directive comes back — never an exception."""
    assert _call(FakeSession(registered)) is not None
