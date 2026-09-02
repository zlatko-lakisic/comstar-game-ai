"""Reactive single-step battle policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from comstar_game_ai.agent.directive import Directive, NEUTRAL_OBJECTIVE
from comstar_game_ai.game_io.battle.orders import BattleOrder, charge, hold_position
from comstar_game_ai.game_io.battle.unit_positions import BattlePositions, UnitPosition


@dataclass
class PolicyStep:
    action: str
    orders: list[BattleOrder]
    rationale: str = ""


class ReactivePolicy:
    """Pick one step of orders from directive plus current positions."""

    def __init__(self, player_alliance: int = 0) -> None:
        self._player_alliance = player_alliance

    def step(self, directive: Directive, positions: BattlePositions, tick: int = 0) -> PolicyStep:
        own = positions.by_alliance(self._player_alliance)
        enemy_alliance = 1 - self._player_alliance if self._player_alliance in (0, 1) else None
        enemies = positions.by_alliance(enemy_alliance) if enemy_alliance is not None else []

        if not own:
            return PolicyStep("noop", [], "no friendly units")

        objective = directive.intent.objective or NEUTRAL_OBJECTIVE
        if objective in ("hold", NEUTRAL_OBJECTIVE):
            orders = [hold_position(self._unit_key(u)) for u in own]
            return PolicyStep("hold", orders, f"hold per {objective}")

        if objective in ("annihilate", "win_cheaply", "break_and_pursue") and enemies:
            target = self._nearest_enemy(own[0], enemies)
            if target is not None:
                orders = [charge(self._unit_key(u), self._unit_key(target)) for u in own]
                return PolicyStep("charge", orders, f"press {objective}")

        orders = [hold_position(self._unit_key(u)) for u in own]
        return PolicyStep("hold", orders, "default hold")

    def _unit_key(self, unit: UnitPosition) -> tuple[int, int, int]:
        return (unit.alliance_index, unit.army_index, unit.unit_index)

    def _nearest_enemy(self, source: UnitPosition, enemies: list[UnitPosition]) -> UnitPosition | None:
        if not enemies:
            return None
        return min(enemies, key=lambda e: (e.x - source.x) ** 2 + (e.y - source.y) ** 2)
