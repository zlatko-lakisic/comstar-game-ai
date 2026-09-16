"""ReachRunError timeout mapping for AO 2.10+."""

from __future__ import annotations

import pytest
from ao_reach.run_status import ReachRunError

from comstar_game_ai.agent.reach.director import call_directive_agent
from comstar_game_ai.agent.reach.session import ReachSession


class _Bridge:
    async def direct_agent(self, **kwargs):
        raise ReachRunError(
            "Ollama /api/chat timed out after 600s",
            code="timeout",
            detail="Ollama /api/chat timed out after 600s (elapsed=601.2)",
            question_id=kwargs.get("question_id"),
        )

    async def cancel(self, question_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_directive_maps_ao_timeout_code(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ready(*_a, **_k):
        return None

    monkeypatch.setattr(
        "comstar_game_ai.agent.reach.director._wait_ready",
        _ready,
    )
    session = ReachSession(bridge=_Bridge(), enable_game_query=False)  # type: ignore[arg-type]
    directive = await call_directive_agent(
        session,
        agent_provider_id="client.campaign_director",
        text="{}",
        question_id="q-timeout",
    )
    assert directive.intent.objective == "hold"
    assert directive.commentary.startswith("timeout:")
