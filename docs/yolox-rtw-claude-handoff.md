# YOLOX RTW campaign detection — Claude handoff

**Date:** 2026-09-15  
**Repo:** `comstar-game-ai`  
**Status:** Plumbing + offline training complete; **custom RTW YOLO is not used for live gameplay**. Settlements remain OpenCV. Army/ship YOLO not trained with real labels.

**Companion archive:** [`docs/design/assets/yolox-rtw-claude-handoff-archive.zip`](../design/assets/yolox-rtw-claude-handoff-archive.zip) (~14 MB)  
Unpacked mirror under `data/detection/handoff_archive/` (gitignored data tree).

Related short ops doc: [`docs/yolox-rtw-detection.md`](yolox-rtw-detection.md).

---

## 1. Goal and product decision

### Intended hybrid

| Target | Intended detector | Why |
|--------|-------------------|-----|
| Settlement badge / plaque | OpenCV until YOLO wins | Structural CV works today; plaques are small, few unique towns early-campaign |
| Army stacks / ships | Custom Megvii YOLOX | Hard for hue-ring CV; YOLO’s job once labeled |

**Megvii YOLOX only (Apache-2.0).** Ultralytics was rejected (license / product constraint).

### Decision after this sprint (do not cut over)

**Do not replace OpenCV settlements with YOLO.** Live cutover gate failed (need recall ≥ 0.9 and precision ≥ 0.8 vs CV badge centres). Custom ONNX stays offline/experimental. Catalog COCO nano is smoke-only.

**Reasoning (expanded in §8):** val AP looked OK but live recall was poor; YOLO confused army banners with badges; early campaign has ~11 unique towns so “more unique classes” is impossible—only multi-view of the same set; armies/ships never got real labels so the product YOLO win condition was never exercised.

---

## 2. What was implemented

### 2.1 Reach / COMSTAR client plumbing

| Piece | Path / id | Notes |
|-------|-----------|--------|
| Catalog smoke agent | `detect_yolox_nano` | Stock Megvii COCO nano on Ada catalog |
| RTW agent id (future) | `client.detect_rtw_campaign` | Allowlisted; YAML is **example only**, not in default overlay |
| Config | `config/default.yaml` → `ao.detection_agent`, `ao.detection_rtw_agent` | |
| Client parse / helpers | `src/comstar_game_ai/game_io/campaign/map_object_detection.py` | Classes, filters, badge↔oval pairing |
| Async call | `call_map_object_detection` in `agent/reach/director.py` | |
| Sync wrapper | `SyncCampaignDeliberator.query_object_detection` | |
| Optional overlay YAML | `overlay/agent_providers/optional/detect_yolox_nano.yaml` | **Not** packed into default overlay |
| RTW publish template | `overlay/agent_providers/detect_rtw_campaign.yaml.example` | |

**Critical Ada lesson:** do **not** `_wait_ready` on catalog detectors (no overlay `agent_state` → 180s hang).  
**Critical overlay lesson:** packing `type: object_detection` into the **default** COMSTAR overlay caused Reach WS `DISCONNECTED` / `WebSocket closed` after `overlay_ack`. Keep detection out of default pack until Ada ensure is stable.

Overlays carry **ONNX URI + agent YAML**, not training images.

### 2.2 Classes (v1)

| id | name | Training reality |
|----|------|------------------|
| 0 | `settlement_badge` | Auto-labeled from OpenCV `detect_settlements` |
| 1 | `settlement_oval` | Auto-labeled as **plaque nameplate** via detector `name_crop` (right of badge)—not ground-town oval (`CLICK_OFFSET_PX` still unmeasured) |
| 2 | `army_stack` | **0** real labels in final trains (weak heuristic dropped—it drowned settlement loss) |
| 3 | `ship` | **0** labels |

### 2.3 OpenCV settlement detector upgrades (feeds labels + live truth)

File: `src/comstar_game_ai/game_io/campaign/settlement_detector.py`

- Hue `BANDS` expanded from red/green only using KB `FACTION_LEGEND_COLOURS` / `campaign_ui_atlas` + live rim samples after `capital_zoom` (Home → capital).
- Final families: **red** (Julii), **green** (Brutii/Gaul), **blue** (Scipii, S≥120 so sea does not flood), **purple** (SPQR).
- Skipped low-sat legend fills (Carthage white, Rebels taupe, Greek olive, …)—they flood terrain.
- **Do not widen red past ~H∈[0,8]**—wider red merges with orange terrain and breaks diameter gates.
- Helper: `scripts/detection/learn_badge_hues.py`

