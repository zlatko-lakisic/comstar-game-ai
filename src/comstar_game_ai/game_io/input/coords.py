"""Coordinate transforms for multi-monitor setups."""

from __future__ import annotations

from dataclasses import dataclass

from comstar_game_ai.game_io.display.monitors import MonitorRect, get_monitor, list_monitors
from comstar_game_ai.shared.config import load_config


@dataclass
class CoordinateTransform:
    """Map game-client coordinates to screen pixels."""

    game_monitor: MonitorRect
    client_origin: tuple[int, int] = (0, 0)
    scale_x: float = 1.0
    scale_y: float = 1.0

    @classmethod
    def from_config(cls, *, client_origin: tuple[int, int] = (0, 0)) -> CoordinateTransform:
        cfg = load_config()
        display = cfg.get("display", {})
        monitor_index = int(display.get("game_monitor_index", 1))
        mon = get_monitor(monitor_index) or (list_monitors()[0] if list_monitors() else None)
        if mon is None:
            mon = MonitorRect(index=1, left=0, top=0, right=1920, bottom=1080)
        return cls(game_monitor=mon, client_origin=client_origin)

    def game_to_screen(self, x: float, y: float) -> tuple[int, int]:
        sx = int(self.game_monitor.left + self.client_origin[0] + x * self.scale_x)
        sy = int(self.game_monitor.top + self.client_origin[1] + y * self.scale_y)
        return sx, sy

    def screen_to_game(self, screen_x: int, screen_y: int) -> tuple[float, float]:
        gx = (screen_x - self.game_monitor.left - self.client_origin[0]) / self.scale_x
        gy = (screen_y - self.game_monitor.top - self.client_origin[1]) / self.scale_y
        return gx, gy

    def cursor_monitor_offset(self) -> tuple[int, int]:
        cfg = load_config()
        display = cfg.get("display", {})
        cursor_index = int(display.get("cursor_monitor_index", 1))
        cursor_mon = get_monitor(cursor_index)
        if cursor_mon is None:
            return 0, 0
        return cursor_mon.left - self.game_monitor.left, cursor_mon.top - self.game_monitor.top
