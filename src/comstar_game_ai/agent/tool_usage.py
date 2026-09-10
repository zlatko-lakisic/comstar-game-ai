"""Measure campaign_director use of client.game_query (C10)."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comstar_game_ai.shared.config import repo_root

_LOGGER = logging.getLogger(__name__)
_LOCK = threading.Lock()


@dataclass
class ToolCallRecord:
    turn: int | None
    tool: str
    asked: str
    changed_directive: bool = False


@dataclass
class ToolUsageLog:
    """Append-only log of game_query calls and whether they changed the directive."""

    path: Path = field(
        default_factory=lambda: repo_root() / "data" / "runtime" / "game_query_usage.jsonl"
    )
    calls: list[ToolCallRecord] = field(default_factory=list)

    def record(
        self,
        *,
        turn: int | None,
        tool: str,
        asked: str,
        changed_directive: bool = False,
    ) -> None:
        row = ToolCallRecord(
            turn=turn, tool=tool, asked=asked, changed_directive=changed_directive
        )
        with _LOCK:
            self.calls.append(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "turn": turn,
                            "tool": tool,
                            "asked": asked,
                            "changed_directive": changed_directive,
                        }
                    )
                    + "\n"
                )
        _LOGGER.info(
            "game_query usage turn=%s tool=%s changed=%s asked=%s",
            turn,
            tool,
            changed_directive,
            asked[:120],
        )

    def summary(self) -> dict[str, int]:
        with _LOCK:
            total = len(self.calls)
            changed = sum(1 for c in self.calls if c.changed_directive)
        return {"calls": total, "changed_directive": changed}


_DEFAULT = ToolUsageLog()


def default_tool_usage_log() -> ToolUsageLog:
    return _DEFAULT
