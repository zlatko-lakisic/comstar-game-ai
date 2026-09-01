"""Parse output_unit_positions battle geometry files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class UnitPosition:
    alliance_index: int
    army_index: int
    unit_index: int
    x: float
    y: float
    rotation_deg: float
    width_metres: float
    men: int


@dataclass
class BattlePositions:
    units: list[UnitPosition]

    @property
    def total_men(self) -> int:
        return sum(u.men for u in self.units)

    def by_alliance(self, alliance_index: int) -> list[UnitPosition]:
        return [u for u in self.units if u.alliance_index == alliance_index]


def parse_unit_positions_line(line: str) -> UnitPosition | None:
    """Parse one CSV line from output_unit_positions."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith(";"):
        return None
    parts = [p.strip() for p in stripped.split(",")]
    if len(parts) < 8:
        return None
    try:
        return UnitPosition(
            alliance_index=int(parts[0]),
            army_index=int(parts[1]),
            unit_index=int(parts[2]),
            x=float(parts[3]),
            y=float(parts[4]),
            rotation_deg=float(parts[5]),
            width_metres=float(parts[6]),
            men=int(float(parts[7])),
        )
    except ValueError:
        return None


def parse_unit_positions(text: str) -> BattlePositions:
    """Parse full output_unit_positions file contents."""
    units: list[UnitPosition] = []
    for line in text.splitlines():
        unit = parse_unit_positions_line(line)
        if unit is not None:
            units.append(unit)
    return BattlePositions(units=units)


def parse_unit_positions_file(path: Path | str) -> BattlePositions:
    return parse_unit_positions(Path(path).read_text(encoding="utf-8", errors="replace"))
