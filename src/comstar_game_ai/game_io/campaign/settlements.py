"""Telling settlements apart: who owns one, how we stand with them, what it says.

`ui_atlas` says what a panel is and `screen_regions` says where the furniture is.
Neither answers the question an agent actually has to answer every turn: of the
settlements on screen, which are mine, which belong to someone I am at war with,
and which one still needs orders.

Rome answers that three separate ways, and they were checked against each other
rather than trusted individually, because each has a failure mode the others do not:

* **The hover tooltip** is authoritative and self-describing. It names the owning
  faction in full and appends the standing in parentheses — `(At war)`, `(Neutral)`,
  `(Ally)` — with nothing appended for our own. It is the only source that cannot be
  confused by lighting or zoom, and the only one that needs no calibration. It costs
  a mouse move and a second of dwell per settlement.
* **The map label pill** is free: it is already on screen for every visible
  settlement, tinted by standing. It is a prefilter, never a verdict — see
  `LABEL_PILL_COLOURS` for why the obvious colour match gets it wrong.
* **The strategic overlay** (Tab) recolours every settlement icon at once and docks a
  legend that states the palette, so the key can be sampled from the same frame it
  decodes. It is the only source that reports *activity* — whether a settlement is
  building something, could be upgraded, or is sitting idle — which is the read that
  actually drives a build order. It also replaces the map, so no pixel heuristic
  calibrated on the normal map survives while it is up.

The trio was cross-validated on turn 1 of a Julii campaign: the Factions panel listed
Brutii, Scipii and S.P.Q.R. as allies and the Rebels as enemies; the overlay drew
those settlements light blue and orange respectively; and hovering Segesta, Patavium
and Rome returned `(At war)`, `(Neutral)` and `(Ally)` to match. Three sources
agreeing is what makes the palettes below safe to rely on.

One structural note about the strings. Where Rome's shipped tables carry the word, it
is stored as a key and resolved from the install so a localised copy stays correct.
Some of this text has no key, because Remastered added UI the 2004 tables predate —
the `(Ally)` suffix and all three overlay activity labels are in that group. Those
carry the observed English instead, and say so, rather than being given an invented
key that would look authoritative and resolve to nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from comstar_game_ai.game_io.campaign.rome_strings import StringTable, lookup

Tables = dict[str, StringTable]


def _text(key: str, observed: str, tables: Tables | None) -> str:
    """Resolve from the install when a key exists, else fall back to observed English."""
    if key and tables:
        found = lookup(tables, key)
        if found is not None:
            return found[1]
    return observed


class Tier(Enum):
    """Settlement size, smallest first.

    Rome's own keys, so a localised install resolves to its own words. Note that
    `ST_CITY` reads "Minor city": the key and the text disagree, which is exactly why
    entries here store keys and resolve late instead of hardcoding English.
    """

    VILLAGE = ("ST_VILLAGE", 0, "Village")
    TOWN = ("ST_TOWN", 1, "Town")
    LARGE_TOWN = ("ST_LARGE_TOWN", 2, "Large town")
    MINOR_CITY = ("ST_CITY", 3, "Minor city")
    LARGE_CITY = ("ST_LARGE_CITY", 4, "Large city")
    HUGE_CITY = ("ST_HUGE_CITY", 5, "Huge city")

    def __init__(self, name_key: str, rank: int, observed: str) -> None:
        self.name_key = name_key
        self.rank = rank
        self.observed = observed

    def label(self, tables: Tables | None = None) -> str:
        return _text(self.name_key, self.observed, tables)


class Relation(Enum):
    """How we stand with a settlement's owner.

    `suffix_key` is the string the tooltip appends in brackets after the tier.

    Two members deliberately have no key. `OURS` has none because our own settlements
    print only their tier and the *absence* of a suffix is the signal — Rome never
    needs to draw a word for it. `ALLY` has none because no shipped table contains the
    tooltip's "Ally": `SMT_ALLIES` reads "Allies", which is the overlay legend's
    heading and not this string, and the only exact match in the install is a
    battle-menu label in shouting caps. Using `SMT_ALLIES` here would resolve a
    localised install to the wrong word and silently stop matching allied settlements.
    """

    OURS = ("", "")
    ALLY = ("", "Ally")
    NEUTRAL = ("SMT_NEUTRAL", "Neutral")
    AT_WAR = ("SMT_AT_WAR", "At war")

    def __init__(self, suffix_key: str, observed: str) -> None:
        self.suffix_key = suffix_key
        self.observed = observed

    def suffix(self, tables: Tables | None = None) -> str:
        return _text(self.suffix_key, self.observed, tables)

    @property
    def localises(self) -> bool:
        """True when the install supplies this word, so it survives a localised copy."""
        return bool(self.suffix_key)

    @property
    def is_hostile(self) -> bool:
        return self is Relation.AT_WAR

    @property
    def is_ours(self) -> bool:
        return self is Relation.OURS


class Activity(Enum):
    """What one of our settlements is doing, as only the overlay reports it.

    No shipped table names these: they are Remastered additions and the values below
    are the observed English. `IDLE` is the one worth acting on — it means the
    settlement is building nothing and recruiting nothing, so it is a wasted turn of
    production, and it is the cheapest available read of "this one needs orders".
    """

    WORKING = "Recruiting or constructing"
    UPGRADEABLE = "Upgrade possible"
    IDLE = "Settlement idle"


#: Where to sample each legend swatch, normalised against the client rect. Both
#: legends dock to a screen edge, so these ride the edge across resolutions. Sampling
#: beats hardcoding: the swatch is drawn by the code that tints the icons, so a
#: sampled key cannot disagree with the map it is decoding, and a mod that recolours a
#: faction updates both at once. Found by scanning the swatch column on a 1920x1080
#: frame rather than eyeballed, after eyeballing put four of six rows on the wrong
#: swatch — see scripts/sample_overlay_legend.py.
OVERLAY_STATE_SWATCHES: dict[Activity | Relation, tuple[float, float]] = {
    Activity.WORKING: (0.0305, 0.7667),
    Activity.UPGRADEABLE: (0.0305, 0.8056),
    Activity.IDLE: (0.0305, 0.8444),
    Relation.ALLY: (0.0305, 0.9065),
    Relation.AT_WAR: (0.0305, 0.9454),
    Relation.NEUTRAL: (0.0305, 0.9843),
}

#: Measured from the docked legend on a 1920x1080 frame with the overlay up. These tint
#: the settlement *icons* on the overlay map. Our own settlements are tinted by activity
#: rather than by standing, which is why `Relation.OURS` is absent.
OVERLAY_STATE_COLOURS: dict[Activity | Relation, tuple[int, int, int]] = {
    Activity.WORKING: (49, 108, 76),
    Activity.UPGRADEABLE: (204, 228, 53),
    Activity.IDLE: (238, 237, 234),
    Relation.ALLY: (138, 193, 234),
    Relation.AT_WAR: (222, 92, 51),
    Relation.NEUTRAL: (223, 204, 116),
}

#: Faction fill colours, sampled from the overlay's right-hand legend. The legend lists
#: only factions already met, so read this per-frame rather than treating it as a fixed
#: table of every faction in the game.
#:
#: Two caveats, both found by trying it. Province *fill* on the map is blended with the
#: terrain underneath, so it reads darker and less saturated than the swatch and needs a
#: generous tolerance. And four of these — Carthage's white, the Rebels' taupe, the
#: Greek Cities' olive, Seleucid mauve — sit close enough to coastline, rock and grass
#: that matching them across a whole frame returns mostly false positives: on the radar,
#: Carthage claimed 611 pixels and the Rebels 1112, nearly all of them sea and terrain.
#: The saturated colours behave: Julii red matched 170 pixels of genuine territory.
FACTION_LEGEND_COLOURS: dict[str, tuple[int, int, int]] = {
    "The Greek Cities": (181, 177, 116),
    "Rebels": (143, 134, 109),
    "The House of Julii": (153, 18, 18),
    "S.P.Q.R.": (140, 74, 189),
    "The House of Scipii": (33, 88, 161),
    "The Seleucid Empire": (145, 119, 118),
    "The House of Brutii": (79, 125, 60),
    "Macedon": (0, 0, 0),
    "Egypt": (238, 237, 129),
    "Carthage": (236, 235, 232),
    "Gaul": (72, 177, 41),
}

#: Modal colour of the settlement label pill on the *normal* map, by standing.
#:
#: This is a prefilter and not a verdict, and the reason is worth stating because the
#: obvious implementation is wrong. The pill palette is related to the overlay legend
#: but not equal to it — labels are drawn over terrain with lighting, so they come out
#: darker. Matching a measured pill to the nearest legend swatch misclassified three of
#: four test settlements, putting both of our own cream pills and Gaul's amber one on
#: "neutral". What does separate them is the blue channel: ours sits near 140, neutral
#: near 59, at-war near 58 with red dominant. Use the tooltip to decide; use these to
#: pick which settlements are worth hovering.
LABEL_PILL_COLOURS: dict[Relation, tuple[int, int, int]] = {
    Relation.OURS: (205, 191, 140),
    Relation.NEUTRAL: (197, 165, 59),
    Relation.AT_WAR: (177, 66, 58),
}

#: Appended to the settlement's own name, not to the tier, when it is a faction capital.
CAPITAL_SUFFIX_KEY = "SMT_CAPITAL_TITLE"
CAPITAL_SUFFIX_OBSERVED = "Capital"

#: The tooltip line offering a double-click. It appears only on settlements we own,
#: because only ours have a details panel to open, which makes its presence a second
#: and independent read of ownership that needs no colour and no faction name.
OWNED_HINT = re.compile(r"x2\s+to\s+get\s+further\s+information", re.IGNORECASE)

_BRACKETED = re.compile(r"^(?P<head>.+?)\s*\(\s*(?P<inside>[^)]+?)\s*\)\s*$")


@dataclass(frozen=True)
class SettlementReading:
    """One settlement as its hover tooltip described it.

    The figures the tooltip shows against a coin, a crenellation and a growth glyph are
    deliberately kept as raw text. No shipped string names them, and the one guess worth
    making is wrong: the coin figure read 184 for a settlement whose Lists entry gave a
    population of 3500 and a turn income of 1710, so it is neither. The Lists panel
    labels its numbers, so read population, growth, public order and income from there.
    Naming them here would put unlabelled numbers into an agent's reasoning with a
    confident and false label attached.
    """

    name: str
    owner: str
    tier: Tier | None
    relation: Relation
    is_capital: bool = False
    #: True when the tooltip offered the double-click hint, i.e. the game will let us
    #: open this settlement's details, i.e. it is ours.
    manageable: bool = False
    figures: str = ""

    @property
    def owner_is_us(self) -> bool:
        return self.relation.is_ours


def parse_settlement_tooltip(
    text: str,
    *,
    tables: Tables | None = None,
) -> SettlementReading | None:
    """Read a settlement hover tooltip.

    The layout is three leading lines — name, owning faction, tier and standing — then
    a figures line, then hints. Returns None when fewer than three lines are present,
    because the same hover can land on a road or an army and produce a tooltip with a
    completely different shape; guessing a settlement out of those would be worse than
    declining. A three-line tooltip that is not a settlement still parses, but yields
    `tier=None`, which is the caller's cue that it did not find one.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return None

    name, owner, tier_line = lines[0], lines[1], lines[2]

    is_capital = False
    match = _BRACKETED.match(name)
    if match:
        capital = _text(CAPITAL_SUFFIX_KEY, CAPITAL_SUFFIX_OBSERVED, tables)
        if match.group("inside").casefold() == capital.casefold():
            name = match.group("head").strip()
            is_capital = True

    relation = Relation.OURS
    match = _BRACKETED.match(tier_line)
    if match:
        inside = match.group("inside").casefold()
        for candidate in (Relation.ALLY, Relation.NEUTRAL, Relation.AT_WAR):
            if candidate.suffix(tables).casefold() == inside:
                relation = candidate
                tier_line = match.group("head").strip()
                break

    tier = None
    for candidate in Tier:
        if candidate.label(tables).casefold() == tier_line.casefold():
            tier = candidate
            break

    return SettlementReading(
        name=name,
        owner=owner,
        tier=tier,
        relation=relation,
        is_capital=is_capital,
        manageable=bool(OWNED_HINT.search(text)),
        figures=lines[3] if len(lines) > 3 else "",
    )


def nearest(
    rgb: tuple[int, int, int],
    palette: dict,
    *,
    tolerance: int = 90,
):
    """Closest palette entry by Manhattan distance, or None past `tolerance`.

    Returning None rather than the least-bad guess is the point. A settlement icon
    half-covered by an army banner, or a swatch sampled a few pixels off, should read
    as "unknown, go and hover it" and not as a confident wrong standing.
    """
    best_key, best_distance = None, None
    for key, value in palette.items():
        distance = sum(abs(a - b) for a, b in zip(rgb, value))
        if best_distance is None or distance < best_distance:
            best_key, best_distance = key, distance
    if best_distance is None or best_distance > tolerance:
        return None
    return best_key
