"""Settings the config carried and nobody read.

`auto_end_turn` is the one that mattered. It defaults to False on the driver and
the campaign loop never set it, so `run_turn_stub` skipped the End Turn block and
fell through to waiting for an *external* turn advance: the run pressed nothing
and waited three minutes a turn for a human to play the game for it, twenty times
over, then reported that no turn had advanced.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.runtime import GameIoRuntime

CONFIG = {
    "campaign": {
        "auto_end_turn": True,
        "end_turn_ready_timeout_s": 30,
        "modal": {"use_ada_vision": True},
        "combat": {"auto_resolve_battles": True, "attack_enabled": False},
    }
}


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr("comstar_game_ai.game_io.runtime.load_config", lambda: CONFIG)
    return GameIoRuntime()


def test_the_loop_is_told_to_end_its_own_turns(runtime):
    assert runtime._campaign_wiring()["auto_end_turn"] is True


def test_the_loop_is_given_eyes_to_clear_a_panel(runtime):
    wiring = runtime._campaign_wiring()

    assert wiring["use_vision"] is True
    assert wiring["end_turn_ready_timeout_s"] == 30.0


def test_an_empty_config_leaves_the_loop_passive(monkeypatch):
    """Absent settings must not invent an agent that plays the game."""
    monkeypatch.setattr("comstar_game_ai.game_io.runtime.load_config", lambda: {})

    wiring = GameIoRuntime()._campaign_wiring()

    assert wiring["auto_end_turn"] is False
    assert wiring["use_vision"] is False


def test_the_wiring_is_what_the_driver_accepts(runtime):
    """These have to be real driver arguments, or the run dies at startup."""
    driver = HardcodedCampaignDriver(
        player_faction="julii", seed_from_setup=False, **runtime._campaign_wiring()
    )

    assert driver.auto_end_turn is True
    assert driver.use_vision is True
    assert driver.end_turn_ready_timeout_s == 30.0


def test_a_driver_that_ends_turns_does_not_wait_for_a_human(runtime):
    """The two paths are exclusive, and the passive one was the bug.

    `run_turn_stub` ends the turn itself when `auto_end_turn`, and otherwise waits
    for someone else to do it. Getting this backwards is silent: both paths return
    a bool and the loop reports a clean failure either way.
    """
    driver = HardcodedCampaignDriver(
        player_faction="julii", seed_from_setup=False, **runtime._campaign_wiring()
    )

    assert driver.auto_end_turn, "otherwise the loop waits for a turn nobody will end"
