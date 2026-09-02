"""Parameterised multi-step battle patterns (plays)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PlayStep:
    name: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Play:
    play_id: str
    steps: list[PlayStep]


PLAYBOOK: dict[str, Play] = {
    "hammer_anvil": Play(
        play_id="hammer_anvil",
        steps=[
            PlayStep("fix_anvil", "hold_position", {"group": "anvil"}),
            PlayStep("swing_hammer", "flank_charge", {"group": "hammer", "side": "left"}),
        ],
    ),
    "refused_flank": Play(
        play_id="refused_flank",
        steps=[
            PlayStep("refuse", "angle_defense", {"facing": "threat"}),
            PlayStep("counter", "charge", {"group": "reserve"}),
        ],
    ),
    "feigned_retreat": Play(
        play_id="feigned_retreat",
        steps=[
            PlayStep("feign", "order_retreat", {"group": "bait"}),
            PlayStep("turn", "charge", {"group": "bait", "target": "pursuer"}),
        ],
    ),
}


class PlaysExecutor:
    """Execute play steps; each step is verified externally by Process A."""

    def __init__(self, on_step: Callable[[PlayStep], bool] | None = None) -> None:
        self._on_step = on_step or (lambda _s: True)

    def run(self, play_id: str, params: dict[str, Any] | None = None) -> bool:
        play = PLAYBOOK.get(play_id)
        if play is None:
            return False
        merged_params = dict(params or {})
        for step in play.steps:
            step_params = {**step.params, **merged_params}
            executed = PlayStep(step.name, step.action, step_params)
            if not self._on_step(executed):
                return False
        return True
