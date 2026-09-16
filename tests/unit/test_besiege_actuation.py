"""Besiege actuation: pan guard, camera restart, sword gate, war-confirm Yes."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from comstar_game_ai.agent.belief.diplomacy import get_standing, seed_standings_from_allies
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.campaign.besiege_actuation import (
    BesiegeActuator,
    never_click_minimap,
)
from comstar_game_ai.game_io.campaign.camera_pose import FrustumMeasure
from comstar_game_ai.game_io.campaign.map_target_vision import (
    MapTargetHit,
    build_map_target_prompt,
)


@dataclass
class FakeController:
    taps: list[str] = field(default_factory=list)
    clicks: list[tuple[str, float, float]] = field(default_factory=list)
    moves: list[tuple[int, int]] = field(default_factory=list)

    def tap_key(self, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
        self.taps.append(key)
        return True

    def click_client_norm(
        self, hwnd: int, x_norm: float, y_norm: float, *, dwell_ms: int = 30
    ) -> bool:
        self.clicks.append(("left", x_norm, y_norm))
        return True

    def right_click_client_norm(
        self, hwnd: int, x_norm: float, y_norm: float, *, dwell_ms: int = 30
    ) -> bool:
        self.clicks.append(("right", x_norm, y_norm))
        return True

    def move_mouse(self, x: int, y: int) -> None:
        self.moves.append((x, y))

    def right_click(self, x: int, y: int, *, dwell_ms: int = 80, settle_ms: int = 120) -> bool:
        self.clicks.append(("right_px", float(x), float(y)))
        return True


def test_never_click_minimap_raises():
    try:
        never_click_minimap(0.9, 0.9)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "minimap" in str(exc).lower()


def test_pan_uses_keys_and_does_not_click(monkeypatch):
    ctrl = FakeController()
    frames = [Image.new("RGB", (64, 64), (20, 40, 20))]

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        allow_region_pan=True,
        pan_taps=1,
        capture=lambda: frames[0],
        sleep=lambda _s: None,
    )
    monkeypatch.setattr(
        actuator,
        "measure_frustum",
        lambda image=None: FrustumMeasure((10.0, 20.0), (40.0, 50.0)),
    )
    actuator.pan_region(dx_hint=5.0, dy_hint=0.0)
    assert "d" in ctrl.taps
    assert ctrl.clicks == []


def test_camera_move_during_vision_restarts(monkeypatch):
    ctrl = FakeController()
    calls = {"n": 0}

    def locate(_image, _label: str):
        calls["n"] += 1
        return MapTargetHit(
            found=True, label="Segesta", x_norm=0.3, y_norm=0.4, confidence=0.9
        )

    frusta = [
        FrustumMeasure((10.0, 20.0), (40.0, 50.0)),
        FrustumMeasure((10.0, 20.0), (40.0, 50.0)),
        FrustumMeasure((30.0, 20.0), (60.0, 50.0)),  # moved
        FrustumMeasure((30.0, 20.0), (60.0, 50.0)),
        FrustumMeasure((30.0, 20.0), (60.0, 50.0)),
        FrustumMeasure((30.0, 20.0), (60.0, 50.0)),
    ]
    idx = {"i": 0}

    def measure(image=None):
        i = min(idx["i"], len(frusta) - 1)
        idx["i"] += 1
        return frusta[i]

    cursor_state = {"n": 0}

    def fake_cursor() -> int:
        cursor_state["n"] += 1
        # Odd reads = baseline open-land; even = sword after hover.
        return 100 if cursor_state["n"] % 2 == 1 else 200

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        fake_cursor,
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (int(x * 100), int(y * 100)),
    )

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        locate_target=locate,
        max_camera_restarts=2,
        capture=lambda: Image.new("RGB", (32, 32), (0, 0, 0)),
        sleep=lambda _s: None,
    )
    actuator.measure_frustum = measure  # type: ignore[method-assign]
    out = actuator.besiege(label="Segesta", standing="at_war")
    assert out.ordered
    assert out.camera_restarted >= 1
    assert any(c[0] == "right" for c in ctrl.clicks)


def test_no_sword_refuses_click(monkeypatch):
    ctrl = FakeController()

    def locate(_image, _label: str):
        return MapTargetHit(
            found=True, label="Segesta", x_norm=0.3, y_norm=0.4, confidence=0.9
        )

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        lambda: 111,
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (10, 10),
    )

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        locate_target=locate,
        capture=lambda: Image.new("RGB", (16, 16), (0, 0, 0)),
        sleep=lambda _s: None,
    )
    actuator.measure_frustum = lambda image=None: FrustumMeasure((0, 0), (10, 10))  # type: ignore[method-assign]
    out = actuator.besiege(label="Segesta", standing="at_war")
    assert not out.ordered
    assert out.reason == "no_sword_glyph"
    assert ctrl.clicks == []


def test_neutral_confirms_war_yes_and_updates_belief(monkeypatch):
    ctrl = FakeController()
    store = BeliefStore()
    seed_standings_from_allies(
        store, player_faction="romans_julii", ally_pairs=[], known_factions={"gaul"}
    )
    assert get_standing(store, "gaul") == "neutral"

    def locate(_image, _label: str):
        return MapTargetHit(
            found=True, label="Patavium", x_norm=0.4, y_norm=0.5, confidence=0.9
        )

    cursors = iter([1, 2])
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        lambda: next(cursors, 2),
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (int(x * 100), int(y * 100)),
    )

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        locate_target=locate,
        belief=store,
        confirm_war_yes=lambda _img: (0.45, 0.78),
        capture=lambda: Image.new("RGB", (16, 16), (0, 0, 0)),
        sleep=lambda _s: None,
    )
    actuator.measure_frustum = lambda image=None: FrustumMeasure((0, 0), (10, 10))  # type: ignore[method-assign]
    out = actuator.besiege(label="Patavium", standing="neutral", owner_raw="gaul")
    assert out.ordered
    assert out.war_confirmed
    assert get_standing(store, "gaul") == "at_war"
    assert any(c[0] == "right" for c in ctrl.clicks)
    assert any(c[0] == "left" and abs(c[1] - 0.45) < 1e-6 for c in ctrl.clicks)


def test_map_target_prompt_reads_plaque_without_coordinates():
    text = build_map_target_prompt(label="Segesta")
    assert "plaque" in text.lower()
    assert "Do NOT report coordinates" in text
    assert '"x_norm"' not in text
    assert '"y_norm"' not in text
    assert "Segesta" in text


def test_besiege_from_view_picks_at_war_first(monkeypatch):
    from comstar_game_ai.game_io.campaign.map_target_vision import SettlementViewHit

    ctrl = FakeController()
    hits = [
        SettlementViewHit("Patavium", 0.7, 0.4, "neutral", 0.9),
        SettlementViewHit("Segesta", 0.3, 0.4, "at_war", 0.8),
        SettlementViewHit("Arretium", 0.5, 0.5, "ours", 0.9),
    ]

    cursors = iter([1, 2])
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        lambda: next(cursors, 2),
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (int(x * 100), int(y * 100)),
    )

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        scan_settlements=lambda _img: hits,
        capture=lambda: Image.new("RGB", (16, 16), (0, 0, 0)),
        sleep=lambda _s: None,
    )
    actuator.measure_frustum = lambda image=None: FrustumMeasure((0, 0), (10, 10))  # type: ignore[method-assign]
    out = actuator.besiege_from_view()
    assert out.ordered
    assert out.label == "Segesta"
    assert any(c[0] == "right" and abs(c[1] - 0.3) < 1e-6 for c in ctrl.clicks)


def test_besiege_from_view_tries_next_when_no_sword(monkeypatch):
    from comstar_game_ai.game_io.campaign.map_target_vision import SettlementViewHit

    ctrl = FakeController()
    hits = [
        SettlementViewHit("Segesta", 0.3, 0.4, "at_war", 0.9),
        SettlementViewHit("Patavium", 0.7, 0.4, "neutral", 0.8),
    ]
    # First candidate: baseline==hovered (no sword). Second: sword.
    cursors = iter([10, 10, 10, 20])
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        lambda: next(cursors, 20),
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (int(x * 100), int(y * 100)),
    )

    actuator = BesiegeActuator(
        hwnd=1,
        controller=ctrl,
        scan_settlements=lambda _img: hits,
        confirm_war_yes=lambda _img: (0.45, 0.78),
        capture=lambda: Image.new("RGB", (16, 16), (0, 0, 0)),
        sleep=lambda _s: None,
    )
    actuator.measure_frustum = lambda image=None: FrustumMeasure((0, 0), (10, 10))  # type: ignore[method-assign]
    out = actuator.besiege_from_view()
    assert out.ordered
    assert out.label == "Patavium"
    assert out.war_confirmed
