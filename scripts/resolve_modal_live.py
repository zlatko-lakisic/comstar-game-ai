#!/usr/bin/env python3
"""One-shot live campaign modal recognition and safe resolution."""

from __future__ import annotations

import sys

from comstar_game_ai.game_io.campaign.modal import ModalHandler
from comstar_game_ai.game_io.campaign.ui_mode import grab_and_classify
from comstar_game_ai.game_io.elevation import ensure_elevation_for_game, strip_elevation_marker
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config


def main() -> int:
    raw_argv = list(sys.argv)
    sys.argv = [sys.argv[0], *strip_elevation_marker()]
    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings", ["Rome"]))
    if game is None:
        print("FAIL Rome window not found", flush=True)
        return 1

    import win32process

    _, pid = win32process.GetWindowThreadProcessId(game.hwnd)
    elevation = ensure_elevation_for_game(pid, argv=raw_argv)
    if elevation == "relaunching":
        print("INFO approve UAC; elevated one-shot modal resolver will continue", flush=True)
        return 0
    if elevation == "failed":
        return 1

    before = grab_and_classify(game.hwnd)
    print(
        f"LIVE before: local_mode={before.mode.value} confidence={before.confidence:.2f} "
        f"detail={before.detail}",
        flush=True,
    )
    after = ModalHandler().handle(game.hwnd, before)
    print(
        f"LIVE after: local_mode={after.mode.value} confidence={after.confidence:.2f} "
        f"detail={after.detail}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
