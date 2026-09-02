"""Startup preconditions from handoff section 2."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field

from comstar_game_ai.game_io.window import find_game_window, process_elevation_matches
from comstar_game_ai.shared.config import load_config

# Windows 10 2004 = build 19041
MIN_CAPTURE_BUILD = 19041


@dataclass
class PreconditionResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.ok = False
            self.failures.append(message)


def check_windows_build() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "host must be Windows"
    version = platform.version().split(".")
    try:
        build = int(version[2])
    except (IndexError, ValueError):
        return False, f"cannot parse Windows build from {platform.version()}"
    if build < MIN_CAPTURE_BUILD:
        return False, f"Windows build {build} < {MIN_CAPTURE_BUILD} (WDA_EXCLUDEFROMCAPTURE)"
    return True, f"Windows build {build}"


def check_preconditions(
    *,
    require_game: bool = False,
    pinned_version: str | None = None,
) -> PreconditionResult:
    cfg = load_config()
    result = PreconditionResult(ok=True)

    build_ok, build_msg = check_windows_build()
    result.require(build_ok, build_msg)

    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if require_game:
        result.require(game is not None, "Rome Remastered window not found")
    elif game is None:
        result.warnings.append("game window not found (skipped — not required)")

    if game is not None:
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(game.hwnd)
        result.require(
            process_elevation_matches(pid),
            "host and game integrity level mismatch (UIPI risk)",
        )

    pin = pinned_version or cfg.get("game", {}).get("pinned_version")
    if pin:
        # Version pin verified externally in Phase 0 spike; placeholder hook.
        result.warnings.append(f"version pin configured: {pin} (manual verify required)")

    return result
