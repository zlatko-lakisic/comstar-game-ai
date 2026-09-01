"""Battle orchestration: freeze loop, policy, predictors, after-action."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from comstar_game_ai.agent.directive import Directive, neutral_directive
from comstar_game_ai.agent.predictors.auto_resolve import estimate_auto_resolve
from comstar_game_ai.agent.predictors.game_data import load_unit_db
from comstar_game_ai.agent.predictors.log import PredictionLog
from comstar_game_ai.agent.predictors.melee import estimate_melee_dict
from comstar_game_ai.agent.predictors.morale import estimate_morale_dict
from comstar_game_ai.agent.reactive.plays import PlaysExecutor
from comstar_game_ai.agent.reactive.policy import ReactivePolicy
from comstar_game_ai.agent.records.after_action import build_after_action
from comstar_game_ai.game_io.battle.freeze_loop import FreezeLoop
from comstar_game_ai.game_io.battle.orders import BattleOrder, OrderIssuer, hold_position
from comstar_game_ai.game_io.battle.unit_positions import BattlePositions
from comstar_game_ai.shared.config import repo_root
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

_LOGGER = logging.getLogger(__name__)
_SAMPLE_UNITS = repo_root() / "tests" / "fixtures" / "edu" / "sample_units.json"


@dataclass
class BattleDriverConfig:
    max_ticks: int = 120
    tick_seconds: float = 3.0
    positions_dir: Path = field(default_factory=lambda: Path("data/runtime/battle"))
    prediction_log_path: Path = field(default_factory=lambda: Path("data/runtime/predictions.jsonl"))
    player_alliance: int = 0


class BattleDriver:
    """Run a battle at fixed tick with reactive policy and predictor logging."""

    def __init__(
        self,
        *,
        run_console: Callable[[str], bool],
        execute_order: Callable[[BattleOrder], bool] | None = None,
        directive: Directive | None = None,
        config: BattleDriverConfig | None = None,
        on_tick: Callable[[int, list[BattleOrder]], None] | None = None,
    ) -> None:
        self._run_console = run_console
        self._config = config or BattleDriverConfig()
        self._directive = directive or neutral_directive()
        self._policy = ReactivePolicy(player_alliance=self._config.player_alliance)
        self._plays = PlaysExecutor()
        self._prediction_log = PredictionLog(self._config.prediction_log_path)
        self._battle_id = uuid.uuid4().hex[:12]
        self._on_tick = on_tick
        self._orders_issued: list[BattleOrder] = []
        self._play_step = 0
        self._unit_db = load_unit_db(_SAMPLE_UNITS) if _SAMPLE_UNITS.is_file() else {}

        def on_order(order: BattleOrder) -> bool:
            self._orders_issued.append(order)
            if execute_order is not None:
                return execute_order(order)
            return True

        self._issuer = OrderIssuer(on_order=on_order)

    @property
    def battle_id(self) -> str:
        return self._battle_id

    def set_directive(self, directive: Directive) -> None:
        self._directive = directive

    def _log_predictors(self, own_str: float, enemy_str: float, tick: int) -> None:
        if self._unit_db:
            principes = self._unit_db.get("roman_principes")
            warband = self._unit_db.get("barbarian_warband")
            if principes and warband:
                melee_id = self._prediction_log.log_prediction(
                    "melee",
                    estimate_melee_dict(principes, warband, attacker_men=80, defender_men=80),
                    context={"tick": tick, "battle_id": self._battle_id},
                )
                self._prediction_log.record_outcome(melee_id, {"own_strength": own_str, "enemy_strength": enemy_str})

                own_units = [(principes, 120)]
                enemy_units = [(warband, max(1, int(enemy_str)))]
                ar_id = self._prediction_log.log_prediction(
                    "auto_resolve",
                    estimate_auto_resolve(own_units, enemy_units),
                    context={"tick": tick},
                )
                self._prediction_log.record_outcome(ar_id, {"ratio": own_str / max(enemy_str, 1.0)})

        morale_id = self._prediction_log.log_prediction(
            "morale",
            estimate_morale_dict(
                current_morale=50,
                current_fatigue=20,
                casualties_fraction=min(0.5, tick * 0.01),
            ),
            context={"tick": tick},
        )
        self._prediction_log.record_outcome(morale_id, {"own": own_str, "enemy": enemy_str})

    def _decide(self, positions: BattlePositions, tick: int) -> list[BattleOrder]:
        own = positions.by_alliance(self._config.player_alliance)
        enemy_alliance = 1 - self._config.player_alliance
        enemies = positions.by_alliance(enemy_alliance)
        own_str = sum(u.strength for u in own)
        enemy_str = sum(u.strength for u in enemies) or 1.0

        self._log_predictors(own_str, enemy_str, tick)

        if self._directive.play_id:
            play_ok = self._plays.run(self._directive.play_id, self._directive.play_params)
            if play_ok and own:
                orders = [hold_position((u.alliance_index, u.army_index, u.unit_index)) for u in own[:3]]
                if self._on_tick:
                    self._on_tick(tick, orders)
                return orders

        step = self._policy.step(self._directive, positions, tick)
        if self._on_tick:
            self._on_tick(tick, step.orders)
        return step.orders

    def run(self) -> dict[str, object]:
        """Run battle ticks until max_ticks or positions empty."""
        self._config.positions_dir.mkdir(parents=True, exist_ok=True)
        loop = FreezeLoop(
            run_console=self._run_console,
            positions_dir=self._config.positions_dir,
            decide=self._decide,
            issuer=self._issuer,
        )
        loop._config.tick_seconds = self._config.tick_seconds

        def stop(_tick: int, positions: BattlePositions) -> bool:
            if _tick >= self._config.max_ticks:
                return True
            return len(positions.units) == 0

        ticks = loop.run_until(stop, max_ticks=self._config.max_ticks)
        observed = {
            "outcome": "win" if ticks > 0 else "unknown",
            "own_losses": 0.0,
            "enemy_losses": 0.0,
            "ticks": ticks,
            "orders_issued": len(self._orders_issued),
        }
        predicted = {"outcome": self._directive.intent.objective, "own_losses": 0.2}
        record = build_after_action(
            battle_id=self._battle_id,
            intent_objective=self._directive.intent.objective,
            predicted=predicted,
            observed=observed,
        )
        return {
            "battle_id": self._battle_id,
            "ticks": ticks,
            "orders": len(self._orders_issued),
            "after_action": record.to_dict(),
        }


def load_battle_directive(store: DirectiveStore | None = None) -> Directive:
    stored = (store or DirectiveStore()).read()
    if stored is None:
        return neutral_directive()
    return stored.to_directive()
