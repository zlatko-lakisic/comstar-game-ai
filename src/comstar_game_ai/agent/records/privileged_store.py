"""Local privileged JSONL store (offline-only, never served to play loop)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from comstar_game_ai.shared.config import repo_root


def privileged_records_path() -> Path:
    return repo_root() / "data" / "records" / "privileged.jsonl"


@dataclass
class PrivilegedRecord:
    record_type: str
    privileged: dict[str, Any]
    observable_ref: str | None = None
    campaign_id: str | None = None
    turn: int | None = None
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_line(cls, line: str) -> PrivilegedRecord:
        data = json.loads(line)
        return cls(
            record_type=str(data.get("record_type") or "unknown"),
            privileged=dict(data.get("privileged") or {}),
            observable_ref=data.get("observable_ref"),
            campaign_id=data.get("campaign_id"),
            turn=data.get("turn"),
            ts=str(data.get("ts") or ""),
        )


class PrivilegedStore:
    """Append-only local JSONL for privileged learning data."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or privileged_records_path()

    def append(self, record: PrivilegedRecord | dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(record, PrivilegedRecord):
            line = record.to_line()
        else:
            line = json.dumps(record, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return self.path

    def iter_records(self) -> Iterator[PrivilegedRecord]:
        if not self.path.is_file():
            return iter(())

        def _gen() -> Iterator[PrivilegedRecord]:
            with self.path.open(encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        yield PrivilegedRecord.from_line(raw)
                    except json.JSONDecodeError:
                        continue

        return _gen()

    def read_all(self) -> list[PrivilegedRecord]:
        return list(self.iter_records())

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        with self.path.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
