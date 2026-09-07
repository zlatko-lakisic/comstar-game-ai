"""Read Rome's own campaign start position into belief.

The belief store had no writer. It was meant to be filled by the telemetry mod,
but that channel cannot carry entities: Rome's script language has no way to
enumerate settlements or characters, so `tutorial.txt` can only emit bare event
pings, and Remastered's verbose script logging does not even record a
`script_log` command's argument text. The mod fires 25 times a session and says
nothing. Every campaign therefore ran with an empty map, and the director was
being asked to choose a strategy from a turn number.

Rome ships the same facts as plain text. `descr_strat.txt` is the campaign's
starting position — every faction's settlements by region, every named
character with map coordinates, and the units standing with them.
`descr_regions.txt` names the settlement in each region. Neither is a guess or a
scrape: they are the files the game itself loads to build the campaign.

Settlement coordinates are the one thing not written down, because Rome takes
them from the map. `map_regions.tga` paints each region in the colour
`descr_regions.txt` assigns it and marks the settlement with a single black
pixel — 103 regions, 103 black pixels. Reading those back gives the position of
every settlement in the game, and the result can be checked against characters
whose coordinates *are* written down: Lucius Julius starts at (91, 80), which is
exactly where this puts Arretium, and Quintus at (96, 82), exactly Ariminum.

What this does not do is hand the player the whole map. See `seed_belief`.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from comstar_game_ai.agent.belief.entities import Army, Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore

_LOGGER = logging.getLogger(__name__)

#: Where the campaign files sit inside a Remastered install.
_DATA_SUFFIX = "Contents/Resources/Data/data"
_STRAT_SUFFIX = "world/maps/campaign/imperial_campaign/descr_strat.txt"
_REGIONS_SUFFIX = "world/maps/base/descr_regions.txt"
_REGION_MAP_SUFFIX = "world/maps/base/map_regions.tga"

#: Rome writes the position on the character line as `x 89, y 82`.
_COORD_RE = re.compile(r"\b([xy])\s+(-?\d+)")

#: How the strat file spells the player factions we care to translate.
_ROMAN_HOUSES = ("julii", "brutii", "scipii")

#: Provenance for anything read from the campaign's own setup files. Distinct
#: from `script_telemetry` on purpose: this is what Rome says the campaign
#: begins as, not something we watched happen.
SETUP_PROVENANCE = "campaign_setup"


def strat_faction_name(player_faction: str) -> str:
    """`julii` is what we call them; `romans_julii` is what the strat file does."""
    name = (player_faction or "").strip().lower()
    if name in _ROMAN_HOUSES:
        return f"romans_{name}"
    return name


def game_data_dir() -> Path | None:
    """Locate the shipped `data` directory of a Remastered install."""
    from comstar_game_ai.game_io.campaign.rome_strings import (
        _GAME_DIR_NAMES,
        _STEAM_LIBRARY_ROOTS,
    )
    from comstar_game_ai.shared.config import load_config

    configured = (load_config().get("paths") or {}).get("rome_data")
    if configured:
        candidate = Path(os.path.expandvars(str(configured)))
        if candidate.is_dir():
            return candidate
        _LOGGER.warning("paths.rome_data is set but not a directory: %s", candidate)

    from_env = os.environ.get("COMSTAR_ROME_DATA")
    if from_env:
        candidate = Path(os.path.expandvars(from_env))
        if candidate.is_dir():
            return candidate

    for root in _STEAM_LIBRARY_ROOTS:
        for game in _GAME_DIR_NAMES:
            candidate = Path(root) / game / _DATA_SUFFIX
            if candidate.is_dir():
                return candidate
    return None


@dataclass(frozen=True)
class Region:
    """One region: its key, the settlement in it, and where that settlement is."""

    key: str
    settlement: str
    colour: tuple[int, int, int]
    #: Rome's own grouping tag. Every Italian region carries `italy`; distant ones
    #: carry `none`. Used as the neighbourhood a faction starts able to see.
    group: str
    x: int | None = None
    y: int | None = None

    def located(self, x: int, y: int) -> Region:
        return Region(self.key, self.settlement, self.colour, self.group, x, y)


@dataclass
class FactionStart:
    """A faction's opening position, as written."""

    name: str
    settlements: list[dict[str, object]] = field(default_factory=list)
    characters: list[dict[str, object]] = field(default_factory=list)


@dataclass
class StartPosition:
    regions: dict[str, Region] = field(default_factory=dict)
    factions: dict[str, FactionStart] = field(default_factory=dict)

    def region_of_settlement(self, settlement: str) -> Region | None:
        for region in self.regions.values():
            if region.settlement.lower() == settlement.lower():
                return region
        return None


