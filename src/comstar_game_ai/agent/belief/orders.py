"""Belief updates that come from orders we ourselves issued.

The campaign KB is the BeliefStore. Screenshots, console output and telemetry
exist to feed it; the director never sees any of them. The cheapest, most
reliable writer is the one that already knows what just happened: when Process A
successfully issues `move_character Name x,y`, the character is wherever we
sent them — update the position and append the from→to trail so the next brief
is still true.

This is not a substitute for observation. It keeps belief honest about what we
did; a Lists panel scrape or settlement tooltip will still have to write what
we saw. Both paths land here, in the store, not in the director's prompt.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus
from comstar_game_ai.agent.belief.store import BeliefStore

_LOGGER = logging.getLogger(__name__)

#: Provenance for anything we know because we ordered it. Distinct from
#: `campaign_setup` (what Rome said at the opening) and `script_telemetry`
#: (what a log claimed to observe).
OWN_ORDER_PROVENANCE = "own_order"

_MOVE_RE = re.compile(
    r"^move_character\s+(.+?)\s+(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def parse_move_character(command: str) -> tuple[str, float, float] | None:
    """`(name, x, y)` from a fair-play move command, or None if it is not one."""
    match = _MOVE_RE.match((command or "").strip())
    if match is None:
        return None
    name, x_raw, y_raw = match.groups()
    return name.strip(), float(x_raw), float(y_raw)


def record_own_move(
    store: BeliefStore,
    command: str,
    *,
    turn: int | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Update the character (and any army that follows them) after a successful move.

    Returns the history entry that was appended, or None when the command is not
    a move or the character is not in the store. Never invents a character: if
    we somehow ordered a move for someone belief does not know, that is a bug in
    the planner, not a fact to invent here.
    """
    parsed = parse_move_character(command)
    if parsed is None:
        return None
    name, x, y = parsed

    character = _find_character(store, name)
    if character is None:
        _LOGGER.warning("own move for unknown character %r — belief unchanged", name)
        return None

    observed_at = now if now is not None else time.time()
    from_xy = (float(character.x), float(character.y))
    if from_xy == (x, y):
        return None

    updated = Character(
        entity_id=character.entity_id,
        provenance=OWN_ORDER_PROVENANCE,
        observed_at=observed_at,
        confidence=1.0,
        existence=ExistenceStatus.OBSERVED_PRESENT,
        attributes=dict(character.attributes),
        name=character.name,
        faction=character.faction,
        x=x,
        y=y,
        role=character.role,
    )
    if turn is not None:
        attrs = dict(updated.attributes)
        attrs["last_seen_turn"] = int(turn)
        updated.attributes = attrs
    store.update(updated)

    # An army seeded as `{character}_army` travels with its general.
    army_id = f"{character.entity_id}_army"
    army = store.get_army_entity(army_id)
    if army is not None:
        from comstar_game_ai.agent.belief.entities import Army

        army_attrs = dict(army.attributes)
        if turn is not None:
            army_attrs["last_seen_turn"] = int(turn)
        store.update(
            Army(
                entity_id=army.entity_id,
                provenance=OWN_ORDER_PROVENANCE,
                observed_at=observed_at,
                confidence=1.0,
                existence=ExistenceStatus.OBSERVED_PRESENT,
                attributes=army_attrs,
                faction=army.faction,
                x=x,
                y=y,
                strength=army.strength,
                general=army.general or character.name,
            )
        )

    entry: dict[str, Any] = {
        "event": "move",
        "source": OWN_ORDER_PROVENANCE,
        "id": character.entity_id,
        "name": character.name,
        "from": [from_xy[0], from_xy[1]],
        "to": [x, y],
    }
    if turn is not None:
        entry["turn"] = int(turn)
    store.history.append(entry)
    # Cap the trail the same way get_history does, so a long campaign does not
    # grow the snapshot without bound.
    if len(store.history) > 100:
        store.history = store.history[-100:]
    return entry


def _find_character(store: BeliefStore, name: str) -> Character | None:
    """Match by name first, then by entity_id — either is how a planner may refer."""
    needle = name.strip().lower()
    if not needle:
        return None
    for character in store.get_characters():
        if (character.name or "").strip().lower() == needle:
            return character
        if (character.entity_id or "").strip().lower() == needle:
            return character
    return None
