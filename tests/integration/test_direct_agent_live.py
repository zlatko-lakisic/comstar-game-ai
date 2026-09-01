"""Integration: live direct_agent call (requires overlay registered on ada)."""

from __future__ import annotations

import pytest

from comstar_game_ai.agent.runtime import run_deliberate_once

pytestmark = pytest.mark.integration_ada


@pytest.mark.asyncio
async def test_deliberate_once_campaign():
    code = await run_deliberate_once(phase="campaign")
    assert code == 0
