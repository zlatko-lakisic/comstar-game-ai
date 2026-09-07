"""Tests for army HUD, field construction, and map-order rules."""

from __future__ import annotations

import itertools

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.army import (
    ATTACK_CURSOR,
    BY_CONTROL,
    CONTROLS,
    FAMILY_TREE,
    FIELD_CONSTRUCTION_OPEN,
    LISTS_LOCATE,
    LISTS_MILITARY_TAB,
    MIN_SAFE_ATTACK_UNITS,
    MAP_ORDER_BUTTON,
    MAP_ORDER_TELL,
    attack_requires_full_stack,
    attack_safe_stack_selected,
    count_selected_unit_cards,
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


def _army_hud_image(card_count: int) -> Image.Image:
    img = Image.new("RGB", (1920, 1080), (20, 40, 20))
    draw = ImageDraw.Draw(img)
    x0 = int(1920 * 0.25)
    y0 = int(1080 * 0.84)
    y1 = int(1080 * 0.96)
    card_w = 76
    gap = 10
    for i in range(card_count):
        left = x0 + i * (card_w + gap)
        right = left + card_w
        draw.rectangle((left, y0, right, y1), fill=(180, 140, 90))
    return img


def test_count_selected_unit_cards_detects_multiple_cards():
    assert count_selected_unit_cards(_army_hud_image(5)) == 5


def test_count_selected_unit_cards_detects_single_general_card():
    assert count_selected_unit_cards(_army_hud_image(1)) == 1


def test_attack_requires_full_stack_rejects_general_alone():
    assert MIN_SAFE_ATTACK_UNITS == 2
    assert not attack_requires_full_stack(1)
    assert attack_requires_full_stack(2)


def test_attack_safe_stack_selected_needs_more_than_one_card():
    assert not attack_safe_stack_selected(_army_hud_image(1))
    assert attack_safe_stack_selected(_army_hud_image(3))


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
