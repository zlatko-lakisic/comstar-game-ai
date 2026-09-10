"""Accept a campaign director answer: parse, reject unknown ids, downgrade, commit."""

from __future__ import annotations

import logging
from typing import Any

from comstar_game_ai.agent.campaign_contract import (
    CampaignDirective,
    commit_until_turn,
    downgrade_campaign_directive,
    log_leak_suspected,
    parse_campaign_directive,
    reject_unknown_ids,
)
from comstar_game_ai.agent.campaign_payload import (
    CampaignPayload,
    pathfinder_turns_for,
    predictor_garrison_for,
)
from comstar_game_ai.agent.campaign_vocab import ADVANCING_OBJECTIVES, NEUTRAL_OBJECTIVE
from comstar_game_ai.agent.predictors.log import PredictionLog
from comstar_game_ai.shared.config import repo_root

_LOGGER = logging.getLogger(__name__)


def default_campaign_prediction_log() -> PredictionLog:
    return PredictionLog(repo_root() / "data" / "runtime" / "campaign_predictions.jsonl")


def accept_campaign_answer(
    text: str,
    *,
    payload: CampaignPayload,
    current_turn: int,
    prediction_log: PredictionLog | None = None,
) -> CampaignDirective:
    """Full acceptance path for a campaign director response.

    Malformed / unknown id / feasibility miss → neutral hold. commit_until_turn is
    always set here from the pathfinder, never from the model.
    """
    directive = parse_campaign_directive(text, question_id=payload.question_id)

    # Leak rate: log before reject so we still measure training-data bleed.
    log_leak_suspected(
        directive=directive,
        allowed_ids=payload.allowed_ids,
        turn=current_turn,
    )
    directive = reject_unknown_ids(directive, payload.allowed_ids)

    pathfinder = pathfinder_turns_for(
        payload, actor=directive.actor, target=directive.target
    )
    # Reinforce targets are owned settlements (threats), not candidates.
    if pathfinder is None and directive.objective == "reinforce" and directive.target:
        for th in payload.threats:
            if th.settlement_id == directive.target:
                pathfinder = th.turns_until_contact
                break

    predictor_garrison = predictor_garrison_for(payload, directive.target)
    directive = downgrade_campaign_directive(
        directive,
        pathfinder_turns=pathfinder,
        predictor_garrison=predictor_garrison,
    )

    if directive.objective in ADVANCING_OBJECTIVES:
        predicted = pathfinder if pathfinder is not None else (
            directive.expects.turns_to_reach or 2
        )
        directive.commit_until_turn = commit_until_turn(
            current_turn=current_turn,
            predicted_turns_to_reach=int(predicted),
        )
    else:
        directive.commit_until_turn = None
        directive.actor = None
        directive.target = None

    if prediction_log is not None and directive.objective != NEUTRAL_OBJECTIVE:
        expects = directive.expects.to_dict()
        if expects.get("turns_to_reach") is not None or expects.get("garrison_at_arrival"):
            entry_id = prediction_log.log_prediction(
                "campaign_directive",
                {
                    "expects": expects,
                    "pathfinder_turns": pathfinder,
                    "predictor_garrison": predictor_garrison,
                    "objective": directive.objective,
                    "actor": directive.actor,
                    "target": directive.target,
                },
                context={
                    "turn": current_turn,
                    "question_id": directive.question_id,
                    "state_hash": payload.state_hash,
                    "commit_until_turn": directive.commit_until_turn,
                },
            )
            directive.raw = {**directive.raw, "prediction_entry_id": entry_id}

    _LOGGER.info(
        "accepted campaign directive turn=%s objective=%s actor=%s target=%s commit=%s because=%r",
        current_turn,
        directive.objective,
        directive.actor,
        directive.target,
        directive.commit_until_turn,
        directive.because,
    )
    return directive
