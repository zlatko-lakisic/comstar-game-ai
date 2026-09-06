"""Produce cost and per-turn run cost for Julii units, buildings, and field works.

`stat_cost` in `export_descr_unit.txt` is turns, recruit, upkeep, weapon, armour,
custom. Recruit tooltips show both the produce cost and a down-arrow upkeep.
Buildings have no upkeep; they change income after they complete, not when queued.
Unit upkeep hits when the unit exists next turn, not when it is queued.

EDB/EDU list the full price. Live hovers this turn were 10% cheaper on several
buildings (Practice Range 1080 vs EDB 1200; Trader 540 vs 600). Prefer the hover
when both exist.

Field works come from `descr_sm_forts_ports_watchtowers.txt`: watchtower 200,
fort 500. Forts vanish in one turn if empty. Watchtowers extend LOS on own land.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitCost:
    name: str
    recruit: int
    upkeep: int
    turns: int
    source: str
    live: str = ""


@dataclass(frozen=True)
class BuildingCost:
    name: str
    construct: int
    turns: int
    #: Buildings have no per-turn upkeep.
    upkeep: int = 0
    live_construct: int | None = None
    source: str = ""
    live: str = ""


@dataclass(frozen=True)
class FieldWork:
    name: str
    construct: int
    source: str
    live: str = ""


#: Pre-Marius Julii units seen or offered this turn.
UNITS: tuple[UnitCost, ...] = (
    UnitCost(
        "Peasants",
        recruit=100,
        upkeep=100,
        turns=1,
        source="edu stat_cost",
        live="Queued at Arretium: treasury 2840 → 2740. One tooltip said 120.",
    ),
    UnitCost(
        "Town Watch",
        recruit=150,
        upkeep=100,
        turns=1,
        source="edu stat_cost",
    ),
    UnitCost(
        "Hastati",
        recruit=440,
        upkeep=170,
        turns=1,
        source="edu stat_cost",
        live="Queued at Arretium: treasury 2740 → 2300.",
    ),
    UnitCost(
        "Velites",
        recruit=270,
        upkeep=170,
        turns=1,
        source="edu stat_cost",
    ),
    UnitCost(
        "Equites",
        recruit=420,
        upkeep=110,
        turns=1,
        source="edu stat_cost",
    ),
    UnitCost(
        "Biremes",
        recruit=660,
        upkeep=100,
        turns=1,
        source="edu stat_cost",
        live="One hover said upkeep 40; EDU 100 is the table.",
    ),
)


#: Construction-dock and EDB prices. `live_construct` is the hover this turn.
BUILDINGS: tuple[BuildingCost, ...] = (
    BuildingCost(
        "Practice Range",
        construct=1200,
        turns=3,
        live_construct=1080,
        source="edb practice_field",
        live="Queued at Arretium: treasury 5000 → 3920. Per-turn HUD stayed +442.",
    ),
    BuildingCost(
        "Stables",
        construct=1200,
        turns=3,
        live_construct=1080,
        source="edb stables",
        live="Hover only. Same 1080 / 3 turns as Practice Range.",
    ),
    BuildingCost(
        "Trader",
        construct=600,
        turns=2,
        live_construct=540,
        source="edb trader",
        live="Already built at Arretium. Hover 540.",
    ),
    BuildingCost(
        "Market",
        construct=1200,
        turns=3,
        source="edb market",
        live="On the construction dock. Unlocks Spy. Not queued.",
    ),
)


FIELD_WORKS: tuple[FieldWork, ...] = (
    FieldWork(
        "watchtower",
        construct=200,
        source="descr_sm_forts_ports_watchtowers.txt",
        live="Left card on FIELD CONSTRUCTION. Not clicked.",
    ),
    FieldWork(
        "fort",
        construct=500,
        source="descr_sm_forts_ports_watchtowers.txt",
        live="Right card on FIELD CONSTRUCTION. Not clicked. Empty forts vanish in 1 turn.",
    ),
)

BY_UNIT: dict[str, UnitCost] = {item.name: item for item in UNITS}
BY_BUILDING: dict[str, BuildingCost] = {item.name: item for item in BUILDINGS}
BY_FIELD: dict[str, FieldWork] = {item.name: item for item in FIELD_WORKS}


#: Live Arretium spend this session, Julii turn 1.
#: Start 5000 (+442). Buildings did not drop +income when queued.
#: Per-turn fell only after recruit (population/tax), not by full unit upkeep.
TREASURY_SPENDS: tuple[tuple[str, int, int, int], ...] = (
    ("Practice Range", 1080, 5000, 3920),
    ("second construct card (1080)", 1080, 3920, 2840),
    ("Peasants", 100, 2840, 2740),
    ("Hastati", 440, 2740, 2300),
)
