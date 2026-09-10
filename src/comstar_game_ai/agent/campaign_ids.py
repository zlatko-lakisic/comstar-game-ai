"""Id ↔ name map for campaign entities.

Ids go to the director. Names go to the narrator and log viewers. The map itself
is never sent to the director.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comstar_game_ai.agent.belief.entities import Army, Character, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.shared.config import repo_root

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    s = _SLUG_RE.sub("_", (text or "").strip().lower()).strip("_")
    return s or "unknown"


@dataclass
class CampaignIdMap:
    """Stable ids for one campaign. Settlements, generals, factions."""

    settlements: dict[str, str] = field(default_factory=dict)  # id -> name
    generals: dict[str, str] = field(default_factory=dict)
    factions: dict[str, str] = field(default_factory=dict)
    _settlement_by_name: dict[str, str] = field(default_factory=dict, repr=False)
    _general_by_key: dict[str, str] = field(default_factory=dict, repr=False)

    def faction_id(self, name: str) -> str:
        key = _slug(name)
        fid = f"fac_{key}"
        self.factions.setdefault(fid, name or key)
        return fid

    def settlement_id(self, settlement: Settlement) -> str:
        name = (settlement.entity_id or settlement.region or "").strip()
        key = name.lower()
        if key in self._settlement_by_name:
            return self._settlement_by_name[key]
        sid = f"set_{_slug(name)}"
        # Collision: append short hash of coords.
        if sid in self.settlements and self.settlements[sid].lower() != key:
            sid = f"set_{_slug(name)}_{int(settlement.x)}_{int(settlement.y)}"
        self.settlements[sid] = name or sid
        self._settlement_by_name[key] = sid
        return sid

    def general_id(self, character: Character) -> str:
        key = (character.entity_id or character.name or "").strip().lower()
        if key in self._general_by_key:
            return self._general_by_key[key]
        gid = f"gen_{_slug(character.entity_id or character.name)}"
        if gid in self.generals and self.generals[gid].lower() != (character.name or "").lower():
            gid = f"gen_{_slug(character.entity_id or character.name)}_{len(self.generals)}"
        self.generals[gid] = character.name or character.entity_id or gid
        self._general_by_key[key] = gid
        return gid

    def all_ids(self) -> set[str]:
        return set(self.settlements) | set(self.generals) | set(self.factions)

    def name_for(self, entity_id: str) -> str:
        eid = (entity_id or "").strip().lower()
        for table in (self.settlements, self.generals, self.factions):
            for k, v in table.items():
                if k.lower() == eid:
                    return v
        return entity_id

    def proper_nouns(self) -> set[str]:
        """Every human-readable name — must not appear in a director payload."""
        names: set[str] = set()
        for table in (self.settlements, self.generals, self.factions):
            for name in table.values():
                n = (name or "").strip()
                if n and not n.startswith(("set_", "gen_", "fac_")):
                    names.add(n)
        return names

    def to_dict(self) -> dict[str, Any]:
        return {
            "settlements": dict(self.settlements),
            "generals": dict(self.generals),
            "factions": dict(self.factions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CampaignIdMap:
        m = cls(
            settlements={str(k): str(v) for k, v in (data.get("settlements") or {}).items()},
            generals={str(k): str(v) for k, v in (data.get("generals") or {}).items()},
            factions={str(k): str(v) for k, v in (data.get("factions") or {}).items()},
        )
        m._settlement_by_name = {v.lower(): k for k, v in m.settlements.items()}
        m._general_by_key = {v.lower(): k for k, v in m.generals.items()}
        for k in m.generals:
            m._general_by_key[k.lower()] = k
        return m

    def save(self, path: Path | None = None) -> Path:
        target = path or default_id_map_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> CampaignIdMap:
        target = path or default_id_map_path()
        if not target.is_file():
            return cls()
        try:
            return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()


def default_id_map_path() -> Path:
    return repo_root() / "data" / "runtime" / "campaign_id_map.json"


def sync_id_map_from_belief(belief: BeliefStore, id_map: CampaignIdMap | None = None) -> CampaignIdMap:
    """Ensure every entity currently in belief has an id."""
    m = id_map or CampaignIdMap.load()
    for s in belief.get_settlements():
        m.settlement_id(s)
        if s.owner:
            m.faction_id(s.owner)
    for c in belief.get_characters():
        m.general_id(c)
        if c.faction:
            m.faction_id(c.faction)
    for a in belief.get_armies():
        if a.faction:
            m.faction_id(a.faction)
    return m
