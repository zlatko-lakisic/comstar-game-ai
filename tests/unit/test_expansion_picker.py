"""Expansion ranking, standing seed, preferred payload, and hold floor."""

from __future__ import annotations

from comstar_game_ai.agent.belief.diplomacy import (
    attack_tier,
    get_standing,
    mark_at_war,
    seed_standings_from_allies,
)
from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_accept import accept_campaign_answer
from comstar_game_ai.agent.campaign_contract import CampaignDirective
from comstar_game_ai.agent.campaign_ids import CampaignIdMap
from comstar_game_ai.agent.campaign_payload import (
    StandingDirectiveView,
    compose_campaign_payload,
)
from comstar_game_ai.agent.campaign_vocab import STABLE_DIRECTOR_BACKSTORY
from comstar_game_ai.agent.hold_floor import apply_hold_floor, expansion_floor_candidate
from comstar_game_ai.agent.predictors.campaign_board import (
    Candidate,
    build_candidates,
    preferred_expansion_target,
    rank_expansion_targets,
)
from comstar_game_ai.game_io.campaign.start_position import (
    parse_start_position,
    seed_belief,
)

from tests.unit.test_start_position import STRAT_TEXT, located_regions


def _settlement(
    sid: str,
    *,
    owner: str,
    x: float,
    y: float,
    pop: int = 900,
) -> Settlement:
    return Settlement(
        entity_id=sid,
        provenance="test",
        confidence=1.0,
        existence=ExistenceStatus.BELIEVED_PRESENT,
        region=sid,
        owner=owner,
        x=x,
        y=y,
        population=pop,
        attributes={"last_seen_turn": 1},
    )


def _general(gid: str, *, x: float, y: float, faction: str = "romans_julii") -> Character:
    return Character(
        entity_id=gid,
        provenance="test",
        confidence=1.0,
        existence=ExistenceStatus.BELIEVED_PRESENT,
        name=gid.replace("_", " ").title(),
        faction=faction,
        x=x,
        y=y,
        role="leader",
        attributes={"last_seen_turn": 1},
    )


def test_seed_parses_ally_pairs_and_standings():
    store = BeliefStore()
    start = parse_start_position(STRAT_TEXT, located_regions())
    assert ("romans_julii", "romans_brutii") in start.ally_pairs
    seed_belief(store, start, player_faction="julii")
    assert get_standing(store, "romans_brutii") == "ally"
    assert get_standing(store, "slave") == "neutral"


def test_seed_standings_work_for_non_julii_player():
    store = BeliefStore()
    store.update(_settlement("town_a", owner="gaul", x=10, y=10))
    store.update(_settlement("town_b", owner="romans_julii", x=12, y=12))
    seed_standings_from_allies(
        store,
        player_faction="gaul",
        ally_pairs=[("gaul", "spain")],
        known_factions={"gaul", "spain", "romans_julii", "slave"},
    )
    assert get_standing(store, "spain") == "ally"
    assert get_standing(store, "romans_julii") == "neutral"
    assert get_standing(store, "slave") == "neutral"


def test_rank_prefers_rebel_over_nearer_enemy():
    candidates = [
        Candidate(
            settlement_id="set_near_war",
            owner_id="fac_gaul",
            turns_to_reach=1,
            nearest_general_id="gen_a",
            garrison="weaker",
            confidence=0.6,
            age_turns=0,
            standing="at_war",
            map_x=90.0,
            map_y=80.0,
            owner_raw="gaul",
        ),
        Candidate(
            settlement_id="set_far_rebel",
            owner_id="fac_slave",
            turns_to_reach=3,
            nearest_general_id="gen_a",
            garrison="weaker",
            confidence=0.6,
            age_turns=0,
            standing="neutral",
            map_x=91.0,
            map_y=95.0,
            owner_raw="slave",
        ),
    ]
    ranked = rank_expansion_targets(candidates, centroid=(90.0, 80.0))
    assert ranked[0].settlement_id == "set_far_rebel"


