"""Console actuator with fair-play gate."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from comstar_game_ai.game_io.console.romeshell import RomeShell
from comstar_game_ai.game_io.fair_play import CommandClass, FairPlayGate
from comstar_game_ai.game_io.state_machine import GameStateDetector

_LOGGER = logging.getLogger(__name__)


@dataclass
class ConsoleActuator:
    """Send RomeShell commands after fair-play and state checks."""

    shell: RomeShell | None = None
    gate: FairPlayGate = field(default_factory=FairPlayGate)
    state: GameStateDetector = field(default_factory=GameStateDetector)
    blocked_commands: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.shell is None:
            self.shell = RomeShell()

    def send(self, command: str, *, require_campaign: bool = False, require_battle: bool = False) -> bool:
        command = command.strip()
        if not command:
            return False

        cls = self.gate.classify(command)
        if cls == CommandClass.NEVER:
            self.blocked_commands.append(command)
            _LOGGER.warning("blocked command (never): %s", command.split()[0])
            return False
        if not self.gate.allow(command):
            self.blocked_commands.append(command)
            _LOGGER.warning("blocked command (not allowed): %s", command.split()[0])
            return False

        if require_campaign and not self.state.allows_campaign_orders():
            _LOGGER.warning("campaign order refused — state=%s", self.state.state.value)
            return False
        if require_battle and not self.state.allows_battle_orders():
            _LOGGER.warning("battle order refused — state=%s", self.state.state.value)
            return False

        assert self.shell is not None
        return self.shell.send_command(command)

    @property
    def evaluation_tainted(self) -> bool:
        return self.gate.evaluation_tainted
