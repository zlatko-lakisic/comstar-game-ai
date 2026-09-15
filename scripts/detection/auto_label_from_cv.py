"""Build COCO annotations from campaign frames using OpenCV settlement detect.

Automates the bulk of dataset labeling for ``settlement_badge`` + ``settlement_oval``.
``army_stack`` / ``ship`` are left empty unless ``--weak-armies`` is set (heuristic
proposals only — review before trusting them for final weights).

Usage::

    python scripts/detection/auto_label_from_cv.py --images data/detection/raw
    python scripts/detection/auto_label_from_cv.py --images data/detection/raw --out data/detection/coco
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comstar_game_ai.game_io.campaign.map_object_detection import RTW_CLASS_NAMES  # noqa: E402

# settlement_oval: plaque nameplate to the right of the badge (same geometry as
# settlement_detector._name_crop_box). Ground-town click oval needs CLICK_OFFSET_PX
# and is not auto-labeled until that CAL exists.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _categories() -> list[dict[str, Any]]:
    return [
        {"id": i + 1, "name": name, "supercategory": "rtw"}
        for i, name in enumerate(RTW_CLASS_NAMES)
    ]


def _cat_id(name: str) -> int:
    return list(RTW_CLASS_NAMES).index(name) + 1


def _clamp_box(x0: float, y0: float, x1: float, y1: float, w: int, h: int) -> tuple[float, float, float, float] | None:
    x0 = max(0.0, min(float(w - 1), x0))
    y0 = max(0.0, min(float(h - 1), y0))
    x1 = max(0.0, min(float(w - 1), x1))
    y1 = max(0.0, min(float(h - 1), y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return (x0, y0, x1, y1)


def _xyxy_to_coco(box: tuple[float, float, float, float]) -> list[float]:
    x0, y0, x1, y1 = box
    return [float(x0), float(y0), float(x1 - x0), float(y1 - y0)]


def badge_and_oval_boxes(hit: dict[str, Any], frame_w: int, frame_h: int) -> list[tuple[str, tuple[float, float, float, float]]]:
    bx, by = hit["badge_px"]
    d = float(hit.get("badge_d") or 28)
    half = d / 2.0
    badge = _clamp_box(bx - half, by - half, bx + half, by + half, frame_w, frame_h)
    out: list[tuple[str, tuple[float, float, float, float]]] = []
    if badge is not None:
        out.append(("settlement_badge", badge))
    # Plaque nameplate (right of badge). Prefer detector crop when present.
    crop = hit.get("name_crop")
    if crop is not None and len(crop) == 4:
        x0, y0, x1, y1 = (float(v) for v in crop)
    else:
        x0 = bx + d * 0.45
        x1 = min(frame_w - 1.0, bx + d * 5.0)
        y0 = max(0.0, by - d * 0.75)
        y1 = min(frame_h - 1.0, by + d * 0.75)
    oval = _clamp_box(x0, y0, x1, y1, frame_w, frame_h)
    if oval is not None:
        out.append(("settlement_oval", oval))
    return out


def weak_army_boxes(bgr: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Heuristic: tall thin saturated blobs (banner-like). High false-positive rate."""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # Saturated colourful pixels (faction banners)
    sat = (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 80)
    mask = sat.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes: list[tuple[float, float, float, float]] = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 40 or area > 2500:
            continue
        if bh < 18 or bw < 4:
            continue
        aspect = bh / max(1, bw)
        if aspect < 1.6 or aspect > 6.0:
            continue
        # Skip HUD margins
        if x < 40 or y < 40 or x + bw > w - 40 or y + bh > h - 60:
            continue
        box = _clamp_box(x - 2, y - 2, x + bw + 2, y + bh + 2, w, h)
        if box is not None:
            boxes.append(box)
    return boxes[:12]


