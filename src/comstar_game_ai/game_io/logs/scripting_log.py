"""Tail and parse Rome scripting_log.txt (key=value telemetry)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from comstar_game_ai.shared.config import load_config

_KV_PATTERN = re.compile(r'(\w+)=(".*?"|[^"\s]+)')
_VERBOSE_SCRIPT_LOG = re.compile(r"\([^:]+::(\d+)\) Executing command script_log")
_SCRIPT_LOG_EVENT = re.compile(r"script_log\s+event=(\w+)")


def expand_user_path(path_str: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def default_scripting_log_path() -> Path:
    cfg = load_config()
    logs = cfg.get("paths", {}).get("rome_logs") or "%USERPROFILE%/AppData/Local/Feral Interactive/Rome/logs"
    return expand_user_path(logs) / "scripting_log.txt"


def discover_comstar_telemetry_line_map() -> dict[int, str]:
    """Map tutorial.txt line numbers to event names from the installed telemetry mod."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    tutorial = (
        Path(localappdata)
        / "Feral Interactive/Total War ROME REMASTERED/Mods/Local Mods/comstar-telemetry"
        / "data/world/maps/campaign/imperial_campaign/tutorial.txt"
    )
    if not tutorial.is_file():
        return {1758: "NewTurnStart", 1762: "I_BattleEndPending", 1766: "I_BattleEnd", 1770: "I_BattleFinished"}

    mapping: dict[int, str] = {}
    for line_no, line in enumerate(tutorial.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        match = _SCRIPT_LOG_EVENT.search(line)
        if match:
            mapping[line_no] = match.group(1)
    return mapping or {1758: "NewTurnStart", 1762: "I_BattleEndPending", 1766: "I_BattleEnd", 1770: "I_BattleFinished"}


def parse_key_value_line(line: str) -> dict[str, str]:
    """Parse `key=value` tokens; quoted values may contain spaces."""
    out: dict[str, str] = {}
    for match in _KV_PATTERN.finditer(line.strip()):
        key = match.group(1)
        raw = match.group(2)
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        out[key] = raw
    return out


def parse_verbose_script_log_line(line: str, line_map: dict[int, str]) -> dict[str, str] | None:
    """Parse Remastered verbose_script_logging lines for script_log execution."""
    match = _VERBOSE_SCRIPT_LOG.search(line)
    if not match:
        return None
    line_no = int(match.group(1))
    event = line_map.get(line_no)
    if not event:
        return None
    return {"event": event, "source": "verbose_script_log", "script_line": str(line_no)}


@dataclass
class ScriptingLogTailer:
    """Incrementally tail scripting_log.txt and parse structured lines."""

    path: Path | None = None
    _offset: int = field(default=0, init=False)
    _partial: str = field(default="", init=False)
    _telemetry_line_map: dict[int, str] = field(default_factory=discover_comstar_telemetry_line_map, init=False)

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = default_scripting_log_path()

    def reset(self) -> None:
        self._offset = 0
        self._partial = ""

    def seek_end(self) -> None:
        path = self.path
        if path is None or not path.is_file():
            self._offset = 0
            return
        self._offset = path.stat().st_size

    def poll(self) -> list[dict[str, str]]:
        """Return newly appended parsed lines since the last poll."""
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

        records: list[dict[str, str]] = []
        for line in lines:
            if not line.strip():
                continue
            rec = parse_key_value_line(line)
            if rec.get("event"):
                records.append(rec)
                continue
            verbose = parse_verbose_script_log_line(line, self._telemetry_line_map)
            if verbose:
                records.append(verbose)
        return records

    def tail_events(self, event_name: str | None = None) -> Iterator[dict[str, str]]:
        for record in self.poll():
            if event_name is None or record.get("event") == event_name:
                yield record
