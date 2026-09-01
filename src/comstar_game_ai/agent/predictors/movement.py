"""Movement reachability stub (campaign)."""

from __future__ import annotations

from typing import Any


def estimate_reach(
    *,
    movement_points: float,
    terrain_cost_per_tile: float = 1.0,
    destination_distance: float,
) -> dict[str, Any]:
    """Estimate whether a destination is reachable this turn."""
    effective_cost = terrain_cost_per_tile * destination_distance
    reachable = movement_points >= effective_cost
    tiles_reachable = int(movement_points // max(terrain_cost_per_tile, 0.01))
    return {
        "predictor": "movement",
        "reachable": reachable,
        "tiles_reachable": tiles_reachable,
        "effective_cost": effective_cost,
        "movement_points": movement_points,
    }
