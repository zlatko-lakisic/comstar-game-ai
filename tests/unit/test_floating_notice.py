"""A scroll can open over the middle of the map, and nothing was looking there.

"Faction Destroyed — Dacia" appeared on turn 38 of an unattended run. The
classifier called the screen `campaign_map`, the left dock was empty so the map
read as clear, and End Turn went into a panel that had the keyboard. Every attempt
came back `no_turn_boundary`; the run spent its remaining fourteen turns doing
that and finished having advanced eight of twenty.

The fixtures are the real frames: the stuck one, and the map after the notice was
closed. Both are halved from 1920x1080, which keeps the close X within half a
thousandth of where it is at full size.
"""

from __future__ import annotations

import pathlib

import pytest
from PIL import Image

from comstar_game_ai.game_io.campaign.modal import (
    CENTRE_PARCHMENT_CLEAR,
    centre_panel_bounds,
    centre_parchment_ratio,
    left_overlay_parchment_ratio,
    localize_centre_scroll_close_x,
    localize_panel_close_x,
    panel_bounds,
)

FRAMES = pathlib.Path(__file__).parent.parent / "fixtures" / "frames"


@pytest.fixture
def notice():
    return Image.open(FRAMES / "floating-notice-faction-destroyed.png").convert("RGB")


@pytest.fixture
def clear_map():
    return Image.open(FRAMES / "campaign-map-clear.png").convert("RGB")


def test_the_old_measures_could_not_see_it(notice):
    """Not a hypothetical blind spot: this is what every existing check reported."""
    assert panel_bounds(notice) is None
    assert localize_panel_close_x(notice) is None
    assert left_overlay_parchment_ratio(notice) < 0.01


def test_the_centre_measure_can(notice, clear_map):
    busy = centre_parchment_ratio(notice)
    empty = centre_parchment_ratio(clear_map)

    assert busy > CENTRE_PARCHMENT_CLEAR > empty, f"notice={busy:.3f} clear={empty:.3f}"


def test_the_close_x_is_found_where_it_is(notice):
    """Clicking (0.6561, 0.2668) cleared it live; 10px off did nothing at all."""
    found = localize_centre_scroll_close_x(notice)

    assert found is not None, "no close X on a scroll that has one"
    assert found.x_norm == pytest.approx(0.656, abs=0.01)
    assert found.y_norm == pytest.approx(0.267, abs=0.01)


def test_a_clear_map_offers_nothing_to_click(clear_map):
    """The expensive failure would be inventing a button and clicking the map."""
    assert centre_panel_bounds(clear_map) is None
    assert localize_centre_scroll_close_x(clear_map) is None
