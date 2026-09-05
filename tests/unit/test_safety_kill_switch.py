"""Phase 3 acceptance: the kill switch releases everything from any state."""

from __future__ import annotations

import threading

import pytest

from comstar_game_ai.game_io.safety import ControlMode, SafetyController

ALL_STATES = [
    ControlMode.IDLE,
    ControlMode.AGENT,
    ControlMode.HANDING_BACK,
    ControlMode.KILLED,
]


def _controller(**kwargs):
    return SafetyController(deadman_seconds=30.0, **kwargs)


def _in_state(state: ControlMode) -> SafetyController:
    released: list[str] = []
    controller = _controller(on_kill=lambda: released.append("kill"))
    if state is ControlMode.AGENT:
        controller.takeover()
    elif state is ControlMode.HANDING_BACK:
        controller.mode = ControlMode.HANDING_BACK
    elif state is ControlMode.KILLED:
        controller.kill(reason="setup")
        released.clear()
    controller._released = released  # type: ignore[attr-defined]
    return controller


def _run_with_timeout(fn, timeout_s: float = 3.0) -> bool:
    """True if `fn` returned in time. A blocked safety layer must fail, not hang."""
    done = threading.Event()

    def target() -> None:
        fn()
        done.set()

    threading.Thread(target=target, daemon=True).start()
    return done.wait(timeout_s)


def test_takeover_does_not_deadlock():
    """takeover() held the lock and called arm_deadman(), which took it again.

    With a non-reentrant lock this hung forever and never released the lock, so the
    kill switch could not run afterwards either.
    """
    controller = _controller()
    assert _run_with_timeout(controller.takeover), "takeover() deadlocked"
    assert controller.mode is ControlMode.AGENT
    assert controller.agent_active


def test_handback_does_not_deadlock():
    controller = _controller()
    controller.takeover()
    assert _run_with_timeout(controller.handback), "handback() deadlocked"
    assert controller.mode is ControlMode.IDLE


@pytest.mark.parametrize("state", ALL_STATES, ids=lambda s: s.value)
def test_kill_releases_from_any_state(state: ControlMode):
    controller = _in_state(state)
    assert _run_with_timeout(lambda: controller.kill(reason="test")), "kill() blocked"
    assert controller.mode is ControlMode.KILLED
    assert controller._released == ["kill"], "input was not released"


@pytest.mark.parametrize("state", ALL_STATES, ids=lambda s: s.value)
def test_kill_is_idempotent_from_any_state(state: ControlMode):
    """The hotkey can be hit repeatedly; each press must still release."""
    controller = _in_state(state)
    controller.kill(reason="first")
    controller.kill(reason="second")
    assert controller.mode is ControlMode.KILLED
    assert controller._released == ["kill", "kill"]


def test_kill_disarms_the_deadman():
    controller = _controller()
    controller.takeover()
    assert controller._timer is not None
    controller.kill(reason="test")
    assert controller._timer is None


def test_petting_the_deadman_after_kill_does_not_revive_the_agent():
    controller = _controller()
    controller.takeover()
    controller.kill(reason="test")
    controller.pet_deadman()
    assert controller.mode is ControlMode.KILLED
    assert controller._timer is None
    assert not controller.agent_active


def test_deadman_fires_a_kill():
    released: list[str] = []
    controller = SafetyController(deadman_seconds=0.05, on_kill=lambda: released.append("kill"))
    controller.deadman_seconds = 0.05
    controller.takeover()
    deadline = threading.Event()
    deadline.wait(1.0)
    assert controller.mode is ControlMode.KILLED
    assert released == ["kill"]


def test_human_override_kills_on_mouse_or_lost_foreground():
    for kwargs in ({"mouse_moved": True}, {"foreground_lost": True}):
        released: list[str] = []
        controller = _controller(on_kill=lambda: released.append("kill"))
        controller.takeover()
        assert controller.human_override(**kwargs) is True
        assert controller.mode is ControlMode.KILLED
        assert released == ["kill"]


def test_human_override_is_quiet_when_nothing_happened():
    controller = _controller()
    controller.takeover()
    assert controller.human_override() is False
    assert controller.mode is ControlMode.AGENT
