"""Deterministic campaign candidates and threats for the director payload.

The model never derives these. Distance and reachability live here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from comstar_game_ai.agent.belief.entities import Character, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_ids import CampaignIdMap
from comstar_game_ai.agent.predictors.movement import estimate_reach

GarrisonBand = Literal["weaker", "similar", "stronger", "unknown"]

#: Assumed free-general movement points per turn for the reach stub.
_DEFAULT_MP = 8.0


@dataclass(frozen=True)
class Candidate:
    settlement_id: str
    owner_id: str
    turns_to_reach: int
    nearest_general_id: str
    garrison: GarrisonBand
    confidence: float
    age_turns: int

    def to_payload_line(self) -> str:
        return (
            f"{self.settlement_id}  owner {self.owner_id}  {self.turns_to_reach} turns  "
            f"garrison {self.garrison}  confidence {self.confidence:.1f}  age {self.age_turns}"
        )


@dataclass(frozen=True)
class Threat:
    settlement_id: str
    hostile_faction_id: str
    turns_until_contact: int
    relative_strength: GarrisonBand

    def to_payload_line(self) -> str:
        return (
            f"{self.settlement_id}  hostile {self.hostile_faction_id}  "
            f"{self.turns_until_contact} turns  strength {self.relative_strength}"
        )


def _own_faction_names(player_faction: str) -> set[str]:
    f = (player_faction or "julii").strip().lower()
    return {f, f"romans_{f}"}


def _age_turns(entity: Any, *, current_turn: int) -> int:
    """Belief entities carry observed_at (unix). Without a turn clock, age is 0 when fresh."""
    # Attributes may hold last_seen_turn; otherwise treat as current.
    attrs = getattr(entity, "attributes", {}) or {}
    seen = attrs.get("last_seen_turn")
    if seen is None:
        return 0
    try:
        return max(0, int(current_turn) - int(seen))
    except (TypeError, ValueError):
        return 0


def _distance(a_x: float, a_y: float, b_x: float, b_y: float) -> float:
    return math.hypot(a_x - b_x, a_y - b_y)


def turns_to_reach(
    *,
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    movement_points: float = _DEFAULT_MP,
) -> int:
    """Integer turns to reach, from the movement stub. Never asked of the model."""
    dist = _distance(from_x, from_y, to_x, to_y)
    est = estimate_reach(
        movement_points=movement_points,
        destination_distance=dist,
    )
    tiles = max(1, int(est["tiles_reachable"]) or 1)
    # Distance in tiles ≈ euclidean for the stub map.
    return max(1, int(math.ceil(dist / tiles))) if dist > 0 else 0


def estimate_garrison(settlement: Settlement, *, against_strength: float | None = None) -> tuple[GarrisonBand, float]:
    """Garrison band from belief. Unknown when we have no signal."""
    pop = settlement.population
    if pop is None and against_strength is None:
        return "unknown", 0.3
    # Crude: larger population → stronger garrison estimate.
    if pop is None:
        return "unknown", 0.3
    if pop < 1500:
        band: GarrisonBand = "weaker"
    elif pop < 4000:
        band = "similar"
    else:
        band = "stronger"
    return band, 0.6


def build_candidates(
    belief: BeliefStore,
    id_map: CampaignIdMap,
    *,
    player_faction: str = "julii",
    current_turn: int = 1,
    max_candidates: int = 5,
    max_turns: int = 8,
) -> list[Candidate]:
    """Enemy/unowned settlements reachable within the commitment horizon."""
    mine = _own_faction_names(player_faction)
    generals = [
        c
        for c in belief.get_characters()
        if c.faction.strip().lower() in mine
        and (c.x or c.y)
        and (c.role or "").lower() in {"", "general", "leader", "heir", "named character"}
    ]
    # If role filter emptied the list, any own character with coords.
    if not generals:
        generals = [
            c
            for c in belief.get_characters()
            if c.faction.strip().lower() in mine and (c.x or c.y)
        ]

    out: list[Candidate] = []
    for s in belief.get_settlements():
        if not (s.x or s.y):
            continue
        owner = (s.owner or "").strip().lower()
        if any(m in owner for m in mine):
            continue  # candidates are settlements we do not own
        if not generals:
            continue
        nearest: Character | None = None
        best_turns = 10**9
        for g in generals:
            t = turns_to_reach(from_x=g.x, from_y=g.y, to_x=s.x, to_y=s.y)
            if t < best_turns:
                best_turns = t
                nearest = g
        if nearest is None or best_turns > max_turns:
            continue
        garrison, conf = estimate_garrison(s)
        out.append(
            Candidate(
                settlement_id=id_map.settlement_id(s),
                owner_id=id_map.faction_id(s.owner or "unknown"),
                turns_to_reach=best_turns,
                nearest_general_id=id_map.general_id(nearest),
                garrison=garrison,
                confidence=conf,
                age_turns=_age_turns(s, current_turn=current_turn),
            )
        )

    out.sort(key=lambda c: (c.turns_to_reach, c.settlement_id))
    return out[:max_candidates]


def build_threats(
    belief: BeliefStore,
    id_map: CampaignIdMap,
    *,
    player_faction: str = "julii",
    current_turn: int = 1,
    threat_horizon_turns: int = 2,
) -> list[Threat]:
    """Owned settlements with a hostile army inside the threat horizon."""
    mine = _own_faction_names(player_faction)
    owned = [
        s
        for s in belief.get_settlements()
        if any(m in (s.owner or "").lower() for m in mine) and (s.x or s.y)
    ]
    hostiles = [
        a
        for a in belief.get_armies()
        if a.faction.strip().lower() not in mine and (a.x or a.y)
    ]
    threats: list[Threat] = []
    for s in owned:
        for a in hostiles:
            t = turns_to_reach(from_x=a.x, from_y=a.y, to_x=s.x, to_y=s.y)
            if t > threat_horizon_turns:
                continue
            garrison, _ = estimate_garrison(s, against_strength=a.strength)
            # Relative strength of hostile vs garrison: invert garrison band roughly.
            if garrison == "weaker":
                rel: GarrisonBand = "stronger"
            elif garrison == "stronger":
                rel = "weaker"
            else:
                rel = "similar" if garrison == "similar" else "unknown"
            threats.append(
                Threat(
                    settlement_id=id_map.settlement_id(s),
                    hostile_faction_id=id_map.faction_id(a.faction or "unknown"),
                    turns_until_contact=t,
                    relative_strength=rel,
                )
            )
    threats.sort(key=lambda th: (th.turns_until_contact, th.settlement_id))
    return threats
