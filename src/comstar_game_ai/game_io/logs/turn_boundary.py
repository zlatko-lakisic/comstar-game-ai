"""Detect campaign turn boundaries in message_log."""

from __future__ import annotations

import re
import time

from comstar_game_ai.game_io.logs.message_log import default_message_log_path

_TURN_END_RE = re.compile(r"Turn\s+\d+\s+End", re.I)
_TURN_BOUNDARY_RE = re.compile(
    r"(Turn\s+\d+\s+End|new round start turn\(|end\.sav)",
    re.I,
)


def message_log_snapshot() -> tuple[int, str]:
    path = default_message_log_path()
    if not path.is_file():
        return 0, ""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return len(raw), text[-6000:]


def turn_boundary_in_tail(tail: str) -> bool:
    lower = tail.lower()
    if "end.sav" in lower and "turn" in lower:
        return True
    if _TURN_END_RE.search(tail):
        return True
    if "new round start turn(" in lower:
        return True
    return False


def new_turn_boundary_since(before_size: int) -> bool:
    """True only when message_log grew and the *new* bytes contain a turn boundary."""
    path = default_message_log_path()
    if not path.is_file():
        return False
    raw = path.read_bytes()
    if len(raw) <= before_size:
        return False
    new_region = raw[before_size:].decode("utf-8", errors="replace")
    return bool(_TURN_BOUNDARY_RE.search(new_region))


def wait_for_turn_boundary(
    before_size: int,
    before_tail: str,
    *,
    timeout_s: float = 8.0,
    poll_s: float = 0.35,
) -> bool:
    """Return True if message_log shows a *new* turn end/start after actuation.

    Historical round-start lines already present in ``before_tail`` must not count —
    that falsely marked End Turn as successful while the game stayed on the same turn.
    """
    del before_tail  # kept for call-site compatibility
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if new_turn_boundary_since(before_size):
            return True
        time.sleep(poll_s)
    return False
