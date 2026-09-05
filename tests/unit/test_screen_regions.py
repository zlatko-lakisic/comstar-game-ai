"""Tests for the campaign screen region map.

The point of most of these is to stop the region map from quietly acquiring a
contradiction: two buttons overlapping, a HUD control sitting inside the map
viewport, or a coordinate escaping the client rect. Any of those would send a click
somewhere that mutates game state.
"""

from __future__ import annotations

import itertools

import pytest

from comstar_game_ai.game_io.campaign import screen_regions
from comstar_game_ai.game_io.campaign.rome_shortcuts import load_shortcuts
from comstar_game_ai.game_io.campaign.screen_regions import (
    BY_ID,
    REGIONS,
    Precision,
    RegionKind,
    buttons,
    region_at,
)


def _overlaps(a, b) -> bool:
    ax0, ay0, ax1, ay1 = a.bounds
    bx0, by0, bx1, by1 = b.bounds
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def test_ids_are_unique():
    assert len(BY_ID) == len(REGIONS)


def test_every_bound_is_inside_the_client_rect():
    for region in REGIONS:
        x0, y0, x1, y1 = region.bounds
        assert 0.0 <= x0 < x1 <= 1.0, f"{region.id} has bad x bounds"
        assert 0.0 <= y0 < y1 <= 1.0, f"{region.id} has bad y bounds"


def test_every_region_states_its_purpose():
    for region in REGIONS:
        assert region.purpose.strip(), f"{region.id} has no purpose"


def test_no_two_buttons_overlap():
    for a, b in itertools.combinations(buttons(), 2):
        assert not _overlaps(a, b), f"{a.id} overlaps {b.id}"


def test_a_click_on_any_button_resolves_to_that_button():
    # The HUD is drawn over the map, so overlapping the viewport is expected and not
    # an error. What must hold is that resolving a button's own centre never comes back
    # as the map: that confusion turns a UI click into a unit order, which is how a
    # guessed End Turn position once opened the building browser.
    for button in buttons():
        x, y = button.centre
        found = region_at(x, y)
        assert found is not None and found.id == button.id, (
            f"{button.id} centre {x, y} resolves to {found and found.id}"
        )


def test_centre_is_the_middle_of_the_bounds():
    region = BY_ID["end_turn_button"]
    x0, y0, x1, y1 = region.bounds
    assert region.centre == (round((x0 + x1) / 2, 4), round((y0 + y1) / 2, 4))


def test_region_at_prefers_the_most_specific_region():
    # End Turn sits inside the bottom HUD bar; the button must win.
    x, y = BY_ID["end_turn_button"].centre
    assert region_at(x, y).id == "end_turn_button"


def test_region_at_finds_the_bar_between_its_buttons():
    # A gap in the bottom bar with no button over it.
    found = region_at(0.30, 0.97)
    assert found is not None and found.id == "bottom_hud_bar"


def test_region_at_returns_none_outside_every_region():
    assert region_at(0.5, 0.02) is None


def test_the_map_viewport_covers_the_middle_of_the_screen():
    assert BY_ID["map_viewport"].contains(0.5, 0.5)


def test_only_end_turn_is_actuation_verified():
    # Honest bookkeeping: everything else was read off a grid and never clicked.
    verified = [r.id for r in REGIONS if r.precision is Precision.VERIFIED]
    assert verified == ["end_turn_button"]
    assert len(screen_regions.unverified()) == len(REGIONS) - 1


def test_the_four_hud_tabs_are_evenly_spaced():
    # They are one control strip, so a mis-measured entry shows up as uneven spacing.
    tabs = [
        BY_ID[f"hud_tab_{name}"].centre[0]
        for name in ("buildings", "army", "agents", "fleets")
    ]
    gaps = [round(b - a, 4) for a, b in zip(tabs, tabs[1:])]
    assert max(gaps) - min(gaps) < 0.006, f"uneven tab spacing: {gaps}"


def test_radar_controls_sit_beside_the_radar_not_on_it():
    radar = BY_ID["radar"]
    for control in ("radar_zoom_in", "radar_zoom_out", "radar_compass"):
        x, y = BY_ID[control].centre
        assert not radar.contains(x, y), f"{control} would click the radar map itself"


def test_readouts_are_not_classified_as_buttons():
    for name in ("treasury_readout", "date_readout"):
        assert BY_ID[name].kind is RegionKind.READOUT


def test_region_actions_exist_in_the_binding_database():
    shortcuts = load_shortcuts()
    if shortcuts is None:
        pytest.skip("descr_shortcuts.txt not present on this machine")
    for region in REGIONS:
        if not region.action:
            continue
        assert shortcuts.find(region.action), (
            f"{region.id} claims action {region.action!r} which the game does not define"
        )


def test_the_camera_controls_have_both_a_key_and_a_mouse_target():
    # Traversal should not depend on the keyset being what we assume.
    mouse = {r.action for r in REGIONS if r.action}
    for action in ("zoom_in", "zoom_out", "point_to_north"):
        assert action in mouse, f"{action} has no on-screen control recorded"
