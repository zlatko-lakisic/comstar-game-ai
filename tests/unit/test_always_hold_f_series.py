"""Always-hold F-series: hashes, belief advance, hold floor, context budget."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comstar_game_ai.agent.belief.refresh import advance_belief_for_turn
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_accept import accept_campaign_answer
from comstar_game_ai.agent.campaign_ids import CampaignIdMap
from comstar_game_ai.agent.campaign_payload import compose_campaign_payload
from comstar_game_ai.agent.context_budget import (
    assert_num_ctx_sufficient,
    estimate_tokens,
    read_provider_num_ctx,
    read_provider_temperature,
)
from comstar_game_ai.agent.hold_floor import apply_hold_floor, top_reachable_weaker

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaign_runs"
    / "20260909-220705"
)


@pytest.fixture
def fixture_belief_payload():
    belief = BeliefStore.load(FIXTURE / "belief" / "belief_snapshot.json")
    id_map = CampaignIdMap.load(FIXTURE / "runtime" / "campaign_id_map.json")
    payload = compose_campaign_payload(
        belief=belief,
        id_map=id_map,
        turn=2,
        question_id="campaign-2-test",
        player_faction="julii",
    )
    return belief, id_map, payload


def test_f1_fixture_still_surfaces_segesta(fixture_belief_payload):
    """Historical hash 90a0b9f8 was under the age-0 bug; Segesta must still appear."""
    _, _, payload = fixture_belief_payload
    assert any(c.settlement_id == "set_segesta" for c in payload.candidates)
    segesta = next(c for c in payload.candidates if c.settlement_id == "set_segesta")
    assert segesta.turns_to_reach == 1
    assert segesta.garrison == "weaker"
    assert top_reachable_weaker(payload) is not None
    assert top_reachable_weaker(payload).settlement_id == "set_segesta"


def test_f2_both_hashes_move_when_turn_advances(fixture_belief_payload):
    belief, id_map, p2 = fixture_belief_payload
    # Stamp last_seen so ages are turn-relative (post-F3 contract).
    for entity in [
        *belief.get_settlements(),
        *belief.get_characters(),
        *belief.get_armies(),
    ]:
        attrs = dict(entity.attributes or {})
        attrs["last_seen_turn"] = 1
        entity.attributes = attrs
    p2 = compose_campaign_payload(
        belief=belief,
        id_map=id_map,
        turn=2,
        question_id="campaign-2-test",
        player_faction="julii",
    )
    p3 = compose_campaign_payload(
        belief=belief,
        id_map=id_map,
        turn=3,
        question_id="campaign-3-test",
        player_faction="julii",
    )
    assert p2.belief_hash != p3.belief_hash
    assert p2.payload_hash != p3.payload_hash
    assert p2.belief_hash == p2.state_hash


def test_f3_belief_hash_changes_across_forced_hold_turns(tmp_path, fixture_belief_payload):
    belief, id_map, _ = fixture_belief_payload
    hashes = []
    ages = []
    for turn in range(2, 7):
        advance_belief_for_turn(
            belief,
            current_turn=turn,
            player_faction="julii",
            observation={"treasury": 5000 + turn, "income": 400},
        )
        payload = compose_campaign_payload(
            belief=belief,
            id_map=id_map,
            turn=turn,
            question_id=f"q-{turn}",
            player_faction="julii",
            treasury=5000 + turn,
            income=400,
        )
        hashes.append(payload.belief_hash)
        # YOU HOLD lines carry age
        hold_line = next(line for line in payload.you_hold if line.startswith("set_"))
        ages.append(int(hold_line.rsplit("age", 1)[1].strip()))
    assert len(set(hashes)) == len(hashes), hashes
    assert ages == sorted(ages)
    assert ages[-1] > ages[0]


def test_f4_provider_pins_and_budget_assert():
    assert read_provider_temperature() == 0.0
    assert read_provider_num_ctx() >= 4096
    assert_num_ctx_sufficient(composed_prompt="hello world", num_ctx=8192)
    with pytest.raises(RuntimeError, match="num_ctx"):
        assert_num_ctx_sufficient(
            composed_prompt="x" * 50_000, num_ctx=100, margin_tokens=10
        )
    assert estimate_tokens("abcd" * 100) == 100


def test_f7_hold_floor_upgrades_fixture_hold(fixture_belief_payload):
    _, _, payload = fixture_belief_payload
    hold = json.dumps(
        {
            "question_id": payload.question_id,
            "objective": "hold",
            "because": "no candidates",
        }
    )
    accepted = accept_campaign_answer(
        hold, payload=payload, current_turn=2, hold_floor="upgrade"
    )
    assert accepted.objective == "besiege"
    assert accepted.target == "set_segesta"
    assert accepted.actor
    assert "hold_floor" in (accepted.raw or {})
    assert accepted.raw["hold_floor"]["predictor"]["settlement_id"] == "set_segesta"


def test_f7_log_mode_keeps_hold_but_records(fixture_belief_payload):
    _, _, payload = fixture_belief_payload
    hold = json.dumps(
        {
            "question_id": payload.question_id,
            "objective": "hold",
            "because": "no candidates",
        }
    )
    accepted = accept_campaign_answer(
        hold, payload=payload, current_turn=2, hold_floor="log"
    )
    assert accepted.objective == "hold"
    assert accepted.raw.get("hold_floor", {}).get("action") == "log"


def test_f7_reask_tags_for_second_call(fixture_belief_payload):
    _, _, payload = fixture_belief_payload
    hold = json.dumps(
        {
            "question_id": payload.question_id,
            "objective": "hold",
            "because": "no candidates",
        }
    )
    accepted = accept_campaign_answer(
        hold, payload=payload, current_turn=2, hold_floor="reask"
    )
    assert accepted.objective == "hold"
    assert accepted.raw.get("hold_floor_reask") is True
    assert "set_segesta" in accepted.because
