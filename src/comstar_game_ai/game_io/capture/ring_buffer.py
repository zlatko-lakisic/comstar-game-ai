"""Rolling frame ring buffer for backward frame selection."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass
class Frame:
    timestamp: float
    data: bytes
    width: int
    height: int


class RingBuffer:
    def __init__(self, max_seconds: float = 5.0) -> None:
        self.max_seconds = max_seconds
        self._frames: Deque[Frame] = deque()

    def push(self, data: bytes, width: int, height: int, ts: float | None = None) -> None:
        now = ts if ts is not None else time.monotonic()
        self._frames.append(Frame(timestamp=now, data=data, width=width, height=height))
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self.max_seconds
        while self._frames and self._frames[0].timestamp < cutoff:
            self._frames.popleft()

    def __len__(self) -> int:
        return len(self._frames)

    def latest(self) -> Frame | None:
        return self._frames[-1] if self._frames else None

    def select_before(self, event_time: float, count: int = 1) -> list[Frame]:
        """Frames at or before event_time, newest first."""
        candidates = [f for f in self._frames if f.timestamp <= event_time]
        candidates.sort(key=lambda f: f.timestamp, reverse=True)
        return candidates[:count]
