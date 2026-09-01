"""After-action record with observable / privileged split."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AfterActionRecord:
    """Split record: observable is retrievable during play; privileged is offline only."""

    battle_id: str
    intent_objective: str
    observable: dict[str, Any] = field(default_factory=dict)
    privileged: dict[str, Any] = field(default_factory=dict)
    record_type: str = "after_action"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.record_type,
            "battle_id": self.battle_id,
            "intent_objective": self.intent_objective,
            "observable": self.observable,
            "privileged": self.privileged,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @property
    def surprise(self) -> float:
        return float(self.observable.get("surprise", 0.0))

    @property
    def intent_achieved(self) -> bool:
        return bool(self.observable.get("intent_achieved", False))


def build_after_action(
    *,
    battle_id: str,
    intent_objective: str,
    predicted: dict[str, Any],
    observed: dict[str, Any],
    privileged_truth: dict[str, Any] | None = None,
) -> AfterActionRecord:
    """Build a record from prediction vs observed engine outcomes."""
    surprise = _surprise(predicted, observed)
    observable = {
        "outcome": observed.get("outcome"),
        "own_losses": observed.get("own_losses"),
        "enemy_losses": observed.get("enemy_losses"),
        "intent_achieved": _intent_achieved(intent_objective, observed),
        "surprise": surprise,
        "predicted": predicted,
        "situation": observed.get("situation", {}),
    }
    privileged = dict(privileged_truth or {})
    privileged.setdefault("ground_truth", observed)
    return AfterActionRecord(
        battle_id=battle_id,
        intent_objective=intent_objective,
        observable=observable,
        privileged=privileged,
    )


def _intent_achieved(objective: str, observed: dict[str, Any]) -> bool:
    if observed.get("intent_achieved") is not None:
        return bool(observed["intent_achieved"])
    outcome = str(observed.get("outcome", "")).lower()
    if objective in ("annihilate", "win_cheaply", "break_and_pursue"):
        return outcome == "win"
    if objective == "hold":
        return outcome in ("win", "draw")
    return outcome == "win"


def _surprise(predicted: dict[str, Any], observed: dict[str, Any]) -> float:
    p_out = str(predicted.get("outcome", "")).lower()
    o_out = str(observed.get("outcome", "")).lower()
    if not p_out or not o_out:
        return 0.5
    if p_out == o_out:
        p_loss = float(predicted.get("own_losses", 0.0))
        o_loss = float(observed.get("own_losses", 0.0))
        return min(1.0, abs(p_loss - o_loss))
    return 1.0
