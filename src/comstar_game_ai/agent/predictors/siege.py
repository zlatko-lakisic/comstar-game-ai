"""Siege duration stub (campaign)."""

from __future__ import annotations

from typing import Any


def estimate_siege_duration(
    *,
    garrison_strength: float,
    attacker_strength: float,
    wall_level: int = 1,
    has_siege_equipment: bool = False,
) -> dict[str, Any]:
    """Pragmatic turns-to-capture from strength and fortification."""
    defence = garrison_strength * (1.0 + 0.25 * wall_level)
    if has_siege_equipment:
        defence *= 0.75
    ratio = attacker_strength / max(defence, 1.0)
    if ratio >= 2.0:
        turns = 2
    elif ratio >= 1.2:
        turns = 4
    elif ratio >= 0.8:
        turns = 8
    else:
        turns = 16
    return {
        "predictor": "siege",
        "turns_to_capture": turns,
        "strength_ratio": ratio,
        "starvation_turns": turns + 4,
    }
