"""Feed the overlay a scripted event stream, so it can be seen without the agent.

Process C draws only what Process A and B publish. Started on its own it sits on
IDLE with an empty chat panel, which looks identical to an overlay that is broken.
This walks it through every surface it owns: the edge glow's state colours, the
state chip, key flashes and held modifiers, the cursor leash, and the chat panel —
including a failed verification, which is the one event that colours the whole frame.

    python -m comstar_game_ai.overlay_ui.main     # window one: the overlay
    python scripts/demo_overlay.py                # window two: this

Nothing here touches the game. The events are fabricated, the pointer coordinates
are derived from the game window's own rect, and no input is injected.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind
from comstar_game_ai.shared.ipc.publisher import EventPublisher


def _window_points() -> tuple[tuple[int, int], tuple[int, int]]:
    """Two points inside the game client, for the leash to run between.

    Falls back to a 1920x1080 window at the origin when no game is found: the
    overlay would not be attached either, and the demo is still worth watching
    against whatever window it did attach to.
    """
    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings") or ["Rome"])
    if game is None:
        left, top, width, height = 0, 0, 1920, 1080
    else:
        left, top = game.rect[0], game.rect[1]
        width, height = game.width, game.height
    origin = (left + int(width * 0.45), top + int(height * 0.45))
    target = (left + int(width * 0.26), top + int(height * 0.38))
    return origin, target


def _script(origin: tuple[int, int], target: tuple[int, int]) -> list[tuple[str, EventKind, dict]]:
    """The demo beat sheet, in the order an operator would see it during a turn."""
    return [
        ("agent takes control", EventKind.CONTROL_STATE, {"state": "acting"}),
        (
            "asks AO for a decision (frame turns to DELIBERATING)",
            EventKind.AO_REQUEST,
            {"summary": "campaign turn 12: Segesta or hold?", "question_id": "demo-1"},
        ),
        ("AO queues the request", EventKind.AO_STATUS, {"phase": "queued", "queue_position": 2}),
        ("AO answers", EventKind.AO_STATUS, {"phase": "generating", "latency_ms": 840}),
        ("directive lands", EventKind.AO_RESULT, {"summary": "take_settlement"}),
        (
            "intent declared, leash drawn to the target",
            EventKind.INTENT_DECLARED,
            {"summary": "attack Segesta with the full stack", "origin": origin, "target": target},
        ),
        ("ctrl held for a control group", EventKind.KEY_DOWN, {"key": "ctrl"}),
        ("5 pressed — Lists opens", EventKind.KEY_DOWN, {"key": "5"}),
        ("ctrl released", EventKind.KEY_UP, {"key": "ctrl"}),
        ("cursor moved onto the target", EventKind.POINTER_MOVED, {"point": target, "synthetic": True}),
        ("verification passes, leash clears", EventKind.VERIFICATION, {"ok": True, "summary": "stack of 8 selected"}),
        ("game frozen to think", EventKind.FREEZE, {}),
        ("resumed", EventKind.RESUME, {}),
        (
            "a verification fails — the whole frame goes FAULT",
            EventKind.VERIFICATION,
            {"ok": False, "summary": "attack order did not register"},
        ),
        ("human grabs the mouse, agent suspends", EventKind.AGENT_SUSPENDED, {}),
        ("agent resumes", EventKind.AGENT_RESUMED, {}),
        ("back to idle", EventKind.CONTROL_STATE, {"state": "idle"}),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step-s", type=float, default=1.8, help="seconds to hold each beat")
    parser.add_argument("--loop", action="store_true", help="repeat until Ctrl+C")
    args = parser.parse_args(argv)

    origin, target = _window_points()
    publisher = EventPublisher()
    try:
        publisher.connect()
    except OSError as exc:
        print(f"FAIL cannot reach the overlay on {publisher.host}:{publisher.port} ({exc})")
        print("     start it first: python -m comstar_game_ai.overlay_ui.main")
        return 1
    print(f"OK  publishing to {publisher.host}:{publisher.port}, leash {origin} -> {target}")

    beats = _script(origin, target)
    try:
        while True:
            for index, (label, kind, payload) in enumerate(beats, start=1):
                print(f"{index:2}/{len(beats)}  {kind.value:18} {label}", flush=True)
                publisher.publish(kind, payload)
                time.sleep(max(0.1, args.step_s))
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        publisher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
