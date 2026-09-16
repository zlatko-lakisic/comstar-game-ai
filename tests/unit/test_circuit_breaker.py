"""Z8 circuit breaker: identical refusal → overlay FAULT → end run."""

from __future__ import annotations

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.shared.ipc.events import EventKind


class _FakePublisher:
    def __init__(self) -> None:
        self.events: list[tuple[EventKind, dict]] = []

    def publish(self, kind: EventKind, payload: dict | None = None) -> None:
        self.events.append((kind, dict(payload or {})))


def test_circuit_breaker_ends_run_on_second_identical_failure(monkeypatch):
    pub = _FakePublisher()
    driver = HardcodedCampaignDriver(publisher=pub, use_vision=False, seed_from_setup=False)
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.state.turn = 6
    driver.last_refusal_code = "no_move_cursor"

    calls = {"n": 0}

    def fail_stub(**kwargs):
        calls["n"] += 1
        driver.last_refusal_code = "no_move_cursor"
        return False

    monkeypatch.setattr(driver, "run_turn_stub", fail_stub)
    monkeypatch.setattr(driver, "poll_observation", lambda: None)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 6)

    result = driver.run_turns(5, require_ok=False, wait_for_next_turn=False)
    assert calls["n"] == 2
    assert result["circuit_breaker"] == 1
    assert result["turns_failed"] == 2
    faults = [
        p
        for k, p in pub.events
        if k is EventKind.VERIFICATION and p.get("ok") is False
    ]
    assert faults
    assert "circuit_breaker" in str(faults[0].get("summary", ""))
    assert "no_move_cursor" in str(faults[0].get("summary", ""))


def test_circuit_breaker_does_not_fire_on_different_refusal(monkeypatch):
    pub = _FakePublisher()
    driver = HardcodedCampaignDriver(publisher=pub, use_vision=False, seed_from_setup=False)
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.state.turn = 6
    reasons = iter(["no_move_cursor", "pose_unverified:quiesce_timeout", "stack_not_selected"])

    def fail_stub(**kwargs):
        driver.last_refusal_code = next(reasons)
        return False

    monkeypatch.setattr(driver, "run_turn_stub", fail_stub)
    monkeypatch.setattr(driver, "poll_observation", lambda: None)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 6)

    result = driver.run_turns(3, require_ok=False, wait_for_next_turn=False)
    assert result["circuit_breaker"] == 0
    assert result["turns_failed"] == 3
    assert not any(
        k is EventKind.VERIFICATION and p.get("ok") is False and "circuit_breaker" in str(p)
        for k, p in pub.events
    )
