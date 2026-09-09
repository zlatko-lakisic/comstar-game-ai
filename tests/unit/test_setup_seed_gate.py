"""Seed the opening position when belief is empty — never overwrite what we know.

`descr_strat.txt` describes 270 BC summer. That is exactly right at the opening.
Turn markers must not gate it: autosaves and the message log survive across
campaigns, so a fresh Julii map at 270 BC still shows "Turn 75" from the previous
run. Gating on that number left the director blind on a brand-new campaign.

What we must not do is overwrite entities we already hold — those may include
moves we recorded ourselves. An empty store is always worse than the opening.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver


@pytest.fixture
def seeded(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.start_position.seed_belief_from_setup",
        lambda _belief, player_faction: calls.append(player_faction) or 7,
    )
    return calls


def test_an_empty_belief_is_seeded_even_when_leftover_saves_say_turn_75(monkeypatch, seeded):
    """The failure mode of the previous gate: fresh 270 BC map, stale Turn 75 marker."""
    monkeypatch.setattr(
        "comstar_game_ai.game_io.logs.turn_boundary.newest_turn_start_marker",
        lambda: (75, 1788822272.0),
    )

    HardcodedCampaignDriver()

    assert seeded, "leftover Turn 75 marker left a fresh campaign blind"


def test_a_campaign_with_no_history_is_seeded(monkeypatch, seeded):
    monkeypatch.setattr(
        "comstar_game_ai.game_io.logs.turn_boundary.newest_turn_start_marker",
        lambda: None,
    )

    HardcodedCampaignDriver()

    assert seeded


def test_existing_entities_are_not_overwritten(monkeypatch, seeded):
    """A character we already moved must not be reset to the opening tile."""
    from comstar_game_ai.agent.belief.store import BeliefStore

    store = BeliefStore()
    store.update(
        Character(
            entity_id="flavius_julius",
            provenance="own_order",
            existence=ExistenceStatus.OBSERVED_PRESENT,
            name="Flavius Julius",
            faction="romans_julii",
            x=91.0,
            y=83.0,
            role="leader",
        )
    )

    HardcodedCampaignDriver(belief=store)

    assert not seeded, "overwrote known entities with the 270 BC opening"
    assert store.get_character_entity("flavius_julius").x == 91.0


def test_the_seed_can_still_be_turned_off_outright(monkeypatch, seeded):
    HardcodedCampaignDriver(seed_from_setup=False)

    assert not seeded
