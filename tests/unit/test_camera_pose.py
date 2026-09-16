"""Unit tests for canonical camera pose reset / verify (no live display)."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.camera_pose import (
    CameraPoseDirector,
    FrustumMeasure,
    _aabb_close,
)


@dataclass
class _FakeController:
    taps: list[str]

    def tap_key(self, key: str, *, dwell_ms: int = 30, hwnd: int | None = None) -> bool:
        self.taps.append(key)
        return True

    def drag_client_norm(self, *args, **kwargs) -> bool:
        return False


def test_aabb_close_tolerance():
    a = FrustumMeasure((10.0, 20.0), (40.0, 50.0))
    b = FrustumMeasure((10.5, 20.2), (40.4, 49.8))
    assert _aabb_close(a, b, 1.5)
    assert not _aabb_close(a, b, 0.1)


def test_verify_fails_missing_frustum():
    director = CameraPoseDirector(
        hwnd=1,
        controller=_FakeController([]),
        capture=lambda: None,
        sleep=lambda _s: None,
        config={
            "verify": {"expected_aabb_width_map": 30.0, "aabb_width_tolerance_map": 5.0},
        },
    )
    result = director.verify(from_xy=(89.0, 82.0))
    assert not result.ok
    assert "frustum_missing" in result.failed_checks


def test_verify_passes_when_expected_unset(monkeypatch):
    """Width expectation is optional until Z7; north-up + frustum still required."""
    measure = FrustumMeasure((70.0, 70.0), (110.0, 95.0))
    director = CameraPoseDirector(
        hwnd=1,
        controller=_FakeController([]),
        capture=lambda: Image.new("RGB", (64, 64)),
        sleep=lambda _s: None,
        config={"verify": {"expected_aabb_width_map": None, "north_up_aspect_min": 0.5}},
        army_match_map=50.0,
    )
    monkeypatch.setattr(director, "measure_frustum", lambda: measure)
    result = director.verify(from_xy=(90.0, 82.0), measured=measure)
    assert result.ok


def test_verify_rejects_wrong_width(monkeypatch):
    measure = FrustumMeasure((0.0, 0.0), (100.0, 50.0))
    director = CameraPoseDirector(
        hwnd=1,
        controller=_FakeController([]),
        capture=lambda: Image.new("RGB", (8, 8)),
        sleep=lambda _s: None,
        config={
            "verify": {
                "expected_aabb_width_map": 40.0,
                "aabb_width_tolerance_map": 5.0,
                "north_up_aspect_min": 0.5,
            }
        },
    )
    result = director.verify(measured=measure)
    assert not result.ok
    assert "aabb_width" in result.failed_checks


def test_reset_zoom_saturates_in_then_steps_out():
    ctrl = _FakeController([])
    director = CameraPoseDirector(
        hwnd=1,
        controller=ctrl,
        capture=lambda: None,
        sleep=lambda _s: None,
        config={
            "bindings": {"zoom_out": "x", "zoom_in": "z", "point_to_north": "pageup"},
            "canonical_pose": {"zoom_steps_from_max_in": 2},
            "zoom_in_saturate_presses": 3,
        },
    )
    assert director.reset_zoom()
    assert ctrl.taps.count("z") == 5  # 3 + 2 extra
    assert ctrl.taps.count("x") == 2


def test_reset_zoom_stays_at_max_in_when_steps_unset():
    ctrl = _FakeController([])
    director = CameraPoseDirector(
        hwnd=1,
        controller=ctrl,
        capture=lambda: None,
        sleep=lambda _s: None,
        config={
            "bindings": {"zoom_out": "x", "zoom_in": "z"},
            "canonical_pose": {"zoom_steps_from_max_in": None},
            "zoom_in_saturate_presses": 2,
        },
    )
    assert director.reset_zoom()
    assert ctrl.taps.count("z") == 4
    assert ctrl.taps.count("x") == 0


def test_reset_rotation_uses_point_to_north():
    ctrl = _FakeController([])
    director = CameraPoseDirector(
        hwnd=1,
        controller=ctrl,
        capture=lambda: None,
        sleep=lambda _s: None,
        config={"bindings": {"point_to_north": "pageup"}},
    )
    assert director.reset_rotation() == "point_to_north"
    assert ctrl.taps == ["pageup"]


def test_quiesce_times_out_when_frustum_never_stable(monkeypatch):
    n = {"i": 0}

    def oscillating() -> FrustumMeasure:
        n["i"] += 1
        if n["i"] % 2:
            return FrustumMeasure((0.0, 0.0), (30.0, 20.0))
        return FrustumMeasure((0.0, 0.0), (50.0, 40.0))

    director = CameraPoseDirector(
        hwnd=1,
        controller=_FakeController([]),
        capture=lambda: Image.new("RGB", (8, 8)),
        sleep=lambda _s: None,
        config={"quiesce": {"stable_frames": 3, "timeout_s": 0.01, "aabb_epsilon_map": 1.0}},
    )
    monkeypatch.setattr(director, "measure_frustum", oscillating)
    assert director.quiesce() is None
