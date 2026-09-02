"""Game state machine from script telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GameState(str, Enum):
    LAUNCHER = "launcher"
    LOADING = "loading"
    MAIN_MENU = "main_menu"
    CAMPAIGN_MAP = "campaign_map"
    CAMPAIGN_MODAL = "campaign_modal"
    PRE_BATTLE_SCROLL = "pre_battle_scroll"
    BATTLE_DEPLOYMENT = "battle_deployment"
    BATTLE_IN_PROGRESS = "battle_in_progress"
    POST_BATTLE_SCROLL = "post_battle_scroll"
    CAMPAIGN_END = "campaign_end"
    UNKNOWN = "unknown"


_SCRIPT_EVENT_TO_STATE: dict[str, GameState] = {
    "NewTurnStart": GameState.CAMPAIGN_MAP,
    "I_BattleEndPending": GameState.PRE_BATTLE_SCROLL,
    "I_BattleEnd": GameState.POST_BATTLE_SCROLL,
    "I_BattleFinished": GameState.POST_BATTLE_SCROLL,
    "BattleDeploymentStart": GameState.BATTLE_DEPLOYMENT,
    "BattleStarted": GameState.BATTLE_IN_PROGRESS,
    "CampaignEnd": GameState.CAMPAIGN_END,
    "MainMenu": GameState.MAIN_MENU,
    "LoadingStart": GameState.LOADING,
    "ModalOpen": GameState.CAMPAIGN_MODAL,
    "ModalClose": GameState.CAMPAIGN_MAP,
}


@dataclass
class GameStateDetector:
    """Track high-level game state from structured script events."""

    state: GameState = GameState.UNKNOWN
    turn: int | None = None
    faction: str | None = None
    battle_id: str | None = None
    _history: list[tuple[str, GameState]] = field(default_factory=list)

    def update_from_script_event(self, record: dict[str, str]) -> GameState | None:
        """Apply one parsed scripting_log record; return state if changed."""
        event = record.get("event")
        if not event:
            return None

        if record.get("turn"):
            try:
                self.turn = int(record["turn"])
            except ValueError:
                pass
        if record.get("faction"):
            self.faction = record["faction"]
        if record.get("battle_id"):
            self.battle_id = record["battle_id"]

        new_state = _SCRIPT_EVENT_TO_STATE.get(event)
        if new_state is None:
            return None

        if new_state != self.state:
            self._history.append((event, new_state))
            if len(self._history) > 200:
                self._history = self._history[-200:]
            self.state = new_state
            return new_state
        return None

    def allows_campaign_orders(self) -> bool:
        return self.state == GameState.CAMPAIGN_MAP

    def allows_battle_orders(self) -> bool:
        return self.state in (GameState.BATTLE_DEPLOYMENT, GameState.BATTLE_IN_PROGRESS)

    def takeover_offered(self) -> bool:
        return self.state in (
            GameState.CAMPAIGN_MAP,
            GameState.BATTLE_DEPLOYMENT,
            GameState.BATTLE_IN_PROGRESS,
        )

    def history(self, n: int = 10) -> list[tuple[str, GameState]]:
        return list(self._history[-max(1, n) :])
