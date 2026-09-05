"""Process C — the operator overlay (PySide6).

Observes a one-way event stream from Process A and B and draws only. It is
allowed to crash: nothing here may block or kill the game I/O process.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.overlay_ui.router import EventRouter, OverlayUpdate
from comstar_game_ai.overlay_ui.surfaces import OverlaySurfaces
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import IpcEvent
from comstar_game_ai.shared.ipc.subscriber import EventSubscriber


class _EventBridge(QObject):
    """Hop events from the subscriber's socket thread onto the Qt thread.

    Touching widgets from the socket thread is undefined behaviour in Qt and
    crashes the overlay under load, which is exactly when it is being watched.
    """

    received = Signal(object)


def apply_update(surfaces: OverlaySurfaces, update: OverlayUpdate) -> None:
    if update.state is not None:
        surfaces.set_state(update.state)
    if update.flash_key:
        surfaces.keyboard.flash_key(update.flash_key)
    if update.held_keys is not None:
        surfaces.keyboard.set_held(set(update.held_keys))
    if update.pointer is not None:
        surfaces.leash.set_pointer(
            _to_client(surfaces, update.pointer), synthetic=update.pointer_synthetic
        )
    if update.leash is not None:
        origin, target = update.leash
        surfaces.leash.set_leash(_to_client(surfaces, origin), _to_client(surfaces, target))
    elif update.clear_leash:
        surfaces.leash.clear_leash()
    if update.chat_line:
        surfaces.chat.append(update.chat_line)


def _to_client(surfaces: OverlaySurfaces, point: tuple[int, int]) -> tuple[int, int]:
    """Screen coords to leash-surface coords.

    Process A works in screen coordinates because that is what SendInput takes;
    the leash surface is positioned over the client area, so points have to be
    rebased or every marker lands offset by the window origin.
    """
    rect = surfaces.game_rect()
    if rect is None:
        return point
    return (point[0] - rect[0], point[1] - rect[1])


def run_overlay(*, test_pattern: bool = False) -> int:
    config = load_config()
    substrings = config.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(substrings)
    if game is None:
        print("game window not found — start the game, then start the overlay", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    surfaces = OverlaySurfaces(game.hwnd, test_pattern=test_pattern)
    router = EventRouter()
    bridge = _EventBridge()

    def on_qt_thread(event: IpcEvent) -> None:
        try:
            apply_update(surfaces, router.route(event.kind, event.payload))
        except Exception as exc:  # the overlay is cosmetic; never die on one event
            print(f"overlay: dropped event {event.kind}: {exc}", file=sys.stderr)

    bridge.received.connect(on_qt_thread, Qt.ConnectionType.QueuedConnection)

    subscriber = EventSubscriber(bridge.received.emit)
    try:
        subscriber.start()
    except OSError as exc:
        print(f"overlay: cannot listen for events ({exc}) — is another overlay running?", file=sys.stderr)
        return 1
    surfaces.show_all()
    try:
        return app.exec()
    finally:
        subscriber.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comstar-overlay", description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the Phase 3 acceptance checks against the full overlay and exit",
    )
    parser.add_argument(
        "--test-pattern",
        action="store_true",
        help="fill the client area with the capture-exclusion test pattern",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        from comstar_game_ai.overlay_ui.live_checks import run_overlay_self_tests

        report = run_overlay_self_tests()
        print(report.render())
        return 0 if report.ok else 1

    return run_overlay(test_pattern=args.test_pattern)


if __name__ == "__main__":
    raise SystemExit(main())
