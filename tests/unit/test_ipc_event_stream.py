"""The one-way event stream from Process A/B to the overlay.

Process C is allowed to crash, but it must never take Process A with it, and a
publish must never block the game loop. Those are the properties tested here.
"""

from __future__ import annotations

import json
import socket
import threading

import pytest

from comstar_game_ai.shared.ipc.events import EventKind, IpcEvent
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.ipc.subscriber import EventSubscriber


@pytest.fixture
def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Collector:
    def __init__(self, expected: int = 1) -> None:
        self.events: list[IpcEvent] = []
        self._done = threading.Event()
        self._expected = expected

    def __call__(self, event: IpcEvent) -> None:
        self.events.append(event)
        if len(self.events) >= self._expected:
            self._done.set()

    def wait(self, timeout: float = 5.0) -> bool:
        return self._done.wait(timeout)


def test_event_round_trips_from_publisher_to_subscriber(free_port):
    collector = _Collector()
    subscriber = EventSubscriber(collector, host="127.0.0.1", port=free_port)
    subscriber.start()
    try:
        publisher = EventPublisher(host="127.0.0.1", port=free_port)
        publisher.publish(EventKind.CONTROL_STATE, {"state": "agent"})
        assert collector.wait(), "event never arrived"
    finally:
        subscriber.stop()

    (event,) = collector.events
    assert event.kind is EventKind.CONTROL_STATE
    assert event.payload == {"state": "agent"}


def test_many_events_arrive_in_order(free_port):
    collector = _Collector(expected=25)
    subscriber = EventSubscriber(collector, host="127.0.0.1", port=free_port)
    subscriber.start()
    try:
        publisher = EventPublisher(host="127.0.0.1", port=free_port)
        for index in range(25):
            publisher.publish(EventKind.KEY_DOWN, {"key": str(index)})
        assert collector.wait(), f"only {len(collector.events)} of 25 arrived"
    finally:
        subscriber.stop()

    assert [event.payload["key"] for event in collector.events] == [str(i) for i in range(25)]


def test_publishing_with_no_overlay_listening_is_silent(free_port):
    """The overlay is optional. Starting the game without it must not raise."""
    publisher = EventPublisher(host="127.0.0.1", port=free_port)
    for _ in range(3):
        publisher.publish(EventKind.FREEZE, {"reason": "deliberation"})


def test_a_malformed_line_does_not_stop_the_stream(free_port):
    """One bad frame used to kill the reader thread and silence the overlay."""
    collector = _Collector()
    subscriber = EventSubscriber(collector, host="127.0.0.1", port=free_port)
    subscriber.start()
    try:
        with socket.create_connection(("127.0.0.1", free_port), timeout=5) as sock:
            sock.sendall(b"not json at all\n")
            sock.sendall(b'{"kind": "no_such_kind", "payload": {}}\n')
            sock.sendall(b"\n")
            good = IpcEvent(kind=EventKind.RESUME, payload={"ok": True})
            sock.sendall((good.to_json() + "\n").encode("utf-8"))
            assert collector.wait(), "the good event after bad ones never arrived"
    finally:
        subscriber.stop()

    assert collector.events[0].kind is EventKind.RESUME


def test_a_throwing_handler_does_not_stop_the_stream(free_port):
    """A crash while drawing one surface must not deafen the overlay."""
    seen: list[IpcEvent] = []
    done = threading.Event()

    def handler(event: IpcEvent) -> None:
        seen.append(event)
        if len(seen) == 1:
            raise RuntimeError("surface blew up")
        done.set()

    subscriber = EventSubscriber(handler, host="127.0.0.1", port=free_port)
    subscriber.start()
    try:
        publisher = EventPublisher(host="127.0.0.1", port=free_port)
        publisher.publish(EventKind.FREEZE, {})
        publisher.publish(EventKind.RESUME, {})
        assert done.wait(5.0), "stream stopped after a handler raised"
    finally:
        subscriber.stop()

    assert len(seen) == 2


def test_every_event_kind_survives_a_json_round_trip():
    for kind in EventKind:
        line = IpcEvent(kind=kind, payload={"n": 1}, ts=1.5).to_json()
        assert json.loads(line)["kind"] == kind.value
        assert IpcEvent.from_json(line).kind is kind
