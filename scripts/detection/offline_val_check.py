"""Offline YOLOX-like postprocess check on a labelled COCO val image (no Ada).

Uses the same decode assumptions as AO ``postprocess_yolox_like`` (strides
8/16/32, letterbox to input size). Requires onnxruntime + the exported ONNX.

Usage::

    python scripts/detection/offline_val_check.py \\
      --onnx path/to/yolox_rtw_nano.onnx \\
      --image data/detection/coco/val/foo.jpg \\
      --out data/runtime/detection_offline/
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CLASS_NAMES = [
    "settlement_badge",
    "settlement_oval",
    "army_stack",
    "ship",
]


def _letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    h, w = img.shape[:2]
    ratio = min(size / h, size / w)
    nh, nw = int(round(h * ratio)), int(round(w * ratio))
    import cv2

    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    pad_w = (size - nw) / 2.0
    pad_h = (size - nh) / 2.0
    top, left = int(math.floor(pad_h)), int(math.floor(pad_w))
    canvas[top : top + nh, left : left + nw] = resized
    return canvas, ratio, (pad_w, pad_h)


def _yolox_demo_postprocess(outputs: np.ndarray, input_h: int, input_w: int) -> np.ndarray:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--input-size", type=int, default=416)
    parser.add_argument("--conf", type=float, default=0.3)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "runtime" / "detection_offline",
    )
    args = parser.parse_args()

    try:
        import onnxruntime as ort
    except ImportError:
        print("FAIL: pip install onnxruntime", flush=True)
        return 2

    import cv2

    bgr = cv2.imread(str(args.image))
    if bgr is None:
        print(f"FAIL: cannot read {args.image}", flush=True)
        return 3
    orig_h, orig_w = bgr.shape[:2]
    canvas, ratio, pads = _letterbox(bgr, args.input_size)
    rgb = canvas[:, :, ::-1].astype(np.float32)
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...]

    sess = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0].name
    outputs = sess.run(None, {inp: tensor})
    arr = np.asarray(outputs[0], dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    expected = sum((args.input_size // s) ** 2 for s in (8, 16, 32))
    # AO uses (h//s)*(w//s); square input → same.
    if arr.shape[0] == expected:
        arr = _yolox_demo_postprocess(arr, args.input_size, args.input_size)[0]

    boxes_cxcywh = arr[:, :4]
    obj = arr[:, 4]
    cls_scores = arr[:, 5:]
    cls_ids = cls_scores.argmax(axis=1)
    scores = (obj * cls_scores.max(axis=1)).astype(np.float32)
    cx, cy, w, h = boxes_cxcywh.T
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    mask = scores >= args.conf
    boxes, scores, cls_ids = boxes[mask], scores[mask], cls_ids[mask]
    # Map from letterbox to original
    pad_w, pad_h = pads
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_w) / ratio
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_h) / ratio
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, orig_w - 1)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, orig_h - 1)

    keep = _nms(boxes, scores, args.iou) if len(scores) else []
    args.out.mkdir(parents=True, exist_ok=True)
    ann = bgr.copy()
    print(f"detections={len(keep)} image={args.image.name}", flush=True)
    for i in keep:
        x1, y1, x2, y2 = boxes[i].astype(int)
        cid = int(cls_ids[i])
        label = CLASS_NAMES[cid] if 0 <= cid < len(CLASS_NAMES) else str(cid)
        print(f"  {label} {scores[i]:.3f} [{x1},{y1},{x2},{y2}]", flush=True)
        cv2.rectangle(ann, (x1, y1), (x2, y2), (0, 255, 80), 2)
        cv2.putText(
            ann,
            f"{label}:{scores[i]:.2f}",
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 80),
            1,
            cv2.LINE_AA,
        )
    out_path = args.out / f"{args.image.stem}_offline_ann.jpg"
    cv2.imwrite(str(out_path), ann)
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
