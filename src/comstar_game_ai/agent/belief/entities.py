"""Belief entities with provenance, age, and confidence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExistenceStatus(str, Enum):
    OBSERVED_PRESENT = "observed_present"
    BELIEVED_PRESENT = "believed_present"
    BELIEVED_DESTROYED = "believed_destroyed"
    NEVER_SEEN = "never_seen"


@dataclass
class BeliefEntity:
    """Fog-respecting world object with decaying confidence."""

    entity_id: str
    provenance: str
    observed_at: float = field(default_factory=time.time)
    confidence: float = 1.0
    existence: ExistenceStatus = ExistenceStatus.NEVER_SEEN
    attributes: dict[str, Any] = field(default_factory=dict)

    def age_seconds(self, now: float | None = None) -> float:
        return max(0.0, (now or time.time()) - self.observed_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "provenance": self.provenance,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "existence": self.existence.value,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeliefEntity:
        existence_raw = data.get("existence", ExistenceStatus.NEVER_SEEN.value)
        try:
            existence = ExistenceStatus(str(existence_raw))
        except ValueError:
            existence = ExistenceStatus.NEVER_SEEN
        return cls(
            entity_id=str(data.get("entity_id") or ""),
            provenance=str(data.get("provenance") or "unknown"),
            observed_at=float(data.get("observed_at") or time.time()),
            confidence=float(data.get("confidence", 1.0)),
            existence=existence,
            attributes=dict(data.get("attributes") or {}),
        )


@dataclass
class Army(BeliefEntity):
    faction: str = ""
    x: float = 0.0
    y: float = 0.0
    strength: float = 0.0
    general: str | None = None

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "entity_type": "army",
                "faction": self.faction,
                "x": self.x,
                "y": self.y,
                "strength": self.strength,
                "general": self.general,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Army:
        base = BeliefEntity.from_dict(data)
        return cls(
            entity_id=base.entity_id,
            provenance=base.provenance,
            observed_at=base.observed_at,
            confidence=base.confidence,
            existence=base.existence,
            attributes=base.attributes,
            faction=str(data.get("faction") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            strength=float(data.get("strength", 0.0)),
            general=(str(data["general"]) if data.get("general") else None),
        )


@dataclass
class Settlement(BeliefEntity):
    region: str = ""
    owner: str = ""
    x: float = 0.0
    y: float = 0.0
    population: int | None = None

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "entity_type": "settlement",
                "region": self.region,
                "owner": self.owner,
                "x": self.x,
                "y": self.y,
                "population": self.population,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settlement:
        base = BeliefEntity.from_dict(data)
        pop = data.get("population")
        return cls(
            entity_id=base.entity_id,
            provenance=base.provenance,
            observed_at=base.observed_at,
            confidence=base.confidence,
            existence=base.existence,
            attributes=base.attributes,
            region=str(data.get("region") or ""),
            owner=str(data.get("owner") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            population=int(pop) if pop is not None else None,
        )


@dataclass
class Character(BeliefEntity):
    name: str = ""
    faction: str = ""
    x: float = 0.0
    y: float = 0.0
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "entity_type": "character",
                "name": self.name,
                "faction": self.faction,
                "x": self.x,
                "y": self.y,
                "role": self.role,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Character:
        base = BeliefEntity.from_dict(data)
        return cls(
            entity_id=base.entity_id,
            provenance=base.provenance,
            observed_at=base.observed_at,
            confidence=base.confidence,
            existence=base.existence,
            attributes=base.attributes,
            name=str(data.get("name") or base.entity_id),
            faction=str(data.get("faction") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            role=str(data.get("role") or ""),
        )
