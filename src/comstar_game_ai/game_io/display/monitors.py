"""Multi-monitor helpers for game on monitor 2."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

if sys.platform == "win32":
    import win32api
    import win32con
    import win32gui
else:
    win32api = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]
    win32con = None  # type: ignore[assignment]


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
    """Return connected monitors in enumeration order (1-based index)."""
    if win32api is None:
        return []

    monitors: list[MonitorRect] = []
    # pywin32: EnumDisplayMonitors() returns [(hMonitor, hdc, rect), ...]
    for idx, (hmon, _hdc, rect) in enumerate(win32api.EnumDisplayMonitors(), start=1):
        try:
            info = win32api.GetMonitorInfo(hmon)
            r = info.get("Monitor", rect)
        except Exception:
            r = rect
        monitors.append(MonitorRect(index=idx, left=r[0], top=r[1], right=r[2], bottom=r[3]))
    return monitors


def get_monitor(index: int) -> MonitorRect | None:
    monitors = list_monitors()
    for m in monitors:
        if m.index == index:
            return m
    if 0 < index <= len(monitors):
        return monitors[index - 1]
    return None


def _try_place_on_monitor(hwnd: int, mon: MonitorRect, *, resize: bool = True) -> bool:
    """Best-effort single attempt to move hwnd onto mon (optionally resize to fill monitor)."""
    if win32gui is None or win32con is None:
        return False

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    no_zorder = win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW
    if not resize:
        try:
            win32gui.SetWindowPos(
                hwnd, 0, mon.left, mon.top, 0, 0, no_zorder | win32con.SWP_NOSIZE
            )
            return True
        except Exception:
            return False

    attempts = (
        lambda: win32gui.SetWindowPos(
            hwnd, 0, mon.left, mon.top, mon.width, mon.height, no_zorder
        ),
        lambda: win32gui.SetWindowPos(
            hwnd, 0, mon.left, mon.top, 0, 0, no_zorder | win32con.SWP_NOSIZE
        ),
        lambda: win32gui.MoveWindow(hwnd, mon.left, mon.top, mon.width, mon.height, True),
    )
    for fn in attempts:
        try:
            fn()
            return True
        except Exception:
            continue
    return False


def move_window_to_monitor(
    hwnd: int,
    monitor_index: int,
    *,
    resize: bool = True,
    retries: int = 1,
    delay_s: float = 0.5,
) -> bool:
    """Move hwnd to monitor_index (1-based). Retries help while the game finishes init."""
    if win32gui is None or win32con is None:
        return False
    mon = get_monitor(monitor_index)
    if mon is None:
        return False

    attempts = max(1, retries)
    for i in range(attempts):
        if _try_place_on_monitor(hwnd, mon, resize=resize):
            return True
        if i + 1 < attempts:
            time.sleep(max(0.0, delay_s))
    return False
