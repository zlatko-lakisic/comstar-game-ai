"""Morale and fatigue stubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MoraleEstimate:
    will_rout: bool
    morale_after: float
    fatigue_after: float


def estimate_morale(
    *,
    current_morale: float,
    current_fatigue: float,
    casualties_fraction: float,
    flank_exposed: bool = False,
    general_nearby: bool = False,
) -> MoraleEstimate:
    """Pragmatic morale tick from casualties and modifiers."""
    morale_hit = casualties_fraction * 35.0
    if flank_exposed:
        morale_hit += 12.0
    if general_nearby:
        morale_hit -= 8.0
    fatigue_after = min(100.0, current_fatigue + casualties_fraction * 20.0 + 2.0)
    morale_after = max(0.0, current_morale - morale_hit + (4.0 if general_nearby else 0.0))
    return MoraleEstimate(
        will_rout=morale_after < 15.0,
        morale_after=morale_after,
        fatigue_after=fatigue_after,
    )


def estimate_morale_dict(
    *,
    current_morale: float,
    current_fatigue: float,
    casualties_fraction: float,
    flank_exposed: bool = False,
    general_nearby: bool = False,
) -> dict[str, Any]:
    est = estimate_morale(
        current_morale=current_morale,
        current_fatigue=current_fatigue,
        casualties_fraction=casualties_fraction,
        flank_exposed=flank_exposed,
        general_nearby=general_nearby,
    )
    return {
        "predictor": "morale",
        "will_rout": est.will_rout,
        "morale_after": est.morale_after,
        "fatigue_after": est.fatigue_after,
    }
