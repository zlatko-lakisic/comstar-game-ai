"""The campaign's own setup files, read as belief.

These run on parsed text rather than the installed game, so they say what the
parser does rather than whether Rome is on this machine. The one thing they
cannot check offline is the settlement coordinates, which come from the region
map; `test_start_position_live.py` does that against the real install.
"""

from __future__ import annotations

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.campaign.start_position import (
    Region,
    parse_regions,
    parse_start_position,
    seed_belief,
    strat_faction_name,
)

REGIONS_TEXT = """\
;
; regions list
;
Etruria
\tArretium
\tmacedon
\tEtruscans
\t157 198 13
\titaly
\t5
\t7
Umbria
\tAriminum
\tmacedon
\tUmbrians
\t198 43 13
\titaly
\t5
\t4
Liguria
\tSegesta
\tgauls
\tLigurians
\t157 13 198
\titaly
\t5
\t4
Latium
\tRome
\tmacedon
\tLatins
\t52 13 198
\trome, italy
\t5
\t7
Aegyptus_Superior
\tThebes
\tegypt
\tEgyptians
\t99 12 40
\tnone
\t5
\t7
"""

STRAT_TEXT = """\
campaign imperial_campaign
playable
\tromans_julii
\tromans_brutii
end

faction\tromans_julii, comfortable_caesar
superfaction romans_senate
denari\t5000
settlement
{
\tlevel large_town
\tregion Etruria

\tyear_founded 0
\tpopulation 4000
\tbuilding
\t{
\t\ttype barracks militia_barracks
\t}
}

settlement
{
\tlevel large_town
\tregion Umbria
\tpopulation 3500
}

character\tFlavius Julius, named character, leader, age 47, , x 89, y 82
traits GoodCommander 2
army
unit\t\troman generals guard cavalry early\texp 1 armour 0 weapon_lvl 0
unit\t\troman hastati\texp 1 armour 0 weapon_lvl 0

character\tSextus Antio, diplomat, age 29, , x 93, y 78
traits GoodDiplomat 3

faction\tslave, balanced_smith
settlement
{
\tlevel town
\tregion Liguria
\tpopulation 900
}

faction\tegypt, religious_caesar
settlement
{
\tlevel huge_city
\tregion Aegyptus_Superior
\tpopulation 12000
}

faction_relationships\tromans_julii, romans_brutii
faction_relationships\tslave, egypt
"""


def located_regions() -> dict[str, Region]:
    """The parsed regions, with the coordinates the region map would supply."""
    regions = parse_regions(REGIONS_TEXT)
    positions = {
        "Etruria": (91, 80),
        "Umbria": (96, 82),
        "Liguria": (83, 84),
        "Latium": (95, 71),
        "Aegyptus_Superior": (181, 12),
    }
    return {key: region.located(*positions[key]) for key, region in regions.items()}


def test_regions_carry_their_settlement_and_group():
    regions = parse_regions(REGIONS_TEXT)

    assert regions["Etruria"].settlement == "Arretium"
    assert regions["Etruria"].colour == (157, 198, 13)
    assert regions["Etruria"].group == "italy"
    assert regions["Aegyptus_Superior"].settlement == "Thebes"


def test_a_faction_keeps_its_settlements_and_characters():
    start = parse_start_position(STRAT_TEXT, located_regions())
    julii = start.factions["romans_julii"]

    assert [s["region"] for s in julii.settlements] == ["Etruria", "Umbria"]
    assert julii.settlements[0]["population"] == 4000
    assert julii.settlements[0]["level"] == "large_town"
    assert [c["name"] for c in julii.characters] == ["Flavius Julius", "Sextus Antio"]


def test_a_relationship_line_is_not_a_faction():
    """The bug that emptied the file: `faction_relationships` starts with `faction`.

    Twenty-nine of those sit at column zero further down `descr_strat.txt`, each
    naming a faction. Matching on the prefix replaced every faction's parsed
    position with a fresh empty record, and the parse came back saying the
    campaign had no settlements and no characters anywhere.
    """
    start = parse_start_position(STRAT_TEXT, located_regions())

    assert start.factions["romans_julii"].settlements, "a relationship line emptied the faction"
    assert "faction_relationships" not in start.factions


def test_a_character_carries_its_post_and_position():
    start = parse_start_position(STRAT_TEXT, located_regions())
    flavius, sextus = start.factions["romans_julii"].characters

    assert (flavius["role"], flavius["x"], flavius["y"]) == ("leader", 89, 82)
    assert flavius["units"] == 2, "the units standing with him are his army"
    assert (sextus["role"], sextus["units"]) == ("diplomat", 0)


def test_the_player_gets_everything_of_their_own():
    store = BeliefStore()
    seed_belief(
        store, parse_start_position(STRAT_TEXT, located_regions()), player_faction="julii"
    )

    own = {s.entity_id for s in store.get_settlements() if "julii" in s.owner}
    assert own == {"arretium", "ariminum"}
    assert {c.name for c in store.get_characters()} == {"Flavius Julius", "Sextus Antio"}
    assert [a.general for a in store.get_armies()] == ["Flavius Julius"], (
        "a diplomat travels alone and should not appear as an army"
    )


def test_a_neighbour_is_seeded_and_the_far_side_of_the_map_is_not():
    """Fog: reading the setup files must not turn into seeing everything.

    Segesta is nine map units from Arretium and a Julii player can see it on turn
    one. Thebes is the other end of the Mediterranean and they cannot.
    """
    store = BeliefStore()
    seed_belief(
        store, parse_start_position(STRAT_TEXT, located_regions()), player_faction="julii"
    )

    seen = {s.entity_id for s in store.get_settlements()}
    assert "segesta" in seen
    assert "thebes" not in seen


def test_what_we_read_is_not_recorded_as_what_we_saw():
    store = BeliefStore()
    seed_belief(
        store, parse_start_position(STRAT_TEXT, located_regions()), player_faction="julii"
    )

    assert all(s.provenance == "campaign_setup" for s in store.get_settlements())
    assert all(s.existence.value == "believed_present" for s in store.get_settlements())


def test_sight_is_measured_from_every_town_the_player_holds():
    """Reach grows with the empire, so the horizon is per-settlement, not one centre."""
    store = BeliefStore()
    seed_belief(
        store,
        parse_start_position(STRAT_TEXT, located_regions()),
        player_faction="julii",
        sight=1.0,
    )

    assert {s.entity_id for s in store.get_settlements()} == {"arretium", "ariminum"}, (
        "with no sight at all, only what the player owns should be known"
    )


def test_the_house_name_becomes_the_name_the_strat_file_uses():
    assert strat_faction_name("julii") == "romans_julii"
    assert strat_faction_name("Brutii") == "romans_brutii"
    assert strat_faction_name("egypt") == "egypt"
