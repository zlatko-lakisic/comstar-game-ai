"""Closed-loop camera pans chosen from center-tile map coordinates."""

from comstar_game_ai.game_io.campaign.camera_seek import (
    MAX_HOLD_S,
    choose_move,
    close_enough,
    record_rate,
)


def test_done_when_both_axes_are_within_three():
    assert close_enough((98, 101), (100, 100))
    assert not close_enough((90, 100), (100, 100))
    assert choose_move((100, 100), (102, 99), {}).kind == "done"


def test_an_uncalibrated_x_error_probes_d():
    move = choose_move((80, 80), (100, 80), {})
    assert move.kind == "move"
    assert move.key == "d"
    assert move.hold_s == 0.20


def test_an_uncalibrated_west_error_uses_a():
    move = choose_move((100, 80), (80, 80), {})
    assert move.key == "a"
    assert move.hold_s == 0.20


def test_a_closed_axis_is_not_nudged_while_the_other_is_open():
    rates = {"w": (0.0, 45.0), "s": (0.0, -45.0), "a": (-45.0, 0.0), "d": (45.0, 0.0)}
    move = choose_move((70, 42), (44, 44), rates)
    assert move.key == "a"


def test_an_uncalibrated_south_error_uses_s():
    move = choose_move((44, 150), (44, 44), {})
    assert move.key == "s"
    assert move.hold_s == 0.20


def test_a_known_d_rate_sets_the_hold_and_caps_it():
    rates = {"d": (10.0, 0.0)}
    move = choose_move((80, 80), (100, 80), rates)
    assert move.key == "d"
    assert move.hold_s == MAX_HOLD_S


def test_the_opposite_key_is_inferred_until_it_is_measured():
    rates: dict[str, tuple[float, float]] = {}
    measured: set[str] = set()
    assert record_rate(rates, measured, "d", (80, 80), (90, 80), 0.5)
    assert rates["a"] == (-20.0, 0.0)
    move = choose_move((90, 80), (80, 80), rates)
    assert move.key == "a"
    assert move.hold_s == 0.5


def test_a_measured_opposite_is_not_overwritten_by_inference():
    rates = {"a": (-5.0, 1.0)}
    measured = {"a"}
    record_rate(rates, measured, "d", (0, 0), (10, 0), 1.0)
    assert rates["a"] == (-5.0, 1.0)
    assert "d" in measured


def test_a_nudge_under_one_map_unit_does_not_become_a_rate():
    rates: dict[str, tuple[float, float]] = {}
    assert record_rate(rates, set(), "up", (10, 10), (10, 10), 0.2) is False
    assert rates == {}


def test_y_is_corrected_when_it_is_the_error():
    rates = {"w": (0.0, 8.0), "s": (0.0, -8.0)}
    move = choose_move((50, 40), (50, 44), rates)
    assert move.key == "w"
    assert move.hold_s == 0.5


def test_an_unreadable_pan_uses_the_measured_rate():
    from comstar_game_ai.game_io.campaign.camera_seek import estimate_after

    rates = {"s": (0.0, -45.0)}
    assert estimate_after("s", (141, 78), 0.51, rates) == (141, 55)


def test_an_unmeasured_key_uses_the_default_speed():
    from comstar_game_ai.game_io.campaign.camera_seek import estimate_after

    assert estimate_after("d", (141, 55), 0.20, {}) == (150, 55)


def test_stuck_when_every_key_increases_the_error():
    rates = {
        "d": (-1.0, 0.0),
        "a": (-1.0, 0.0),
        "w": (0.0, -1.0),
        "s": (0.0, -1.0),
    }
    assert choose_move((0, 0), (10, 10), rates).kind == "stuck"
