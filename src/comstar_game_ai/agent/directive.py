"""Directive contract parse and neutral fallback."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

NEUTRAL_OBJECTIVE = "hold"

#: Objectives that permit advancing a character this turn. "hold" — the neutral
#: fallback, and what a silent or malformed AO answer becomes — is deliberately not
#: here: when nobody is reasoning, the army stays where it is.
ADVANCING_OBJECTIVES = frozenset(
    {"expand", "advance", "attack", "take_settlement", "besiege", "pressure"}
)

#: The only console reads a directive may ask for. An unrecognised focus action is
#: ignored rather than sent: the fair-play gate should never be the first thing
#: standing between a model and Rome.
DIRECTIVE_OBSERVATIONS = frozenset({"list_characters", "list_units"})

#: What a campaign directive may choose. Offering exactly this list — and no battle
#: verbs — is what makes the enum worth constraining on: every value here means
#: something to the planner, and four of the seven decide whether an army moves.
CAMPAIGN_OBJECTIVES: tuple[str, ...] = (
    "hold",
    "fortify",
    "expand",
    "attack",
    "take_settlement",
    "besiege",
)

#: What a battle directive may choose.
BATTLE_OBJECTIVES: tuple[str, ...] = (
    "hold",
    "fortify",
    "win_cheaply",
    "annihilate",
    "break_and_pursue",
)

HORIZONS: tuple[str, ...] = ("short", "normal", "long")

#: Selects the engine's JSON mode, which is a different pipeline rather than a hint:
#: it skips the crew and the prose sanitizer and asks the model for native structured
#: output. Without it a directive comes back through a sanitizer whose job is to make
#: an answer speakable — it unwraps a JSON object to the one field a voice assistant
#: should read aloud, so nine fields arrived as the single word `normal`.
JSON_OBJECT_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}


def _directive_schema(objectives: tuple[str, ...]) -> dict[str, Any]:
    """Schema for one directive, shaped for Ollama's constrained decoding.

    Small on purpose, in both directions. The engine puts the schema in the prompt
    *and* compiles it into a decoding grammar, so every field costs tokens twice —
    and on a shared GPU a thousand-token prompt is most of a minute before the first
    token of the answer.

    Flat, and free of arrays, for a harder reason. Under a grammar the model is only
    ever offered valid next tokens, which means an unbounded field is an invitation
    to keep going: the same prompt that answered in 115 tokens once ran to 11,400 on
    the next call, repeating itself inside an array, and was still going when the
    client gave up. Enums cannot do that, and a single free-text `reason` is the one
    place left where it could — worth keeping, because a decision with no stated
    reason cannot be reviewed.

    Only the decision and its reason are required. A required field is *generated*
    under constrained decoding rather than considered, so requiring a threshold would
    collect an invented number where the parser's default is the honest answer.
    """
    return {
        "type": "object",
        "properties": {
            # Objective first: the shortest path to a complete, valid answer, since
            # nothing is usable until the closing brace arrives.
            "objective": {"type": "string", "enum": list(objectives)},
            "reason": {"type": "string"},
            "horizon": {"type": "string", "enum": list(HORIZONS)},
            "risk_posture": {"type": "number"},
        },
        "required": ["objective", "reason"],
    }


def campaign_directive_schema() -> dict[str, Any]:
    return _directive_schema(CAMPAIGN_OBJECTIVES)


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
    """Find the JSON object in an answer, or say why there is none.

    Fences and surrounding prose are tolerated because a model that ignores the
    format still produced reasoning worth reading. A bare word is not: this used to
    map a lone `normal` onto "hold" and scan loose prose for any objective-shaped
    word, which turned sanitizer debris into a decision — an invented directive that
    the store, the overlay and the run report all presented as a real one. A
    directive we cannot read is a directive we do not have, and `hold` reached
    honestly through `neutral_directive` says so.
    """
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
    """Parse a JSON directive, tolerating fences and surrounding prose."""
    data, reason = _coerce_directive_payload(text)
    if data is None:
        return neutral_directive(reason or "malformed_json")
    if not isinstance(data, dict):
        return neutral_directive("not_object")
    if reason:
        # Readable, but the answer arrived wrapped — worth seeing, since JSON mode
        # is supposed to make that impossible.
        _LOGGER.info("directive needed extraction from the answer (%s)", reason)

    intent_raw = data.get("intent") or {}
    if not isinstance(intent_raw, dict):
        intent_raw = {}

    # Two shapes are read here. The schema asks for a flat `objective`/`reason`,
    # which is what a constrained answer looks like; the nested `intent` block is the
    # full contract, still used by the battle plays and by anything hand-written.
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
        commentary=str(data.get("commentary") or data.get("reason") or ""),
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
