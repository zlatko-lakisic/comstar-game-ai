"""Win32 window discovery for Rome Remastered."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

if sys.platform == "win32":
    import win32gui
    import win32process
else:
    win32gui = None  # type: ignore[assignment]
    win32process = None  # type: ignore[assignment]


@dataclass
class GameWindow:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]


def _match_title(title: str, substrings: list[str]) -> bool:
    lower = title.lower()
    return any(s.lower() in lower for s in substrings)


def find_game_window(title_substrings: list[str]) -> GameWindow | None:
    if win32gui is None:
        return None
    found: GameWindow | None = None

    def enum_handler(hwnd: int, _: int) -> None:
        nonlocal found
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or not _match_title(title, title_substrings):
            return
        rect = win32gui.GetWindowRect(hwnd)
        found = GameWindow(hwnd=hwnd, title=title, rect=rect)

    win32gui.EnumWindows(enum_handler, 0)
    return found


def get_foreground_hwnd() -> int | None:
    if win32gui is None:
        return None
    return win32gui.GetForegroundWindow()


def process_elevation_matches(other_pid: int) -> bool:
    """Return True if current process and other_pid share elevation (best-effort)."""
    if sys.platform != "win32":
        return True
    import ctypes

    shell32 = ctypes.windll.shell32
    IsUserAnAdmin = shell32.IsUserAnAdmin
    we_admin = bool(IsUserAnAdmin())
    try:
        import win32api
        import win32con
        import win32security

        h_proc = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, other_pid)
        token = win32security.OpenProcessToken(h_proc, win32con.TOKEN_QUERY)
        elevation = win32security.GetTokenInformation(token, win32security.TokenElevation)
        they_admin = bool(elevation)
        return we_admin == they_admin
    except Exception:
        return True
