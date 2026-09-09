"""Own orders are facts the campaign KB must record.

The director reads BeliefStore as text and never sees a screenshot. When Process
A successfully issues `move_character Name x,y`, the character is at (x, y) —
that is as certain as anything in the store. Leaving the position at its seeded
opening value is how a brief goes stale the first turn a general walks.
"""

from __future__ import annotations

from comstar_game_ai.agent.belief.entities import (
    Army,
    Character,
    ExistenceStatus,
)
from comstar_game_ai.agent.belief.orders import (
    OWN_ORDER_PROVENANCE,
    parse_move_character,
    record_own_move,
)
from comstar_game_ai.agent.belief.store import BeliefStore


def _store_with_flavius() -> BeliefStore:
    store = BeliefStore()
    store.update(
        Character(
            entity_id="flavius_julius",
            provenance="campaign_setup",
            existence=ExistenceStatus.BELIEVED_PRESENT,
            name="Flavius Julius",
            faction="romans_julii",
            x=89.0,
            y=82.0,
            role="leader",
        )
    )
    store.update(
        Army(
            entity_id="flavius_julius_army",
            provenance="campaign_setup",
            existence=ExistenceStatus.BELIEVED_PRESENT,
            faction="romans_julii",
            x=89.0,
            y=82.0,
            strength=5.0,
            general="Flavius Julius",
        )
    )
    return store


def test_a_move_command_parses_to_name_and_tile():
    assert parse_move_character("move_character Flavius Julius 90,82") == (
        "Flavius Julius",
        90.0,
        82.0,
    )
    assert parse_move_character("halt_ai julii") is None


def test_recording_a_move_updates_the_character_and_its_army():
    store = _store_with_flavius()

    entry = record_own_move(
        store, "move_character Flavius Julius 90,82", turn=1, now=1_700_000_000.0
    )

    assert entry is not None
    assert entry["from"] == [89.0, 82.0]
    assert entry["to"] == [90.0, 82.0]
    assert entry["turn"] == 1
    assert entry["source"] == OWN_ORDER_PROVENANCE

    character = store.get_character_entity("flavius_julius")
    assert character is not None
    assert (character.x, character.y) == (90.0, 82.0)
    assert character.provenance == OWN_ORDER_PROVENANCE
    assert character.existence == ExistenceStatus.OBSERVED_PRESENT

    army = store.get_army_entity("flavius_julius_army")
    assert army is not None
    assert (army.x, army.y) == (90.0, 82.0)
    assert army.provenance == OWN_ORDER_PROVENANCE


def test_an_unknown_character_is_not_invented():
    store = BeliefStore()

    assert record_own_move(store, "move_character Nobody 1,1") is None
    assert store.get_characters() == []
    assert store.history == []


def test_a_no_op_move_leaves_history_alone():
    store = _store_with_flavius()

    assert record_own_move(store, "move_character Flavius Julius 89,82") is None
    assert store.history == []


def test_the_brief_sees_the_new_position():
    """The director's eyes are the brief. After a move it must not still show 89,82."""
    from comstar_game_ai.agent.reach.context_builder import (
        ObservableContext,
        build_observable_brief,
    )

    store = _store_with_flavius()
    record_own_move(store, "move_character Flavius Julius 91,83", turn=2)

    brief = build_observable_brief(
        ObservableContext(phase="campaign", turn=2, player_faction="julii", summary=""),
        store,
    )

    assert '"at":[91,83]' in brief.replace(" ", "")
    assert '"from":[89.0,82.0]' in brief.replace(" ", "") or '"from": [89.0, 82.0]' in brief
