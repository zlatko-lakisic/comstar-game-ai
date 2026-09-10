"""Fair campaign orders: observe, mouse march, never cheats.

A directive from AO is *intent*, not a command channel. It can decide whether this
turn advances and which observations are worth making. Army marches are issued by
mouse (Lists → locate → map click), not ``move_character`` in the console.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from comstar_game_ai.agent.belief.entities import Character, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_ids import CampaignIdMap, sync_id_map_from_belief
from comstar_game_ai.agent.directive import ADVANCING_OBJECTIVES, DIRECTIVE_OBSERVATIONS
from comstar_game_ai.shared.config import load_config

if TYPE_CHECKING:
    from comstar_game_ai.agent.directive import Directive

_LOGGER = logging.getLogger(__name__)

OrderKind = Literal["observe", "move_character", "march", "end_turn"]

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
    #: Map coords for a mouse march (from → to). Ignored for console orders.
    from_xy: tuple[float, float] | None = None
    to_xy: tuple[float, float] | None = None
    character_name: str = ""


@dataclass
class CampaignPlanner:
    """Conservative Julii policy: observe every turn; move only with known coords."""

    player_faction: str = "julii"
    max_moves_per_turn: int = 1
    id_map: CampaignIdMap | None = None

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

    def _resolve_actor_target(
        self, belief: BeliefStore, directive: Directive
    ) -> tuple[Character | None, Settlement | None]:
        """Resolve play_params actor/target ids to belief entities."""
        params = directive.play_params or {}
        actor_id = str(params.get("actor") or "").strip().lower()
        target_id = str(params.get("target") or "").strip().lower()
        if not actor_id or not target_id:
            return None, None

        id_map = sync_id_map_from_belief(belief, self.id_map)
        self.id_map = id_map

        actor_name = id_map.name_for(actor_id).strip().lower()
        target_name = id_map.name_for(target_id).strip().lower()

        characters = [
            c
            for c in belief.get_characters()
            if c.faction.lower()
            in {self.player_faction.lower(), f"romans_{self.player_faction.lower()}", ""}
            and (c.x or c.y)
        ]
        settlements = [s for s in belief.get_settlements() if s.x or s.y]

        char = None
        for c in characters:
            keys = {
                (c.entity_id or "").strip().lower(),
                (c.name or "").strip().lower(),
                id_map.general_id(c).lower(),
            }
            if actor_id in keys or actor_name in keys:
                char = c
                break

        settlement = None
        for s in settlements:
            keys = {
                (s.entity_id or "").strip().lower(),
                (s.region or "").strip().lower(),
                id_map.settlement_id(s).lower(),
            }
            if target_id in keys or target_name in keys:
                settlement = s
                break

        if char is None or settlement is None:
            _LOGGER.warning(
                "could not resolve actor=%s target=%s from belief", actor_id, target_id
            )
            return None, None
        return char, settlement

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

        char = characters[0]
        target = None
        objective = ""
        if directive is not None:
            objective = directive.intent.objective.strip().lower()
            resolved_char, resolved_target = self._resolve_actor_target(belief, directive)
            if resolved_char is not None and resolved_target is not None:
                char, target = resolved_char, resolved_target
            elif objective in ADVANCING_OBJECTIVES:
                # Contract requires actor+target; without them, do not invent a march.
                return []

        if target is None:
            # No directive (hardcoded baseline): step toward nearest non-owned settlement.
            owned = [s for s in settlements if "julii" in (s.owner or "").lower()]
            targets = [s for s in settlements if s not in owned] or owned
            if not targets:
                return []
            target = min(targets, key=lambda s: (s.x - char.x) ** 2 + (s.y - char.y) ** 2)

        # Nudge one tile toward the target on the map — issued by mouse, not console.
        dx = 0 if abs(target.x - char.x) < 0.5 else (1 if target.x > char.x else -1)
        dy = 0 if abs(target.y - char.y) < 0.5 else (1 if target.y > char.y else -1)
        if dx == 0 and dy == 0:
            return []
        name = (char.name or char.entity_id).strip()
        if not name:
            return []
        reason = f"step toward {target.entity_id or target.region}"
        if objective:
            reason = f"{objective}: {reason}"
        return [
            CampaignOrder(
                "march",
                f"march {name} toward {target.entity_id or target.region}",
                reason,
                from_xy=(float(char.x), float(char.y)),
                to_xy=(float(target.x), float(target.y)),
                character_name=name,
            )
        ]