### 2.4 Dataset pipeline

| Script | Role |
|--------|------|
| `scripts/detection/capture_frames.py` | WGC grabs → `data/detection/raw/`; `--auto-move`, `--pan-only`, `--countdown` |
| `scripts/detection/auto_label_from_cv.py` | CV → COCO; stratified split; `--oversample-settlements` on train positives |
| `scripts/detection/automate_dataset.py` | Capture + label orchestration |
| `scripts/detection/label_config.py` | Label Studio XML for 4 classes |

COCO layout: `data/detection/coco/{train2017,val2017,annotations}/`.

Final auto-label summary (`auto_label_summary.json`):

```json
{
  "images": 275,
  "train_unique": 234,
  "train_after_oversample": 1011,
  "val": 41,
  "counts_unique": {
    "settlement_badge": 257,
    "settlement_oval": 257,
    "army_stack": 0,
    "ship": 0
  },
  "oversample_settlements": 8,
  "oval": "nameplate_right_of_badge",
  "weak_armies": false
}
```

Early campaign constraint: ~11 unique visible settlements—volume comes from **multi-view**, not new town IDs.

### 2.5 Train / export on Ada

| Script | Role |
|--------|------|
| `scripts/detection/train_on_ada.py` | SSH upload COCO, venv+torch, YOLOX install, background train, `--status`, `--export` |
| `scripts/detection/yolox_exps/rtw_nano.py` | Exp: 4 classes, **640×640**, mosaic 0.4, mixup off, 80 epochs typical |
| `scripts/detection/automate_train.py` | Local YOLOX train/export/publish alternative |
| `scripts/detection/publish_rtw_weights.py` | Write overlay YAML from ONNX (not activated in default overlay) |

Ada setup fixes encountered:

1. Install **torch (cu121) before** `pip install -e YOLOX`.
2. Pin YOLOX setup version (shallow clone → `unknown` breaks setuptools).
3. Install YOLOX with `--no-deps` (skip broken `onnx-simplifier` metadata).
4. Patch `tools/export_onnx.py`: `torch.onnx._export` → `torch.onnx.export` (Torch 2.x).

Remote workdir (operator machine): `~/comstar-yolox-rtw/` (YOLOX clone, venv, coco, weights, logs). Credentials via `.cursor/secrets/.ada` + `~/.ssh/id_rsa`—never commit/print.

Exported artifact: `data/detection/weights/yolox_rtw_nano.onnx` (~8.6 MB).  
Last handoff sha256 file is in the archive under `weights/`.

### 2.6 Eval / accept scripts

| Script | Role |
|--------|------|
| `scripts/accept_detect_smoke.py` | Reach catalog nano smoke |
| `scripts/detection/eval_settlement_yolo_vs_cv.py` | Live/fixture cutover: CV vs local ONNX (default) or `--reach` |
| `scripts/detection/offline_val_check.py` | onnxruntime letterbox + YOLOX decode |
| `scripts/accept_yolo_besiege_segesta.py` | Hybrid accept skeleton: **CV settlements** + YOLO armies when available |
| `scripts/accept_cv_besiege_segesta.py` | CV-only settlement path (production-aligned) |

Cutover gate (eval script): among CV badge centres vs YOLO badge (or oval if no badges) centres within `--match-px` (default 40–60):

- `CUTOVER=YES` iff CV count > 0 and **recall ≥ 0.9** and **precision ≥ 0.8**.

---

## 3. How training was done (chronology condensed)

1. **Smoke:** catalog `detect_yolox_nano` via Reach — OK (~person boxes on unrelated art; plumbing works).
2. **Capture:** auto pan/zoom Italy, then south/Sicily, then close **pan-only** passes; later “hard-neg” pass with banners in frame.
3. **Label:** CV badges + nameplate ovals; drop weak armies for settlement-focused trains; oversample settlement-positive train frames ×8.
4. **Hue expansion:** KB legend → HSV; Home capital_zoom; learn rims; add blue/purple with sat floors → badges **108 → 192 → 257**.
5. **Ada trains:** YOLOX-Nano pretrained, FP16, batch 4, 80 epochs, 640 input. Best reported AP climbed into mid–high 60s / ~76 on last settlement-heavy set (optimistic—same towns in train/val views).
6. **Export ONNX** each time; download locally. **Did not** activate RTW agent in default overlay.

---

## 4. What was tested and how

### 4.1 Unit / structural

```text
python -m pytest tests/unit/test_settlement_detector.py -q
```

