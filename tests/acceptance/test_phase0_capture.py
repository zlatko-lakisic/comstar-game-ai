"""Acceptance tests — skip gracefully when Rome is not running."""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.self_tests import run_self_tests
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


pytestmark = pytest.mark.requires_game


@pytest.fixture
def game_window():
    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    w = find_game_window(subs)
    if w is None:
        pytest.skip("Rome Remastered not running")
    return w


def test_phase0_self_tests(game_window):
    result = run_self_tests(require_game=True)
    assert result.tests.get("preconditions", False)
    assert result.tests.get("game_window", False)


def test_phase0_capture_ring(game_window):
    from comstar_game_ai.game_io.capture.capture_loop import CaptureLoop

    loop = CaptureLoop(game_window.hwnd)
    loop.start()
    import time

    time.sleep(0.5)
    loop.stop()
    assert len(loop.ring) >= 1
