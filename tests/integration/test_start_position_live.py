"""The setup parser against the installed game.

Skipped where Rome is not installed. What these check is the one thing the
offline tests cannot: that the settlement coordinates read out of
`map_regions.tga` are real positions on Rome's map rather than plausible numbers.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.campaign.start_position import (
    game_data_dir,
    load_start_position,
    seed_belief,
)

pytestmark = pytest.mark.skipif(
    game_data_dir() is None, reason="Rome: Total War Remastered is not installed here"
)


@pytest.fixture(scope="module")
def start():
    position = load_start_position()
    assert position is not None
    return position


def test_every_region_has_a_settlement_on_the_map(start):
    located = [r for r in start.regions.values() if r.x is not None]

    assert len(start.regions) == 103
    assert len(located) == 103, "a region whose settlement we could not find on the map"


def test_the_settlements_land_on_the_generals_who_start_in_them(start):
    """The check that makes the coordinates trustworthy rather than merely plausible.

    Character positions are written down in `descr_strat.txt`; settlement
    positions are not, and are read back from the region map. Lucius Julius
    begins in Arretium and Quintus in Ariminum, so if the two sources agree to
    the pixel, the map has been read in Rome's own coordinate system — including
    the vertical flip, which is the easy thing to get backwards and the hard
    thing to notice.
    """
    julii = start.factions["romans_julii"]
    at = {c["name"]: (c["x"], c["y"]) for c in julii.characters}
    arretium = start.region_of_settlement("Arretium")
    ariminum = start.region_of_settlement("Ariminum")

    assert at["Lucius Julius"] == (arretium.x, arretium.y)
    assert at["Quintus Julius"] == (ariminum.x, ariminum.y)


def test_the_julii_open_where_the_campaign_says_they_do(start):
    julii = start.factions["romans_julii"]

    assert [s["region"] for s in julii.settlements] == ["Etruria", "Umbria"]
    assert {c["name"] for c in julii.characters} >= {
        "Flavius Julius",
        "Lucius Julius",
        "Vibius Julius",
    }


def test_the_opening_belief_is_a_neighbourhood_not_the_world(start):
    store = BeliefStore()
    seed_belief(store, start, player_faction="julii")

    seen = {s.entity_id for s in store.get_settlements()}
    assert {"arretium", "ariminum"} <= seen, "the player's own towns"
    assert {"segesta", "patavium", "mediolanium", "rome"} <= seen, "northern Italy"
    assert not {"thebes", "alexandria", "carthage", "londinium"} & seen, (
        "seeded a settlement the Julii cannot see on turn 1"
    )
