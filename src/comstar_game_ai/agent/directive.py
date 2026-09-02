"""Directive contract parse and neutral fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


NEUTRAL_OBJECTIVE = "hold"


@dataclass
class DirectiveIntent:
    objective: str = NEUTRAL_OBJECTIVE
    acceptable_own_losses: float = 0.35
    required_enemy_losses: float = 0.50
    hold_for_seconds: float | None = None
    preserve: list[str] = field(default_factory=list)
    abort_if: dict[str, Any] = field(default_factory=dict)


@dataclass
class Directive:
    intent: DirectiveIntent
    horizon: str = "normal"
    risk_posture: float = 0.0
    focus_actions: list[str] = field(default_factory=list)
    avoid_actions: list[str] = field(default_factory=list)
    opponent_read: dict[str, Any] = field(default_factory=dict)
    commentary: str = ""
    valid_for_plies: int = 4
    play_id: str | None = None
    play_params: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def neutral_directive(reason: str = "") -> Directive:
    return Directive(
        intent=DirectiveIntent(objective=NEUTRAL_OBJECTIVE),
        commentary=reason,
        valid_for_plies=1,
    )


def parse_directive(text: str) -> Directive:
    """Parse JSON directive; malformed input returns neutral."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return neutral_directive("malformed_json")
    if not isinstance(data, dict):
        return neutral_directive("not_object")

    intent_raw = data.get("intent") or {}
    if not isinstance(intent_raw, dict):
        intent_raw = {}

    intent = DirectiveIntent(
        objective=str(intent_raw.get("objective") or NEUTRAL_OBJECTIVE),
        acceptable_own_losses=float(intent_raw.get("acceptable_own_losses", 0.35)),
        required_enemy_losses=float(intent_raw.get("required_enemy_losses", 0.50)),
        hold_for_seconds=intent_raw.get("hold_for_seconds"),
        preserve=[str(x) for x in (intent_raw.get("preserve") or [])],
        abort_if=dict(intent_raw.get("abort_if") or {}),
    )

    play_params = data.get("play_params") or {}
    if not isinstance(play_params, dict):
        play_params = {}

    return Directive(
        intent=intent,
        horizon=str(data.get("horizon") or "normal"),
        risk_posture=float(data.get("risk_posture", 0.0)),
        focus_actions=[str(x) for x in (data.get("focus_actions") or [])],
        avoid_actions=[str(x) for x in (data.get("avoid_actions") or [])],
        opponent_read=dict(data.get("opponent_read") or {}),
        commentary=str(data.get("commentary") or ""),
        valid_for_plies=int(int(data.get("valid_for_plies", 4))),
        play_id=(str(data["play_id"]) if data.get("play_id") else None),
        play_params=play_params,
        raw=data,
    )


def downgrade_infeasible(directive: Directive, own_strength: float, enemy_strength: float) -> Directive:
    """Downgrade annihilation when force ratio is unfavorable."""
    if enemy_strength <= 0:
        return directive
    ratio = own_strength / enemy_strength
    if directive.intent.objective == "annihilate" and ratio < 0.8:
        directive.intent.objective = "win_cheaply"
        directive.commentary = (directive.commentary + " [downgraded: force ratio]").strip()
    return directive
