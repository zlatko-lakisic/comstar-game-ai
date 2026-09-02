"""Offline consolidator stub — reads privileged records, proposes doctrine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from comstar_game_ai.agent.records.privileged_store import PrivilegedStore


@dataclass
class DoctrineProposal:
    heading: str
    body: str
    source_record_types: list[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading": self.heading,
            "body": self.body,
            "source_record_types": self.source_record_types,
            "confidence": self.confidence,
        }


def consolidate_offline(
    store: PrivilegedStore | None = None,
    *,
    min_records: int = 1,
) -> list[DoctrineProposal]:
    """Stub consolidator: scan privileged JSONL and emit placeholder proposals.

    Phase 7 is blocked on AO KB write path; this runs locally and returns
    proposals for the host app to review or ingest later.
    """
    privileged = store or PrivilegedStore()
    records = privileged.read_all()
    if len(records) < min_records:
        return []

    by_type: dict[str, int] = {}
    for rec in records:
        by_type[rec.record_type] = by_type.get(rec.record_type, 0) + 1

    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
    return [
        DoctrineProposal(
            heading="Consolidation stub",
            body=(
                f"Reviewed {len(records)} privileged records ({summary}). "
                "Replace this stub with dynamic consolidation via client.consolidator."
            ),
            source_record_types=sorted(by_type.keys()),
            confidence=0.1,
        )
    ]


def proposals_as_json(proposals: list[DoctrineProposal]) -> str:
    return json.dumps([p.to_dict() for p in proposals], indent=2)
