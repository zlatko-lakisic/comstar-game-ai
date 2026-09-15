"""Live settlement-detector smoke: 5s countdown → WGC frame → annotate badges."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from comstar_game_ai.game_io.campaign.settlement_detector import (
        click_point,
        detect_settlements,
    )
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    print("LIVE DETECT: focus the campaign map.", flush=True)
    for i in range(5, 0, -1):
        print(f"  capturing in {i}...", flush=True)
        time.sleep(1)
    print("CAPTURE", flush=True)

    cfg = load_config()
    game = find_game_window(cfg["game"]["window_title_substrings"])
    if game is None:
        print("FAIL: no game window", flush=True)
        return 2
    frame = grab_rgb_image(game.hwnd)
    if frame is None:
        print("FAIL: no frame", flush=True)
        return 2

    out = ROOT / "data" / "runtime" / "view_besiege"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_path = out / f"{stamp}_live_detect_frame.jpg"
    frame.convert("RGB").save(raw_path, quality=90)
    print(f"frame {frame.size} -> {raw_path}", flush=True)

    bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
    t0 = time.perf_counter()
    hits = detect_settlements(bgr)
    ms = (time.perf_counter() - t0) * 1000
    h, w = bgr.shape[:2]
    print(f"detected {len(hits)} in {ms:.1f} ms", flush=True)

    ann = frame.convert("RGB").copy()
    draw = ImageDraw.Draw(ann)
    for d in hits:
        x, y = d["badge_px"]
        col = (0, 220, 0) if d["faction_colour"] == "green" else (255, 60, 60)
        r = max(8, int(d["badge_d"]) // 2)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=col, width=3)
        draw.line((x - 16, y, x + 16, y), fill=col, width=2)
        draw.line((x, y - 16, x, y + 16), fill=col, width=2)
        nx, ny = x / w, y / h
        draw.text(
            (x + 12, y - 18),
            f"{d['faction_colour']} ({nx:.3f},{ny:.3f}) d={d['badge_d']}",
            fill=col,
        )
        draw.rectangle(d["name_crop"], outline=(255, 255, 0), width=1)
        print(
            json.dumps(
                {
                    "faction_colour": d["faction_colour"],
                    "badge_px": list(d["badge_px"]),
                    "badge_d": d["badge_d"],
                    "norm": [round(nx, 4), round(ny, 4)],
                    "name_crop": list(d["name_crop"]),
                }
            ),
            flush=True,
        )

    ann_path = out / f"{stamp}_live_detect_ann.jpg"
    ann.save(ann_path, quality=90)
    print(f"annotated -> {ann_path}", flush=True)

    try:
        click_point(hits[0] if hits else {"badge_px": (0, 0)})
        print("UNEXPECTED: click_point did not raise", flush=True)
    except NotImplementedError as exc:
        print(f"click_point refused (expected): {exc}", flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
