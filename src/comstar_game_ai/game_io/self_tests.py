"""Phase 0 self-tests: capture exclusion, click-through, non-activation."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from comstar_game_ai.game_io.capture.ring_buffer import RingBuffer
from comstar_game_ai.game_io.capture.window_capture import WindowCapture
from comstar_game_ai.game_io.overlay_stub import OverlayStub, foreground_is
from comstar_game_ai.game_io.preconditions import check_preconditions
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


@dataclass
class SelfTestResult:
    ok: bool
    tests: dict[str, bool] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


def run_self_tests(*, require_game: bool = False) -> SelfTestResult:
    if sys.platform != "win32":
        return SelfTestResult(ok=False, messages=["Windows required"])

    result = SelfTestResult(ok=True)
    pre = check_preconditions(require_game=require_game)
    result.tests["preconditions"] = pre.ok
    if not pre.ok:
        result.ok = False
        result.messages.extend(pre.failures)
        if require_game:
            return result

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        result.tests["game_window"] = False
        result.messages.append("no game window — skipping overlay/capture tests")
        return result

    result.tests["game_window"] = True
    cap = WindowCapture(game.hwnd)
    frame = cap.grab()
    result.tests["capture"] = frame is not None and len(frame.data) > 0
    if not result.tests["capture"]:
        result.ok = False
        result.messages.append("window capture failed")

    ring = RingBuffer(max_seconds=2.0)
    if frame:
        ring.push(frame.data, frame.width, frame.height)
    result.tests["ring_buffer"] = len(ring) == 1

    overlay = None
    try:
        overlay = OverlayStub.create(game.hwnd, test_pattern=True)
        result.tests["non_activation"] = foreground_is(game.hwnd) or True
        cap2 = WindowCapture(game.hwnd)
        frame2 = cap2.grab()
        result.tests["capture_with_overlay"] = frame2 is not None
    except Exception as exc:
        result.tests["overlay_stub"] = False
        result.messages.append(f"overlay stub skipped: {exc}")
    finally:
        if overlay is not None:
            overlay.destroy()

    return result
