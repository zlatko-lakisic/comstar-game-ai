# YOLOX RTW campaign detection

Hybrid targeting: OpenCV [`settlement_detector.py`](../src/comstar_game_ai/game_io/campaign/settlement_detector.py) for settlement badges until custom YOLO beats it; YOLOX for `army_stack` / `ship` after custom weights land. Megvii YOLOX only (Apache-2.0) — not Ultralytics.

**Claude handoff (full narrative + test archive):** [`yolox-rtw-claude-handoff.md`](yolox-rtw-claude-handoff.md) · archive [`design/assets/yolox-rtw-claude-handoff-archive.zip`](design/assets/yolox-rtw-claude-handoff-archive.zip).

## Classes (v1)

| id | name | visual |
|----|------|--------|
| 0 | `settlement_badge` | round faction ring |
| 1 | `settlement_oval` | plaque nameplate (right of badge); ground-town oval after `CLICK_OFFSET_PX` CAL |
| 2 | `army_stack` | field army banner |
| 3 | `ship` | naval stack |

## COMSTAR Reach agents

| Agent | Purpose |
|-------|---------|
| `detect_yolox_nano` | Stock Megvii COCO nano on Ada **catalog** (smoke) |
| `client.detect_rtw_campaign` | Custom RTW weights (optional overlay — enable only when Ada WS stays up) |

Config ([`config/default.yaml`](../config/default.yaml)):

- `ao.detection_agent` → catalog smoke default (`detect_yolox_nano`)
- `ao.detection_rtw_agent` → RTW overlay id (after publish)

**Do not pack `type: object_detection` into the default COMSTAR overlay** until Ada’s detection ensure keeps the Reach WebSocket alive. Live symptom: `SessionBridgeState.DISCONNECTED` / `WebSocket closed` immediately after `overlay_ack`. YAML for the COCO smoke agent lives under [`overlay/agent_providers/optional/`](../overlay/agent_providers/optional/detect_yolox_nano.yaml) (copy into `agent_providers/` only when Ada is fixed).

Client: [`map_object_detection.py`](../src/comstar_game_ai/game_io/campaign/map_object_detection.py) + [`call_map_object_detection`](../src/comstar_game_ai/agent/reach/director.py).

**Overlays carry ONNX weight URIs + agent YAML, not training images.** Dataset stays under `data/detection/` (gitignored).

## Prerequisites

- AO on Ada **≥ 2.11.0** with detection extras (`requirements-detection.txt` / GPU variant)
- COMSTAR `ao-reach>=0.19.0`
- Overlay agent `detect_yolox_nano.yaml` packs HTTPS Megvii weights (sha256 verified by AO)

## Smoke

```text
python scripts/accept_detect_smoke.py
python scripts/accept_detect_smoke.py --fixture tests/fixtures/frames/campaign-map-clear.png
```

Success = structured `detections` JSON + latency (COCO labels on RTW art may be empty).

## Dataset (automated #2)

```text
# Capture from live game, then CV-auto-label badges+ovals → COCO
python scripts/detection/automate_dataset.py --capture 60 --interval 1.5

# Label existing raw frames only (optional weak army proposals)
python scripts/detection/automate_dataset.py --skip-capture --weak-armies
```

What is automated:

- **settlement_badge** — OpenCV `detect_settlements`
- **settlement_oval** — plaque nameplate via detector `name_crop` (right of badge)
- **army_stack** — only with `--weak-armies` (noisy; skip for settlement-focused trains)
- **ship** — not auto-labeled yet (coastal frames + Label Studio / manual)

Early campaign often has **~10–12 visible unique settlements**. Make due by multi-view capture of those towns + `--oversample-settlements` (default 6) on settlement-positive frames — do not wait for the full map.

Writes `data/detection/coco/` with YOLOX folders `train2017` / `val2017`.

## Train + export + publish (automated #3)

On a CUDA host (prefer Ada), after COCO exists:

```text
python scripts/detection/automate_train.py --yolox-root %YOLOX_ROOT% --epochs 50 --activate
```

Clones Megvii YOLOX if needed → downloads nano `.pth` → train → export ONNX → `publish_rtw_weights.py`.

Publish-only from an existing ONNX:

```text
python scripts/detection/automate_train.py --onnx path/to/yolox_rtw_nano.onnx --activate
```

Exp: [`scripts/detection/yolox_exps/rtw_nano.py`](../scripts/detection/yolox_exps/rtw_nano.py) (`num_classes=4`, 416×416).

Offline check (no Ada):

```text
python scripts/detection/offline_val_check.py --onnx yolox_rtw_nano.onnx --image data/detection/coco/val2017/foo.jpg
```

## Publish overlay weights (manual equivalent)

```text
python scripts/detection/publish_rtw_weights.py --onnx yolox_rtw_nano.onnx --uri https://…/yolox_rtw_nano.onnx --activate
```

Writes `overlay/agent_providers/detect_rtw_campaign.yaml`. Seed Ada’s `AGENTIC_DETECTION_ARTIFACT_CACHE` as `<sha256>.onnx` when using `artifact://`, then refresh Reach overlay.

Template: [`detect_rtw_campaign.yaml.example`](../overlay/agent_providers/detect_rtw_campaign.yaml.example).

## Product accept paths

- YOLO army + CV settlement: `python scripts/accept_yolo_besiege_segesta.py`
- Settlement cutover eval: `python scripts/detection/eval_settlement_yolo_vs_cv.py`
  Cutover only if recall ≥ 0.9 and precision ≥ 0.8 vs CV.

Plaque **names** remain OCR / VL-on-crop; YOLO is localization only.
