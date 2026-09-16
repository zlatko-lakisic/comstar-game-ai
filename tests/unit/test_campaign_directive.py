"""AO's directive reaching the campaign turn — and failing closed when it does not.

The contract worth protecting is the one that keeps a bad model cheap: a directive
decides whether the turn advances, never what gets typed at the console, and
anything stale, missing or malformed reads as "hold".
"""

from __future__ import annotations

import time

from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.directive import Directive, DirectiveIntent, neutral_directive
from comstar_game_ai.game_io.campaign.orders import CampaignPlanner
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.intent_record import IntentRecordWriter
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore


def _belief_with_a_reachable_target() -> BeliefStore:
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
            entity_id="segesta",
            provenance="test",
            confidence=1.0,
            existence=ExistenceStatus.OBSERVED_PRESENT,
            region="Segesta",
            owner="rebels",
            x=110.0,
            y=100.0,
        )
    )
    return store


def _directive(objective: str, **kwargs) -> Directive:
    return Directive(intent=DirectiveIntent(objective=objective), **kwargs)


def _moves(orders):
    return [o for o in orders if o.kind in {"move_character", "march"}]


# --- planner ---------------------------------------------------------------


def test_no_directive_leaves_the_hardcoded_policy_alone():
    """The 20-turn baseline must not change just because the feature exists."""
    orders = CampaignPlanner().plan(_belief_with_a_reachable_target())
    assert len(_moves(orders)) == 1


def test_hold_keeps_the_army_where_it_is():
    orders = CampaignPlanner().plan(_belief_with_a_reachable_target(), neutral_directive("ao down"))
    assert _moves(orders) == []


def test_an_advancing_objective_moves():
    from comstar_game_ai.agent.campaign_ids import CampaignIdMap, sync_id_map_from_belief

    belief = _belief_with_a_reachable_target()
    id_map = sync_id_map_from_belief(belief)
    actor = id_map.general_id(belief.get_characters()[0])
    target = id_map.settlement_id(belief.get_settlements()[0])
    directive = _directive(
        "besiege",
        play_params={"actor": actor, "target": target},
    )
    orders = CampaignPlanner(id_map=id_map).plan(belief, directive)
    assert len(_moves(orders)) == 1
    move = _moves(orders)[0]
    assert move.kind == "march"
    assert move.from_xy == (100.0, 100.0)
    assert move.to_xy == (110.0, 100.0)
    assert "Flavius" in move.character_name


def test_an_invented_objective_reads_as_hold():
    """A model that makes up a verb should not be able to move an army by accident."""
    orders = CampaignPlanner().plan(_belief_with_a_reachable_target(), _directive("sack_everything"))
    assert _moves(orders) == []


def test_avoid_actions_outranks_the_objective():
    directive = _directive(
        "besiege",
        avoid_actions=["move_character"],
        play_params={"actor": "gen_x", "target": "set_y"},
    )
    orders = CampaignPlanner().plan(_belief_with_a_reachable_target(), directive)
    assert _moves(orders) == []


def test_focus_actions_can_only_ask_for_known_reads():
    directive = _directive("hold", focus_actions=["list_units", "add_money", "capture_settlement"])
    commands = [o.command for o in CampaignPlanner().plan(BeliefStore(), directive)]

    assert "list_units" in commands
    assert "add_money" not in commands
    assert "capture_settlement" not in commands


def test_a_focus_action_is_never_ordered_twice():
    directive = _directive("hold", focus_actions=["list_characters"])
    commands = [o.command for o in CampaignPlanner().plan(BeliefStore(), directive)]
    assert commands.count("list_characters") == 1


# --- driver freshness ------------------------------------------------------


def _driver(tmp_path, **kwargs) -> HardcodedCampaignDriver:
    driver = HardcodedCampaignDriver(
        use_vision=False,
        directive_store=DirectiveStore(tmp_path / "directive.json"),
        **kwargs,
    )
    driver.state.state = GameState.CAMPAIGN_MAP
    return driver


def test_without_a_store_the_driver_asks_ao_for_nothing():
    assert HardcodedCampaignDriver(use_vision=False).current_directive() is None


def test_a_missing_file_is_hold_not_a_free_hand(tmp_path):
    directive = _driver(tmp_path).current_directive()
    assert directive is not None
    assert directive.intent.objective == "hold"


def test_a_fresh_directive_is_adopted(tmp_path):
    driver = _driver(tmp_path)
    driver.directive_store.write("campaign-4-abc", _directive("besiege"))

    directive = driver.current_directive()

    assert directive.intent.objective == "besiege"
    assert driver.last_directive == "besiege"


def test_a_directive_from_an_earlier_session_is_ignored(tmp_path):
    driver = _driver(tmp_path, directive_max_age_s=60)
    driver.directive_store.write("campaign-4-abc", _directive("besiege"))
    stale = driver.directive_store.read()
    payload = driver.directive_store.path.read_text(encoding="utf-8")
    driver.directive_store.path.write_text(
        payload.replace(str(stale.ts), str(time.time() - 3600)), encoding="utf-8"
    )

    assert driver.current_directive().intent.objective == "hold"


def test_a_directive_expires_after_its_own_ply_budget(tmp_path, monkeypatch):
    """valid_for_plies is the model's own claim about how long it should apply."""
    driver = _driver(tmp_path)
    turn = {"value": 10}
    monkeypatch.setattr(driver, "_known_game_turn", lambda: turn["value"])
    driver.directive_store.write("campaign-10-abc", _directive("besiege", valid_for_plies=2))

    assert driver.current_directive().intent.objective == "besiege"
    turn["value"] = 11
    assert driver.current_directive().intent.objective == "besiege"
    turn["value"] = 12
    assert driver.current_directive().intent.objective == "hold"


def test_a_new_directive_resets_the_ply_budget(tmp_path, monkeypatch):
    driver = _driver(tmp_path)
    turn = {"value": 10}
    monkeypatch.setattr(driver, "_known_game_turn", lambda: turn["value"])
    driver.directive_store.write("campaign-10-abc", _directive("besiege", valid_for_plies=1))
    driver.current_directive()

    turn["value"] = 11
    assert driver.current_directive().intent.objective == "hold"

    driver.directive_store.write("campaign-11-def", _directive("reinforce", valid_for_plies=1))
    assert driver.current_directive().intent.objective == "reinforce"


def test_a_corrupt_directive_file_is_hold(tmp_path):
    driver = _driver(tmp_path)
    driver.directive_store.path.parent.mkdir(parents=True, exist_ok=True)
    driver.directive_store.path.write_text("{not json", encoding="utf-8")

    assert driver.current_directive().intent.objective == "hold"


def test_the_turn_records_which_directive_drove_it(tmp_path):
    driver = _driver(tmp_path)
    driver.intent_writer = IntentRecordWriter(tmp_path / "intents.jsonl")
    driver.directive_store.write("campaign-4-abc", _directive("besiege"))

    driver.run_turn_stub(wait_for_next_turn=False)

    record = driver.intent_writer.path.read_text(encoding="utf-8")
    assert "campaign-4-abc" in record
    assert "besiege" in record