- Reference frame: `data/runtime/view_besiege/20260911-220517_qwen3vl_frame.jpg` (also copied into archive `cv_unit_fixture/`).
- Expects ≥3 CV hits including red + green near hand-measured centres.
- Confirms `CLICK_OFFSET_PX` still raises until measured.

### 4.2 Reach smoke

```text
python scripts/accept_detect_smoke.py
```

- Catalog nano; structured detections JSON; proves COMSTAR↔Ada detection path without custom weights.

### 4.3 Offline ONNX

```text
python scripts/detection/offline_val_check.py \
  --onnx data/detection/weights/yolox_rtw_nano.onnx \
  --image <val jpg> --input-size 640
```

- Letterbox 640, YOLOX strides 8/16/32 decode, NMS; visual annotated dump.

### 4.4 Live cutover (primary product gate)

```text
python scripts/detection/eval_settlement_yolo_vs_cv.py --countdown 20 --input-size 640 --match-px 60
```

Default path: grab Rome window → OpenCV `detect_settlements` → local ONNX decode (same as offline) → centre match → write annotated JPEG under `data/runtime/detection_eval/`.

Green rings = CV badges; orange boxes = YOLO detections.

### 4.5 Ada train monitoring

```text
python scripts/detection/train_on_ada.py --status
python scripts/detection/train_on_ada.py --export
```

---

## 5. Results (what Claude should believe)

### 5.1 Offline / val (Ada YOLOX COCO eval)

Approximate progression (per-class AP on tiny val; **same early-campaign towns**, so optimistic):

| Phase | Rough best AP | Badge / oval notes |
|-------|---------------|--------------------|
| First train (weak armies drowning) | ~9.5 | Settlements **0** AP |
| Settlements-only + oval fix + oversample | ~66–72 | Badge/oval learning |
| + hue bands (Scipii blue etc.) | ~70 | More GT volume |
| + hard-neg / more close views | **~76.5** | Badge ~74 / oval ~76 on val |

These numbers **do not** transfer cleanly to live cutover.

### 5.2 Live CV vs YOLO (annotated frames in archive `eval/`)

| Stamp | CV | YOLO | Match @60px | Notes |
|-------|----|------|-------------|--------|
| `20260914-190818` | 4 | 1 badge + 2 ovals | 0 / 0 | Ovals near plaques; badge FP on army banner |
| `20260914-194452` | 4 | 1 oval | 0 | Zoomed-out Italy; tooltip clutter |
| `20260914-201105` | 0 | 0 | n/a | Empty / wrong camera at capture |
| `20260914-221046` | 4 | 1 badge | 0 / 0 | Badge on **blue army/agent banner** |
| `20260914-231402` | 0 | 0 | n/a | Empty at countdown |
| `20260915-062933` | 4 | 0 badge + 1 oval | **P=1.00 R=0.25** | Best live: no banner FP; **recall too low** |

**Final live verdict:** `CUTOVER=NO`. Precision can look fine when YOLO fires rarely; **recall ≪ 0.9**.

### 5.3 What YOLO can recognize today

| Class | Useful for gameplay? |
|-------|----------------------|
| `settlement_oval` | Weak experimental plaque localization only |
| `settlement_badge` | Unreliable; historically FP on army banners |
| `army_stack` | No (untrained) |
| `ship` | No (untrained) |
| Catalog COCO nano | Smoke only |

### 5.4 What production uses now

- Settlements: **OpenCV** `detect_settlements`.
- YOLO RTW ONNX: **not** on the live actuate path.
- `accept_yolo_besiege_segesta.py` still takes settlement centres from CV.

---

## 6. Archive contents (for re-test)

Zip: `docs/design/assets/yolox-rtw-claude-handoff-archive.zip`

| Path in archive | Purpose |
|-----------------|--------|
| `eval/*_cv_vs_yolo.jpg` | Live cutover annotated frames (CV green / YOLO orange) |
| `hue_learn/` | Rome capital frame, rim hits, `learned_bands.json` |
| `coco_val_sample/instances_val2017.json` | Full val annotation file |
| `coco_val_sample/*.jpg` | 12 settlement-positive val images |
| `weights/yolox_rtw_nano.onnx` | Last exported RTW nano |
| `weights/yolox_rtw_nano.onnx.sha256` | Digest |
| `auto_label_summary.json` | Dataset counts |
| `cv_unit_fixture/20260911-220517_qwen3vl_frame.jpg` | CV unit-test reference (if present) |

