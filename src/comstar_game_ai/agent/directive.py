"""Directive contract parse and neutral fallback."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from comstar_game_ai.agent.campaign_vocab import (
    ADVANCING_OBJECTIVES,
    CAMPAIGN_OBJECTIVES,
    NEUTRAL_OBJECTIVE,
)

_LOGGER = logging.getLogger(__name__)

# Re-export so existing imports of directive.ADVANCING_OBJECTIVES keep working
# against the single vocabulary source.
__all__ = [
    "ADVANCING_OBJECTIVES",
    "BATTLE_OBJECTIVES",
    "CAMPAIGN_OBJECTIVES",
    "DIRECTIVE_OBSERVATIONS",
    "Directive",
    "DirectiveIntent",
    "HORIZONS",
    "JSON_OBJECT_RESPONSE_FORMAT",
    "NEUTRAL_OBJECTIVE",
    "battle_directive_schema",
    "campaign_directive_schema",
    "downgrade_infeasible",
    "neutral_directive",
    "parse_directive",
]

#: The only console reads a directive may ask for.
DIRECTIVE_OBSERVATIONS = frozenset({"list_characters", "list_units"})

#: What a battle directive may choose.
BATTLE_OBJECTIVES: tuple[str, ...] = (
    "hold",
    "fortify",
    "win_cheaply",
    "annihilate",
    "break_and_pursue",
)

HORIZONS: tuple[str, ...] = ("short", "normal", "long")

JSON_OBJECT_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}


def _directive_schema(objectives: tuple[str, ...]) -> dict[str, Any]:
    """Flat schema for battle (and legacy) constrained decoding."""
    return {
        "type": "object",
        "properties": {
            "objective": {"type": "string", "enum": list(objectives)},
            "reason": {"type": "string"},
            "horizon": {"type": "string", "enum": list(HORIZONS)},
            "risk_posture": {"type": "number"},
        },
        "required": ["objective", "reason"],
    }


def campaign_directive_schema() -> dict[str, Any]:
    # Lazy: campaign_contract imports Directive from this module.
    from comstar_game_ai.agent.campaign_contract import (
        campaign_directive_schema as _campaign_schema,
    )

    return _campaign_schema()


def battle_directive_schema() -> dict[str, Any]:
    return _directive_schema(BATTLE_OBJECTIVES)


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


def _coerce_directive_payload(text: str) -> tuple[dict[str, Any] | None, str]:
    """Find the JSON object in an answer, or say why there is none."""
    raw = str(text or "").strip()
    if not raw:
        return None, "empty"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return data, ""

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data, "unfenced_json"

    inline = re.search(r"\{.*\}", raw, re.DOTALL)
    if inline:
        try:
            data = json.loads(inline.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data, "extracted_json"

    return None, "malformed_json"


def parse_directive(text: str) -> Directive:
    """Parse a JSON directive, tolerating fences and surrounding prose.

    Accepts both the campaign contract (actor/target/because/expects) and the
    flat battle shape (objective/reason).
    """
    data, reason = _coerce_directive_payload(text)
    if data is None:
        return neutral_directive(reason or "malformed_json")
    if not isinstance(data, dict):
        return neutral_directive("not_object")
    if reason:
        _LOGGER.info("directive needed extraction from the answer (%s)", reason)

    # Prefer the campaign contract when actor/target/because are present.
    if any(k in data for k in ("actor", "target", "because", "expects")):
        from comstar_game_ai.agent.campaign_contract import parse_campaign_directive

        return parse_campaign_directive(text).to_legacy_directive()

    intent_raw = data.get("intent") or {}
    if not isinstance(intent_raw, dict):
        intent_raw = {}

    if "objective" not in intent_raw and data.get("objective"):
        intent_raw = {**intent_raw, "objective": data["objective"]}

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
        commentary=str(data.get("commentary") or data.get("reason") or data.get("because") or ""),
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
