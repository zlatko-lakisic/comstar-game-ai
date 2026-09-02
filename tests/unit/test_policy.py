import json

from comstar_game_ai.agent.directive import parse_directive
from comstar_game_ai.agent.reactive.policy import ReactivePolicy
from comstar_game_ai.game_io.battle.unit_positions import BattlePositions, UnitPosition


def _positions() -> BattlePositions:
    return BattlePositions(
        units=[
            UnitPosition(0, 0, 0, 0, 0, 0, 20, 40),
            UnitPosition(1, 0, 0, 50, 0, 0, 20, 40),
        ]
    )


def test_hold_objective():
    d = parse_directive(json.dumps({"intent": {"objective": "hold"}}))
    step = ReactivePolicy(player_alliance=0).step(d, _positions())
    assert step.action == "hold"
    assert len(step.orders) == 1
    assert step.orders[0].action == "hold_position"


def test_annihilate_charges_nearest():
    d = parse_directive(json.dumps({"intent": {"objective": "annihilate"}}))
    step = ReactivePolicy(player_alliance=0).step(d, _positions())
    assert step.action == "charge"
    assert step.orders[0].params["target"] == (1, 0, 0)
