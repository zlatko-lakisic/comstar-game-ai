"""File-backed directive handoff between Process A and Process B."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from comstar_game_ai.agent.directive import Directive, neutral_directive, parse_directive


@dataclass
class StoredDirective:
    question_id: str
    directive: dict[str, Any]
    ts: float = field(default_factory=time.time)

    def to_directive(self) -> Directive:
        return parse_directive(json.dumps(self.directive))


class DirectiveStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path or "data/runtime/directive.json")

    @property
    def path(self) -> Path:
        return self._path

    def write(self, question_id: str, directive: Directive) -> None:
        payload = StoredDirective(
            question_id=question_id,
            directive=_directive_to_dict(directive),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(asdict(payload), indent=2), encoding="utf-8")

    def write_neutral(self, question_id: str, reason: str = "") -> None:
        d = neutral_directive(reason)
        self.write(question_id, d)

    def read(self) -> StoredDirective | None:
        if not self._path.is_file():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return StoredDirective(
                question_id=str(data.get("question_id", "")),
                directive=dict(data.get("directive") or {}),
                ts=float(data.get("ts") or 0),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def clear(self) -> None:
        if self._path.is_file():
            self._path.unlink()


def _directive_to_dict(directive: Directive) -> dict[str, Any]:
    if directive.raw:
        return dict(directive.raw)
    return {
        "intent": {
            "objective": directive.intent.objective,
            "acceptable_own_losses": directive.intent.acceptable_own_losses,
            "required_enemy_losses": directive.intent.required_enemy_losses,
            "hold_for_seconds": directive.intent.hold_for_seconds,
            "preserve": directive.intent.preserve,
            "abort_if": directive.intent.abort_if,
        },
        "horizon": directive.horizon,
        "risk_posture": directive.risk_posture,
        "focus_actions": directive.focus_actions,
        "avoid_actions": directive.avoid_actions,
        "opponent_read": directive.opponent_read,
        "commentary": directive.commentary,
        "valid_for_plies": directive.valid_for_plies,
        "play_id": directive.play_id,
        "play_params": directive.play_params,
    }
