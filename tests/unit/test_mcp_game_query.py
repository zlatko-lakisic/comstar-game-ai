"""Unit tests for mcp_game_query tool dispatch."""

import json

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.reach import mcp_game_query as gq


def test_game_query_tools_dispatch(tmp_path, monkeypatch):
    snap = tmp_path / "belief.json"
    store = BeliefStore(
        armies={"a1": {"strength": 100}},
        faction_beliefs={"julii": {"attitude": "neutral"}},
        history=[{"event": "turn_start"}],
        unit_types={"principes": {"role": "infantry"}},
    )
    store.save(snap)
    monkeypatch.setattr(gq, "belief_snapshot_path", lambda: snap)

    army = gq._dispatch_tool("get_army", {"army_id": "a1"})
    assert "100" in army["content"][0]["text"]
    hist = gq._dispatch_tool("get_history", {"n": 1})
    assert "turn_start" in hist["content"][0]["text"]
    unit = gq._dispatch_tool("explain_unit", {"unit_type": "principes"})
    assert "infantry" in unit["content"][0]["text"]
    assert gq.GAME_QUERY_CLIENT_ID == "client.game_query"
