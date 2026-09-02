"""Hardcoded campaign driver for Phase 2 actuation acceptance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from comstar_game_ai.agent.belief.entities import Army, ExistenceStatus
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.console.actuator import ConsoleActuator
from comstar_game_ai.game_io.intent_record import IntentRecordWriter
from comstar_game_ai.game_io.logs.scripting_log import ScriptingLogTailer
from comstar_game_ai.game_io.state_machine import GameState, GameStateDetector
from comstar_game_ai.game_io.verification import VerificationPipeline, VerificationResult

_LOGGER = logging.getLogger(__name__)


@dataclass
class HardcodedCampaignDriver:
    """Minimal end-to-end campaign loop without reasoning."""

    belief: BeliefStore = field(default_factory=BeliefStore)
    actuator: ConsoleActuator = field(default_factory=ConsoleActuator)
    state: GameStateDetector = field(default_factory=GameStateDetector)
    log_tailer: ScriptingLogTailer = field(default_factory=ScriptingLogTailer)
    intent_writer: IntentRecordWriter = field(default_factory=IntentRecordWriter)
    verification: VerificationPipeline = field(default_factory=VerificationPipeline)
    player_faction: str = "julii"
    turn_wait_timeout_s: float = 180.0
    _julii_turns_seen: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.actuator.state = self.state

    def bootstrap_from_logs(self) -> int:
        """Ingest existing scripting_log (e.g. after load) before live tailing."""
        self.log_tailer.reset()
        return self.poll_observation()

    def poll_observation(self) -> int:
        """Ingest new script telemetry into belief + state; return line count."""
        count = 0
        for record in self.log_tailer.poll():
            count += 1
            self._ingest_script_record(record)
        if count:
            self.belief.decay()
        return count

    def _ingest_script_record(self, record: dict[str, str]) -> None:
        event = record.get("event")
        if not event:
            return

        self.state.update_from_script_event(record)
        self.belief.history.append(dict(record))

        if event == "NewTurnStart":
            self._julii_turns_seen += 1
            if self.state.turn is None:
                self.state.turn = self._julii_turns_seen
            else:
                self.state.turn = max(self.state.turn, self._julii_turns_seen)

        self._ingest_entity_record(record)

    def _ingest_entity_record(self, record: dict[str, str]) -> None:
        entity_type = record.get("entity")
        entity_id = record.get("id")
        if not entity_type or not entity_id:
            return

        provenance = "script_telemetry"
        confidence = float(record.get("confidence", "1.0"))
        existence = ExistenceStatus.OBSERVED_PRESENT

        if entity_type == "army":
            self.belief.update(
                Army(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    faction=record.get("faction", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    strength=float(record.get("strength", "0")),
                    general=record.get("general"),
                )
            )
        elif entity_type == "settlement":
            from comstar_game_ai.agent.belief.entities import Settlement

            pop = record.get("population")
            self.belief.update(
                Settlement(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    region=record.get("region", ""),
                    owner=record.get("owner", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    population=int(pop) if pop else None,
                )
            )
        elif entity_type == "character":
            from comstar_game_ai.agent.belief.entities import Character

            self.belief.update(
                Character(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    name=record.get("name", entity_id),
                    faction=record.get("faction", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    role=record.get("role", ""),
                )
            )

    def wait_for_turn_event(self, *, timeout_s: float | None = None) -> bool:
        """Block until NewTurnStart telemetry or timeout."""
        timeout = timeout_s if timeout_s is not None else self.turn_wait_timeout_s
        before = self._julii_turns_seen
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.poll_observation()
            if self._julii_turns_seen > before:
                return True
            time.sleep(0.25)
        _LOGGER.warning("timed out waiting for NewTurnStart (seen=%s)", before)
        return False

    def run_turn_stub(self, *, wait_for_next_turn: bool = True) -> bool:
        """Halt AI, observe via console, resume AI, verify state, optionally wait for next turn."""
        if not self.state.allows_campaign_orders():
            _LOGGER.info("skip turn — state=%s", self.state.state.value)
            return False

        halt = f"halt_ai {self.player_faction}"
        intent = {"objective": "observe", "turn": self.state.turn}
        action = {"type": "console", "command": "list_characters"}
        expected = {"state": GameState.CAMPAIGN_MAP.value}

        record = self.intent_writer.declare(
            question_id="hardcoded-turn",
            ply_or_tick=self.state.turn,
            state_hash=str(self.state.turn or 0),
            intent=intent,
            action=action,
            expected_effect=expected,
        )

        start = time.perf_counter()
        ok = self.actuator.send(halt, require_campaign=True)
        ok = self.actuator.send("list_characters", require_campaign=True) and ok
        ok = self.actuator.send("run_ai", require_campaign=True) and ok

        if wait_for_next_turn and ok:
            ok = self.wait_for_turn_event() and ok

        observed = {"state": self.state.state.value}
        outcomes = self.verification.verify(action, expected, observed=observed)
        verified = all(o.result != VerificationResult.FAIL for o in outcomes)
        ok = ok and verified

        latency_ms = (time.perf_counter() - start) * 1000.0
        observed["verification"] = [o.result.value for o in outcomes]
        self.intent_writer.complete(record, observed_effect=observed, latency_ms=latency_ms)
        return ok

    def run_turns(
        self,
        n: int,
        *,
        require_ok: bool = True,
        wait_for_next_turn: bool = True,
    ) -> dict[str, int]:
        """Run n campaign turn stubs; return success counts."""
        ok_count = 0
        fail_count = 0
        for _ in range(n):
            self.poll_observation()
            if self.run_turn_stub(wait_for_next_turn=wait_for_next_turn):
                ok_count += 1
            else:
                fail_count += 1
                if require_ok:
                    break
        return {
            "turns_ok": ok_count,
            "turns_failed": fail_count,
            "requested": n,
            "desyncs": fail_count,
        }
