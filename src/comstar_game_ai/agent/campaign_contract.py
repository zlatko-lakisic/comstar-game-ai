"""Campaign directive contract — parse, validate, commit window, leak check.

Campaign counterpart to the battle contract in cursor-handoff.md §8.3.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from comstar_game_ai.agent.campaign_vocab import (
    ADVANCING_OBJECTIVES,
    CAMPAIGN_OBJECTIVES,
    GARRISON_AT_ARRIVAL,
    NEUTRAL_OBJECTIVE,
)
from comstar_game_ai.agent.directive import (
    Directive,
    DirectiveIntent,
    _coerce_directive_payload,
    neutral_directive,
)

_LOGGER = logging.getLogger(__name__)

_ID_RE = re.compile(r"\b((?:gen|set|fac)_[a-z0-9_]+)\b", re.IGNORECASE)


@dataclass
class CampaignExpects:
    turns_to_reach: int | None = None
    garrison_at_arrival: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns_to_reach": self.turns_to_reach,
            "garrison_at_arrival": self.garrison_at_arrival,
        }


@dataclass
class CampaignDirective:
    """Structured campaign intent. Falsifiable; ids only; commit set by us."""

    objective: str = NEUTRAL_OBJECTIVE
    actor: str | None = None
    target: str | None = None
    commit_until_turn: int | None = None
    abandon_if: dict[str, Any] = field(default_factory=dict)
    expects: CampaignExpects = field(default_factory=CampaignExpects)
    because: str = ""
    question_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    downgraded: bool = False
    downgrade_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "objective": self.objective,
            "actor": self.actor,
            "target": self.target,
            "commit_until_turn": self.commit_until_turn,
            "abandon_if": dict(self.abandon_if),
            "expects": self.expects.to_dict(),
            "because": self.because,
        }

    def to_legacy_directive(self, *, issued_turn: int | None = None) -> Directive:
        """Bridge into the existing DirectiveStore / planner shape.

        `valid_for_plies` is derived from the deterministic commitment window, never
        from a model field. When `issued_turn` is known, plies = commit_until - issued.
        """
        if self.commit_until_turn is not None and issued_turn is not None:
            plies = max(1, int(self.commit_until_turn) - int(issued_turn))
        elif self.commit_until_turn is not None:
            plies = max(1, min(8, int(self.commit_until_turn)))
        else:
            plies = 1
        return Directive(
            intent=DirectiveIntent(
                objective=self.objective,
                abort_if=dict(self.abandon_if),
            ),
            commentary=self.because,
            valid_for_plies=plies,
            play_params={
                "actor": self.actor,
                "target": self.target,
                "commit_until_turn": self.commit_until_turn,
                "expects": self.expects.to_dict(),
            },
            raw=self.to_dict(),
        )


def campaign_directive_schema() -> dict[str, Any]:
    """Schema for constrained decoding. `commit_until_turn` is deliberately absent."""
    return {
        "type": "object",
        "properties": {
            "question_id": {"type": "string"},
            "objective": {"type": "string", "enum": list(CAMPAIGN_OBJECTIVES)},
            "actor": {"type": ["string", "null"]},
            "target": {"type": ["string", "null"]},
            "abandon_if": {
                "type": "object",
                "properties": {
                    "hostile_stack_within_turns": {"type": "number"},
                    "treasury_below": {"type": "number"},
                },
            },
            "expects": {
                "type": "object",
                "properties": {
                    "turns_to_reach": {"type": "number"},
                    "garrison_at_arrival": {
                        "type": "string",
                        "enum": list(GARRISON_AT_ARRIVAL),
                    },
                },
            },
            "because": {"type": "string"},
        },
        "required": ["objective", "because"],
    }


def commit_until_turn(
    *,
    current_turn: int,
    predicted_turns_to_reach: int,
) -> int:
    """Deterministic commitment window. Never set by the model.

    current_turn + predicted_turns_to_reach + 1, clamped to [current+2, current+8].
    """
    raw = int(current_turn) + max(0, int(predicted_turns_to_reach)) + 1
    lo = int(current_turn) + 2
    hi = int(current_turn) + 8
    return max(lo, min(hi, raw))


def neutral_campaign_directive(reason: str = "", *, question_id: str = "") -> CampaignDirective:
    return CampaignDirective(
        objective=NEUTRAL_OBJECTIVE,
        actor=None,
        target=None,
        because=reason or "neutral",
        question_id=question_id,
    )


def parse_campaign_directive(text: str, *, question_id: str = "") -> CampaignDirective:
    """Parse model JSON into a CampaignDirective. Malformed → neutral hold."""
    data, reason = _coerce_directive_payload(text)
    if data is None:
        return neutral_campaign_directive(reason or "malformed_json", question_id=question_id)
    if not isinstance(data, dict):
        return neutral_campaign_directive("not_object", question_id=question_id)

    # Model-supplied commit_until_turn is ignored (acceptance 10).
    data.pop("commit_until_turn", None)

    objective = str(data.get("objective") or NEUTRAL_OBJECTIVE).strip().lower()
    if objective not in CAMPAIGN_OBJECTIVES:
        return neutral_campaign_directive(f"unknown_objective:{objective}", question_id=question_id)

    actor = data.get("actor")
    target = data.get("target")
    if actor is not None:
        actor = str(actor).strip() or None
    if target is not None:
        target = str(target).strip() or None

    if objective == NEUTRAL_OBJECTIVE:
        actor, target = None, None
    elif objective in ADVANCING_OBJECTIVES and (not actor or not target):
        return neutral_campaign_directive("missing_actor_or_target", question_id=question_id)

    expects_raw = data.get("expects") if isinstance(data.get("expects"), dict) else {}
    garrison = str(expects_raw.get("garrison_at_arrival") or "unknown").strip().lower()
    if garrison not in GARRISON_AT_ARRIVAL:
        garrison = "unknown"
    turns = expects_raw.get("turns_to_reach")
    try:
        turns_i = int(turns) if turns is not None else None
    except (TypeError, ValueError):
        turns_i = None

    abandon = data.get("abandon_if") if isinstance(data.get("abandon_if"), dict) else {}
    qid = str(data.get("question_id") or question_id or "").strip()

    return CampaignDirective(
        objective=objective,
        actor=actor,
        target=target,
        abandon_if=dict(abandon),
        expects=CampaignExpects(turns_to_reach=turns_i, garrison_at_arrival=garrison),
        because=str(data.get("because") or data.get("reason") or "").strip(),
        question_id=qid,
        raw=dict(data),
    )


def ids_named_in_directive(directive: CampaignDirective) -> set[str]:
    """Every id the model named in actor, target, or because."""
    found: set[str] = set()
    for value in (directive.actor, directive.target, directive.because):
        if not value:
            continue
        found.update(m.group(1).lower() for m in _ID_RE.finditer(value))
        # Bare actor/target that already look like a single id token.
        token = str(value).strip().lower()
        if " " not in token and token.startswith(("gen_", "set_", "fac_")):
            found.add(token)
    return found


def reject_unknown_ids(
    directive: CampaignDirective,
    allowed_ids: set[str],
) -> CampaignDirective:
    """Any id not in the payload → neutral hold. No fuzzy matching."""
    allowed = {i.lower() for i in allowed_ids}
    named = ids_named_in_directive(directive)
    unknown = sorted(i for i in named if i not in allowed)
    if unknown:
        _LOGGER.warning("campaign directive rejected unknown ids: %s", unknown)
        return neutral_campaign_directive(
            f"unknown_id:{','.join(unknown)}",
            question_id=directive.question_id,
        )
    return directive


def log_leak_suspected(
    *,
    directive: CampaignDirective,
    allowed_ids: set[str],
    turn: int | None,
) -> list[str]:
    """Log ids the model named that were not in the payload. Does not block."""
    allowed = {i.lower() for i in allowed_ids}
    leaked = sorted(i for i in ids_named_in_directive(directive) if i not in allowed)
    if leaked:
        _LOGGER.warning(
            "leak_suspected turn=%s ids=%s question_id=%s because=%r",
            turn,
            leaked,
            directive.question_id,
            directive.because,
        )
    return leaked


def downgrade_campaign_directive(
    directive: CampaignDirective,
    *,
    pathfinder_turns: int | None,
    predictor_garrison: str | None,
) -> CampaignDirective:
    """Downgrade when the model's expects disagree with the deterministic layer."""
    if directive.objective == NEUTRAL_OBJECTIVE:
        return directive

    reasons: list[str] = []
    if (
        pathfinder_turns is not None
        and directive.expects.turns_to_reach is not None
        and directive.expects.turns_to_reach < pathfinder_turns
    ):
        reasons.append(
            f"turns_to_reach model={directive.expects.turns_to_reach} pathfinder={pathfinder_turns}"
        )

    strength_rank = {"weaker": 0, "similar": 1, "stronger": 2, "unknown": 1}
    if predictor_garrison in strength_rank and directive.expects.garrison_at_arrival in strength_rank:
        if (
            directive.expects.garrison_at_arrival == "weaker"
            and predictor_garrison == "stronger"
        ):
            reasons.append(
                f"garrison_at_arrival model=weaker predictor={predictor_garrison}"
            )

    if not reasons:
        return directive

    _LOGGER.warning("campaign directive downgraded: %s", "; ".join(reasons))
    out = neutral_campaign_directive(
        f"downgraded: {'; '.join(reasons)}",
        question_id=directive.question_id,
    )
    out.downgraded = True
    out.downgrade_reason = "; ".join(reasons)
    return out
