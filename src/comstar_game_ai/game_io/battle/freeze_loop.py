"""toggle_game_update freeze cycle for battle deliberation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from comstar_game_ai.game_io.battle.orders import BattleOrder, OrderIssuer
from comstar_game_ai.game_io.battle.unit_positions import BattlePositions, parse_unit_positions_file


@dataclass
class FreezeCycleConfig:
    tick_seconds: float = 3.0
    positions_filename: str = "comstar_unit_positions.txt"


class FreezeLoop:
    """One freeze cycle: toggle off, dump positions, decide, order, toggle on."""

    def __init__(
        self,
        *,
        run_console: Callable[[str], bool],
        positions_dir: Path | str,
        decide: Callable[[BattlePositions, int], list[BattleOrder]],
        issuer: OrderIssuer | None = None,
        config: FreezeCycleConfig | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._run_console = run_console
        self._positions_dir = Path(positions_dir)
        self._decide = decide
        self._issuer = issuer or OrderIssuer()
        self._config = config or FreezeCycleConfig()
        self._sleep = sleep or time.sleep
        self._tick = 0
        self._frozen = False

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def frozen(self) -> bool:
        return self._frozen

    def toggle_freeze(self) -> bool:
        ok = self._run_console("toggle_game_update")
        if ok:
            self._frozen = not self._frozen
        return ok

    def dump_positions(self) -> Path:
        path = self._positions_dir / self._config.positions_filename
        self._run_console(f"output_unit_positions {path}")
        return path

    def read_positions(self, path: Path | None = None) -> BattlePositions:
        file_path = path or (self._positions_dir / self._config.positions_filename)
        if not file_path.is_file():
            return BattlePositions(units=[])
        return parse_unit_positions_file(file_path)

    def run_cycle(self) -> bool:
        """Execute one freeze deliberation cycle."""
        if not self.toggle_freeze():
            return False
        try:
            pos_path = self.dump_positions()
            positions = self.read_positions(pos_path)
            orders = self._decide(positions, self._tick)
            if orders and not self._issuer.issue_many(orders):
                return False
            self._tick += 1
            return True
        finally:
            if self._frozen:
                self.toggle_freeze()

    def run_until(self, should_stop: Callable[[int, BattlePositions], bool], max_ticks: int = 10_000) -> int:
        """Run freeze cycles until should_stop returns True or max_ticks reached."""
        ticks_run = 0
        while ticks_run < max_ticks:
            if not self.run_cycle():
                break
            positions = self.read_positions()
            ticks_run += 1
            if should_stop(self._tick, positions):
                break
            self._sleep(self._config.tick_seconds)
        return ticks_run
