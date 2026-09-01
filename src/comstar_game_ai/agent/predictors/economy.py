"""Economy projection stub (campaign)."""

from __future__ import annotations

from typing import Any


def estimate_income(
    *,
    settlements: int,
    avg_tax: float,
    trade_income: float = 0.0,
    upkeep: float = 0.0,
    turns: int = 1,
) -> dict[str, Any]:
    """Project net treasury delta over N turns."""
    gross = settlements * avg_tax + trade_income
    net_per_turn = gross - upkeep
    return {
        "predictor": "economy",
        "gross_per_turn": gross,
        "net_per_turn": net_per_turn,
        "projected_treasury_delta": net_per_turn * turns,
        "turns": turns,
    }
