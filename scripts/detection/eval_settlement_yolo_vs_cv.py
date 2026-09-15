"""Side-by-side: OpenCV settlement badges vs YOLO settlement_badge/oval.

Default path uses local ONNX (Ada-trained weights) — no Reach publish needed.
Pass ``--reach`` to hit AO ``client.detect_rtw_campaign`` / catalog fallback.

Usage::

    python scripts/detection/eval_settlement_yolo_vs_cv.py --countdown 15
    python scripts/detection/eval_settlement_yolo_vs_cv.py --fixture path.jpg
    python scripts/detection/eval_settlement_yolo_vs_cv.py --reach
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_ONNX = ROOT / "data" / "detection" / "weights" / "yolox_rtw_nano.onnx"
CLASS_NAMES = [
    "settlement_badge",
    "settlement_oval",
    "army_stack",
    "ship",
]


def _match(
    cv_pts: list[tuple[float, float]],
    yolo_pts: list[tuple[float, float]],
    max_dist: float,
) -> tuple[int, list[tuple[float, float]], list[tuple[float, float]]]:
    remaining = list(enumerate(yolo_pts))
    matched = 0
    unmatched_cv: list[tuple[float, float]] = []
    for cx, cy in cv_pts:
        best_i = None
        best_d = float("inf")
        for i, (yx, yy) in remaining:
            d = math.hypot(cx - yx, cy - yy)
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None or best_d > max_dist:
            unmatched_cv.append((cx, cy))
            continue
        matched += 1
        remaining = [(i, p) for i, p in remaining if i != best_i]
    unmatched_yolo = [p for _, p in remaining]
    return matched, unmatched_cv, unmatched_yolo


def _countdown(seconds: int) -> None:
    if seconds <= 0:
        return
    print(
        f"\n>>> FOCUS ROME ON SETTLEMENTS — capture in {seconds}s <<<\n",
        flush=True,
    )
    for i in range(seconds, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)
    print("  CAPTURE\n", flush=True)


def _letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    h, w = img.shape[:2]
    ratio = min(size / h, size / w)
    nh, nw = int(round(h * ratio)), int(round(w * ratio))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    pad_w = (size - nw) / 2.0
    pad_h = (size - nh) / 2.0
    top, left = int(math.floor(pad_h)), int(math.floor(pad_w))
    canvas[top : top + nh, left : left + nw] = resized
    return canvas, ratio, (pad_w, pad_h)


def _yolox_decode(outputs: np.ndarray, input_h: int, input_w: int) -> np.ndarray:
    arr = np.asarray(outputs, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[None, ...]
    grids = []
    expanded_strides = []
    for stride in (8, 16, 32):
        hsize = input_h // stride
        wsize = input_w // stride
        xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((1, grid.shape[1], 1), stride))
    grids_a = np.concatenate(grids, 1).astype(np.float32)
    strides_a = np.concatenate(expanded_strides, 1).astype(np.float32)
    out = arr.copy()
    out[..., :2] = (out[..., :2] + grids_a) * strides_a
    out[..., 2:4] = np.exp(out[..., 2:4]) * strides_a
    return out


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return keep


def _run_onnx(
    bgr: np.ndarray,
    onnx_path: Path,
    *,
    input_size: int,
    conf: float,
    iou: float,
) -> list[dict[str, float | str | tuple[float, float, float, float]]]:
    import onnxruntime as ort

    orig_h, orig_w = bgr.shape[:2]
    canvas, ratio, pads = _letterbox(bgr, input_size)
    rgb = canvas[:, :, ::-1].astype(np.float32)
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...]
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    arr = np.asarray(sess.run(None, {sess.get_inputs()[0].name: tensor})[0], dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    expected = sum((input_size // s) ** 2 for s in (8, 16, 32))
    if arr.shape[0] == expected:
        arr = _yolox_decode(arr, input_size, input_size)[0]
    boxes_cxcywh = arr[:, :4]
    obj = arr[:, 4]
    cls_scores = arr[:, 5:]
    cls_ids = cls_scores.argmax(axis=1)
    scores = (obj * cls_scores.max(axis=1)).astype(np.float32)
    cx, cy, w, h = boxes_cxcywh.T
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    mask = scores >= conf
    boxes, scores, cls_ids = boxes[mask], scores[mask], cls_ids[mask]
    pad_w, pad_h = pads
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_w) / ratio
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_h) / ratio
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, orig_w - 1)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, orig_h - 1)
    keep = _nms(boxes, scores, iou) if len(scores) else []
    dets: list[dict[str, float | str | tuple[float, float, float, float]]] = []
    for i in keep:
        x1, y1, x2, y2 = (float(v) for v in boxes[i])
        cid = int(cls_ids[i])
        label = CLASS_NAMES[cid] if 0 <= cid < len(CLASS_NAMES) else str(cid)
        dets.append(
            {
                "label": label,
                "score": float(scores[i]),
                "box_xyxy": (x1, y1, x2, y2),
                "cx": (x1 + x2) / 2.0,
                "cy": (y1 + y2) / 2.0,
            }
        )
    return dets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="")
    parser.add_argument("--match-px", type=float, default=40.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--countdown", type=int, default=0)
    parser.add_argument(
        "--onnx",
        type=Path,
        default=DEFAULT_ONNX,
        help="Local ONNX for offline eval (default Ada export path)",
    )
    parser.add_argument("--input-size", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument(
        "--reach",
        action="store_true",
        help="Use AO Reach detection instead of local ONNX",
    )
    parser.add_argument(
        "--agent",
        default="",
        help="Detection agent when --reach (default: ao.detection_rtw_agent)",
    )
    args = parser.parse_args()

    from comstar_game_ai.game_io.campaign.settlement_detector import detect_settlements
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    _countdown(args.countdown)

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

    bgr = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
    cv_hits = detect_settlements(bgr)
    cv_pts = [(float(h["badge_px"][0]), float(h["badge_px"][1])) for h in cv_hits]
    print(f"CV badges={len(cv_pts)}", flush=True)

    provider = "local-onnx"
    if args.reach:
        from comstar_game_ai.agent.reach.director import DETECT_RTW_CAMPAIGN, DETECT_YOLOX_NANO
        from comstar_game_ai.agent.sync_deliberator import SyncCampaignDeliberator
        from comstar_game_ai.game_io.campaign.map_object_detection import (
            SETTLEMENT_LIKE,
            filter_labels,
            pair_badge_to_oval,
        )
        from comstar_game_ai.shared.ipc.publisher import EventPublisher
        from comstar_game_ai.shared.runtime import ada_yield
        from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

        ao = cfg.get("ao") or {}
        agent_id = (
            args.agent.strip()
            or str(ao.get("detection_rtw_agent") or DETECT_RTW_CAMPAIGN).strip()
        )
        faction = str((cfg.get("campaign") or {}).get("player_faction") or "julii")
        deliberator = SyncCampaignDeliberator(
            directive_store=DirectiveStore(),
            publisher=EventPublisher(),
            player_faction=faction,
        )
        print("starting AO deliberator...", flush=True)
        try:
            deliberator.start(timeout_s=900.0)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: AO session start: {exc}", flush=True)
            return 2
        try:
            with ada_yield.held(holder="accept", reason="settlement_eval"):
                try:
                    result = deliberator.query_object_detection(
                        frame,
                        agent_provider_id=agent_id,
                        timeout_s=args.timeout,
                        question_id="eval-settlement-yolo",
                    )
                except Exception:
                    result = deliberator.query_object_detection(
                        frame,
                        agent_provider_id=DETECT_YOLOX_NANO,
                        timeout_s=args.timeout,
                        question_id="eval-settlement-smoke",
                    )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL detect: {type(exc).__name__}: {exc}", flush=True)
            return 3
        finally:
            deliberator.stop()

        settlements = filter_labels(result.detections, SETTLEMENT_LIKE)
        badges = filter_labels(settlements, ["settlement_badge"])
        ovals = filter_labels(settlements, ["settlement_oval"])
        yolo_pts = [(d.cx, d.cy) for d in badges] or [(d.cx, d.cy) for d in ovals]
        provider = result.provider_id or agent_id
        print(
            f"YOLO badges={len(badges)} ovals={len(ovals)} provider={provider}",
            flush=True,
        )
        for badge, oval in pair_badge_to_oval(badges, ovals):
            print(
                f"  badge@{badge.centre_px()} → "
                f"{'oval@' + str(oval.centre_px()) if oval else 'no oval'}",
                flush=True,
            )
        draw_boxes = [(d.label, d.box_xyxy) for d in settlements]
    else:
        if not args.onnx.is_file():
            print(f"FAIL: missing ONNX {args.onnx}", flush=True)
            return 2
        try:
            dets = _run_onnx(
                bgr,
                args.onnx,
                input_size=args.input_size,
                conf=args.conf,
                iou=args.iou,
            )
        except ImportError:
            print("FAIL: pip install onnxruntime", flush=True)
            return 2
        badges = [d for d in dets if d["label"] == "settlement_badge"]
        ovals = [d for d in dets if d["label"] == "settlement_oval"]
        yolo_pts = [(float(d["cx"]), float(d["cy"])) for d in badges] or [
            (float(d["cx"]), float(d["cy"])) for d in ovals
        ]
        print(
            f"YOLO badges={len(badges)} ovals={len(ovals)} "
            f"other={len(dets) - len(badges) - len(ovals)} provider={provider} "
            f"onnx={args.onnx.name}",
            flush=True,
        )
        for d in badges:
            print(
                f"  badge@({d['cx']:.0f},{d['cy']:.0f}) score={d['score']:.2f}",
                flush=True,
            )
        for d in ovals:
            print(
                f"  oval@({d['cx']:.0f},{d['cy']:.0f}) score={d['score']:.2f}",
                flush=True,
            )
        draw_boxes = [(str(d["label"]), d["box_xyxy"]) for d in dets]

    matched, miss_cv, miss_yolo = _match(cv_pts, yolo_pts, args.match_px)
    precision = matched / len(yolo_pts) if yolo_pts else 0.0
    recall = matched / len(cv_pts) if cv_pts else 0.0
    print(
        f"match_px={args.match_px} matched={matched} "
        f"precision={precision:.2f} recall={recall:.2f} "
        f"unmatched_cv={len(miss_cv)} unmatched_yolo={len(miss_yolo)}",
        flush=True,
    )
    if miss_cv:
        print(f"  CV unmatched centres: {[(round(x), round(y)) for x, y in miss_cv]}", flush=True)
    if miss_yolo:
        print(f"  YOLO unmatched centres: {[(round(x), round(y)) for x, y in miss_yolo]}", flush=True)
    cutover_ok = bool(cv_pts) and recall >= 0.9 and precision >= 0.8

    out = ROOT / "data" / "runtime" / "detection_eval"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ann = frame.copy()
    draw = ImageDraw.Draw(ann)
    for x, y in cv_pts:
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], outline=(0, 255, 0), width=2)
    for label, box in draw_boxes:
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], outline=(255, 160, 0), width=2)
        draw.text((x1, max(0, y1 - 12)), str(label), fill=(255, 160, 0))
    ann_path = out / f"{stamp}_cv_vs_yolo.jpg"
    ann.save(ann_path, quality=90)
    print(f"wrote {ann_path}", flush=True)
    print(
        f"CUTOVER={'YES' if cutover_ok else 'NO'} "
        "(need recall>=0.9 and precision>=0.8 vs CV)",
        flush=True,
    )
    return 0 if cutover_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
