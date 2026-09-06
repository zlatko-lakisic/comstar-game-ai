"""Is the game actually talking to us, before a run spends twenty turns finding out.

Rome writes its logs only when launched with `enable_logging`, and the scripting log
only with `verbose_script_logging`. Neither is visible from inside the game: the mod
loads, the console accepts commands, turns advance, and every telemetry channel stays
silent. A run in that state drives the campaign blind and records nothing, so this is
a preflight rather than a diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from comstar_game_ai.game_io.logs.message_log import default_message_log_path
from comstar_game_ai.game_io.logs.scripting_log import default_scripting_log_path

# Rome prints this in the message log header when it was launched without the switch,
# which is the only self-report of the failure we get.
_DISABLED_MARKER = "logging disabled"

# The header is a few hundred bytes; the rest of the file can be tens of megabytes.
_HEADER_BYTES = 4096


@dataclass(frozen=True)
class TelemetryHealth:
    """What the log files say about our two read channels."""

    message_log: bool
    script_log: bool
    detail: str

    @property
    def ok(self) -> bool:
        """Both channels available, i.e. belief can actually be populated."""
        return self.message_log and self.script_log

    @property
    def summary(self) -> str:
        state = "ok" if self.ok else "degraded"
        return f"telemetry {state}: {self.detail}"


def telemetry_health(
    *,
    message_log_path: Path | None = None,
    script_log_path: Path | None = None,
) -> TelemetryHealth:
    message_log = message_log_path or default_message_log_path()
    script_log = script_log_path or default_scripting_log_path()

    reasons: list[str] = []

    if not message_log.is_file():
        message_ok = False
        reasons.append("no message_log.txt")
    else:
        header = _read_header(message_log)
        message_ok = _DISABLED_MARKER not in header.lower()
        if not message_ok:
            # Frozen at its startup contents: turn markers, faction lines and console
            # output never arrive, and the file's own header says so.
            reasons.append("message_log.txt says logging is disabled")

    script_ok = script_log.is_file()
    if not script_ok:
        reasons.append("no scripting_log.txt (needs -verbose_script_logging)")

    if message_ok and script_ok:
        reasons.append("message_log.txt and scripting_log.txt both present")

    return TelemetryHealth(message_log=message_ok, script_log=script_ok, detail="; ".join(reasons))


def _read_header(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(_HEADER_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""
