"""Counting turn advances against a saves folder that remembers other campaigns."""

from __future__ import annotations

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver


def _feed(driver: HardcodedCampaignDriver, values: list[int]) -> None:
    for value in values:
        driver._note_turn_started(value)


def test_the_first_reading_is_a_baseline_not_progress():
    """Otherwise a campaign resumed on turn 26 would report 26 turns driven."""
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [26])

    assert driver._turn_advances == 0


def test_each_climb_counts_once():
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [2, 2, 3, 3, 3, 4, 5])

    assert driver._turn_advances == 3


def test_a_gap_counts_every_turn_in_it():
    """A turn can land while we were mid-classification; the campaign still moved."""
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [10, 13])

    assert driver._turn_advances == 3


def test_a_number_going_down_re_baselines_instead_of_counting():
    """Rome's saves folder keeps earlier campaigns: 26 then 2 is a leftover, not a rewind."""
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [26, 2, 3, 4])

    assert driver._turn_advances == 2
    assert driver._turn_baseline_resets == 1


def test_the_real_run_that_scored_zero_now_scores_eighteen():
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [26] + list(range(2, 21)))

    assert driver._turn_advances == 18
    assert driver._turn_baseline_resets == 1


def test_zero_means_no_evidence_and_never_counts():
    """No saves folder, or none for this campaign yet, reads as 0 and must not count."""
    driver = HardcodedCampaignDriver(use_vision=False)
    _feed(driver, [0, 0, 5, 0, 6])

    assert driver._turn_advances == 1
    assert driver._turn_baseline_resets == 0
