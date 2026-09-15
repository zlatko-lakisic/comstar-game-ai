"""Live smoke: AO object_detection on one campaign (or fixture) frame.

Success = structured detections JSON + latency, not useful RTW labels.
Stock ``detect_yolox_nano`` is COCO — expect person/car/empty on RTW art.

Uses Ada **catalog** id ``detect_yolox_nano`` by default (not a session-overlay
``client.*`` detector). Packing ``object_detection`` into the COMSTAR overlay has
been observed to leave the Reach WebSocket ``DISCONNECTED`` right after
``overlay_ack``; keep detectors out of the default overlay until Ada is stable.

Usage (from repo root)::

    python scripts/accept_detect_smoke.py
    python scripts/accept_detect_smoke.py --fixture tests/fixtures/frames/campaign-map-clear.png
    python scripts/accept_detect_smoke.py --agent detect_yolox_nano
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="",
        help="Agent id (default: config ao.detection_agent / client.detect_yolox_nano)",
    )
    parser.add_argument(
        "--fixture",
        default="",
        help="Image path instead of live WGC grab",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    from comstar_game_ai.agent.reach.director import DETECT_YOLOX_NANO
    from comstar_game_ai.agent.sync_deliberator import SyncCampaignDeliberator
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config
    from comstar_game_ai.shared.ipc.publisher import EventPublisher
    from comstar_game_ai.shared.runtime import ada_yield
    from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

    cfg = load_config()
    agent_id = (
        args.agent.strip()
        or str((cfg.get("ao") or {}).get("detection_agent") or DETECT_YOLOX_NANO).strip()
    )

    if args.fixture:
        frame = Image.open(args.fixture).convert("RGB")
    else:
        subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
        game = find_game_window(subs)
        if game is None:
            print("FAIL: Rome window not found (pass --fixture)", flush=True)
            return 2
        frame = grab_rgb_image(game.hwnd)
        if frame is None:
            print("FAIL: no frame", flush=True)
            return 2

    out = ROOT / "data" / "runtime" / "detection_smoke"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    frame.save(out / f"{stamp}_frame.jpg", quality=90)
    log_path = out / f"detect_smoke_{stamp}.log"

    faction = str((cfg.get("campaign") or {}).get("player_faction") or "julii")
    deliberator = SyncCampaignDeliberator(
        directive_store=DirectiveStore(),
        publisher=EventPublisher(),
        player_faction=faction,
        log_path=log_path,
    )
    print("starting AO deliberator...", flush=True)
    try:
        deliberator.start(timeout_s=900.0)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: AO session start: {exc}", flush=True)
        return 2
    # Same pump as accept_cv_besiege — let run_forever take the loop before calls.
    assert deliberator._loop is not None
    asyncio.run_coroutine_threadsafe(asyncio.sleep(0), deliberator._loop).result(timeout=10)
    time.sleep(0.4)
    session = deliberator._runtime.session
    if session is None or not session.is_active:
        bridge = getattr(session, "bridge", None) if session else None
        print(
            f"FAIL: bridge inactive after start "
            f"(state={getattr(bridge, 'state', None)!s} "
            f"error={getattr(bridge, 'error', None)!r})",
            flush=True,
        )
        deliberator.stop(timeout_s=30.0)
        return 2
    print(
        f"AO ready — bridge={session.bridge.state!s} log {log_path}",
        flush=True,
    )

    t0 = time.perf_counter()
    try:
        with ada_yield.held(holder="accept", reason="detect_smoke"):
            result = deliberator.query_object_detection(
                frame,
                agent_provider_id=agent_id,
                timeout_s=args.timeout,
                question_id=f"detect-smoke-{stamp}",
            )
    except Exception as exc:  # noqa: BLE001
        session = deliberator._runtime.session
        bridge = getattr(session, "bridge", None) if session else None
        print(
            f"FAIL: {type(exc).__name__}: {exc} "
            f"(bridge state={getattr(bridge, 'state', None)!s} "
            f"error={getattr(bridge, 'error', None)!r})",
            flush=True,
        )
        return 4
    finally:
        try:
            deliberator.stop(timeout_s=30.0)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN stop: {exc}", flush=True)

    elapsed = time.perf_counter() - t0
    raw = result.raw_text or ""
    (out / f"{stamp}_raw.json").write_text(raw, encoding="utf-8")
    print(
        f"OK agent={agent_id} elapsed={elapsed:.2f}s "
        f"dets={len(result.detections)} inference_ms={result.inference_ms}",
        flush=True,
    )
    for d in result.detections[:20]:
        print(f"  {d.label} score={d.score:.3f} box={d.box_xyxy}", flush=True)

    ann = frame.copy()
    draw = ImageDraw.Draw(ann)
    for d in result.detections:
        x1, y1, x2, y2 = d.box_xyxy
        draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 80), width=2)
        draw.text((x1, max(0, y1 - 12)), f"{d.label}:{d.score:.2f}", fill=(0, 255, 80))
    ann.save(out / f"{stamp}_ann.jpg", quality=90)

    try:
        obj = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        obj = None
    if not isinstance(obj, dict) or "detections" not in obj:
        # Some bridges may already parse; accept if we got DetectionResult boxes/meta
        if result.detections or result.inference_ms is not None:
            print(f"OK (parsed result without raw JSON text) artifacts under {out}", flush=True)
            return 0
        print("FAIL: answer was not detection JSON", flush=True)
        return 5
    print(f"artifacts under {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
