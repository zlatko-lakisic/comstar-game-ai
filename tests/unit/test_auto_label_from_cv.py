"""Tests for CV → COCO auto-label helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "detection" / "auto_label_from_cv.py"


def _load():
    spec = importlib.util.spec_from_file_location("auto_label_from_cv", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auto_label_from_cv"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_badge_and_oval_boxes_in_frame():
    mod = _load()
    hit = {"badge_px": (100, 80), "badge_d": 28}
    boxes = mod.badge_and_oval_boxes(hit, 1280, 720)
    names = [n for n, _ in boxes]
    assert names == ["settlement_badge", "settlement_oval"]
    for _, (x0, y0, x1, y1) in boxes:
        assert 0 <= x0 < x1 < 1280
        assert 0 <= y0 < y1 < 720


def test_build_coco_on_synthetic_badge(tmp_path):
    import cv2

    mod = _load()
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.circle(img, (160, 100), 14, (0, 200, 0), 3)
    cv2.circle(img, (160, 100), 8, (220, 220, 220), -1)
    path = tmp_path / "frame.png"
    cv2.imwrite(str(path), img)
    coco, counts = mod.build_coco([path], weak_armies=False)
    assert "images" in coco and len(coco["categories"]) == 4
    assert isinstance(counts, dict)
