"""Human-override watchdog: kill agent control when the human takes the machine back.

docs/design/host-overlay-ui.md lists three ways control ends — hotkey, deadman,
and human activity. This is the third.

Both triggers ship **disabled by default**. They cannot be validated without a
live campaign, and a false positive here aborts a run in progress, so arming them
is a deliberate choice made by config rather than a default inherited silently:

  safety.human_override_on_foreground_loss
  safety.human_override_on_mouse

Foreground loss is the safer of the two and the one to arm first. Mouse motion is
harder: the agent moves the cursor itself, so the watchdog can only tell human
motion from synthetic motion if every synthetic move is declared through
`expect_pointer`. Until every input path does that, an armed mouse trigger would
read the agent's own clicks as a human grabbing the mouse.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field

from comstar_game_ai.game_io.safety import SafetyController
from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)

if sys.platform == "win32":
    import win32gui
else:  # pragma: no cover - Windows only
    win32gui = None  # type: ignore[assignment]


def foreground_window() -> int:
    if win32gui is None:
        return 0
    try:
        return int(win32gui.GetForegroundWindow())
    except Exception:
        return 0


def cursor_position() -> tuple[int, int] | None:
    if win32gui is None:
        return None
    try:
        return tuple(win32gui.GetCursorPos())  # type: ignore[return-value]
    except Exception:
        return None


@dataclass
class HumanOverrideWatch:
    """Polls for signs a human took over, and kills agent control if so."""

    safety: SafetyController
    game_hwnd: int | None = None
    on_foreground_loss: bool = False
    on_mouse: bool = False
    tolerance_px: int = 6
    poll_seconds: float = 0.25
    _expected_pointer: tuple[int, int] | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)

    @classmethod
    def from_config(cls, safety: SafetyController, game_hwnd: int | None) -> HumanOverrideWatch:
        cfg = load_config().get("safety") or {}
        return cls(
            safety=safety,
            game_hwnd=game_hwnd,
            on_foreground_loss=bool(cfg.get("human_override_on_foreground_loss", False)),
            on_mouse=bool(cfg.get("human_override_on_mouse", False)),
            tolerance_px=int(cfg.get("human_override_tolerance_px", 6)),
        )

    @property
    def armed(self) -> bool:
        return self.on_foreground_loss or self.on_mouse

    def expect_pointer(self, point: tuple[int, int] | None) -> None:
        """Declare where the agent just put the cursor.

        Without this the watchdog cannot distinguish the agent's own clicks from a
        human grabbing the mouse, which is why the mouse trigger stays disabled
        until every input path calls it.
        """
        self._expected_pointer = point

    def reason_to_kill(
        self,
        *,
        foreground: int | None = None,
        pointer: tuple[int, int] | None = None,
    ) -> str | None:
        """Why control should end, or None. Pure enough to test with fake inputs."""
        if not self.safety.agent_active:
            return None

        if self.on_foreground_loss and self.game_hwnd:
            current = foreground_window() if foreground is None else foreground
            # A zero handle means nothing has focus, which happens transiently
            # while the game switches between loading screens; not a takeover.
            if current and current != self.game_hwnd:
                return "foreground_lost"

        if self.on_mouse:
            observed = cursor_position() if pointer is None else pointer
            expected = self._expected_pointer
            if observed is not None and expected is not None:
                drifted = max(abs(observed[0] - expected[0]), abs(observed[1] - expected[1]))
                if drifted > self.tolerance_px:
                    return "mouse_moved"

        return None

    def check(self) -> str | None:
        reason = self.reason_to_kill()
        if reason is None:
            return None
        _LOGGER.warning("human override: %s — killing agent control", reason)
        self.safety.human_override(
            mouse_moved=reason == "mouse_moved",
            foreground_lost=reason == "foreground_lost",
        )
        return reason

    def start(self) -> None:
        if not self.armed or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            if self.check() is not None:
                return

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
