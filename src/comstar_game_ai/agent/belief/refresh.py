"""Per-turn belief advance: ages, confidence decay, treasury refresh (F3).

Ages and confidence must move every turn even under a pure hold policy. A
belief that freezes after the opening seed cannot satisfy the Phase 1 contract.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from comstar_game_ai.agent.belief.entities import BeliefEntity
from comstar_game_ai.agent.belief.store import BeliefStore

_LOGGER = logging.getLogger(__name__)

#: Half-life of confidence in *turns* (not wall-clock). Matches the spirit of
#: handoff §5.1; attribute-specific curves can replace this single knob later.
TURN_CONFIDENCE_HALF_LIFE = 2.0
MIN_CONFIDENCE = 0.05

#: Faction-beliefs key that records the last turn we advanced the store.
_META_KEY = "_belief_clock"
_LAST_TURN_KEY = "last_advanced_turn"


def last_seen_turn(entity: BeliefEntity) -> int | None:
    attrs = entity.attributes or {}
    raw = attrs.get("last_seen_turn")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def mark_observed(entity: BeliefEntity, *, turn: int, now: float | None = None) -> None:
    """Stamp an entity as freshly observed on `turn`."""
    attrs = dict(entity.attributes or {})
    attrs["last_seen_turn"] = int(turn)
    entity.attributes = attrs
    entity.observed_at = now if now is not None else time.time()
    entity.confidence = max(entity.confidence, 1.0)


def _entities(store: BeliefStore) -> list[BeliefEntity]:
    return [
        *store.get_armies(),
        *store.get_settlements(),
        *store.get_characters(),
    ]


def _decay_one_turn(confidence: float, *, half_life: float) -> float:
    factor = 0.5 ** (1.0 / max(half_life, 1e-6))
    return max(MIN_CONFIDENCE, float(confidence) * factor)


def advance_belief_for_turn(
    store: BeliefStore,
    *,
    current_turn: int,
    observation: dict[str, Any] | None = None,
    player_faction: str = "julii",
    half_life_turns: float = TURN_CONFIDENCE_HALF_LIFE,
) -> dict[str, Any]:
    """Advance ages/confidence for `current_turn` and apply any fresh observation.

    Idempotent for the same `current_turn`. Returns a small summary for logs.
    """
    turn = int(current_turn)
    clock = dict(store.faction_beliefs.get(_META_KEY) or {})
    last = clock.get(_LAST_TURN_KEY)
    try:
        last_i = int(last) if last is not None else None
    except (TypeError, ValueError):
        last_i = None

    turns_elapsed = 0
    if last_i is None:
        # First advance after seed: stamp missing last_seen_turn, then age by
        # how far the game has already moved past the stamp.
        for entity in _entities(store):
            if last_seen_turn(entity) is None:
                # Treat as seen on the prior turn so this advance yields age ≥ 1
                # when the campaign has already progressed, or age 0 on turn 1.
                stamp = max(0, turn - 1)
                attrs = dict(entity.attributes or {})
                attrs["last_seen_turn"] = stamp
                entity.attributes = attrs
        turns_elapsed = 1 if turn > 0 else 0
    elif turn > last_i:
        turns_elapsed = turn - last_i
    elif turn == last_i:
        turns_elapsed = 0
    else:
        # Reload / turn counter reset — re-baseline without inventing decay.
        turns_elapsed = 0
        _LOGGER.warning(
            "belief clock went backwards (%s -> %s); re-baselining", last_i, turn
        )

    decayed = 0
    if turns_elapsed > 0:
        for entity in _entities(store):
            before = entity.confidence
            for _ in range(turns_elapsed):
                entity.confidence = _decay_one_turn(
                    entity.confidence, half_life=half_life_turns
                )
            if entity.confidence != before:
                decayed += 1

    refreshed = _apply_observation(
        store, observation=observation, player_faction=player_faction, turn=turn
    )

    clock[_LAST_TURN_KEY] = turn
    store.faction_beliefs[_META_KEY] = clock

    summary = {
        "turn": turn,
        "turns_elapsed": turns_elapsed,
        "entities_decayed": decayed,
        "observation_keys": sorted(refreshed),
    }
    _LOGGER.info(
        "belief advanced turn=%s elapsed=%s decayed=%s refreshed=%s",
        turn,
        turns_elapsed,
        decayed,
        sorted(refreshed) or "none",
    )
    return summary


def _apply_observation(
    store: BeliefStore,
    *,
    observation: dict[str, Any] | None,
    player_faction: str,
    turn: int,
) -> set[str]:
    """Write treasury / income / unrest from the current turn's observation."""
    if not observation:
        return set()
    touched: set[str] = set()
    faction_key = (player_faction or "julii").strip().lower()
    treasury = observation.get("treasury")
    income = observation.get("income")
    if treasury is not None or income is not None:
        slot = dict(store.faction_beliefs.get(faction_key) or {})
        if treasury is not None:
            slot["treasury"] = int(treasury)
            touched.add("treasury")
        if income is not None:
            slot["income"] = int(income)
            touched.add("income")
        slot["observed_turn"] = turn
        store.faction_beliefs[faction_key] = slot

    unrest_by_settlement = observation.get("unrest") or {}
    if isinstance(unrest_by_settlement, dict):
        for sid, unrest in unrest_by_settlement.items():
            entity = store.get_settlement_entity(str(sid).lower())
            if entity is None:
                continue
            attrs = dict(entity.attributes or {})
            attrs["unrest"] = unrest
            attrs["last_seen_turn"] = turn
            entity.attributes = attrs
            entity.confidence = max(entity.confidence, 0.9)
            entity.observed_at = time.time()
            touched.add("unrest")
    return touched


def treasury_from_belief(
    store: BeliefStore, *, player_faction: str
) -> tuple[int | None, int | None]:
    """Read the last refreshed treasury/income pair for the player faction."""
    faction_key = (player_faction or "julii").strip().lower()
    slot = store.faction_beliefs.get(faction_key) or {}
    treasury = slot.get("treasury")
    income = slot.get("income")
    try:
        t = int(treasury) if treasury is not None else None
    except (TypeError, ValueError):
        t = None
    try:
        i = int(income) if income is not None else None
    except (TypeError, ValueError):
        i = None
    return t, i
