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


def build_observable_brief(
    ctx: ObservableContext,
    store: BeliefStore | None = None,
    *,
    max_history: int = 5,
) -> str:
    """Compose a fog-respecting brief from context plus belief snapshot."""
    belief = store or default_belief_store()
    header = {
        "context": ctx.to_dict(),
        "recent_history": belief.get_history(max_history),
        "faction_beliefs": {
            faction: belief.get_faction_belief(faction)
            for faction in list(belief.faction_beliefs.keys())[:8]
        },
    }
    return json.dumps(header, indent=2)


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
