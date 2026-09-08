"""The watchdog has to outlast a turn.

A campaign turn spends minutes waiting for Rome's AI round; the deadman allows
ten seconds. The loop petted it once per turn, which is to say once per several
minutes, so it fired partway through turn one of every run — killed input, and
left the loop waiting out its full timeout against a game it could no longer
touch. The run reported `turns_advanced: 0` and looked like the game had ignored
End Turn.
"""

from __future__ import annotations

import time

import pytest

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver


@pytest.fixture
def driver():
    return HardcodedCampaignDriver(player_faction="julii", seed_from_setup=False)


def test_a_wait_reports_in_while_it_waits(driver, monkeypatch):
    beats: list[float] = []
    driver.on_heartbeat = lambda: beats.append(time.time())
    monkeypatch.setattr(driver, "poll_observation", lambda: 0)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 5)

    advanced = driver.wait_for_turn_event(timeout_s=1.0)

    assert not advanced, "nothing advanced, so this is the timeout path"
    assert len(beats) > 1, "one beat per turn is what let the watchdog fire mid-turn"


def test_a_loop_with_nobody_watching_still_runs(driver, monkeypatch):
    """`on_heartbeat` is optional: the driver is used without a safety layer."""
    monkeypatch.setattr(driver, "poll_observation", lambda: 0)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 5)

    assert driver.wait_for_turn_event(timeout_s=0.5) is False


def test_a_failing_watchdog_does_not_end_the_run(driver, monkeypatch):
    """The heartbeat exists to keep the run alive; it must not be what kills it."""

    def explode() -> None:
        raise RuntimeError("watchdog is gone")

    driver.on_heartbeat = explode
    monkeypatch.setattr(driver, "poll_observation", lambda: 0)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 5)

    assert driver.wait_for_turn_event(timeout_s=0.5) is False


def test_the_campaign_loop_hands_the_driver_its_watchdog(monkeypatch):
    """The wiring itself, so a rename cannot quietly restore the old behaviour."""
    from comstar_game_ai.game_io.runtime import GameIoRuntime

    runtime = GameIoRuntime()
    driver = HardcodedCampaignDriver(
        player_faction="julii",
        seed_from_setup=False,
        on_heartbeat=runtime.safety.pet_deadman,
    )

    assert driver.on_heartbeat == runtime.safety.pet_deadman


def test_a_dialog_does_not_crash_a_run_nobody_is_watching(driver, monkeypatch, tmp_path):
    """`on_progress` is optional, so an unguarded call is a crash only when unobserved.

    That is exactly how the unattended 20-turn run died: eighteen turns in, a battle
    dialog came up, the loop saved a debug frame, and then reported the frame through
    a callback that was None because no overlay was attached.
    """
    from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode
    from comstar_game_ai.game_io.drivers import hardcoded_campaign as mod

    driver.use_vision = True
    monkeypatch.setattr(driver, "poll_observation", lambda: 0)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 5)
    monkeypatch.setattr(driver, "_sync_ui", lambda **_k: CampaignUiMode.MODAL)
    monkeypatch.setattr(driver, "_resolve_hwnd", lambda: 1)
    monkeypatch.setattr(mod, "save_debug_capture", lambda *_a, **_k: True)
    driver._last_debug_capture_ts = 0.0

    # No on_progress, which is the normal case for a headless run.
    assert driver.wait_for_turn_event(timeout_s=1.0) is False
