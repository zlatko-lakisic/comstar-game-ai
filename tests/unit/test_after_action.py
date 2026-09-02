import json

from comstar_game_ai.agent.records.after_action import AfterActionRecord, build_after_action


def test_after_action_observable_privileged_split():
    record = build_after_action(
        battle_id="btl-1",
        intent_objective="win_cheaply",
        predicted={"outcome": "win", "own_losses": 0.15},
        observed={"outcome": "win", "own_losses": 0.30},
        privileged_truth={"enemy_ai_plan": "hold_center"},
    )
    assert isinstance(record, AfterActionRecord)
    assert record.observable["outcome"] == "win"
    assert record.privileged["enemy_ai_plan"] == "hold_center"
    assert "privileged" not in json.loads(record.to_json())["observable"]


def test_surprise_higher_on_wrong_outcome():
    record = build_after_action(
        battle_id="btl-2",
        intent_objective="annihilate",
        predicted={"outcome": "win", "own_losses": 0.1},
        observed={"outcome": "loss", "own_losses": 0.6},
    )
    assert record.surprise == 1.0
    assert not record.intent_achieved
