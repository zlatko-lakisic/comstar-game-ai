"""Load EDU-like unit stats from fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comstar_game_ai.shared.config import repo_root


@dataclass
class UnitStats:
    unit_type: str
    attack: float
    defence: float
    morale: float
    charge_bonus: float = 0.0
    armour: float = 0.0
    weapon: str = ""
    category: str = ""


def _parse_unit(entry: dict[str, Any]) -> UnitStats:
    return UnitStats(
        unit_type=str(entry["unit_type"]),
        attack=float(entry.get("attack", 0)),
        defence=float(entry.get("defence", 0)),
        morale=float(entry.get("morale", 50)),
        charge_bonus=float(entry.get("charge_bonus", 0)),
        armour=float(entry.get("armour", 0)),
        weapon=str(entry.get("weapon", "")),
        category=str(entry.get("category", "")),
    )


def load_unit_db(path: Path | str | None = None) -> dict[str, UnitStats]:
    """Load unit stats keyed by unit_type."""
    file_path = Path(path) if path is not None else repo_root() / "tests" / "fixtures" / "edu" / "sample_units.json"
    data = json.loads(file_path.read_text(encoding="utf-8"))
    units = data.get("units") if isinstance(data, dict) else data
    if not isinstance(units, list):
        return {}
    return {_parse_unit(u).unit_type: _parse_unit(u) for u in units if isinstance(u, dict) and u.get("unit_type")}


def unit_strength(stats: UnitStats, men: int) -> float:
    """Scalar strength from EDU-like stats and headcount."""
    per_man = stats.attack * 0.6 + stats.defence * 0.3 + stats.morale * 0.1 + stats.charge_bonus * 0.2
    return per_man * max(men, 1)
