"""Tests for the selected-agent HUD (range, send lists, character scroll)."""

from __future__ import annotations

import itertools

from comstar_game_ai.game_io.campaign.agents import (
    BY_CONTROL,
    BY_KIND,
    CHARACTER_SCROLL_CLOSE_X,
    CHARACTER_SCROLL_TOP,
    CONTROLS,
    KINDS,
    SEND_DISTANCE_READ,
    mutating_controls,
    seen_kinds,
)
from comstar_game_ai.game_io.campaign.ui_atlas import BY_ID, OVERVIEW_FRAME, match_geometry


def test_ids_are_unique():
    assert len(BY_KIND) == len(KINDS)
    assert len(BY_CONTROL) == len(CONTROLS)


def test_seen_kinds_keep_the_titles_read_off_the_screen():
    assert [kind.id for kind in seen_kinds()] == ["diplomat", "spy"]
    assert BY_KIND["diplomat"].send_title == "SEND EMISSARY"
    assert BY_KIND["diplomat"].send_verb == "Negotiate with"
    assert BY_KIND["spy"].send_title == "SEND SPY"
    assert BY_KIND["spy"].send_verb == "Spy on"


def test_assassin_send_title_is_not_invented():
    assert BY_KIND["assassin"].send_title == ""
    assert BY_KIND["assassin"].send_verb == "Assassinate"


def test_mutating_controls_are_named_as_hazards():
    hazards = {control.id for control in mutating_controls()}
    assert {"traits_followers", "left_third", "disband", "send_hub", "send_confirm", "assign_mission"} <= hazards
    assert "wiki" in BY_CONTROL["traits_followers"].hazard.lower()
    assert "delete" in BY_CONTROL["disband"].hazard.lower()
    assert "confirm" in BY_CONTROL["send_hub"].hazard.lower()


def test_neighbouring_controls_do_not_share_a_centre():
    for a, b in itertools.combinations(CONTROLS, 2):
        assert a.centre != b.centre


def test_character_scroll_is_not_an_overview_tab():
    scroll = BY_ID["character_scroll"]
    assert scroll.tab_of == ""
    assert scroll.requires
    assert CHARACTER_SCROLL_TOP > OVERVIEW_FRAME.top
    assert CHARACTER_SCROLL_CLOSE_X != OVERVIEW_FRAME.close_x


def test_character_scroll_matches_its_measured_edges():
    match = match_geometry(0.256, 0.743, 0.261)
    assert match is not None
    assert match.entry.id == "character_scroll"


def test_character_scroll_is_not_the_building_browser():
    assert match_geometry(0.26, 0.74, 0.21).entry.id == "building_browser"
    assert match_geometry(0.256, 0.743, 0.261).entry.id == "character_scroll"


def test_send_distance_is_the_turn_glyph_not_the_map():
    assert SEND_DISTANCE_READ == "turn_glyph"


def test_agent_hub_note_separates_the_map_list_from_confirm():
    note = BY_ID["agent_hub"].note.lower()
    assert "confirm" in note
    assert "send emissary" in note
    assert "end turn" in note
