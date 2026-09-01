"""One-way IPC event publisher (Process A/B -> Process C)."""

from __future__ import annotations

import socket
import time
from typing import Any

from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind, IpcEvent


class EventPublisher:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        cfg = load_config()
        ipc = cfg.get("ipc") or {}
        self.host = host or ipc.get("event_socket_host", "127.0.0.1")
        self.port = int(port or ipc.get("event_socket_port", 9876))
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        if self._sock is not None:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((self.host, self.port))
        self._sock = s

    def publish(self, kind: EventKind, payload: dict[str, Any] | None = None) -> None:
        try:
            self.connect()
            ev = IpcEvent(kind=kind, payload=payload or {}, ts=time.time())
            assert self._sock is not None
            self._sock.sendall((ev.to_json() + "\n").encode("utf-8"))
        except OSError:
            self._sock = None

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None
