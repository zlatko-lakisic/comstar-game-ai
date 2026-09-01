"""IPC event subscriber for Process C overlay."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable

from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import IpcEvent


class EventSubscriber:
    def __init__(
        self,
        on_event: Callable[[IpcEvent], None],
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        cfg = load_config()
        ipc = cfg.get("ipc") or {}
        self.host = host or ipc.get("event_socket_host", "127.0.0.1")
        self.port = int(port or ipc.get("event_socket_port", 9876))
        self.on_event = on_event
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                self._server.settimeout(1.0)
                conn, _ = self._server.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except TimeoutError:
                continue
            except OSError:
                break

    def _handle(self, conn: socket.socket) -> None:
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self.on_event(IpcEvent.from_json(line.decode("utf-8")))
        finally:
            conn.close()

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.close()
