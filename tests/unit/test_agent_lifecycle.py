"""Unit tests for AO agent_state helpers."""

from __future__ import annotations

from ao_reach.agent_state import AgentLifecycleState, AgentStateUpdate

from comstar_game_ai.agent.reach.agent_lifecycle import (
    agent_state_payload,
    format_agent_state,
    read_agent_status,
    write_agent_status,
)


def test_format_agent_state_includes_pull_progress() -> None:
    update = AgentStateUpdate(
        agent_provider_id="client.campaign_director",
        state=AgentLifecycleState.PULLING,
        model="qwen3.5:9b",
        progress=0.42,
        detail="pulling weights",
    )
    line = format_agent_state(update)
    assert "campaign_director" in line
    assert "pulling" in line
    assert "qwen3.5:9b" in line
    assert "42%" in line


def test_agent_state_payload_overlay_fields() -> None:
    update = AgentStateUpdate(
        agent_provider_id="client.map_target_vision",
        state=AgentLifecycleState.READY,
        model="llava:7b",
    )
    payload = agent_state_payload(update)
    assert payload["agent"] == "client.map_target_vision"
    assert payload["state"] == "ready"
    assert payload["phase"] == "ready"
    assert "map_target_vision" in payload["summary"]


def test_write_read_agent_status_roundtrip(tmp_path) -> None:
    path = tmp_path / "ao_agent_status.json"
    update = AgentStateUpdate(
        agent_provider_id="client.campaign_director",
        state=AgentLifecycleState.BUSY,
        question_id="campaign-4-abc",
    )
    write_agent_status(update, path=path)
    data = read_agent_status(path=path)
    assert data is not None
    assert data["state"] == "busy"
    assert data["question_id"] == "campaign-4-abc"
    assert "ts" in data
