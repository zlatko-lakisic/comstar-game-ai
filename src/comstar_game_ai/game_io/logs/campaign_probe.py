"""Infer campaign-map state from Rome engine logs when script events are not yet available."""

from __future__ import annotations

import re

_FACTION_ALIASES: dict[str, str] = {
    "julii": "romans_julii",
    "brutii": "romans_brutii",
    "scipii": "romans_scipii",
}

_STRATMAP_RE = re.compile(r"music manager being set to state stratmap", re.I)
_PLAYER_TURN_RE = re.compile(r"new round start turn\(([^)]+)\)", re.I)
_AUTOSAVE_TURN_RE = re.compile(r"turn\s+(\d+)\s+start", re.I)
_AUTOSAVE_JULII_RE = re.compile(
    r"Campaign saved:.*House of Julii\s+Turn\s+(\d+)\s+Start",
    re.I,
)
_LOAD_JULII_RE = re.compile(
    r'Attempting to load ".*House of Julii\s+Turn\s+(\d+)\s+(Start|End)',
    re.I,
)
_FRONTEND_RE = re.compile(r"music manager being set to state frontend", re.I)


def player_faction_log_name(faction: str) -> str:
    key = faction.strip().lower().replace("romans_", "")
    return _FACTION_ALIASES.get(key, faction)


def count_player_turn_starts(text: str, *, player_faction: str = "julii") -> int:
    """Count Julii (player) turn-start lines already present in message_log."""
    log_faction = player_faction_log_name(player_faction)
    count = 0
    for match in _PLAYER_TURN_RE.finditer(text):
        if match.group(1).lower() == log_faction.lower():
            count += 1
    return count


def latest_julii_autosave_turn(text: str) -> int | None:
    """Latest 'Turn N Start' autosave line for The House of Julii."""
    latest: int | None = None
    for match in _AUTOSAVE_JULII_RE.finditer(text):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if latest is None or n > latest:
            latest = n
    return latest


def latest_julii_load_turn(text: str) -> int | None:
    """Turn number from 'Attempting to load ... House of Julii Turn N Start|End'."""
    latest: int | None = None
    for match in _LOAD_JULII_RE.finditer(text):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if latest is None or n > latest:
            latest = n
    return latest


def summarize_julii_turn_markers(text: str, *, player_faction: str = "julii") -> dict[str, int | None]:
    """Round-start line count and best-known Julii turn from message_log."""
    autosave = latest_julii_autosave_turn(text)
    load_turn = latest_julii_load_turn(text)
    known_turn = autosave
    if load_turn is not None and (known_turn is None or load_turn > known_turn):
        known_turn = load_turn
    return {
        "round_starts": count_player_turn_starts(text, player_faction=player_faction),
        "autosave_turn": autosave,
        "load_turn": load_turn,
        "known_turn": known_turn,
    }


def is_campaign_session_ready(
    text: str,
    *,
    player_faction: str = "julii",
) -> tuple[bool, int | None]:
    """True when message_log shows Julii stratmap session is loaded and playable."""
    on_map, turn = infer_campaign_map_from_message_log(text, player_faction=player_faction)
    if not on_map:
        return False, None

    markers = summarize_julii_turn_markers(text, player_faction=player_faction)
    known = markers.get("known_turn")
    if known is not None:
        return True, int(known)

    lower = text[-8000:].lower()
    if "initialise timer for time taken for ai turns" in lower:
        return True, turn

    return False, turn


def infer_campaign_map_from_message_log(
    text: str,
    *,
    player_faction: str = "julii",
) -> tuple[bool, int | None]:
    """
    Return (on_campaign_map, turn_number_if_known).

    Uses message_log heuristics so automation can start mid-turn without waiting
    for NewTurnStart (which only fires at turn boundaries).
    """
    if not text.strip():
        return False, None

    log_faction = player_faction_log_name(player_faction)
    tail = text[-12000:]
    lower = tail.lower()

    if _FRONTEND_RE.search(tail) and not _STRATMAP_RE.search(tail):
        return False, None

    on_map = bool(_STRATMAP_RE.search(tail))
    if not on_map:
        return False, None

    turn: int | None = latest_julii_autosave_turn(tail)
    if turn is None:
        turn = latest_julii_load_turn(tail)
    if turn is None:
        for match in _AUTOSAVE_TURN_RE.finditer(tail):
            try:
                turn = int(match.group(1))
            except ValueError:
                continue

    player_turn = _PLAYER_TURN_RE.search(tail)
    if player_turn and player_turn.group(1).lower() == log_faction.lower():
        on_map = True

    return on_map, turn


def wait_for_campaign_ready(
    *,
    player_faction: str = "julii",
    timeout_s: float = 1800.0,
    poll_s: float = 2.0,
    log_fn=print,
) -> tuple[bool, int | None]:
    """Poll message_log until Julii campaign is ready or timeout."""
    import time

    from comstar_game_ai.game_io.logs.message_log import default_message_log_path
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    deadline = time.time() + timeout_s
    path = default_message_log_path()
    last_hint = ""

    while time.time() < deadline:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            ready, turn = is_campaign_session_ready(text, player_faction=player_faction)
            if ready:
                return True, turn

            tail = text[-4000:].lower()
            if "music manager being set to state frontend" in tail and "stratmap" not in tail:
                hint = "main menu — load your Julii save in Rome"
            elif "campaign_loading" in tail or "loading savegame" in tail:
                hint = "save loading..."
            elif "stratmap" in tail:
                hint = "on stratmap, waiting for session markers..."
            else:
                hint = "waiting for campaign map..."
            if hint != last_hint:
                log_fn(f"WAIT  {hint}")
                last_hint = hint
        else:
            if last_hint != "waiting for message_log.txt...":
                log_fn("WAIT  waiting for message_log.txt...")
                last_hint = "waiting for message_log.txt..."

        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
        if find_game_window(subs) is None:
            log_fn("WARN  Rome window not found — is the game still running?")

        time.sleep(poll_s)

    return False, None
