"""The third way agent control ends: the human takes the machine back."""

from __future__ import annotations

from comstar_game_ai.game_io.safety import ControlMode, SafetyController
from comstar_game_ai.game_io.watchdog import HumanOverrideWatch

GAME_HWND = 0x2222
OTHER_HWND = 0x3333


def _watch(**kwargs) -> HumanOverrideWatch:
    safety = SafetyController(deadman_seconds=30.0)
    released: list[str] = []
    safety.on_kill = lambda: released.append("kill")
    watch = HumanOverrideWatch(safety=safety, game_hwnd=GAME_HWND, **kwargs)
    watch._released = released  # type: ignore[attr-defined]
    return watch


def test_disarmed_by_default():
    """Both triggers are unvalidated, so nothing arms itself silently."""
    watch = _watch()
    assert not watch.armed
    watch.safety.takeover()
    assert watch.reason_to_kill(foreground=OTHER_HWND, pointer=(999, 999)) is None


def test_starting_a_disarmed_watch_spawns_no_thread():
    watch = _watch()
    watch.start()
    assert watch._thread is None


def test_foreground_loss_ends_control_when_armed():
    watch = _watch(on_foreground_loss=True)
    watch.safety.takeover()
    assert watch.reason_to_kill(foreground=OTHER_HWND) == "foreground_lost"


def test_the_game_keeping_focus_is_not_an_override():
    watch = _watch(on_foreground_loss=True)
    watch.safety.takeover()
    assert watch.reason_to_kill(foreground=GAME_HWND) is None


def test_a_momentary_focus_gap_is_not_an_override():
    """Rome reports no foreground window between loading screens."""
    watch = _watch(on_foreground_loss=True)
    watch.safety.takeover()
    assert watch.reason_to_kill(foreground=0) is None


def test_nothing_trips_while_the_agent_is_not_driving():
    """Before takeover the human is supposed to be using the mouse."""
    watch = _watch(on_foreground_loss=True, on_mouse=True)
    assert watch.safety.mode is ControlMode.IDLE
    assert watch.reason_to_kill(foreground=OTHER_HWND, pointer=(500, 500)) is None


def test_mouse_drift_beyond_tolerance_ends_control():
    watch = _watch(on_mouse=True)
    watch.safety.takeover()
    watch.expect_pointer((100, 100))
    assert watch.reason_to_kill(pointer=(400, 100)) == "mouse_moved"


def test_the_agents_own_click_is_not_a_human_takeover():
    watch = _watch(on_mouse=True)
    watch.safety.takeover()
    watch.expect_pointer((100, 100))
    assert watch.reason_to_kill(pointer=(100, 100)) is None


def test_a_few_pixels_of_jitter_is_tolerated():
    watch = _watch(on_mouse=True, tolerance_px=6)
    watch.safety.takeover()
    watch.expect_pointer((100, 100))
    assert watch.reason_to_kill(pointer=(104, 97)) is None


def test_mouse_trigger_stays_quiet_until_a_position_is_declared():
    """With no baseline the watchdog cannot tell who moved the cursor."""
    watch = _watch(on_mouse=True)
    watch.safety.takeover()
    assert watch.reason_to_kill(pointer=(1, 1)) is None


def test_check_kills_and_releases_input():
    watch = _watch(on_foreground_loss=True)
    watch.safety.takeover()

    def foreground_is_elsewhere(**_kwargs):
        return "foreground_lost"

    watch.reason_to_kill = foreground_is_elsewhere  # type: ignore[method-assign]
    assert watch.check() == "foreground_lost"
    assert watch.safety.mode is ControlMode.KILLED
    assert watch._released == ["kill"]  # type: ignore[attr-defined]


def test_from_config_reads_the_safety_block(monkeypatch):
    import comstar_game_ai.game_io.watchdog as watchdog

    monkeypatch.setattr(
        watchdog,
        "load_config",
        lambda: {
            "safety": {
                "human_override_on_foreground_loss": True,
                "human_override_on_mouse": True,
                "human_override_tolerance_px": 12,
            }
        },
    )
    watch = HumanOverrideWatch.from_config(SafetyController(deadman_seconds=30.0), GAME_HWND)
    assert watch.armed
    assert watch.on_foreground_loss and watch.on_mouse
    assert watch.tolerance_px == 12


def test_from_config_defaults_to_disarmed(monkeypatch):
    import comstar_game_ai.game_io.watchdog as watchdog

    monkeypatch.setattr(watchdog, "load_config", lambda: {})
    watch = HumanOverrideWatch.from_config(SafetyController(deadman_seconds=30.0), GAME_HWND)
    assert not watch.armed


def test_shipped_config_leaves_the_triggers_disarmed():
    """Guards the default itself: arming these must be an explicit edit."""
    from comstar_game_ai.shared.config import load_config

    safety = load_config().get("safety") or {}
    assert safety.get("human_override_on_foreground_loss") is False
    assert safety.get("human_override_on_mouse") is False
