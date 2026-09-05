"""Tests for the campaign camera navigation strategies.

These mostly guard the honesty of the accuracy labels. The value of this module is
that it says which primitives land on a named target and which only get you to the
right region; a strategy silently promoted to EXACT without evidence would send an
agent to look for a settlement that is not in frame.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.campaign import navigation
from comstar_game_ai.game_io.campaign.navigation import (
    BY_ID,
    STRATEGIES,
    Accuracy,
    exact,
)
from comstar_game_ai.game_io.campaign.rome_shortcuts import load_shortcuts


def test_ids_are_unique():
    assert len(BY_ID) == len(STRATEGIES)


def test_every_strategy_says_how_and_what_it_needs():
    for strategy in STRATEGIES:
        assert strategy.how, f"{strategy.id} does not say how to do it"
        assert strategy.requires, f"{strategy.id} does not state its preconditions"


def test_every_strategy_carries_evidence():
    """An accuracy claim with no captured frame behind it is an opinion."""
    for strategy in STRATEGIES:
        assert strategy.evidence, f"{strategy.id} claims {strategy.accuracy} with no evidence"


def test_capital_zoom_is_the_recovery_primitive():
    """Everything else is safe to try only because this always works."""
    strategy = BY_ID["capital_zoom"]
    assert strategy.accuracy is Accuracy.EXACT
    assert "nothing" in strategy.requires


def test_capital_zoom_is_bound_to_home_in_the_game_itself():
    """The atlas must not drift from descr_shortcuts.txt."""
    database = load_shortcuts()
    bindings = database.find("capital_zoom")
    if not bindings:
        pytest.skip("no installed shortcut file to check against")
    assert any(b.chord == "home" for b in bindings)


def test_the_zoom_actions_exist_in_the_game_and_are_distinct():
    database = load_shortcuts()
    if not database.keysets:
        pytest.skip("no installed shortcut file to check against")
    assert navigation.ZOOM_IN_ACTION != navigation.ZOOM_OUT_ACTION
    for action in (navigation.ZOOM_IN_ACTION, navigation.ZOOM_OUT_ACTION):
        assert database.find(action), f"{action} is not a real action"


def test_zoom_out_is_bound_to_x_and_zoom_in_to_z():
    """Measured in game: x widened the view, z narrowed it."""
    database = load_shortcuts()
    if not database.keysets:
        pytest.skip("no installed shortcut file to check against")
    chords = {
        navigation.ZOOM_OUT_ACTION: "x",
        navigation.ZOOM_IN_ACTION: "z",
    }
    for action, chord in chords.items():
        found = database.find(action, keyset="moderntw")
        assert any(b.chord == chord for b in found), f"{action} is no longer {chord}"


def test_the_exact_strategies_are_the_two_that_name_a_target():
    ids = {strategy.id for strategy in exact()}
    assert ids == {"capital_zoom", "locate_via_lists"}


def test_panning_is_not_claimed_to_be_precise():
    """12 presses crossed the map, 4 presses moved almost nothing."""
    assert BY_ID["arrow_pan"].accuracy is Accuracy.IMPRECISE


def test_the_radar_is_coarse_and_says_why():
    strategy = BY_ID["radar_click"]
    assert strategy.accuracy is Accuracy.COARSE
    assert "228" in strategy.note, "the structural reason for the imprecision is the point"


def test_the_overlay_is_recorded_as_not_navigable():
    """It looks like a clickable map and is not, which is worth a permanent note."""
    assert navigation.OVERLAY_IS_CLICKABLE is False


def test_the_radar_is_recorded_as_a_survey_instrument():
    assert navigation.RADAR_HOVER_YIELDS_REGION_AND_OWNER is True


def test_the_zoom_clamp_is_recorded_as_a_small_number():
    """Pressing zoom fifty times is a tell that nobody measured the clamp."""
    assert 0 < navigation.ZOOM_PRESSES_TO_CLAMP <= 12
