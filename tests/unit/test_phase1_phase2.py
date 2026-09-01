"""Unit tests for Phase 1/2 observation and actuation modules."""

import json
import time

import pytest

from comstar_game_ai.agent.belief.entities import Army, ExistenceStatus
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.fair_play import FairPlayGate
from comstar_game_ai.game_io.input.diff_actuator import UnitOrder, compute_order_diff
from comstar_game_ai.game_io.input.send_input import normalize_key_name, virtual_key_for
from comstar_game_ai.game_io.intent_record import IntentRecordWriter
from comstar_game_ai.game_io.logs.scripting_log import ScriptingLogTailer, parse_key_value_line
from comstar_game_ai.game_io.state_machine import GameState, GameStateDetector
from comstar_game_ai.game_io.verification import VerificationPipeline, VerificationResult


def test_parse_key_value_line():
    record = parse_key_value_line('event=NewTurnStart turn=5 faction=julii name="Caesar IV"')
    assert record["event"] == "NewTurnStart"
    assert record["turn"] == "5"
    assert record["name"] == "Caesar IV"


def test_scripting_log_tailer(tmp_path):
    log = tmp_path / "scripting_log.txt"
    log.write_text("event=NewTurnStart turn=1 faction=julii\n", encoding="utf-8")
    tailer = ScriptingLogTailer(path=log)
    first = tailer.poll()
    assert first == [{"event": "NewTurnStart", "turn": "1", "faction": "julii"}]
    log.write_text("event=NewTurnStart turn=1 faction=julii\nentity=army id=a1 x=10 y=20\n", encoding="utf-8")
    tailer.reset()
    batch = tailer.poll()
    assert len(batch) == 2
    assert batch[1]["entity"] == "army"


def test_belief_store_update_decay():
    store = BeliefStore()
    army = Army(
        entity_id="a1",
        provenance="script_telemetry",
        observed_at=time.time() - 600,
        confidence=1.0,
        existence=ExistenceStatus.OBSERVED_PRESENT,
        faction="julii",
        strength=500,
    )
    store.update(army, now=time.time() - 600)
    store.decay(now=time.time(), half_life_seconds=300)
    updated = store.get_army_entity("a1")
    assert updated is not None
    assert updated.confidence < 1.0


def test_belief_store_legacy_compat():
    store = BeliefStore(armies={"a1": {"strength": 100}})
    assert store.get_army("a1")["strength"] == 100
    data = store.to_dict()
    restored = BeliefStore.from_dict(data)
    assert restored.get_army("a1")["strength"] == 100


def test_game_state_detector():
    det = GameStateDetector()
    changed = det.update_from_script_event({"event": "NewTurnStart", "turn": "3", "faction": "julii"})
    assert changed == GameState.CAMPAIGN_MAP
    assert det.turn == 3
    assert det.allows_campaign_orders()


def test_compute_order_diff():
    current = {"u1": UnitOrder("u1", 10, 10)}
    desired = {"u1": UnitOrder("u1", 10, 10), "u2": UnitOrder("u2", 5, 5)}
    diff = compute_order_diff(desired, current)
    assert "u1" in diff.unchanged
    assert len(diff.move) == 1
    assert diff.move[0].unit_id == "u2"


def test_intent_record_writer(tmp_path):
    writer = IntentRecordWriter(path=tmp_path / "handoff.jsonl")
    record = writer.declare(
        question_id="q1",
        ply_or_tick=1,
        state_hash="abc",
        intent={"objective": "hold"},
        action={"type": "console", "command": "run_ai"},
    )
    lines = (tmp_path / "handoff.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["question_id"] == "q1"
    writer.complete(record, observed_effect={"ok": True}, latency_ms=12.5)
    assert len((tmp_path / "handoff.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 2


def test_verification_pipeline_pass():
    pipe = VerificationPipeline()
    outcomes = pipe.verify(
        action={"type": "move"},
        expected_effect={"x": 1},
        observed={"x": 1},
    )
    assert outcomes[0].result == VerificationResult.PASS


def test_virtual_key_normalization():
    assert normalize_key_name(" Enter ") == "enter"
    assert virtual_key_for("`") == 0xC0
