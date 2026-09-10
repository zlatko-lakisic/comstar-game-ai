"""Deterministic floor under a bad director hold (F7).

A `hold` while a reachable weaker target sits inside the commitment window is a
case the predictors can catch without the model. Intervention action is
configurable because section 6 of the always-hold handoff leaves the choice
open: substitute the top candidate, or force a re-ask.
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


def apply_hold_floor(
    directive: CampaignDirective,
    *,
    payload: CampaignPayload,
    current_turn: int,
    action: HoldFloorAction = "log",
    max_turns: int = DEFAULT_COMMITMENT_TURNS,
) -> CampaignDirective:
    """Intervene when the model holds against a clear weaker target.

    - ``log``: record the finding, leave the hold (detection only until §6 lands)
    - ``upgrade``: substitute besiege against the top candidate
    - ``reask``: leave hold but tag raw so the caller can re-prompt
    """
    if directive.objective != NEUTRAL_OBJECTIVE:
        return directive

    candidate = top_reachable_weaker(payload, max_turns=max_turns)
    if candidate is None:
        return directive

    predictor_view = {
        "settlement_id": candidate.settlement_id,
        "nearest_general_id": candidate.nearest_general_id,
        "turns_to_reach": candidate.turns_to_reach,
        "garrison": candidate.garrison,
        "confidence": candidate.confidence,
        "age_turns": candidate.age_turns,
        "threats": [th.to_payload_line() for th in payload.threats],
        "candidates_head": [c.to_payload_line() for c in payload.candidates[:3]],
    }
    finding = HoldFloorFinding(
        candidate=candidate, action=action, predictor_view=predictor_view
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
            f"hold rejected by floor: reachable weaker {candidate.settlement_id} "
            f"via {candidate.nearest_general_id} in {candidate.turns_to_reach} turns"
        )
        return directive

    # upgrade
    upgraded = CampaignDirective(
        question_id=directive.question_id,
        objective="besiege",
        actor=candidate.nearest_general_id,
        target=candidate.settlement_id,
        abandon_if=dict(directive.abandon_if),
        expects=directive.expects,
        because=(
            f"hold floor upgraded: reachable weaker {candidate.settlement_id} "
            f"({candidate.turns_to_reach} turns, garrison weaker); "
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
    # finding kept for callers/tests
    _ = finding
    return upgraded
