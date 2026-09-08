"""The opening position is only true at the opening.

`descr_strat.txt` describes 270 BC summer: which faction holds Arretium, where
Vibius Julius is standing, who owns Segesta. Seeding it is what gave the director
a map to reason about at all — before that the belief store was empty and every
turn came back "hold", indistinguishable from a deliberate one.

Seeded into a campaign already running, the same facts are a lie with the same
provenance as the truth. A campaign on turn 56 is at 243 BC; 55 turns of
conquests, losses and dead generals are missing from what it claims. Live
telemetry overwrites what it happens to observe, so what survives is a quiet,
partial, 27-year-old picture rather than an obviously empty one.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver

MODULE = "comstar_game_ai.game_io.drivers.hardcoded_campaign"


@pytest.fixture
def seeded(monkeypatch):
    """Record whether the setup seed was read, without touching the install."""
    calls: list[str] = []
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.start_position.seed_belief_from_setup",
        lambda _belief, player_faction: calls.append(player_faction) or 7,
    )
    return calls


def _driver_at_turn(monkeypatch, turn: int | None, **kwargs) -> HardcodedCampaignDriver:
    marker = None if turn is None else (turn, 1788822272.0)
    monkeypatch.setattr(
        "comstar_game_ai.game_io.logs.turn_boundary.newest_turn_start_marker",
        lambda: marker,
    )
    return HardcodedCampaignDriver(**kwargs)


def test_a_fresh_campaign_is_seeded(monkeypatch, seeded):
    """Turn 1 at 270 BC: the setup files are exactly right."""
    _driver_at_turn(monkeypatch, 1)

    assert seeded, "a campaign at its opening was left blind"


def test_a_campaign_with_no_history_is_seeded(monkeypatch, seeded):
    """No marker at all means Rome has recorded nothing yet."""
    _driver_at_turn(monkeypatch, None)

    assert seeded


def test_a_campaign_underway_is_not_seeded(monkeypatch, seeded):
    """Turn 56 is 243 BC. The opening position is 27 years stale."""
    _driver_at_turn(monkeypatch, 56)

    assert not seeded, "seeded 270 BC facts into a campaign on turn 56"


def test_the_seed_can_still_be_turned_off_outright(monkeypatch, seeded):
    _driver_at_turn(monkeypatch, 1, seed_from_setup=False)

    assert not seeded


def test_an_unreadable_log_does_not_stop_the_run(monkeypatch, seeded):
    """Guessing turn 0 and seeding is the safe direction: worst case is a stale
    prior on a fresh campaign, against a crash on startup."""

    def boom():
        raise OSError("log is gone")

    monkeypatch.setattr(
        "comstar_game_ai.game_io.logs.turn_boundary.newest_turn_start_marker", boom
    )

    driver = HardcodedCampaignDriver()

    assert driver is not None
    assert seeded
