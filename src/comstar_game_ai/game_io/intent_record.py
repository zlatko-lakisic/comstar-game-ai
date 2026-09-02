"""JSONL intent record per action handoff."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from comstar_game_ai.shared.config import repo_root


def default_intent_log_dir() -> Path:
    return repo_root() / "data" / "intent_records"


@dataclass
class IntentRecord:
    question_id: str
    ply_or_tick: int | None
    state_hash: str
    intent: dict[str, Any]
    action: dict[str, Any]
    expected_effect: dict[str, Any] = field(default_factory=dict)
    observed_effect: dict[str, Any] | None = None
    latency_ms: float | None = None
    handoff_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentRecordWriter:
    """Append-only JSONL writer, one file per handoff session."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (default_intent_log_dir() / f"handoff_{int(time.time())}.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: IntentRecord) -> Path:
        line = json.dumps(record.to_dict(), separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return self.path

    def declare(
        self,
        *,
        question_id: str,
        ply_or_tick: int | None,
        state_hash: str,
        intent: dict[str, Any],
        action: dict[str, Any],
        expected_effect: dict[str, Any] | None = None,
    ) -> IntentRecord:
        record = IntentRecord(
            question_id=question_id,
            ply_or_tick=ply_or_tick,
            state_hash=state_hash,
            intent=intent,
            action=action,
            expected_effect=expected_effect or {},
        )
        self.write(record)
        return record

    def complete(self, record: IntentRecord, observed_effect: dict[str, Any], latency_ms: float) -> IntentRecord:
        record.observed_effect = observed_effect
        record.latency_ms = latency_ms
        self.write(record)
        return record
