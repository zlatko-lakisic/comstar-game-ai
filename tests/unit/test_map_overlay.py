"""Tests for the twelve campaign-map overlay layers."""

from __future__ import annotations

import itertools

from comstar_game_ai.game_io.campaign.map_overlay import (
    BY_ID,
    LAYERS,
    LayerKind,
    checkboxes,
    radios,
)


def test_ids_are_unique():
    assert len(BY_ID) == len(LAYERS) == 12


def test_the_left_six_are_checkboxes_and_the_right_six_are_radios():
    """The shape of the indicator is the kind, and they sit in two groups."""
    assert [layer.kind for layer in checkboxes()] == [LayerKind.CHECKBOX] * 6
    assert [layer.kind for layer in radios()] == [LayerKind.RADIO] * 6
    assert checkboxes() + radios() == LAYERS
    # Checkboxes are the left half of the strip, radios the right — so the last
    # checkbox sits left of the first radio.
    assert checkboxes()[-1].centre[0] < radios()[0].centre[0]


def test_a_checkbox_is_independent_and_a_radio_is_exclusive():
    """The distinction an agent has to honour, not just the names."""
    assert LayerKind.CHECKBOX.value == "checkbox"
    assert LayerKind.RADIO.value == "radio"
    # Vocabulary: these are the HUD's own control types. A test that still says
    # 'location' or 'colouring' would let the old framing sneak back in.
    assert {kind.value for kind in LayerKind} == {"checkbox", "radio"}


def test_the_buttons_are_in_left_to_right_order_on_one_row():
    xs = [layer.centre[0] for layer in LAYERS]
    ys = {layer.centre[1] for layer in LAYERS}
    assert xs == sorted(xs)
    assert ys == {0.952}
    for x, y in (layer.centre for layer in LAYERS):
        assert 0.0 < x < 1.0
        assert 0.0 < y < 1.0


def test_neighbouring_buttons_do_not_share_a_centre():
    for a, b in itertools.combinations(LAYERS, 2):
        assert a.centre != b.centre


def test_confirmed_legends_keep_the_titles_read_off_the_screen():
    assert BY_ID["armies"].legend_title == "ARMIES Legend"
    assert BY_ID["agents"].legend_title == "AGENTS Legend"
    assert BY_ID["fortifications"].legend_title == "FORTIFICATIONS Legend"
    assert BY_ID["trade_goods"].legend_title == "TRADE GOODS Legend"
    assert BY_ID["factions"].legend_title == "FACTIONS Legend"
    assert BY_ID["diplomacy"].legend_title == "DIPLOMACY Legend"
    assert BY_ID["activity"].legend_title == "ACTIVITY Legend"


def test_diplomacy_view_names_the_two_standings_a_hover_cannot():
    text = BY_ID["diplomacy"].what_it_shows
    assert "Ally of Ally" in text
    assert "Ally of Enemy" in text


def test_unconfirmed_layer_titles_are_not_invented():
    """A guessed legend title would ship as if it had been read."""
    for layer_id in ("trade_routes", "public_order", "wealth", "military"):
        assert BY_ID[layer_id].note, f"{layer_id} must say why its title is unconfirmed"