**Reproduce cutover offline on an archived eval frame:** the eval JPEGs are already annotated composites; for raw re-inference use a live grab or a `raw/` frame plus:

```text
python scripts/detection/offline_val_check.py \
  --onnx docs/.../extract/weights/yolox_rtw_nano.onnx \
  --image <frame.jpg> --input-size 640 --conf 0.25
```

**Reproduce CV vs ONNX on a fixture** (after extracting archive):

```text
python scripts/detection/eval_settlement_yolo_vs_cv.py \
  --fixture <path-to-raw-or-rome.jpg> \
  --onnx <path-to-yolox_rtw_nano.onnx> \
  --input-size 640 --match-px 60
```

Full raw set (275 JPEGs) and full COCO train live under `data/detection/` (large; not all zipped).

---

## 7. Key file index

```text
src/comstar_game_ai/game_io/campaign/settlement_detector.py
src/comstar_game_ai/game_io/campaign/map_object_detection.py
src/comstar_game_ai/game_io/campaign/settlements.py          # FACTION_LEGEND_COLOURS
overlay/agent_skills/campaign_ui_atlas.yaml                  # KB faction_colours
overlay/agent_providers/optional/detect_yolox_nano.yaml
overlay/agent_providers/detect_rtw_campaign.yaml.example
scripts/detection/*                                          # capture/label/train/eval
scripts/accept_detect_smoke.py
scripts/accept_cv_besiege_segesta.py
scripts/accept_yolo_besiege_segesta.py
docs/yolox-rtw-detection.md
docs/settlement-detector-handoff.md
config/default.yaml                                          # ao.detection_* 
```

---

## 8. Reasoning for not going with YOLO (settlements)

1. **Cutover gate failed in live conditions.** Val AP ~70–76 did not produce recall ≥ 0.9 vs CV on the campaign map. Optimistic val (few towns, correlated views) overstated readiness.

2. **OpenCV already solves the settlement job structurally.** Rim/core badge geometry + hue bands (from KB + live) finds the plaques we need for click targeting. YOLO must *beat* that bar, not merely exist.

3. **Confusion with army/agent banners.** Rectangular faction banners share colours/logos with settlement badges. Without a strong `army_stack` class (or hard negatives), YOLO treats banners as badges—dangerous for actuation.

4. **Class that matters for YOLO was never trained.** Product plan: YOLO owns **armies/ships**. Final datasets had **0** `army_stack` and **0** `ship` labels. Settlement YOLO was a detour relative to the hybrid design.

5. **Data ceiling is multi-view, not more unique towns.** ~11 early-campaign settlements; Sicily pass barely added CV labels until blue hue existed. More NE pans do not create a new problem distribution.

6. **Operational risk on Ada overlay.** Object-detection in the default overlay destabilized Reach WS. Shipping RTW weights into production overlay was deferred intentionally.

7. **Oval semantics unfinished.** Training “oval” = nameplate crop, not measured ground-town oval. Even a perfect nameplate detector would not replace `CLICK_OFFSET_PX` calibration for click-to-settle.

**Therefore:** keep **CV for settlements**; treat RTW YOLO ONNX as experimental; next YOLO investment should be **labeled army_stack/ship**, then hybrid accept (`accept_yolo_besiege_segesta.py`), then cautious Reach publish—not settlement cutover.

---

## 9. Recommended next steps (for a later agent)

1. Park settlement-YOLO cutover unless doing one deliberate **very close-zoom** plaque recall pass.
2. Manual / Label Studio labels for `army_stack` (+ coastal `ship`); retrain; live army accept.
3. Only then publish `client.detect_rtw_campaign` with ONNX on Ada artifact cache—still keep detection out of default overlay until WS is proven.
4. Measure `CLICK_OFFSET_PX` if ground-oval clicks are required.

---

## 10. One-paragraph summary for Claude

COMSTAR wired Megvii YOLOX detection through Reach (catalog smoke + RTW agent scaffolding), built a CV-auto-labeled COCO dataset (~275 frames, 257 badge/oval pairs after hue-band expansion), trained YOLOX-Nano on Ada to ~76 val AP, and exported ONNX locally. Live CV-vs-YOLO cutover never passed (best live recall ~0.25 with rare precise ovals; badges often missed or confused with army banners). Settlements therefore remain OpenCV; custom YOLO is not on the actuate path; armies/ships were never properly labeled. Archive of eval frames, val sample, hue learning artifacts, and ONNX is at `docs/design/assets/yolox-rtw-claude-handoff-archive.zip`.
