"""Acceptance: 20-turn hardcoded campaign (dry, no Rome)."""

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver


def test_twenty_turn_hardcoded_dry():
    driver = HardcodedCampaignDriver()
    result = driver.run_turns(20, require_ok=False)
    assert result["requested"] == 20
    assert result["turns_ok"] + result["turns_failed"] == 20
