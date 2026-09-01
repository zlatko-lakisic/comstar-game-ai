"""IPC event types for Process A/B -> Process C."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    POINTER_MOVED = "pointer_moved"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    INTENT_DECLARED = "intent_declared"
    VERIFICATION = "verification"
    FREEZE = "freeze"
    RESUME = "resume"
    AO_REQUEST = "ao_request"
    AO_STATUS = "ao_status"
    AO_RESULT = "ao_result"
    AGENT_SUSPENDED = "agent_suspended"
    AGENT_RESUMED = "agent_resumed"
    CONTROL_STATE = "control_state"


@dataclass
class IpcEvent:
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0

    def to_json(self) -> str:
        return json.dumps({"kind": self.kind.value, "payload": self.payload, "ts": self.ts})

    @classmethod
    def from_json(cls, line: str) -> IpcEvent:
        data = json.loads(line)
        return cls(
            kind=EventKind(data["kind"]),
            payload=dict(data.get("payload") or {}),
            ts=float(data.get("ts") or 0),
        )
