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

For attack safety, a selected general is not enough evidence that the whole stack is
selected: a map click on the general model can narrow selection to the bodyguard.
Reacquire via Lists → Military Forces → locate and confirm multiple unit cards before
issuing an attack order.
"""

from __future__ import annotations
from collections.abc import Sequence

from dataclasses import dataclass
from typing import TYPE_CHECKING

from comstar_game_ai.game_io.campaign import construction

if TYPE_CHECKING:
    from PIL import Image


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
MIN_SAFE_ATTACK_UNITS = 2

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


def attack_requires_full_stack(selected_units: int, *, minimum_units: int = MIN_SAFE_ATTACK_UNITS) -> bool:
    """Require at least two selected unit cards before attacking.

    A general alone can move and fight, but unattended campaign logic should not send
    the bodyguard in by itself because a map reselect silently narrowed the selection.
    """
    return selected_units >= max(1, int(minimum_units))


def count_selected_unit_cards(image: Image.Image) -> int:
    """Count visible selected-army unit cards in the bottom HUD.

    The measured army HUD keeps the selected stack's unit cards in the bottom-centre
    strip. Cards are warm parchment with dark separators between them, so a 1-D density
    scan is enough to estimate how many are present without OCR.
    """
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    strip = rgb[int(height * 0.84) : int(height * 0.96), int(width * 0.25) : int(width * 0.73)]
    if strip.size == 0:
        return 0

    r = strip[:, :, 0].astype(np.int16)
    g = strip[:, :, 1].astype(np.int16)
    b = strip[:, :, 2].astype(np.int16)
    parchment = (r >= 140) & (g >= 105) & (b >= 60) & (r >= g) & (g >= b)
    dense_cols = parchment.mean(axis=0) >= 0.22
    runs = _true_runs(dense_cols)
    return sum(1 for start, end in runs if end - start >= 12)


def attack_safe_stack_selected(image: Image.Image, *, minimum_units: int = MIN_SAFE_ATTACK_UNITS) -> bool:
    """Whether the screenshot shows enough selected unit cards for a safe attack."""
    return attack_requires_full_stack(
        count_selected_unit_cards(image),
        minimum_units=minimum_units,
    )


def _true_runs(values: Sequence[bool]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for idx, value in enumerate(values):
        if value and start is None:
            start = idx
        elif not value and start is not None:
            runs.append((start, idx))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs
