import json

import pytest

from comstar_game_ai.agent.directive import (
    NEUTRAL_OBJECTIVE,
    downgrade_infeasible,
    neutral_directive,
    parse_directive,
)


def test_neutral_directive_default():
    d = neutral_directive("timeout")
    assert d.intent.objective == NEUTRAL_OBJECTIVE
    assert "timeout" in d.commentary


def test_parse_valid_directive():
    payload = {
        "intent": {
            "objective": "annihilate",
            "acceptable_own_losses": 0.35,
            "required_enemy_losses": 0.90,
        },
        "horizon": "short",
        "risk_posture": -0.5,
        "valid_for_plies": 4,
        "play_id": "hammer_anvil",
        "play_params": {"flank": "left"},
    }
    d = parse_directive(json.dumps(payload))
    assert d.intent.objective == "annihilate"
    assert d.play_id == "hammer_anvil"
    assert d.play_params["flank"] == "left"


def test_malformed_returns_neutral():
    d = parse_directive("not json at all")
    assert d.intent.objective == NEUTRAL_OBJECTIVE


def test_downgrade_annihilation():
    payload = {"intent": {"objective": "annihilate"}}
    d = parse_directive(json.dumps(payload))
    d2 = downgrade_infeasible(d, own_strength=100, enemy_strength=200)
    assert d2.intent.objective == "win_cheaply"