def test_rank_prefers_enemy_over_nearer_neutral():
    candidates = [
        Candidate(
            settlement_id="set_near_neutral",
            owner_id="fac_a",
            turns_to_reach=1,
            nearest_general_id="gen_a",
            garrison="weaker",
            confidence=0.6,
            age_turns=0,
            standing="neutral",
            map_x=90.0,
            map_y=80.0,
        ),
        Candidate(
            settlement_id="set_far_war",
            owner_id="fac_b",
            turns_to_reach=3,
            nearest_general_id="gen_a",
            garrison="weaker",
            confidence=0.6,
            age_turns=0,
            standing="at_war",
            map_x=91.0,
            map_y=95.0,
        ),
    ]
    ranked = rank_expansion_targets(candidates, centroid=(90.0, 80.0))
    assert ranked[0].settlement_id == "set_far_war"


def test_rank_among_equal_standing_prefers_weaker_then_nearer():
    candidates = [
        Candidate(
            "set_capua",
            "fac_a",
            2,
            "gen_a",
            "stronger",
            0.6,
            0,
            standing="neutral",
            map_x=95.0,
            map_y=60.0,
        ),
        Candidate(
            "set_segesta",
            "fac_b",
            1,
            "gen_a",
            "weaker",
            0.6,
            0,
            standing="neutral",
            map_x=83.0,
            map_y=84.0,
        ),
    ]
    preferred = preferred_expansion_target(candidates, centroid=(90.0, 80.0))
    assert preferred is not None
    assert preferred.settlement_id == "set_segesta"


def test_rank_among_equal_standing_and_garrison_prefers_frontier():
    candidates = [
        Candidate(
            "set_interior",
            "fac_a",
            1,
            "gen_a",
            "weaker",
            0.6,
            0,
            standing="at_war",
            map_x=91.0,
            map_y=81.0,
        ),
        Candidate(
            "set_frontier",
            "fac_b",
            1,
            "gen_a",
            "weaker",
            0.6,
            0,
            standing="at_war",
            map_x=91.0,
            map_y=100.0,
        ),
    ]
    preferred = preferred_expansion_target(candidates, centroid=(90.0, 80.0))
    assert preferred is not None
    assert preferred.settlement_id == "set_frontier"


def test_roman_houses_count_as_allies():
    store = BeliefStore()
    seed_standings_from_allies(
        store,
        player_faction="romans_julii",
        ally_pairs=[],
        known_factions={"romans_julii", "romans_scipii", "slave"},
    )
    assert get_standing(store, "romans_scipii") == "ally"
    assert get_standing(store, "slave") == "neutral"


def test_hold_floor_upgrades_missing_actor_or_target():
    store = BeliefStore()
    store.update(_settlement("arretium", owner="romans_julii", x=91, y=80, pop=4000))
    store.update(_settlement("segesta", owner="slave", x=83, y=84, pop=900))
    store.update(_general("flavius_julius", x=89, y=82))
    seed_standings_from_allies(
        store, player_faction="romans_julii", ally_pairs=[], known_factions={"slave"}
    )
    payload = compose_campaign_payload(
        belief=store, question_id="q-miss", turn=2, player_faction="julii"
    )
    hold = CampaignDirective(
        question_id="q-miss",
        objective="hold",
        because="missing_actor_or_target",
    )
    upgraded = apply_hold_floor(
        hold, payload=payload, current_turn=2, action="upgrade"
    )
    assert upgraded.objective == "besiege"
    assert upgraded.target == payload.preferred.settlement_id


def test_ally_only_when_no_enemy_or_neutral():
    candidates = [
        Candidate(
            "set_ally",
            "fac_a",
            1,
            "gen_a",
            "weaker",
            0.6,
            0,
            standing="ally",
            map_x=95.0,
            map_y=90.0,
        ),
    ]
    preferred = preferred_expansion_target(candidates, centroid=(90.0, 80.0))
    assert preferred is not None
    assert preferred.standing == "ally"


