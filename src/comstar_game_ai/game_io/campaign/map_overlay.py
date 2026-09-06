"""The campaign map overlay: twelve layer buttons and two docked legends.

Opened from the eye-and-scroll disc at the top-right of the HUD, or Tab. It is not
a parchment dialog — it replaces the 3D map with a framed strategic view — so there
is no close X. Escape leaves it, and clicking the eye again toggles it off. Both
were confirmed against a live campaign.

The twelve buttons along the bottom edge are two different kinds of control.
The shape of the indicator *is* the kind:

* **Square = checkbox.** Independent on/off for a feature layer. Several can be
  on at once, so Settlements and Armies can both draw. Clicking the *icon* shows
  that layer's legend; ticking the *box* toggles whether it is drawn.
* **Round = radio.** Exclusive view switch. Selecting Diplomacy replaces the
  Factions colouring; it does not add a second layer on top. Only one radio is
  selected at a time, which is why later clicks in the walk kept showing the
  Activity legend — each one selected a different view, and the last one won.

Treating a radio as a checkbox (or the reverse) is how an agent would think a
click did nothing, or would turn off a view it meant to keep.

`Alt+click` on any of them opens the Steam wiki overlay — the same hazard as F1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LayerKind(Enum):
    #: Square indicator. Independent on/off; several may be drawn together.
    CHECKBOX = "checkbox"
    #: Round indicator. Exclusive view; selecting one deselects the others.
    RADIO = "radio"


@dataclass(frozen=True)
class OverlayLayer:
    id: str
    kind: LayerKind
    #: Normalised centre of the *icon*, not the checkbox or radio beside it.
    centre: tuple[float, float]
    legend_title: str
    what_it_shows: str
    note: str = ""


#: Measured by hovering and clicking each icon on a 1920x1080 overlay frame.
#: y is the shared button row; x was walked left-to-right until each tooltip fired.
LAYERS: tuple[OverlayLayer, ...] = (
    OverlayLayer(
        id="settlements",
        kind=LayerKind.CHECKBOX,
        centre=(0.2710, 0.952),
        legend_title="SETTLEMENTS Legend",
        what_it_shows=(
            "Settlement tiers, alerts, and the three activity states: recruiting or "
            "constructing, upgrade possible, settlement idle"
        ),
        note="Ticked by default. Idle is the cheapest read of which of our towns needs orders.",
    ),
    OverlayLayer(
        id="armies",
        kind=LayerKind.CHECKBOX,
        centre=(0.3075, 0.952),
        legend_title="ARMIES Legend",
        what_it_shows=(
            "Movement remaining (four greens/white), army strength (five shield fills), "
            "in-settlement vs in-field filters, plus ally/enemy/neutral colouring"
        ),
    ),
    OverlayLayer(
        id="agents",
        kind=LayerKind.CHECKBOX,
        centre=(0.3440, 0.952),
        legend_title="AGENTS Legend",
        what_it_shows=(
            "The same movement-remaining scale, then filters for diplomats, merchants, "
            "spies and assassins, plus ally/enemy/neutral colouring"
        ),
    ),
    OverlayLayer(
        id="fortifications",
        kind=LayerKind.CHECKBOX,
        centre=(0.3805, 0.952),
        legend_title="FORTIFICATIONS Legend",
        what_it_shows="Watchtowers, forts, choke points and alerts, plus ally/enemy/neutral colouring",
    ),
    OverlayLayer(
        id="trade_routes",
        kind=LayerKind.CHECKBOX,
        centre=(0.4170, 0.952),
        legend_title="",
        what_it_shows="Trade-route / merchant layer (coins-and-banner icon)",
        note=(
            "Clicked during the walk but the left legend did not switch off Fortifications, "
            "so the title is unconfirmed. The tooltip on the neighbouring goods button "
            "is not this one."
        ),
    ),
    OverlayLayer(
        id="trade_goods",
        kind=LayerKind.CHECKBOX,
        centre=(0.4535, 0.952),
        legend_title="TRADE GOODS Legend",
        what_it_shows=(
            "Resources grouped by tier, each tier independently tickable: pottery, "
            "textiles, wild animals, hides, tin, lead; timber, iron, olive oil, wine, "
            "slaves, copper; grain and further goods below a scrollbar"
        ),
    ),
    OverlayLayer(
        id="factions",
        kind=LayerKind.RADIO,
        centre=(0.4900, 0.952),
        legend_title="FACTIONS Legend",
        what_it_shows="One colour per met faction — the palette settlements.FACTION_LEGEND_COLOURS samples",
        note="On by default with Settlements. Tooltip: 'View Factions overlay'.",
    ),
    OverlayLayer(
        id="diplomacy",
        kind=LayerKind.RADIO,
        centre=(0.5265, 0.952),
        legend_title="DIPLOMACY Legend",
        what_it_shows=(
            "Six standings, richer than a hover tooltip: Player, Ally, Ally of Ally, "
            "Neutral, Enemy, Ally of Enemy"
        ),
        note=(
            "The two extra states — ally-of-ally and ally-of-enemy — exist only here. "
            "A hover on a settlement never says them."
        ),
    ),
    OverlayLayer(
        id="activity",
        kind=LayerKind.RADIO,
        centre=(0.5630, 0.952),
        legend_title="ACTIVITY Legend",
        what_it_shows=(
            "A Bad→Good colour scale over four independently-tickable topics: Farming, "
            "Culture, Military, Trade"
        ),
    ),
    OverlayLayer(
        id="public_order",
        kind=LayerKind.RADIO,
        centre=(0.5995, 0.952),
        legend_title="ACTIVITY Legend",
        what_it_shows="Same Activity legend in the captures; mask icon, suspected public-order colouring",
        note="Click landed on Activity. Title reserved until a distinct legend is captured.",
    ),
    OverlayLayer(
        id="wealth",
        kind=LayerKind.RADIO,
        centre=(0.6360, 0.952),
        legend_title="ACTIVITY Legend",
        what_it_shows="Same Activity legend in the captures; pickaxe-and-wheat icon",
        note="Click landed on Activity. Title reserved until a distinct legend is captured.",
    ),
    OverlayLayer(
        id="military",
        kind=LayerKind.RADIO,
        centre=(0.6725, 0.952),
        legend_title="ACTIVITY Legend",
        what_it_shows="Same Activity legend in the captures; shield-and-sword icon",
        note="Click landed on Activity. Title reserved until a distinct legend is captured.",
    ),
)

BY_ID: dict[str, OverlayLayer] = {layer.id: layer for layer in LAYERS}


def checkboxes() -> tuple[OverlayLayer, ...]:
    """Feature layers that can be on together."""
    return tuple(layer for layer in LAYERS if layer.kind is LayerKind.CHECKBOX)


def radios() -> tuple[OverlayLayer, ...]:
    """Mutually exclusive views. Selecting one replaces the previous."""
    return tuple(layer for layer in LAYERS if layer.kind is LayerKind.RADIO)
