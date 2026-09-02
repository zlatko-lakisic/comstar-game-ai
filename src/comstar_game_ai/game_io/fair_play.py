"""Fair-play console command gate."""

from __future__ import annotations

from enum import Enum


class CommandClass(str, Enum):
    ALLOWED = "allowed"
    EVALUATION_ONLY = "evaluation_only"
    NEVER = "never"


ALLOWED_PREFIXES = (
    "move_character",
    "diplomatic_stance",
    "force_diplomacy",
    "diplomacy_mission",
    "halt_ai",
    "run_ai",
    "ai_turn_speed",
    "disable_ai",
    "list_characters",
    "list_units",
    "show_cursorstat",
    "output_unit_positions",
    "toggle_game_update",
    "show_battle_paths",
    "show_battle_line",
    "show_battle_circle",
    "show_battle_marker",
)

EVALUATION_ONLY = frozenset({"toggle_fow", "toggle_perfect_spy"})

NEVER = frozenset(
    {
        "add_money",
        "auto_win",
        "force_battle_victory",
        "force_autoresolve_outcome",
        "capture_settlement",
        "process_cq",
        "create_unit",
        "give_trait",
        "create_building",
    }
)


class FairPlayGate:
    """Classify RomeShell commands; block cheats at runtime."""

    def __init__(self) -> None:
        self.evaluation_tainted = False

    def classify(self, command: str) -> CommandClass:
        base = command.strip().split()[0].lower() if command.strip() else ""
        if base in NEVER:
            return CommandClass.NEVER
        if base in EVALUATION_ONLY:
            return CommandClass.EVALUATION_ONLY
        if base in ALLOWED_PREFIXES or base.startswith("show_"):
            return CommandClass.ALLOWED
        # Unknown commands default to never — fail closed.
        return CommandClass.NEVER

    def allow(self, command: str) -> bool:
        cls = self.classify(command)
        if cls == CommandClass.EVALUATION_ONLY:
            self.evaluation_tainted = True
            return True
        return cls == CommandClass.ALLOWED
