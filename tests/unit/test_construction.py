"""Tests for owned-settlement construction, recruitment, and unlocks."""

from __future__ import annotations

import itertools

from comstar_game_ai.game_io.campaign.construction import (
    BROWSER_CLOSE_X,
    BROWSER_OPEN,
    BROWSER_TOP,
    BY_BUILDING,
    BY_CONTROL,
    CONSTRUCT_FOOTER,
    CONSTRUCTION_HELP,
    CONTROLS,
    JULII_UNLOCKS,
    POPULATION_THRESHOLDS,
    RECRUIT_FOOTER,
    agent_unlocks,
    mutating_controls,
)
from comstar_game_ai.game_io.campaign.ui_atlas import BY_ID, match_geometry


def test_ids_are_unique():
    assert len(BY_CONTROL) == len(CONTROLS)
    assert len(BY_BUILDING) == len(JULII_UNLOCKS)


def test_footer_discs_sit_left_of_end_turn():
    assert RECRUIT_FOOTER[0] < CONSTRUCT_FOOTER[0] < BROWSER_OPEN[0] < 0.980
    assert all(control.centre[1] == 0.968 for control in CONTROLS)


def test_neighbouring_controls_do_not_share_a_centre():
    for a, b in itertools.combinations(CONTROLS, 2):
        assert a.centre != b.centre


def test_card_docks_are_named_as_hazards():
    hazards = {control.id for control in mutating_controls()}
    assert hazards == {"recruit_footer", "construct_footer"}
    assert "spend" in BY_CONTROL["construct_footer"].hazard.lower()
    assert "spend" in BY_CONTROL["recruit_footer"].hazard.lower()


def test_browser_close_is_not_the_overview_x():
    assert BROWSER_CLOSE_X == BY_ID["building_browser"].geometry.close_x
    assert BROWSER_CLOSE_X != BY_ID["faction_summary"].geometry.close_x
    assert BROWSER_TOP < BY_ID["character_scroll"].geometry.top


def test_browser_match_still_uses_the_atlas_edges():
    assert match_geometry(0.26, 0.74, 0.21).entry.id == "building_browser"


def test_construction_help_is_the_shipped_string():
    assert "queue" in CONSTRUCTION_HELP.lower()
    assert "right click" in CONSTRUCTION_HELP.lower()


def test_population_thresholds_match_the_browser_header():
    by_name = dict(POPULATION_THRESHOLDS)
    assert by_name["Large town"] == 2000
    assert by_name["Minor city"] == 6000
    assert by_name["Huge city"] == 24000


def test_julii_agent_unlocks_come_from_the_edb():
    agents = {item.building: item.trains for item in agent_unlocks()}
    assert "Diplomat" in agents["Governor's Villa"]
    assert "Spy" in agents["Market"]
    assert "Assassin" in agents["Forum"]
    assert "Spy" not in BY_BUILDING["Trader"].trains


def test_live_arretium_notes_do_not_invent_a_spy():
    assert "no spy" in BY_BUILDING["Trader"].live.lower()
    assert "no spy" in BY_BUILDING["Market"].live.lower()
    assert "Diplomat" in BY_BUILDING["Governor's Villa"].live


def test_atlas_browser_opener_is_no_longer_a_stray_click():
    opened = BY_ID["building_browser"].opened_by.lower()
    assert "tree disc" in opened
    assert "stray" not in opened
    assert "escape" in BY_ID["building_browser"].note.lower()