def parse_regions(text: str) -> dict[str, Region]:
    """Parse `descr_regions.txt` into region key → region.

    The format is positional, not keyed: an unindented region name followed by
    indented lines — settlement, rebel faction, ethnicity, `R G B`, group, and
    two numbers. Comments start with `;`.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if line[0].isspace():
            current.append(stripped)
        else:
            if current:
                blocks.append(current)
            current = [stripped]
    if current:
        blocks.append(current)

    regions: dict[str, Region] = {}
    for block in blocks:
        if len(block) < 6:
            continue
        try:
            r, g, b = (int(v) for v in block[4].split())
        except ValueError:
            continue
        regions[block[0]] = Region(
            key=block[0], settlement=block[1], colour=(r, g, b), group=block[5]
        )
    return regions


def locate_settlements(
    regions: dict[str, Region], map_path: Path
) -> dict[str, tuple[int, int]]:
    """Find each settlement on `map_regions.tga` and return region key → (x, y).

    A settlement is a black pixel. Which region it belongs to is decided by the
    colours around it rather than under it, since the marker itself covers the
    region's own colour.

    The y axis is flipped: the image is top-down and Rome counts from the bottom.
    That is not a guess — it is what makes the settlements land on the characters
    who start in them.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a declared dependency
        _LOGGER.warning("Pillow is missing — settlements will have no coordinates")
        return {}

    if not map_path.is_file():
        _LOGGER.warning("region map not found: %s", map_path)
        return {}

    with Image.open(map_path) as raw:
        image = raw.convert("RGB")
        width, height = image.size
        pixels = image.load()

    by_colour = {region.colour: key for key, region in regions.items()}
    located: dict[str, tuple[int, int]] = {}

    for y in range(height):
        for x in range(width):
            if pixels[x, y] != (0, 0, 0):
                continue
            tally: dict[str, int] = {}
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        key = by_colour.get(pixels[nx, ny])
                        if key:
                            tally[key] = tally.get(key, 0) + 1
            if tally:
                best = max(tally, key=lambda k: tally[k])
                located[best] = (x, height - 1 - y)

    return located


def _parse_character(line: str) -> dict[str, object] | None:
    """Parse one `character` line into name, role and position."""
    body = line.split(None, 1)
    if len(body) < 2:
        return None
    fields = [f.strip() for f in body[1].split(",")]
    name = fields[0]
    if not name:
        return None

    descriptors = {f.lower() for f in fields[1:] if f}
    if "leader" in descriptors:
        role = "leader"
    elif "heir" in descriptors:
        role = "heir"
    elif "named character" in descriptors:
        role = "general"
    else:
        role = next(
            (f for f in ("diplomat", "spy", "admiral", "general") if f in descriptors),
            "character",
        )

    coords = dict(_COORD_RE.findall(body[1]))
    if "x" not in coords or "y" not in coords:
        return None

    return {
        "name": name,
        "role": role,
        "x": int(coords["x"]),
        "y": int(coords["y"]),
        "units": 0,
    }


def parse_start_position(strat_text: str, regions: dict[str, Region]) -> StartPosition:
    """Parse `descr_strat.txt` into per-faction settlements and characters."""
    factions: dict[str, FactionStart] = {}
    current: FactionStart | None = None
    last_character: dict[str, object] | None = None
    settlement: dict[str, object] | None = None
    depth = 0

    for raw in strat_text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        # Faction blocks start unindented; the faction lists in the file header
        # are indented under `playable`, so column zero is what separates them.
        # The keyword has to match exactly. Matching a prefix instead quietly
        # emptied the file: 29 `faction_relationships` lines sit at column zero
        # further down, each naming a faction, and each one replaced that
        # faction's parsed position with a fresh empty record. Every faction
        # came back with no settlements and no characters, and the parse looked
        # like it had simply found nothing.
        parts = stripped.split(None, 1)
        if not line[0].isspace() and parts[0].lower() == "faction":
            if len(parts) == 2 and "," in parts[1]:
                name = parts[1].split(",")[0].strip().lower()
                current = FactionStart(name=name)
                factions[name] = current
                last_character = None
                continue

        if current is None:
            continue

        if settlement is not None:
            if stripped == "{":
                depth += 1
                continue
            if stripped == "}":
                depth -= 1
                if depth == 0:
                    if settlement.get("region"):
                        current.settlements.append(settlement)
                    settlement = None
                continue
            if depth == 1:
                key, _, value = stripped.partition(" ")
                key = key.lower()
                if key == "region":
                    settlement["region"] = value.strip()
                elif key == "level":
                    settlement["level"] = value.strip()
                elif key == "population":
                    try:
                        settlement["population"] = int(value.strip())
                    except ValueError:
                        pass
            continue

        if stripped == "settlement":
            settlement = {}
            depth = 0
            continue

        if stripped.lower().startswith("character\t") or stripped.lower().startswith(
            "character "
        ):
            parsed = _parse_character(stripped)
            if parsed:
                current.characters.append(parsed)
                last_character = parsed
            else:
                last_character = None
            continue

        if stripped.lower().startswith("unit") and last_character is not None:
            last_character["units"] = int(last_character.get("units", 0)) + 1

    return StartPosition(regions=regions, factions=factions)


