"""Tests for army HUD, field construction, and map-order rules."""

from __future__ import annotations

import itertools

from comstar_game_ai.game_io.campaign.army import (
    ATTACK_CURSOR,
    BY_CONTROL,
    CONTROLS,
    FAMILY_TREE,
    FIELD_CONSTRUCTION_OPEN,
    LISTS_LOCATE,
    LISTS_MILITARY_TAB,
    MAP_ORDER_BUTTON,
    MAP_ORDER_TELL,
    mutating_controls,
)
from comstar_game_ai.game_io.campaign.construction import CONSTRUCT_FOOTER
from comstar_game_ai.game_io.campaign.ui_atlas import BY_ID


def test_ids_are_unique():
    assert len(BY_CONTROL) == len(CONTROLS)


def test_neighbouring_controls_do_not_share_a_centre():
    for a, b in itertools.combinations(CONTROLS, 2):
        assert a.centre != b.centre


def test_field_construction_reuses_the_town_construct_disc():
    assert FIELD_CONSTRUCTION_OPEN == CONSTRUCT_FOOTER
    assert "spend" in BY_CONTROL["watchtower"].hazard.lower()
    assert "spend" in BY_CONTROL["fort"].hazard.lower()


def test_family_tree_is_named_as_a_succession_hazard():
    assert FAMILY_TREE == (0.120, 0.960)
    assert "heir" in BY_CONTROL["family_tree"].hazard.lower()


def test_map_orders_wait_for_the_cursor_glyph():
    assert MAP_ORDER_BUTTON == "left"
    assert MAP_ORDER_TELL == "cursor_glyph"
    assert ATTACK_CURSOR == "sword"


def test_lists_military_is_not_the_capital_button():
    assert LISTS_MILITARY_TAB[1] == 0.259
    assert LISTS_LOCATE != (0.72, 0.90)


def test_atlas_field_construction_is_the_select_string():
    entry = BY_ID["field_construction"]
    assert entry.name_key == "SMT_SELECT_FORT_OR_WATCHTOWER"
    assert "left-click" in entry.note.lower() or "left click" in entry.note.lower()


def test_every_army_hazard_is_listed():
    hazards = {control.id for control in mutating_controls()}
    assert hazards == {"family_tree", "field_construction", "watchtower", "fort"}
