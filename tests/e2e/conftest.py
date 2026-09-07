"""Fixtures for the agent end-to-end suite.

The point of this suite is that every agent is exercised with the prompt and the
context it will actually be given, so a channel that mangles the answer fails here
rather than on turn 1 of a live campaign. Two transports, one set of prompts:
`test_agent_channels` runs them against a recording bridge and always runs,
`test_agents_live` runs them against ada.

The belief fixture is the real Julii opening — Arretium held, Segesta and Patavium
rebel-held to the north, Gauls at Mediolanium — because the questions we are testing
ask the model to weigh distances and ownership. A director shown an empty map would
answer "hold" correctly, and prove nothing.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import pytest_asyncio

from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.reach.context_builder import ObservableContext, build_observable_brief

JULII = "romans_julii"


def _character(entity_id: str, name: str, x: float, y: float) -> Character:
    return Character(
        entity_id=entity_id,
        provenance="script_telemetry",
        confidence=1.0,
        existence=ExistenceStatus.OBSERVED_PRESENT,
        name=name,
        faction=JULII,
        x=x,
        y=y,
        role="general",
    )


def _settlement(
    entity_id: str, region: str, owner: str, x: float, y: float, population: int
) -> Settlement:
    return Settlement(
        entity_id=entity_id,
        provenance="script_telemetry",
        confidence=1.0,
        existence=ExistenceStatus.OBSERVED_PRESENT,
        region=region,
        owner=owner,
        x=x,
        y=y,
        population=population,
    )


@pytest.fixture
def julii_opening() -> BeliefStore:
    """One held town, two free generals, three towns worth taking."""
    store = BeliefStore()
    store.update(_character("flavius", "Flavius Julius", 98, 142))
    store.update(_character("vibius", "Vibius Julius", 96, 146))
    store.update(_settlement("arretium", "Etruria", JULII, 98, 142, 2400))
    store.update(_settlement("segesta", "Liguria", "slave", 86, 152, 1200))
    store.update(_settlement("patavium", "Venetia", "slave", 108, 158, 1400))
    store.update(_settlement("mediolanium", "Cisalpine Gaul", "gauls", 92, 160, 2000))
    store.history.extend(
        [
            {"event": "NewTurnStart", "turn": 3, "faction": "julii"},
            {"event": "SettlementSelected", "settlement": "arretium"},
        ]
    )
    return store


@pytest.fixture
def empty_belief() -> BeliefStore:
    """What a blind run actually hands the director."""
    return BeliefStore()


@pytest.fixture
def campaign_brief(julii_opening: BeliefStore) -> str:
    return build_observable_brief(
        ObservableContext(
            phase="campaign", turn=3, player_faction="julii", summary="turn 3"
        ),
        julii_opening,
    )


@pytest.fixture
def battle_brief(julii_opening: BeliefStore) -> str:
    return build_observable_brief(
        ObservableContext(
            phase="battle",
            tick=2,
            battle_id="segesta-assault",
            player_faction="julii",
            summary="assaulting Segesta: 6 units engaged, rams at the gate",
        ),
        julii_opening,
    )


@pytest.fixture
def after_action_context() -> str:
    """Records shaped like the privileged store's, for the offline analysts."""
    return json.dumps(
        {
            "records": [
                {
                    "record_type": "battle",
                    "turn": 6,
                    "outcome": "won",
                    "note": "Auto-resolved the Segesta assault at 40% losses; the "
                    "general led the first wave.",
                },
                {
                    "record_type": "battle",
                    "turn": 11,
                    "outcome": "lost",
                    "note": "Lone general charged a rebel stack in the open and died.",
                },
                {
                    "record_type": "campaign",
                    "turn": 14,
                    "outcome": "deficit",
                    "note": "Income fell to -191 as four new family members added "
                    "bodyguard upkeep; no settlement built income buildings.",
                },
            ]
        },
        indent=2,
    )


@pytest.fixture
def doctrine_document() -> str:
    return (
        "## Siege economics\n"
        "Starving a settlement costs turns but no men. Assault when the garrison is "
        "below half the besieging force, otherwise wait.\n\n"
        "## Generals\n"
        "A general alone is a casualty waiting to happen. Never move a general "
        "without at least two accompanying units.\n\n"
        "## The Julii opening\n"
        "The Julii begin at Arretium with rebel Segesta and Patavium to the north and "
        "the Gauls beyond. Historically the northern towns fall by turn 12."
    )


# --- live session ----------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def live_session() -> Any:
    """One Reach session for the whole live module.

    Registering the overlay per test would spend more time on handshakes than on
    inference. `game_query` stays off: every agent here is either JSON mode, which
    runs no crew and so can hold no tools, or prose that needs none.

    The `loop_scope` is load-bearing, and every test in the module must declare the
    same one. The bridge's receive task belongs to the loop this fixture was created
    on; a test running on its own loop never gets the frames, so `run_end` arrives
    to nobody and a call that the engine answered in twelve seconds fails as a
    five-minute timeout. That mismatch cost an afternoon of chasing the engine.
    """
    from comstar_game_ai.agent.reach.session import ReachSession

    session = ReachSession(enable_game_query=False)
    await session.start()
    try:
        yield session
    finally:
        await session.stop(clear_remote=True)
