"""The campaign loop's combat step: when it acts, and when it stays out of the way."""

from __future__ import annotations

from dataclasses import dataclass, field

import comstar_game_ai.game_io.drivers.hardcoded_campaign as driver_module
from comstar_game_ai.game_io.campaign.combat import AttackOutcome, StackSelection
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.shared.ipc.events import EventKind


@dataclass
class StubDirector:
    """Stands in for CombatDirector, recording what the driver asked it to do."""

    pending: bool = False
    resolves: bool = True
    selection: StackSelection = field(
        default_factory=lambda: StackSelection(unit_cards=8, safe_to_attack=True)
    )
    outcomes: dict[tuple[float, float], AttackOutcome] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    attacked: list[tuple[float, float]] = field(default_factory=list)
    last_reason: str = "no_attack_cursor"

    def battle_pending(self) -> bool:
        self.calls.append("battle_pending")
        return self.pending

    def resolve_battle(self) -> bool:
        self.calls.append("resolve_battle")
        return self.resolves

    def selected_stack(self) -> StackSelection:
        self.calls.append("selected_stack")
        return self.selection

    def acquire_stack(self, row) -> StackSelection:
        self.calls.append(f"acquire_stack{row}")
        return self.selection

    def attack(self, target, **_kwargs) -> AttackOutcome:
        self.attacked.append(target)
        return self.outcomes.get(
            target,
            AttackOutcome(ordered=False, battle_resolved=False, reason=self.last_reason),
        )


def make_driver(stub: StubDirector, **kwargs) -> HardcodedCampaignDriver:
    driver = HardcodedCampaignDriver(use_vision=True, auto_end_turn=False, **kwargs)
    driver.state.state = GameState.CAMPAIGN_MAP
    driver.combat_director = lambda: stub  # type: ignore[method-assign]
    return driver


def test_a_pending_battle_is_auto_resolved_and_recorded():
    stub = StubDirector(pending=True)
    driver = make_driver(stub)

    assert driver.resolve_pending_battle() is True
    assert driver.battles_resolved == 1
    assert [e["event"] for e in driver.belief.history] == ["BattleAutoResolved"]


def test_no_panel_means_nothing_is_clicked():
    stub = StubDirector(pending=False)
    driver = make_driver(stub)

    assert driver.resolve_pending_battle() is False
    assert stub.calls == ["battle_pending"]
    assert driver.battles_resolved == 0


def test_a_panel_that_will_not_clear_is_not_counted():
    stub = StubDirector(pending=True, resolves=False)
    driver = make_driver(stub)

    assert driver.resolve_pending_battle() is False
    assert driver.battles_resolved == 0
    assert driver.belief.history == []


def test_auto_resolve_can_be_turned_off():
    stub = StubDirector(pending=True)
    driver = make_driver(stub, auto_resolve_battles=False)

    assert driver.resolve_pending_battle() is False
    assert stub.calls == []


def test_a_dry_run_never_consults_the_director():
    """Vision off is the dry test path, and it must not reach for a live window."""
    stub = StubDirector(pending=True)
    driver = HardcodedCampaignDriver(use_vision=False)
    driver.combat_director = lambda: stub  # type: ignore[method-assign]

    assert driver.resolve_pending_battle() is False
    assert stub.calls == []


def test_battles_are_resolved_before_the_modal_handler_runs(monkeypatch):
    """Order matters: the handler cannot tell Battle Deployment from any other panel."""
    order: list[str] = []
    stub = StubDirector(pending=True)
    stub.resolve_battle = lambda: (order.append("resolve_battle"), True)[1]  # type: ignore[method-assign]

    driver = make_driver(stub)
    monkeypatch.setattr(driver, "_resolve_hwnd", lambda: 42)
    monkeypatch.setattr(
        driver_module,
        "ensure_campaign_map",
        lambda *_a, **_k: (
            order.append("ensure_campaign_map"),
            UiClassification(mode=CampaignUiMode.CAMPAIGN_MAP, confidence=0.9),
        )[1],
    )

    assert driver._sync_ui(handle_modal=True) == CampaignUiMode.CAMPAIGN_MAP
    assert order == ["resolve_battle", "ensure_campaign_map"]


def test_the_attack_step_is_off_until_it_is_configured():
    stub = StubDirector()
    driver = make_driver(stub)

    driver._run_combat_step()

    assert stub.calls == []
    assert driver.attacks_ordered == 0


def test_the_attack_step_refuses_a_narrowed_selection():
    stub = StubDirector(
        selection=StackSelection(unit_cards=1, safe_to_attack=False, reason="only 1 unit card(s)")
    )
    driver = make_driver(stub, attack_enabled=True, attack_targets=((0.26, 0.38),))
    phases: list[str] = []

    driver._run_combat_step(on_progress=lambda **kw: phases.append(kw["phase"]))

    assert stub.attacked == []
    assert driver.attacks_ordered == 0
    assert "attack skipped" in phases[0]


def test_the_attack_step_tries_targets_until_one_takes_the_order():
    ordered = AttackOutcome(ordered=True, battle_resolved=True, reason="ordered", unit_cards=8)
    stub = StubDirector(outcomes={(0.25, 0.35): ordered})
    driver = make_driver(
        stub,
        attack_enabled=True,
        army_lists_row_norm=(0.30, 0.415),
        attack_targets=((0.26, 0.38), (0.25, 0.35), (0.24, 0.36)),
    )

    driver._run_combat_step()

    # Stops at the one that took the order, and reacquires the stack from Lists first.
    assert stub.attacked == [(0.26, 0.38), (0.25, 0.35)]
    assert stub.calls == ["acquire_stack(0.3, 0.415)"]
    assert (driver.attacks_ordered, driver.battles_resolved) == (1, 1)


@dataclass
class RecordingPublisher:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def publish(self, kind, payload=None):
        self.events.append((kind.value, dict(payload or {})))


class BrokenPublisher:
    def publish(self, _kind, _payload=None):
        raise OSError("overlay went away")


def test_a_dry_run_narrates_itself_to_the_overlay():
    publisher = RecordingPublisher()
    driver = HardcodedCampaignDriver(use_vision=False, auto_end_turn=False, publisher=publisher)
    driver.state.state = GameState.CAMPAIGN_MAP

    driver.run_turns(1, require_ok=False, wait_for_next_turn=False)

    kinds = [kind for kind, _payload in publisher.events]
    assert kinds[0] == "control_state"
    assert kinds[-1] == "control_state"
    assert "intent_declared" in kinds and "verification" in kinds


def test_a_dead_overlay_is_dropped_rather_than_taxing_every_turn():
    """Each publish to a dead socket costs a connect timeout, so stop trying."""
    driver = HardcodedCampaignDriver(use_vision=False, publisher=BrokenPublisher())

    for _ in range(3):
        driver._publish(EventKind.CONTROL_STATE, {"state": "agent"})

    assert driver.publisher is None


def test_run_turns_reports_the_combat_counters():
    driver = HardcodedCampaignDriver(use_vision=False, auto_end_turn=False, end_turn_delay_s=0)
    driver.state.state = GameState.CAMPAIGN_MAP

    result = driver.run_turns(2, require_ok=False, wait_for_next_turn=False)

    assert result["attacks_ordered"] == 0
    assert result["battles_resolved"] == 0
