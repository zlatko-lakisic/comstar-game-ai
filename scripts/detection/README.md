# Detection tooling

See [docs/yolox-rtw-detection.md](../../docs/yolox-rtw-detection.md).

| Script | Role |
|--------|------|
| `automate_dataset.py` | **#2** Capture + CV auto-label → COCO |
| `automate_train.py` | **#3** Clone/train/export/publish ONNX |
| `capture_frames.py` | Dump WGC frames → `data/detection/raw/` |
| `auto_label_from_cv.py` | CV badges/ovals (+ optional weak armies) → COCO |
| `label_config.py` | Label Studio XML for 4 classes |
| `yolox_exps/rtw_nano.py` | Megvii YOLOX exp (`num_classes=4`) |
| `train_yolox_rtw.sh` | Train inside YOLOX checkout (manual) |
| `export_yolox_onnx.sh` | Export ONNX + sha256 (manual) |
| `offline_val_check.py` | Local onnxruntime decode check |
| `publish_rtw_weights.py` | Write overlay YAML from ONNX |
| `eval_settlement_yolo_vs_cv.py` | CV vs YOLO cutover gate |

Live accepts (repo `scripts/`):

- `accept_detect_smoke.py` — COCO nano plumbing
- `accept_yolo_besiege_segesta.py` — YOLO army + CV settlement
