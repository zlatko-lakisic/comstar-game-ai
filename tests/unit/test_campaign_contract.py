"""Acceptance tests for the campaign director contract rework."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from comstar_game_ai.agent.answer_cache import assert_answer_cache_disabled
from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_accept import accept_campaign_answer
from comstar_game_ai.agent.campaign_contract import (
    commit_until_turn,
    parse_campaign_directive,
)
from comstar_game_ai.agent.campaign_payload import compose_campaign_payload
from comstar_game_ai.agent.campaign_vocab import (
    CAMPAIGN_OBJECTIVES,
    STABLE_DIRECTOR_BACKSTORY,
)
from comstar_game_ai.agent.directive import campaign_directive_schema
from comstar_game_ai.agent.json_safe import assert_json_round_trip
from comstar_game_ai.agent.predictors.log import PredictionLog


def _belief() -> BeliefStore:
    store = BeliefStore()
    store.update(
        Character(
            entity_id="flavius",
            provenance="test",
            confidence=1.0,
            existence=ExistenceStatus.OBSERVED_PRESENT,
            name="Flavius Julius",
            faction="julii",
            x=100.0,
            y=100.0,
            role="general",
        )
    )
    store.update(
        Settlement(
            entity_id="arse",
            provenance="test",
            confidence=1.0,
            existence=ExistenceStatus.OBSERVED_PRESENT,
            region="Arse",
            owner="julii",
            x=100.0,
            y=100.0,
            population=2000,
        )
    )
    store.update(
        Settlement(
            entity_id="segesta",
            provenance="test",
            confidence=1.0,
            existence=ExistenceStatus.OBSERVED_PRESENT,
            region="Segesta",
            owner="rebels",
            x=110.0,
            y=100.0,
            population=800,
        )
    )
    return store


def test_c0_dates_round_trip_through_json():
    payload = {
        "turn_date": dt.date(270, 1, 1),
        "observed_at": dt.datetime(2026, 9, 10, 12, 0, 0),
        "nested": {"d": dt.date(2026, 9, 10)},
    }
    out = assert_json_round_trip(payload)
    assert out["turn_date"] == "0270-01-01" or out["turn_date"].endswith("01-01")
    assert "T" in out["observed_at"]


def test_c0_composed_payload_with_dates_is_json_safe():
    belief = _belief()
    # Stamp a date into attributes — must not reach Reach as a date object.
    for s in belief.get_settlements():
        s.attributes["seen_on"] = dt.date(270, 1, 1)
    payload = compose_campaign_payload(
        belief=belief, question_id="q-1", turn=9, player_faction="julii"
    )
    assert_json_round_trip({"payload": payload.text, "extras": [dt.date.today()]})


def test_vocab_is_exactly_three():
    assert CAMPAIGN_OBJECTIVES == ("hold", "besiege", "reinforce")
    offered = campaign_directive_schema()["properties"]["objective"]["enum"]
    assert offered == list(CAMPAIGN_OBJECTIVES)


def test_stable_backstory_is_verbatim():
    assert "You are the campaign director for the Julii" in STABLE_DIRECTOR_BACKSTORY
    assert "expand" not in STABLE_DIRECTOR_BACKSTORY
    assert "take_settlement" not in STABLE_DIRECTOR_BACKSTORY
    assert "fortify" not in STABLE_DIRECTOR_BACKSTORY
    assert "attack" not in STABLE_DIRECTOR_BACKSTORY.split("OBJECTIVES")[1].split("HOW TO")[0]


def test_unknown_id_is_rejected_to_hold():
    payload = compose_campaign_payload(
        belief=_belief(), question_id="q-1", turn=3, player_faction="julii"
    )
    answer = json.dumps(
        {
            "question_id": "q-1",
            "objective": "besiege",
            "actor": "gen_flavius",
            "target": "set_99",
            "expects": {"turns_to_reach": 2, "garrison_at_arrival": "weaker"},
            "because": "set_99 looks open",
        }
    )
    accepted = accept_campaign_answer(answer, payload=payload, current_turn=3)
    assert accepted.objective == "hold"
    assert "unknown_id" in accepted.because


def test_downgrade_optimistic_garrison(tmp_path: Path):
    belief = _belief()
    for s in belief.get_settlements():
        if "segesta" in (s.entity_id or "").lower():
            s.population = 9000
    payload = compose_campaign_payload(
        belief=belief, question_id="q-2", turn=3, player_faction="julii"
    )
    assert payload.candidates, "need at least one candidate"
    target = payload.candidates[0].settlement_id
    actor = payload.candidates[0].nearest_general_id
    assert payload.candidates[0].garrison == "stronger"

    plog = PredictionLog(tmp_path / "pred.jsonl")
    answer = json.dumps(
        {
            "question_id": "q-2",
            "objective": "besiege",
            "actor": actor,
            "target": target,
            "expects": {"turns_to_reach": 3, "garrison_at_arrival": "weaker"},
            "because": f"{target} is weak",
        }
    )
    accepted = accept_campaign_answer(
        answer, payload=payload, current_turn=3, prediction_log=plog
    )
    assert accepted.objective == "hold"
    assert accepted.downgraded
    assert "weaker" in accepted.downgrade_reason
    assert "stronger" in accepted.downgrade_reason


def test_commit_until_turn_ignored_from_model():
    payload = compose_campaign_payload(
        belief=_belief(), question_id="q-3", turn=5, player_faction="julii"
    )
    target = payload.candidates[0].settlement_id
    actor = payload.candidates[0].nearest_general_id
    pathfinder = payload.candidates[0].turns_to_reach
    answer = json.dumps(
        {
            "question_id": "q-3",
            "objective": "besiege",
            "actor": actor,
            "target": target,
            "commit_until_turn": 99,
            "expects": {
                "turns_to_reach": pathfinder,
                "garrison_at_arrival": payload.candidates[0].garrison,
            },
            "because": f"{target} is next",
        }
    )
    accepted = accept_campaign_answer(answer, payload=payload, current_turn=5)
    assert accepted.commit_until_turn != 99
    assert accepted.commit_until_turn == commit_until_turn(
        current_turn=5, predicted_turns_to_reach=pathfinder
    )


def test_no_proper_nouns_in_payload():
    import re

    payload = compose_campaign_payload(
        belief=_belief(), question_id="q-4", turn=1, player_faction="julii"
    )
    lower = payload.text.lower()
    for name in payload.id_map.proper_nouns():
        assert not re.search(
            rf"(?<![a-z0-9_]){re.escape(name.lower())}(?![a-z0-9_])", lower
        ), name


def test_schema_omits_commit_until_turn():
    props = campaign_directive_schema()["properties"]
    assert "commit_until_turn" not in props
    assert "because" in props
    assert set(campaign_directive_schema()["required"]) == {"objective", "because"}


def test_answer_cache_assert_trips_on_env(monkeypatch):
    monkeypatch.setenv("AGENTIC_ANSWER_CACHE", "1")
    with pytest.raises(RuntimeError, match="AGENTIC_ANSWER_CACHE"):
        assert_answer_cache_disabled({})


def test_parse_ignores_model_commit_field():
    d = parse_campaign_directive(
        json.dumps(
            {
                "objective": "hold",
                "because": "consolidate",
                "commit_until_turn": 50,
            }
        )
    )
    assert d.commit_until_turn is None
    assert d.objective == "hold"
