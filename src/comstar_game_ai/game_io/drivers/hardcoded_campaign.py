"""Hardcoded campaign driver stub for Phase 2 acceptance."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from comstar_game_ai.agent.belief.entities import Army, ExistenceStatus
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.console.actuator import ConsoleActuator
from comstar_game_ai.game_io.intent_record import IntentRecordWriter
from comstar_game_ai.game_io.logs.scripting_log import ScriptingLogTailer
from comstar_game_ai.game_io.state_machine import GameStateDetector

_LOGGER = logging.getLogger(__name__)


@dataclass
class HardcodedCampaignDriver:
    """Minimal end-to-end campaign loop without reasoning."""

    belief: BeliefStore = field(default_factory=BeliefStore)
    actuator: ConsoleActuator = field(default_factory=ConsoleActuator)
    state: GameStateDetector = field(default_factory=GameStateDetector)
    log_tailer: ScriptingLogTailer = field(default_factory=ScriptingLogTailer)
    intent_writer: IntentRecordWriter = field(default_factory=IntentRecordWriter)
    player_faction: str = "julii"

    def poll_observation(self) -> int:
        """Ingest new script telemetry into belief + state; return line count."""
        count = 0
        for record in self.log_tailer.poll():
            count += 1
            self.state.update_from_script_event(record)
            self._ingest_entity_record(record)
        if count:
            self.belief.decay()
        return count

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

    def run_turn_stub(self) -> bool:
        """Halt AI, declare intent, issue a no-op observation command, resume AI."""
        if not self.state.allows_campaign_orders():
            _LOGGER.info("skip turn — state=%s", self.state.state.value)
            return False

        halt = f"halt_ai {self.player_faction}"
        intent = {"objective": "observe", "turn": self.state.turn}
        action = {"type": "console", "command": "list_characters"}
        expected = {"state": "campaign_map"}

        record = self.intent_writer.declare(
            question_id="hardcoded-turn",
            ply_or_tick=self.state.turn,
            state_hash=str(self.state.turn or 0),
            intent=intent,
            action=action,
            expected_effect=expected,
        )

        ok = self.actuator.send(halt, require_campaign=True)
        ok = self.actuator.send("list_characters", require_campaign=True) and ok
        ok = self.actuator.send("run_ai", require_campaign=True) and ok

        self.intent_writer.complete(record, observed_effect={"state": self.state.state.value}, latency_ms=0.0)
        return ok
