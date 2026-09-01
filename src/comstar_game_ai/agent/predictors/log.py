"""Prediction JSONL log — every output paired with observed outcome."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


@dataclass
class PredictionEntry:
    entry_id: str
    predictor: str
    predicted: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    observed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "predictor": self.predictor,
            "predicted": self.predicted,
            "context": self.context,
            "timestamp": self.timestamp,
            "observed": self.observed,
        }


class PredictionLog:
    """Append-only JSONL log of predictions and outcomes."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._pending: dict[str, PredictionEntry] = {}

    @property
    def path(self) -> Path:
        return self._path

    def log_prediction(
        self,
        predictor: str,
        predicted: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> str:
        entry = PredictionEntry(
            entry_id=entry_id or uuid.uuid4().hex,
            predictor=predictor,
            predicted=dict(predicted),
            context=dict(context or {}),
        )
        self._pending[entry.entry_id] = entry
        self._append(entry.to_dict())
        return entry.entry_id

    def record_outcome(self, entry_id: str, observed: dict[str, Any]) -> bool:
        if entry_id not in self._pending:
            return False
        entry = self._pending.pop(entry_id)
        row = entry.to_dict()
        row["observed"] = dict(observed)
        row["paired_at"] = time.time()
        self._append(row)
        return True

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _append(self, row: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            self._write_line(fh, row)

    @staticmethod
    def _write_line(fh: TextIO, row: dict[str, Any]) -> None:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
