"""Acceptance: intent record round-trip."""

import tempfile
from pathlib import Path

from comstar_game_ai.game_io.intent_record import IntentRecordWriter


def test_intent_record_jsonl():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "intent.jsonl"
        writer = IntentRecordWriter(path=path)
        rec = writer.declare(
            question_id="q1",
            ply_or_tick=1,
            state_hash="abc",
            intent={"move": True},
            action={"cmd": "move_character"},
            expected_effect={"ok": True},
        )
        writer.complete(rec, observed_effect={"ok": True}, latency_ms=10.0)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 2
