"""Selected armies: Lists, HUD, family tree, field construction, and map orders.

Lists → Military Forces (Ctrl+5, sub-tab at (0.50, 0.259)) names every stack.
Hover a row for stack upkeep. Double-click, or the locate disc at (0.72, 0.52),
frames the army and closes Lists. Do not use the Settlements footer 3 (capital).

The general HUD is not the agent HUD. The silhouette at (0.120, 0.960) is
Family Tree — 'Your faction's lineage with an option to set the faction heir'.
Opening the tab is a read. Clicking a character sets the heir. Official unit
details for a bodyguard are `TMT_SHOW_GENERAL_UNIT_DETAILS`; agents use the
gray `TMT_NO_BODYGUARD_UNIT_TO_VIEW`.

Field construction is the same Construction <6> disc as town building. With a
named general on own land, not in a town, it opens a right-edge dock titled
FIELD CONSTRUCTION: watchtower left (200), fort right (500). A card click
spends. Official reject strings are `TMT_FIELD_CONSTRUCTION_TEST_*` (no
general, not named, sea, enemy land, invalid tile, not enough money, sieging).
The Mercenaries grid sits under that dock; it was empty in Etruria this turn.

Map orders: select the character, park on the target until the cursor glyph
changes (sword for an army attack), then left-click. The 2004
`cursor_action_tooltips` still say 'Right click to …'; Remastered issues the
order on that left-click. A nameplate click before the sword appears selects
the settlement — Enemy SEGESTA Village this turn — instead of attacking.
Town attack is a siege. A field-army click is Battle Deployment (Phase 5).
Do not click a Gallic stack: that would declare war.
"""

from __future__ import annotations

from dataclasses import dataclass

from comstar_game_ai.game_io.campaign import construction


@dataclass(frozen=True)
class HudControl:
    id: str
    centre: tuple[float, float]
    purpose: str
    hazard: str = ""


LISTS_MILITARY_TAB = (0.50, 0.259)
LISTS_LOCATE = (0.72, 0.52)
FAMILY_TREE = (0.120, 0.960)

#: Same footer disc as settlement construction. Context decides the dock.
FIELD_CONSTRUCTION_OPEN = construction.CONSTRUCT_FOOTER
WATCHTOWER_CARD = (0.865, 0.605)
FORT_CARD = (0.925, 0.605)
FIELD_CONSTRUCTION_CLOSE_X = (0.830, 0.419)

#: Shipped strings. Live Remastered spends on left-click once the glyph shows.
MAP_ORDER_BUTTON = "left"
MAP_ORDER_TELL = "cursor_glyph"
ATTACK_CURSOR = "sword"

CONTROLS: tuple[HudControl, ...] = (
    HudControl(
        id="family_tree",
        centre=FAMILY_TREE,
        purpose=(
            "Silhouette on the selected-general HUD. Tooltip: Family Tree — "
            "lineage with an option to set the faction heir."
        ),
        hazard="Do not click a character in the tree. That sets the heir.",
    ),
    HudControl(
        id="field_construction",
        centre=FIELD_CONSTRUCTION_OPEN,
        purpose=(
            "Construction <6> disc. With a named general on own land this opens "
            "FIELD CONSTRUCTION (watchtower / fort), not the town building dock."
        ),
        hazard="A click on a watchtower or fort card spends 200 or 500.",
    ),
    HudControl(
        id="watchtower",
        centre=WATCHTOWER_CARD,
        purpose="Left FIELD CONSTRUCTION card. descr cost 200. Extends LOS.",
        hazard="Spends immediately. Needs own land, named general, not sieging.",
    ),
    HudControl(
        id="fort",
        centre=FORT_CARD,
        purpose="Right FIELD CONSTRUCTION card. descr cost 500. Empty forts vanish in 1 turn.",
        hazard="Spends immediately. Do not leave a new fort empty.",
    ),
)

BY_CONTROL: dict[str, HudControl] = {control.id: control for control in CONTROLS}


def mutating_controls() -> tuple[HudControl, ...]:
    return tuple(control for control in CONTROLS if control.hazard)
