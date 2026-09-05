"""Process A runtime — capture, safety, hotkeys, campaign/battle drivers."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from comstar_game_ai.game_io.battle.battle_driver import BattleDriver, BattleDriverConfig, load_battle_directive
from comstar_game_ai.game_io.battle.orders import BattleOrder
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, grab_and_classify
from comstar_game_ai.game_io.capture.capture_loop import CaptureLoop
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver, phase2_accepted
from comstar_game_ai.game_io.hotkeys import HotkeyManager
from comstar_game_ai.game_io.input.send_input import SendInputController
from comstar_game_ai.game_io.safety import ControlMode, SafetyController
from comstar_game_ai.game_io.watchdog import HumanOverrideWatch
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

_LOGGER = logging.getLogger(__name__)

HOTKEY_KILL = 1
HOTKEY_TAKEOVER = 2
HOTKEY_HANDBACK = 3


@dataclass
class GameIoRuntime:
    """Orchestrates capture, safety, IPC, and game drivers."""

    turns: int = 20
    battle_ticks: int = 120
    require_game: bool = True
    player_faction: str = "julii"
    safety: SafetyController = field(default_factory=SafetyController)
    publisher: EventPublisher = field(default_factory=EventPublisher)
    input_ctrl: SendInputController = field(default_factory=SendInputController)
    hotkeys: HotkeyManager = field(default_factory=HotkeyManager)
    directive_store: DirectiveStore = field(default_factory=DirectiveStore)
    _capture: CaptureLoop | None = field(default=None, init=False)
    _game_hwnd: int | None = field(default=None, init=False)
    _override_watch: HumanOverrideWatch | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        cfg = load_config()
        self.player_faction = cfg.get("campaign", {}).get("player_faction", self.player_faction)
        self.safety.on_kill = self._release_all_input
        self.safety.on_handback = self._release_all_input

    def _release_all_input(self) -> None:
        self.input_ctrl.normalize_keyboard_state()
        self.publisher.publish(EventKind.CONTROL_STATE, {"state": self.safety.mode.value})

    def _publish_control(self) -> None:
        self.publisher.publish(EventKind.CONTROL_STATE, {"state": self.safety.mode.value})

    def setup(self) -> bool:
        if sys.platform != "win32":
            _LOGGER.error("Process A requires Windows")
            return False

        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
        game = find_game_window(subs)
        if game is None:
            if self.require_game:
                _LOGGER.error("Rome window not found")
                return False
            _LOGGER.warning("no game window — running in dry mode")
            return True

        self._game_hwnd = game.hwnd
        self._capture = CaptureLoop(game.hwnd)
        self._capture.start()

        safety_cfg = cfg.get("safety") or {}
        try:
            self.hotkeys.register(HOTKEY_KILL, safety_cfg.get("kill_hotkey", "ctrl+shift+end"), self._on_kill)
            self.hotkeys.register(
                HOTKEY_TAKEOVER,
                safety_cfg.get("takeover_hotkey", "ctrl+shift+home"),
                self._on_takeover,
            )
            self.hotkeys.register(
                HOTKEY_HANDBACK,
                safety_cfg.get("handback_hotkey", "ctrl+shift+pause"),
                self._on_handback,
            )
            self.hotkeys.start()
        except OSError as exc:
            _LOGGER.warning("hotkeys unavailable: %s", exc)

        self._override_watch = HumanOverrideWatch.from_config(self.safety, game.hwnd)
        if self._override_watch.armed:
            self._override_watch.start()
            _LOGGER.info("human override watch armed")

        self._publish_control()
        return True

    def shutdown(self) -> None:
        self.hotkeys.stop()
        if self._override_watch:
            self._override_watch.stop()
        if self._capture:
            self._capture.stop()
        self._release_all_input()
        self.publisher.close()

    def _on_kill(self) -> None:
        self.safety.kill(reason="hotkey")
        self._publish_control()

    def refuse_takeover_reason(self) -> str | None:
        """Why the agent must not take control now, or None.

        The design offers takeover only in a playable state. The gate refuses on a
        *confident* reading of an unplayable screen rather than demanding a
        confident reading of a playable one: in phase 2 a readiness gate that
        required positive proof refused to start on a live, playable campaign,
        because dim winter maps and open sea both classify as unknown.
        """
        if self._game_hwnd is None:
            return None
        try:
            classification = grab_and_classify(self._game_hwnd)
        except Exception:
            return None
        if classification.mode is CampaignUiMode.PAUSE and classification.confidence >= 0.6:
            return f"game is paused or on a menu ({classification.detail})"
        return None

    def _on_takeover(self) -> None:
        refusal = self.refuse_takeover_reason()
        if refusal is not None:
            _LOGGER.warning("takeover refused: %s", refusal)
            self.publisher.publish(
                EventKind.AO_STATUS, {"phase": "takeover refused", "summary": refusal}
            )
            return
        self.safety.takeover()
        self._publish_control()

    def _on_handback(self) -> None:
        self.safety.handback()
        self._publish_control()

    def run_campaign(self, *, turns: int | None = None) -> dict[str, object]:
        """Hardcoded campaign loop for Phase 1-2 acceptance."""
        n = turns if turns is not None else self.turns
        if not self.setup():
            return {"ok": False, "reason": "setup_failed"}

        driver = HardcodedCampaignDriver(player_faction=self.player_faction)
        driver.bootstrap_from_logs()
        successes = 0
        desyncs = 0
        turn_at_start = driver.turns_ended

        try:
            if self.safety.mode == ControlMode.IDLE:
                self.safety.takeover()
                self._publish_control()

            for turn_idx in range(n):
                if self.safety.mode not in (ControlMode.AGENT, ControlMode.HANDING_BACK):
                    break

                driver.poll_observation()
                self.publisher.publish(
                    EventKind.INTENT_DECLARED, {"summary": f"end turn {turn_idx + 1}"}
                )

                ok = driver.run_turn_stub(wait_for_next_turn=True)
                if ok:
                    successes += 1
                else:
                    desyncs += 1

                # The turn either advanced on disk or it did not, so this is a real
                # verification rather than a restatement of the intent: it is what
                # turns the overlay red when a turn silently fails to end.
                self.publisher.publish(
                    EventKind.VERIFICATION,
                    {
                        "ok": ok,
                        "summary": f"turn {turn_idx + 1} "
                        + ("advanced" if ok else "did not advance"),
                        "game_turn": driver.turns_ended,
                    },
                )
                self.safety.pet_deadman()
                time.sleep(0.05)

            result = {
                "turns_requested": n,
                "turns_ok": successes,
                "desyncs": desyncs,
                "game_turn_start": turn_at_start,
                "game_turn_end": driver.turns_ended,
                "turns_advanced": max(0, driver.turns_ended - turn_at_start),
            }
            return {"ok": phase2_accepted(result, turns=n), **result}
        finally:
            self.shutdown()

    def run_battle(self, *, max_ticks: int | None = None) -> dict[str, object]:
        """Battle freeze loop with reactive policy."""
        if not self.setup():
            return {"ok": False, "reason": "setup_failed"}

        driver_cfg = BattleDriverConfig(max_ticks=max_ticks or self.battle_ticks)
        campaign = HardcodedCampaignDriver()
        directive = load_battle_directive(self.directive_store)

        def run_console(cmd: str) -> bool:
            return campaign.actuator.send(cmd, require_battle=True)

        def execute_order(order: BattleOrder) -> bool:
            self.publisher.publish(EventKind.KEY_DOWN, {"action": order.action, "unit": order.unit_key})
            return True

        driver = BattleDriver(
            run_console=run_console,
            execute_order=execute_order,
            directive=directive,
            config=driver_cfg,
            on_tick=lambda tick, orders: self.publisher.publish(
                EventKind.FREEZE, {"tick": tick, "orders": len(orders)}
            ),
        )

        try:
            if self.safety.mode == ControlMode.IDLE:
                self.safety.takeover()
                self._publish_control()
            result = driver.run()
            self.publisher.publish(EventKind.AO_RESULT, {"summary": f"battle {result.get('battle_id')}"})
            return {"ok": True, **result}
        finally:
            self.shutdown()

    def run_service(self) -> None:
        """Idle service: capture + hotkeys until killed."""
        if not self.setup():
            raise SystemExit(1)
        _LOGGER.info("Process A service running — hotkeys armed")
        try:
            while self.safety.mode != ControlMode.KILLED:
                time.sleep(0.5)
                if self._game_hwnd and self.safety.agent_active:
                    self.safety.pet_deadman()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
