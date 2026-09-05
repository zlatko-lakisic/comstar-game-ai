"""Detect campaign turn boundaries from Rome's autosaves and message_log."""

from __future__ import annotations

import re
import time

from comstar_game_ai.game_io.logs.message_log import default_message_log_path, default_saves_dir

# Ending a turn makes Rome autosave `Turn 18 End.sav` and log a matching line, both
# before the AI factions move, so that turn number is the proof a turn actually ended.
# The same pattern matches the filename and the log line.
#
# The `new round start turn(...)` line is not proof: it arrives once the AI round
# finishes, seconds to a minute later, which usually falls inside the next End Turn
# attempt's wait window, where it read as an instant success and double-counted turns.
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
    """Highest turn Rome has recorded as ended, or None if it has ended none.

    Both records are consulted and the higher wins, because neither is always written:
    a session has been observed playing a whole campaign with message_log.txt frozen at
    its startup contents, while the autosave file for every ended turn appeared on disk.
    """
    candidates = [n for n in (_latest_turn_end_from_saves(), _latest_turn_end_from_log()) if n]
    return max(candidates) if candidates else None


def _latest_turn_end_from_saves() -> int | None:
    """Turn number of the most recently written `...Turn N End.sav` autosave.

    Deliberately the newest file rather than the highest number: the folder keeps
    autosaves from earlier campaigns, and an abandoned campaign that reached turn 69
    would otherwise mask a fresh one sitting on turn 3 forever.
    """
    saves = default_saves_dir()
    if not saves.is_dir():
        return None
    newest_turn: int | None = None
    newest_mtime = -1.0
    try:
        entries = list(saves.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.suffix.lower() != ".sav":
            continue
        match = _TURN_END_RE.search(entry.name)
        if match is None:
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest_turn = int(match.group(1))
    return newest_turn


def _latest_turn_end_from_log() -> int | None:
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
