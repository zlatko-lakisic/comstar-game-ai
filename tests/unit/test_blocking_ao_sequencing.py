"""Each campaign turn blocks on AO before planning orders."""

from __future__ import annotations

from comstar_game_ai.agent.directive import Directive, DirectiveIntent
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore


def test_run_turn_stub_blocks_on_deliberate_fn_before_orders(tmp_path, monkeypatch):
    store = DirectiveStore(tmp_path / "directive.json")
    calls: list[int] = []

    def deliberate(turn: int) -> None:
        calls.append(turn)
        store.write(
            f"campaign-{turn}-test",
            Directive(intent=DirectiveIntent(objective="hold"), commentary="unit"),
        )

    driver = HardcodedCampaignDriver(
        seed_from_setup=False,
        use_vision=False,
        auto_end_turn=False,
        directive_store=store,
        deliberate_fn=deliberate,
    )
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.state.turn = 12
    monkeypatch.setattr(driver, "_sync_ui", lambda handle_modal=True: None)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 12)
    monkeypatch.setattr(driver, "poll_observation", lambda: None)

    phases: list[str] = []

    def on_progress(*, index, total, phase, ok=None):
        phases.append(phase)

    ok = driver.run_turn_stub(
        wait_for_next_turn=False,
        on_progress=on_progress,
        index=1,
        total=1,
    )
    del ok  # return value depends on console; ignored here

    assert calls == [12]
    assert any(p.startswith("waiting for AO on turn 12") for p in phases)
    assert any(p.startswith("AO answered:") for p in phases)
    assert driver.last_directive == "hold"
    # Console orders fail without Rome; sequencing is what this test protects.


def test_align_turn_clock_prefers_live_game_turn_over_stale_bootstrap(monkeypatch):
    """Belief may say turn 11 while newest Start.sav is turn 4 — AO must use 4."""
    driver = HardcodedCampaignDriver(seed_from_setup=False, use_vision=False)
    driver.state.turn = 11
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 4)
    assert driver._align_turn_clock() == 4
    assert driver.state.turn == 4


def test_block_on_ao_uses_live_game_turn_not_stale_state(tmp_path, monkeypatch):
    store = DirectiveStore(tmp_path / "directive.json")
    calls: list[int] = []

    def deliberate(turn: int) -> None:
        calls.append(turn)
        store.write(
            f"campaign-{turn}-test",
            Directive(intent=DirectiveIntent(objective="hold"), commentary="unit"),
        )

    driver = HardcodedCampaignDriver(
        seed_from_setup=False,
        use_vision=False,
        auto_end_turn=False,
        directive_store=store,
        deliberate_fn=deliberate,
    )
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.state.turn = 11  # stale bootstrap
    monkeypatch.setattr(driver, "_sync_ui", lambda handle_modal=True: None)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 5)
    monkeypatch.setattr(driver, "poll_observation", lambda: None)

    driver.run_turn_stub(wait_for_next_turn=False, index=1, total=1)
    assert calls == [5]
    assert driver.state.turn == 5


def test_without_deliberate_fn_orders_do_not_wait(tmp_path, monkeypatch):
    store = DirectiveStore(tmp_path / "directive.json")
    store.write(
        "stale",
        Directive(intent=DirectiveIntent(objective="besiege"), commentary="preloaded"),
    )
    driver = HardcodedCampaignDriver(
        seed_from_setup=False,
        use_vision=False,
        auto_end_turn=False,
        directive_store=store,
        deliberate_fn=None,
    )
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.state.turn = 3
    monkeypatch.setattr(driver, "_sync_ui", lambda handle_modal=True: None)
    monkeypatch.setattr(driver, "_refresh_turn_from_message_log", lambda: None)
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 3)

    driver.run_turn_stub(wait_for_next_turn=False, index=1, total=1)
    assert driver.last_directive == "besiege"
