"""Mouse march destination math — no Rome required."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.march import MarchDirector


def test_destination_is_east_of_centre_when_target_is_east():
    click = MarchDirector.destination_norm(
        from_x=100, from_y=100, to_x=110, to_y=100, step_norm=0.16
    )
    assert click is not None
    assert click[0] > 0.50
    assert abs(click[1] - 0.48) < 0.02


def test_destination_flips_map_north_to_screen_up():
    click = MarchDirector.destination_norm(
        from_x=100, from_y=100, to_x=100, to_y=110, step_norm=0.16
    )
    assert click is not None
    assert click[1] < 0.48  # higher map Y → upper screen


def test_one_tile_step_toward_target():
    assert MarchDirector.one_tile_step(
        from_x=100, from_y=100, to_x=110, to_y=100
    ) == (101.0, 100.0)


def test_already_at_target_has_no_destination():
    assert (
        MarchDirector.destination_norm(from_x=5, from_y=5, to_x=5, to_y=5) is None
    )
