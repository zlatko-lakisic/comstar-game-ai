"""Pre-inject observable context into agent prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from comstar_game_ai.agent.belief.store import BeliefStore, default_belief_store


@dataclass
class ObservableContext:
    """Structured header the model sees before tool pulls."""

    phase: str = "unknown"
    turn: int | None = None
    battle_id: str | None = None
    tick: int | None = None
    player_faction: str | None = None
    summary: str = ""
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "phase": self.phase,
            "summary": self.summary,
            "signals": self.signals,
        }
        if self.turn is not None:
            out["turn"] = self.turn
        if self.battle_id is not None:
            out["battle_id"] = self.battle_id
        if self.tick is not None:
            out["tick"] = self.tick
        if self.player_faction is not None:
            out["player_faction"] = self.player_faction
        return out


def _own_faction(value: str | None) -> set[str]:
    """Names Rome's logs use for the player, which are not the same string."""
    faction = str(value or "").strip().lower()
    if not faction:
        return set()
    return {faction, f"romans_{faction}"}


def _character_line(char: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": (char.name or char.entity_id),
        "at": [round(char.x), round(char.y)],
    }
    if char.role:
        out["role"] = char.role
    return out


def _settlement_line(settlement: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": settlement.entity_id or settlement.region,
        "owner": settlement.owner,
    }
    # Nothing in Rome stands at the origin, so (0, 0) means we never found out
    # where this is. Saying so beats printing a coordinate the model would happily
    # measure distances from.
    if (settlement.x, settlement.y) != (0.0, 0.0):
        out["at"] = [round(settlement.x), round(settlement.y)]
    if settlement.region:
        out["region"] = settlement.region
    if settlement.population is not None:
        out["population"] = settlement.population
    return out


def _army_line(army: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": army.entity_id,
        "faction": army.faction,
        "at": [round(army.x), round(army.y)],
        "strength": round(army.strength, 1),
    }
    if army.general:
        out["general"] = army.general
    return out


def build_observable_brief(
    ctx: ObservableContext,
    store: BeliefStore | None = None,
    *,
    max_history: int = 5,
    max_entities: int = 12,
) -> str:
    """Compose a fog-respecting brief from context plus belief snapshot.

    This used to send recent history and faction beliefs and nothing else, which on
    a fresh campaign is two empty collections: the campaign director was choosing a
    strategic objective while being shown a turn number. Its own generals and
    settlements were sitting in the belief store, unread. Whatever it answered was
    guesswork, so the fix for "the directive is always hold" starts here rather than
    in the prompt.

    Fog is still respected — every field comes from the observable belief store, so
    what the model sees is what we saw.
    """
    belief = store or default_belief_store()
    mine = _own_faction(ctx.player_faction)

    characters = belief.get_characters()
    armies = belief.get_armies()
    settlements = belief.get_settlements()

    own_characters = [c for c in characters if c.faction.strip().lower() in mine]
    own_settlements = [s for s in settlements if any(m in (s.owner or "").lower() for m in mine)]
    other_settlements = [s for s in settlements if s not in own_settlements]
    other_armies = [a for a in armies if a.faction.strip().lower() not in mine]

    header: dict[str, Any] = {
        "context": ctx.to_dict(),
        "belief": {
            # Say the quiet part out loud: a model told the map is empty can say it
            # has nothing to go on, instead of inventing a campaign from a number.
            "is_empty": not (characters or armies or settlements),
            "counts": {
                "own_characters": len(own_characters),
                "own_settlements": len(own_settlements),
                "other_settlements": len(other_settlements),
                "other_armies": len(other_armies),
            },
            "own_characters": [_character_line(c) for c in own_characters[:max_entities]],
            "own_settlements": [_settlement_line(s) for s in own_settlements[:max_entities]],
            "other_settlements": [_settlement_line(s) for s in other_settlements[:max_entities]],
            "other_armies": [_army_line(a) for a in other_armies[:max_entities]],
        },
    }
    # Empty collections were being sent as empty collections, which reads as evidence
    # of nothing rather than absence of evidence, and costs prompt tokens to say it.
    history = belief.get_history(max_history)
    if history:
        header["recent_history"] = history
    faction_beliefs = {
        faction: belief.get_faction_belief(faction)
        for faction in list(belief.faction_beliefs.keys())[:8]
    }
    if faction_beliefs:
        header["faction_beliefs"] = faction_beliefs

    # Compact, not pretty. Indentation is whitespace the model has to read: on a
    # shared GPU this brief's prompt was taking ~50s to evaluate before the model
    # produced a single token, and the newlines and padding were a real share of it.
    return json.dumps(header, separators=(",", ":"))


def update_belief_from_observation(
    observation: dict[str, Any],
    store: BeliefStore | None = None,
) -> BeliefStore:
    """Merge an observable observation dict into the belief store and persist."""
    belief = store or default_belief_store()
    for army_id, data in (observation.get("armies") or {}).items():
        if isinstance(data, dict):
            belief.armies[str(army_id)] = data
    for settlement_id, data in (observation.get("settlements") or {}).items():
        if isinstance(data, dict):
            belief.settlements[str(settlement_id)] = data
    for faction, data in (observation.get("faction_beliefs") or {}).items():
        if isinstance(data, dict):
            belief.faction_beliefs[str(faction)] = data
    for unit_type, data in (observation.get("unit_types") or {}).items():
        if isinstance(data, dict):
            belief.unit_types[str(unit_type)] = data
    entry = observation.get("history_entry")
    if isinstance(entry, dict):
        belief.history.append(entry)
        if len(belief.history) > 500:
            belief.history = belief.history[-500:]
    belief.save()
    return belief
