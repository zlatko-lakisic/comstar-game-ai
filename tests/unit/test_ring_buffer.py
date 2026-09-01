import time

from comstar_game_ai.game_io.capture.ring_buffer import RingBuffer


def test_ring_evicts_old_frames():
    ring = RingBuffer(max_seconds=1.0)
    now = time.monotonic()
    ring.push(b"a", 1, 1, ts=now - 2)
    ring.push(b"b", 1, 1, ts=now)
    assert len(ring) == 1
    assert ring.latest().data == b"b"


def test_select_before():
    ring = RingBuffer(max_seconds=10.0)
    base = 1000.0
    ring.push(b"1", 1, 1, ts=base)
    ring.push(b"2", 1, 1, ts=base + 1)
    ring.push(b"3", 1, 1, ts=base + 2)
    picked = ring.select_before(base + 1.5, count=2)
    assert [f.data for f in picked] == [b"2", b"1"]
