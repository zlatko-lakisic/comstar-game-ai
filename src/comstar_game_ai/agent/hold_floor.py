"""Deterministic floor under a bad director hold / freelanced expansion (F7).

A `hold` (or a worse expansion pick) while a preferred reachable target exists is
a case the predictors can catch without the model. Intervention action is
configurable: substitute the preferred expansion target, or force a re-ask.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from comstar_game_ai.agent.campaign_contract import CampaignDirective
from comstar_game_ai.agent.campaign_payload import CampaignPayload
from comstar_game_ai.agent.campaign_vocab import NEUTRAL_OBJECTIVE
from comstar_game_ai.agent.predictors.campaign_board import Candidate

_LOGGER = logging.getLogger(__name__)

HoldFloorAction = Literal["log", "upgrade", "reask"]

#: Commitment window for "reachable soon" — pathfinder turns, not calendar.
DEFAULT_COMMITMENT_TURNS = 2


@dataclass(frozen=True)
class HoldFloorFinding:
    candidate: Candidate
    action: HoldFloorAction
    predictor_view: dict[str, Any]


def _standing_directive_locks_target(payload: CampaignPayload) -> bool:
    """One-settlement stickiness: in-progress besiege must not retarget."""
    standing = payload.standing
    if standing is None:
        return False
    if (standing.status or "").lower() not in {"in progress", "in_progress"}:
        return False
    return (standing.objective or "").lower() == "besiege" and bool(standing.target)


def top_reachable_weaker(
    payload: CampaignPayload,
    *,
    max_turns: int = DEFAULT_COMMITMENT_TURNS,
) -> Candidate | None:
    """Best besiege opportunity the predictors already ranked into the brief."""
    if payload.threats:
        # Threats outrank opportunities; hold may still be wrong, but this floor
        # only covers the no-threat / ignore-candidates case from the fixture.
        return None
    for candidate in payload.candidates:
        if candidate.garrison != "weaker":
            continue
        if candidate.turns_to_reach > max_turns:
            continue
        if not candidate.nearest_general_id:
            continue
        return candidate
    return None


def expansion_floor_candidate(payload: CampaignPayload) -> Candidate | None:
    """Preferred expansion target when threats are clear and stickiness allows."""
    if payload.threats:
        return None
    if _standing_directive_locks_target(payload):
        return None
    preferred = payload.preferred
    if preferred is not None and preferred.nearest_general_id:
        return preferred
    return top_reachable_weaker(payload)


def _needs_expansion_upgrade(
    directive: CampaignDirective, preferred: Candidate
) -> bool:
    if directive.objective == NEUTRAL_OBJECTIVE:
        return True
    if directive.objective != "besiege":
        return False
    if directive.target == preferred.settlement_id:
        return False
    # Freelanced or worse standing than preferred.
    chosen = None
    # Prefer matching from payload candidates when present.
    return True


def apply_hold_floor(
    directive: CampaignDirective,
    *,
    payload: CampaignPayload,
    current_turn: int,
    action: HoldFloorAction = "log",
    max_turns: int = DEFAULT_COMMITMENT_TURNS,
) -> CampaignDirective:
    """Intervene when the model holds or freelances against the preferred target.

    - ``log``: record the finding, leave the directive
    - ``upgrade``: substitute besiege against the preferred expansion candidate
    - ``reask``: leave hold but tag raw so the caller can re-prompt
    """
    # Do not mask unknown-id rejects — those because strings are the acceptance signal.
    # missing_actor_or_target must still upgrade: the reask path often returns a bare
    # besiege without ids, and that is exactly when the preferred target should land.
    because = (directive.because or "").lower()
    if because.startswith("unknown_id") or "unknown_id:" in because:
        return directive
    if because.startswith("malformed") or because.startswith("downgraded:"):
        return directive

    # One-settlement stickiness: never retarget an in-progress besiege.
    if _standing_directive_locks_target(payload):
        return directive

    preferred = expansion_floor_candidate(payload)
    if preferred is None:
        if directive.objective != NEUTRAL_OBJECTIVE:
            return directive
        candidate = top_reachable_weaker(payload, max_turns=max_turns)
        if candidate is None:
            return directive
        preferred = candidate
    elif not _needs_expansion_upgrade(directive, preferred):
        return directive

    # When model already besieges preferred, nothing to do.
    if (
        directive.objective == "besiege"
        and directive.target == preferred.settlement_id
    ):
        return directive

    predictor_view = {
        "settlement_id": preferred.settlement_id,
        "nearest_general_id": preferred.nearest_general_id,
        "turns_to_reach": preferred.turns_to_reach,
        "garrison": preferred.garrison,
        "standing": preferred.standing,
        "confidence": preferred.confidence,
        "age_turns": preferred.age_turns,
        "threats": [th.to_payload_line() for th in payload.threats],
        "candidates_head": [c.to_payload_line() for c in payload.candidates[:3]],
        "preferred": preferred.to_payload_line(),
    }
    finding = HoldFloorFinding(
        candidate=preferred, action=action, predictor_view=predictor_view
    )
    _LOGGER.warning(
        "hold floor turn=%s action=%s model_because=%r predictor=%s",
        current_turn,
        action,
        directive.because,
        predictor_view,
    )

    raw = dict(directive.raw or {})
    raw["hold_floor"] = {
        "action": action,
        "predictor": predictor_view,
        "model_objective": directive.objective,
        "model_because": directive.because,
    }

    if action == "log":
        directive.raw = raw
        return directive

    if action == "reask":
        raw["hold_floor_reask"] = True
        directive.raw = raw
        directive.because = (
            f"hold rejected by floor: preferred expansion {preferred.settlement_id} "
            f"via {preferred.nearest_general_id} in {preferred.turns_to_reach} turns "
            f"(standing {preferred.standing})"
        )
        return directive

    # upgrade
    upgraded = CampaignDirective(
        question_id=directive.question_id,
        objective="besiege",
        actor=preferred.nearest_general_id,
        target=preferred.settlement_id,
        abandon_if=dict(directive.abandon_if),
        expects=directive.expects,
        because=(
            f"expansion floor upgraded: preferred {preferred.settlement_id} "
            f"(standing {preferred.standing}, {preferred.turns_to_reach} turns); "
            f"model said: {directive.because}"
        ),
        commit_until_turn=None,
        raw=raw,
    )
    _LOGGER.info(
        "hold floor upgraded turn=%s to besiege %s -> %s",
        current_turn,
        upgraded.actor,
        upgraded.target,
    )
    _ = finding
    return upgraded
