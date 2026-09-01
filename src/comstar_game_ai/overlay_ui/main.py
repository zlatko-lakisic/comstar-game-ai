"""Process C — operator overlay (PySide6)."""

from __future__ import annotations

import sys
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind, IpcEvent
from comstar_game_ai.shared.ipc.subscriber import EventSubscriber


class OverlayWindow(QWidget):
    def __init__(self, game_hwnd: int) -> None:
        super().__init__()
        self.game_hwnd = game_hwnd
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._state = "idle"
        self._chat: deque[str] = deque(maxlen=10)

        layout = QVBoxLayout(self)
        self.state_chip = QLabel("IDLE")
        self.state_chip.setStyleSheet(
            "background: rgba(9,14,17,0.74); color: #5fd0e0; padding: 6px; border: 1px solid rgba(120,200,215,0.26);"
        )
        self.state_chip.setFont(QFont("Consolas", 9))
        layout.addWidget(self.state_chip)

        self.chat_panel = QLabel("")
        self.chat_panel.setWordWrap(True)
        self.chat_panel.setStyleSheet(
            "background: rgba(9,14,17,0.74); color: #e6ecef; padding: 8px; max-width: 310px;"
        )
        self.chat_panel.setFont(QFont("Consolas", 8))
        layout.addWidget(self.chat_panel, alignment=Qt.AlignRight)

        self.kbd_hint = QLabel("Keys: 1-6 Ctrl Alt Shift Space")
        self.kbd_hint.setStyleSheet("color: rgba(95,208,224,0.7); font-size: 10px;")
        layout.addWidget(self.kbd_hint, alignment=Qt.AlignLeft | Qt.AlignBottom)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sync_geometry)
        self._timer.start(500)

        try:
            from comstar_game_ai.overlay_ui.win32_styles import apply_overlay_styles

            apply_overlay_styles(int(self.winId()))
        except Exception:
            pass

    def _sync_geometry(self) -> None:
        try:
            import win32gui

            rect = win32gui.GetWindowRect(self.game_hwnd)
            self.setGeometry(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        except Exception:
            pass

    def on_event(self, ev: IpcEvent) -> None:
        if ev.kind == EventKind.CONTROL_STATE:
            self._state = ev.payload.get("state", "idle")
            self.state_chip.setText(self._state.upper())
        elif ev.kind in (EventKind.AO_REQUEST, EventKind.AO_STATUS, EventKind.AO_RESULT, EventKind.INTENT_DECLARED):
            line = f"{ev.kind.value}: {ev.payload.get('summary', ev.payload)}"
            self._chat.append(line[:120])
            self.chat_panel.setText("\n".join(self._chat))

    def set_state(self, state: str) -> None:
        self._state = state
        self.state_chip.setText(state.upper())


def run_overlay() -> int:
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("Rome window not found", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    win = OverlayWindow(game.hwnd)

    def on_ev(ev: IpcEvent) -> None:
        win.on_event(ev)

    sub = EventSubscriber(on_ev)
    sub.start()
    win.show()
    code = app.exec()
    sub.stop()
    return code


def main(argv: list[str] | None = None) -> int:
    return run_overlay()


if __name__ == "__main__":
    raise SystemExit(main())
