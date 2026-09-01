"""Four overlay surfaces per mockup defaults."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import QLabel, QWidget


class SurfaceBase(QWidget):
    """Top-level click-through overlay surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def apply_win32_styles(self) -> None:
        try:
            from comstar_game_ai.overlay_ui.win32_styles import apply_overlay_styles

            apply_overlay_styles(int(self.winId()))
        except Exception:
            pass


class StateChipSurface(SurfaceBase):
    """Surface 1 — agent state chip (top-left)."""

    def __init__(self) -> None:
        super().__init__()
        self._label = QLabel("IDLE", self)
        self._label.setStyleSheet(
            "background: rgba(9,14,17,0.74); color: #5fd0e0; padding: 6px 10px;"
            "border: 1px solid rgba(120,200,215,0.26); border-radius: 3px;"
        )
        self._label.setFont(QFont("Consolas", 9))
        self._label.adjustSize()
        self.resize(self._label.size())

    def set_state(self, state: str) -> None:
        self._label.setText(state.upper())
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

    KEYS = ["1", "2", "3", "4", "5", "6", "Ctrl", "Alt", "Shift", "Space"]

    def __init__(self) -> None:
        super().__init__()
        self._held: set[str] = set()
        self._flash: dict[str, int] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay_flash)
        self._timer.start(80)
        self.setFixedSize(220, 36)

    def set_held(self, keys: set[str]) -> None:
        self._held = {k.lower() for k in keys}
        self.update()

    def flash_key(self, key: str) -> None:
        self._flash[key.lower()] = 6
        self.update()

    def _decay_flash(self) -> None:
        if not self._flash:
            return
        expired = [k for k, v in self._flash.items() if v <= 1]
        for k in expired:
            del self._flash[k]
        for k in list(self._flash):
            self._flash[k] -= 1
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
    """Surface 4 — dashed leash + ghost marker before travel."""

    def __init__(self) -> None:
        super().__init__()
        self._origin: tuple[int, int] | None = None
        self._target: tuple[int, int] | None = None
        self.setFixedSize(800, 600)

    def set_leash(self, origin: tuple[int, int] | None, target: tuple[int, int] | None) -> None:
        self._origin = origin
        self._target = target
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._origin or not self._target:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(95, 208, 224, 140))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(2)
        painter.setPen(pen)
        ox, oy = self._origin
        tx, ty = self._target
        painter.drawLine(ox, oy, tx, ty)
        painter.setBrush(QColor(95, 208, 224, 80))
        painter.drawEllipse(tx - 6, ty - 6, 12, 12)


class OverlaySurfaces:
    """Manage four top-level overlay windows synced to game geometry."""

    def __init__(self, game_hwnd: int) -> None:
        self.game_hwnd = game_hwnd
        self.state = StateChipSurface()
        self.chat = ChatPanelSurface()
        self.keyboard = KeyboardSurface()
        self.leash = CursorLeashSurface()
        self._surfaces = [self.state, self.chat, self.keyboard, self.leash]
        for s in self._surfaces:
            s.apply_win32_styles()
        self._timer = QTimer()
        self._timer.timeout.connect(self._sync_geometry)
        self._timer.start(400)

    def show_all(self) -> None:
        self._sync_geometry()
        for s in self._surfaces:
            s.show()

    def hide_all(self) -> None:
        for s in self._surfaces:
            s.hide()

    def _sync_geometry(self) -> None:
        try:
            import win32gui

            left, top, right, bottom = win32gui.GetWindowRect(self.game_hwnd)
            w, h = right - left, bottom - top
            self.state.move(left + 12, top + 12)
            self.chat.move(left + w - 330, top + 12)
            self.keyboard.move(left + 12, top + h - 48)
            self.leash.setGeometry(left, top, w, h)
        except Exception:
            pass
