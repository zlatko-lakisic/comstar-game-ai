"""Four overlay surfaces per mockup defaults."""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import QLabel, QWidget

from comstar_game_ai.overlay_ui.state import (
    TEST_PATTERN_RGB,
    SurfaceState,
    coerce_state,
    state_colour,
    state_label,
)


class SurfaceBase(QWidget):
    """Top-level click-through overlay surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def apply_win32_styles(self):
        """Apply click-through / non-activating / capture-excluded styles.

        Returns the StyleReport, or None if styling could not run at all, so the
        self tests can tell a failed exclusion from a missing platform.
        """
        try:
            from comstar_game_ai.overlay_ui.win32_styles import apply_overlay_styles

            return apply_overlay_styles(int(self.winId()))
        except Exception:
            return None


class EdgeGlowSurface(SurfaceBase):
    """Surface 1a — window-sized border glow whose colour encodes the state.

    Covers the whole client area, so it is the surface most likely to expose a
    click-through regression; it paints a stroke and corner brackets only, never
    a fill, except in test-pattern mode.
    """

    BORDER_WIDTH = 6
    BRACKET_LENGTH = 48

    def __init__(self, *, test_pattern: bool = False) -> None:
        super().__init__()
        self._state = SurfaceState.IDLE
        self._test_pattern = test_pattern

    def set_state(self, state: object) -> None:
        new_state = coerce_state(state)
        if new_state is not self._state:
            self._state = new_state
            self.update()

    @property
    def state(self) -> SurfaceState:
        return self._state

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()

        if self._test_pattern:
            # Opaque, unmistakable, and covering the frame the game is captured
            # from: if capture exclusion is broken this cannot be missed.
            painter.fillRect(0, 0, width, height, QColor(*TEST_PATTERN_RGB))
            return

        red, green, blue = state_colour(self._state)
        inset = self.BORDER_WIDTH / 2

        pen = QPen(QColor(red, green, blue, 90))
        pen.setWidth(self.BORDER_WIDTH)
        painter.setPen(pen)
        painter.drawRect(int(inset), int(inset), int(width - inset * 2), int(height - inset * 2))

        # Brighter corner brackets read as deliberate framing rather than a
        # rendering artefact at a glance.
        bracket = QPen(QColor(red, green, blue, 210))
        bracket.setWidth(self.BORDER_WIDTH)
        painter.setPen(bracket)
        span = self.BRACKET_LENGTH
        for x_edge, x_dir in ((inset, 1), (width - inset, -1)):
            for y_edge, y_dir in ((inset, 1), (height - inset, -1)):
                painter.drawLine(int(x_edge), int(y_edge), int(x_edge + span * x_dir), int(y_edge))
                painter.drawLine(int(x_edge), int(y_edge), int(x_edge), int(y_edge + span * y_dir))


class StateChipSurface(SurfaceBase):
    """Surface 1b — agent state chip (top-left)."""

    def __init__(self) -> None:
        super().__init__()
        self._state = SurfaceState.IDLE
        self._label = QLabel(state_label(self._state), self)
        self._label.setFont(QFont("Consolas", 9))
        self._restyle()

    def set_state(self, state: object) -> None:
        self._state = coerce_state(state)
        self._label.setText(state_label(self._state))
        self._restyle()

    @property
    def state(self) -> SurfaceState:
        return self._state

    def _restyle(self) -> None:
        red, green, blue = state_colour(self._state)
        self._label.setStyleSheet(
            "background: rgba(9,14,17,0.74); padding: 6px 10px; border-radius: 3px;"
            f"color: rgb({red},{green},{blue});"
            f"border: 1px solid rgba({red},{green},{blue},0.42);"
        )
        self._label.adjustSize()
        self.resize(self._label.size())


class ChatPanelSurface(SurfaceBase):
    """Surface 2 — AO chat scrollback (top-right)."""

    def __init__(self, *, max_lines: int = 10) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._label = QLabel("", self)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            "background: rgba(9,14,17,0.74); color: #e6ecef; padding: 8px;"
            "border: 1px solid rgba(120,200,215,0.18); max-width: 310px;"
        )
        self._label.setFont(QFont("Consolas", 8))
        self.setFixedWidth(320)

    def append(self, line: str) -> None:
        self._lines.append(line[:120])
        self._label.setText("\n".join(self._lines))
        self._label.adjustSize()
        self.resize(max(320, self._label.width()), self._label.height())

    def set_directive_summary(self, summary: str) -> None:
        if summary:
            self.append(f"directive: {summary[:80]}")


class KeyboardSurface(SurfaceBase):
    """Surface 3 — compact keyboard bottom-left; modifiers lit, taps flash."""

    # Only the keys the agent actually presses: control groups, modifiers, and the
    # two the campaign driver leans on. A full keyboard would be noise.
    KEYS = ["1", "2", "3", "4", "5", "6", "Ctrl", "Alt", "Shift", "Space", "Esc"]

    IDLE_FADE_AFTER_S = 2.5
    IDLE_OPACITY = 0.16
    ACTIVE_OPACITY = 1.0

    def __init__(self) -> None:
        super().__init__()
        self._held: set[str] = set()
        self._flash: dict[str, int] = {}
        self._last_activity = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)
        self.setFixedSize(len(self.KEYS) * 22 + 8, 36)
        self.setWindowOpacity(self.IDLE_OPACITY)

    def set_held(self, keys: set[str]) -> None:
        self._held = {key.lower() for key in keys}
        self._mark_activity()
        self.update()

    def flash_key(self, key: str) -> None:
        self._flash[key.lower()] = 6
        self._mark_activity()
        self.update()

    def _mark_activity(self) -> None:
        self._last_activity = time.monotonic()
        self.setWindowOpacity(self.ACTIVE_OPACITY)

    def _tick(self) -> None:
        # Fade out once nothing has been pressed for a beat; held modifiers keep
        # the surface lit because a stuck modifier is exactly what you need to see.
        if not self._held and time.monotonic() - self._last_activity > self.IDLE_FADE_AFTER_S:
            if self.windowOpacity() > self.IDLE_OPACITY:
                self.setWindowOpacity(max(self.IDLE_OPACITY, self.windowOpacity() - 0.08))
        if not self._flash:
            return
        for key in [key for key, ticks in self._flash.items() if ticks <= 1]:
            del self._flash[key]
        for key in list(self._flash):
            self._flash[key] -= 1
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 4
        for key in self.KEYS:
            kl = key.lower()
            held = kl in self._held or key.lower() in self._held
            flash = kl in self._flash
            if held or flash:
                painter.fillRect(x, 4, 18, 28, QColor(95, 208, 224, 180 if held else 100))
                painter.setPen(QColor(9, 14, 17))
            else:
                painter.fillRect(x, 4, 18, 28, QColor(9, 14, 17, 190))
                painter.setPen(QColor(95, 208, 224, 180))
            painter.drawRect(x, 4, 18, 28)
            painter.drawText(x + 2, 22, key[:1] if len(key) == 1 else key[:3])
            x += 22


class CursorLeashSurface(SurfaceBase):
    """Surface 3 — cursor ring and trail, plus a dashed leash to the destination.

    The leash is drawn *before* the cursor travels, so an operator can see where
    a click is about to land while there is still time to hit the kill switch.
    Synthetic and human motion are different colours because the whole point of
    watching this surface is knowing which one is moving the mouse.
    """

    SYNTHETIC_RGB = (0x5F, 0xD0, 0xE0)
    HUMAN_RGB = (0x8D, 0x9A, 0xA2)
    RING_RADIUS = 13
    TRAIL_LENGTH = 12

    def __init__(self) -> None:
        super().__init__()
        self._origin: tuple[int, int] | None = None
        self._target: tuple[int, int] | None = None
        self._trail: deque[tuple[int, int]] = deque(maxlen=self.TRAIL_LENGTH)
        self._synthetic = True

    def set_leash(self, origin: tuple[int, int] | None, target: tuple[int, int] | None) -> None:
        self._origin = origin
        self._target = target
        self.update()

    def clear_leash(self) -> None:
        self._origin = None
        self._target = None
        self.update()

    def set_pointer(self, point: tuple[int, int], *, synthetic: bool = True) -> None:
        self._synthetic = synthetic
        self._trail.append(point)
        self.update()

    @property
    def pointer(self) -> tuple[int, int] | None:
        return self._trail[-1] if self._trail else None

    def _rgb(self) -> tuple[int, int, int]:
        return self.SYNTHETIC_RGB if self._synthetic else self.HUMAN_RGB

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        red, green, blue = self._rgb()

        if self._origin and self._target:
            leash = QPen(QColor(red, green, blue, 150))
            leash.setStyle(Qt.PenStyle.DashLine)
            leash.setWidth(2)
            painter.setPen(leash)
            painter.drawLine(*self._origin, *self._target)
            # Hollow marker: the destination is a proposal, not a click yet.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(red, green, blue, 210), 2))
            target_x, target_y = self._target
            painter.drawEllipse(target_x - 9, target_y - 9, 18, 18)

        trail = list(self._trail)
        for index, (x, y) in enumerate(trail[:-1]):
            fade = int(20 + 90 * (index + 1) / max(len(trail), 1))
            painter.setPen(QPen(QColor(red, green, blue, fade), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(x - 2, y - 2, 4, 4)

        if trail:
            x, y = trail[-1]
            painter.setPen(QPen(QColor(red, green, blue, 230), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = self.RING_RADIUS
            painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)


class OverlaySurfaces:
    """Manage the overlay's top-level windows, synced to the game's client area."""

    def __init__(self, game_hwnd: int, *, test_pattern: bool = False, sync_ms: int = 400) -> None:
        self.game_hwnd = game_hwnd
        self.glow = EdgeGlowSurface(test_pattern=test_pattern)
        self.state = StateChipSurface()
        self.chat = ChatPanelSurface()
        self.keyboard = KeyboardSurface()
        self.leash = CursorLeashSurface()
        # Glow first so it paints beneath the readable surfaces.
        self._surfaces = [self.glow, self.state, self.chat, self.keyboard, self.leash]
        self.style_reports = [surface.apply_win32_styles() for surface in self._surfaces]
        self._timer = QTimer()
        self._timer.timeout.connect(self._sync_geometry)
        self._timer.start(sync_ms)

    @property
    def surfaces(self) -> list[SurfaceBase]:
        return list(self._surfaces)

    def hwnds(self) -> list[int]:
        """Every overlay window handle — what the click-through check must not hit."""
        return [int(surface.winId()) for surface in self._surfaces]

    def set_state(self, state: object) -> None:
        """State drives the glow and the chip together; they must never disagree."""
        self.glow.set_state(state)
        self.state.set_state(state)

    def show_all(self) -> None:
        self._sync_geometry()
        for surface in self._surfaces:
            surface.show()

    def hide_all(self) -> None:
        for surface in self._surfaces:
            surface.hide()

    def close_all(self) -> None:
        self._timer.stop()
        for surface in self._surfaces:
            surface.close()

    def game_rect(self) -> tuple[int, int, int, int] | None:
        """Client area in screen coords, matching the frame vision works from.

        Aligning to the window rect instead would frame the title bar and shift
        every surface against the coordinates Process A derives from a capture.
        """
        try:
            from comstar_game_ai.game_io.capture.window_capture import client_screen_rect

            rect = client_screen_rect(self.game_hwnd)
            if rect is not None:
                return rect
            import win32gui

            return win32gui.GetWindowRect(self.game_hwnd)
        except Exception:
            return None

    def _sync_geometry(self) -> None:
        rect = self.game_rect()
        if rect is None:
            return
        left, top, right, bottom = rect
        width, height = right - left, bottom - top
        self.glow.setGeometry(left, top, width, height)
        self.state.move(left + 20, top + 20)
        self.chat.move(left + width - 340, top + 20)
        self.keyboard.move(left + 20, top + height - 56)
        self.leash.setGeometry(left, top, width, height)
