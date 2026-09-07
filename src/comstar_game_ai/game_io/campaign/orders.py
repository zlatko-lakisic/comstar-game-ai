"""Fair campaign orders: observe, optional move_character, never cheats.

A directive from AO is *intent*, not a command channel. It can decide whether this
turn advances and which observations are worth making, and nothing else: the orders
themselves are still built here, from belief, and still go through the fair-play
gate. A model that returns nonsense therefore costs a turn of standing still, which
is the failure we can afford.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from comstar_game_ai.agent.belief.store import BeliefStore

# Re-exported: the vocabulary belongs to the directive contract, so the schema the
# model decodes against and the gate that reads its answer cannot drift apart.
from comstar_game_ai.agent.directive import ADVANCING_OBJECTIVES, DIRECTIVE_OBSERVATIONS
from comstar_game_ai.shared.config import load_config

if TYPE_CHECKING:
    from comstar_game_ai.agent.directive import Directive

_LOGGER = logging.getLogger(__name__)

OrderKind = Literal["observe", "move_character", "end_turn"]

__all__ = [
    "ADVANCING_OBJECTIVES",
    "DIRECTIVE_OBSERVATIONS",
    "CampaignOrder",
    "CampaignPlanner",
    "OrderKind",
]


@dataclass(frozen=True)
class CampaignOrder:
    kind: OrderKind
    command: str
    reason: str = ""


@dataclass
class CampaignPlanner:
    """Conservative Julii policy: observe every turn; move only with known coords."""

    player_faction: str = "julii"
    max_moves_per_turn: int = 1

    def plan(self, belief: BeliefStore, directive: Directive | None = None) -> list[CampaignOrder]:
        orders: list[CampaignOrder] = [
            CampaignOrder("observe", f"halt_ai {self.player_faction}", "pause faction AI"),
            CampaignOrder("observe", "list_characters", "console roster query"),
        ]
        seen = {order.command for order in orders}
        for command in self._directive_observations(directive):
            if command not in seen:
                seen.add(command)
                orders.append(CampaignOrder("observe", command, "directive focus"))
        for move in self._planned_moves(belief, directive)[: self.max_moves_per_turn]:
            orders.append(move)
        orders.append(CampaignOrder("observe", "run_ai", "resume faction AI"))
        return orders

    def _directive_observations(self, directive: Directive | None) -> list[str]:
        if directive is None:
            return []
        return [
            action
            for action in directive.focus_actions
            if action.strip().lower() in DIRECTIVE_OBSERVATIONS
        ]

    def _advance_allowed(self, directive: Directive | None) -> bool:
        """Whether the directive lets a character move at all this turn.

        Unknown objectives read as "hold". A model inventing a verb should not be
        able to move an army by accident.
        """
        if directive is None:
            return True
        if any(a.strip().lower() == "move_character" for a in directive.avoid_actions):
            return False
        return directive.intent.objective.strip().lower() in ADVANCING_OBJECTIVES

    def _planned_moves(
        self, belief: BeliefStore, directive: Directive | None = None
    ) -> list[CampaignOrder]:
        cfg = (load_config().get("campaign") or {}).get("policy") or {}
        if cfg.get("allow_moves") is False:
            return []
        if not self._advance_allowed(directive):
            return []

        characters = [
            c
            for c in belief.get_characters()
            if c.faction.lower() in {self.player_faction.lower(), "romans_julii", ""}
            and (c.x or c.y)
        ]
        settlements = [s for s in belief.get_settlements() if s.x or s.y]
        if not characters or not settlements:
            return []

        owned = [s for s in settlements if "julii" in (s.owner or "").lower()]
        targets = [s for s in settlements if s not in owned] or owned
        if not targets:
            return []

        char = characters[0]
        target = min(targets, key=lambda s: (s.x - char.x) ** 2 + (s.y - char.y) ** 2)
        # Nudge one tile toward the target — never teleport to guessed coords.
        dx = 0 if abs(target.x - char.x) < 0.5 else (1 if target.x > char.x else -1)
        dy = 0 if abs(target.y - char.y) < 0.5 else (1 if target.y > char.y else -1)
        if dx == 0 and dy == 0:
            return []
        nx, ny = char.x + dx, char.y + dy
        name = (char.name or char.entity_id).strip()
        if not name:
            return []
        return [
            CampaignOrder(
                "move_character",
                f"move_character {name} {nx:.0f},{ny:.0f}",
                f"step toward {target.entity_id or target.region}",
            )
        ]
