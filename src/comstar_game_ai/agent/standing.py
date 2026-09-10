"""Standing campaign directive — continuity across turns (C5)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from comstar_game_ai.agent.campaign_contract import CampaignDirective
from comstar_game_ai.agent.campaign_payload import StandingDirectiveView
from comstar_game_ai.agent.campaign_vocab import NEUTRAL_OBJECTIVE, STANDING_STATUSES
from comstar_game_ai.shared.config import repo_root

_LOGGER = logging.getLogger(__name__)


@dataclass
class StandingDirective:
    objective: str = NEUTRAL_OBJECTIVE
    actor: str | None = None
    target: str | None = None
    issued_turn: int = 0
    commit_until_turn: int = 0
    status: str = "expired"
    question_id: str = ""
    prediction_entry_id: str | None = None
    expects: dict[str, Any] | None = None

    def to_view(self, *, turns_from_target: int | None = None) -> StandingDirectiveView:
        status = self.status if self.status in STANDING_STATUSES else "expired"
        return StandingDirectiveView(
            objective=self.objective,
            actor=self.actor,
            target=self.target,
            issued_turn=self.issued_turn,
            commit_until_turn=self.commit_until_turn,
            status=status,
            turns_from_target=turns_from_target,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandingDirective:
        return cls(
            objective=str(data.get("objective") or NEUTRAL_OBJECTIVE),
            actor=data.get("actor"),
            target=data.get("target"),
            issued_turn=int(data.get("issued_turn") or 0),
            commit_until_turn=int(data.get("commit_until_turn") or 0),
            status=str(data.get("status") or "expired"),
            question_id=str(data.get("question_id") or ""),
            prediction_entry_id=data.get("prediction_entry_id"),
            expects=data.get("expects") if isinstance(data.get("expects"), dict) else None,
        )


def default_standing_path() -> Path:
    return repo_root() / "data" / "runtime" / "standing_directive.json"


class StandingDirectiveStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_standing_path()

    def read(self) -> StandingDirective | None:
        if not self.path.is_file():
            return None
        try:
            return StandingDirective.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError):
            _LOGGER.warning("standing directive unreadable at %s", self.path)
            return None

    def write(self, standing: StandingDirective) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(standing.to_dict(), indent=2), encoding="utf-8")

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()

    def refresh_status(self, *, current_turn: int, prediction_log=None) -> StandingDirective | None:
        """Expire commitment windows. Returns the view-ready standing or None."""
        standing = self.read()
        if standing is None:
            return None
        if standing.objective == NEUTRAL_OBJECTIVE:
            return standing
        if current_turn > standing.commit_until_turn and standing.status == "in progress":
            standing.status = "expired"
            self.write(standing)
            _LOGGER.info(
                "standing directive expired at turn %s (commit_until=%s)",
                current_turn,
                standing.commit_until_turn,
            )
            if prediction_log is not None and standing.prediction_entry_id:
                prediction_log.record_outcome(
                    standing.prediction_entry_id,
                    {
                        "status": "expired",
                        "turn": current_turn,
                        "objective": standing.objective,
                        "actor": standing.actor,
                        "target": standing.target,
                    },
                )
        return standing


def accept_into_standing(
    store: StandingDirectiveStore,
    directive: CampaignDirective,
    *,
    current_turn: int,
    prediction_entry_id: str | None = None,
) -> StandingDirective | None:
    """Persist an accepted advancing directive as the standing plan.

    `hold` clears standing — a completed consolidate is not a plan to continue,
    and treating it as one locks the director into perpetual hold (C5 churn).
    """
    if directive.objective == NEUTRAL_OBJECTIVE:
        store.clear()
        return None
    standing = StandingDirective(
        objective=directive.objective,
        actor=directive.actor,
        target=directive.target,
        issued_turn=current_turn,
        commit_until_turn=int(directive.commit_until_turn or current_turn + 2),
        status="in progress",
        question_id=directive.question_id,
        prediction_entry_id=prediction_entry_id,
        expects=directive.expects.to_dict() if directive.expects else None,
    )
    store.write(standing)
    return standing
