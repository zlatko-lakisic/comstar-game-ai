"""Acceptance: 20-turn hardcoded campaign (dry, no Rome)."""

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.state_machine import GameState


def test_twenty_turn_hardcoded_dry():
    driver = HardcodedCampaignDriver(use_vision=False, auto_end_turn=False, end_turn_delay_s=0)
    driver.state.state = GameState.CAMPAIGN_MAP
    result = driver.run_turns(20, require_ok=False, wait_for_next_turn=False)
    assert result["requested"] == 20
    assert result["turns_ok"] + result["turns_failed"] == 20
