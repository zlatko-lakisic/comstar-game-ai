"""Auto-resolve battle outcome estimate."""

from __future__ import annotations

from typing import Any

from comstar_game_ai.agent.predictors.game_data import UnitStats, unit_strength


def estimate_auto_resolve(
    own_units: list[tuple[UnitStats, int]],
    enemy_units: list[tuple[UnitStats, int]],
    *,
    difficulty_bonus: float = 0.0,
) -> dict[str, Any]:
    """Estimate pre-battle auto-resolve from aggregate strength."""
    own_power = sum(unit_strength(s, m) for s, m in own_units)
    enemy_power = sum(unit_strength(s, m) for s, m in enemy_units)
    enemy_power = max(enemy_power * (1.0 + difficulty_bonus), 1.0)
    ratio = own_power / enemy_power

    if ratio >= 1.3:
        outcome = "decisive_win"
        own_losses = 0.10
    elif ratio >= 1.05:
        outcome = "win"
        own_losses = 0.18
    elif ratio >= 0.85:
        outcome = "pyrrhic"
        own_losses = 0.35
    elif ratio >= 0.6:
        outcome = "loss"
        own_losses = 0.55
    else:
        outcome = "rout"
        own_losses = 0.75

    enemy_losses = min(0.95, own_losses + (ratio - 1.0) * 0.4)
    return {
        "predictor": "auto_resolve",
        "outcome": outcome,
        "own_losses": max(0.0, own_losses),
        "enemy_losses": max(0.0, enemy_losses),
        "strength_ratio": ratio,
    }