@lru_cache(maxsize=4)
def load_start_position(data_dir: Path | None = None) -> StartPosition | None:
    """Read and join the campaign's setup files. Returns None if the install is absent.

    Cached because the answer cannot change while the game is installed, and the
    settlement scan walks every pixel of the region map.
    """
    root = data_dir or game_data_dir()
    if root is None:
        _LOGGER.warning("Rome data directory not found — cannot seed belief from setup")
        return None

    strat_path = root / _STRAT_SUFFIX
    regions_path = root / _REGIONS_SUFFIX
    if not strat_path.is_file() or not regions_path.is_file():
        _LOGGER.warning("campaign setup files missing under %s", root)
        return None

    regions = parse_regions(regions_path.read_text(encoding="utf-8", errors="replace"))
    for key, (x, y) in locate_settlements(regions, root / _REGION_MAP_SUFFIX).items():
        regions[key] = regions[key].located(x, y)

    return parse_start_position(
        strat_path.read_text(encoding="utf-8", errors="replace"), regions
    )


#: How far from a settlement it holds a faction is taken to be able to see, in
#: map units. Arretium to Segesta is about 9, to Rome about 10, to Capua about
#: 16; Tarentum is 27 and Lilybaeum 32. Twenty therefore draws roughly the
#: neighbourhood a Julii player can see on turn 1 and stops at the horizon.
DEFAULT_SIGHT: float = 20.0


def seed_belief(
    store: BeliefStore,
    start: StartPosition,
    *,
    player_faction: str,
    sight: float = DEFAULT_SIGHT,
) -> int:
    """Write the opening position into belief, without handing over the whole map.

    The setup files describe every faction, which is far more than a player may
    know: Rome shrouds the map at the start, and a director that could see
    Alexandria on turn 1 would be cheating rather than playing.

    So two things are seeded. Everything belonging to the player, which they
    genuinely have. And other factions' settlements within `sight` of somewhere
    the player holds — for the Julii that is Segesta, Patavium and Mediolanium to
    the north, with Rome and Capua below, and nothing further.

    Distance is the test rather than Rome's own region grouping, which looked
    like the obvious answer and is not: the tag is a list, Latium carries
    `rome, italy` so Rome fell out of a plain match, and Laconia carries
    `sparta, italy`, which would have handed the Julii sight of Sparta.

    Everything beyond the horizon stays unknown until something observes it.
    These are marked `believed_present` rather than `observed_present`, because
    we read them rather than saw them, and they age like any other belief.

    Returns the number of entities written.
    """
    strat_name = strat_faction_name(player_faction)
    own = start.factions.get(strat_name)
    if own is None:
        _LOGGER.warning("no faction %r in the campaign setup", strat_name)
        return 0

    home: list[tuple[int, int]] = []
    for entry in own.settlements:
        region = start.regions.get(str(entry.get("region") or ""))
        if region is not None and region.x is not None and region.y is not None:
            home.append((region.x, region.y))

    def within_sight(region: Region) -> bool:
        if region.x is None or region.y is None:
            return False
        return any(
            (region.x - hx) ** 2 + (region.y - hy) ** 2 <= sight**2 for hx, hy in home
        )

    written = 0

    def write_settlement(faction: str, entry: dict[str, object]) -> None:
        nonlocal written
        region = start.regions.get(str(entry.get("region") or ""))
        if region is None:
            return
        population = entry.get("population")
        store.update(
            Settlement(
                entity_id=region.settlement.lower(),
                provenance=SETUP_PROVENANCE,
                confidence=1.0,
                existence=ExistenceStatus.BELIEVED_PRESENT,
                region=region.key,
                owner=faction,
                x=float(region.x if region.x is not None else 0),
                y=float(region.y if region.y is not None else 0),
                population=int(population) if isinstance(population, int) else None,
                attributes={"level": entry.get("level") or ""},
            )
        )
        written += 1

    for entry in own.settlements:
        write_settlement(strat_name, entry)

    for faction_name, faction in start.factions.items():
        if faction_name == strat_name:
            continue
        for entry in faction.settlements:
            region = start.regions.get(str(entry.get("region") or ""))
            if region is not None and within_sight(region):
                write_settlement(faction_name, entry)

    for entry in own.characters:
        slug = str(entry["name"]).lower().replace(" ", "_")
        store.update(
            Character(
                entity_id=slug,
                provenance=SETUP_PROVENANCE,
                confidence=1.0,
                existence=ExistenceStatus.BELIEVED_PRESENT,
                name=str(entry["name"]),
                faction=strat_name,
                x=float(entry["x"]),
                y=float(entry["y"]),
                role=str(entry["role"]),
            )
        )
        written += 1

        units = int(entry.get("units") or 0)
        if units:
            store.update(
                Army(
                    entity_id=f"{slug}_army",
                    provenance=SETUP_PROVENANCE,
                    confidence=1.0,
                    existence=ExistenceStatus.BELIEVED_PRESENT,
                    faction=strat_name,
                    x=float(entry["x"]),
                    y=float(entry["y"]),
                    strength=float(units),
                    general=str(entry["name"]),
                )
            )
            written += 1

    return written


def seed_belief_from_setup(
    store: BeliefStore, *, player_faction: str, data_dir: Path | None = None
) -> int:
    """Convenience: load the setup files and seed, or do nothing if absent."""
    start = load_start_position(data_dir)
    if start is None:
        return 0
    return seed_belief(store, start, player_faction=player_faction)