def label_image(bgr: np.ndarray, *, weak_armies: bool) -> list[dict[str, Any]]:
    from comstar_game_ai.game_io.campaign.settlement_detector import detect_settlements

    h, w = bgr.shape[:2]
    anns: list[dict[str, Any]] = []
    for hit in detect_settlements(bgr):
        for name, box in badge_and_oval_boxes(hit, w, h):
            xywh = _xyxy_to_coco(box)
            anns.append(
                {
                    "category_id": _cat_id(name),
                    "bbox": xywh,
                    "area": xywh[2] * xywh[3],
                    "iscrowd": 0,
                    "attributes": {"source": "cv_settlement_detector", "auto": True},
                }
            )
    if weak_armies:
        for box in weak_army_boxes(bgr):
            xywh = _xyxy_to_coco(box)
            anns.append(
                {
                    "category_id": _cat_id("army_stack"),
                    "bbox": xywh,
                    "area": xywh[2] * xywh[3],
                    "iscrowd": 0,
                    "attributes": {"source": "weak_banner_heuristic", "auto": True, "weak": True},
                }
            )
    return anns


def build_coco(
    image_paths: list[Path],
    *,
    weak_armies: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    counts = {name: 0 for name in RTW_CLASS_NAMES}
    ann_id = 1
    for img_id, path in enumerate(image_paths, start=1):
        bgr = cv2.imread(str(path))
        if bgr is None:
            continue
        h, w = bgr.shape[:2]
        images.append(
            {
                "id": img_id,
                "file_name": path.name,
                "width": w,
                "height": h,
            }
        )
        for ann in label_image(bgr, weak_armies=weak_armies):
            ann = dict(ann)
            ann["id"] = ann_id
            ann["image_id"] = img_id
            annotations.append(ann)
            name = RTW_CLASS_NAMES[ann["category_id"] - 1]
            counts[name] = counts.get(name, 0) + 1
            ann_id += 1
    coco = {
        "info": {
            "description": "COMSTAR RTW auto-label (CV badges/ovals)",
            "version": "0.1",
            "year": int(time.strftime("%Y")),
            "date_created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": _categories(),
    }
    return coco, counts


def split_indices(
    n: int,
    val_frac: float,
    seed: int = 13,
    *,
    positive: set[int] | None = None,
) -> tuple[list[int], list[int]]:
    """Split indices; keep settlement-positive frames in both train and val when possible."""
    rng = np.random.default_rng(seed)
    all_idx = list(range(n))
    pos = sorted(positive or set())
    neg = [i for i in all_idx if i not in set(pos)]
    rng.shuffle(pos)
    rng.shuffle(neg)
    n_val = max(1, int(round(n * val_frac))) if n >= 5 else max(0, min(1, n // 5))
    # Prefer ~20% of settlement-positive frames in val (scarce early-campaign towns).
    n_val_pos = min(len(pos), max(1, int(round(len(pos) * 0.2)))) if pos else 0
    n_val_neg = min(len(neg), max(0, n_val - n_val_pos))
    if n_val_pos + n_val_neg < n_val and len(neg) > n_val_neg:
        n_val_neg = min(len(neg), n_val - n_val_pos)
    if n_val_pos + n_val_neg < n_val and len(pos) > n_val_pos:
        n_val_pos = min(len(pos), n_val - n_val_neg)
    val = set(pos[:n_val_pos] + neg[:n_val_neg])
    train = [i for i in all_idx if i not in val]
    return train, sorted(val)


def oversample_paths(
    paths: list[Path],
    coco: dict[str, Any],
    *,
    factor: int,
    out_dir: Path,
) -> tuple[list[Path], dict[str, Any]]:
    """Repeat settlement-positive frames ``factor`` times (multi-view stand-in)."""
    if factor <= 1:
        return paths, coco
    sett_ids = {
        c["id"]
        for c in coco["categories"]
        if c["name"] in ("settlement_badge", "settlement_oval")
    }
    pos_img_ids = {
        a["image_id"] for a in coco["annotations"] if a["category_id"] in sett_ids
    }
    if not pos_img_ids:
        return paths, coco

    out_dir.mkdir(parents=True, exist_ok=True)
    id_to_path = {img["id"]: paths[i] for i, img in enumerate(coco["images"])}
    new_paths: list[Path] = []
    new_images: list[dict[str, Any]] = []
    new_anns: list[dict[str, Any]] = []
    ann_by_img: dict[int, list[dict[str, Any]]] = {}
    for a in coco["annotations"]:
        ann_by_img.setdefault(a["image_id"], []).append(a)

    next_img = 1
    next_ann = 1
    for img in coco["images"]:
        src = id_to_path[img["id"]]
        repeats = factor if img["id"] in pos_img_ids else 1
        for r in range(repeats):
            if r == 0:
                dst = out_dir / src.name
            else:
                dst = out_dir / f"{src.stem}_os{r}{src.suffix}"
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
            new_paths.append(dst)
            new_images.append(
                {
                    "id": next_img,
                    "file_name": dst.name,
                    "width": img["width"],
                    "height": img["height"],
                }
            )
            for a in ann_by_img.get(img["id"], []):
                new_anns.append({**a, "id": next_ann, "image_id": next_img})
                next_ann += 1
            next_img += 1

    new_coco = {
        **coco,
        "images": new_images,
        "annotations": new_anns,
    }
    return new_paths, new_coco


def write_split(
    coco: dict[str, Any],
    image_paths: list[Path],
    indices: list[int],
    *,
    images_dir: Path,
    ann_path: Path,
) -> None:
    images_dir.mkdir(parents=True, exist_ok=True)
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    id_map: dict[int, int] = {}
    new_images: list[dict[str, Any]] = []
    for new_id, old_i in enumerate(indices, start=1):
        old = coco["images"][old_i]
        src = image_paths[old_i]
        dst = images_dir / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        id_map[old["id"]] = new_id
        new_images.append({**old, "id": new_id, "file_name": src.name})
    new_anns: list[dict[str, Any]] = []
    ann_id = 1
    for ann in coco["annotations"]:
        if ann["image_id"] not in id_map:
            continue
        new_anns.append({**ann, "id": ann_id, "image_id": id_map[ann["image_id"]]})
        ann_id += 1
    out = {
        "info": coco["info"],
        "licenses": coco.get("licenses") or [],
        "images": new_images,
        "annotations": new_anns,
        "categories": coco["categories"],
    }
    ann_path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "data" / "detection" / "raw",
        help="Directory of captured frames",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "detection" / "coco",
        help="COCO root (train/ val/ annotations/)",
    )
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--weak-armies", action="store_true")
    parser.add_argument(
        "--oversample-settlements",
        type=int,
        default=6,
        help="Repeat settlement-positive train frames this many times (early-campaign scarcity)",
    )
    parser.add_argument(
        "--min-boxes",
        type=int,
        default=1,
        help="Skip images with fewer than this many auto boxes",
    )
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    if not args.images.is_dir():
        print(f"FAIL: missing images dir {args.images}", flush=True)
        return 2

    paths = sorted(
        p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file()
    )
    if not paths:
        print(f"FAIL: no images in {args.images}", flush=True)
        return 3

    print(f"Auto-labeling {len(paths)} images (weak_armies={args.weak_armies})…", flush=True)
    coco, counts = build_coco(paths, weak_armies=args.weak_armies)

    # Drop empty images if requested
    keep_ids = set()
    per_image: dict[int, int] = {}
    for ann in coco["annotations"]:
        per_image[ann["image_id"]] = per_image.get(ann["image_id"], 0) + 1
    for img in coco["images"]:
        if per_image.get(img["id"], 0) >= args.min_boxes:
            keep_ids.add(img["id"])

    # image ids were 1..n matching paths order
    filtered_paths = [paths[i - 1] for i in sorted(keep_ids)]
    coco, counts = build_coco(filtered_paths, weak_armies=args.weak_armies)
    kept_paths = filtered_paths

    print("box counts:", flush=True)
    for name, n in counts.items():
        print(f"  {name}: {n}", flush=True)
    print(f"images kept: {len(kept_paths)}", flush=True)

    sett_cat = {
        c["id"]
        for c in coco["categories"]
        if c["name"] in ("settlement_badge", "settlement_oval")
    }
    pos_img_ids = {
        a["image_id"] for a in coco["annotations"] if a["category_id"] in sett_cat
    }
    # images id is 1..n → path index = id-1
    positive_idx = {img_id - 1 for img_id in pos_img_ids}

    train_idx, val_idx = split_indices(
        len(kept_paths),
        args.val_frac,
        seed=args.seed,
        positive=positive_idx,
    )
    print(
        f"split train={len(train_idx)} val={len(val_idx)} "
        f"(settlement-positive: train={sum(1 for i in train_idx if i in positive_idx)} "
        f"val={sum(1 for i in val_idx if i in positive_idx)})",
        flush=True,
    )

    # Oversample settlement frames in train only (copies under coco/_os_train).
    train_paths = [kept_paths[i] for i in train_idx]
    train_coco_imgs = [coco["images"][i] for i in train_idx]
    train_img_ids = {img["id"] for img in train_coco_imgs}
    train_coco = {
        **coco,
        "images": train_coco_imgs,
        "annotations": [a for a in coco["annotations"] if a["image_id"] in train_img_ids],
    }
    # Remap train coco image ids to 1..len for oversample helper
    remap = {old["id"]: j + 1 for j, old in enumerate(train_coco["images"])}
    train_coco = {
        **train_coco,
        "images": [{**im, "id": remap[im["id"]]} for im in train_coco["images"]],
        "annotations": [
            {**a, "image_id": remap[a["image_id"]]} for a in train_coco["annotations"]
        ],
    }
    os_dir = args.out / "_os_train"
    os_paths, os_coco = oversample_paths(
        train_paths,
        train_coco,
        factor=max(1, args.oversample_settlements),
        out_dir=os_dir,
    )
    os_train_idx = list(range(len(os_paths)))
    write_split(
        os_coco,
        os_paths,
        os_train_idx,
        images_dir=args.out / "train2017",
        ann_path=args.out / "annotations" / "instances_train2017.json",
    )
    write_split(
        coco,
        kept_paths,
        val_idx,
        images_dir=args.out / "val2017",
        ann_path=args.out / "annotations" / "instances_val2017.json",
    )
    # Also mirror short names for humans / docs.
    write_split(
        os_coco,
        os_paths,
        os_train_idx,
        images_dir=args.out / "train",
        ann_path=args.out / "annotations" / "instances_train.json",
    )
    write_split(
        coco,
        kept_paths,
        val_idx,
        images_dir=args.out / "val",
        ann_path=args.out / "annotations" / "instances_val.json",
    )
    train_counts = {name: 0 for name in RTW_CLASS_NAMES}
    for a in os_coco["annotations"]:
        name = RTW_CLASS_NAMES[a["category_id"] - 1]
        train_counts[name] = train_counts.get(name, 0) + 1
    summary = {
        "images": len(kept_paths),
        "train_unique": len(train_idx),
        "train_after_oversample": len(os_paths),
        "val": len(val_idx),
        "counts_unique": counts,
        "counts_train_oversampled": train_counts,
        "weak_armies": args.weak_armies,
        "oversample_settlements": args.oversample_settlements,
        "oval": "nameplate_right_of_badge",
        "note": "Early campaign: few unique settlements; oversample multi-view frames.",
    }
    (args.out / "auto_label_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.out}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    if counts.get("settlement_badge", 0) < 20:
        print(
            "NOTE: few settlement boxes — keep OpenCV for settlements; "
            "revisit when more towns are visible or zoomed.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
