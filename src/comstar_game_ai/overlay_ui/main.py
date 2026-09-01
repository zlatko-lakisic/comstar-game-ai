"""Process C — four-surface operator overlay (PySide6)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind, IpcEvent
from comstar_game_ai.shared.ipc.subscriber import EventSubscriber
from comstar_game_ai.overlay_ui.surfaces import OverlaySurfaces


def run_overlay() -> int:
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("Rome window not found", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    surfaces = OverlaySurfaces(game.hwnd)

    def on_event(ev: IpcEvent) -> None:
        if ev.kind == EventKind.CONTROL_STATE:
            surfaces.state.set_state(ev.payload.get("state", "idle"))
        elif ev.kind == EventKind.KEY_DOWN:
            key = str(ev.payload.get("key") or ev.payload.get("action") or "")
            if key:
                surfaces.keyboard.flash_key(key)
        elif ev.kind == EventKind.KEY_UP:
            pass
        elif ev.kind == EventKind.POINTER_MOVED:
            o = ev.payload.get("origin")
            t = ev.payload.get("target")
            if isinstance(o, (list, tuple)) and isinstance(t, (list, tuple)):
                surfaces.leash.set_leash((int(o[0]), int(o[1])), (int(t[0]), int(t[1])))
        elif ev.kind in (EventKind.AO_REQUEST, EventKind.AO_STATUS, EventKind.AO_RESULT, EventKind.INTENT_DECLARED):
            summary = ev.payload.get("summary", str(ev.payload)[:80])
            surfaces.chat.append(f"{ev.kind.value}: {summary}")
        elif ev.kind == EventKind.VERIFICATION:
            surfaces.chat.append(f"verify: {ev.payload.get('summary', ev.payload)}")

    sub = EventSubscriber(on_event)
    sub.start()
    surfaces.show_all()
    code = app.exec()
    sub.stop()
    return code


def main(argv: list[str] | None = None) -> int:
    return run_overlay()


if __name__ == "__main__":
    raise SystemExit(main())
