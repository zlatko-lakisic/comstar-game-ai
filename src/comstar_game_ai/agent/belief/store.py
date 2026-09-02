"""Belief store with provenance, age, confidence, and decay."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comstar_game_ai.agent.belief.entities import (
    Army,
    BeliefEntity,
    Character,
    ExistenceStatus,
    Settlement,
)
from comstar_game_ai.shared.config import repo_root

DEFAULT_HALF_LIFE_SECONDS = 300.0


def belief_snapshot_path() -> Path:
    return repo_root() / "data" / "belief_snapshot.json"


@dataclass
class BeliefStore:
    """Observable beliefs only — fog-respecting, no privileged ground truth."""

    _armies: dict[str, Army] = field(default_factory=dict)
    _settlements: dict[str, Settlement] = field(default_factory=dict)
    _characters: dict[str, Character] = field(default_factory=dict)
    faction_beliefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    unit_types: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __init__(
        self,
        *,
        armies: dict[str, dict[str, Any]] | None = None,
        settlements: dict[str, dict[str, Any]] | None = None,
        characters: dict[str, dict[str, Any]] | None = None,
        faction_beliefs: dict[str, dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
        unit_types: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._armies = {}
        self._settlements = {}
        self._characters = {}
        self.faction_beliefs = dict(faction_beliefs or {})
        self.history = list(history or [])
        self.unit_types = dict(unit_types or {})
        for army_id, data in (armies or {}).items():
            if isinstance(data, dict):
                self._armies[str(army_id)] = self._army_from_legacy(str(army_id), data)
        for settlement_id, data in (settlements or {}).items():
            if isinstance(data, dict):
                self._settlements[str(settlement_id)] = self._settlement_from_legacy(str(settlement_id), data)
        for character_id, data in (characters or {}).items():
            if isinstance(data, dict):
                self._characters[str(character_id)] = self._character_from_legacy(str(character_id), data)

    @property
    def armies(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in self._armies.items()}

    @armies.setter
    def armies(self, value: dict[str, dict[str, Any]]) -> None:
        self._armies = {
            str(k): self._army_from_legacy(str(k), v) for k, v in value.items() if isinstance(v, dict)
        }

    @property
    def settlements(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in self._settlements.items()}

    @settlements.setter
    def settlements(self, value: dict[str, dict[str, Any]]) -> None:
        self._settlements = {
            str(k): self._settlement_from_legacy(str(k), v) for k, v in value.items() if isinstance(v, dict)
        }

    @staticmethod
    def _army_from_legacy(army_id: str, data: dict[str, Any]) -> Army:
        if "entity_id" in data:
            return Army.from_dict(data)
        return Army(
            entity_id=army_id,
            provenance=str(data.get("provenance") or "legacy"),
            observed_at=float(data.get("observed_at") or time.time()),
            confidence=float(data.get("confidence", 1.0)),
            existence=ExistenceStatus(str(data.get("existence") or ExistenceStatus.BELIEVED_PRESENT.value)),
            attributes=dict(data.get("attributes") or {}),
            faction=str(data.get("faction") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            strength=float(data.get("strength", 0.0)),
            general=(str(data["general"]) if data.get("general") else None),
        )

    @staticmethod
    def _settlement_from_legacy(settlement_id: str, data: dict[str, Any]) -> Settlement:
        if "entity_id" in data:
            return Settlement.from_dict(data)
        pop = data.get("population")
        return Settlement(
            entity_id=settlement_id,
            provenance=str(data.get("provenance") or "legacy"),
            observed_at=float(data.get("observed_at") or time.time()),
            confidence=float(data.get("confidence", 1.0)),
            existence=ExistenceStatus(str(data.get("existence") or ExistenceStatus.BELIEVED_PRESENT.value)),
            attributes=dict(data.get("attributes") or {}),
            region=str(data.get("region") or ""),
            owner=str(data.get("owner") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            population=int(pop) if pop is not None else None,
        )

    @staticmethod
    def _character_from_legacy(character_id: str, data: dict[str, Any]) -> Character:
        if "entity_id" in data:
            return Character.from_dict(data)
        return Character(
            entity_id=character_id,
            provenance=str(data.get("provenance") or "legacy"),
            observed_at=float(data.get("observed_at") or time.time()),
            confidence=float(data.get("confidence", 1.0)),
            existence=ExistenceStatus(str(data.get("existence") or ExistenceStatus.BELIEVED_PRESENT.value)),
            attributes=dict(data.get("attributes") or {}),
            name=str(data.get("name") or character_id),
            faction=str(data.get("faction") or ""),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            role=str(data.get("role") or ""),
        )

    def update(self, entity: Army | Settlement | Character | BeliefEntity, *, now: float | None = None) -> None:
        """Insert or replace an entity; fresher observations win on conflict."""
        ts = now or time.time()
        if isinstance(entity, Army):
            entity.observed_at = ts
            self._armies[entity.entity_id] = entity
        elif isinstance(entity, Settlement):
            entity.observed_at = ts
            self._settlements[entity.entity_id] = entity
        elif isinstance(entity, Character):
            entity.observed_at = ts
            self._characters[entity.entity_id] = entity
        else:
            raise TypeError(f"unsupported entity type: {type(entity)!r}")

    def decay(
        self,
        *,
        now: float | None = None,
        half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
        min_confidence: float = 0.05,
    ) -> None:
        """Exponential confidence decay by entity age."""
        ts = now or time.time()
        for bucket in (self._armies, self._settlements, self._characters):
            for entity in bucket.values():
                age = entity.age_seconds(ts)
                if age <= 0:
                    continue
                decay_factor = 0.5 ** (age / max(half_life_seconds, 1.0))
                entity.confidence = max(min_confidence, entity.confidence * decay_factor)
                if entity.confidence <= min_confidence and entity.existence == ExistenceStatus.OBSERVED_PRESENT:
                    entity.existence = ExistenceStatus.BELIEVED_PRESENT

    def get_army_entity(self, army_id: str) -> Army | None:
        return self._armies.get(army_id)

    def get_settlement_entity(self, settlement_id: str) -> Settlement | None:
        return self._settlements.get(settlement_id)

    def get_character_entity(self, character_id: str) -> Character | None:
        return self._characters.get(character_id)

    def get_armies(self) -> list[Army]:
        return list(self._armies.values())

    def get_settlements(self) -> list[Settlement]:
        return list(self._settlements.values())

    def get_characters(self) -> list[Character]:
        return list(self._characters.values())

    def get_army(self, army_id: str) -> dict[str, Any] | None:
        entity = self._armies.get(army_id)
        return entity.to_dict() if entity else None

    def get_settlement(self, settlement_id: str) -> dict[str, Any] | None:
        entity = self._settlements.get(settlement_id)
        return entity.to_dict() if entity else None

    def get_character(self, character_id: str) -> dict[str, Any] | None:
        entity = self._characters.get(character_id)
        return entity.to_dict() if entity else None

    def get_history(self, n: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(int(n), 100))
        return list(self.history[-limit:])

    def get_faction_belief(self, faction: str) -> dict[str, Any] | None:
        return self.faction_beliefs.get(faction)

    def explain_unit(self, unit_type: str) -> dict[str, Any] | None:
        return self.unit_types.get(unit_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "armies": self.armies,
            "settlements": self.settlements,
            "characters": {k: v.to_dict() for k, v in self._characters.items()},
            "faction_beliefs": self.faction_beliefs,
            "history": self.history,
            "unit_types": self.unit_types,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeliefStore:
        return cls(
            armies=dict(data.get("armies") or {}),
            settlements=dict(data.get("settlements") or {}),
            characters=dict(data.get("characters") or {}),
            faction_beliefs=dict(data.get("faction_beliefs") or {}),
            history=list(data.get("history") or []),
            unit_types=dict(data.get("unit_types") or {}),
        )

    def save(self, path: Path | None = None) -> Path:
        target = path or belief_snapshot_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> BeliefStore:
        target = path or belief_snapshot_path()
        if not target.is_file():
            return cls()
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)


_default_store: BeliefStore | None = None


def default_belief_store() -> BeliefStore:
    global _default_store
    if _default_store is None:
        _default_store = BeliefStore.load()
    return _default_store
