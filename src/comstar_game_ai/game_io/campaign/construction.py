"""Owned-settlement construction, recruitment, and the building-unlock line.

Select a town first. Home frames and selects the capital. 6 opens Construction,
5 opens Recruitment; both are right-edge docks and leave the map playable.
The same two actions sit on footer discs left of End Turn, tooltips
`Recruitment <5>` and `Construction <6>`. The tree disc to their right is the
Building Browser. Construction's tooltip also says right-click that disc to
open the browser. There is no key binding.

A left-click on a construction or recruitment card queues the item and spends
money. Hover reads name, cost, time, and effects. Right-click opens the info
scroll. Alt+click / Alt+right-click is the Steam wiki.

The Building Browser is the unlock line. Columns are settlement tiers with
population thresholds. Colour means built; grey means not built or unavailable.
Green connectors are open paths. A red chain is a missing gate — population or
the government building of that tier — not accept/reject. Escape does not
close it. Close with its X.

Two different upgrades:

* **Building upgrade.** The next icon in a chain (Trader → Market) appears in
  the construction dock when the prior building is present and the town is
  large enough.
* **Settlement expand.** The HUD shows current population next to the next
  tier's threshold (Arretium this turn: 4000 / 6000). When population reaches
  that number the next government building can be queued; finishing it grows
  the settlement and unlocks the next column.

Fandom's Building Browser page is thin: population bands and the rule that
government buildings gate the same tier. It does not publish a Julii unlock
table. The official Total War wiki adds colour/grey, right-click info, and
that government gates same-level structures. The Remastered
`export_descr_buildings.txt` is the table for who a building trains.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HudControl:
    id: str
    centre: tuple[float, float]
    purpose: str
    hazard: str = ""


#: Footer discs under the construction / recruitment dock, left of End Turn.
#: Centres from gold-disc peaks on town_construct.png, confirmed by tooltip.
CONTROLS: tuple[HudControl, ...] = (
    HudControl(
        id="recruit_footer",
        centre=(0.878, 0.968),
        purpose="Banner-plus disc. Tooltip: 'Recruitment <5>'. Same as key 5.",
        hazard="A click on a unit card inside the dock queues and spends.",
    ),
    HudControl(
        id="construct_footer",
        centre=(0.902, 0.968),
        purpose=(
            "Building-plus disc. Tooltip: 'Construction <6>' and "
            "'right-click to open Building Browser'. Same as key 6."
        ),
        hazard="A click on a building card inside the dock queues and spends.",
    ),
    HudControl(
        id="browser_footer",
        centre=(0.934, 0.968),
        purpose="Tree disc. Tooltip: 'Building Browser'. No key binding.",
    ),
)


BROWSER_OPEN = (0.934, 0.968)
CONSTRUCT_FOOTER = (0.902, 0.968)
RECRUIT_FOOTER = (0.878, 0.968)

#: Live measure of the Building Browser this session (town_browser.png).
BROWSER_LEFT = 0.256
BROWSER_RIGHT = 0.743
BROWSER_TOP = 0.206
BROWSER_CLOSE_X = (0.752, 0.196)

#: Shipped construction-card tooltip (`TMT_CONSTRUCTION_HELP`).
CONSTRUCTION_HELP = "Left click to add to queue, right click for information"

#: Population thresholds drawn on the Building Browser header this turn.
#: Fandom lists the same bands (town 1–1999, large town 2000–5999, …).
#: The live header also printed Town 400 as the first column.
POPULATION_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("Town", 400),
    ("Large town", 2000),
    ("Minor city", 6000),
    ("Large city", 12000),
    ("Huge city", 24000),
)


@dataclass(frozen=True)
class Unlock:
    """One Julii unlock, sourced from the install EDB and checked live where noted."""

    building: str
    chain: str
    settlement_min: str
    trains: tuple[str, ...]
    source: str
    live: str = ""


#: Roman / Julii lines from Remastered `export_descr_buildings.txt`.
#: `merchant` is gated on a Remastered toggle and was not on the recruit dock.
#: Pre-Marius unit names; Marian replacements are in the same EDB block.
JULII_UNLOCKS: tuple[Unlock, ...] = (
    Unlock(
        building="Governor's Villa",
        chain="core_building",
        settlement_min="town",
        trains=("Peasants", "Diplomat"),
        source="edb governors_villa; browser hover on Arretium",
        live="Villa already built. Recruit dock offered Diplomat.",
    ),
    Unlock(
        building="Governor's Palace",
        chain="core_building",
        settlement_min="large_town",
        trains=("Peasants", "Diplomat"),
        source="edb governors_palace; browser hover",
        live=(
            "Grey with a red chain this turn. HUD shows 4000 / 6000 — the "
            "palace is the expand step, not on the construction dock yet."
        ),
    ),
    Unlock(
        building="Muster Field",
        chain="barracks",
        settlement_min="town",
        trains=("Town Watch",),
        source="edb muster_field recruit roman city militia",
        live="Town Watch on the recruit dock.",
    ),
    Unlock(
        building="Militia Barracks",
        chain="barracks",
        settlement_min="large_town",
        trains=("Town Watch", "Hastati"),
        source="edb militia_barracks; Hastati requires not marian_reforms",
        live="Hastati on the recruit dock.",
    ),
    Unlock(
        building="Stables",
        chain="equestrian",
        settlement_min="large_town",
        trains=("Equites", "Wardogs"),
        source="edb stables; hover on construction dock",
        live="Not built. Construction hover: 1080 gold, 3 turns.",
    ),
    Unlock(
        building="Practice Range",
        chain="missiles",
        settlement_min="large_town",
        trains=("Velites",),
        source="edb practice_field; hover on construction dock",
        live="Not built. Construction hover: 1080 gold, 3 turns.",
    ),
    Unlock(
        building="Trader",
        chain="market",
        settlement_min="town",
        trains=(),
        source="edb trader (income only)",
        live="Already built. No spy.",
    ),
    Unlock(
        building="Market",
        chain="market",
        settlement_min="large_town",
        trains=("Spy",),
        source="edb market agent spy",
        live="On the construction dock. Recruit dock had no spy.",
    ),
    Unlock(
        building="Forum",
        chain="market",
        settlement_min="city",
        trains=("Spy", "Assassin"),
        source="edb forum agent assassin",
    ),
    Unlock(
        building="Port",
        chain="port_buildings",
        settlement_min="large_town",
        trains=("Biremes",),
        source="edb port recruit naval biremes",
        live="A warship card sat on the recruit dock.",
    ),
    Unlock(
        building="Academy",
        chain="academic",
        settlement_min="city",
        trains=(),
        source="edb academy requires building_present_min_level market market",
    ),
)


BY_CONTROL: dict[str, HudControl] = {control.id: control for control in CONTROLS}
BY_BUILDING: dict[str, Unlock] = {item.building: item for item in JULII_UNLOCKS}


def mutating_controls() -> tuple[HudControl, ...]:
    return tuple(control for control in CONTROLS if control.hazard)


def agent_unlocks() -> tuple[Unlock, ...]:
    return tuple(
        item
        for item in JULII_UNLOCKS
        if any(name in item.trains for name in ("Diplomat", "Spy", "Assassin"))
    )
