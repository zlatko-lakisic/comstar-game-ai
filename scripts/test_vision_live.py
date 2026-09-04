#!/usr/bin/env python3
"""Live end-to-end test: capture game window → Ada vision → print result.

Run with game open and on any screen (campaign map or dialog).
"""
from __future__ import annotations

import asyncio
import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, help="Analyze a saved screenshot instead of capturing Rome")
    args = parser.parse_args()

    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    # ── 1. Capture ──────────────────────────────────────────────────────────
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image, classify_campaign_image
    from PIL import Image

    print("\n── Step 1: Capture ──")
    if args.image:
        image = Image.open(args.image).convert("RGB")
        print(f"OK   replay image loaded: {args.image}")
    else:
        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
        game = find_game_window(subs)
        if game is None:
            print("FAIL: Rome window not found — make sure the game is running")
            return 1
        print(f"OK   game window: {game.title!r} {game.width}x{game.height} hwnd={game.hwnd}")
        image = grab_rgb_image(game.hwnd)
        if image is None:
            print("FAIL: grab_rgb_image returned None")
            return 1

    out_path = Path("data/runtime/live_vision_test_capture.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    print(f"OK   frame captured: {image.size[0]}x{image.size[1]} saved to {out_path}")

    # ── 2. Local classify ────────────────────────────────────────────────────
    print("\n── Step 2: Local classification ──")
    result = classify_campaign_image(image)
    print(f"     mode={result.mode.value}")
    print(f"     confidence={result.confidence:.3f}")
    print(f"     parchment_ratio={result.parchment_ratio:.3f}")
    print(f"     center_variance={result.center_variance:.4f}")
    print(f"     edge_luminance={result.edge_luminance:.3f}")
    print(f"     center_luminance={result.center_luminance:.3f}")
    print(f"     detail={result.detail!r}")

    # ── 3. Encode for Ada ────────────────────────────────────────────────────
    print("\n── Step 3: Encode for Ada ──")
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images

    from comstar_game_ai.game_io.campaign.modal import (
        build_modal_vision_prompt,
        vision_crop_bounds,
    )

    w, h = image.size
    crop_bounds = vision_crop_bounds(image, result.mode.value)
    cx0, cy0, cx1, cy1 = crop_bounds
    vision_image = image.crop((int(w * cx0), int(h * cy0), int(w * cx1), int(h * cy1)))
    print(f"     crop_bounds={crop_bounds} crop_size={vision_image.size}")
    images, stats = compose_reach_images(
        [vision_image],
        budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85),
    )
    if not images:
        print("FAIL: compose_reach_images returned nothing")
        return 1
    print(f"OK   encoded: {stats['encoded']} image(s), {stats['total_bytes']:,} bytes")

    # ── 4. Ada vision call ───────────────────────────────────────────────────
    print("\n── Step 4: Ada vision call (Reach/Ollama) ──")
    print("     Connecting to Ada Reach session...")

    request_id = f"live-vision-{int(time.time())}"
    prompt = build_modal_vision_prompt(ui_mode=result.mode.value, crop_bounds=crop_bounds)
    context = (
        f"screen_size={image.size[0]}x{image.size[1]}. "
        "Independently inspect the pixels; do not rely on any prior screen classification."
    )

    async def run_vision() -> str:
        from comstar_game_ai.agent.reach.director import call_modal_vision
        from comstar_game_ai.agent.reach.session import ReachSession

        session = ReachSession(enable_game_query=False)
        try:
            await session.start()
            print("OK   Reach session started")
            text = await call_modal_vision(
                session,
                text=prompt,
                context=context,
                question_id=request_id,
                images=images,
                timeout=180.0,
                on_status=lambda status: print(f"     ADA STATUS: {status}", flush=True),
                raise_errors=True,
            )
            print(f"OK   Ada response received ({len(text)} chars)")
            return text
        except Exception as exc:
            print(f"FAIL Ada call error: {type(exc).__name__}: {exc}")
            raise
        finally:
            await session.stop(clear_remote=False)

    try:
        raw = asyncio.run(run_vision())
    except Exception as exc:
        print(f"\nFAIL: Ada vision call failed: {exc}")
        return 1

    # ── 5. Parse + report ────────────────────────────────────────────────────
    print("\n── Step 5: Parse result ──")
    from comstar_game_ai.game_io.campaign.modal import _parse_modal_vision_result

    print("     Raw response from Ada:")
    print(f"     {raw}")

    parsed = _parse_modal_vision_result(raw, request_id=request_id)
    if parsed is None:
        print("\nWARN: Could not parse response as structured ModalVisionResult")
        print("      Ada may have returned prose instead of JSON — check model/prompt")
    else:
        sx, sy = cx1 - cx0, cy1 - cy0
        print(f"\nOK   modal_kind={parsed.modal_kind}")
        print(f"     dialog_bounds_norm={parsed.dialog_bounds_norm}  (crop-relative)")
        print(f"     reason={parsed.reason!r}")
        print(f"     candidates ({len(parsed.candidates)}):  crop-relative → window")
        for c in parsed.candidates:
            safe_marker = "SAFE" if c.action in {"reject", "close", "continue"} else "UNSAFE"
            wx, wy = cx0 + c.x_norm * sx, cy0 + c.y_norm * sy
            print(
                f"       [{safe_marker}] action={c.action} conf={c.confidence:.2f} "
                f"at=({c.x_norm:.3f},{c.y_norm:.3f}) → window=({wx:.3f},{wy:.3f})"
            )
        best = parsed.best_safe
        if best:
            wx, wy = cx0 + best.x_norm * sx, cy0 + best.y_norm * sy
            print(
                f"\n     → Best safe action: {best.action} conf={best.confidence:.2f} "
                f"window=({wx:.3f},{wy:.3f})"
            )
        else:
            print("\n     → No safe action candidate found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
