"""Kill switch, deadman timer, and human override stubs."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)


class ControlMode(str, Enum):
    IDLE = "idle"
    AGENT = "agent"
    HANDING_BACK = "handing_back"
    KILLED = "killed"


@dataclass
class SafetyController:
    """Process A safety layer — release input on every exit path."""

    mode: ControlMode = ControlMode.IDLE
    deadman_seconds: float = 10.0
    on_kill: Callable[[], None] | None = None
    on_handback: Callable[[], None] | None = None
    _deadman_deadline: float | None = field(default=None, init=False)
    _timer: threading.Timer | None = field(default=None, init=False)
    # Reentrant: takeover() holds the lock and calls arm_deadman(), which takes it
    # again. With a plain Lock that deadlocked forever, and because the lock was then
    # never released the kill switch could no longer run — the one thing that must
    # always work.
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        cfg = load_config().get("safety", {})
        self.deadman_seconds = float(cfg.get("deadman_seconds", self.deadman_seconds))

    def arm_deadman(self) -> None:
        with self._lock:
            self._disarm_timer()
            self._deadman_deadline = time.monotonic() + self.deadman_seconds
            self._timer = threading.Timer(self.deadman_seconds, self._deadman_fired)
            self._timer.daemon = True
            self._timer.start()

    def pet_deadman(self) -> None:
        if self.mode == ControlMode.AGENT:
            self.arm_deadman()

    def _disarm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._deadman_deadline = None

    def _deadman_fired(self) -> None:
        _LOGGER.warning("deadman timer fired — invoking kill")
        self.kill(reason="deadman")

    def takeover(self) -> None:
        with self._lock:
            self.mode = ControlMode.AGENT
            self.arm_deadman()

    def handback(self) -> None:
        with self._lock:
            self.mode = ControlMode.HANDING_BACK
            self._disarm_timer()
        if self.on_handback:
            self.on_handback()
        with self._lock:
            self.mode = ControlMode.IDLE

    def kill(self, *, reason: str = "manual") -> None:
        with self._lock:
            self.mode = ControlMode.KILLED
            self._disarm_timer()
        _LOGGER.warning("kill switch: %s", reason)
        if self.on_kill:
            self.on_kill()

    def human_override(self, *, mouse_moved: bool = False, foreground_lost: bool = False) -> bool:
        """Return True if human activity should trigger kill."""
        if mouse_moved or foreground_lost:
            self.kill(reason="human_override")
            return True
        return False

    @property
    def agent_active(self) -> bool:
        return self.mode == ControlMode.AGENT
