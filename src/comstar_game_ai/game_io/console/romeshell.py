"""RomeShell console channel (backtick opens console)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from comstar_game_ai.game_io.input.send_input import SendInputController, normalize_key_name
from comstar_game_ai.game_io.window import find_game_window, get_foreground_hwnd
from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)

CONSOLE_TOGGLE_KEY = "`"
CONSOLE_SUBMIT_KEY = "enter"


@dataclass
class RomeShell:
    """Open the Rome console and submit commands via synthetic input."""

    hwnd: int | None = None
    input_controller: SendInputController | None = None
    console_open: bool = False
    dwell_ms: int = 40

    def __post_init__(self) -> None:
        if self.input_controller is None:
            self.input_controller = SendInputController()

    def resolve_hwnd(self) -> int | None:
        if self.hwnd is not None:
            return self.hwnd
        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
        game = find_game_window(subs)
        return game.hwnd if game else None

    def focus_game(self) -> bool:
        hwnd = self.resolve_hwnd()
        if hwnd is None:
            _LOGGER.warning("RomeShell: game window not found")
            return False
        return self.input_controller.focus_window(hwnd)

    def open_console(self) -> bool:
        """Toggle console open with grave/backtick."""
        if not self.focus_game():
            return False
        ok = self.input_controller.tap_key(CONSOLE_TOGGLE_KEY, dwell_ms=self.dwell_ms)
        if ok:
            self.console_open = True
            time.sleep(self.dwell_ms / 1000.0)
        return ok

    def close_console(self) -> bool:
        if not self.console_open:
            return True
        ok = self.input_controller.tap_key(CONSOLE_TOGGLE_KEY, dwell_ms=self.dwell_ms)
        if ok:
            self.console_open = False
        return ok

    def send_command(self, command: str, *, open_console: bool = True) -> bool:
        """Focus game, open console if needed, type command, press enter."""
        command = command.strip()
        if not command:
            return False

        if not self.focus_game():
            return False

        fg = get_foreground_hwnd()
        hwnd = self.resolve_hwnd()
        if hwnd is not None and fg != hwnd:
            _LOGGER.warning("RomeShell: game not foreground after focus attempt")

        if open_console and not self.console_open:
            if not self.open_console():
                return False

        typed = self.input_controller.type_text(command, dwell_ms=self.dwell_ms)
        submitted = self.input_controller.tap_key(CONSOLE_SUBMIT_KEY, dwell_ms=self.dwell_ms)
        return typed and submitted

    def end_turn(self) -> bool:
        hwnd = self.resolve_hwnd()
        if hwnd is None:
            _LOGGER.warning("RomeShell: end_turn — game window not found")
            return False
        from comstar_game_ai.game_io.campaign.end_turn import end_turn_campaign

        ok, method = end_turn_campaign(
            hwnd=hwnd,
            input_controller=self.input_controller,
            console_open=self.console_open,
            dwell_ms=self.dwell_ms,
        )
        if ok:
            self.console_open = False
            _LOGGER.info("RomeShell: end_turn ok via %s", method)
        else:
            _LOGGER.warning("RomeShell: end_turn failed (%s)", method)
        return ok

    def send_raw_keys(self, keys: list[str]) -> bool:
        normalized = [normalize_key_name(k) for k in keys]
        return self.input_controller.send_keys(normalized, dwell_ms=self.dwell_ms)
