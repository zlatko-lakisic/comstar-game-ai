"""Diff-based order actuator — issue only deltas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnitOrder:
    unit_id: str
    x: float
    y: float
    facing: float | None = None
    stance: str | None = None


@dataclass
class OrderDiff:
    move: list[UnitOrder] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def compute_order_diff(
    desired: dict[str, UnitOrder],
    current: dict[str, UnitOrder],
    *,
    position_epsilon: float = 1.0,
) -> OrderDiff:
    """Return orders that differ from current state."""
    diff = OrderDiff()
    desired_ids = set(desired)
    current_ids = set(current)

    for unit_id in sorted(desired_ids & current_ids):
        want = desired[unit_id]
        have = current[unit_id]
        if _positions_close(want, have, position_epsilon) and want.stance == have.stance:
            diff.unchanged.append(unit_id)
        else:
            diff.move.append(want)

    for unit_id in sorted(desired_ids - current_ids):
        diff.move.append(desired[unit_id])

    for unit_id in sorted(current_ids - desired_ids):
        diff.removed.append(unit_id)

    return diff


def _positions_close(a: UnitOrder, b: UnitOrder, epsilon: float) -> bool:
    return abs(a.x - b.x) <= epsilon and abs(a.y - b.y) <= epsilon


@dataclass
class DiffActuator:
    """Apply only changed orders via injected send callbacks."""

    send_move: Any = None

    def apply(self, diff: OrderDiff) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for order in diff.move:
            payload = {
                "type": "move",
                "unit_id": order.unit_id,
                "x": order.x,
                "y": order.y,
                "facing": order.facing,
                "stance": order.stance,
            }
            actions.append(payload)
            if self.send_move is not None:
                self.send_move(order)
        return actions
