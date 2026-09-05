"""Tail Rome message_log.txt."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from comstar_game_ai.shared.config import load_config


def expand_user_path(path_str: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def default_rome_logs_dir() -> Path:
    cfg = load_config()
    logs = cfg.get("paths", {}).get("rome_logs") or "%USERPROFILE%/AppData/Local/Feral Interactive/Rome/logs"
    return expand_user_path(logs)


def default_message_log_path() -> Path:
    return default_rome_logs_dir() / "message_log.txt"


def default_saves_dir() -> Path:
    """Rome's save folder, the sibling of its log folder.

    Autosaves are the only turn record that is always written: a session has been
    observed playing a full campaign while message_log.txt stayed frozen at its
    startup contents.
    """
    cfg = load_config()
    saves = cfg.get("paths", {}).get("rome_saves")
    if saves:
        return expand_user_path(saves)
    return default_rome_logs_dir().parent / "saves"


@dataclass
class MessageLogTailer:
    """Incrementally tail message_log.txt (raw text lines)."""

    path: Path | None = None
    _offset: int = field(default=0, init=False)
    _partial: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = default_message_log_path()

    def reset(self) -> None:
        self._offset = 0
        self._partial = ""

    def seek_end(self) -> None:
        path = self.path
        if path is None or not path.is_file():
            self._offset = 0
            return
        self._offset = path.stat().st_size

    def poll(self) -> list[str]:
        path = self.path
        if path is None or not path.is_file():
            return []

        with path.open(encoding="utf-8", errors="replace") as fh:
            fh.seek(self._offset)
            chunk = fh.read()
            self._offset = fh.tell()

        if not chunk:
            return []

        text = self._partial + chunk
        lines = text.splitlines()
        if text and not text.endswith(("\n", "\r")):
            self._partial = lines.pop() if lines else text
        else:
            self._partial = ""

        return [line for line in lines if line.strip()]
