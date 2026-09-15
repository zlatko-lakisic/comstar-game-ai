"""Ada yield lock — Process A holds, director waits for release."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from comstar_game_ai.shared.runtime import ada_yield


def test_ada_yield_acquire_release(tmp_path: Path, monkeypatch):
    lock = tmp_path / "ada_yield.lock"
    monkeypatch.setattr(ada_yield, "DEFAULT_LOCK_PATH", lock)
    assert not ada_yield.is_held()
    with ada_yield.held(holder="test", reason="unit"):
        assert ada_yield.is_held()
        payload = lock.read_text(encoding="utf-8")
        assert "test" in payload
    assert not ada_yield.is_held()


def test_wait_until_released(tmp_path: Path, monkeypatch):
    lock = tmp_path / "ada_yield.lock"
    monkeypatch.setattr(ada_yield, "DEFAULT_LOCK_PATH", lock)
    ada_yield.acquire(holder="test", reason="unit")

    def _release_soon() -> None:
        time.sleep(0.15)
        ada_yield.release(holder="test")

    threading.Thread(target=_release_soon, daemon=True).start()
    assert ada_yield.wait_until_released(timeout_s=2.0, poll_s=0.05)
    assert not ada_yield.is_held()


def test_wait_until_released_times_out(tmp_path: Path, monkeypatch):
    lock = tmp_path / "ada_yield.lock"
    monkeypatch.setattr(ada_yield, "DEFAULT_LOCK_PATH", lock)
    ada_yield.acquire(holder="test", reason="unit")
    assert not ada_yield.wait_until_released(timeout_s=0.2, poll_s=0.05)
    ada_yield.release(holder="test")


def test_parse_map_target_found_and_miss():
    from comstar_game_ai.game_io.campaign.map_target_vision import parse_map_target_result

    hit = parse_map_target_result(
        '{"found":true,"label":"Segesta","region":"Liguria","colour":"green",'
        '"confidence":0.8,"standing":"at_war","reason":"plaque"}',
        expected_label="Segesta",
    )
    assert hit is not None and hit.found
    assert hit.click_norm is None
    assert hit.colour == "green"
    # Stale coordinate fields must not become click points.
    stale = parse_map_target_result(
        '{"found":true,"label":"Segesta","x_norm":0.24,"y_norm":0.5,'
        '"confidence":0.8,"reason":"nameplate"}',
        expected_label="Segesta",
    )
    assert stale is not None and stale.found and stale.click_norm is None

    miss = parse_map_target_result(
        '{"found":false,"label":"Segesta","confidence":0,"reason":"gone"}',
        expected_label="Segesta",
    )
    assert miss is not None and not miss.found
