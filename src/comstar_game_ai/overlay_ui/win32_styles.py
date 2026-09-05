"""Win32 extended styles for overlay windows, and the queries that verify them."""

from __future__ import annotations

import sys
from dataclasses import dataclass

if sys.platform == "win32":
    from ctypes import windll, wintypes

    import win32con
    import win32gui
else:  # pragma: no cover - the overlay only runs on Windows
    windll = None  # type: ignore[assignment]
    win32con = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

#: WS_EX_TRANSPARENT gives click-through, WS_EX_NOACTIVATE stops the overlay taking
#: focus from the game, WS_EX_TOOLWINDOW keeps it out of alt-tab, and WS_EX_LAYERED
#: is what makes a translucent, click-through window composite correctly.
OVERLAY_EX_STYLES = (
    WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
)


@dataclass(frozen=True)
class StyleReport:
    """Outcome of styling one surface. Never raises: the overlay is optional."""

    hwnd: int
    styles_ok: bool
    capture_excluded: bool
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.styles_ok and self.capture_excluded


def _set_display_affinity(hwnd: int, affinity: int) -> bool:
    fn = windll.user32.SetWindowDisplayAffinity
    fn.argtypes = [wintypes.HWND, wintypes.DWORD]
    fn.restype = wintypes.BOOL
    return bool(fn(wintypes.HWND(hwnd), wintypes.DWORD(affinity)))


def apply_overlay_styles(hwnd: int) -> StyleReport:
    """Make `hwnd` click-through, non-activating and invisible to capture.

    Returns a report rather than swallowing failures: a silent
    SetWindowDisplayAffinity failure means the overlay is being fed to the vision
    model, which corrupts every frame the agent reasons about.
    """
    if sys.platform != "win32":
        return StyleReport(hwnd, False, False, "not Windows")

    try:
        existing = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, existing | OVERLAY_EX_STYLES)
        applied = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        styles_ok = applied & OVERLAY_EX_STYLES == OVERLAY_EX_STYLES
    except Exception as exc:  # pragma: no cover - needs a real hwnd
        return StyleReport(hwnd, False, False, f"style call failed: {exc}")

    try:
        excluded = _set_display_affinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception as exc:  # pragma: no cover - needs a real hwnd
        return StyleReport(hwnd, styles_ok, False, f"display affinity call failed: {exc}")

    detail = "" if styles_ok and excluded else "requires Windows 10 2004 (build 19041) or later"
    return StyleReport(hwnd, styles_ok, excluded, detail)


def missing_styles(hwnd: int) -> int:
    """Bitmask of the required extended styles that `hwnd` does not have."""
    if sys.platform != "win32":
        return OVERLAY_EX_STYLES
    return OVERLAY_EX_STYLES & ~win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)


def describe_styles(missing: int) -> str:
    names = {
        WS_EX_LAYERED: "WS_EX_LAYERED",
        WS_EX_TRANSPARENT: "WS_EX_TRANSPARENT",
        WS_EX_NOACTIVATE: "WS_EX_NOACTIVATE",
        WS_EX_TOPMOST: "WS_EX_TOPMOST",
        WS_EX_TOOLWINDOW: "WS_EX_TOOLWINDOW",
    }
    return ", ".join(name for bit, name in names.items() if missing & bit) or "none"


def window_from_point(x: int, y: int) -> int:
    """The window the OS says owns a screen point.

    This is the click-through oracle: WindowFromPoint skips WS_EX_TRANSPARENT
    windows, so if it ever names an overlay surface, clicks are being swallowed.
    """
    if sys.platform != "win32":
        return 0
    try:
        return int(win32gui.WindowFromPoint((int(x), int(y))))
    except Exception:
        return 0


def foreground_window() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(win32gui.GetForegroundWindow())
    except Exception:
        return 0


def root_owner(hwnd: int) -> int:
    """Top-level ancestor of `hwnd`, so a hit on a game child still reads as the game."""
    if sys.platform != "win32" or not hwnd:
        return 0
    try:
        GA_ROOT = 2
        return int(windll.user32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT))
    except Exception:
        return hwnd
