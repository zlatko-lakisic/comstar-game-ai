"""Multi-monitor helpers for game on monitor 2."""

from __future__ import annotations

import sys
from dataclasses import dataclass

if sys.platform == "win32":
    import win32api
    import win32con
    import win32gui
else:
    win32api = None  # type: ignore[assignment]


@dataclass
class MonitorRect:
    index: int  # 1-based
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def list_monitors() -> list[MonitorRect]:
    if win32api is None:
        return []
    monitors: list[MonitorRect] = []

    def cb(hmon, _hdc, rect, _data):
        info = win32api.GetMonitorInfo(hmon)
        r = info["Monitor"]
        monitors.append(MonitorRect(index=len(monitors) + 1, left=r[0], top=r[1], right=r[2], bottom=r[3]))
        return True

    win32gui.EnumDisplayMonitors(None, None, cb, None)
    return monitors


def get_monitor(index: int) -> MonitorRect | None:
    monitors = list_monitors()
    for m in monitors:
        if m.index == index:
            return m
    return monitors[index - 1] if 0 < index <= len(monitors) else None


def move_window_to_monitor(hwnd: int, monitor_index: int) -> bool:
    if win32gui is None:
        return False
    mon = get_monitor(monitor_index)
    if mon is None:
        return False
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOP,
        mon.left,
        mon.top,
        mon.width,
        mon.height,
        win32con.SWP_SHOWWINDOW,
    )
    return True
