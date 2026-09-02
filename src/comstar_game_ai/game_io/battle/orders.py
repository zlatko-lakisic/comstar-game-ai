"""Battle order issuance stub (hotkeys / mouse in later phases)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class BattleOrder:
    action: str
    unit_key: tuple[int, int, int] | None = None
    params: dict[str, Any] = field(default_factory=dict)


class OrderIssuer:
    """Queue and dispatch battle orders; verified externally by Process A."""

    def __init__(self, on_order: Callable[[BattleOrder], bool] | None = None) -> None:
        self._on_order = on_order or (lambda _o: True)
        self._pending: list[BattleOrder] = []

    def issue(self, order: BattleOrder) -> bool:
        self._pending.append(order)
        return self._on_order(order)

    def issue_many(self, orders: list[BattleOrder]) -> bool:
        return all(self.issue(order) for order in orders)

    def clear(self) -> None:
        self._pending.clear()

    @property
    def pending(self) -> list[BattleOrder]:
        return list(self._pending)


def hold_position(unit_key: tuple[int, int, int]) -> BattleOrder:
    return BattleOrder("hold_position", unit_key=unit_key)


def charge(unit_key: tuple[int, int, int], target: tuple[int, int, int] | None = None) -> BattleOrder:
    params: dict[str, Any] = {}
    if target is not None:
        params["target"] = target
    return BattleOrder("charge", unit_key=unit_key, params=params)


def move_to_orientation(
    unit_key: tuple[int, int, int],
    *,
    x: float,
    y: float,
    facing_deg: float,
) -> BattleOrder:
    return BattleOrder(
        "move_to_orientation",
        unit_key=unit_key,
        params={"x": x, "y": y, "facing_deg": facing_deg},
    )
