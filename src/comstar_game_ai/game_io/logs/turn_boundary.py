"""Detect campaign turn boundaries in message_log."""

from __future__ import annotations

import re
import time

from comstar_game_ai.game_io.logs.message_log import default_message_log_path

# Rome writes `Campaign saved: "...Turn 18 End.sav"` the moment the player ends a turn,
# before the AI factions move, so the turn number in that line is the only proof a turn
# actually ended. The `new round start turn(...)` line marks the player's *next* turn and
# arrives seconds later, once the AI round finishes — late enough to land inside the next
# End Turn attempt's wait window, where it read as an instant success.
_TURN_END_RE = re.compile(r"Turn\s+(\d+)\s+End", re.I)

# The log runs to tens of megabytes over a campaign, and turn numbers only ever climb,
# so the highest one is always near the end.
_TAIL_BYTES = 262_144


def message_log_snapshot() -> tuple[int, str]:
    path = default_message_log_path()
    if not path.is_file():
        return 0, ""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return len(raw), text[-6000:]


def latest_turn_end() -> int | None:
    """Highest turn number Rome has autosaved, or None if it has autosaved none."""
    path = default_message_log_path()
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - _TAIL_BYTES))
            tail = handle.read()
    except OSError:
        return None

    numbers = _turn_numbers(tail)
    if numbers:
        return max(numbers)
    if size <= _TAIL_BYTES:
        return None
    try:
        numbers = _turn_numbers(path.read_bytes())
    except OSError:
        return None
    return max(numbers) if numbers else None


def _turn_numbers(raw: bytes) -> list[int]:
    text = raw.decode("utf-8", errors="replace")
    return [int(match.group(1)) for match in _TURN_END_RE.finditer(text)]


def wait_for_turn_end(
    baseline: int | None,
    *,
    timeout_s: float = 8.0,
    poll_s: float = 0.35,
) -> int | None:
    """The new turn number once Rome autosaves a turn later than ``baseline``.

    Scoring log growth, or any boundary-looking line, instead of comparing turn numbers
    double-counted turns: 20 End Turn attempts were reported as 19 successes while the
    campaign advanced 10 turns.
    """
    deadline = time.time() + timeout_s
    while True:
        latest = latest_turn_end()
        if latest is not None and (baseline is None or latest > baseline):
            return latest
        if time.time() >= deadline:
            return None
        time.sleep(poll_s)
