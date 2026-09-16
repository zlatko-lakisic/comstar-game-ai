"""Live accept: scan attackable settlements on the current campaign view.

Uses the same AO path as phase2: one ``SyncCampaignDeliberator`` Reach session
(not a one-shot ``ReachSession``, which re-registers overlay agents and often
returns empty/prose answers).

Requires Rome Remastered on the campaign map with an army selected (no Lists).

Usage (from repo root)::

    python scripts/accept_view_besiege.py
    python scripts/accept_view_besiege.py --prefer Segesta --click
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefer", default="", help="Prefer this settlement label if visible")
    parser.add_argument(
        "--click",
        action="store_true",
        help="Hover/sword/right-click the top ranked attackable settlement",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--faction",
        default="",
        help="Player faction slug for AO session (default: config campaign.player_faction)",
    )
    args = parser.parse_args()

    from comstar_game_ai.agent.sync_deliberator import SyncCampaignDeliberator
    from comstar_game_ai.game_io.campaign.army import count_selected_unit_cards
    from comstar_game_ai.game_io.campaign.besiege_actuation import BesiegeActuator
    from comstar_game_ai.game_io.campaign.map_target_vision import (
        rank_attackable_settlements,
    )
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config
    from comstar_game_ai.shared.ipc.publisher import EventPublisher
    from comstar_game_ai.shared.runtime import ada_yield
    from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

    cfg = load_config()
    faction = (
        args.faction.strip()
        or str((cfg.get("campaign") or {}).get("player_faction") or "julii")
    )
    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("ACCEPT FAIL: Rome window not found", flush=True)
        return 2

    hwnd = game.hwnd
    controller = SendInputController()
    controller.focus_window(hwnd)
    time.sleep(0.4)

    frame = grab_rgb_image(hwnd)
    if frame is None:
        print("ACCEPT FAIL: no frame", flush=True)
        return 2

    cards = count_selected_unit_cards(frame)
    print(f"ACCEPT: unit_cards={cards} (need >=1 for --click)", flush=True)

    out_dir = ROOT / "data" / "runtime" / "view_besiege"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    frame_path = out_dir / f"{stamp}_frame.jpg"
    frame.convert("RGB").save(frame_path, format="JPEG", quality=85)
    print(f"ACCEPT: saved frame {frame_path}", flush=True)

    log_path = out_dir / f"accept_scan_{stamp}.log"
    deliberator = SyncCampaignDeliberator(
        directive_store=DirectiveStore(),
        publisher=EventPublisher(),
        player_faction=faction,
        log_path=log_path,
    )
    print(
        "ACCEPT: starting AO deliberator (same path as phase2)...",
        flush=True,
    )
    try:
        deliberator.start(timeout_s=900.0)
    except Exception as exc:
        print(f"ACCEPT FAIL: AO session start: {exc}", flush=True)
        return 2
    print(f"ACCEPT: AO ready — log {log_path}", flush=True)

    try:
        print("ACCEPT: scanning settlements via deliberator session...", flush=True)
        with ada_yield.held(holder="accept", reason="settlement_scan"):
            hits = deliberator.query_settlement_scan(
                frame,
                prefer_label=args.prefer,
                timeout_s=args.timeout,
            )
        ranked = rank_attackable_settlements(hits, prefer_label=args.prefer)
        print(f"ACCEPT: raw={len(hits)} attackable={len(ranked)}", flush=True)
        for i, hit in enumerate(ranked[:12]):
            print(
                f"  [{i}] {hit.label} standing={hit.standing} "
                f"xy=({hit.x_norm:.3f},{hit.y_norm:.3f}) conf={hit.confidence:.2f} "
                f"{hit.reason}",
                flush=True,
            )
        for hit in hits:
            if hit.standing == "ours":
                print(
                    f"  (skip ours) {hit.label} xy=({hit.x_norm:.3f},{hit.y_norm:.3f})",
                    flush=True,
                )

        if not ranked:
            print("ACCEPT FAIL: no attackable settlements in view", flush=True)
            return 1

        if not args.click:
            print("ACCEPT OK: scan only (pass --click to besiege)", flush=True)
            return 0

        if cards < 1:
            print("ACCEPT FAIL: select an army on the map first (no Lists)", flush=True)
            return 1

        def scan(_image):
            return hits

        actuator = BesiegeActuator(
            hwnd=hwnd,
            controller=controller,
            scan_settlements=scan,
            capture=lambda: grab_rgb_image(hwnd),
        )
        outcome = actuator.besiege_from_view(prefer_label=args.prefer)
        print(
            f"ACCEPT besiege: ordered={outcome.ordered} reason={outcome.reason} "
            f"label={outcome.label!r} standing={outcome.standing} "
            f"click={outcome.click_norm} war={outcome.war_confirmed}",
            flush=True,
        )
        return 0 if outcome.ordered else 1
    finally:
        try:
            deliberator.stop(timeout_s=30.0)
        except Exception as exc:
            print(f"ACCEPT WARN: deliberator stop: {exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