def test_build_candidates_include_standing_and_payload_preferred():
    store = BeliefStore()
    store.update(_settlement("arretium", owner="romans_julii", x=91, y=80, pop=4000))
    store.update(_settlement("segesta", owner="slave", x=83, y=84, pop=900))
    store.update(_settlement("patavium", owner="gaul", x=88, y=95, pop=1200))
    store.update(_general("flavius_julius", x=89, y=82))
    seed_standings_from_allies(
        store,
        player_faction="romans_julii",
        ally_pairs=[],
        known_factions={"slave", "gaul"},
    )
    mark_at_war(store, "gaul")
    id_map = CampaignIdMap()
    candidates = build_candidates(store, id_map, player_faction="julii", current_turn=2)
    assert candidates
    # Rebels outrank at_war enemies (attack tier order).
    assert candidates[0].owner_raw == "slave"
    assert attack_tier(faction=candidates[0].owner_raw, standing=candidates[0].standing) == "rebel"
    payload = compose_campaign_payload(
        belief=store, question_id="q1", turn=2, player_faction="julii"
    )
    assert payload.preferred is not None
    assert "EXPANSION preferred" in payload.text
    assert payload.preferred.settlement_id == candidates[0].settlement_id


def test_hold_floor_upgrades_to_preferred():
    store = BeliefStore()
    store.update(_settlement("arretium", owner="romans_julii", x=91, y=80, pop=4000))
    store.update(_settlement("segesta", owner="slave", x=83, y=84, pop=900))
    store.update(_general("flavius_julius", x=89, y=82))
    seed_standings_from_allies(
        store, player_faction="romans_julii", ally_pairs=[], known_factions={"slave"}
    )
    payload = compose_campaign_payload(
        belief=store, question_id="q-hold", turn=2, player_faction="julii"
    )
    hold = CampaignDirective(
        question_id="q-hold",
        objective="hold",
        because="waiting",
    )
    upgraded = apply_hold_floor(
        hold, payload=payload, current_turn=2, action="upgrade"
    )
    assert upgraded.objective == "besiege"
    assert upgraded.target == payload.preferred.settlement_id


def test_hold_floor_respects_standing_besiege_stickiness():
    store = BeliefStore()
    store.update(_settlement("arretium", owner="romans_julii", x=91, y=80, pop=4000))
    store.update(_settlement("segesta", owner="slave", x=83, y=84, pop=900))
    store.update(_general("flavius_julius", x=89, y=82))
    seed_standings_from_allies(
        store, player_faction="romans_julii", ally_pairs=[], known_factions={"slave"}
    )
    payload = compose_campaign_payload(
        belief=store,
        question_id="q-stick",
        turn=3,
        player_faction="julii",
        standing=StandingDirectiveView(
            objective="besiege",
            actor="gen_flavius_julius",
            target="set_segesta",
            issued_turn=2,
            commit_until_turn=6,
            status="in progress",
        ),
    )
    assert expansion_floor_candidate(payload) is None
    hold = CampaignDirective(question_id="q-stick", objective="hold", because="pause")
    out = apply_hold_floor(hold, payload=payload, current_turn=3, action="upgrade")
    assert out.objective == "hold"


def test_accept_path_still_upgrades_hold_with_preferred():
    store = BeliefStore()
    store.update(_settlement("arretium", owner="romans_julii", x=91, y=80, pop=4000))
    store.update(_settlement("segesta", owner="slave", x=83, y=84, pop=900))
    store.update(_general("flavius_julius", x=89, y=82))
    seed_standings_from_allies(
        store, player_faction="romans_julii", ally_pairs=[], known_factions={"slave"}
    )
    payload = compose_campaign_payload(
        belief=store, question_id="q-acc", turn=2, player_faction="julii"
    )
    accepted = accept_campaign_answer(
        '{"objective":"hold","because":"nothing"}',
        payload=payload,
        current_turn=2,
        hold_floor="upgrade",
    )
    assert accepted.objective == "besiege"
    assert accepted.target == payload.preferred.settlement_id


def test_director_backstory_is_faction_agnostic():
    assert "player's faction" in STABLE_DIRECTOR_BACKSTORY
    assert "EXPANSION preferred" in STABLE_DIRECTOR_BACKSTORY
    assert "Julii" not in STABLE_DIRECTOR_BACKSTORY
