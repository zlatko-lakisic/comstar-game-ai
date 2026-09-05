"""Acceptance: 20-turn hardcoded campaign (dry, no Rome)."""

import pytest

import comstar_game_ai.game_io.logs.turn_boundary as turn_boundary
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver, phase2_accepted
from comstar_game_ai.game_io.state_machine import GameState


@pytest.fixture(autouse=True)
def _isolate_turn_sources(tmp_path, monkeypatch):
    """Keep the dry run off this machine's real autosaves and log.

    Without this the run reads whatever campaign happens to be open, and a live game
    advancing turns in the background makes the dry run look like it drove them.
    """
    empty = tmp_path / "saves-empty"
    empty.mkdir()
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: empty)
    monkeypatch.setattr(turn_boundary, "default_message_log_path", lambda: tmp_path / "absent.txt")


def _dry_run(turns=20):
    driver = HardcodedCampaignDriver(use_vision=False, auto_end_turn=False, end_turn_delay_s=0)
    driver.state.state = GameState.CAMPAIGN_MAP
    return driver.run_turns(turns, require_ok=False, wait_for_next_turn=False)


def test_twenty_turn_hardcoded_dry():
    result = _dry_run()
    assert result["requested"] == 20
    assert result["turns_ok"] + result["turns_failed"] == 20


def test_run_reports_the_campaigns_own_turn_count():
    result = _dry_run()
    assert result["turns_advanced"] == result["game_turn_end"] - result["game_turn_start"]


def test_cycles_without_a_campaign_do_not_pass_acceptance():
    """No Rome running means no turn can have advanced, whatever the cycles report."""
    result = _dry_run()
    assert result["turns_advanced"] == 0
    assert not phase2_accepted(result, turns=20)


def test_acceptance_needs_turns_desyncs_and_real_advance():
    passing = {"turns_ok": 20, "desyncs": 0, "turns_advanced": 20}
    assert phase2_accepted(passing, turns=20)

    assert not phase2_accepted({**passing, "desyncs": 1}, turns=20)
    assert not phase2_accepted({**passing, "turns_ok": 19}, turns=20)
    assert not phase2_accepted({**passing, "turns_advanced": 10}, turns=20)
    assert not phase2_accepted({"turns_ok": 20, "desyncs": 0}, turns=20)
