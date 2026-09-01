"""Simple melee outcome estimate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from comstar_game_ai.agent.predictors.game_data import UnitStats, unit_strength


@dataclass
class MeleeEstimate:
    attacker_wins: bool
    attacker_casualty_rate: float
    defender_casualty_rate: float
    confidence: float


def estimate_melee(
    attacker: UnitStats,
    defender: UnitStats,
    *,
    attacker_men: int,
    defender_men: int,
    charging: bool = False,
) -> MeleeEstimate:
    """Pragmatic one-step melee from published-style stat terms."""
    atk = unit_strength(attacker, attacker_men)
    dfn = unit_strength(defender, defender_men)
    if charging:
        atk *= 1.0 + attacker.charge_bonus / 100.0
    ratio = atk / max(dfn, 1.0)

    attacker_wins = ratio >= 1.0
    if ratio >= 1.5:
        atk_loss, def_loss = 0.08, 0.25
    elif ratio >= 1.0:
        atk_loss, def_loss = 0.15, 0.20
    elif ratio >= 0.7:
        atk_loss, def_loss = 0.22, 0.12
    else:
        atk_loss, def_loss = 0.30, 0.08

    confidence = min(0.95, 0.5 + abs(ratio - 1.0) * 0.3)
    return MeleeEstimate(
        attacker_wins=attacker_wins,
        attacker_casualty_rate=atk_loss,
        defender_casualty_rate=def_loss,
        confidence=confidence,
    )


def estimate_melee_dict(
    attacker: UnitStats,
    defender: UnitStats,
    *,
    attacker_men: int,
    defender_men: int,
    charging: bool = False,
) -> dict[str, Any]:
    est = estimate_melee(
        attacker,
        defender,
        attacker_men=attacker_men,
        defender_men=defender_men,
        charging=charging,
    )
    return {
        "predictor": "melee",
        "attacker_wins": est.attacker_wins,
        "attacker_casualty_rate": est.attacker_casualty_rate,
        "defender_casualty_rate": est.defender_casualty_rate,
        "confidence": est.confidence,
    }
